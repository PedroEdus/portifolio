"""
Motor Determinístico de Taxonomia de Campanhas de Marketing Digital (core/taxonomia.py).

Implementa:
- Normalização Unicode (NFKD) sem acentos;
- Cache LRU (@lru_cache(maxsize=4096)) para avaliação em sub-milissegundos;
- Padrões hierárquicos de Expressões Regulares (Regex) que extraem (cidade, uf, tipo_lancamento)
  a partir de nomenclaturas livres de campanhas de Google Ads, Meta Ads e Programática.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Dict, List, Pattern, Tuple

# Catálogo canônico de municípios monitorados (amostra representativa do dicionário corporativo)
CATALOGO_MUNICIPIOS_PADRAO: List[Tuple[Pattern[str], str, str]] = [
    (re.compile(r"\baparecida\s*(?:de\s*)?goiania\b|\bap\s*goiania\b", re.I), "Aparecida de Goiânia", "GO"),
    (re.compile(r"\bsenador\s*canedo\b|\bsen\s*canedo\b", re.I), "Senador Canedo", "GO"),
    (re.compile(r"\btrindade\b", re.I), "Trindade", "GO"),
    (re.compile(r"\banapolis\b", re.I), "Anápolis", "GO"),
    (re.compile(r"\brio\s*verde\b", re.I), "Rio Verde", "GO"),
    (re.compile(r"\bcaldas\s*novas\b", re.I), "Caldas Novas", "GO"),
    (re.compile(r"\bitumbiara\b", re.I), "Itumbiara", "GO"),
    (re.compile(r"\bcidade\s*ocidental\b", re.I), "Cidade Ocidental", "GO"),
    (re.compile(r"\bgoiania\b", re.I), "Goiânia", "GO"),
    (re.compile(r"\bpalmas\b", re.I), "Palmas", "TO"),
    (re.compile(r"\baraguaina\b", re.I), "Araguaína", "TO"),
    (re.compile(r"\bgurupi\b", re.I), "Gurupi", "TO"),
    (re.compile(r"\bporto\s*nacional\b", re.I), "Porto Nacional", "TO"),
    (re.compile(r"\bparauapebas\b", re.I), "Parauapebas", "PA"),
    (re.compile(r"\bmaraba\b", re.I), "Marabá", "PA"),
    (re.compile(r"\bredencao\b", re.I), "Redenção", "PA"),
    (re.compile(r"\brondonopolis\b", re.I), "Rondonópolis", "MT"),
    (re.compile(r"\bsinop\b", re.I), "Sinop", "MT"),
    (re.compile(r"\bcuiaba\b", re.I), "Cuiabá", "MT"),
    (re.compile(r"\bcampo\s*grande\b", re.I), "Campo Grande", "MS"),
    (re.compile(r"\bdourados\b", re.I), "Dourados", "MS"),
    (re.compile(r"\buberlandia\b", re.I), "Uberlândia", "MG"),
    (re.compile(r"\buberaba\b", re.I), "Uberaba", "MG"),
    (re.compile(r"\bluis\s*eduardo\s*magalhaes\b|\blem\b", re.I), "Luís Eduardo Magalhães", "BA"),
    (re.compile(r"\bbarreiras\b", re.I), "Barreiras", "BA"),
    (re.compile(r"\bsao\s*jose\s*do\s*rio\s*preto\b|\brio\s*preto\b", re.I), "São José do Rio Preto", "SP"),
]

# Padrões hierárquicos para Tipo de Campanha (Lançamento vs Estoque vs Institucional)
REGEX_LANCAMENTO: Pattern[str] = re.compile(
    r"\b(?:lancamento|lanc|pre[\s_-]*lancamento|teaser|abertura[\s_-]*vendas)\b", re.I
)
REGEX_ESTOQUE: Pattern[str] = re.compile(
    r"\b(?:estoque|remanescentes|pronto|oportunidade|queima|ultimas[\s_-]*unidades|retargeting|rmkt)\b",
    re.I,
)
REGEX_INSTITUCIONAL: Pattern[str] = re.compile(
    r"\b(?:institucional|branding|marca|corporativo)\b", re.I
)

# Fallback de UF explícita no texto da campanha (ex: "- GO", "/TO", "_PA")
REGEX_UF_EXPLICITA: Pattern[str] = re.compile(
    r"(?:[\s_/\-\|\[\(])(GO|TO|PA|MT|MS|MG|BA|SP|DF|MA)(?:[\s_/\-\|\]\)]|$)"
)


def remover_acentos(texto: str) -> str:
    """Remove diacríticos via decomposição Unicode NFKD e substitui separadores por espaço."""
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in normalizado if not unicodedata.combining(c))
    return re.sub(r"[_\-\|/]+", " ", sem_acento)


@lru_cache(maxsize=4096)
def classificar_campanha(nome_campanha: str) -> Tuple[str, str, str]:
    """
    Extrai deterministicamente (cidade, uf, tipo_lancamento) a partir do nome livre da campanha.

    Retorna:
        Tuple[cidade, uf, tipo_lancamento]
        - cidade: Nome canônico do município ou 'Não Identificada'
        - uf: Sigla da UF (ex: 'GO', 'TO', 'PA') ou 'ND'
        - tipo_lancamento: 'LANÇAMENTO', 'ESTOQUE' ou 'INSTITUCIONAL'
    """
    texto_limpo = remover_acentos(nome_campanha)

    # 1. Identificação hierárquica de Cidade e UF
    cidade_detectada = "Não Identificada"
    uf_detectada = "ND"

    for padrao_mun, cidade_canonica, uf_canonica in CATALOGO_MUNICIPIOS_PADRAO:
        if padrao_mun.search(texto_limpo):
            cidade_detectada = cidade_canonica
            uf_detectada = uf_canonica
            break

    if uf_detectada == "ND":
        match_uf = REGEX_UF_EXPLICITA.search(nome_campanha.upper())
        if match_uf:
            uf_detectada = match_uf.group(1)

    # 2. Identificação hierárquica do Tipo de Campanha
    if REGEX_LANCAMENTO.search(texto_limpo):
        tipo_campanha = "LANÇAMENTO"
    elif REGEX_ESTOQUE.search(texto_limpo):
        tipo_campanha = "ESTOQUE"
    elif REGEX_INSTITUCIONAL.search(texto_limpo):
        tipo_campanha = "INSTITUCIONAL"
    else:
        # Regra default operacional: campanhas de captação contínua sem tag de lançamento vão para ESTOQUE
        tipo_campanha = "ESTOQUE"

    return (cidade_detectada, uf_detectada, tipo_campanha)


def classificar_lote_campanhas(nomes: List[str]) -> List[Dict[str, str]]:
    """Classifica uma lista de nomes de campanhas e retorna dicionários estruturados."""
    resultado: List[Dict[str, str]] = []
    for nome in nomes:
        cidade, uf, tipo = classificar_campanha(nome)
        resultado.append(
            {
                "campaign_name": nome,
                "cidade": cidade,
                "uf": uf,
                "tipo_lancamento": tipo,
            }
        )
    return resultado


def obter_estatisticas_cache_taxonomia() -> Dict[str, int]:
    """Retorna métricas de uso do @lru_cache (hits, misses, maxsize, currsize)."""
    info = classificar_campanha.cache_info()
    return {
        "hits": info.hits,
        "misses": info.misses,
        "maxsize": info.maxsize or 4096,
        "currsize": info.currsize,
    }
