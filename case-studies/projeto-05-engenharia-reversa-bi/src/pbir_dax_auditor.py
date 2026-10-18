"""
Motor de Auditoria Estática de Modelos Semânticos PBIR / TMDL e Expressões DAX.

Inspirado na auditoria em larga escala de 44 relatórios `.pbix` (convertidos para
6.125 visuais PBIR e 4.994 medidas DAX), este módulo detecta deterministicamente:
1. Medidas DAX homônimas com fórmulas/árvores lógicas divergentes entre relatórios;
2. Literais de data inválidos em DAX (ex.: `DATE(2026, 9, 31)`, `DATE(2025, 2, 29)`);
3. Listas de exclusão hardcoded conflitantes (`NOT IN (...)`) entre visuais/medidas;
4. Tabelas suspeitas de credenciais/senhas em texto claro (`DIM_Senhas`, `Dados de Login`).
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Set, Tuple


@dataclass(frozen=True)
class DaxMeasureRecord:
    """Representa uma medida DAX extraída de um modelo semântico PBIR/TMDL."""

    report_name: str
    table_name: str
    measure_name: str
    expression: str


@dataclass(frozen=True)
class HomonymousMeasureConflict:
    """Conflito de medida homônima com fórmulas canônicas distintas entre painéis."""

    measure_name: str
    distinct_formulas: Dict[str, List[str]]  # canonical_formula -> [report_names]


@dataclass(frozen=True)
class InvalidDaxDateFinding:
    """Ocorrência de literal `DATE(ano, mes, dia)` inexistente no calendário."""

    report_name: str
    measure_name: str
    raw_literal: str
    year: int
    month: int
    day: int
    reason: str


@dataclass(frozen=True)
class HardcodedExclusionConflict:
    """Divergência em listas de exclusão hardcoded (`NOT IN (...)`) para uma mesma dimensão."""

    target_column: str
    exclusions_by_report: Dict[str, List[str]]


@dataclass
class SemanticAuditReport:
    """Resultado consolidado da auditoria estática de modelos PBIR/TMDL."""

    total_reports_scanned: int
    total_measures_scanned: int
    homonymous_conflicts: List[HomonymousMeasureConflict] = field(default_factory=list)
    invalid_date_literals: List[InvalidDaxDateFinding] = field(default_factory=list)
    exclusion_conflicts: List[HardcodedExclusionConflict] = field(default_factory=list)
    suspicious_credential_tables: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_reports_scanned": self.total_reports_scanned,
            "total_measures_scanned": self.total_measures_scanned,
            "homonymous_conflicts_count": len(self.homonymous_conflicts),
            "homonymous_conflicts": [
                {
                    "measure_name": c.measure_name,
                    "distinct_formulas": c.distinct_formulas,
                }
                for c in self.homonymous_conflicts
            ],
            "invalid_date_literals": [
                {
                    "report_name": d.report_name,
                    "measure_name": d.measure_name,
                    "raw_literal": d.raw_literal,
                    "year": d.year,
                    "month": d.month,
                    "day": d.day,
                    "reason": d.reason,
                }
                for d in self.invalid_date_literals
            ],
            "exclusion_conflicts": [
                {
                    "target_column": e.target_column,
                    "exclusions_by_report": e.exclusions_by_report,
                }
                for e in self.exclusion_conflicts
            ],
            "suspicious_credential_tables": self.suspicious_credential_tables,
        }


class PbirDaxAuditor:
    """Auditor estático de definições de modelos semânticos Power BI (PBIR / TMDL)."""

    DATE_LITERAL_REGEX = re.compile(
        r"\bDATE\s*\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)",
        re.IGNORECASE,
    )

    NOT_IN_REGEX = re.compile(
        r"([A-Za-z0-9_'\[\]\.]+)\s+NOT\s+IN\s*\{([^}]+)\}",
        re.IGNORECASE,
    )

    CREDENTIAL_TABLE_REGEX = re.compile(
        r"(?i)\b(dim_senhas|dados\s+de\s+login|tb_senhas|usuarios_senhas|credenciais_acesso|login_plaintext)\b"
    )

    @staticmethod
    def canonicalize_dax(expression: str) -> str:
        """
        Normaliza uma expressão DAX removendo comentários de linha (`//`, `--`),
        comentários de bloco (`/* ... */`) e colapsando espaços em branco para comparação
        estrutural justa entre relatórios.
        """
        no_block_comments = re.sub(r"/\*.*?\*/", "", expression, flags=re.DOTALL)
        no_line_comments = re.sub(r"(//|--).*?$", "", no_block_comments, flags=re.MULTILINE)
        collapsed = re.sub(r"\s+", "", no_line_comments).upper()
        return collapsed

    def detect_homonymous_conflicts(
        self, measures: Sequence[DaxMeasureRecord]
    ) -> List[HomonymousMeasureConflict]:
        """
        Identifica medidas DAX que compartilham exatamente o mesmo nome de negócio,
        mas possuem árvores/fórmulas canônicas divergentes entre relatórios.
        """
        grouped: Dict[str, Dict[str, Set[str]]] = {}
        raw_representation: Dict[Tuple[str, str], str] = {}

        for m in measures:
            canon = self.canonicalize_dax(m.expression)
            name_key = m.measure_name.strip()
            grouped.setdefault(name_key, {}).setdefault(canon, set()).add(m.report_name)
            raw_representation.setdefault((name_key, canon), m.expression.strip())

        conflicts: List[HomonymousMeasureConflict] = []
        for measure_name, canon_map in sorted(grouped.items()):
            if len(canon_map) > 1:
                readable_map: Dict[str, List[str]] = {}
                for canon_expr, reports in canon_map.items():
                    pretty_expr = raw_representation[(measure_name, canon_expr)]
                    readable_map[pretty_expr] = sorted(reports)
                conflicts.append(
                    HomonymousMeasureConflict(
                        measure_name=measure_name,
                        distinct_formulas=readable_map,
                    )
                )
        return conflicts

    def detect_invalid_date_literals(
        self, measures: Sequence[DaxMeasureRecord]
    ) -> List[InvalidDaxDateFinding]:
        """
        Inspeciona expressões DAX em busca de literais `DATE(YYYY, MM, DD)` inválidos
        no calendário gregoriano (como `DATE(2026, 9, 31)` ou `DATE(2025, 2, 29)`),
        que sofrem overflow silencioso para o mês seguinte no motor DAX.
        """
        findings: List[InvalidDaxDateFinding] = []
        for m in measures:
            for match in self.DATE_LITERAL_REGEX.finditer(m.expression):
                raw_lit = match.group(0)
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))

                if month < 1 or month > 12:
                    findings.append(
                        InvalidDaxDateFinding(
                            report_name=m.report_name,
                            measure_name=m.measure_name,
                            raw_literal=raw_lit,
                            year=year,
                            month=month,
                            day=day,
                            reason=f"Mês inválido ({month}); deve estar entre 1 e 12.",
                        )
                    )
                    continue

                _, max_day = calendar.monthrange(year, month)
                if day < 1 or day > max_day:
                    findings.append(
                        InvalidDaxDateFinding(
                            report_name=m.report_name,
                            measure_name=m.measure_name,
                            raw_literal=raw_lit,
                            year=year,
                            month=month,
                            day=day,
                            reason=(
                                f"Dia inexistente ({day:02d}/{month:02d}/{year}): "
                                f"o mês {month:02d}/{year} possui no máximo {max_day} dias "
                                "(causa deslocamento silencioso no motor DAX)."
                            ),
                        )
                    )
        return findings

    def detect_exclusion_conflicts(
        self, measures: Sequence[DaxMeasureRecord]
    ) -> List[HardcodedExclusionConflict]:
        """
        Detecta filtros `Coluna NOT IN { ... }` hardcoded em medidas DAX onde
        diferentes relatórios aplicam conjuntos de exclusão divergentes sobre a mesma coluna.
        """
        col_to_report_sets: Dict[str, Dict[str, List[str]]] = {}
        col_to_signatures: Dict[str, Set[Tuple[str, ...]]] = {}

        for m in measures:
            for match in self.NOT_IN_REGEX.finditer(m.expression):
                col_name = match.group(1).strip()
                raw_items = match.group(2)
                items = sorted(
                    {
                        item.strip().strip('"').strip("'")
                        for item in raw_items.split(",")
                        if item.strip()
                    }
                )
                col_to_report_sets.setdefault(col_name, {})[
                    f"{m.report_name}::{m.measure_name}"
                ] = items
                col_to_signatures.setdefault(col_name, set()).add(tuple(items))

        conflicts: List[HardcodedExclusionConflict] = []
        for col_name, sigs in sorted(col_to_signatures.items()):
            if len(sigs) > 1:
                conflicts.append(
                    HardcodedExclusionConflict(
                        target_column=col_name,
                        exclusions_by_report=col_to_report_sets[col_name],
                    )
                )
        return conflicts

    def detect_suspicious_tables(
        self, report_tables: Dict[str, Sequence[str]]
    ) -> List[Dict[str, str]]:
        """
        Verifica se algum modelo semântico importa tabelas de senhas ou credenciais
        em texto claro (ex.: `DIM_Senhas`, `Dados de Login`).
        """
        findings: List[Dict[str, str]] = []
        for report_name, tables in sorted(report_tables.items()):
            for tb in tables:
                if self.CREDENTIAL_TABLE_REGEX.search(tb):
                    findings.append(
                        {
                            "report_name": report_name,
                            "table_name": tb,
                            "severity": "CRITICAL_SECURITY_RISK",
                            "description": (
                                f"Tabela sensível de autenticação '{tb}' exposta no modelo semântico."
                            ),
                        }
                    )
        return findings

    def audit_models(
        self,
        measures: Sequence[DaxMeasureRecord],
        report_tables: Dict[str, Sequence[str]],
    ) -> SemanticAuditReport:
        """Executa a bateria completa de auditoria estática PBIR/TMDL."""
        unique_reports = set(report_tables.keys()) | {m.report_name for m in measures}
        return SemanticAuditReport(
            total_reports_scanned=len(unique_reports),
            total_measures_scanned=len(measures),
            homonymous_conflicts=self.detect_homonymous_conflicts(measures),
            invalid_date_literals=self.detect_invalid_date_literals(measures),
            exclusion_conflicts=self.detect_exclusion_conflicts(measures),
            suspicious_credential_tables=self.detect_suspicious_tables(report_tables),
        )
