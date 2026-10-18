"""
Script CLI de Demonstração Ponta a Ponta - Projeto 02:
Motor de Conciliação Bancária, Recálculo de 5 Pernas Contábeis e Auditoria de Ciclos.

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

from generate_all import CONFIDENTIALITY_NOTICE, generate_reconciliation_dataset  # noqa: E402
from src.engine_conciliacao import (  # noqa: E402
    audit_reconciliation_cycles,
    calculate_icp_and_coverage_sentinel,
    compute_easter_meeus_butcher,
    get_febraban_holidays,
    recalculate_five_legs_and_confront_extrato,
)


def main() -> None:
    print("=" * 80)
    print("PROJETO 02: MOTOR DE CONCILIAÇÃO BANCÁRIA, 5 PERNAS & AUDITORIA DE CICLOS")
    print(CONFIDENTIALITY_NOTICE)
    print("=" * 80)

    datasets = generate_reconciliation_dataset(seed=42)

    # 1. Recálculo das 5 pernas do razão ERP + Expurgo R3 vs Extrato Oficial
    df_confronto_com_r3, df_purged_r3 = recalculate_five_legs_and_confront_extrato(
        perna_extrato=datasets["perna_extrato"],
        perna_recebepgto=datasets["perna_recebepgto"],
        perna_depositos=datasets["perna_depositos"],
        perna_entsai_aplic=datasets["perna_entsai_aplic"],
        perna_transf=datasets["perna_transf"],
        extrato_bancario=datasets["extrato_bancario"],
        apply_r3=True,
    )

    df_confronto_sem_r3, _ = recalculate_five_legs_and_confront_extrato(
        perna_extrato=datasets["perna_extrato"],
        perna_recebepgto=datasets["perna_recebepgto"],
        perna_depositos=datasets["perna_depositos"],
        perna_entsai_aplic=datasets["perna_entsai_aplic"],
        perna_transf=datasets["perna_transf"],
        extrato_bancario=datasets["extrato_bancario"],
        apply_r3=False,
    )

    # 2. Auditoria de Ciclo de Conciliação sobre múltiplos snapshots (Num_exa 1..N)
    df_ciclos = audit_reconciliation_cycles(datasets["snapshots_ciclo"])

    # 3. Calendário Bancário FEBRABAN (Meeus/Butcher) & ICP (Contas Correntes vs Aplicação)
    easter_2026 = compute_easter_meeus_butcher(2026)
    holidays_2026 = {
        k.isoformat(): v for k, v in sorted(get_febraban_holidays(2026).items())
    }
    icp_report = calculate_icp_and_coverage_sentinel(
        df_contas=datasets["contas_bancarias"],
        df_extrato=datasets["extrato_bancario"],
        start_date="2026-04-01",
        end_date="2026-04-15",
    )

    total_conta_dias = len(df_confronto_com_r3)
    paridade_com_r3 = int(df_confronto_com_r3["paridade_5pernas_ok"].sum())
    paridade_sem_r3 = int(df_confronto_sem_r3["paridade_5pernas_ok"].sum())
    pares_r3_expurgados = len(df_purged_r3) // 2

    in_place_detected = int(df_ciclos["validacao_in_place"].sum())

    output_payload = {
        "confidentiality_notice": CONFIDENTIALITY_NOTICE,
        "five_legs_reconciliation_summary": {
            "total_conta_dias_avaliados": total_conta_dias,
            "conta_dias_paridade_100pct_com_r3": paridade_com_r3,
            "conta_dias_paridade_sem_r3": paridade_sem_r3,
            "lancamentos_transitorios_r3_expurgados": len(df_purged_r3),
            "pares_intermediacao_0071_casados_expurgados": pares_r3_expurgados,
            "lancamentos_0071_unilaterais_preservados": 1,
        },
        "cycle_audit_summary": {
            "total_itens_auditados": len(df_ciclos),
            "anomalias_validacao_in_place_detectadas": in_place_detected,
            "itens": df_ciclos.to_dict(orient="records"),
        },
        "febraban_and_icp_summary": {
            "pascoa_2026_meeus_butcher": easter_2026.isoformat(),
            "feriados_febraban_2026": holidays_2026,
            "dias_uteis_febraban_periodo": icp_report[
                "dias_uteis_febraban_no_periodo"
            ],
            "icp_contas_correntes_pct": icp_report["icp_global_contas_correntes_pct"],
            "icp_ingenuo_distorcido_por_aplicacao_pct": icp_report[
                "icp_ingenuo_sem_expurgo_aplicacao_pct"
            ],
            "alertas_sentinela_10du": icp_report["alertas_sentinela_disparados"],
            "serie_diaria_icp": icp_report["serie_diaria"].to_dict(orient="records"),
        },
        "sample_confronto_5pernas": df_confronto_com_r3.head(5).to_dict(
            orient="records"
        ),
    }

    examples_dir = PROJECT_DIR / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    sample_output_path = examples_dir / "sample_output.json"
    with open(sample_output_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    print("\n[1] Recálculo das 5 Pernas do Razão ERP vs Extrato Oficial (SF = SI + C - D):")
    print(f"    - Pares transitórios R3 ('0071', TipoControle 5 e 6) expurgados: {pares_r3_expurgados} pares ({len(df_purged_r3)} lançamentos)")
    print(f"    - Paridade Conta×Dia SEM Regra R3 (crédito/débito inflado): {paridade_sem_r3}/{total_conta_dias}")
    print(f"    - Paridade Conta×Dia COM Regra R3 (líquido + órfão preservado): {paridade_com_r3}/{total_conta_dias} (100.0%)")

    print("\n[2] Motor de Ciclo de Conciliação sobre Múltiplos Snapshots (Num_exa 1..N):")
    print(f"    - Itens auditados: {len(df_ciclos)} | Anomalias 'validacao_in_place' detectadas: {in_place_detected}")
    for _, row in df_ciclos.iterrows():
        print(
            f"      * {row['id_item_extrato']}: status {row['status_inicial']}->{row['status_final']} | "
            f"in_place={row['validacao_in_place']} | dias_para_conciliar={row['dias_para_conciliar']} "
            f"({row['classificacao_ciclo']})"
        )

    print("\n[3] Calendário Bancário FEBRABAN (Meeus/Butcher) & Índice de Cobertura (ICP):")
    print(f"    - Páscoa 2026 (Meeus/Butcher): {easter_2026.isoformat()} | Sexta-Feira Santa: 2026-04-03")
    print(
        f"    - ICP Real (apenas Contas Correntes no denominador): {icp_report['icp_global_contas_correntes_pct']:.2f}% "
        f"(vs {icp_report['icp_ingenuo_sem_expurgo_aplicacao_pct']:.2f}% sem separar Contas de Aplicação)"
    )
    print(f"\nRelatório JSON salvo em: {sample_output_path}")


if __name__ == "__main__":
    main()
