"""SOLO PARA PROBAR QUE EL CÓDIGO CORRE. Genera datos sintéticos, NO reales.
Los resultados obtenidos con esto no deben reportarse en el documento.

Uso:
    python make_synthetic.py data/synthetic            # dataset ya armado (X,Y,meta)
    python make_synthetic.py data/synthetic_tiles --tiles   # tiles + etiqueta sintéticos para probar 02_build_dataset
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic")
out.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(0)

if "--tiles" in sys.argv:
    import rasterio
    from rasterio.transform import from_origin
    H = W = 256
    tr = from_origin(-75.0, 1.0, 0.0002, 0.0002)
    prof = dict(driver="GTiff", height=H, width=W, dtype="float32", crs="EPSG:4326", transform=tr)
    lab = np.zeros((H, W), "float32")
    lab[0:64, 64:128] = 22          # parche (fila0,col1): pérdida en 2022 -> positivo para (2021->2022)
    lab[64:128, 0:64] = 23          # parche (fila1,col0): pérdida en 2023 -> positivo para (2022->2023)
    lab[128, 128:192] = 22          # solo 64 px (1,6% del parche) -> NO positivo (bajo MIN_OVERLAP)
    lab[192:256, 192:256] = 10      # pérdida en 2010 -> negativo
    for y in (2021, 2022, 2023):
        a = rng.random((6, H, W)).astype("float32")
        if y == 2022:
            a[:, 200:210, 10:20] = -9999.0     # pocos píxeles sin dato (se imputan)
        if y == 2023:
            a[:, 0:100, 100:256] = -9999.0     # muchos sin dato (parches descartados)
        with rasterio.open(out / f"tile_000_000_{y}.tif", "w", count=6, **prof) as d:
            d.write(a)
    with rasterio.open(out / "label_000_000.tif", "w", count=1, **prof) as d:
        d.write(lab, 1)
    print("tiles sintéticos en", out)
else:
    N, P = 600, 64
    tiles = [f"{i:03d}_000" for i in range(24)]
    y = (rng.random(N) < 0.25).astype(np.int8)
    X = rng.normal(0, 1, (N, 12, P, P)).astype(np.float32)
    cloudy = (rng.random(N) < 0.4) & (y == 1)              # positivos donde solo el radar ve el cambio
    for i in np.where(y == 1)[0]:
        if not cloudy[i]:
            X[i, 6:10] -= 0.8                              # el año evaluado cambia en el óptico
        X[i, 10:12] -= 0.6                                 # y en el radar
    X[:, 4:6] -= 12.0; X[:, 10:12] -= 12.0                 # escala tipo dB en SAR
    np.save(out / "X.npy", X.astype(np.float16)); np.save(out / "Y.npy", y[:, None])
    pd.DataFrame(dict(tile=rng.choice(tiles, N), year=2022, row=0, col=0, lon=-75.0, lat=1.0)
                 ).to_csv(out / "meta.csv", index=False)
    print("sintético en", out, X.shape)
