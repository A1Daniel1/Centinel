# Centinel MVP - Alert API (sin probar en la nube; ver README)
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgdal-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY config.py gee_utils.py models.py 04_api.py ./
RUN cp 04_api.py api.py
# Los checkpoints (models/*.pt) no se incluyen en la imagen: montarlos como volumen en /app/models
ENV CENTINEL_MODEL=fusion
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
