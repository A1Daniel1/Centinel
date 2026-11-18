# Centinel – MVP (piloto reducido: deforestación)

Pipeline: **preprocesamiento → modelo → API**. Valida una sola hipótesis:
¿agregar radar (Sentinel-1) a las imágenes ópticas (Sentinel-2) mejora la detección de
deforestación anual, y es más robusto cuando hay nubes?

- **Config `optical`:** Sentinel-2 del año previo + año evaluado (8 canales).
- **Config `fusion`:** Sentinel-2 + Sentinel-1 de ambos años (12 canales).
- Misma arquitectura (ResNet-18), mismo split y mismas semillas; solo cambian los canales de entrada.

La hipótesis original (detección conjunta vs. independiente de tres fenómenos) queda como trabajo
futuro: no se consiguieron capas descargables de minería (EVOA) ni de coca (SIMCI).

## Estado de verificación

| Pieza | Estado |
|---|---|
| `01_export_tiles.py`, `gee_utils.py` | Ejecutados en Earth Engine sobre el área completa (24 tiles × 3 años + 24 etiquetas Hansen): las 96 tareas terminaron. |
| `02_build_dataset.py` | Ejecutado con datos reales: 11.764 parches, 2.461 positivos (20,9 %). |
| `03_train_eval.py`, `models.py` | Ejecutados con datos reales en GPU (T4): 2 configuraciones × 3 semillas. Resultados en `results/`. |
| `04_api.py` | Servidor FastAPI ejecutado en una máquina de Colab (16-nov-2026) con el checkpoint `fusion.pt` entrenado (semilla 0). Dos consultas en vivo a Earth Engine respondieron 200: un parche con 31,4 % de pérdida real dio probabilidad 0,999 (alerta: sí) y un parche sin pérdida dio 0,034 (alerta: no), con umbral 0,717. Es una prueba de funcionamiento con dos puntos, no una evaluación: el parche positivo pudo estar en el conjunto de entrenamiento, y no se midieron latencia ni rendimiento. El contenedor (Dockerfile) y el despliegue en la nube **no** se han probado. |

## Resultados del piloto (datos reales)

Detalle en `results/results.json`, `results/summary.csv` y `results/training_log.txt`.

| Prueba (media sobre 3 semillas) | Óptico | Óptico + SAR |
|---|---|---|
| AP, test limpio | 0,776 | 0,778 |
| Recall, test limpio | 0,625 | 0,636 |
| Precisión, test limpio | 0,756 | 0,770 |
| AP, con oclusión sintética | 0,639 | 0,661 |

- La fusión cumple precisión (≥ 0,70) y FPR (≤ 0,20) pero **no** recall (0,636 < 0,75): `passes: false`.
- ΔAP limpio por semilla: +0,003, −0,015, +0,017 (diferencia despreciable frente a la variación entre semillas).
- ΔAP con oclusión: +0,022 de media, positivo en las 3 semillas (ventaja pequeña).
- Cada semilla cambia la inicialización y la división geográfica; con 3 semillas no se puede afirmar significancia.
- Los checkpoints (`models/*.pt`, semilla 0) no se incluyen por tamaño; se regeneran con el paso 3.

## Datos

- **Imágenes:** compuestos anuales medianos (Sentinel-2 SR con máscara SCL; Sentinel-1 IW VV/VH), 20 m.
- **Etiquetas:** pérdida de bosque Hansen/GLAD (`UMD/hansen/global_forest_change_2023_v1_11`, banda `lossyear`),
  solo donde la cobertura arbórea del 2000 era ≥ 30 %. Se exporta desde Earth Engine junto con los tiles.
- **Parche:** 64×64 px (1,28 km). Positivo si ≥ 2 % de sus píxeles tienen pérdida en el año evaluado.
- **Pares temporales:** (2021→2022) y (2022→2023). Cada muestra concatena el año previo y el evaluado.

## Orden de ejecución (Colab, GPU)

```python
!pip install -q geopandas rasterio
!python 01_export_tiles.py --project centinel-tdse --dry-run     # revisar tiles
!python 01_export_tiles.py --project centinel-tdse               # tiles + etiquetas (o --labels-only)
# Esperar a que terminen las tareas en la pestaña Tareas de Earth Engine.
# Earth Engine crea una carpeta de Drive por tarea; copiarlas todas a data/tiles:
import glob, shutil, os
os.makedirs('data/tiles', exist_ok=True)
for pat in ('tile_*.tif', 'label_*.tif'):
    for f in glob.glob(f'/content/drive/MyDrive/**/{pat}', recursive=True):
        shutil.copy(f, 'data/tiles/')
!python 02_build_dataset.py        # imprime parches y proporción de positivos
!python 03_train_eval.py --epochs 15 --seeds 3
```

Salidas: `results/summary.csv`, `results/results.json` (con el veredicto) y `models/{optical,fusion}.pt`.

API (después de entrenar):

```bash
export CENTINEL_MODEL=fusion CENTINEL_GEE_PROJECT=centinel-tdse
cp 04_api.py api.py && uvicorn api:app --port 8000
curl "http://localhost:8000/predict?lat=1.2&lon=-75.3&year=2023"
```

## Decisiones de diseño (para la sección Prototype)

- **Entrada bitemporal:** el modelo ve el año previo y el evaluado, para detectar cambio y no solo apariencia.
- **Prueba de oclusión:** en test se cubre con una “nube” rectangular sintética una región de los canales
  ópticos (la misma para ambas configuraciones). Mide la robustez que aporta el radar.
- **Split:** 70/15/15 agrupado por tile (o por bloques de 512 px si hay menos de 10 tiles) para evitar fuga espacial.
- **Selección:** época por AP en validación; umbral que maximiza F1 en validación; métricas finales solo en test.
- **Desbalance:** `pos_weight` en la BCE y submuestreo de parches negativos (`NEG_KEEP`).
- **Rigor:** 3 semillas; se reporta media ± desviación y la diferencia pareada fusion − optical.
- **Veredicto automático** (`results.json`): `meets_thresholds` (recall ≥ 0,75, precisión ≥ 0,70, FPR ≤ 0,20 en fusion),
  `fusion_beats_optical` (ΔAP > 0 en la media y en al menos 2 de 3 semillas) y `fusion_more_robust_to_occlusion`.

## Limitaciones a declarar en el documento

- Las etiquetas Hansen/GLAD son globales y miden pérdida de cobertura arbórea, no deforestación oficial
  del IDEAM ni su causa. El piloto detecta pérdida de bosque, **no** la ilegalidad de la actividad.
- Etiquetas anuales contra compuestos anuales: no se detecta cambio intra-anual.
- La “nube” de la prueba de oclusión es sintética (un rectángulo), no nubosidad real.
- La API consulta GEE en cada petición (latencia de segundos); es una demostración del contrato, no un servicio de producción.
- Con pocos tiles, el número de positivos puede ser bajo y las métricas inestables; el script lo avisa.
- `NEG_KEEP=0.5` descarta la mitad de los parches negativos antes del split: la prevalencia en test (≈ 20,9 %) es mayor que la natural (≈ 12 %). Recall y FPR no cambian, pero la precisión reportada queda inflada (≈ 0,73 estimada a prevalencia natural, frente a 0,77 medida).
