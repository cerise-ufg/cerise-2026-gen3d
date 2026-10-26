# CERISE 2026 - servidor de geracao 3D (API FastAPI + worker de GPU), derivado da imagem do pipeline.
# Build (no Spark, em ~/cerise2026/gen3d/server):  sudo docker build -t cerise26_gen3d_server:latest .
FROM cerise26_gen3d:latest

# FastAPI/uvicorn/multipart (PyPI oficial). torch/pydantic ficam como na imagem base (PIP_CONSTRAINT da NGC).
RUN pip install --no-cache-dir "fastapi==0.115.12" "uvicorn==0.34.2" "python-multipart==0.0.20" \
      "prometheus_client>=0.20" "httpx>=0.27" pytest

ENV GEN3D_DATA_DIR=/data \
    GEN3D_PIPELINE_DIR=/opt/gen3d/pipeline \
    HF_HUB_OFFLINE=1 \
    HF_MODULES_CACHE=/tmp/hf_modules \
    PYTHONPATH=/opt/gen3d/server \
    PYTHONUNBUFFERED=1

COPY cerise_gen3d_server /opt/gen3d/server/cerise_gen3d_server
COPY baseline_2025 /opt/gen3d/server/baseline_2025
COPY loadtest /opt/gen3d/server/loadtest
COPY tests /opt/gen3d/server/tests
WORKDIR /opt/gen3d/server
EXPOSE 8095
CMD ["uvicorn", "cerise_gen3d_server.api:app", "--host", "0.0.0.0", "--port", "8095"]
