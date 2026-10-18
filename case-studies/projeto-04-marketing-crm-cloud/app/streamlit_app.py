"""
Aplicação Executiva Demonstrativa em Streamlit — Estudo de Caso 04 (Painel-Geral & Marketing Cloud).

Destaques de Engenharia:
- Renderização de Funil Comercial em SVG dinâmico codificado em Base64 Data URI (core/charts.py);
- Matriz Hierárquica Expansível nativa em HTML5 <details>/<summary> (UF -> Cidade -> Tipo -> Campanha);
- Otimização de Memória RAM via categorização de colunas de baixa cardinalidade (compactar_dataframe_ram).

AVISO: Todos os dados exibidos nesta aplicação são 100% sintéticos (seed=42).
"""

from __future__ import annotations

import base64
import html
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.marketing_pipeline import compactar_dataframe_ram
from src.taxonomia import classificar_campanha


def gerar_funil_svg_data_uri(etapas: Sequence[Tuple[str, int]]) -> str:
    """
    Gera um gráfico de Funil Executivo em SVG vetorial puro e retorna como Data URI (data:image/svg+xml;base64,...).
    Reproduz a técnica leve utilizada em core/charts.py do Painel-Geral para evitar sobrecarga de iframes.
    """
    largura = 640
    altura_etapa = 48
    altura_total = max(120, len(etapas) * (altura_etapa + 8) + 24)
    max_val = max((v for _, v in etapas), default=1) or 1

    cores = ["#0f172a", "#1e293b", "#1d4ed8", "#2563eb", "#3b82f6", "#0284c7"]
    elementos_svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura_total}" width="100%" height="{altura_total}">',
        '<style>.lbl{font-family:Inter,Segoe UI,sans-serif;font-size:13px;fill:#ffffff;font-weight:600;}</style>',
    ]

    for idx, (nome, valor) in enumerate(etapas):
        proporcao = max(0.28, min(1.0, valor / max_val))
        w_barra = int((largura - 40) * proporcao)
        x_barra = (largura - w_barra) // 2
        y_barra = 12 + idx * (altura_etapa + 8)
        cor = cores[idx % len(cores)]
        nome_esc = html.escape(str(nome))

        elementos_svg.append(
            f'<rect x="{x_barra}" y="{y_barra}" width="{w_barra}" height="{altura_etapa}" rx="6" fill="{cor}" />'
        )
        elementos_svg.append(
            f'<text x="{largura // 2}" y="{y_barra + 29}" text-anchor="middle" class="lbl">{nome_esc}: {valor:,}</text>'
        )

    elementos_svg.append("</svg>")
    svg_raw = "".join(elementos_svg)
    b64 = base64.b64encode(svg_raw.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def gerar_matriz_hierarquica_html(registros: Sequence[Dict[str, Any]]) -> str:
    """
    Constrói uma Matriz Hierárquica Expansível usando tags nativas <details> e <summary>
    agrupando por UF -> Cidade -> Campanha (reproduzindo core/ui.py do Painel-Geral).
    """
    arvore: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for r in registros:
        uf = str(r.get("uf", "ND"))
        cidade = str(r.get("cidade", "Não Identificada"))
        arvore.setdefault(uf, {}).setdefault(cidade, []).append(r)

    blocos: List[str] = ['<div class="matriz-hierarquica">']
    for uf in sorted(arvore.keys()):
        cidades = arvore[uf]
        spend_uf = sum(float(x.get("spend", 0.0)) for lista in cidades.values() for x in lista)
        leads_uf = sum(int(x.get("leads_validos", 0)) for lista in cidades.values() for x in lista)
        cpl_uf = round(spend_uf / leads_uf, 2) if leads_uf > 0 else 0.0

        blocos.append(
            f'<details open style="margin-bottom:8px;border:1px solid #cbd5e1;border-radius:6px;padding:8px;">'
            f'<summary style="font-weight:700;cursor:pointer;">'
            f'UF: {html.escape(uf)} — Investimento: R$ {spend_uf:,.2f} | Leads: {leads_uf} | CPL: R$ {cpl_uf:,.2f}'
            f"</summary>"
        )
        for cidade in sorted(cidades.keys()):
            itens = cidades[cidade]
            spend_cid = sum(float(x.get("spend", 0.0)) for x in itens)
            leads_cid = sum(int(x.get("leads_validos", 0)) for x in itens)
            blocos.append(
                f'<details style="margin:6px 0 6px 18px;padding:6px;border-left:3px solid #2563eb;">'
                f'<summary style="font-weight:600;cursor:pointer;">'
                f'{html.escape(cidade)} — R$ {spend_cid:,.2f} ({leads_cid} leads)'
                f"</summary><ul>"
            )
            for item in itens:
                camp = html.escape(str(item.get("campaign_name", "")))
                tipo = html.escape(str(item.get("tipo_lancamento", "")))
                sp = float(item.get("spend", 0.0))
                ld = int(item.get("leads_validos", 0))
                blocos.append(
                    f"<li><code>[{tipo}]</code> {camp} — <b>R$ {sp:,.2f}</b> ({ld} leads)</li>"
                )
            blocos.append("</ul></details>")
        blocos.append("</details>")
    blocos.append("</div>")
    return "".join(blocos)


def main() -> None:
    import pandas as pd
    import streamlit as st

    st.set_page_config(
        page_title="Painel-Geral Marketing & CRM Cloud (Demo Sintética)",
        layout="wide",
    )
    st.title("Plataforma Cloud de Marketing & CRM — Demo Executiva (Dados Sintéticos)")
    st.caption(
        "Demonstração pública reconstruída: Funil SVG via Data URI, Matriz Hierárquica <details>/<summary> e Otimização de RAM."
    )

    etapas_funil = [
        ("Impressões Qualificadas", 185400),
        ("Cliques de Mídia Paga", 9420),
        ("Leads Válidos (Sem Dupla Contagem)", 1280),
        ("Atendimentos & Visitas no Stand", 410),
        ("Propostas Emitidas no CRM", 145),
        ("Vendas Concluídas", 58),
    ]
    uri_svg = gerar_funil_svg_data_uri(etapas_funil)
    st.subheader("1. Funil Executivo Vetorial (SVG Data URI)")
    st.markdown(f'<img src="{uri_svg}" alt="Funil Executivo SVG"/>', unsafe_allow_html=True)

    amostra_campanhas = [
        {
            "campaign_name": "[LANÇAMENTO] Jardins do Cerrado - Aparecida de Goiânia - Leads",
            "spend": 14500.00,
            "leads_validos": 210,
            "cidade": "Aparecida de Goiânia",
            "uf": "GO",
            "tipo_lancamento": "LANÇAMENTO",
        },
        {
            "campaign_name": "[ESTOQUE] Parque das Águas | Palmas/TO | Retargeting",
            "spend": 9800.00,
            "leads_validos": 140,
            "cidade": "Palmas",
            "uf": "TO",
            "tipo_lancamento": "ESTOQUE",
        },
        {
            "campaign_name": "[LANÇAMENTO] Reserva Carajás - Parauapebas_PA - Conversão",
            "spend": 12300.00,
            "leads_validos": 175,
            "cidade": "Parauapebas",
            "uf": "PA",
            "tipo_lancamento": "LANÇAMENTO",
        },
    ]
    st.subheader("2. Matriz Hierárquica Expansível (<details>/<summary>)")
    st.markdown(gerar_matriz_hierarquica_html(amostra_campanhas), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
