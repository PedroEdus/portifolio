"""
Máquina do Tempo de Estoque Imobiliário Multi-CRM/ERP (2017–2026).

Reconcilia eventos históricos oriundos de múltiplos sistemas legados e atuais
(Sienge, Dynamics, Construtor de Vendas - CV, Anapro) e reconstrói a
Fotografia Mensal de Estoque (Unidade × Mês).

Destaque de Engenharia:
- Resolução determinística de anomalias cronológicas (`corrigir_conflito_cronologico`):
  quando a formalização contábil do Distrato do contrato N ocorre em data posterior
  à nova Venda (contrato N+1) da mesma unidade imobiliária, o distrato não pode
  sobrescrever o estado ativo da venda N+1 na linha do tempo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

import pandas as pd

VALID_STATES = (
    "Disponível",
    "Assinatura Pendente",
    "Vendida",
    "Distratada",
    "Permutante",
)


@dataclass(frozen=True)
class UnidadeImobiliaria:
    """Cadastro base de uma unidade autônoma de empreendimento imobiliário."""

    id_unidade: str
    empreendimento: str
    data_lancamento: str  # YYYY-MM-DD
    is_permuta: bool = False


@dataclass(frozen=True)
class EventoContratual:
    """
    Evento transacional registrado no ERP/CRM (Sienge, Dynamics, CV ou Anapro).

    `tipo_evento` pode ser:
    - 'PROPOSTA_ASSINATURA' -> leva ao estado 'Assinatura Pendente'
    - 'VENDA'               -> leva ao estado 'Vendida'
    - 'REPASSE_ASSOCIATIVO' -> mantém/confirma o estado 'Vendida'
    - 'DISTRATO'            -> leva ao estado 'Distratada' (se pertencer ao contrato vigente)
    """

    id_unidade: str
    numero_contrato: int
    tipo_evento: str
    data_evento: str  # YYYY-MM-DD
    origem_sistema: str = "Sienge"


def corrigir_conflito_cronologico(df_eventos: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta e corrige anomalias temporais onde o registro de `DISTRATO` de um
    contrato anterior (N) possui `data_evento` posterior à `VENDA` ou `PROPOSTA_ASSINATURA`
    de um contrato mais recente (N+1) da mesma unidade.

    Regra de reconciliação:
    1. Para cada unidade e contrato, identifica se existe um contrato sucessor (M > N)
       com evento de ativação (`VENDA` ou `PROPOSTA_ASSINATURA`).
    2. Se o `DISTRATO` do contrato N ocorreu após o início do contrato sucessor M,
       a data efetiva do distrato de N é retroagida para 1 dia antes da ativação de M
       (e marcada com `conflito_cronologico_corrigido = True`), impedindo que o distrato
       tardio do contrato antigo contamine a fotografia mensal da venda nova.
    """
    if df_eventos.empty:
        return df_eventos.copy()

    df = df_eventos.copy()
    df["data_evento_original"] = pd.to_datetime(df["data_evento"])
    df["data_evento_efetiva"] = df["data_evento_original"]
    df["conflito_cronologico_corrigido"] = False

    # Identifica a data mínima de ativação (VENDA ou PROPOSTA_ASSINATURA) de cada (id_unidade, numero_contrato)
    ativacoes = df[df["tipo_evento"].isin(["VENDA", "PROPOSTA_ASSINATURA", "REPASSE_ASSOCIATIVO"])]
    inicio_por_contrato = (
        ativacoes.groupby(["id_unidade", "numero_contrato"])["data_evento_original"]
        .min()
        .reset_index()
        .rename(columns={"data_evento_original": "data_inicio_contrato"})
    )

    for idx, row in df[df["tipo_evento"] == "DISTRATO"].iterrows():
        unidade = row["id_unidade"]
        contrato_n = int(row["numero_contrato"])
        data_distrato_n = row["data_evento_original"]

        contratos_posteriores = inicio_por_contrato[
            (inicio_por_contrato["id_unidade"] == unidade)
            & (inicio_por_contrato["numero_contrato"] > contrato_n)
        ]

        if not contratos_posteriores.empty:
            menor_inicio_sucessor = contratos_posteriores["data_inicio_contrato"].min()
            if data_distrato_n >= menor_inicio_sucessor:
                df.loc[idx, "data_evento_efetiva"] = menor_inicio_sucessor - pd.Timedelta(days=1)
                df.loc[idx, "conflito_cronologico_corrigido"] = True

    # Ordena cronologicamente pela data efetiva e pelo número do contrato
    prioridade_evento = {
        "DISTRATO": 1,
        "PROPOSTA_ASSINATURA": 2,
        "VENDA": 3,
        "REPASSE_ASSOCIATIVO": 4,
    }
    df["_ordem_tipo"] = df["tipo_evento"].map(lambda x: prioridade_evento.get(x, 9))
    df = (
        df.sort_values(
            by=["id_unidade", "data_evento_efetiva", "numero_contrato", "_ordem_tipo"],
            ascending=[True, True, True, True],
        )
        .drop(columns=["_ordem_tipo"])
        .reset_index(drop=True)
    )
    return df


