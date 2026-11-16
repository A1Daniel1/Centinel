"""Paso 1: lanza en GEE la exportación a Google Drive de
  - compuestos anuales Sentinel-2 + Sentinel-1  -> tile_{ix}_{iy}_{año}.tif   (6 bandas)
  - etiqueta de pérdida de bosque Hansen/GLAD   -> label_{ix}_{iy}.tif        (1 banda)

Uso:
    python 01_export_tiles.py --project TU_PROYECTO --dry-run   # solo lista
    python 01_export_tiles.py --project TU_PROYECTO             # lanza todo
    python 01_export_tiles.py --project TU_PROYECTO --labels-only   # solo etiquetas

Earth Engine crea una carpeta de Drive por tarea ('centinel_tiles', 'centinel_tiles (1)', ...).
Para juntarlas en data/tiles/ usen la celda de copia recursiva del README.
"""
import argparse
import math

import ee

import config as C
import gee_utils


def tile_grid():
    lon0, lat0, lon1, lat1 = C.AOI
    nx = math.ceil((lon1 - lon0) / C.TILE_DEG)
    ny = math.ceil((lat1 - lat0) / C.TILE_DEG)
    for ix in range(nx):
        for iy in range(ny):
            x0 = lon0 + ix * C.TILE_DEG
            y0 = lat0 + iy * C.TILE_DEG
            yield ix, iy, [x0, y0, min(x0 + C.TILE_DEG, lon1), min(y0 + C.TILE_DEG, lat1)]


def launch(image, name, region, folder):
    task = ee.batch.Export.image.toDrive(
        image=image, description=name, folder=folder, fileNamePrefix=name,
        region=region, scale=C.SCALE_M, crs="EPSG:4326", maxPixels=1e10)
    task.start()
    print("lanzada:", name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=None)
    ap.add_argument("--folder", default="centinel_tiles")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--labels-only", action="store_true")
    args = ap.parse_args()

    tiles = list(tile_grid())
    n_comp = 0 if args.labels_only else len(tiles) * len(C.YEARS)
    print(f"{len(tiles)} tiles -> {n_comp} compuestos + {len(tiles)} etiquetas = {n_comp + len(tiles)} tareas")
    if args.dry_run:
        for ix, iy, bbox in tiles:
            print(f"tile_{ix:03d}_{iy:03d}", bbox)
        return

    gee_utils.init(args.project)
    for ix, iy, bbox in tiles:
        region = ee.Geometry.Rectangle(bbox)
        if not args.labels_only:
            for year in C.YEARS:
                launch(gee_utils.fused_composite(region, year),
                       f"tile_{ix:03d}_{iy:03d}_{year}", region, args.folder)
        launch(gee_utils.loss_label(region), f"label_{ix:03d}_{iy:03d}", region, args.folder)


if __name__ == "__main__":
    main()
