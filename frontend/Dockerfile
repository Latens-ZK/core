# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:18-alpine AS builder

WORKDIR /app

# Install deps (layer-cached)
COPY frontend/package*.json ./
RUN npm ci

# Copy source
COPY frontend/ .

# NEXT_PUBLIC_* vars must be baked in at build time for static export.
# Pass them as Docker build args: docker-compose passes them from .env
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api
ARG NEXT_PUBLIC_VERIFIER_ADDRESS=""
ARG NEXT_PUBLIC_REGISTRY_ADDRESS=""

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_VERIFIER_ADDRESS=$NEXT_PUBLIC_VERIFIER_ADDRESS
ENV NEXT_PUBLIC_REGISTRY_ADDRESS=$NEXT_PUBLIC_REGISTRY_ADDRESS

RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM node:18-alpine

WORKDIR /app

# 'serve' is a zero-config static file server
RUN npm install -g serve@14

# Copy the static export output from the builder
COPY --from=builder /app/out ./out

EXPOSE 3000

CMD ["serve", "-s", "out", "-l", "3000"]