def mapear_evento_para_estado(tipo_evento: str) -> str:
    """Converte o tipo de evento transacional no estado canônico do estoque."""
    mapa: Dict[str, str] = {
        "PROPOSTA_ASSINATURA": "Assinatura Pendente",
        "VENDA": "Vendida",
        "REPASSE_ASSOCIATIVO": "Vendida",
        "DISTRATO": "Distratada",
    }
    if tipo_evento not in mapa:
        raise ValueError(f"Tipo de evento desconhecido: '{tipo_evento}'.")
    return mapa[tipo_evento]


def reconstruir_fotografia_mensal(
    unidades: Sequence[UnidadeImobiliaria],
    eventos: Sequence[EventoContratual],
    mes_inicio: str,
    mes_fim: str,
) -> pd.DataFrame:
    """
    Expande a grade cartesiana (Unidade × Competência Mensal) entre `mes_inicio` e `mes_fim`
    (formato `YYYY-MM`) e propaga o estado determinístico de cada unidade no fechamento de cada mês.
    """
    grade_meses = pd.period_range(start=mes_inicio, end=mes_fim, freq="M")

    df_raw_eventos = pd.DataFrame(
        [
            {
                "id_unidade": e.id_unidade,
                "numero_contrato": e.numero_contrato,
                "tipo_evento": e.tipo_evento,
                "data_evento": e.data_evento,
                "origem_sistema": e.origem_sistema,
            }
            for e in eventos
        ]
    )

    if not df_raw_eventos.empty:
        df_eventos_corrigidos = corrigir_conflito_cronologico(df_raw_eventos)
        df_eventos_corrigidos["competencia_efetiva"] = df_eventos_corrigidos[
            "data_evento_efetiva"
        ].dt.to_period("M")
    else:
        df_eventos_corrigidos = pd.DataFrame()

    registros_fotografia: List[Dict[str, object]] = []

    for u in unidades:
        comp_lancamento = pd.Period(u.data_lancamento[:7], freq="M")
        ev_unidade = (
            df_eventos_corrigidos[df_eventos_corrigidos["id_unidade"] == u.id_unidade]
            if not df_eventos_corrigidos.empty
            else pd.DataFrame()
        )

        for comp in grade_meses:
            if comp < comp_lancamento:
                continue

            if u.is_permuta:
                registros_fotografia.append(
                    {
                        "id_unidade": u.id_unidade,
                        "empreendimento": u.empreendimento,
                        "competencia": str(comp),
                        "estado_estoque": "Permutante",
                        "contrato_vigente": None,
                        "teve_conflito_corrigido": False,
                    }
                )
                continue

            # Eventos ocorridos até o final do mês de competência
            ev_ate_mes = (
                ev_unidade[ev_unidade["competencia_efetiva"] <= comp]
                if not ev_unidade.empty
                else pd.DataFrame()
            )

            if ev_ate_mes.empty:
                estado_atual = "Disponível"
                contrato_atual = None
                conflito_flag = False
            else:
                ultimo_ev = ev_ate_mes.iloc[-1]
                estado_atual = mapear_evento_para_estado(str(ultimo_ev["tipo_evento"]))
                contrato_atual = int(ultimo_ev["numero_contrato"])
                conflito_flag = bool(ev_ate_mes["conflito_cronologico_corrigido"].any())

            registros_fotografia.append(
                {
                    "id_unidade": u.id_unidade,
                    "empreendimento": u.empreendimento,
                    "competencia": str(comp),
                    "estado_estoque": estado_atual,
                    "contrato_vigente": contrato_atual,
                    "teve_conflito_corrigido": conflito_flag,
                }
            )

    return pd.DataFrame(registros_fotografia)
