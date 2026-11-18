# artifacts/ — modelo entrenado y archivos de datos del piloto

Resultados del piloto de Centinel que no son código: el modelo entrenado y las tablas que describen el dataset.
Todo se puede regenerar con los scripts de `mvp/`; se guarda aquí para poder desplegar la API y verificar los
resultados sin repetir el entrenamiento.

## Archivos

| Archivo | Qué es |
|---|---|
| `fusion.pt` | Modelo con óptico + radar (Sentinel-2 + Sentinel-1). Es el que usa la API desplegada |
| `optical.pt` | Modelo solo óptico (Sentinel-2), para repetir la comparación *(incluir solo si está disponible)* |
| `meta.csv` | Una fila por parche (11.764 en total): de dónde sale cada uno |
| `Y.npy` | Etiqueta de cada parche, en el mismo orden que `meta.csv` |

### `fusion.pt` y `optical.pt`

- Arquitectura: ResNet-18 adaptada a un parche de 64 × 64 píxeles (1,28 km de lado, a 20 m por píxel) y comparando dos años.
- Entradas: `fusion` usa 12 canales (año previo y año evaluado, con B2, B3, B4, B8, VV y VH cada uno); `optical` usa 8 (sin VV ni VH).
- Cada archivo es un *checkpoint* de PyTorch con un diccionario: `state` (pesos), `channels` (índices de los canales usados),
  `mean` y `std` (normalización) y `threshold` (umbral de alerta, elegido por el mejor F1 en validación).
- El `fusion.pt` incluido es el de la semilla 0, con umbral 0,7167.

### `meta.csv`

Columnas: `tile`, `year`, `row`, `col`, `lon`, `lat`, `loss_frac`.

- `tile`: zona de 0,25° de la que sale el parche.
- `year`: año evaluado (2022 o 2023); se compara contra el año anterior.
- `row`, `col`: posición del parche dentro de la zona.
- `lon`, `lat`: centro del parche.
- `loss_frac`: fracción de píxeles del parche con pérdida de bosque según Hansen/GLAD ese año.

### `Y.npy`

Arreglo de forma `(11764, 1)`. Vale 1 si el parche es positivo (al menos 2 % de sus píxeles con pérdida de bosque
según Hansen/GLAD) y 0 si no. Hay 2.461 positivos. Para usarlo como vector: `y = np.load("Y.npy").ravel()`.

## Uso rápido

```python
import numpy as np, pandas as pd, torch

m = pd.read_csv("artifacts/meta.csv")
y = np.load("artifacts/Y.npy").ravel()
print(len(m), int(y.sum()))              # 11764 2461

ck = torch.load("artifacts/fusion.pt", map_location="cpu", weights_only=False)
print(ck["threshold"], len(ck["channels"]))   # 0.7167... 12
```

Para desplegar la API hay que copiar el modelo a la carpeta del despliegue (el contenedor solo ve `deploy/`):

```bash
cp artifacts/fusion.pt deploy/models/fusion.pt
```

Esa copia no se versiona (`deploy/.gitignore` bloquea `models/*.pt`), para no duplicar el archivo en el repositorio.

## Qué NO está aquí

- Los GeoTIFF exportados de Earth Engine y el arreglo de imágenes del dataset: pesan gigabytes y se regeneran con
  `mvp/01_export_tiles.py` y `mvp/02_build_dataset.py` a partir de datos abiertos.
- Cualquier llave o credencial de Google Cloud. Nunca deben subirse al repositorio.

## Cómo se generaron

1. `mvp/01_export_tiles.py` exporta desde Earth Engine las imágenes (Sentinel-2 y Sentinel-1) y las etiquetas.
2. `mvp/02_build_dataset.py` arma los parches y escribe `meta.csv` y `Y.npy`.
3. `mvp/03_train_eval.py` entrena los modelos (óptico y fusión, tres semillas) y escribe los checkpoints.

## Límites

- Las etiquetas son pérdida de bosque según el mapa de Hansen/GLAD, no deforestación verificada en campo ni ilegalidad.
- Al armar el dataset se conservó la mitad de los parches negativos (`NEG_KEEP = 0.5`), así que la proporción de
  positivos (21 %) es mayor que la natural (cerca de 12 %) y la precisión reportada queda algo inflada.
- Los modelos solo son válidos dentro del área piloto (longitud −75,5 a −74,0; latitud 0,8 a 1,8) y para los años 2022 y 2023.
- Un checkpoint de PyTorch cargado con `weights_only=False` puede ejecutar código: cárguelo solo si proviene de una fuente
  de confianza, como este repositorio.

## Datos y atribución

Sentinel-1 y Sentinel-2 (Copernicus, Agencia Espacial Europea), mapa de pérdida de bosque de Hansen et al. (2013) y
Google Earth Engine. Verifique las condiciones de uso de cada fuente antes de reutilizar los datos.
