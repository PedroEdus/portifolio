"""
Script de Demonstração Executável — Estudo de Caso 04 (Marketing & CRM Cloud Data Engineering).

Executa localmente toda a esteira de engenharia:
1. Classificação de campanhas pelo motor taxonomia.py (@lru_cache + Regex hierárquico);
2. Ingestão do Meta Ads com janela de Lookback de 3 dias via Staging + MERGE e prevenção de dupla contagem de leads;
3. Ingestão incremental de CRM por watermark (MAX(data_alteracao)) com simulação de falha parcial na Página 2/3
   (comprovando que a watermark não avança) seguida de reexecução íntegra;
4. Detector granular de lacunas no GA4 por (property_id, date_ref) gravando sentinela 'ZERO_LEGITIMO'
   para dias sem tráfego e comprovando 0 reconsultas na segunda rodada;
5. Compactação de memória RAM (compactar_dataframe_ram) convertendo colunas string de baixa cardinalidade
   para category dtype e reduzindo >60% da memória;
6. Geração de evidências em examples/sample_output.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from app.streamlit_app import gerar_funil_svg_data_uri, gerar_matriz_hierarquica_html
from src.marketing_pipeline import (
    CRMPageFetchError,
    compactar_dataframe_ram,
    detectar_e_preencher_lacunas_ga4,
    ingerir_crm_incremental_com_watermark,
    inicializar_banco_marketing,
    obter_watermark_crm,
    upsert_meta_ads_lookback,
)
from src.taxonomia import (
    classificar_campanha,
    classificar_lote_campanhas,
    obter_estatisticas_cache_taxonomia,
)


def gerar_dataframe_sintetico_alta_volumetria(n_linhas: int = 12000) -> pd.DataFrame:
    """Gera um DataFrame sintético com colunas string de baixa cardinalidade (padrão carteira/painel)."""
    empreendimentos = [
        "Jardins do Cerrado I - Aparecida de Goiânia/GO",
        "Parque das Águas Sul - Palmas/TO",
        "Reserva Carajás - Parauapebas/PA",
        "Portal do Sol - Rondonópolis/MT",
        "Bosque dos Ipês - Uberlândia/MG",
        "Vila Imperial - Luís Eduardo Magalhães/BA",
    ]
    etapas = [
        "01 - Lead Captado",
        "02 - Em Atendimento",
        "03 - Visita Agendada",
        "04 - Visita Realizada",
        "05 - Proposta Enviada",
        "06 - Venda Fechada",
    ]
    canais = ["Meta Ads - Instagram", "Google Ads - Search", "Publya - Programática", "QRFY - Stand"]
    status_contrato = ["ADIMPLENTE ELEGIVEL", "EM ANALISE DOCUMENTAL", "QUITADO", "CEDIDO CRI"]

    registros = []
    for i in range(n_linhas):
        registros.append(
            {
                "id_contrato": i + 100000,
                "empreendimento_nome": empreendimentos[i % len(empreendimentos)],
                "etapa_funil_comercial": etapas[i % len(etapas)],
                "canal_aquisicao_midia": canais[i % len(canais)],
                "status_elegibilidade_campanha": status_contrato[i % len(status_contrato)],
                "uf_regional": ("GO", "TO", "PA", "MT", "MG", "BA")[i % 6],
                "valor_contrato": float(120000 + (i % 50) * 1500),
            }
        )
    return pd.DataFrame(registros)


def executar_demonstracao() -> Dict[str, Any]:
    conn = inicializar_banco_marketing(":memory:")
    classificar_campanha.cache_clear()

    # 1. Demonstração do Motor de Taxonomia Regex + @lru_cache
    campanhas_teste = [
        "[LANÇAMENTO] Jardins do Cerrado - Aparecida de Goiania - Leads Fev",
        "RMKT | Parque das Águas | Palmas/TO | Estoque Oportunidade",
        "Busca_Institucional_Marca_Corporativo_GO",
        "Pre-Lancamento_Reserva_Carajas_Parauapebas_PA_Conversao",
        "Campanha_Continua_Lotes_Rondonopolis_MT",
        # Repete nomes para exercitar hits no @lru_cache
        "[LANÇAMENTO] Jardins do Cerrado - Aparecida de Goiania - Leads Fev",
        "RMKT | Parque das Águas | Palmas/TO | Estoque Oportunidade",
    ]
    taxonomia_res = classificar_lote_campanhas(campanhas_teste)
    cache_stats = obter_estatisticas_cache_taxonomia()

    # 2. Meta Ads: Carga inicial + Reprocessamento com Lookback de 3 dias e Anti-Dupla-Contagem
    lote_meta_dia_1 = [
        {
            "account_id": "act_1001",
            "adset_id": "adset_go_01",
            "date_start": "2026-10-16",
            "campaign_name": "[LANÇAMENTO] Jardins do Cerrado - Aparecida de Goiania",
            "spend": 1200.00,
            "impressions": 24000,
            "clicks": 480,
            # Possui action__lead=35 e subcomponentes=20+15 (não pode somar 35+20+15=70!)
            "action__lead": 35,
            "action__onsite_conversion_lead_grouped": 20,
            "action__offsite_conversion_fb_pixel_lead": 15,
            "action__onsite_conversion_messaging_lead": 0,
        },
        {
            "account_id": "act_1002",
            "adset_id": "adset_to_01",
            "date_start": "2026-10-17",
            "campaign_name": "RMKT | Parque das Águas | Palmas/TO | Estoque",
            "spend": 850.00,
            "impressions": 15000,
            "clicks": 310,
            # Sem action__lead primário (0): deve acionar fallback somando 12 + 8 + 4 = 24 leads
            "action__lead": 0,
            "action__onsite_conversion_lead_grouped": 12,
            "action__offsite_conversion_fb_pixel_lead": 8,
            "action__onsite_conversion_messaging_lead": 4,
        },
    ]
    res_meta_1 = upsert_meta_ads_lookback(
        conn, lote_meta_dia_1, data_referencia="2026-10-17", lookback_days=3
    )

    # Rodada do dia seguinte (2026-10-18) com lookback de 3 dias:
    # - Atualiza atribuição tardia de 2026-10-16 (leads_validos passa de 35 para 42, spend 1200 -> 1250)
    # - Insere novo dia 2026-10-18
    lote_meta_dia_2 = [
        {
            "account_id": "act_1001",
            "adset_id": "adset_go_01",
            "date_start": "2026-10-16",
            "campaign_name": "[LANÇAMENTO] Jardins do Cerrado - Aparecida de Goiania",
            "spend": 1250.00,
            "impressions": 24500,
            "clicks": 495,
            "action__lead": 42,
            "action__onsite_conversion_lead_grouped": 25,
            "action__offsite_conversion_fb_pixel_lead": 17,
            "action__onsite_conversion_messaging_lead": 0,
        },
        {
            "account_id": "act_1001",
            "adset_id": "adset_go_01",
            "date_start": "2026-10-18",
            "campaign_name": "[LANÇAMENTO] Jardins do Cerrado - Aparecida de Goiania",
            "spend": 1400.00,
            "impressions": 28000,
            "clicks": 530,
            "action__lead": 48,
            "action__onsite_conversion_lead_grouped": 30,
            "action__offsite_conversion_fb_pixel_lead": 18,
            "action__onsite_conversion_messaging_lead": 0,
        },
    ]
    res_meta_2 = upsert_meta_ads_lookback(
        conn, lote_meta_dia_2, data_referencia="2026-10-18", lookback_days=3
    )

    # 3. CRM comercial: Proteção Transacional de Watermark
    pagina_inicial = [
        {
            "lead_id": "LEAD-001",
            "empreendimento": "Jardins do Cerrado I",
            "cidade": "Aparecida de Goiânia",
            "uf": "GO",
            "etapa_funil": "02 - Em Atendimento",
            "origem_midia": "Meta Ads",
            "valor_proposta": 185000.0,
            "data_criacao": "2026-10-15T10:00:00",
            "data_alteracao": "2026-10-16T12:00:00",
        }
    ]
    res_crm_inicial = ingerir_crm_incremental_com_watermark(conn, [pagina_inicial])
    wm_antes_falha = obter_watermark_crm(conn)

    # Simula extração incremental com 3 páginas onde a página 2 falha (None)
    paginas_com_falha = [
        [
            {
                "lead_id": "LEAD-002",
                "empreendimento": "Parque das Águas Sul",
                "cidade": "Palmas",
                "uf": "TO",
                "etapa_funil": "05 - Proposta Enviada",
                "origem_midia": "Google Ads",
                "valor_proposta": 210000.0,
                "data_criacao": "2026-10-17T09:00:00",
                "data_alteracao": "2026-10-18T15:00:00",
            }
        ],
        None,  # Falha simulada na página 2!
    ]
    falha_crm_protegida = False
    try:
        ingerir_crm_incremental_com_watermark(conn, paginas_com_falha)
    except CRMPageFetchError:
        falha_crm_protegida = True

    wm_apos_falha = obter_watermark_crm(conn)

    # Reexecução com todas as páginas íntegras
    paginas_integras = [
        paginas_com_falha[0],
        [
            {
                "lead_id": "LEAD-003",
                "empreendimento": "Reserva Carajás",
                "cidade": "Parauapebas",
                "uf": "PA",
                "etapa_funil": "06 - Venda Fechada",
                "origem_midia": "Meta Ads",
                "valor_proposta": 245000.0,
                "data_criacao": "2026-10-17T11:00:00",
                "data_alteracao": "2026-10-18T14:00:00",
            }
        ],
    ]
    res_crm_recuperado = ingerir_crm_incremental_com_watermark(conn, paginas_integras)

    # 4. GA4: Detecção granular de lacunas com sentinela de 0 linhas legítimas
    respostas_ga4 = {
        ("PROP-GO-01", "2026-10-17"): [{"sessions": 420, "total_users": 350, "conversions": 28}],
        ("PROP-GO-01", "2026-10-18"): [{"sessions": 510, "total_users": 410, "conversions": 34}],
        ("PROP-TO-02", "2026-10-17"): [],  # Dia legítimo com 0 sessões!
        ("PROP-TO-02", "2026-10-18"): [{"sessions": 190, "total_users": 160, "conversions": 11}],
    }
    res_ga4_rodada_1 = detectar_e_preencher_lacunas_ga4(
        conn,
        propriedades_ativas=["PROP-GO-01", "PROP-TO-02"],
        data_inicio="2026-10-17",
        data_fim="2026-10-18",
        respostas_api_por_par=respostas_ga4,
    )
    # Segunda rodada para o mesmo intervalo: deve detectar 0 lacunas (não reconsulta o dia de 0 sessões!)
    res_ga4_rodada_2 = detectar_e_preencher_lacunas_ga4(
        conn,
        propriedades_ativas=["PROP-GO-01", "PROP-TO-02"],
        data_inicio="2026-10-17",
        data_fim="2026-10-18",
        respostas_api_por_par=respostas_ga4,
    )

    # 5. Compactação de Memória RAM (DataFrame para Streamlit)
    df_bruto = gerar_dataframe_sintetico_alta_volumetria(12000)
    _, metricas_ram = compactar_dataframe_ram(df_bruto, limiar_cardinalidade=0.50)

    # 6. Validação dos Componentes Visuais (SVG Data URI e Matriz HTML)
    svg_uri = gerar_funil_svg_data_uri([("Leads", 1280), ("Vendas", 58)])
    rows_meta = [
        dict(r)
        for r in conn.execute("SELECT * FROM silver_meta_ads ORDER BY date_start").fetchall()
    ]
    html_matriz = gerar_matriz_hierarquica_html(rows_meta)

    relatorio = {
        "projeto": "case-04-marketing-crm-cloud",
        "aviso_dados_sinteticos": "100% sinteticos (seed=42) - Nenhuma informacao corporativa real exposta.",
        "taxonomia_regex_lru_cache": {
            "amostras_classificadas": taxonomia_res[:5],
            "estatisticas_cache": cache_stats,
        },
        "meta_ads_lookback_merge": {
            "carga_inicial": res_meta_1,
            "reprocessamento_lookback_3d": res_meta_2,
            "registros_silver_consolidados": rows_meta,
        },
        "crm_protecao_transacional_watermark": {
            "carga_inicial": res_crm_inicial,
            "falha_parcial_pagina_bloqueada": falha_crm_protegida,
            "watermark_antes_falha": wm_antes_falha,
            "watermark_apos_falha_intacta": wm_apos_falha,
            "recuperacao_integra": res_crm_recuperado,
        },
        "ga4_detector_granular_lacunas": {
            "rodada_1_preenchimento": res_ga4_rodada_1,
            "rodada_2_zero_reconsultas": res_ga4_rodada_2,
        },
        "otimizacao_memoria_ram_streamlit": metricas_ram,
        "componentes_ui_validados": {
            "svg_data_uri_prefix": svg_uri[:35],
            "tamanho_html_matriz_details": len(html_matriz),
        },
    }

    output_path = Path(__file__).resolve().parent / "examples" / "sample_output.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return relatorio


if __name__ == "__main__":
    res = executar_demonstracao()
    print("=== DEMONSTRACAO MARKETING & CRM CLOUD DATA ENGINEERING CONCLUIDA ===")
    print(
        f"Taxonomia Cache: hits={res['taxonomia_regex_lru_cache']['estatisticas_cache']['hits']}, "
        f"misses={res['taxonomia_regex_lru_cache']['estatisticas_cache']['misses']}"
    )
    print(
        f"Meta Ads MERGE Lookback: total_silver={res['meta_ads_lookback_merge']['reprocessamento_lookback_3d']['total_silver_meta_ads']}, "
        f"atualizadas_lookback={res['meta_ads_lookback_merge']['reprocessamento_lookback_3d']['linhas_atualizadas_lookback']}"
    )
    print(
        f"CRM Watermark Guard: falha_bloqueada={res['crm_protecao_transacional_watermark']['falha_parcial_pagina_bloqueada']}, "
        f"watermark_final={res['crm_protecao_transacional_watermark']['recuperacao_integra']['watermark_nova']}"
    )
    print(
        f"GA4 Gap Detector: rodada_1_consultas={res['ga4_detector_granular_lacunas']['rodada_1_preenchimento']['lacunas_consultadas_na_api']}, "
        f"rodada_2_consultas={res['ga4_detector_granular_lacunas']['rodada_2_zero_reconsultas']['lacunas_consultadas_na_api']}"
    )
    print(
        f"Otimizacao RAM: reducao={res['otimizacao_memoria_ram_streamlit']['reducao_percentual_ram']}%"
    )
