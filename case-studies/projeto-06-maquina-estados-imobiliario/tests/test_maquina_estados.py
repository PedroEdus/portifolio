"""
Suíte de testes automatizados (pytest) para o Estudo de Caso 06:
- Resolução de conflitos cronológicos na Fotografia Mensal de Estoque (`state_machine_estoque.py`)
- Regra de 3 faixas na Suavização Estatística de Preços/m² com INCC defasado (`suavizacao_estatistica_incc.py`)
- Funções geoespaciais: Haversine, dispersão polar sem colisão e área de polígonos via Shoelace (`geoespacial_utils.py`)
"""

from __future__ import annotations

import math
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geoespacial_utils import (
    ajustar_coordenadas_duplicadas_fast,
    calcular_area_poligono_shoelace_m2,
    haversine_km,
)
from src.state_machine_estoque import (
    EventoContratual,
    UnidadeImobiliaria,
    reconstruir_fotografia_mensal,
)
from src.suavizacao_estatistica_incc import (
    aplicar_defasagem_incc,
    classificar_e_suavizar_preco_m2,
    executar_pipeline_suavizacao,
)


def test_resolucao_conflito_cronologico_distrato_tardio() -> None:
    """
    Garante que quando o distrato do contrato N (1001) é registrado em 2025-04-10,
    após a venda do contrato N+1 (1002) ocorrida em 2025-03-05, a unidade permanece
    com estado 'Vendida' (contrato 1002) em Março, Abril e Maio de 2025, e não 'Distratada'.
    """
    unidades = [
        UnidadeImobiliaria(
            id_unidade="UN-01",
            empreendimento="Reserva Sul",
            data_lancamento="2025-01-01",
            is_permuta=False,
        )
    ]
    eventos = [
        EventoContratual("UN-01", 1001, "PROPOSTA_ASSINATURA", "2025-01-10", "Anapro"),
        EventoContratual("UN-01", 1001, "VENDA", "2025-02-05", "Sienge"),
        EventoContratual("UN-01", 1002, "VENDA", "2025-03-05", "CV"),
        # Distrato tardio do contrato 1001 registrado somente em Abril/2025:
        EventoContratual("UN-01", 1001, "DISTRATO", "2025-04-10", "Sienge"),
    ]

    df_foto = reconstruir_fotografia_mensal(unidades, eventos, "2025-01", "2025-05")
    estados_por_mes = dict(zip(df_foto["competencia"], df_foto["estado_estoque"]))
    contratos_por_mes = dict(zip(df_foto["competencia"], df_foto["contrato_vigente"]))

    assert estados_por_mes["2025-01"] == "Assinatura Pendente"
    assert estados_por_mes["2025-02"] == "Vendida"
    assert estados_por_mes["2025-03"] == "Vendida"
    assert estados_por_mes["2025-04"] == "Vendida"
    assert estados_por_mes["2025-05"] == "Vendida"

    assert contratos_por_mes["2025-04"] == 1002
    assert bool(df_foto.loc[df_foto["competencia"] == "2025-04", "teve_conflito_corrigido"].iloc[0]) is True


