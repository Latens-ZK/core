# ── Stage: runtime ────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# System deps (none strictly required for our pure-Python stack, but good to have)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cached when code changes)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source + scripts
COPY backend/src ./src
COPY backend/scripts ./scripts

# Data directory for SQLite (mounted as a volume in docker-compose)
RUN mkdir -p /app/data

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////app/data/latens.db

EXPOSE 8000

# Entrypoint: seed demo data on first run, then start the API server
COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
