# Centinel MVP – Alert API

API REST (FastAPI) del piloto de detección de pérdida de bosque en Caquetá y Putumayo, con una
página web (`/`) para elegir un punto en un mapa y consultar la alerta.

- `GET /` página con mapa.
- `GET /predict?lat=1.2&lon=-75.3&year=2023` devuelve la probabilidad de pérdida de bosque y una alerta.
- `GET /health` estado del servicio. `GET /docs` documentación interactiva.

Detecta pérdida de cobertura arbórea (Hansen/GLAD), no la ilegalidad de la actividad. Solo responde
dentro del área piloto (lon -75.5..-74.0, lat 0.8..1.8) y para los años 2022 y 2023. Cada petición
consulta Google Earth Engine en vivo, por lo que tarda del orden de decenas de segundos.

## Despliegue en Google Cloud Run

Ponga el modelo entrenado en `models/fusion.pt` (no se incluye en el repositorio) y la llave de la cuenta
de servicio de Earth Engine en Secret Manager (`ee-sa-json`). Desde esta carpeta:

```bash
gcloud run deploy centinel-api --source . --region us-central1 \
  --allow-unauthenticated --port 7860 --memory 2Gi --cpu 1 --timeout 300 \
  --concurrency 4 --max-instances 2 \
  --service-account centinel-api@centinel-tdse.iam.gserviceaccount.com \
  --set-secrets EE_SERVICE_ACCOUNT_JSON=ee-sa-json:latest \
  --set-env-vars CENTINEL_GEE_PROJECT=centinel-tdse,CENTINEL_MODEL=fusion
```

El endpoint de la demostración es público y sin autenticación.
