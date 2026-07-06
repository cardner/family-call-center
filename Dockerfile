# syntax=docker/dockerfile:1

# Stage 1: vendor Basecoat CSS/JS/Jinja assets with Node.
FROM node:20-slim AS assets
WORKDIR /build
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY scripts/vendor-basecoat.sh ./scripts/vendor-basecoat.sh
# The vendor script writes into app/static and app/templates; create the tree.
RUN mkdir -p app/static app/templates && bash scripts/vendor-basecoat.sh

# Stage 2: Python runtime.
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    DATA_DIR=/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bring in the vendored Basecoat assets from the Node stage.
COPY --from=assets /build/app/static/vendor/basecoat ./app/static/vendor/basecoat
COPY --from=assets /build/app/templates/components ./app/templates/components

RUN mkdir -p /data

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["gunicorn", "-b", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "run:app"]
