"""
Script de demonstração ponta a ponta do Estudo de Caso 05:
Toolkit de Engenharia Reversa: Parser Binário de QVD em NumPy Bitwise,
Auditoria Estática PBIR/TMDL e Governança Epistêmica.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.pbir_dax_auditor import DaxMeasureRecord, PbirDaxAuditor
from src.qvd_bitstuffed_codec import QvdBitStuffedCodec
from src.vault_epistemic_verifier import VaultEpistemicVerifier


def main() -> None:
    # 1. Demonstração do Codec Binário QVD Bit-Stuffed em NumPy + Filtro Anti-PII
    codec = QvdBitStuffedCodec(drop_pii=True)
    sample_columns = {
        "COD_FILIAL": [101, 102, 101, 103, 102, 101],
        "STATUS_PEDIDO": ["FATURADO", "PENDENTE", "FATURADO", "CANCELADO", None, "FATURADO"],
        "VALOR_LIQUIDO": [15400.50, 8200.00, 15400.50, 0.0, 9100.75, 22300.00],
        "CPF_CLIENTE": [
            "111.222.333-44",
            "555.666.777-88",
            "111.222.333-44",
            "999.888.777-66",
            "123.456.789-00",
            "111.222.333-44",
        ],
    }

    qvd_blob = codec.encode_table(
        table_name="FATO_FATURAMENTO_ERP",
        columns=sample_columns,
        nullable_columns=["STATUS_PEDIDO"],
    )
    decoded_qvd = codec.decode_table(qvd_blob)

    # 2. Demonstração da Auditoria Estática PBIR / TMDL / DAX
    auditor = PbirDaxAuditor()
    sample_measures = [
        DaxMeasureRecord(
            report_name="Comercial_Corporativo.pbix",
            table_name="Medidas_Vendas",
            measure_name="Receita Líquida",
            expression="CALCULATE(SUM(Fato[ValorBruto]) - SUM(Fato[Impostos]), Fato[Status] = \"FATURADO\")",
        ),
        DaxMeasureRecord(
            report_name="Diretoria_Financeira.pbix",
            table_name="Medidas_Vendas",
            measure_name="Receita Líquida",
            expression=(
                "CALCULATE(SUM(Fato[ValorBruto]) - SUM(Fato[Impostos]) - SUM(Fato[Devolucoes]), "
                "Fato[Status] = \"FATURADO\")"
            ),
        ),
        DaxMeasureRecord(
            report_name="Planejamento_Safra.pbix",
            table_name="Medidas_Safra",
            measure_name="Meta Safra Corte Setembro",
            expression=(
                "CALCULATE([Receita Líquida], "
                "FILTER(dCalendario, dCalendario[Data] <= DATE(2026, 9, 31)))"
            ),
        ),
        DaxMeasureRecord(
            report_name="Comercial_Corporativo.pbix",
            table_name="Medidas_Vendas",
            measure_name="Vendas Sem Expurgos",
            expression="CALCULATE([Receita Líquida], DimOperacao[CFOP] NOT IN {\"5910\", \"5949\"})",
        ),
        DaxMeasureRecord(
            report_name="Diretoria_Financeira.pbix",
            table_name="Medidas_Vendas",
            measure_name="Vendas Sem Expurgos Diretoria",
            expression="CALCULATE([Receita Líquida], DimOperacao[CFOP] NOT IN {\"5910\", \"5949\", \"6910\"})",
        ),
    ]
    report_tables = {
        "Comercial_Corporativo.pbix": ["Fato_Vendas", "Dim_Cliente", "dCalendario"],
        "Diretoria_Financeira.pbix": ["Fato_Vendas", "Dim_Cliente", "DIM_Senhas"],
        "Planejamento_Safra.pbix": ["Fato_Safra", "dCalendario", "Dados de Login"],
    }
    audit_report = auditor.audit_models(sample_measures, report_tables)

    # 3. Demonstração do Verificador Epistêmico e Anti-PII do Vault Markdown
    verifier = VaultEpistemicVerifier(
        evidence_manifest_numbers=[508, 654000000, 44, 6125, 4994, 171, 4255, 573, 300, 2026, 9, 31]
    )
    valid_note = (
        "# Auditoria Camada QVD e PBIR\n"
        "- Status: [CONFIRMADO] Varridos 508 arquivos QVD totalizando 654.000.000 de registros.\n"
        "- Status: [CONFIRMADO] Auditados 44 relatórios PBIX com 6.125 visuais e 4.994 medidas DAX, "
        "identificando 171 medidas homônimas conflitantes.\n"
        "- Status: [PROVÁVEL] Migração das 4.255 FKs e 573 decodes para dbt Core.\n"
    )
    invalid_note = (
        "# Rascunho Não Auditado\n"
        "Foram processados 999999 registros com XPassword=Segredo123 e contato joao.silva@empresa.com.br "
        "para o CPF 123.456.789-00.\n"
    )

    valid_check = verifier.verify_note("MOD-001-AUDITORIA-BI", valid_note)
    invalid_check = verifier.verify_note("RASCUNHO-VAZAMENTO", invalid_note)

    output_payload = {
        "case_study": "projeto-05-engenharia-reversa-bi",
        "qvd_bitstuffed_demo": {
            "table_name": decoded_qvd["table_name"],
            "no_of_records": decoded_qvd["no_of_records"],
            "record_byte_size": decoded_qvd["record_byte_size"],
            "binary_size_bytes": len(qvd_blob),
            "dropped_pii_columns": decoded_qvd["dropped_pii_columns"],
            "decoded_columns": decoded_qvd["data"],
            "fields_metadata": [
                {
                    "field_name": f.field_name,
                    "bit_offset": f.bit_offset,
                    "bit_width": f.bit_width,
                    "bias": f.bias,
                    "no_of_symbols": f.no_of_symbols,
                }
                for f in decoded_qvd["metadata"].fields
            ],
        },
        "pbir_dax_audit_demo": audit_report.to_dict(),
        "vault_epistemic_verifier_demo": {
            "approved_note": valid_check.to_dict(),
            "blocked_note": invalid_check.to_dict(),
        },
    }

    examples_dir = Path(__file__).resolve().parent / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    out_path = examples_dir / "sample_output.json"
    out_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Demo executada com sucesso. Saída gravada em: {out_path}")


if __name__ == "__main__":
    main()