def test_suavizacao_estatistica_tres_faixas_e_defasagem_incc() -> None:
    # Testa individualmente as 3 faixas de tolerância: <=10%, 10%-20%, >20%
    p1, f1, d1 = classificar_e_suavizar_preco_m2(10500.0, 10000.0, 10200.0)
    assert p1 == 10500.0
    assert f1 == "FAIXA_1_ORIGINAL_ATE_10PCT"
    assert math.isclose(d1, 0.05, rel_tol=1e-6)

    p2, f2, d2 = classificar_e_suavizar_preco_m2(11500.0, 10000.0, 10200.0)
    assert p2 == 10000.0
    assert f2 == "FAIXA_2_MEDIANA_365D_10_A_20PCT"
    assert math.isclose(d2, 0.15, rel_tol=1e-6)

    p3, f3, d3 = classificar_e_suavizar_preco_m2(13500.0, 10000.0, 10200.0)
    assert p3 == 10200.0
    assert f3 == "FAIXA_3_CURVA_INCC_ACIMA_20PCT"
    assert math.isclose(d3, 0.35, rel_tol=1e-6)

    # Testa defasagem de +2 meses no INCC e pipeline completo
    df_incc = pd.DataFrame(
        [
            {"data_base": "2024-11-01", "taxa_mensal_incc": 0.01},
            {"data_base": "2024-12-01", "taxa_mensal_incc": 0.01},
            {"data_base": "2025-01-01", "taxa_mensal_incc": 0.01},
        ]
    )
    df_lag = aplicar_defasagem_incc(df_incc, meses_defasagem=2)
    assert list(df_lag["competencia_aplicacao"]) == ["2025-01", "2025-02", "2025-03"]

    df_pesq = pd.DataFrame(
        [
            {"empreendimento": "Emp A", "area_m2": 50.0, "data_pesquisa": "2025-01-10", "preco_m2_observado": 10000.0},
            {"empreendimento": "Emp A", "area_m2": 50.0, "data_pesquisa": "2025-02-10", "preco_m2_observado": 11500.0},
            {"empreendimento": "Emp A", "area_m2": 50.0, "data_pesquisa": "2025-03-10", "preco_m2_observado": 15000.0},
            {"empreendimento": "Emp B", "area_m2": 90.0, "data_pesquisa": "2025-01-10", "preco_m2_observado": 12000.0},
            {"empreendimento": "Emp C", "area_m2": 180.0, "data_pesquisa": "2025-01-10", "preco_m2_observado": 14000.0},
        ]
    )
    df_out = executar_pipeline_suavizacao(df_pesq, df_incc, n_clusters=3)
    emp_a = df_out[df_out["empreendimento"] == "Emp A"].reset_index(drop=True)
    assert emp_a.loc[0, "regra_suavizacao"] == "FAIXA_1_ORIGINAL_ATE_10PCT"
    assert emp_a.loc[1, "regra_suavizacao"] == "FAIXA_2_MEDIANA_365D_10_A_20PCT"
    assert emp_a.loc[2, "regra_suavizacao"] == "FAIXA_3_CURVA_INCC_ACIMA_20PCT"


def test_geoespacial_haversine_dispersao_polar_e_shoelace() -> None:
    # 1. Haversine: 1 grau de latitude no meridiano equivale a ~111.195 km
    dist_1deg = haversine_km(0.0, 0.0, 1.0, 0.0)
    assert 111.0 <= dist_1deg <= 111.4

    # 2. Dispersão Polar: 5 pontos idênticos passam a ter 5 coordenadas únicas dentro de ~30m
    df_dup = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "latitude": [-16.700000] * 5,
            "longitude": [-49.260000] * 5,
        }
    )
    df_adj = ajustar_coordenadas_duplicadas_fast(df_dup, raio_base_metros=10.0, pontos_por_anel=4)
    pares_unicos = set(zip(df_adj["lat_ajustada"].round(8), df_adj["lon_ajustada"].round(8)))
    assert len(pares_unicos) == 5

    # O ponto 0 permanece exatamente no centro original
    assert df_adj.loc[0, "lat_ajustada"] == -16.700000
    assert df_adj.loc[0, "lon_ajustada"] == -49.260000

    # Todos os pontos dispersos permanecem na mesma vizinhança (< 0.05 km = 50 metros)
    for idx in range(1, 5):
        d_km = haversine_km(
            -16.700000,
            -49.260000,
            float(df_adj.loc[idx, "lat_ajustada"]),
            float(df_adj.loc[idx, "lon_ajustada"]),
        )
        assert 0.005 <= d_km <= 0.030

    # 3. Shoelace: quadrado de 100m x 100m = 10.000 m² no Equador
    d_deg = 100.0 / 111_320.0
    quadrado = [
        (0.0, 0.0),
        (0.0, d_deg),
        (d_deg, d_deg),
        (d_deg, 0.0),
    ]
    area = calcular_area_poligono_shoelace_m2(quadrado)
    assert math.isclose(area, 10_000.0, rel_tol=1e-3)
