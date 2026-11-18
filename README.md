# Centinel

Arquitectura en la nube para la detección temprana de actividades ilegales sobre el territorio colombiano
(deforestación, minería ilegal de oro y cultivos de coca) a partir de imágenes satelitales, y un piloto que la pone a prueba.

Proyecto del curso TDSE. Equipo: Juan Pablo Vélez Muñoz, Luiza Mariana Gonzalez Veloza y Daniel Alexander Ahumada León.

## De qué trata

La propuesta es un solo modelo que detecte varios fenómenos a la vez, con alertas que un operador puede ajustar y una API
para entregarlas. La hipótesis central es que un modelo conjunto (multietiqueta) genera menos falsas alarmas que tres
detectores independientes.

No se consiguieron a tiempo las capas oficiales de referencia (IDEAM, UNODC/SIMCI, EVOA), así que el piloto se ajustó a
datos abiertos y a una pregunta más pequeña:

> ¿Agregar radar (Sentinel-1) a las imágenes ópticas (Sentinel-2) mejora la detección anual de pérdida de bosque en
> Caquetá y Putumayo, sobre todo cuando hay nubes?

**Resultado:** no hubo una ganancia significativa. La hipótesis original sigue siendo viable y el siguiente paso es
probarla solo con imágenes ópticas.

| Métrica (promedio de 3 semillas, prueba) | Solo óptico | Óptico + radar |
|---|---|---|
| Precisión | 0,756 | 0,770 |
| Recall | 0,625 | 0,636 |
| Tasa de falsas alarmas | 0,030 | 0,031 |
| AP (precisión media), imágenes limpias | 0,776 | 0,778 |
| AP con nubes simuladas | 0,639 | 0,661 |

El criterio de recall (al menos 0,75) no se cumplió. Las cifras completas están en `centinel_mvp/results/`.

## Estructura del repositorio

```
.
├── README.md
├── main.tex            # artículo
├── centinel_mvp/       # pipeline del piloto
├── artifacts/          # modelo entrenado y archivos del dataset
└── deploy/             # API y página web desplegadas en Google Cloud Run
```

### `centinel_mvp/` — el piloto

Código para repetir el experimento de principio a fin:

- `01_export_tiles.py`: exporta desde Google Earth Engine las imágenes (Sentinel-2 y Sentinel-1) y las etiquetas de pérdida de bosque.
- `02_build_dataset.py`: arma los parches de 64 × 64 píxeles (1,28 km de lado) y escribe `meta.csv` y `Y.npy`.
- `03_train_eval.py`: entrena y evalúa las dos configuraciones (óptico y fusión) con tres semillas.
- `04_api.py`: API local de prueba (FastAPI).
- `config.py`, `models.py`, `gee_utils.py`: configuración, modelo y acceso a Earth Engine.
- `results/`: resultados reales del piloto (`results.json`, `summary.csv`, `training_log.txt`).
- `README.md`: instrucciones de uso y tabla de qué se verificó y qué no.

### `artifacts/` — modelo y datos

- `fusion.pt` (y `optical.pt`, si se incluye): modelos entrenados. El de fusión es el que usa la API.
- `meta.csv` y `Y.npy`: de dónde sale cada uno de los 11.764 parches y su etiqueta.
- `README.md`: qué es cada archivo y cómo cargarlo.

No incluye los GeoTIFF ni las imágenes del dataset: son de varios gigabytes y se regeneran con `centinel_mvp/`.

### `deploy/` — el despliegue

API (FastAPI) y página web con mapa, empaquetadas en un contenedor para Google Cloud Run:

- `api.py`: `/` (página web), `/predict`, `/health`, `/info` y `/docs`.
- `static/index.html`: página para elegir un punto en el mapa y consultar la alerta.
- `Dockerfile` y `requirements.txt`: construcción del contenedor.
- `DEPLOY.md`: paso a paso para reproducir el despliegue (cuenta de servicio, secreto, comando de Cloud Run, pruebas y cómo deshacerlo).

Antes de desplegar hay que copiar el modelo: `cp artifacts/fusion.pt deploy/models/fusion.pt`.

### `main.tex` — el artículo

Artículo en LaTeX: problema y brecha, arquitectura propuesta, diseño y resultados del piloto, costos, riesgos, gobernanza
y trabajo futuro.

## Cómo reproducir

1. Exportar las imágenes y etiquetas con `centinel_mvp/01_export_tiles.py` (requiere una cuenta de Earth Engine).
2. Construir el dataset con `02_build_dataset.py`.
3. Entrenar y evaluar con `03_train_eval.py`.
4. Desplegar la API siguiendo `deploy/DEPLOY.md`.

Los modelos y las tablas del dataset ya están en `artifacts/` para no repetir los pasos 1 a 3.

## Límites

- Las etiquetas son pérdida de bosque según el mapa de Hansen/GLAD, no deforestación verificada en campo ni ilegalidad.
  Una alerta no es una prueba: requiere verificación humana.
- Solo se probó deforestación; la minería y la coca no se evaluaron.
- Al armar el dataset se conservó la mitad de los parches negativos, así que la precisión reportada queda algo inflada.
- Tres semillas son pocas para una conclusión estadística firme.
- El endpoint de la demostración es público y sin autenticación. La autenticación, el límite de tasa y el monitoreo son
  diseño propuesto, no implementado. No se midieron latencia, carga ni escalado.
- Solo responde dentro del área piloto (longitud −75,5 a −74,0; latitud 0,8 a 1,8) y para los años 2022 y 2023.

## Datos y atribución

Sentinel-1 y Sentinel-2 (Copernicus, Agencia Espacial Europea), mapa de pérdida de bosque de Hansen et al. (2013) y
Google Earth Engine. Verifique las condiciones de uso de cada fuente antes de reutilizar los datos.

## Despliegue

API y página web en Google Cloud Run (demostración; el servicio se elimina al terminar la evaluación):

- Aplicación: https://centinel-api-201209038013.us-central1.run.app
- Documentación interactiva: https://centinel-api-201209038013.us-central1.run.app/docs
- Estado del servicio: https://centinel-api-201209038013.us-central1.run.app/health

Ejemplo: `/predict?lat=1.2253&lon=-74.3909&year=2022` devuelve probabilidad 0,9993 y alerta. Cada consulta tarda del orden
de decenas de segundos, porque descarga imágenes de Earth Engine en el momento.
