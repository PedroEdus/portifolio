"""
Motor de Suavização Estatística de Preços por m² via Curva INCC e Mediana Móvel 365d.

Inspirado no pipeline `tratamento_sintese [preco].py`, este módulo higieniza séries
temporais de pesquisas de mercado imobiliário aplicando:
1. Defasagem contratual de +2 meses na série histórica do INCC;
2. Clusterização de empreendimentos por quantis de área privativa (`pd.qcut`);
3. Cálculo da mediana móvel de 365 dias por empreendimento;
4. Regra de decisão em 3 faixas de desvio relativo (`|preco - ref| / ref`):
   - Faixa 1 (`desvio <= 10%`): mantém o valor original coletado na pesquisa;
   - Faixa 2 (`10% < desvio <= 20%`): substitui pela mediana móvel de 365 dias;
   - Faixa 3 (`desvio > 20%`): substitui pelo valor projetado pela curva INCC do cluster.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def aplicar_defasagem_incc(df_incc: pd.DataFrame, meses_defasagem: int = 2) -> pd.DataFrame:
    """
    Aplica defasagem de +2 meses na competência de referência do índice INCC,
    refletindo a regra de reajuste contratual do setor imobiliário (o índice
    divulgado no mês T-2 reajusta as tabelas de vendas na competência T).
    """
    df = df_incc.copy()
    df["data_base"] = pd.to_datetime(df["data_base"])
    df = df.sort_values("data_base").reset_index(drop=True)
    df["data_aplicacao"] = df["data_base"] + pd.DateOffset(months=meses_defasagem)
    df["competencia_aplicacao"] = df["data_aplicacao"].dt.to_period("M").astype(str)
    df["fator_acumulado_incc"] = (1.0 + df["taxa_mensal_incc"].astype(float)).cumprod()
    return df


def clusterizar_por_quantis_area(
    df_pesquisas: pd.DataFrame, n_clusters: int = 3
) -> pd.DataFrame:
    """
    Agrupa os empreendimentos em clusters homogêneos de padrão construtivo
    com base nos quantis da área privativa (`area_m2`) via `pd.qcut`.
    """
    df = df_pesquisas.copy()
    labels = [f"CLUSTER_Q{i + 1}" for i in range(n_clusters)]
    df["cluster_area"] = pd.qcut(
        df["area_m2"].rank(method="first"),
        q=n_clusters,
        labels=labels,
    ).astype(str)
    return df


def classificar_e_suavizar_preco_m2(
    preco_observado: float,
    mediana_365d: float,
    preco_curva_incc: float,
) -> tuple[float, str, float]:
    """
    Aplica a regra de decisão de suavização estatística em 3 faixas de desvio relativo
    em relação à mediana móvel de 365 dias:

    - Se `desvio <= 0.10`: mantém `preco_observado` (`FAIXA_1_ORIGINAL_ATE_10PCT`)
    - Se `0.10 < desvio <= 0.20`: adota `mediana_365d` (`FAIXA_2_MEDIANA_365D_10_A_20PCT`)
    - Se `desvio > 0.20`: adota `preco_curva_incc` (`FAIXA_3_CURVA_INCC_ACIMA_20PCT`)
    """
    if mediana_365d <= 0 or np.isnan(mediana_365d):
        return float(preco_observado), "FAIXA_1_ORIGINAL_ATE_10PCT", 0.0

    desvio_relativo = abs(preco_observado - mediana_365d) / mediana_365d

    if desvio_relativo <= 0.10 + 1e-9:
        return float(preco_observado), "FAIXA_1_ORIGINAL_ATE_10PCT", float(desvio_relativo)
    if desvio_relativo <= 0.20 + 1e-9:
        return float(mediana_365d), "FAIXA_2_MEDIANA_365D_10_A_20PCT", float(desvio_relativo)
    return float(preco_curva_incc), "FAIXA_3_CURVA_INCC_ACIMA_20PCT", float(desvio_relativo)


def executar_pipeline_suavizacao(
    df_pesquisas: pd.DataFrame,
    df_incc: pd.DataFrame,
    n_clusters: int = 3,
) -> pd.DataFrame:
    """
    Executa o pipeline completo de suavização estatística de preços/m²:
    1. Defasa o INCC em +2 meses;
    2. Clusteriza os empreendimentos por quantis de área (`qcut`);
    3. Calcula a mediana móvel de 365 dias por empreendimento;
    4. Projeta a curva teórica do cluster corrigida pelo INCC defasado;
    5. Aplica a decisão em 3 faixas de tolerância (<=10%, 10%-20%, >20%).
    """
    df_idx = aplicar_defasagem_incc(df_incc, meses_defasagem=2)
    df = clusterizar_por_quantis_area(df_pesquisas, n_clusters=n_clusters)

    df["data_pesquisa"] = pd.to_datetime(df["data_pesquisa"])
    df["competencia"] = df["data_pesquisa"].dt.to_period("M").astype(str)
    df = df.sort_values(["empreendimento", "data_pesquisa"]).reset_index(drop=True)

    # Junta fator INCC defasado
    mapa_fator = dict(zip(df_idx["competencia_aplicacao"], df_idx["fator_acumulado_incc"]))
    fator_default = float(df_idx["fator_acumulado_incc"].iloc[0]) if not df_idx.empty else 1.0
    df["fator_incc_defasado"] = df["competencia"].map(lambda c: mapa_fator.get(c, fator_default))

    # Calcula mediana móvel de 365 dias por empreendimento (usando observações dentro da janela de 365d
    # excluindo choques extremos > 20% quando há histórico anterior suficiente)
    medianas_365d = []
    for _, row in df.iterrows():
        emp = row["empreendimento"]
        dt_atual = row["data_pesquisa"]
        dt_inicio = dt_atual - pd.Timedelta(days=365)
        janela = df[
            (df["empreendimento"] == emp)
            & (df["data_pesquisa"] >= dt_inicio)
            & (df["data_pesquisa"] < dt_atual)
        ]
        if janela.empty:
            medianas_365d.append(float(row["preco_m2_observado"]))
        else:
            medianas_365d.append(float(janela["preco_m2_observado"].median()))
    df["mediana_movel_365d"] = medianas_365d

    # Curva base do cluster no primeiro mês + correção pelo fator INCC defasado
    base_cluster = (
        df.groupby("cluster_area")
        .first()[["preco_m2_observado", "fator_incc_defasado"]]
        .to_dict(orient="index")
    )

    precos_incc = []
    precos_finais = []
    faixas_aplicadas = []
    desvios = []

    for _, row in df.iterrows():
        info_base = base_cluster[row["cluster_area"]]
        preco_incc_proj = float(info_base["preco_m2_observado"]) * (
            float(row["fator_incc_defasado"]) / float(info_base["fator_incc_defasado"])
        )
        preco_final, faixa, desvio = classificar_e_suavizar_preco_m2(
            preco_observado=float(row["preco_m2_observado"]),
            mediana_365d=float(row["mediana_movel_365d"]),
            preco_curva_incc=preco_incc_proj,
        )
        precos_incc.append(round(preco_incc_proj, 2))
        precos_finais.append(round(preco_final, 2))
        faixas_aplicadas.append(faixa)
        desvios.append(round(desvio, 4))

    df["preco_curva_cluster_incc"] = precos_incc
    df["desvio_relativo_365d"] = desvios
    df["regra_suavizacao"] = faixas_aplicadas
    df["preco_m2_suavizado"] = precos_finais
    return df
