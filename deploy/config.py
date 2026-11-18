"""Configuración central del MVP de Centinel (piloto reducido: deforestación).

Hipótesis: ¿agregar radar (Sentinel-1) a las imágenes ópticas (Sentinel-2) mejora
la detección de deforestación anual, sobre todo cuando hay nubes?
  Config "optical": solo Sentinel-2      (año previo + año evaluado)
  Config "fusion" : Sentinel-2 + Sentinel-1 (año previo + año evaluado)

EDITAR AQUÍ: área de estudio.
"""
from pathlib import Path

# --- Área de estudio (lon_min, lat_min, lon_max, lat_max) en EPSG:4326 ---
AOI = (-75.5, 0.8, -74.0, 1.8)
TILE_DEG = 0.25          # tamaño de cada tile de exportación (grados)
YEARS = [2021, 2022, 2023]
PAIRS = [(2021, 2022), (2022, 2023)]   # (año previo, año evaluado); la etiqueta es pérdida en el 2.º año
SCALE_M = 20             # resolución en metros
PATCH = 64               # lado del parche en píxeles (64 px * 20 m = 1,28 km)

# Canales de cada compuesto anual (en el .tif exportado)
CHANNELS = ["B2", "B3", "B4", "B8", "VV", "VH"]

# Canales del dataset = [año previo (6) | año evaluado (6)] = 12
OPTICAL_IDX = [0, 1, 2, 3, 6, 7, 8, 9]
ALL_IDX = list(range(12))
CONFIGS = {"optical": OPTICAL_IDX, "fusion": ALL_IDX}

# --- Etiquetas: pérdida de bosque Hansen/GLAD (dentro de Earth Engine) ---
# 'lossyear' = 1..23 (año - 2000); se exporta junto con los tiles. Solo se cuenta
# pérdida donde la cobertura arbórea del 2000 era >= TREECOVER_MIN %.
HANSEN_ASSET = "UMD/hansen/global_forest_change_2023_v1_11"
TREECOVER_MIN = 30

MIN_OVERLAP = 0.02       # fracción del parche con pérdida para marcarlo positivo
MAX_MISSING = 0.20       # descartar parches con >20% de píxeles sin dato
NEG_KEEP = 0.5           # fracción de parches negativos que se conserva
MISSING = -9999.0        # valor centinela de píxeles enmascarados

DATA_DIR = Path("data")
TILES_DIR = DATA_DIR / "tiles"       # aquí van los tile_*.tif y label_*.tif de Drive
DATASET_DIR = DATA_DIR / "dataset"
MODELS_DIR = Path("models")
RESULTS_DIR = Path("results")
