"""
Script de demonstração ponta a ponta do Estudo de Caso 06:
Máquina do Tempo de Estoque Imobiliário (Multi-CRM/ERP),
Suavização Estatística de Preços via INCC e Enriquecimento Geoespacial.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

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
from src.suavizacao_estatistica_incc import executar_pipeline_suavizacao


def main() -> None:
    # 1. Demonstração da Máquina de Estados de Estoque com Conflito Cronológico (Contrato N vs N+1)
    unidades = [
        UnidadeImobiliaria(
            id_unidade="TORRE-A-101",
            empreendimento="Residencial Reserva Flamboyant",
            data_lancamento="2025-01-01",
            is_permuta=False,
        ),
        UnidadeImobiliaria(
            id_unidade="TORRE-A-102",
            empreendimento="Residencial Reserva Flamboyant",
            data_lancamento="2025-01-01",
            is_permuta=True,
        ),
    ]

    # Anomalia real: Contrato 1001 foi vendido em Jan/2025, mas seu DISTRATO só foi
    # baixa contábil no ERP em Abril/2025 (2025-04-10), DEPOIS que a unidade já havia
    # sido revendida no Contrato 1002 em Março/2025 (2025-03-05)!
    eventos = [
        EventoContratual(
            id_unidade="TORRE-A-101",
            numero_contrato=1001,
            tipo_evento="VENDA",
            data_evento="2025-01-15",
            origem_sistema="Sienge",
        ),
        EventoContratual(
            id_unidade="TORRE-A-101",
            numero_contrato=1002,
            tipo_evento="VENDA",
            data_evento="2025-03-05",
            origem_sistema="CV_ConstrutorDeVendas",
        ),
        EventoContratual(
            id_unidade="TORRE-A-101",
            numero_contrato=1001,
            tipo_evento="DISTRATO",
            data_evento="2025-04-10",
            origem_sistema="Sienge",
        ),
    ]

    df_fotografia = reconstruir_fotografia_mensal(
        unidades=unidades,
        eventos=eventos,
        mes_inicio="2025-01",
        mes_fim="2025-05",
    )

    # 2. Demonstração da Suavização Estatística de Preços/m² via INCC (+2m lag) e 3 Faixas
    df_incc = pd.DataFrame(
        [
            {"data_base": "2024-11-01", "taxa_mensal_incc": 0.0050},
            {"data_base": "2024-12-01", "taxa_mensal_incc": 0.0060},
            {"data_base": "2025-01-01", "taxa_mensal_incc": 0.0070},
            {"data_base": "2025-02-01", "taxa_mensal_incc": 0.0055},
            {"data_base": "2025-03-01", "taxa_mensal_incc": 0.0065},
        ]
    )

    df_pesquisas = pd.DataFrame(
        [
            # Histórico base do Residencial Alpha (compacto 60 m²)
            {"empreendimento": "Residencial Alpha", "area_m2": 60.0, "data_pesquisa": "2025-01-15", "preco_m2_observado": 10000.0},
            {"empreendimento": "Residencial Alpha", "area_m2": 60.0, "data_pesquisa": "2025-02-15", "preco_m2_observado": 10050.0},
            # Faixa 1 (<= 10% de desvio sobre mediana ~10025): mantém original (10400 -> ~3.7% desvio)
            {"empreendimento": "Residencial Alpha", "area_m2": 60.0, "data_pesquisa": "2025-03-15", "preco_m2_observado": 10400.0},
            # Faixa 2 (10% a 20% de desvio): substitui pela mediana 365d (11600 -> ~15.4% desvio)
            {"empreendimento": "Residencial Alpha", "area_m2": 60.0, "data_pesquisa": "2025-04-15", "preco_m2_observado": 11600.0},
            # Faixa 3 (> 20% de desvio - erro de digitação/outlier): usa curva INCC do cluster (14500 -> >40% desvio)
            {"empreendimento": "Residencial Alpha", "area_m2": 60.0, "data_pesquisa": "2025-05-15", "preco_m2_observado": 14500.0},
            # Outros padrões de área para compor os quantis (qcut)
            {"empreendimento": "Parque Beta", "area_m2": 110.0, "data_pesquisa": "2025-01-15", "preco_m2_observado": 12000.0},
            {"empreendimento": "Mansões Gamma", "area_m2": 220.0, "data_pesquisa": "2025-01-15", "preco_m2_observado": 15000.0},
        ]
    )

    df_suavizado = executar_pipeline_suavizacao(df_pesquisas, df_incc, n_clusters=3)

    # 3. Demonstração Geoespacial: Haversine, Dispersão Polar de CEPs Duplicados e Área Shoelace
    dist_km = haversine_km(-16.7045, -49.2646, -16.6869, -49.2648)

    df_coords = pd.DataFrame(
        [
            {"id_imovel": "IMV-01", "cep": "74810-100", "latitude": -16.704500, "longitude": -49.264600},
            {"id_imovel": "IMV-02", "cep": "74810-100", "latitude": -16.704500, "longitude": -49.264600},
            {"id_imovel": "IMV-03", "cep": "74810-100", "latitude": -16.704500, "longitude": -49.264600},
            {"id_imovel": "IMV-04", "cep": "74810-100", "latitude": -16.704500, "longitude": -49.264600},
        ]
    )
    df_disperso = ajustar_coordenadas_duplicadas_fast(df_coords, raio_base_metros=15.0)

    # Polígono retangular de aproximadamente 100m x 50m = 5.000 m² em Goiânia
    dlat_50m = 50.0 / 111_320.0
    dlon_100m = 100.0 / (111_320.0 * 0.957795)  # cos(-16.7045 deg)
    poligono_terreno = [
        (-16.704500, -49.264600),
        (-16.704500, -49.264600 + dlon_100m),
        (-16.704500 + dlat_50m, -49.264600 + dlon_100m),
        (-16.704500 + dlat_50m, -49.264600),
    ]
    area_m2 = calcular_area_poligono_shoelace_m2(poligono_terreno)

    payload = {
        "case_study": "projeto-06-maquina-estados-imobiliario",
        "fotografia_mensal_estoque": df_fotografia.to_dict(orient="records"),
        "suavizacao_incc_precos": df_suavizado[
            [
                "empreendimento",
                "cluster_area",
                "competencia",
                "preco_m2_observado",
                "mediana_movel_365d",
                "preco_curva_cluster_incc",
                "desvio_relativo_365d",
                "regra_suavizacao",
                "preco_m2_suavizado",
            ]
        ].to_dict(orient="records"),
        "geoespacial_demo": {
            "haversine_distancia_km": round(float(dist_km), 4),
            "area_terreno_shoelace_m2": round(area_m2, 2),
            "coordenadas_dispersas_polar": df_disperso.to_dict(orient="records"),
        },
    }

    examples_dir = Path(__file__).resolve().parent / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    out_path = examples_dir / "sample_output.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Demo executada com sucesso. Saída gravada em: {out_path}")


if __name__ == "__main__":
    main()
