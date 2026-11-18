"""Utilidades de Google Earth Engine compartidas por preprocesamiento y API.

IMPORTANTE: la misma función de compuesto se usa para entrenar (tiles) y para
inferir (API), así el modelo ve exactamente el mismo tipo de dato en ambos casos.
"""
import numpy as np
import ee

import config as C


def init(project=None):
    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)


def s2_composite(region, year):
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 70))
    )

    def mask(img):
        scl = img.select("SCL")
        # Excluye sin dato(1), sombra(3), nube media/alta(8,9), cirrus(10), nieve(11)
        ok = (scl.neq(1).And(scl.neq(3)).And(scl.neq(8))
              .And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11)))
        return img.updateMask(ok).select(["B2", "B3", "B4", "B8"]).divide(10000)

    return col.map(mask).median()


def s1_composite(region, year):
    col = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(region)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    )
    return col.select(["VV", "VH"]).median()


def fused_composite(region, year):
    """Tensor de 6 canales (4 ópticos + 2 SAR), píxeles sin dato = MISSING."""
    img = s2_composite(region, year).addBands(s1_composite(region, year))
    return img.select(C.CHANNELS).unmask(C.MISSING).toFloat()


def loss_label(region):
    """Pérdida de bosque Hansen/GLAD: 0 = sin pérdida, 1..23 = año-2000 de la pérdida."""
    h = ee.Image(C.HANSEN_ASSET)
    loss = h.select("lossyear").updateMask(h.select("treecover2000").gte(C.TREECOVER_MIN))
    return loss.unmask(0).rename("lossyear").toFloat()


def fetch_patch(lat, lon, year, patch=None):
    """Descarga un parche (6, patch, patch) centrado en (lat, lon). Usado por la API."""
    patch = patch or C.PATCH
    half_deg = patch * C.SCALE_M / 111320.0 / 2.0
    region = ee.Geometry.Rectangle(
        [lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg]
    )
    proj = ee.Projection("EPSG:4326").atScale(C.SCALE_M)
    img = fused_composite(region, year).reproject(proj)
    props = img.sampleRectangle(region=region, defaultValue=C.MISSING).getInfo()["properties"]

    bands = [np.array(props[b], dtype=np.float32) for b in C.CHANNELS]
    arr = np.stack(bands)                      # (6, h, w) con h,w ≈ patch ± 1
    out = np.full((len(C.CHANNELS), patch, patch), C.MISSING, dtype=np.float32)
    h, w = min(arr.shape[1], patch), min(arr.shape[2], patch)
    out[:, :h, :w] = arr[:, :h, :w]
    return out, [lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg]
