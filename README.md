# Stock Portfolio API

Backend FastAPI para análisis de acciones (TSX, NYSE, LSE, NASDAQ) con enriquecimiento vía Yahoo Finance.

Este repo contiene solo el **API** desplegable en [Render](https://render.com). El frontend vive en un repo separado: `stock-portfolio-web`.

## Estructura

```
stock-portfolio-api/
├── backend/          # FastAPI app
├── data/             # CSVs y JSON para el pipeline ETL
├── scripts/          # Utilidades CLI (add_stocks, test_api)
├── render.yaml       # Deploy automático en Render
└── .env.example
```

## Quick Start (local)

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env
python main.py
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/health`

### Cargar datos iniciales

En el Dashboard del frontend, o vía API:

```bash
curl http://localhost:8000/api/etl/run
```

## Variables de entorno

| Variable | Descripción | Local | Render |
|----------|-------------|-------|--------|
| `DATABASE_PATH` | Ruta SQLite | `./backend/stock_unifier.db` | `/var/data/stock_unifier.db` |
| `DATA_DIR` | CSVs/JSON del ETL | `./data` | `/opt/render/project/src/data` |
| `CORS_ORIGINS` | Orígenes permitidos | `http://localhost:5173` | URL del frontend |

## Deploy en Render

1. Crear repo en GitHub: `Qleoz12/stock-portfolio-api`
2. Push de este código a `main`
3. En Render: **New → Blueprint** (detecta `render.yaml`)
4. Verificar: `https://TU-URL.onrender.com/api/health`

## Scripts útiles

```bash
# Agregar acciones
python scripts/add_stocks.py NFLX GOOG

# Probar endpoints
python scripts/test_api.py
```
