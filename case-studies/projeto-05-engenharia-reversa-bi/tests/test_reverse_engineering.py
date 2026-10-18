"""
Suíte de testes automatizados (pytest) para o Estudo de Caso 05:
- Roundtrip binário exato do codec Bit-Stuffed QVD em NumPy (`qvd_bitstuffed_codec.py`)
- Proteção determinística e descarte na origem de colunas PII (`CPF`, `Senha`, etc.)
- Detecção estática de medidas DAX homônimas divergentes, datas inválidas (`DATE(2026, 9, 31)`)
  e tabelas de credenciais em texto claro (`pbir_dax_auditor.py`)
- Verificação epistêmica e bloqueio de PII / números sem lastro (`vault_epistemic_verifier.py`)
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pbir_dax_auditor import DaxMeasureRecord, PbirDaxAuditor
from src.qvd_bitstuffed_codec import QvdBitStuffedCodec, is_sensitive_column
from src.vault_epistemic_verifier import VaultEpistemicVerifier


def test_qvd_bitstuffed_roundtrip_and_null_bias() -> None:
    codec = QvdBitStuffedCodec(drop_pii=False)
    original_columns = {
        "ID_PEDIDO": [10, 20, 30, 10, 40, 20, 50],
        "UF": ["GO", "MT", "MS", "GO", None, "PR", "MT"],
        "VALOR": [1250.5, 3400.0, 1250.5, 99.9, 500.0, 3400.0, 0.0],
        "CONSTANTE": ["ATIVO"] * 7,
    }

    blob = codec.encode_table(
        table_name="FATO_TESTE",
        columns=original_columns,
        nullable_columns=["UF"],
    )
    decoded = codec.decode_table(blob)

    assert decoded["table_name"] == "FATO_TESTE"
    assert decoded["no_of_records"] == 7
    assert decoded["dropped_pii_columns"] == []
    assert decoded["data"]["ID_PEDIDO"] == original_columns["ID_PEDIDO"]
    assert decoded["data"]["UF"] == original_columns["UF"]
    assert decoded["data"]["VALOR"] == original_columns["VALOR"]
    assert decoded["data"]["CONSTANTE"] == original_columns["CONSTANTE"]

    # Verifica metadados do campo com Bias = -2 (UF) e campo constante BitWidth = 0
    meta_by_name = {f.field_name: f for f in decoded["metadata"].fields}
    assert meta_by_name["UF"].bias == -2
    assert meta_by_name["UF"].bit_width > 0
    assert meta_by_name["CONSTANTE"].bit_width == 0


def test_qvd_pii_column_filtering_on_decode() -> None:
    codec = QvdBitStuffedCodec(drop_pii=True)
    columns = {
        "COD_CLIENTE": [1, 2, 3],
        "NR_CPF_TITULAR": ["111.111.111-11", "222.222.222-22", "333.333.333-33"],
        "DS_SENHA_PORTAL": ["abc", "def", "ghi"],
        "EMAIL_CONTATO": ["a@b.com", "c@d.com", "e@f.com"],
    }
    blob = codec.encode_table("DIM_CLIENTE", columns)
    decoded = codec.decode_table(blob)

    assert "COD_CLIENTE" in decoded["data"]
    assert "NR_CPF_TITULAR" not in decoded["data"]
    assert "DS_SENHA_PORTAL" not in decoded["data"]
    assert "EMAIL_CONTATO" not in decoded["data"]
    assert set(decoded["dropped_pii_columns"]) == {
        "NR_CPF_TITULAR",
        "DS_SENHA_PORTAL",
        "EMAIL_CONTATO",
    }
    assert is_sensitive_column("VL_SALARIO_BASE") is True
    assert is_sensitive_column("COD_PRODUTO") is False


def test_pbir_dax_auditor_detects_conflicts_and_invalid_dates() -> None:
    auditor = PbirDaxAuditor()
    measures = [
        DaxMeasureRecord(
            report_name="Painel_A.pbix",
            table_name="Medidas",
            measure_name="Margem Contribuição",
            expression="SUM(Fato[Receita]) - SUM(Fato[CustoVariavel])",
        ),
        DaxMeasureRecord(
            report_name="Painel_B.pbix",
            table_name="Medidas",
            measure_name="Margem Contribuição",
            expression="SUM(Fato[Receita]) - SUM(Fato[CustoVariavel]) - SUM(Fato[Frete])",
        ),
        DaxMeasureRecord(
            report_name="Painel_Safra.pbix",
            table_name="Medidas",
            measure_name="Corte Setembro",
            expression="CALCULATE([Margem Contribuição], dCalendario[Data] <= DATE(2026, 9, 31))",
        ),
        DaxMeasureRecord(
            report_name="Painel_Bissexto.pbix",
            table_name="Medidas",
            measure_name="Corte Fevereiro",
            expression="CALCULATE([Margem Contribuição], dCalendario[Data] <= DATE(2025, 2, 29))",
        ),
        DaxMeasureRecord(
            report_name="Painel_A.pbix",
            table_name="Medidas",
            measure_name="Filtro CFOP",
            expression="CALCULATE(SUM(Fato[Receita]), Fato[CFOP] NOT IN {\"5910\", \"5949\"})",
        ),
        DaxMeasureRecord(
            report_name="Painel_B.pbix",
            table_name="Medidas",
            measure_name="Filtro CFOP",
            expression="CALCULATE(SUM(Fato[Receita]), Fato[CFOP] NOT IN {\"5910\"})",
        ),
    ]
    tables = {
        "Painel_A.pbix": ["Fato", "DIM_Senhas"],
        "Painel_B.pbix": ["Fato", "Dados de Login"],
    }

    report = auditor.audit_models(measures, tables)
    assert len(report.homonymous_conflicts) == 2
    conflict_names = {c.measure_name for c in report.homonymous_conflicts}
    assert "Margem Contribuição" in conflict_names

    assert len(report.invalid_date_literals) == 2
    raw_dates = {d.raw_literal for d in report.invalid_date_literals}
    assert "DATE(2026, 9, 31)" in raw_dates
    assert "DATE(2025, 2, 29)" in raw_dates

    assert len(report.exclusion_conflicts) == 1
    assert report.exclusion_conflicts[0].target_column == "Fato[CFOP]"
    assert len(report.suspicious_credential_tables) == 2


def test_vault_epistemic_verifier_enforces_tags_numbers_and_anti_pii() -> None:
    verifier = VaultEpistemicVerifier(evidence_manifest_numbers=[508, 654000000, 171])

    clean_note = (
        "## Nota Auditada\n"
        "[CONFIRMADO] O acervo possui 508 arquivos QVD com 654.000.000 de linhas e 171 conflitos.\n"
    )
    res_clean = verifier.verify_note("NOTE-OK", clean_note)
    assert res_clean.is_valid is True
    assert res_clean.epistemic_tags_found == ["CONFIRMADO"]
    assert res_clean.unbacked_numbers == []
    assert res_clean.pii_violations == []

    bad_note = (
        "## Nota Sem Tag e Com Vazamento\n"
        "Encontrados 42999 registros do CPF 111.222.333-44 com XPassword=Abc12345 e email dev@corp.com.br.\n"
    )
    res_bad = verifier.verify_note("NOTE-BAD", bad_note)
    assert res_bad.is_valid is False
    assert res_bad.epistemic_tags_found == []
    assert "42999" in res_bad.unbacked_numbers
    assert len(res_bad.pii_violations) == 3
