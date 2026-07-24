# Stock Portfolio API

Backend FastAPI para análisis de acciones. Desplegado en [Render](https://render.com).

La base de datos **no** va en git. Se descarga al arrancar desde un **GitHub Release privado** (`stock-portfolio-db`).

## Estructura

```
stock-portfolio-api/
├── backend/                 # FastAPI + Docker
│   ├── scripts/download_db.py
│   └── docker-entrypoint.sh
├── data/                    # CSVs para ETL (opcional)
├── render.yaml
└── .env.example
```

## DB en producción (GitHub Release)

```
Render arranca
    → download_db.py
    → descarga stock_unifier.db del Release (GITHUB_TOKEN)
    → uvicorn
```

| Variable | Descripción |
|----------|-------------|
| `GITHUB_TOKEN` | PAT fine-grained, Contents:Read en `stock-portfolio-db` |
| `DB_REPO` | `Qleoz12/stock-portfolio-db` |
| `DB_RELEASE_TAG` | ej. `v1.0.0` |
| `DATABASE_PATH` | `/app/stock_unifier.db` |
| `CORS_ORIGINS` | URL del frontend (GitHub Pages) |

Publicar nueva DB: ver repo `stock-portfolio-db` → `publish.ps1`.

## Quick Start (local)

```bash
cd backend
pip install -r requirements.txt
# Usa la DB local de dataAnalitics o copia stock_unifier.db aquí
set DATABASE_PATH=stock_unifier.db
python main.py
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/health`

## Deploy en Render (Docker)

1. Push a `Qleoz12/stock-portfolio-api`
2. **Settings → Root Directory:** `backend`
3. **Environment:**
   - `GITHUB_TOKEN` = tu PAT (secret)
   - `DB_RELEASE_TAG` = `v1.0.0`
   - `DB_REPO` = `Qleoz12/stock-portfolio-db`
   - `DATABASE_PATH` = `/app/stock_unifier.db`
4. **Health Check Path:** `/api/health`
5. Deploy

Verificar:

```bash
curl https://TU-URL.onrender.com/api/health
# {"status":"ok","stocks_count":7876}
```

## Actualizar DB en producción

1. En `stock-portfolio-db`: `.\publish.ps1 -Tag v1.0.1`
2. En Render: `DB_RELEASE_TAG=v1.0.1`
3. Borrar la DB efímera: **Manual Deploy** (re-descarga al boot)

> En plan Free la DB vive en el contenedor. Cada redeploy vuelve a descargar del Release.
