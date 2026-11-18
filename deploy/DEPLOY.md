# Despliegue de la API de Centinel en Google Cloud Run

Guía para reproducir el despliegue del piloto. La API (FastAPI) y la página web con mapa se empaquetan
en un solo contenedor (`Dockerfile`) y se ejecutan en Cloud Run. El contenedor consulta Google Earth Engine
en cada petición, con una cuenta de servicio.

## Qué hay en esta carpeta

| Archivo | Para qué sirve |
|---|---|
| `Dockerfile` | Imagen: Python 3.11, PyTorch solo CPU, FastAPI, puerto 7860 |
| `api.py` | API: `/` (página web), `/health`, `/predict`, `/info`, `/docs` |
| `static/index.html` | Página con mapa para elegir un punto y consultar `/predict` |
| `config.py`, `models.py`, `gee_utils.py` | Configuración, modelo y acceso a Earth Engine (mismos que el piloto) |
| `requirements.txt` | Dependencias (además de PyTorch, que instala el Dockerfile) |
| `models/fusion.pt` | Modelo entrenado. **No está en el repositorio** (ver más abajo) |

## Requisitos

- Proyecto de Google Cloud con facturación activa (el piloto se probó con el crédito de prueba) y registrado
  para Earth Engine (uso no comercial).
- `gcloud` instalado, o Cloud Shell.
- El archivo `models/fusion.pt` generado por `03_train_eval.py` del piloto.

## 1. Preparar el proyecto

```bash
gcloud config set project TU_PROYECTO
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

## 2. Cuenta de servicio para Earth Engine

En la consola: IAM y administración → Cuentas de servicio → crear `centinel-api` con solo estos dos roles:

- Earth Engine Resource Viewer (`roles/earthengine.viewer`)
- Service Usage Consumer (`roles/serviceusage.serviceUsageConsumer`)

Luego, en la pestaña Claves, crear una clave JSON y descargarla.

## 3. Guardar la llave como secreto (nunca en el código ni en el repositorio)

```bash
gcloud secrets create ee-sa-json --data-file=RUTA/A/LA-LLAVE.json
SA=centinel-api@TU_PROYECTO.iam.gserviceaccount.com
gcloud secrets add-iam-policy-binding ee-sa-json \
  --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
rm RUTA/A/LA-LLAVE.json     # la copia local ya no hace falta
```

## 4. Desplegar

Desde esta carpeta (con `models/fusion.pt` en su sitio):

```bash
gcloud run deploy centinel-api --source . --region us-central1 \
  --allow-unauthenticated --port 7860 --memory 2Gi --cpu 1 --timeout 300 \
  --concurrency 4 --max-instances 2 \
  --service-account $SA \
  --set-secrets EE_SERVICE_ACCOUNT_JSON=ee-sa-json:latest \
  --set-env-vars CENTINEL_GEE_PROJECT=TU_PROYECTO,CENTINEL_MODEL=fusion
```

Al final imprime la `Service URL`. La construcción tarda entre 5 y 10 minutos.

## 5. Probar

```bash
URL=https://...run.app            # la Service URL
curl -s $URL/health               # {"status":"ok","model":"fusion","valid_years":[2022,2023]}
curl -s --max-time 120 "$URL/predict?lat=1.2253&lon=-74.3909&year=2022"
```

Con el modelo del piloto, ese caso dio probabilidad 0,9993 y alerta; `lat=0.8604&lon=-75.3104&year=2023`
dio 0,0338 y sin alerta (los mismos valores que en Colab). También se puede abrir `$URL/` (mapa) y `$URL/docs`.
Cada consulta descarga imágenes de Earth Engine en el momento y tarda del orden de decenas de segundos.

## Operación

- **Volver a una versión anterior:**
  `gcloud run services update-traffic centinel-api --region us-central1 --to-revisions NOMBRE_DE_LA_REVISION=100`
- **Borrar el servicio** (recomendado al terminar la evaluación):
  `gcloud run services delete centinel-api --region us-central1`
- **Gasto:** `--max-instances 2` y `--concurrency 4` ponen un techo a la carga y al uso de la cuota de Earth Engine.
  Conviene además crear un presupuesto con alerta en Facturación.

## El modelo (`models/fusion.pt`)

Pesa unos 45 MB y está excluido por `.gitignore`. Opciones para compartirlo:

1. Adjuntarlo a un *Release* de GitHub y descargarlo antes de desplegar.
2. Versionarlo con Git LFS: `git lfs install && git lfs track "models/*.pt"`, y quitar la línea `models/*.pt` del `.gitignore`.
3. Regenerarlo con el pipeline del piloto (`03_train_eval.py`).

## Alcance y límites

- Es un despliegue de demostración: el endpoint es **público y sin autenticación**. Autenticación, límite de tasa
  y monitoreo no están implementados.
- Verificado: `/health` y `/predict` en la nube reproducen los resultados de Colab en dos consultas. No se
  midieron latencia, carga ni escalado.
- La alerta indica pérdida de bosque según el modelo (entrenado con etiquetas Hansen/GLAD), no ilegalidad.
  Solo responde dentro del área piloto (lon −75,5 a −74,0; lat 0,8 a 1,8) y para los años 2022 y 2023.
