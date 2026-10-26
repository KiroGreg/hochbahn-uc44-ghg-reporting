# UC44 — THG Reporting Prototype

Two-tier app for the Hamburger Hochbahn THG-reporting flow:

- `backend/` — FastAPI service that reuses the existing
  `PlausibilityModel` and `PredictionModel` from `Use Case/models/`.
- `frontend/` — Angular app whose API client is generated from the
  FastAPI OpenAPI spec via `openapi-generator-cli`.

## Run with Docker (recommended)

```
cd app
docker compose up --build
```

Open http://localhost:8080 — nginx serves the SPA and proxies `/api/*` to
the FastAPI container. Swagger UI at http://localhost:8080/docs.

The OPENAI key is taken from the host environment (or an `.env` next to
`docker-compose.yml`):

```
OPENAI_API_KEY=sk-...
```

The bundled `Use Case/models/.env` is also baked into the backend image,
so the sample dataset works without any host config.

## Run locally (without Docker)

Backend:

```
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
# Swagger UI: http://127.0.0.1:8000/docs
```

Frontend:

```
cd frontend
npm start          # http://127.0.0.1:4200, proxies /api → http://localhost:8000
```

## Regenerating the API client

The Angular client lives at `frontend/src/api/` and is fully generated.
After changing FastAPI routes or schemas, run:

```
cd frontend
npm run openapi    # dumps openapi.json then runs openapi-generator-cli
```

This dumps the spec via `backend/scripts/dump_openapi.py` (no server
needed) and regenerates the typescript-angular client in place.
