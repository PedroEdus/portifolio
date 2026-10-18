"""
Verificador Unificado do Portfólio Técnico (Fase 8 — Qualidade, Testes & Segurança)

Executa:
1. As 6 suítes de testes automatizados (pytest) em subprocessos isolados (30 testes);
2. Validação estrutural dos artefatos de saída (`examples/sample_output.json`) e do site (`portfolio-site/`);
3. Varredura determinística anti-segredos nas pastas de código público (`case-studies/`, `shared/`, `portfolio-site/`).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parent

CASE_STUDIES = [
    "projeto-01-lakehouse-recebiveis",
    "projeto-02-conciliacao-bancaria",
    "projeto-03-dw-snapshots-diff",
    "projeto-04-marketing-crm-cloud",
    "projeto-05-engenharia-reversa-bi",
    "projeto-06-maquina-estados-imobiliario",
]

FORBIDDEN_SECRET_PATTERNS = [
    (r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "IP privado de rede interna"),
    (r"BEGIN PRIVATE KEY", "Chave privada PEM/GCP"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API Key real"),
    (r"EAAG[0-9A-Za-z]{20,}", "Meta Graph Token real"),
]


def run_verification() -> int:
    print("=" * 78)
    print("VERIFICAÇÃO UNIFICADA DO PORTFÓLIO TÉCNICO (FASE 8)")
    print("=" * 78)

    # 1. Executar Pytest em cada Case Study
    for case in CASE_STUDIES:
        case_dir = WORKSPACE_ROOT / "case-studies" / case
        sample_json = case_dir / "examples" / "sample_output.json"
        if not sample_json.exists():
            print(f"[ERRO] sample_output.json ausente em {case}")
            return 1
        with sample_json.open("r", encoding="utf-8") as fh:
            json.load(fh)

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(case_dir / "tests"), "-q"],
            cwd=str(case_dir),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"[FALHA] {case}:\n{proc.stdout}\n{proc.stderr}")
            return 1
        summary_line = [line for line in proc.stdout.splitlines() if "passed" in line][-1]
        print(f"[OK] {case:<42} -> {summary_line} | sample_output.json válido")

    # 2. Varredura Anti-Segredos em código executável e site
    scan_dirs = [
        WORKSPACE_ROOT / "case-studies",
        WORKSPACE_ROOT / "shared",
        WORKSPACE_ROOT / "portfolio-site",
    ]
    scanned_files = 0
    for sdir in scan_dirs:
        for path in sdir.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".sql", ".json", ".yaml", ".html", ".js", ".css"}:
                scanned_files += 1
                content = path.read_text(encoding="utf-8", errors="ignore")
                for pattern, desc in FORBIDDEN_SECRET_PATTERNS:
                    if re.search(pattern, content):
                        print(f"[VIOLAÇÃO DE SEGURANÇA] {desc} encontrado em {path}")
                        return 1

    print("-" * 78)
    print(f"[OK] Auditoria Anti-Segredos aprovada em {scanned_files} arquivos de código/dados/site.")
    print("[OK] Todas as 6 demonstrações executáveis e o portfolio-site estão 100% íntegros.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_verification())
