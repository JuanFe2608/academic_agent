# ---- builder stage --------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Instala uv para gestion de dependencias rapida
RUN pip install --no-cache-dir uv

# Copia manifiestos de dependencias primero para aprovechar cache de capas
COPY pyproject.toml uv.lock ./

# Instala dependencias en un venv aislado (sin dev)
RUN uv sync --frozen --no-dev --no-install-project

# ---- runtime stage --------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Dependencias de sistema minimas para psycopg (PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copia el venv desde el builder
COPY --from=builder /app/.venv /app/.venv

# Copia codigo fuente y recursos
COPY src/ ./src/
COPY knowledge_base/ ./knowledge_base/
COPY assets/ ./assets/
COPY main.py ./

# Activa el venv del proyecto
ENV PATH="/app/.venv/bin:$PATH"
# Hace importable todos los paquetes de src/ sin instalacion adicional
ENV PYTHONPATH="/app/src"

# Puerto de escucha (configurable via variable de entorno en Azure)
EXPOSE 8000

# Healthcheck para Azure Container Apps / App Service
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Ejecuta uvicorn en modo produccion
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
