"""
Suíte de Testes Automatizados (pytest) - Projeto 01:
Plataforma Lakehouse Medallion, Controle Transacional e Matriz Roll-Rate de Recebíveis.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = PROJECT_DIR.parent.parent
SYNTHETIC_DIR = WORKSPACE_DIR / "shared" / "synthetic-data"

sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(SYNTHETIC_DIR))
if "src" in sys.modules and Path(getattr(sys.modules["src"], "__file__", "")).resolve().parent != (PROJECT_DIR / "src").resolve():
    del sys.modules["src"]

from generate_all import generate_receivables_dataset  # noqa: E402
from src.pipeline_lakehouse import (  # noqa: E402
    LakehouseQualityGateError,
    LakehouseRecebiveisPipeline,
)


def test_block_publication_on_schema_drift_and_low_coverage() -> None:
    """
    (1) Testa o bloqueio de publicação quando há Schema Drift ou cobertura < 99.5%,
    garantindo que a Bronze anterior permaneça intacta (promoção Staging-First atômica)
    e valida a regra de dia 1 (`aceitar_calc_defasada`).
    """
    base_datasets = generate_receivables_dataset(seed=42)
    pipeline = LakehouseRecebiveisPipeline(min_coverage_pct=99.5)

    # Primeiro: carga válida promove para Bronze
    status_ok = pipeline.ingest_staging_and_promote_to_bronze(
        datasets=base_datasets,
        data_referencia="2026-01-01",
        aceitar_calc_defasada=True,
    )
    assert status_ok.status == "PUBLICADA"
    bronze_initial_count = len(
        pipeline.db.query_df("SELECT * FROM bronze_contas_receber")
    )

    # Caso A: Schema Drift (coluna inesperada / coluna renomeada na fonte)
    drifted_datasets = copy.deepcopy(base_datasets)
    drifted_datasets["contas_receber"] = drifted_datasets["contas_receber"].rename(
        columns={"ValorNom_prc": "ValorNominal_DRIFT"}
    )
    with pytest.raises(LakehouseQualityGateError, match="Schema Drift"):
        pipeline.ingest_staging_and_promote_to_bronze(
            datasets=drifted_datasets,
            data_referencia="2026-02-01",
            aceitar_calc_defasada=False,
        )

    # Caso B: Cobertura de chaves entre ContasReceber e ContasReceberCalc < 99.5%
    low_cov_datasets = copy.deepcopy(base_datasets)
    # Remove 10% das linhas da tabela de cálculo reajustado (cobertura = 90% < 99.5%)
    n_keep = int(len(low_cov_datasets["contas_receber_calc"]) * 0.90)
    low_cov_datasets["contas_receber_calc"] = (
        low_cov_datasets["contas_receber_calc"].iloc[:n_keep].copy()
    )
    with pytest.raises(LakehouseQualityGateError, match="BLOQUEADO: Cobertura de chaves"):
        pipeline.ingest_staging_and_promote_to_bronze(
            datasets=low_cov_datasets,
            data_referencia="2026-02-01",
            aceitar_calc_defasada=False,
        )

    # Garante que a Bronze original permaneceu 100% intacta após as duas falhas em Staging
    bronze_after_failures = len(
        pipeline.db.query_df("SELECT * FROM bronze_contas_receber")
    )
    assert bronze_after_failures == bronze_initial_count

    # Caso C: Regra de dia 1 (`aceitar_calc_defasada`) quando a data do cálculo está defasada (D-1)
    lagged_calc_datasets = copy.deepcopy(base_datasets)
    lagged_calc_datasets["contas_receber_calc"]["DtCalculo_crc"] = "2025-12-31"

    # Fora do dia 1 (aceitar_calc_defasada=False), deve bloquear:
    with pytest.raises(
        LakehouseQualityGateError,
        match="BLOQUEADO: Cobertura de cálculo atualizado no dia",
    ):
        pipeline.ingest_staging_and_promote_to_bronze(
            datasets=lagged_calc_datasets,
            data_referencia="2026-01-15",
            aceitar_calc_defasada=False,
        )

    # No dia 1 (aceitar_calc_defasada=True), deve permitir com rastreabilidade:
    status_day1 = pipeline.ingest_staging_and_promote_to_bronze(
        datasets=lagged_calc_datasets,
        data_referencia="2026-01-01",
        aceitar_calc_defasada=True,
    )
    assert status_day1.status == "PUBLICADA"
    assert status_day1.aceitar_calc_defasada is True


def test_day1_monthly_snapshot_idempotency() -> None:
    """
    (2) Testa a idempotência da retenção da foto mensal no dia 1 (`replaceWhere` por `DataFoto`).
    Múltiplas execuções na mesma partição não podem duplicar linhas nem afetar outras partições.
    """
    datasets = generate_receivables_dataset(seed=42)
    pipeline = LakehouseRecebiveisPipeline(min_coverage_pct=99.5)
    pipeline.ingest_staging_and_promote_to_bronze(
        datasets=datasets, data_referencia="2026-01-01"
    )

    cnt_exec_1 = pipeline.retain_monthly_snapshot_idempotent("2026-01-01")
    cnt_exec_2 = pipeline.retain_monthly_snapshot_idempotent("2026-01-01")
    cnt_exec_3 = pipeline.retain_monthly_snapshot_idempotent("2026-01-01")

    assert cnt_exec_1 == 240
    assert cnt_exec_1 == cnt_exec_2 == cnt_exec_3

    # Retém também a partição de 2026-02-01 e garante que 2026-01-01 continua com 240 linhas
    cnt_feb = pipeline.retain_monthly_snapshot_idempotent("2026-02-01")
    assert cnt_feb == 240

    total_fotos = len(
        pipeline.db.query_df("SELECT * FROM bronze_foto_mensal_recebiveis")
    )
    assert total_fotos == 480


def test_cessoes_excluded_from_distratos_and_precedence() -> None:
    """
    (3) Testa a exclusão de cessões de direitos (`TipoMnt = 2`) da contagem de distratos
    e verifica a precedência `cedido > cancelado` na Matriz de Transição Roll-Rate.
    """
    datasets = generate_receivables_dataset(seed=42)
    pipeline = LakehouseRecebiveisPipeline(min_coverage_pct=99.5)
    pipeline.ingest_staging_and_promote_to_bronze(
        datasets=datasets, data_referencia="2026-01-01"
    )
    pipeline.build_silver_layer()
    gold = pipeline.build_gold_layer(
        data_foto_m="2026-01-01", data_foto_m1="2026-02-01"
    )

    df_distratos_raw = datasets["distratos"]
    df_cessoes_raw = datasets["cessoes"]
    df_distratos_gold = gold["gold_fato_distratos_auditados"]

    vendas_cedidas = set(
        zip(
            df_cessoes_raw["Empresa_mnt"],
            df_cessoes_raw["Obra_mnt"],
            df_cessoes_raw["NumVendOrig_mnt"],
        )
    )
    assert len(vendas_cedidas) > 0

    # Nenhuma venda com TipoMnt = 2 pode estar presente em gold_fato_distratos_auditados
    for _, row in df_distratos_gold.iterrows():
        chave_venda = (row["cod_empresa"], row["cod_obra"], row["num_venda"])
        assert chave_venda not in vendas_cedidas

    # O total de distratos auditados deve ser exatamente o bruto menos os registros de cessão
    assert len(df_distratos_gold) == len(df_distratos_raw) - len(df_cessoes_raw)

    # Verifica precedência cedido > cancelado na carteira e na Matriz Roll-Rate
    df_carteira = gold["gold_fato_carteira_recebiveis"]
    chaves_cedidas = set(df_cessoes_raw["ChaveParcela"])
    df_m1_cedidas = df_carteira[
        (df_carteira["dt_foto"] == "2026-02-01")
        & (df_carteira["id_chave_parcela"].isin(chaves_cedidas))
    ]
    # Mesmo com flg_cancelado == 1 na origem, o status_canonico deve ser 'cedido'
    assert (df_m1_cedidas["flg_cancelado"] == 1).all()
    assert (df_m1_cedidas["status_canonico"] == "cedido").all()


@pytest.mark.parametrize("prefer_duckdb", [True, False])
def test_100pct_cell_by_cell_parity_sql_bronze_vs_gold(prefer_duckdb: bool) -> None:
    """
    (4) Prova de paridade 100% célula a célula entre uma query SQL pura executada
    diretamente sobre a camada Bronze e a tabela `gold_matriz_roll_rate` processada
    pela pipeline (testado tanto em DuckDB quanto no fallback SQLite).
    """
    datasets = generate_receivables_dataset(seed=42)
    pipeline = LakehouseRecebiveisPipeline(
        min_coverage_pct=99.5, prefer_duckdb=prefer_duckdb
    )
    pipeline.ingest_staging_and_promote_to_bronze(
        datasets=datasets, data_referencia="2026-01-01"
    )
    pipeline.build_silver_layer()
    pipeline.build_gold_layer(data_foto_m="2026-01-01", data_foto_m1="2026-02-01")

    parity_ok, df_sql_bronze, df_gold = pipeline.verify_bronze_to_gold_parity(
        data_foto_m="2026-01-01", data_foto_m1="2026-02-01"
    )
    assert parity_ok is True
    assert len(df_sql_bronze) == len(df_gold) > 0
    pd.testing.assert_frame_equal(
        df_sql_bronze,
        df_gold,
        check_dtype=False,
        check_exact=False,
        rtol=1e-5,
        atol=1e-2,
    )
