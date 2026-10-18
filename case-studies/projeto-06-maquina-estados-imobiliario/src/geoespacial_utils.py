"""
Utilitários Geoespaciais de Alta Precisão para Inteligência de Mercado Imobiliário.

Implementa três algoritmos matemáticos fundamentais utilizados nos pipelines
`Pesquisas V5` e `kmztocsv.py`:
1. Distância Esférica de Haversine ($R = 6371.0\\text{ km}$) vetorizada / escalar;
2. Dispersão Polar Trigonométrica em Anéis Concêntricos (`ajustar_coordenadas_duplicadas_fast`
   com $\\cos\\theta, \\sin\\theta$) para separar empreendimentos ou leads que compartilham
   exatamente o mesmo CEP/coordenada sem deslocá-los para fora da quadra/bairro;
3. Cálculo de Área Plana em $\\text{m}^2$ de polígonos geográficos (KMZ/KML) via
   projeção métrica local e Fórmula de Gauss / *Shoelace*.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np
import pandas as pd

EARTH_RADIUS_KM: float = 6371.0
METERS_PER_DEGREE_LAT: float = 111_320.0


def haversine_km(
    lat1: float | np.ndarray,
    lon1: float | np.ndarray,
    lat2: float | np.ndarray,
    lon2: float | np.ndarray,
) -> float | np.ndarray:
    """
    Calcula a distância ortodrômica (grande círculo) na superfície terrestre
    usando a Fórmula de Haversine com raio médio $R = 6371.0\\text{ km}$:

    $$a = \\sin^2\\left(\\frac{\\Delta\\phi}{2}\\right) + \\cos(\\phi_1)\\cos(\\phi_2)\\sin^2\\left(\\frac{\\Delta\\lambda}{2}\\right)$$
    $$d = 2 R \\arctan2\\left(\\sqrt{a}, \\sqrt{1 - a}\\right)$$
    """
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(np.asarray(lat2) - np.asarray(lat1))
    dlambda = np.radians(np.asarray(lon2) - np.asarray(lon1))

    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * (np.sin(dlambda / 2.0) ** 2)
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    dist = EARTH_RADIUS_KM * c

    if np.ndim(dist) == 0:
        return float(dist)
    return dist


def ajustar_coordenadas_duplicadas_fast(
    df: pd.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    raio_base_metros: float = 12.0,
    pontos_por_anel: int = 8,
) -> pd.DataFrame:
    """
    Aplica dispersão polar vetorizada em anéis concêntricos sobre pontos com coordenadas
    idênticas (ex.: múltiplos imóveis geocodificados pelo centroide do mesmo CEP).

    - O primeiro ponto do grupo ($k = 0$) permanece exatamente na coordenada original.
    - Os pontos subsequentes ($k \\ge 1$) são distribuídos em anéis concêntricos de raio
      $r_k = r_{\\text{base}} \\cdot \\lceil k / M \\rceil$ metros e ângulo $\\theta_k = \\frac{2\\pi (k - 1 \\bmod M)}{M}$:
      $$\\Delta\\text{lat} = \\frac{r_k \\sin\\theta_k}{111320}, \\quad \\Delta\\text{lon} = \\frac{r_k \\cos\\theta_k}{111320 \\cos(\\text{lat}_0)}$$
    """
    out = df.copy()
    out["ordem_no_ponto"] = out.groupby([lat_col, lon_col]).cumcount()

    mask_dup = out["ordem_no_ponto"] > 0
    if not mask_dup.any():
        out["lat_ajustada"] = out[lat_col].astype(float)
        out["lon_ajustada"] = out[lon_col].astype(float)
        return out

    k = out.loc[mask_dup, "ordem_no_ponto"].to_numpy(dtype=np.float64)
    lat0 = out.loc[mask_dup, lat_col].to_numpy(dtype=np.float64)
    lon0 = out.loc[mask_dup, lon_col].to_numpy(dtype=np.float64)

    anel_idx = np.ceil(k / float(pontos_por_anel))
    raio_m = raio_base_metros * anel_idx
    theta = (2.0 * np.pi * ((k - 1.0) % float(pontos_por_anel))) / float(pontos_por_anel)

    dlat = (raio_m * np.sin(theta)) / METERS_PER_DEGREE_LAT
    cos_lat = np.clip(np.cos(np.radians(lat0)), 1e-6, 1.0)
    dlon = (raio_m * np.cos(theta)) / (METERS_PER_DEGREE_LAT * cos_lat)

    out["lat_ajustada"] = out[lat_col].astype(float)
    out["lon_ajustada"] = out[lon_col].astype(float)
    out.loc[mask_dup, "lat_ajustada"] = lat0 + dlat
    out.loc[mask_dup, "lon_ajustada"] = lon0 + dlon
    return out


def calcular_area_poligono_shoelace_m2(
    coordenadas_lat_lon: Sequence[Tuple[float, float]]
) -> float:
    """
    Calcula a área plana em metros quadrados ($\\text{m}^2$) de um polígono fechado ou aberto
    definido por pares `(latitude, longitude)` (ex.: terrenos extraídos de arquivos `.kmz`/`.kml`)
    utilizando projeção tangente local e a **Fórmula de Gauss / Shoelace**:

    $$A = \\frac{1}{2} \\left| \\sum_{i=0}^{n-1} (x_i y_{i+1} - x_{i+1} y_i) \\right|$$
    """
    if len(coordenadas_lat_lon) < 3:
        return 0.0

    pts = np.asarray(coordenadas_lat_lon, dtype=np.float64)
    lats = pts[:, 0]
    lons = pts[:, 1]

    lat_ref = float(np.mean(lats))
    lon_ref = float(np.mean(lons))
    cos_ref = math.cos(math.radians(lat_ref))

    # Projeção local em metros em relação ao centroide do polígono
    x_m = (lons - lon_ref) * METERS_PER_DEGREE_LAT * cos_ref
    y_m = (lats - lat_ref) * METERS_PER_DEGREE_LAT

    # Fórmula de Gauss / Shoelace vetorizada via np.roll
    area = 0.5 * np.abs(np.dot(x_m, np.roll(y_m, -1)) - np.dot(y_m, np.roll(x_m, -1)))
    return float(area)
