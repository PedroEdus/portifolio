"""
Verificador Determinístico de Governança Epistêmica e Anti-PII para Vault Markdown.

Implementa as três barreiras de qualidade aplicadas às 300 notas técnicas do Vault:
1. Presença obrigatória de marcadores epistêmicos (`CONFIRMADO`, `PROVÁVEL` ou `HIPÓTESE`);
2. Lastro numérico estrito: todo número quantitativo citado na nota técnica deve constar no
   manifesto de evidências da auditoria (prevenindo alucinação ou números sem fonte);
3. Varredura determinística anti-PII e anti-credenciais (CPF, CNPJ, e-mail corporativo/pessoal,
   `XPassword`, strings de conexão com senha e chaves privadas).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Set


@dataclass
class NoteVerificationResult:
    """Resultado da validação determinística de uma nota Markdown do Vault."""

    note_id: str
    is_valid: bool
    epistemic_tags_found: List[str] = field(default_factory=list)
    unbacked_numbers: List[str] = field(default_factory=list)
    pii_violations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "note_id": self.note_id,
            "is_valid": self.is_valid,
            "epistemic_tags_found": self.epistemic_tags_found,
            "unbacked_numbers": self.unbacked_numbers,
            "pii_violations": self.pii_violations,
            "errors": self.errors,
        }


class VaultEpistemicVerifier:
    """
    Motor de verificação determinística de documentação técnica (Governance-as-Code).
    """

    EPISTEMIC_TAG_REGEX = re.compile(r"\b(CONFIRMADO|PROVÁVEL|PROVAVEL|HIPÓTESE|HIPOTESE)\b")

    # Padrões determinísticos de PII e segredos de conexão Qlik/SQL
    PII_DETECTORS = {
        "CPF": re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
        "CNPJ": re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),
        "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "QLIK_XPASSWORD": re.compile(r"(?i)\b(XPassword|Password|Pwd)\s*=\s*[^\s;\"']+"),
        "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    }

    # Extrai números inteiros ou decimais formatados (ex.: 654000000, 6.125, 4.994, 508, 171)
    NUMBER_TOKEN_REGEX = re.compile(r"(?<![A-Za-z0-9_/-])\d+(?:[.,]\d+)*(?![A-Za-z0-9_/-])")

    # Números triviais permitidos estruturalmente (ex.: listas numeradas 1, 2, 3 ou 0, 100%)
    TRIVIAL_ALLOWED_NUMBERS = {"0", "1", "2", "3", "4", "5", "8", "10", "16", "32", "64", "100"}

    def __init__(self, evidence_manifest_numbers: Sequence[int | float | str]) -> None:
        self.allowed_numbers: Set[str] = set(self.TRIVIAL_ALLOWED_NUMBERS)
        for num in evidence_manifest_numbers:
            normalized = self._normalize_number_token(str(num))
            self.allowed_numbers.add(normalized)
            self.allowed_numbers.add(str(num).strip())

    @staticmethod
    def _normalize_number_token(token: str) -> str:
        """
        Normaliza separadores de milhar (`.` no padrão pt-BR quando seguido de 3 dígitos)
        para comparação exata contra o manifesto de evidências.
        """
        cleaned = token.strip()
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):
            return cleaned.replace(".", "")
        return cleaned.replace(",", ".")

    def verify_note(self, note_id: str, markdown_text: str) -> NoteVerificationResult:
        """Executa as 3 validações determinísticas sobre o texto Markdown de uma nota."""
        errors: List[str] = []

        # 1. Tags Epistêmicas
        raw_tags = self.EPISTEMIC_TAG_REGEX.findall(markdown_text)
        unique_tags = sorted(
            {
                t.replace("PROVAVEL", "PROVÁVEL").replace("HIPOTESE", "HIPÓTESE")
                for t in raw_tags
            }
        )
        if not unique_tags:
            errors.append(
                "Nota não possui tag de qualificação epistêmica obrigatória (CONFIRMADO, PROVÁVEL ou HIPÓTESE)."
            )

        # 2. Varredura Anti-PII e Credenciais
        pii_violations: List[str] = []
        for label, pattern in self.PII_DETECTORS.items():
            for match in pattern.finditer(markdown_text):
                pii_violations.append(f"{label}: '{match.group(0)}'")

        if pii_violations:
            errors.append(
                f"Detectados {len(pii_violations)} vazamentos de PII/credenciais na nota técnica."
            )

        # Remove matches de PII do texto antes de extrair números para evitar falsos positivos cruzados
        sanitized_for_numbers = markdown_text
        for pattern in self.PII_DETECTORS.values():
            sanitized_for_numbers = pattern.sub(" ", sanitized_for_numbers)

        # 3. Lastro Numérico Estrito contra o Manifesto de Evidências
        unbacked_numbers: List[str] = []
        for match in self.NUMBER_TOKEN_REGEX.finditer(sanitized_for_numbers):
            raw_num = match.group(0)
            norm_num = self._normalize_number_token(raw_num)
            if raw_num not in self.allowed_numbers and norm_num not in self.allowed_numbers:
                if raw_num not in unbacked_numbers:
                    unbacked_numbers.append(raw_num)

        if unbacked_numbers:
            errors.append(
                f"Números sem lastro no manifesto de evidências: {', '.join(unbacked_numbers)}."
            )

        return NoteVerificationResult(
            note_id=note_id,
            is_valid=(len(errors) == 0),
            epistemic_tags_found=unique_tags,
            unbacked_numbers=unbacked_numbers,
            pii_violations=pii_violations,
            errors=errors,
        )
