"""
Motor de Conciliação Bancária, Recálculo de 5 Pernas Contábeis e Auditoria de Ciclos.

Reproduz a engenharia de dados e auditoria contábil desenvolvida em produção
no Microsoft Fabric (`ws_financeiro` - Brasil Terrenos / Buriti Empreendimentos):

a) Recálculo independente das 5 pernas do razão ERP (`Extrato`, `RecebePgto`,
   `Depositos`, `EntSaiEmpAplic`, `VwTransfBcoExtrato`) confrontado contra o
   extrato bancário oficial (`SF = SI + C - D`).
b) Algoritmo de casamento e expurgo de lançamentos transitórios de intermediação (`R3`):
   remove pares casados `(TipoControle = 5, TipoControle = 6)` na natureza `'0071'` por
   `(cod_empresa, cod_banco, conta_bancaria, proposta)`, preservando casos unilaterais reais.
c) Motor de Ciclo de Conciliação sobre múltiplos snapshots (`Num_exa 1..N`):
   calcula `status_inicial`, `status_final`, `dias_para_conciliar` e detecta a anomalia
   de `validacao_in_place` (`Status_exa = 2` sobrescrito já no `Num_exa = 1`, calculando
   `MAX(data_validacao) - MIN(data_criacao)`).
d) Calendário Bancário FEBRABAN com feriados móveis via algoritmo de Meeus/Butcher para
   a Páscoa, separação de Contas Correntes vs Contas de Aplicação no denominador do ICP
   e sentinela de cobertura de extratos (mediana móvel de 10 dias úteis).

AVISO DE CONFIDENCIALIDADE:
Todos os dados processados por este módulo são 100% sintéticos (`seed=42`).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


# =============================================================================
# d.1) Calendário Bancário FEBRABAN & Algoritmo de Meeus/Butcher para a Páscoa
# =============================================================================
def compute_easter_meeus_butcher(year: int) -> date:
    """
    Calcula o Domingo de Páscoa para qualquer ano do calendário Gregoriano
    utilizando o algoritmo astronômico exato de Meeus/Jones/Butcher.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l_val = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_val) // 451
    month = (h + l_val - 7 * m + 114) // 31
    day = ((h + l_val - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_febraban_holidays(year: int) -> Dict[date, str]:
    """
    Retorna o dicionário de feriados bancários nacionais FEBRABAN (fixos e móveis)
    para o ano especificado.
    Feriados móveis derivados da Páscoa (Meeus/Butcher):
      - Segunda-feira de Carnaval: Páscoa - 48 dias
      - Terça-feira de Carnaval:   Páscoa - 47 dias
      - Sexta-feira da Paixão:     Páscoa - 2 dias
      - Corpus Christi:            Páscoa + 60 dias
    """
    easter = compute_easter_meeus_butcher(year)
    holidays: Dict[date, str] = {
        # Feriados Nacionais Fixos
        date(year, 1, 1): "Confraternização Universal",
        date(year, 4, 21): "Tiradentes",
        date(year, 5, 1): "Dia do Trabalho",
        date(year, 9, 7): "Independência do Brasil",
        date(year, 10, 12): "Nossa Senhora Aparecida",
        date(year, 11, 2): "Finados",
        date(year, 11, 15): "Proclamação da República",
        date(year, 11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
        date(year, 12, 25): "Natal",
        # Feriados Bancários Móveis FEBRABAN
        easter - timedelta(days=48): "Segunda-feira de Carnaval",
        easter - timedelta(days=47): "Terça-feira de Carnaval",
        easter - timedelta(days=2): "Sexta-feira da Paixão",
        easter + timedelta(days=60): "Corpus Christi",
    }
    return holidays


def is_febraban_business_day(dt: date) -> bool:
    """Retorna True se a data for um dia útil bancário segundo o calendário FEBRABAN."""
    if dt.weekday() >= 5:
        return False
    holidays = get_febraban_holidays(dt.year)
    return dt not in holidays


# =============================================================================
# b) Algoritmo de Casamento e Expurgo de Intermediação Transitória (Regra R3)
# =============================================================================
def purge_intermediation_pairs_r3(
    df_ledger: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Aplica a Regra R3 sobre os lançamentos das pernas do razão ERP:
    - Identifica lançamentos na natureza `'0071'` com `tipo_controle` em `(5, 6)`.
    - Pareia 1-para-1 lançamentos `(TipoControle = 5 [Crédito], TipoControle = 6 [Débito])`
      que compartilham a mesma chave `(cod_empresa, cod_banco, conta_bancaria, proposta)`
      e mesmo `valor` (com pareamento determinístico por data/id).
    - Expurga exclusivamente os pares casados (que se anulam mutuamente e não existem no
      extrato bancário real).
    - Preserva rigorosamente lançamentos `'0071'` unilaterais (órfãos), pois representam
      movimentações efetivas de caixa.
    """
    if df_ledger.empty:
        return df_ledger.copy(), df_ledger.copy()

    df_work = df_ledger.copy().reset_index(drop=True)
    candidatos_mask = (
        (df_work["natureza"].astype(str) == "0071")
        & (df_work["tipo_controle"].isin([5, 6]))
        & (df_work["proposta"].notna())
    )

    df_candidatos = df_work[candidatos_mask].copy()
    if df_candidatos.empty:
        return df_work, pd.DataFrame(columns=df_work.columns)

    indices_para_expurgar: List[int] = []
    group_cols = ["cod_empresa", "cod_banco", "conta_bancaria", "proposta", "valor"]

    for _, grp in df_candidatos.groupby(group_cols, dropna=False):
        idx_ctrl_5 = list(grp[grp["tipo_controle"] == 5].index)
        idx_ctrl_6 = list(grp[grp["tipo_controle"] == 6].index)
        n_pares = min(len(idx_ctrl_5), len(idx_ctrl_6))
        if n_pares > 0:
            indices_para_expurgar.extend(idx_ctrl_5[:n_pares])
            indices_para_expurgar.extend(idx_ctrl_6[:n_pares])

    purged_set = set(indices_para_expurgar)
    df_purged = df_work.loc[sorted(purged_set)].copy().reset_index(drop=True)
    df_clean = (
        df_work.loc[[i for i in df_work.index if i not in purged_set]]
        .copy()
        .reset_index(drop=True)
    )
    return df_clean, df_purged


# =============================================================================
# a) Recálculo Independente das 5 Pernas do Razão ERP vs Extrato Bancário
# =============================================================================
def recalculate_five_legs_and_confront_extrato(
    perna_extrato: pd.DataFrame,
    perna_recebepgto: pd.DataFrame,
    perna_depositos: pd.DataFrame,
    perna_entsai_aplic: pd.DataFrame,
    perna_transf: pd.DataFrame,
    extrato_bancario: pd.DataFrame,
    apply_r3: bool = True,
    tolerance: float = 0.01,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Unifica as 5 pernas do razão ERP (`Extrato`, `RecebePgto`, `Depositos`,
    `EntSaiEmpAplic`, `VwTransfBcoExtrato`), aplica o expurgo `R3` (quando ativo)
    e confronta a equação contábil `SF = SI + C - D` contra o extrato bancário oficial
    para cada `(cod_empresa, cod_banco, conta_bancaria, data_movimento)`.
    """
    df_all_legs = pd.concat(
        [
            perna_extrato,
            perna_recebepgto,
            perna_depositos,
            perna_entsai_aplic,
            perna_transf,
        ],
        ignore_index=True,
    )

    if apply_r3:
        df_clean_legs, df_purged_r3 = purge_intermediation_pairs_r3(df_all_legs)
    else:
        df_clean_legs = df_all_legs.copy()
        df_purged_r3 = pd.DataFrame(columns=df_all_legs.columns)

    df_clean_legs["vlr_credito"] = np.where(
        df_clean_legs["natureza_dc"].str.upper() == "C",
        df_clean_legs["valor"].astype(float),
        0.0,
    )
    df_clean_legs["vlr_debito"] = np.where(
        df_clean_legs["natureza_dc"].str.upper() == "D",
        df_clean_legs["valor"].astype(float),
        0.0,
    )

    df_erp_agg = (
        df_clean_legs.groupby(
            ["cod_empresa", "cod_banco", "conta_bancaria", "data_movimento"],
            as_index=False,
        )
        .agg(
            creditos_erp_5pernas=("vlr_credito", "sum"),
            debitos_erp_5pernas=("vlr_debito", "sum"),
            qtd_lancamentos_erp=("id_lancamento", "count"),
        )
    )
    df_erp_agg["creditos_erp_5pernas"] = df_erp_agg["creditos_erp_5pernas"].round(2)
    df_erp_agg["debitos_erp_5pernas"] = df_erp_agg["debitos_erp_5pernas"].round(2)

    df_confronto = extrato_bancario.merge(
        df_erp_agg,
        on=["cod_empresa", "cod_banco", "conta_bancaria", "data_movimento"],
        how="left",
    )
    df_confronto["creditos_erp_5pernas"] = df_confronto[
        "creditos_erp_5pernas"
    ].fillna(0.0)
    df_confronto["debitos_erp_5pernas"] = df_confronto[
        "debitos_erp_5pernas"
    ].fillna(0.0)
    df_confronto["qtd_lancamentos_erp"] = (
        df_confronto["qtd_lancamentos_erp"].fillna(0).astype(int)
    )

    # Equação fundamental do saldo: SF = SI + C - D
    df_confronto["saldo_final_esperado_extrato"] = (
        df_confronto["saldo_inicial"]
        + df_confronto["creditos_extrato"]
        - df_confronto["debitos_extrato"]
    ).round(2)

    df_confronto["saldo_final_recalculado_5pernas"] = (
        df_confronto["saldo_inicial"]
        + df_confronto["creditos_erp_5pernas"]
        - df_confronto["debitos_erp_5pernas"]
    ).round(2)

    df_confronto["diff_creditos"] = (
        df_confronto["creditos_erp_5pernas"] - df_confronto["creditos_extrato"]
    ).round(2)
    df_confronto["diff_debitos"] = (
        df_confronto["debitos_erp_5pernas"] - df_confronto["debitos_extrato"]
    ).round(2)
    df_confronto["diff_saldo_final"] = (
        df_confronto["saldo_final_recalculado_5pernas"] - df_confronto["saldo_final"]
    ).round(2)

    df_confronto["equacao_extrato_valida"] = (
        df_confronto["saldo_final_esperado_extrato"] - df_confronto["saldo_final"]
    ).abs() <= tolerance

    df_confronto["paridade_5pernas_ok"] = (
        (df_confronto["diff_creditos"].abs() <= tolerance)
        & (df_confronto["diff_debitos"].abs() <= tolerance)
        & (df_confronto["diff_saldo_final"].abs() <= tolerance)
        & df_confronto["equacao_extrato_valida"]
    )

    return df_confronto, df_purged_r3


# =============================================================================
# c) Motor de Ciclo de Conciliação sobre Múltiplos Snapshots (Num_exa 1..N)
# =============================================================================
def audit_reconciliation_cycles(df_snapshots: pd.DataFrame) -> pd.DataFrame:
    """
    Audita o ciclo de vida de conciliação de cada item ao longo dos snapshots `num_exa 1..N`:
    - Calcula `status_inicial` (no menor `num_exa`) e `status_final` (no maior `num_exa`).
    - Detecta a anomalia `validacao_in_place`: ocorre quando `status_inicial == 2` já no
      `num_exa == 1` (o ERP sobrescreveu o status no snapshot inicial em vez de preservar
      `status_exa = 0` na abertura).
    - Calcula `dias_para_conciliar` usando `MAX(data_validacao) - MIN(data_criacao)` para
      todos os itens conciliados (`status_final == 2`), recuperando o lead time real mesmo
      quando houve sobrescrita in-place.
    """
    df_sorted = df_snapshots.sort_values(["id_item_extrato", "num_exa"]).reset_index(
        drop=True
    )
    records: List[Dict[str, Any]] = []

    for item_id, grp in df_sorted.groupby("id_item_extrato", sort=False):
        first_row = grp.iloc[0]
        last_row = grp.iloc[-1]

        status_inicial = int(first_row["status_exa"])
        status_final = int(last_row["status_exa"])
        min_num_exa = int(first_row["num_exa"])
        max_num_exa = int(last_row["num_exa"])

        dt_criacao_min = pd.to_datetime(grp["data_criacao"].dropna()).min()
        validacoes_validas = pd.to_datetime(grp["data_validacao"].dropna())
        dt_validacao_max = (
            validacoes_validas.max() if not validacoes_validas.empty else pd.NaT
        )

        # Anomalia de sobrescrita in-place: já nasce com Status_exa = 2 no Num_exa = 1
        validacao_in_place = bool(min_num_exa == 1 and status_inicial == 2)

        if status_final == 2 and pd.notna(dt_validacao_max) and pd.notna(dt_criacao_min):
            dias_para_conciliar: int | None = int(
                (dt_validacao_max - dt_criacao_min).days
            )
        else:
            dias_para_conciliar = None

        if status_final != 2:
            classificacao = "PENDENTE_ABERTO"
        elif validacao_in_place:
            classificacao = "CONCILIADO_IN_PLACE_OVERWRITE"
        else:
            classificacao = "CONCILIADO_FLUXO_PADRAO"

        records.append(
            {
                "id_item_extrato": item_id,
                "cod_empresa": int(first_row["cod_empresa"]),
                "conta_bancaria": str(first_row["conta_bancaria"]),
                "num_snapshots": len(grp),
                "min_num_exa": min_num_exa,
                "max_num_exa": max_num_exa,
                "status_inicial": status_inicial,
                "status_final": status_final,
                "min_data_criacao": dt_criacao_min.strftime("%Y-%m-%d")
                if pd.notna(dt_criacao_min)
                else None,
                "max_data_validacao": dt_validacao_max.strftime("%Y-%m-%d")
                if pd.notna(dt_validacao_max)
                else None,
                "validacao_in_place": validacao_in_place,
                "dias_para_conciliar": dias_para_conciliar,
                "classificacao_ciclo": classificacao,
            }
        )

    return pd.DataFrame(records)


# =============================================================================
# d.2) Cálculo do ICP (Contas Correntes vs Aplicação) e Sentinela de 10 Dias Úteis
# =============================================================================
def calculate_icp_and_coverage_sentinel(
    df_contas: pd.DataFrame,
    df_extrato: pd.DataFrame,
    start_date: str,
    end_date: str,
    window_business_days: int = 10,
    alert_drop_ratio: float = 0.80,
) -> Dict[str, Any]:
    """
    Calcula o Índice de Cobertura de Processamento de Extratos (ICP) sobre o calendário
    bancário FEBRABAN:
    - Separa estritamente `CONTA_CORRENTE` vs `CONTA_APLICACAO`: apenas contas correntes
      ativas entram no denominador diário obrigatório do ICP (contas de aplicação não
      emitem extrato diário contínuo).
    - Calcula a sentinela de cobertura baseada na mediana móvel de `window_business_days`
      (10 dias úteis) para detectar quedas abruptas de recepção de extratos.
    """
    dt_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    dt_end = datetime.strptime(end_date, "%Y-%m-%d").date()

    business_days: List[str] = []
    cur = dt_start
    while cur <= dt_end:
        if is_febraban_business_day(cur):
            business_days.append(cur.isoformat())
        cur += timedelta(days=1)

    contas_correntes = set(
        df_contas[df_contas["tipo_conta"] == "CONTA_CORRENTE"]["conta_bancaria"].unique()
    )
    contas_aplicacao = set(
        df_contas[df_contas["tipo_conta"] == "CONTA_APLICACAO"]["conta_bancaria"].unique()
    )
    n_cc_denominador = len(contas_correntes)

    daily_rows: List[Dict[str, Any]] = []
    for bday in business_days:
        df_dia = df_extrato[df_extrato["data_movimento"] == bday]
        cc_presentes = len(
            set(df_dia["conta_bancaria"]).intersection(contas_correntes)
        )
        aplic_presentes = len(
            set(df_dia["conta_bancaria"]).intersection(contas_aplicacao)
        )
        icp_dia_pct = (
            round((cc_presentes / n_cc_denominador) * 100.0, 2)
            if n_cc_denominador > 0
            else 0.0
        )
        daily_rows.append(
            {
                "data_util_febraban": bday,
                "denominador_contas_correntes": n_cc_denominador,
                "contas_correntes_com_extrato": cc_presentes,
                "contas_aplicacao_com_extrato": aplic_presentes,
                "icp_diario_pct": icp_dia_pct,
            }
        )

    df_daily = pd.DataFrame(daily_rows)
    if not df_daily.empty:
        df_daily["mediana_movel_10du_cc"] = (
            df_daily["contas_correntes_com_extrato"]
            .rolling(window=window_business_days, min_periods=1)
            .median()
            .round(2)
        )
        df_daily["alerta_sentinela_queda"] = df_daily[
            "contas_correntes_com_extrato"
        ] < (df_daily["mediana_movel_10du_cc"] * alert_drop_ratio)
    else:
        df_daily["mediana_movel_10du_cc"] = []
        df_daily["alerta_sentinela_queda"] = []

    total_cc_slots = int(df_daily["denominador_contas_correntes"].sum()) if not df_daily.empty else 0
    total_cc_cobertos = int(df_daily["contas_correntes_com_extrato"].sum()) if not df_daily.empty else 0
    icp_global_pct = (
        round((total_cc_cobertos / total_cc_slots) * 100.0, 2)
        if total_cc_slots > 0
        else 0.0
    )

    # Comparação ilustrativa: se as contas de aplicação fossem erroneamente incluídas no denominador
    n_total_ingenuo = len(contas_correntes) + len(contas_aplicacao)
    total_ingenuo_slots = n_total_ingenuo * len(business_days)
    total_ingenuo_cobertos = (
        int(
            (
                df_daily["contas_correntes_com_extrato"]
                + df_daily["contas_aplicacao_com_extrato"]
            ).sum()
        )
        if not df_daily.empty
        else 0
    )
    icp_ingenuo_distorcido_pct = (
        round((total_ingenuo_cobertos / total_ingenuo_slots) * 100.0, 2)
        if total_ingenuo_slots > 0
        else 0.0
    )

    return {
        "dias_uteis_febraban_no_periodo": len(business_days),
        "total_contas_correntes_denominador": n_cc_denominador,
        "total_contas_aplicacao_excluidas_denominador": len(contas_aplicacao),
        "icp_global_contas_correntes_pct": icp_global_pct,
        "icp_ingenuo_sem_expurgo_aplicacao_pct": icp_ingenuo_distorcido_pct,
        "alertas_sentinela_disparados": int(df_daily["alerta_sentinela_queda"].sum())
        if not df_daily.empty
        else 0,
        "serie_diaria": df_daily,
    }
