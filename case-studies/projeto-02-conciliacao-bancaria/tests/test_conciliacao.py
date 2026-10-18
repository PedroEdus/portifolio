"""
Suíte de Testes Automatizados (pytest) - Projeto 02:
Motor de Conciliação Bancária, Recálculo de 5 Pernas Contábeis e Auditoria de Ciclos.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = PROJECT_DIR.parent.parent
SYNTHETIC_DIR = WORKSPACE_DIR / "shared" / "synthetic-data"

sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(SYNTHETIC_DIR))
if "src" in sys.modules and Path(getattr(sys.modules["src"], "__file__", "")).resolve().parent != (PROJECT_DIR / "src").resolve():
    del sys.modules["src"]

from generate_all import generate_reconciliation_dataset  # noqa: E402
from src.engine_conciliacao import (  # noqa: E402
    audit_reconciliation_cycles,
    calculate_icp_and_coverage_sentinel,
    compute_easter_meeus_butcher,
    get_febraban_holidays,
    is_febraban_business_day,
    purge_intermediation_pairs_r3,
    recalculate_five_legs_and_confront_extrato,
)


def test_accounting_equation_and_five_legs_parity() -> None:
    """
    (1) Valida a equação contábil fundamental (SF = SI + C - D) e comprova
    100% de paridade nas 5 pernas do razão ERP contra o extrato bancário oficial
    após o expurgo R3 (e comprova que sem R3 os créditos/débitos ficam inflados).
    """
    datasets = generate_reconciliation_dataset(seed=42)

    df_com_r3, df_purged = recalculate_five_legs_and_confront_extrato(
        perna_extrato=datasets["perna_extrato"],
        perna_recebepgto=datasets["perna_recebepgto"],
        perna_depositos=datasets["perna_depositos"],
        perna_entsai_aplic=datasets["perna_entsai_aplic"],
        perna_transf=datasets["perna_transf"],
        extrato_bancario=datasets["extrato_bancario"],
        apply_r3=True,
    )
    assert len(df_com_r3) > 0
    assert df_com_r3["equacao_extrato_valida"].all()
    assert df_com_r3["paridade_5pernas_ok"].all()
    assert len(df_purged) == 80  # 40 pares casados (TipoControle 5 e 6)

    # Sem o expurgo R3, todos os dias possuem créditos e débitos inflados pelos pares transitórios
    df_sem_r3, _ = recalculate_five_legs_and_confront_extrato(
        perna_extrato=datasets["perna_extrato"],
        perna_recebepgto=datasets["perna_recebepgto"],
        perna_depositos=datasets["perna_depositos"],
        perna_entsai_aplic=datasets["perna_entsai_aplic"],
        perna_transf=datasets["perna_transf"],
        extrato_bancario=datasets["extrato_bancario"],
        apply_r3=False,
    )
    assert not df_sem_r3["paridade_5pernas_ok"].any()
    assert (df_sem_r3["diff_creditos"] > 0).all()
    assert (df_sem_r3["diff_debitos"] > 0).all()


def test_r3_purge_matched_pairs_vs_preserve_orphans() -> None:
    """
    (2) Valida o algoritmo R3 de casamento e expurgo de lançamentos transitórios
    na natureza '0071': deve remover apenas os pares casados (TipoControle = 5 e 6)
    na mesma chave (cod_empresa, cod_banco, conta_bancaria, proposta, valor) e
    preservar lançamentos unilaterais (órfãos).
    """
    df_sample = pd.DataFrame(
        [
            # Par casado 1 (deve ser expurgado)
            {
                "id_lancamento": "L1",
                "cod_empresa": 101,
                "cod_banco": 341,
                "conta_bancaria": "CC-101-001",
                "data_movimento": "2026-04-02",
                "natureza": "0071",
                "tipo_controle": 5,
                "proposta": "PROP-CASADA-01",
                "natureza_dc": "C",
                "valor": 2500.00,
            },
            {
                "id_lancamento": "L2",
                "cod_empresa": 101,
                "cod_banco": 341,
                "conta_bancaria": "CC-101-001",
                "data_movimento": "2026-04-02",
                "natureza": "0071",
                "tipo_controle": 6,
                "proposta": "PROP-CASADA-01",
                "natureza_dc": "D",
                "valor": 2500.00,
            },
            # Lançamento unilateral órfão na natureza '0071' (NÃO tem par TipoControle=6, deve ser preservado!)
            {
                "id_lancamento": "L3-ORFAO",
                "cod_empresa": 101,
                "cod_banco": 341,
                "conta_bancaria": "CC-101-001",
                "data_movimento": "2026-04-02",
                "natureza": "0071",
                "tipo_controle": 5,
                "proposta": "PROP-UNILATERAL-99",
                "natureza_dc": "C",
                "valor": 850.00,
            },
            # Lançamento normal de outra natureza (deve ser preservado)
            {
                "id_lancamento": "L4-NORMAL",
                "cod_empresa": 101,
                "cod_banco": 341,
                "conta_bancaria": "CC-101-001",
                "data_movimento": "2026-04-02",
                "natureza": "0010",
                "tipo_controle": 2,
                "proposta": "PROP-NORMAL-01",
                "natureza_dc": "C",
                "valor": 1200.00,
            },
        ]
    )

    df_clean, df_purged = purge_intermediation_pairs_r3(df_sample)
    assert set(df_purged["id_lancamento"]) == {"L1", "L2"}
    assert set(df_clean["id_lancamento"]) == {"L3-ORFAO", "L4-NORMAL"}


def test_reconciliation_cycle_and_in_place_overwrite_detection() -> None:
    """
    (3) Valida o motor de ciclo de conciliação sobre múltiplos snapshots (Num_exa 1..N)
    e a detecção da anomalia de sobrescrita `validacao_in_place` (quando `Status_exa = 2`
    foi gravado diretamente no `Num_exa = 1`, calculando `MAX(data_validacao) - MIN(data_criacao)`).
    """
    datasets = generate_reconciliation_dataset(seed=42)
    df_ciclos = audit_reconciliation_cycles(datasets["snapshots_ciclo"]).set_index(
        "id_item_extrato"
    )

    # ITEM-1001: fluxo padrão (abriu com 0 no Num_exa=1 em 2026-04-01, validou com 2 no Num_exa=3 em 2026-04-04 -> 3 dias)
    item1 = df_ciclos.loc["ITEM-1001"]
    assert item1["status_inicial"] == 0
    assert item1["status_final"] == 2
    assert bool(item1["validacao_in_place"]) is False
    assert item1["dias_para_conciliar"] == 3
    assert item1["classificacao_ciclo"] == "CONCILIADO_FLUXO_PADRAO"

    # ITEM-1002: anomalia de validação in-place (já apareceu com Status_exa=2 no Num_exa=1;
    # data_criacao = 2026-04-02 e MAX(data_validacao) = 2026-04-09 -> 7 dias)
    item2 = df_ciclos.loc["ITEM-1002"]
    assert item2["status_inicial"] == 2
    assert item2["status_final"] == 2
    assert bool(item2["validacao_in_place"]) is True
    assert item2["dias_para_conciliar"] == 7
    assert item2["classificacao_ciclo"] == "CONCILIADO_IN_PLACE_OVERWRITE"

    # ITEM-1003: ainda pendente (status_final = 0)
    item3 = df_ciclos.loc["ITEM-1003"]
    assert item3["status_final"] == 0
    assert pd.isna(item3["dias_para_conciliar"])
    assert item3["classificacao_ciclo"] == "PENDENTE_ABERTO"


def test_meeus_butcher_easter_and_febraban_holidays() -> None:
    """
    (4) Valida o algoritmo astronômico de Meeus/Butcher para o Domingo de Páscoa
    e o calendário de feriados móveis e fixos da FEBRABAN.
    """
    assert compute_easter_meeus_butcher(2024) == date(2024, 3, 31)
    assert compute_easter_meeus_butcher(2025) == date(2025, 4, 20)
    assert compute_easter_meeus_butcher(2026) == date(2026, 4, 5)
    assert compute_easter_meeus_butcher(2027) == date(2027, 3, 28)

    holidays_2026 = get_febraban_holidays(2026)
    # Carnaval 2026: 16 e 17 de fevereiro
    assert date(2026, 2, 16) in holidays_2026
    assert date(2026, 2, 17) in holidays_2026
    # Sexta-feira da Paixão 2026: 3 de abril
    assert date(2026, 4, 3) in holidays_2026
    # Corpus Christi 2026: 4 de junho
    assert date(2026, 6, 4) in holidays_2026

    assert is_febraban_business_day(date(2026, 4, 3)) is False  # Sexta-Feira Santa
    assert is_febraban_business_day(date(2026, 4, 4)) is False  # Sábado
    assert is_febraban_business_day(date(2026, 4, 6)) is True   # Segunda-feira útil


def test_icp_calculation_and_moving_median_sentinel() -> None:
    """
    (5) Valida o cálculo do ICP separando Contas Correntes vs Contas de Aplicação
    no denominador e testa o disparo da sentinela de cobertura (mediana móvel de 10 dias úteis).
    """
    datasets = generate_reconciliation_dataset(seed=42)
    icp_res = calculate_icp_and_coverage_sentinel(
        df_contas=datasets["contas_bancarias"],
        df_extrato=datasets["extrato_bancario"],
        start_date="2026-04-01",
        end_date="2026-04-15",
    )

    # 3 Contas Correntes com 100% de cobertura nos 10 dias úteis FEBRABAN entre 01/04 e 15/04/2026
    assert icp_res["dias_uteis_febraban_no_periodo"] == 10
    assert icp_res["total_contas_correntes_denominador"] == 3
    assert icp_res["total_contas_aplicacao_excluidas_denominador"] == 1
    assert icp_res["icp_global_contas_correntes_pct"] == 100.0
    # Se incluísse erroneamente a conta de aplicação no denominador diário, o ICP cairia para 85.0%
    assert icp_res["icp_ingenuo_sem_expurgo_aplicacao_pct"] == 85.0
    assert icp_res["alertas_sentinela_disparados"] == 0

    # Simula falha de ingestão de extratos no último dia útil (2026-04-15) para disparar a sentinela
    df_extrato_falha = datasets["extrato_bancario"][
        ~(
            (datasets["extrato_bancario"]["data_movimento"] == "2026-04-15")
            & (
                datasets["extrato_bancario"]["conta_bancaria"].isin(
                    ["CC-101-001", "CC-102-001"]
                )
            )
        )
    ].copy()

    icp_falha = calculate_icp_and_coverage_sentinel(
        df_contas=datasets["contas_bancarias"],
        df_extrato=df_extrato_falha,
        start_date="2026-04-01",
        end_date="2026-04-15",
    )
    assert icp_falha["alertas_sentinela_disparados"] == 1
    last_day = icp_falha["serie_diaria"].iloc[-1]
    assert bool(last_day["alerta_sentinela_queda"]) is True
