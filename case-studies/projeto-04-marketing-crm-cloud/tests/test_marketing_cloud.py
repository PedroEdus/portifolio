"""
Suíte de Testes Automatizados (pytest) — Estudo de Caso 04: Plataforma Cloud de Marketing & CRM.

Cobre:
1. Proteção transacional de watermark do CRM em falha parcial de paginação;
2. Upsert idempotente com Lookback de 3 dias via Staging + MERGE no Meta Ads;
3. Prevenção de dupla contagem de leads (action__lead primário vs fallback de componentes);
4. Motor de taxonomia regex com @lru_cache(maxsize=4096);
5. Detecção granular de lacunas no GA4 registrando sentinela de 0 linhas legítimas;
6. Redução de memória RAM (>50%) via categorização automática de colunas string;
7. Componentes visuais do Data App (Funil SVG via Data URI e Matriz <details>/<summary>).
"""

from __future__ import annotations

from pathlib import Path
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.streamlit_app import gerar_funil_svg_data_uri, gerar_matriz_hierarquica_html
from run_demo import executar_demonstracao, gerar_dataframe_sintetico_alta_volumetria
from src.marketing_pipeline import (
    CRMPageFetchError,
    calcular_leads_sem_dupla_contagem,
    compactar_dataframe_ram,
    detectar_e_preencher_lacunas_ga4,
    ingerir_crm_incremental_com_watermark,
    inicializar_banco_marketing,
    obter_watermark_crm,
    upsert_meta_ads_lookback,
)
from src.taxonomia import (
    classificar_campanha,
    obter_estatisticas_cache_taxonomia,
)


def test_protecao_transacional_watermark_crm_em_falha_parcial() -> None:
    conn = inicializar_banco_marketing(":memory:")

    # Carga base inicial
    ingerir_crm_incremental_com_watermark(
        conn,
        [
            [
                {
                    "lead_id": "L-100",
                    "empreendimento": "Jardins I",
                    "cidade": "Goiânia",
                    "uf": "GO",
                    "etapa_funil": "01 - Lead Captado",
                    "origem_midia": "Meta Ads",
                    "valor_proposta": 150000.0,
                    "data_criacao": "2026-10-10T10:00:00",
                    "data_alteracao": "2026-10-15T12:00:00",
                }
            ]
        ],
    )
    assert obter_watermark_crm(conn) == "2026-10-15T12:00:00"

    # Tentativa incremental onde a Página 1 traz um lead de 2026-10-18, mas a Página 2 falha (None)
    paginas_com_erro = [
        [
            {
                "lead_id": "L-101",
                "empreendimento": "Jardins I",
                "cidade": "Goiânia",
                "uf": "GO",
                "etapa_funil": "05 - Proposta Enviada",
                "origem_midia": "Google Ads",
                "valor_proposta": 195000.0,
                "data_criacao": "2026-10-17T08:00:00",
                "data_alteracao": "2026-10-18T18:00:00",
            }
        ],
        None,
    ]
    with pytest.raises(CRMPageFetchError, match="Abortando antes do MERGE"):
        ingerir_crm_incremental_com_watermark(conn, paginas_com_erro)

    # A watermark NÃO pode ter avançado para 2026-10-18 e L-101 não pode ter sido gravado parcialmente
    assert obter_watermark_crm(conn) == "2026-10-15T12:00:00"
    total_leads = conn.execute("SELECT COUNT(*) FROM silver_crm_leads").fetchone()[0]
    assert total_leads == 1


def test_upsert_meta_ads_lookback_3_dias_idempotente() -> None:
    conn = inicializar_banco_marketing(":memory:")
    lote_inicial = [
        {
            "account_id": "act_1",
            "adset_id": "adset_1",
            "date_start": "2026-10-16",
            "campaign_name": "[LANÇAMENTO] Jardins - Aparecida de Goiânia",
            "spend": 500.0,
            "impressions": 10000,
            "clicks": 200,
            "action__lead": 10,
        },
        # Registro fora da janela de lookback de 3 dias (ex: 10 dias atrás) deve ser ignorado pela janela
        {
            "account_id": "act_1",
            "adset_id": "adset_1",
            "date_start": "2026-10-01",
            "campaign_name": "[LANÇAMENTO] Jardins - Aparecida de Goiânia",
            "spend": 300.0,
            "impressions": 5000,
            "clicks": 100,
            "action__lead": 5,
        },
    ]
    r1 = upsert_meta_ads_lookback(conn, lote_inicial, data_referencia="2026-10-18", lookback_days=3)
    assert r1["linhas_inseridas"] == 1
    assert r1["total_silver_meta_ads"] == 1

    # Reprocessamento com atribuição tardia para 2026-10-16 (spend 500 -> 580, leads 10 -> 14)
    lote_revisado = [
        {
            "account_id": "act_1",
            "adset_id": "adset_1",
            "date_start": "2026-10-16",
            "campaign_name": "[LANÇAMENTO] Jardins - Aparecida de Goiânia",
            "spend": 580.0,
            "impressions": 10500,
            "clicks": 215,
            "action__lead": 14,
        }
    ]
    r2 = upsert_meta_ads_lookback(conn, lote_revisado, data_referencia="2026-10-18", lookback_days=3)
    assert r2["linhas_atualizadas_lookback"] == 1
    assert r2["total_silver_meta_ads"] == 1

    row = conn.execute(
        "SELECT spend, leads_validos FROM silver_meta_ads WHERE date_start = '2026-10-16'"
    ).fetchone()
    assert row["spend"] == 580.0
    assert row["leads_validos"] == 14


