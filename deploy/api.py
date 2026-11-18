"""Paso 4: API REST mínima (FastAPI). Modelo en memoria, sin base de datos.

    export CENTINEL_MODEL=fusion           # o optical
    export CENTINEL_GEE_PROJECT=tu_proyecto
    cp 04_api.py api.py && uvicorn api:app --port 8000

    GET /            (página web con mapa)
    GET /health
    GET /predict?lat=1.2&lon=-75.3&year=2023     (año evaluado: 2022 o 2023; se compara contra el año previo)
"""
import os
from pathlib import Path

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import config as C
import gee_utils
from models import build_model

KIND = os.getenv("CENTINEL_MODEL", "fusion")
VALID_YEARS = sorted({y1 for _, y1 in C.PAIRS})
app = FastAPI(title="Centinel MVP – Alert API", version="0.2")
STATE = {}


@app.on_event("startup")
def load():
    ckpt = torch.load(Path(C.MODELS_DIR) / f"{KIND}.pt", map_location="cpu", weights_only=False)
    model = build_model(len(ckpt["channels"]), False)
    model.load_state_dict(ckpt["state"]); model.eval()
    STATE.update(model=model, ckpt=ckpt)
    gee_utils.init(os.getenv("CENTINEL_GEE_PROJECT"))


STATIC = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def home():
    """Página web: mapa para elegir un punto y consultar /predict."""
    return FileResponse(STATIC / "index.html")


@app.get("/info")
def info():
    return {"service": "Centinel MVP – Alert API", "docs": "/docs", "health": "/health",
            "example": "/predict?lat=1.2&lon=-75.3&year=2023"}


@app.get("/health")
def health():
    return {"status": "ok", "model": KIND, "valid_years": VALID_YEARS}


def _prepare(patch):
    miss = patch <= -9000
    if miss.any(axis=0).mean() > C.MAX_MISSING:
        raise HTTPException(422, "Demasiados píxeles sin dato en ese parche y año.")
    for k in range(patch.shape[0]):                      # misma imputación que en entrenamiento
        valid = patch[k][~miss[k]]
        patch[k][miss[k]] = valid.mean() if valid.size else 0.0
    return patch


@app.get("/predict")
def predict(lat: float, lon: float, year: int = 2023):
    lon0, lat0, lon1, lat1 = C.AOI
    if not (lon0 <= lon <= lon1 and lat0 <= lat <= lat1):
        raise HTTPException(422, f"Fuera del área piloto {C.AOI}: el modelo no fue entrenado allí.")
    if year not in VALID_YEARS:
        raise HTTPException(422, f"Año no soportado. Use uno de {VALID_YEARS}.")
    try:
        prev, _ = gee_utils.fetch_patch(lat, lon, year - 1)
        curr, bbox = gee_utils.fetch_patch(lat, lon, year)
    except Exception as e:
        raise HTTPException(502, f"Error al obtener imagen de GEE: {e}")

    x12 = np.concatenate([_prepare(prev), _prepare(curr)])        # (12, P, P)
    ck = STATE["ckpt"]
    x = (x12[ck["channels"]][None].astype(np.float32) - ck["mean"]) / ck["std"]
    with torch.no_grad():
        p = float(torch.sigmoid(STATE["model"](torch.from_numpy(x))).item())

    return {
        "location": {"lat": lat, "lon": lon, "bbox": bbox},
        "year": year,
        "compared_against": year - 1,
        "model": KIND,
        "deforestation": {"probability": p, "threshold": ck["threshold"], "alert": bool(p >= ck["threshold"])},
    }
