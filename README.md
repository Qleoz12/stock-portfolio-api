# Stock Portfolio API

Backend **FastAPI** para análisis de acciones (TSX, NYSE, LSE, NASDAQ), portfolios, dividendos, arbitrage, clustering y más.

| | |
|---|---|
| **Producción** | https://stock-portfolio-api-zecl.onrender.com |
| **Docs** | https://stock-portfolio-api-zecl.onrender.com/docs |
| **OpenAPI** | https://stock-portfolio-api-zecl.onrender.com/openapi.json |
| **Repo código** | https://github.com/Qleoz12/stock-portfolio-api |
| **Repo DB** | https://github.com/Qleoz12/stock-portfolio-db (privado) |

---

## Arquitectura

```
Local (dataAnalitics)  →  publish.ps1  →  GitHub Release (stock-portfolio-db)
                                                    ↓
                                         Render Docker (este repo)
                                                    ↓
                                         Frontend GitHub Pages (futuro)
```

**Polyrepo:** 1 repo = 1 servicio. La SQLite **no va en git**; se publica como [GitHub Release](https://github.com/Qleoz12/stock-portfolio-db/releases) y se descarga al arrancar el contenedor.

Detalle completo: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**

### Boot en Render

```
docker-entrypoint.sh
  → download_db.py (GITHUB_TOKEN + DB_RELEASE_TAG)
  → uvicorn main:app
```

---

## Documentación

| Archivo | Contenido |
|---------|-----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Diagramas, módulos, env vars, flujos |
| [docs/API_CURLS.md](docs/API_CURLS.md) | cURLs resumidos por sección |
| [docs/API_CURLS_FULL.md](docs/API_CURLS_FULL.md) | **Todos** los curls (Postman-ready) |
| [scripts/test_api.py](scripts/test_api.py) | Tests de integración contra la API |

### Quick test

```bash
curl https://stock-portfolio-api-zecl.onrender.com/api/health
# {"status":"ok","stocks_count":7876}
```

---

## Estructura del repo

```
stock-portfolio-api/
├── backend/                    # FastAPI (Root Directory en Render)
│   ├── main.py
│   ├── routers/                # stocks, portfolios, dividends, cluster...
│   ├── analytics/              # clustering pipeline
│   ├── docker-entrypoint.sh
│   ├── Dockerfile
│   └── scripts/download_db.py
├── data/                       # CSVs ETL (opcional)
├── scripts/                    # test_api.py, add_stocks.py
├── docs/                       # arquitectura + curls
├── .github/workflows/          # CI + smoke test
├── render.yaml
└── .env.example
```

---

## Desarrollo local

```bash
cd backend
pip install -r requirements.txt

# Usa tu DB local (copia desde dataAnalitics o symlink)
set DATABASE_PATH=stock_unifier.db   # Windows
export DATABASE_PATH=stock_unifier.db  # Linux/Mac

python main.py
```

- API: http://localhost:8000  
- Docs: http://localhost:8000/docs  

### Tests

```bash
cd backend
pytest tests/ -q --ignore=tests/analytics

# Integración contra servidor corriendo
python ../scripts/test_api.py --url http://localhost:8000
```

---

## Deploy en Render

Ya configurado. Cada `git push` a `main` redespliega automáticamente.

| Setting | Valor |
|---------|-------|
| Root Directory | `backend` |
| Runtime | Docker |
| Health Check | `/api/health` |

### Environment (Render dashboard)

| Variable | Valor |
|----------|-------|
| `GITHUB_TOKEN` | `gh auth token` (Contents: Read en `stock-portfolio-db`) |
| `DB_REPO` | `Qleoz12/stock-portfolio-db` |
| `DB_RELEASE_TAG` | `v1.0.0` |
| `DATABASE_PATH` | `/app/stock_unifier.db` |
| `DB_ASSET_NAME` | `stock_unifier.db` |
| `CORS_ORIGINS` | `*` o URL del frontend |

> **Nunca** commitees tokens. Solo en Render Environment.

### Obtener `GITHUB_TOKEN`

```powershell
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
gh auth login
gh auth token
```

---

## Actualizar DB en producción

```powershell
# 1. En stock-portfolio-db
.\publish.ps1 -Tag v1.0.1 -Notes "updated enrich"

# 2. En Render: DB_RELEASE_TAG=v1.0.1 + Manual Deploy
```

---

## Automatización

| Qué | Automático | Cómo |
|-----|------------|------|
| **Deploy API** | ✅ | Render ↔ GitHub, push `main` |
| **CI tests** | ✅ | `.github/workflows/ci.yml` |
| **Smoke test prod** | ✅ | `.github/workflows/production-smoke.yml` |
| **Publicar DB** | ❌ manual | `publish.ps1` en `stock-portfolio-db` |
| **Frontend** | 🔜 pendiente | GitHub Pages + Action |

### Flujo completo automatizado (código)

```
git push main
    → GitHub Actions: pytest
    → GitHub Actions: curl /api/health en Render
    → Render: Docker build + deploy
```

### Futuro: automatizar DB publish

En `stock-portfolio-db` se puede agregar un workflow `workflow_dispatch` que ejecute `publish.ps1` con secret `GITHUB_TOKEN`. Por ahora es manual (más seguro para una DB de 11 MB).

---

## Módulos API

| Prefijo | Descripción |
|---------|-------------|
| `/api/stocks` | Screener, enrich, OHLCV, fair value |
| `/api/portfolios` | Carteras |
| `/api/dividends` | Calendario |
| `/api/analytics` | Dashboard |
| `/api/arbitrage` | Rates, P2P |
| `/api/journal` | Bitácora |
| `/api/cluster` | Clustering ML |
| `/api/market` | Sector charts |
| `/api/forex` | FX |
| `/api/limitless` | Prediction markets |
| `/api/polymarket` | Polymarket |

Ver [docs/API_CURLS_FULL.md](docs/API_CURLS_FULL.md) para ejemplos `curl` de cada endpoint.

---

## Licencia

Uso personal / portfolio. Ver repositorios relacionados en [Qleoz12](https://github.com/Qleoz12).