def test_prevencao_dupla_contagem_leads_meta() -> None:
    # Caso 1: action__lead preenchido -> ignora subcomponentes para evitar somar em dobro
    reg_com_primario = {
        "action__lead": 50,
        "action__onsite_conversion_lead_grouped": 30,
        "action__offsite_conversion_fb_pixel_lead": 20,
        "action__onsite_conversion_messaging_lead": 5,
    }
    assert calcular_leads_sem_dupla_contagem(reg_com_primario) == 50

    # Caso 2: action__lead zerado/ausente -> fallback soma os componentes granulares
    reg_sem_primario = {
        "action__lead": 0,
        "action__onsite_conversion_lead_grouped": 15,
        "action__offsite_conversion_fb_pixel_lead": 10,
        "action__onsite_conversion_messaging_lead": 3,
    }
    assert calcular_leads_sem_dupla_contagem(reg_sem_primario) == 28


def test_motor_taxonomia_regex_lru_cache() -> None:
    classificar_campanha.cache_clear()

    c1, uf1, t1 = classificar_campanha("[LANÇAMENTO] Jardins - Aparecida de Goiânia - Fev")
    assert (c1, uf1, t1) == ("Aparecida de Goiânia", "GO", "LANÇAMENTO")

    c2, uf2, t2 = classificar_campanha("RMKT | Palmas/TO | Oportunidade Estoque")
    assert (c2, uf2, t2) == ("Palmas", "TO", "ESTOQUE")

    c3, uf3, t3 = classificar_campanha("Campanha Institucional Branding - PA")
    assert (c3, uf3, t3) == ("Não Identificada", "PA", "INSTITUCIONAL")

    # Segunda chamada com mesmo texto deve incrementar hits no @lru_cache
    _ = classificar_campanha("[LANÇAMENTO] Jardins - Aparecida de Goiânia - Fev")
    stats = obter_estatisticas_cache_taxonomia()
    assert stats["hits"] >= 1
    assert stats["maxsize"] == 4096


def test_deteccao_granular_lacunas_ga4_com_sentinela_zero_linhas() -> None:
    conn = inicializar_banco_marketing(":memory:")
    respostas = {
        ("PROP-1", "2026-10-17"): [{"sessions": 100, "total_users": 80, "conversions": 5}],
        ("PROP-1", "2026-10-18"): [],  # Zero sessões legítimas
    }
    r1 = detectar_e_preencher_lacunas_ga4(
        conn, ["PROP-1"], "2026-10-17", "2026-10-18", respostas
    )
    assert r1["lacunas_consultadas_na_api"] == 2
    assert r1["pares_gravados_com_trafego"] == 1
    assert r1["pares_gravados_zero_legitimo"] == 1

    # Nova execução para o mesmo período não deve reconsultar o dia de zero sessões
    r2 = detectar_e_preencher_lacunas_ga4(
        conn, ["PROP-1"], "2026-10-17", "2026-10-18", respostas
    )
    assert r2["lacunas_consultadas_na_api"] == 0


def test_compactar_dataframe_ram_reduz_memoria_acima_50_pct() -> None:
    df = gerar_dataframe_sintetico_alta_volumetria(10000)
    df_opt, metricas = compactar_dataframe_ram(df, limiar_cardinalidade=0.50)

    assert metricas["reducao_percentual_ram"] >= 55.0
    assert metricas["qtd_colunas_convertidas"] == 5
    assert str(df_opt["empreendimento_nome"].dtype) == "category"


def test_execucao_completa_demo_e_componentes_visuais() -> None:
    relatorio = executar_demonstracao()
    assert relatorio["crm_protecao_transacional_watermark"]["falha_parcial_pagina_bloqueada"] is True

    uri = gerar_funil_svg_data_uri([("Leads", 500), ("Vendas", 25)])
    assert uri.startswith("data:image/svg+xml;base64,")

    html_mat = gerar_matriz_hierarquica_html(
        relatorio["meta_ads_lookback_merge"]["registros_silver_consolidados"]
    )
    assert "<details" in html_mat and "<summary" in html_mat
