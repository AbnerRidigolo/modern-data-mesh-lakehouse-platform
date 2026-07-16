# Enterprise Data Mesh & Lakehouse Portal (Frontend)

React + TypeScript SPA (Vite) that replaces the previous Streamlit portal. It talks exclusively to the
FastAPI DaaS Gateway (`../app`) over HTTP/JWT — it has no direct access to DuckDB, Delta Lake or Qdrant.

## Development

```bash
npm install
npm run dev
```

Configure the API base URL via `VITE_API_URL` (see `.env.example`). Defaults to `http://localhost:8000`.

## Build

```bash
npm run build
```

Type-checks with `tsc -b` and produces a static bundle in `dist/`, served by `Dockerfile` via Nginx
(SPA fallback configured in `nginx.conf`).

## Structure

- `src/api/` — axios client, JWT handling, typed endpoint wrappers.
- `src/auth/` — auth context (login/logout, token persistence).
- `src/components/` — shared UI (layout, cards, alerts, dbt lineage graph).
- `src/pages/` — one page per portal section (dashboard, time travel, catalog, MLOps, search, data quality).
