# Backend Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies (needed for cairo-lang sometimes, or just essential build tools)
RUN apt-get update && apt-get install -y \
    build-essential \
    libgmp-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY backend/src ./src
COPY backend/scripts ./scripts

# Environment variables
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:///./latens.db

# Expose port
EXPOSE 8000

# Run command
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
