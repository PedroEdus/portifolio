"""
Pipeline Cloud de Marketing & CRM Data Engineering (src/marketing_pipeline.py).

Implementa:
1. Prevenção de dupla contagem de leads no Meta Ads (action__lead primário vs fallback de componentes);
2. Upsert com Lookback de 3 dias via Staging + MERGE na chave (account_id, adset_id, date_start);
3. Ingestão incremental de CRM por watermark (MAX(data_alteracao)) com proteção transacional
   (aborta antes do MERGE se qualquer página da API falhar, evitando avançar a watermark com dados parciais);
4. Detecção granular de lacunas por (property_id, date) no GA4, gravando sentinela para dias com
   0 sessões legítimas ('ZERO_LEGITIMO') para não reconsultar infinitamente;
5. Otimização de Memória RAM (compactar_dataframe_ram): converte colunas string de baixa cardinalidade
   (< 50% de valores únicos) para category dtype e mede a redução percentual de memória.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from src.taxonomia import classificar_campanha


class CRMPageFetchError(RuntimeError):
    """Exceção lançada quando uma página da API do CRM falha durante a extração incremental."""


def inicializar_banco_marketing(db_path: str = ":memory:") -> sqlite3.Connection:
    """
    Inicializa o banco relacional emulando os datasets Silver/Gold do BigQuery
    (analytics-cloud-dw):
    - stg_meta_ads / silver_meta_ads
    - stg_crm_leads / silver_crm_leads
    - silver_ga4_daily
    - ctl_watermark_crm
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS stg_meta_ads (
            account_id TEXT NOT NULL,
            adset_id TEXT NOT NULL,
            date_start TEXT NOT NULL,
            campaign_name TEXT NOT NULL,
            spend REAL NOT NULL,
            impressions INTEGER NOT NULL,
            clicks INTEGER NOT NULL,
            action__lead INTEGER NOT NULL DEFAULT 0,
            action__onsite_conversion_lead_grouped INTEGER NOT NULL DEFAULT 0,
            action__offsite_conversion_fb_pixel_lead INTEGER NOT NULL DEFAULT 0,
            action__onsite_conversion_messaging_lead INTEGER NOT NULL DEFAULT 0,
            leads_validos INTEGER NOT NULL,
            cidade TEXT NOT NULL,
            uf TEXT NOT NULL,
            tipo_lancamento TEXT NOT NULL,
            dt_atualizacao TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS silver_meta_ads (
            account_id TEXT NOT NULL,
            adset_id TEXT NOT NULL,
            date_start TEXT NOT NULL,
            campaign_name TEXT NOT NULL,
            spend REAL NOT NULL,
            impressions INTEGER NOT NULL,
            clicks INTEGER NOT NULL,
            action__lead INTEGER NOT NULL DEFAULT 0,
            action__onsite_conversion_lead_grouped INTEGER NOT NULL DEFAULT 0,
            action__offsite_conversion_fb_pixel_lead INTEGER NOT NULL DEFAULT 0,
            action__onsite_conversion_messaging_lead INTEGER NOT NULL DEFAULT 0,
            leads_validos INTEGER NOT NULL,
            cidade TEXT NOT NULL,
            uf TEXT NOT NULL,
            tipo_lancamento TEXT NOT NULL,
            dt_atualizacao TEXT NOT NULL,
            PRIMARY KEY (account_id, adset_id, date_start)
        );

        CREATE TABLE IF NOT EXISTS silver_crm_leads (
            lead_id TEXT PRIMARY KEY,
            empreendimento TEXT NOT NULL,
            cidade TEXT NOT NULL,
            uf TEXT NOT NULL,
            etapa_funil TEXT NOT NULL,
            origem_midia TEXT NOT NULL,
            valor_proposta REAL NOT NULL DEFAULT 0.0,
            data_criacao TEXT NOT NULL,
            data_alteracao TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS silver_ga4_daily (
            property_id TEXT NOT NULL,
            date_ref TEXT NOT NULL,
            sessions INTEGER NOT NULL,
            total_users INTEGER NOT NULL,
            conversions INTEGER NOT NULL,
            status_coleta TEXT NOT NULL,
            dt_carga TEXT NOT NULL,
            PRIMARY KEY (property_id, date_ref)
        );
        """
    )
    conn.commit()
    return conn


def calcular_leads_sem_dupla_contagem(registro_meta: Dict[str, Any]) -> int:
    """
    Prevenção de Dupla Contagem de Leads no Meta Ads (sources/meta.py).

    Na Graph API v19.0, 'action__lead' já consolida os eventos de formulário nativo e pixel
    quando presente. Somar 'action__lead' com 'onsite_conversion.lead_grouped' e
    'offsite_conversion.fb_pixel_lead' duplica os leads em 2x a 3x.

    Regra:
    - Se action__lead > 0: usa exclusivamente action__lead.
    - Caso contrário (fallback): soma os componentes granulares.
    """
    lead_primario = int(registro_meta.get("action__lead", 0) or 0)
    if lead_primario > 0:
        return lead_primario

    onsite = int(registro_meta.get("action__onsite_conversion_lead_grouped", 0) or 0)
    pixel = int(registro_meta.get("action__offsite_conversion_fb_pixel_lead", 0) or 0)
    msg = int(registro_meta.get("action__onsite_conversion_messaging_lead", 0) or 0)
    return onsite + pixel + msg


def upsert_meta_ads_lookback(
    conn: sqlite3.Connection,
    registros_api: Sequence[Dict[str, Any]],
    data_referencia: str,
    lookback_days: int = 3,
    dt_atualizacao: str = "2026-10-18T06:00:00",
) -> Dict[str, Any]:
    """
    Executa ingestão do Meta Ads com janela de Lookback de 3 dias via Staging + MERGE
    na chave composta (account_id, adset_id, date_start).

    Registros fora da janela [data_referencia - lookback_days, data_referencia] são ignorados,
    enquanto registros dentro da janela sofrem UPSERT atômico, capturando atribuições tardias.
    """
    dt_ref = datetime.strptime(data_referencia, "%Y-%m-%d").date()
    dt_inicio_janela = dt_ref - timedelta(days=lookback_days)

    lote_filtrado: List[Tuple[Any, ...]] = []
    for r in registros_api:
        dt_reg = datetime.strptime(str(r["date_start"]), "%Y-%m-%d").date()
        if not (dt_inicio_janela <= dt_reg <= dt_ref):
            continue

        leads_val = calcular_leads_sem_dupla_contagem(r)
        cidade, uf, tipo_lanc = classificar_campanha(str(r["campaign_name"]))

        lote_filtrado.append(
            (
                str(r["account_id"]),
                str(r["adset_id"]),
                str(r["date_start"]),
                str(r["campaign_name"]),
                round(float(r["spend"]), 2),
                int(r["impressions"]),
                int(r["clicks"]),
                int(r.get("action__lead", 0) or 0),
                int(r.get("action__onsite_conversion_lead_grouped", 0) or 0),
                int(r.get("action__offsite_conversion_fb_pixel_lead", 0) or 0),
                int(r.get("action__onsite_conversion_messaging_lead", 0) or 0),
                leads_val,
                cidade,
                uf,
                tipo_lanc,
                dt_atualizacao,
            )
        )

    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        cur.execute("DELETE FROM stg_meta_ads")
        cur.executemany(
            """
            INSERT INTO stg_meta_ads (
                account_id, adset_id, date_start, campaign_name,
                spend, impressions, clicks,
                action__lead, action__onsite_conversion_lead_grouped,
                action__offsite_conversion_fb_pixel_lead, action__onsite_conversion_messaging_lead,
                leads_validos, cidade, uf, tipo_lancamento, dt_atualizacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            lote_filtrado,
        )

        # Conta quantos registros da staging já existem na Silver (serão atualizados pelo MERGE)
        atualizados = cur.execute(
            """
            SELECT COUNT(*) FROM stg_meta_ads s
            INNER JOIN silver_meta_ads m
                ON m.account_id = s.account_id
               AND m.adset_id = s.adset_id
               AND m.date_start = s.date_start
            """
        ).fetchone()[0]
        inseridos = len(lote_filtrado) - int(atualizados)

        # Emula o MERGE INTO marketing_silver.meta_ads do BigQuery
        cur.execute(
            """
            INSERT INTO silver_meta_ads (
                account_id, adset_id, date_start, campaign_name,
                spend, impressions, clicks,
                action__lead, action__onsite_conversion_lead_grouped,
                action__offsite_conversion_fb_pixel_lead, action__onsite_conversion_messaging_lead,
                leads_validos, cidade, uf, tipo_lancamento, dt_atualizacao
            )
            SELECT
                account_id, adset_id, date_start, campaign_name,
                spend, impressions, clicks,
                action__lead, action__onsite_conversion_lead_grouped,
                action__offsite_conversion_fb_pixel_lead, action__onsite_conversion_messaging_lead,
                leads_validos, cidade, uf, tipo_lancamento, dt_atualizacao
            FROM stg_meta_ads
            WHERE true
            ON CONFLICT(account_id, adset_id, date_start) DO UPDATE SET
                campaign_name = excluded.campaign_name,
                spend = excluded.spend,
                impressions = excluded.impressions,
                clicks = excluded.clicks,
                action__lead = excluded.action__lead,
                action__onsite_conversion_lead_grouped = excluded.action__onsite_conversion_lead_grouped,
                action__offsite_conversion_fb_pixel_lead = excluded.action__offsite_conversion_fb_pixel_lead,
                action__onsite_conversion_messaging_lead = excluded.action__onsite_conversion_messaging_lead,
                leads_validos = excluded.leads_validos,
                cidade = excluded.cidade,
                uf = excluded.uf,
                tipo_lancamento = excluded.tipo_lancamento,
                dt_atualizacao = excluded.dt_atualizacao
            """
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    total_silver = cur.execute("SELECT COUNT(*) FROM silver_meta_ads").fetchone()[0]
    return {
        "janela_inicio": dt_inicio_janela.isoformat(),
        "janela_fim": dt_ref.isoformat(),
        "linhas_staging": len(lote_filtrado),
        "linhas_inseridas": inseridos,
        "linhas_atualizadas_lookback": int(atualizados),
        "total_silver_meta_ads": int(total_silver),
    }


def obter_watermark_crm(conn: sqlite3.Connection) -> Optional[str]:
    """Obtém a watermark atual MAX(data_alteracao) da tabela silver_crm_leads."""
    row = conn.execute(
        "SELECT MAX(data_alteracao) AS wm FROM silver_crm_leads"
    ).fetchone()
    return row["wm"] if row and row["wm"] else None


def ingerir_crm_incremental_com_watermark(
    conn: sqlite3.Connection,
    paginas_api: Sequence[Optional[Sequence[Dict[str, Any]]]],
) -> Dict[str, Any]:
    """
    Ingestão incremental de CRM por watermark (MAX(data_alteracao)) com proteção transacional
    (All-or-Nothing Page Guard — funil_crm.py).

    Se qualquer página da API falhar (representada por None ou exceção durante a coleta),
    o processo aborta ANTES do MERGE no banco, garantindo que a watermark nunca avance com
    dados parciais e prevenindo perda silenciosa de leads.
    """
    watermark_anterior = obter_watermark_crm(conn)

    # Fase 1: Coleta integral em buffer de memória (antes de abrir transação de escrita na Silver)
    buffer_leads: List[Dict[str, Any]] = []
    for idx_pagina, pagina in enumerate(paginas_api, start=1):
        if pagina is None:
            raise CRMPageFetchError(
                f"Falha na extração da página {idx_pagina}/{len(paginas_api)} da API do CRM comercial! "
                f"Abortando antes do MERGE para proteger a watermark ({watermark_anterior})."
            )
        for lead in pagina:
            if watermark_anterior is None or str(lead["data_alteracao"]) > watermark_anterior:
                buffer_leads.append(lead)

    # Fase 2: MERGE atômico na tabela Silver somente se 100% das páginas foram coletadas com sucesso
    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        cur.executemany(
            """
            INSERT INTO silver_crm_leads (
                lead_id, empreendimento, cidade, uf, etapa_funil,
                origem_midia, valor_proposta, data_criacao, data_alteracao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
                empreendimento = excluded.empreendimento,
                cidade = excluded.cidade,
                uf = excluded.uf,
                etapa_funil = excluded.etapa_funil,
                origem_midia = excluded.origem_midia,
                valor_proposta = excluded.valor_proposta,
                data_alteracao = excluded.data_alteracao
            WHERE excluded.data_alteracao >= silver_crm_leads.data_alteracao
            """,
            [
                (
                    str(l["lead_id"]),
                    str(l["empreendimento"]),
                    str(l["cidade"]),
                    str(l["uf"]),
                    str(l["etapa_funil"]),
                    str(l["origem_midia"]),
                    round(float(l.get("valor_proposta", 0.0)), 2),
                    str(l["data_criacao"]),
                    str(l["data_alteracao"]),
                )
                for l in buffer_leads
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    watermark_nova = obter_watermark_crm(conn)
    total_leads = cur.execute("SELECT COUNT(*) FROM silver_crm_leads").fetchone()[0]
    return {
        "watermark_anterior": watermark_anterior,
        "watermark_nova": watermark_nova,
        "registros_processados": len(buffer_leads),
        "total_leads_silver": int(total_leads),
    }


def detectar_e_preencher_lacunas_ga4(
    conn: sqlite3.Connection,
    propriedades_ativas: Sequence[str],
    data_inicio: str,
    data_fim: str,
    respostas_api_por_par: Dict[Tuple[str, str], List[Dict[str, Any]]],
    dt_carga: str = "2026-10-18T06:30:00",
) -> Dict[str, Any]:
    """
    Detector Granular de Lacunas por (property_id, date_ref) no GA4 (load_ga4_v2.py).

    1. Constrói a grade esperada de (property_id, date_ref) no intervalo solicitado.
    2. Verifica quais pares ainda não constam em silver_ga4_daily.
    3. Consulta a API apenas para os pares faltantes.
    4. Se a API retornar 0 linhas legítimas para um par (property_id, date_ref),
       insere um registro sentinela (status_coleta = 'ZERO_LEGITIMO', sessions = 0)
       para que execuções futuras saibam que aquele dia já foi verificado e não
       reconsultem a API infinitamente.
    """
    d_ini = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    d_fim = datetime.strptime(data_fim, "%Y-%m-%d").date()

    dias_grade: List[str] = []
    atual = d_ini
    while atual <= d_fim:
        dias_grade.append(atual.isoformat())
        atual += timedelta(days=1)

    cur = conn.cursor()
    existentes = {
        (r["property_id"], r["date_ref"])
        for r in cur.execute("SELECT property_id, date_ref FROM silver_ga4_daily").fetchall()
    }

    lacunas_detectadas: List[Tuple[str, str]] = []
    for prop in propriedades_ativas:
        for d_str in dias_grade:
            if (prop, d_str) not in existentes:
                lacunas_detectadas.append((prop, d_str))

    linhas_para_inserir: List[Tuple[Any, ...]] = []
    pares_com_trafego = 0
    pares_zero_legitimo = 0

    for prop, d_str in lacunas_detectadas:
        linhas_api = respostas_api_por_par.get((prop, d_str), [])
        if len(linhas_api) == 0:
            pares_zero_legitimo += 1
            linhas_para_inserir.append(
                (prop, d_str, 0, 0, 0, "ZERO_LEGITIMO", dt_carga)
            )
        else:
            pares_com_trafego += 1
            sess = sum(int(x.get("sessions", 0)) for x in linhas_api)
            users = sum(int(x.get("total_users", 0)) for x in linhas_api)
            conv = sum(int(x.get("conversions", 0)) for x in linhas_api)
            linhas_para_inserir.append(
                (prop, d_str, sess, users, conv, "COM_TRAFEGO", dt_carga)
            )

    if linhas_para_inserir:
        cur.execute("BEGIN IMMEDIATE")
        try:
            cur.executemany(
                """
                INSERT OR REPLACE INTO silver_ga4_daily (
                    property_id, date_ref, sessions, total_users,
                    conversions, status_coleta, dt_carga
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                linhas_para_inserir,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "total_grade_esperada": len(propriedades_ativas) * len(dias_grade),
        "lacunas_consultadas_na_api": len(lacunas_detectadas),
        "pares_gravados_com_trafego": pares_com_trafego,
        "pares_gravados_zero_legitimo": pares_zero_legitimo,
    }


def compactar_dataframe_ram(
    df: pd.DataFrame, limiar_cardinalidade: float = 0.50
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Otimizador de Memória RAM para Data Apps Streamlit (painel_campanhas / Painel-Geral).

    Converte colunas string/object de baixa cardinalidade (< 50% de valores únicos)
    para 'category' dtype, reduzindo drasticamente o consumo de RAM em grandes tabelas.
    """
    df_otimizado = df.copy(deep=True)
    bytes_antes = int(df_otimizado.memory_usage(deep=True).sum())
    n_linhas = len(df_otimizado)

    colunas_convertidas: List[str] = []
    if n_linhas > 0:
        for col in df_otimizado.columns:
            dtype_str = str(df_otimizado[col].dtype)
            if dtype_str in ("object", "string", "str") or dtype_str.startswith("str"):
                n_unicos = df_otimizado[col].nunique(dropna=False)
                razao = n_unicos / n_linhas
                if razao < limiar_cardinalidade:
                    df_otimizado[col] = df_otimizado[col].astype("category")
                    colunas_convertidas.append(col)

    bytes_depois = int(df_otimizado.memory_usage(deep=True).sum())
    reducao_pct = (
        round((1.0 - (bytes_depois / bytes_antes)) * 100.0, 2)
        if bytes_antes > 0
        else 0.0
    )

    metricas = {
        "linhas": n_linhas,
        "colunas_totais": len(df_otimizado.columns),
        "colunas_convertidas_category": colunas_convertidas,
        "qtd_colunas_convertidas": len(colunas_convertidas),
        "bytes_antes": bytes_antes,
        "bytes_depois": bytes_depois,
        "reducao_percentual_ram": reducao_pct,
    }
    return df_otimizado, metricas
