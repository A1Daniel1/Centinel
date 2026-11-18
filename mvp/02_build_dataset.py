"""Paso 2: arma el dataset bitemporal de parches.

Entrada : data/tiles/tile_{ix}_{iy}_{año}.tif (6 bandas) + data/tiles/label_{ix}_{iy}.tif (lossyear)
Salida  : data/dataset/X.npy (N,12,P,P float16) = [año previo (6) | año evaluado (6)]
          data/dataset/Y.npy (N,1 int8)         = 1 si hubo pérdida de bosque en el año evaluado
          data/dataset/meta.csv

Un parche es positivo si >= C.MIN_OVERLAP de sus píxeles tienen lossyear == (año evaluado - 2000).
"""
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

import config as C

TILE_RE = re.compile(r"tile_(\d+)_(\d+)_(\d{4})\.tif$")


def impute(patch):
    """Rellena píxeles sin dato con la media del canal. Devuelve (parche, fracción sin dato)."""
    miss = patch <= -9000
    frac = float(miss.any(axis=0).mean())
    if frac > 0:
        for k in range(patch.shape[0]):
            valid = patch[k][~miss[k]]
            patch[k][miss[k]] = valid.mean() if valid.size else 0.0
    return patch, frac


def main():
    rng = np.random.default_rng(0)
    tdir = Path(C.TILES_DIR)
    tiles = defaultdict(dict)
    for tif in sorted(tdir.glob("tile_*.tif")):
        m = TILE_RE.search(tif.name)
        if m:
            tiles[(int(m[1]), int(m[2]))][int(m[3])] = tif
    if not tiles:
        raise FileNotFoundError(f"No hay tile_*.tif en {tdir}. ¿Copiaron los archivos de Drive?")

    X, Y, meta = [], [], []
    P = C.PATCH
    for (ix, iy), years in sorted(tiles.items()):
        lab_path = tdir / f"label_{ix:03d}_{iy:03d}.tif"
        if not lab_path.exists():
            print(f"[aviso] falta {lab_path.name}; se omite el tile {ix:03d}_{iy:03d}")
            continue
        with rasterio.open(lab_path) as ls:
            lab = ls.read(1)
        for y0, y1 in C.PAIRS:
            if y0 not in years or y1 not in years:
                continue
            with rasterio.open(years[y0]) as s0, rasterio.open(years[y1]) as s1:
                a0, a1 = s0.read().astype(np.float32), s1.read().astype(np.float32)
                transform = s1.transform
            H = min(a0.shape[1], a1.shape[1], lab.shape[0])
            W = min(a0.shape[2], a1.shape[2], lab.shape[1])
            for r in range(0, H - P + 1, P):
                for c in range(0, W - P + 1, P):
                    p0, f0 = impute(a0[:, r:r + P, c:c + P].copy())
                    p1, f1 = impute(a1[:, r:r + P, c:c + P].copy())
                    if max(f0, f1) > C.MAX_MISSING:
                        continue
                    frac = float((lab[r:r + P, c:c + P] == (y1 - 2000)).mean())
                    y = int(frac >= C.MIN_OVERLAP)
                    if y == 0 and rng.random() > C.NEG_KEEP:
                        continue
                    lon, lat = transform * (c + P / 2, r + P / 2)
                    X.append(np.concatenate([p0, p1]).astype(np.float16))
                    Y.append([y])
                    meta.append(dict(tile=f"{ix:03d}_{iy:03d}", year=y1, row=r, col=c,
                                     lon=lon, lat=lat, loss_frac=frac))
        print(f"tile {ix:03d}_{iy:03d}: acumulado {len(X)} parches")

    if not X:
        raise RuntimeError("No se generó ningún parche. Revisen que existan tiles y etiquetas.")
    X, Y = np.stack(X), np.array(Y, dtype=np.int8)
    out = Path(C.DATASET_DIR)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "X.npy", X)
    np.save(out / "Y.npy", Y)
    pd.DataFrame(meta).to_csv(out / "meta.csv", index=False)
    print(f"\nDataset: {X.shape} | positivos {int(Y.sum())} ({Y.mean():.1%}) | negativos {int((Y == 0).sum())}")
    if Y.sum() < 50:
        print("[aviso] muy pocos positivos: las métricas serán inestables. Amplíen el área de estudio.")


if __name__ == "__main__":
    main()
