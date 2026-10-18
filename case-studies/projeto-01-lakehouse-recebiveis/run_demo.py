"""
Script CLI de Demonstração Ponta a Ponta - Projeto 01:
Plataforma Lakehouse Medallion, Controle Transacional e Matriz Roll-Rate de Recebíveis.

AVISO DE CONFIDENCIALIDADE:
Todos os dados executados neste script são 100% sintéticos (`seed=42`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_DIR.parent.parent
SYNTHETIC_DIR = WORKSPACE_DIR / "shared" / "synthetic-data"

sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(SYNTHETIC_DIR))

from generate_all import CONFIDENTIALITY_NOTICE, generate_receivables_dataset  # noqa: E402
from src.pipeline_lakehouse import LakehouseRecebiveisPipeline  # noqa: E402


def main() -> None:
    print("=" * 80)
    print("PROJETO 01: PLATAFORMA LAKEHOUSE MEDALLION & MATRIZ ROLL-RATE DE RECEBÍVEIS")
    print(CONFIDENTIALITY_NOTICE)
    print("=" * 80)

    datasets = generate_receivables_dataset(seed=42)
    pipeline = LakehouseRecebiveisPipeline(min_coverage_pct=99.5, prefer_duckdb=True)

    # 1. Ingestão Staging-First Atômica + Foto Mensal Idempotente (Dia 1)
    rodada_status = pipeline.ingest_staging_and_promote_to_bronze(
        datasets=datasets,
        data_referencia="2026-01-01",
        aceitar_calc_defasada=True,
    )
    foto_m_count_1 = pipeline.retain_monthly_snapshot_idempotent("2026-01-01")
    foto_m_count_2 = pipeline.retain_monthly_snapshot_idempotent("2026-01-01")

    # 2. Camada Silver Declarativa
    silver_counts = pipeline.build_silver_layer()

    # 3. Camada Gold Star Schema (Carteira, Distratos Auditados, Roll-Rate e Coorte)
    gold_tables = pipeline.build_gold_layer(
        data_foto_m="2026-01-01", data_foto_m1="2026-02-01"
    )

    # 4. Verificação de Paridade 100% Célula a Célula (SQL Pura na Bronze vs Gold)
    parity_ok, df_sql_bronze, df_gold_rr = pipeline.verify_bronze_to_gold_parity(
        data_foto_m="2026-01-01", data_foto_m1="2026-02-01"
    )

    df_distratos_raw = datasets["distratos"]
    df_distratos_gold = gold_tables["gold_fato_distratos_auditados"]
    cessoes_expurgadas = len(df_distratos_raw) - len(df_distratos_gold)

    df_carteira = gold_tables["gold_fato_carteira_recebiveis"]
    custas_separadas = int((df_carteira["flg_custa"] == 1).sum())
    divergencia_prorrogacao = int(
        (
            df_carteira["faixa_atraso_contratual"]
            != df_carteira["faixa_atraso_prorrogado"]
        ).sum()
    )

    report_payload = {
        "confidentiality_notice": CONFIDENTIALITY_NOTICE,
        "engine": pipeline.db.engine_name,
        "transactional_control": {
            "id_rodada": rodada_status.id_rodada,
            "data_referencia": rodada_status.data_referencia,
            "status_rodada": rodada_status.status,
            "cobertura_calc_pct": rodada_status.cobertura_calc_pct,
            "aceitar_calc_defasada": rodada_status.aceitar_calc_defasada,
            "mensagem": rodada_status.mensagem,
        },
        "idempotent_day1_snapshot": {
            "data_foto": "2026-01-01",
            "count_first_execution": foto_m_count_1,
            "count_second_execution_replace_where": foto_m_count_2,
            "idempotent_verified": foto_m_count_1 == foto_m_count_2,
        },
        "silver_layer_counts": silver_counts,
        "gold_audit_metrics": {
            "total_carteira_rows": len(df_carteira),
            "custas_isoladas_tipo_1": custas_separadas,
            "parcelas_com_atraso_mascarado_por_prorrogacao": divergencia_prorrogacao,
            "distratos_brutos_erp": len(df_distratos_raw),
            "cessoes_tipo_mnt_2_expurgadas_de_distratos": cessoes_expurgadas,
            "distratos_reais_auditados_gold": len(df_distratos_gold),
            "bronze_to_gold_100pct_cell_parity": parity_ok,
        },
        "roll_rate_matrix_m_to_m1": df_gold_rr.to_dict(orient="records"),
        "renegotiation_survival_cohort": gold_tables[
            "gold_coorte_renegociacao"
        ].to_dict(orient="records"),
    }

    examples_dir = PROJECT_DIR / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    sample_output_path = examples_dir / "sample_output.json"
    with open(sample_output_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, ensure_ascii=False, indent=2)

    print(f"\n[1] Controle Transacional (Rodada #{rodada_status.id_rodada}):")
    print(f"    Status: {rodada_status.status} | Cobertura Calc: {rodada_status.cobertura_calc_pct:.2f}%")
    print(f"     Foto Mensal Dia 1 Idempotente (replaceWhere): {foto_m_count_1} == {foto_m_count_2} linhas")
    print("\n[2] Camada Silver Declarativa (Conservação 100% Bronze == Silver):")
    print(f"    silver_contas_receber: {silver_counts['silver_contas_receber']} registros")
    print("\n[3] Auditoria Gold Star Schema:")
    print(f"    - Custas isoladas (TipoParc = '1'): {custas_separadas} registros")
    print(f"    - Parcelas com atraso mascarado por prorrogação: {divergencia_prorrogacao} registros")
    print(
        f"    - Distratos ERP Bruto: {len(df_distratos_raw)} | "
        f"Cessões (TipoMnt=2) Expurgadas: {cessoes_expurgadas} | "
        f"Distratos Reais Gold: {len(df_distratos_gold)}"
    )
    print(f"    - Paridade 100% Célula a Célula (SQL Pura Bronze vs Gold): {parity_ok}")
    print(f"\nRelatório JSON salvo em: {sample_output_path}")


if __name__ == "__main__":
    main()
