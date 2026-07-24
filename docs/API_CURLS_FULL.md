# Stock Portfolio Unifier — API cURL reference (completo)

> Repo: [stock-portfolio-api](https://github.com/Qleoz12/stock-portfolio-api) · Resumen: [API_CURLS.md](./API_CURLS.md)

Base URLs (cambia según entorno):

```bash
# Local
export BASE="http://localhost:8000"

# Render (producción)
export BASE="https://stock-portfolio-api-zecl.onrender.com"
```

Docs interactivos: `$BASE/docs`  
OpenAPI JSON: `$BASE/openapi.json`

> **Windows PowerShell:** reemplaza `curl` por `Invoke-RestMethod` o usa Git Bash.  
> Ejemplo POST: `Invoke-RestMethod -Method POST -Uri "$env:BASE/api/stocks" -ContentType "application/json" -Body '{"ticker":"NFLX","enrich":true}'`

---

## 0. Smoke test (empieza aquí)

```bash
curl -s "$BASE/api/health"
curl -s "$BASE/docs" -o /dev/null -w "%{http_code}\n"
```

---

## 1. Core / ETL / Export

```bash
# Health
curl -s "$BASE/api/health"

# Cargar CSVs en DB (solo si DB vacía)
curl -s -X POST "$BASE/api/etl/run"

# Exportar todas las acciones CSV
curl -s "$BASE/api/export/stocks" -o stocks_export.csv
```

---

## 2. Stocks (`/api/stocks`)

```bash
# Listar (paginado + filtros)
curl -s "$BASE/api/stocks?page=1&page_size=20"
curl -s "$BASE/api/stocks?search=AAPL&page_size=10"
curl -s "$BASE/api/stocks?exchange=NYSE&sector=Technology&sort_by=div_yield_ttm&order=desc"
curl -s "$BASE/api/stocks?quanfury_only=true&min_health_score=70"

# Metadatos
curl -s "$BASE/api/stocks/exchanges"
curl -s "$BASE/api/stocks/sectors"
curl -s "$BASE/api/stocks/sector-stats"
curl -s "$BASE/api/stocks/search?q=bank"
curl -s "$BASE/api/stocks/by-ticker/AAPL"

# Score trend stats
curl -s "$BASE/api/stocks/score-trend/stats?exchange=NYSE"

# Detalle por id
curl -s "$BASE/api/stocks/1"

# Crear acción
curl -s -X POST "$BASE/api/stocks" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"NFLX","enrich":true}'

curl -s -X POST "$BASE/api/stocks" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","exchange":"NASDAQ","shares":10,"avg_price":180,"portfolio_id":1,"enrich":true}'

# Actualizar identidad / value trap
curl -s -X PATCH "$BASE/api/stocks/1" \
  -H "Content-Type: application/json" \
  -d '{"sector":"Technology","company_name":"Apple Inc."}'

curl -s -X POST "$BASE/api/stocks/1/identity" \
  -H "Content-Type: application/json" \
  -d '{"exchange":"NASDAQ","symbol":"AAPL"}'

curl -s -X POST "$BASE/api/stocks/1/value-trap" \
  -H "Content-Type: application/json" \
  -d '{"possible_value_trap":true}'

# Precios / fundamentals
curl -s -X POST "$BASE/api/stocks/1/refresh-prices"
curl -s "$BASE/api/stocks/fundamentals/yahoo/1"
curl -s "$BASE/api/stocks/1/price-normalization"

# Enrich
curl -s "$BASE/api/stocks/enrich/status"
curl -s -X POST "$BASE/api/stocks/enrich/batch" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":10,"mode":"missing_prices"}'

curl -s "$BASE/api/stocks/features/refresh-status?hours=24"

curl -s -X POST "$BASE/api/stocks/enrich/filtered" \
  -H "Content-Type: application/json" \
  -d '{"exchange":"NYSE","batch_size":5,"max_workers":3}'

# Sector admin
curl -s -X POST "$BASE/api/stocks/sector/rename" \
  -H "Content-Type: application/json" \
  -d '{"from_sector":"Tech","to_sector":"Technology"}'

curl -s -X POST "$BASE/api/stocks/sector/clear-tag" \
  -H "Content-Type: application/json" \
  -d '{"sector":"Unknown"}'

curl -s -X POST "$BASE/api/stocks/sector-sample-refresh" \
  -H "Content-Type: application/json" \
  -d '{"sector":"Technology","sample_size":5}'

# Borrar
curl -s -X DELETE "$BASE/api/stocks/999" -w "\nHTTP %{http_code}\n"
```

---

## 3. Charts & Fair value (`/api/stocks/{id}/...`)

```bash
STOCK_ID=1

# OHLCV
curl -s "$BASE/api/stocks/$STOCK_ID/ohlcv?period=1y"
curl -s "$BASE/api/stocks/$STOCK_ID/ohlcv?period=5y"

# Drawings
curl -s "$BASE/api/stocks/$STOCK_ID/drawings"

curl -s -X POST "$BASE/api/stocks/$STOCK_ID/drawings" \
  -H "Content-Type: application/json" \
  -d '{"drawing_type":"hline","price1":150.5,"color":"#ff0000","label":"support"}'

curl -s -X PUT "$BASE/api/stocks/$STOCK_ID/drawings/1" \
  -H "Content-Type: application/json" \
  -d '{"price1":155.0,"label":"support v2"}'

curl -s -X DELETE "$BASE/api/stocks/$STOCK_ID/drawings/1" -w "\nHTTP %{http_code}\n"

# Fair value
curl -s "$BASE/api/stocks/$STOCK_ID/fair-value-summary?ensure_ohlcv=true"
curl -s "$BASE/api/stocks/$STOCK_ID/fair-value-series?granularity=weekly&period=5y"
curl -s "$BASE/api/stocks/$STOCK_ID/fair-value-annual-table?year_from=2020&year_to=2025"
curl -s "$BASE/api/stocks/$STOCK_ID/fair-value-revisions"

curl -s -X POST "$BASE/api/stocks/$STOCK_ID/fair-value-revisions" \
  -H "Content-Type: application/json" \
  -d '{"revisions":[{"effective_date":"2026-01-01","fair_value":200,"uncertainty":"medium","source":"manual"}]}'

curl -s -X DELETE "$BASE/api/stocks/$STOCK_ID/fair-value-revisions/1" -w "\nHTTP %{http_code}\n"

# Valuation / prediction compare
curl -s "$BASE/api/stocks/$STOCK_ID/valuation"
curl -s "$BASE/api/stocks/$STOCK_ID/prediction-compare"
```

---

## 4. Portfolios (`/api/portfolios`)

```bash
# Listar / crear
curl -s "$BASE/api/portfolios"

curl -s -X POST "$BASE/api/portfolios" \
  -H "Content-Type: application/json" \
  -d '{"name":"Growth","broker":"IBKR","description":"long term"}'

# Detalle / CRUD
curl -s "$BASE/api/portfolios/1"
curl -s -X PUT "$BASE/api/portfolios/1" \
  -H "Content-Type: application/json" \
  -d '{"name":"Growth Updated","description":"updated"}'

curl -s -X DELETE "$BASE/api/portfolios/1" -w "\nHTTP %{http_code}\n"

# Holdings
curl -s -X POST "$BASE/api/portfolios/1/holdings" \
  -H "Content-Type: application/json" \
  -d '{"stock_id":1,"shares":10,"avg_price":150.25}'

curl -s -X PUT "$BASE/api/portfolios/1/holdings/1" \
  -H "Content-Type: application/json" \
  -d '{"shares":15,"avg_price":148.0}'

curl -s -X DELETE "$BASE/api/portfolios/1/holdings/1" -w "\nHTTP %{http_code}\n"

# Snapshots
curl -s -X POST "$BASE/api/portfolios/1/snapshots" \
  -H "Content-Type: application/json" \
  -d '{"month":3,"year":2026,"total_value":50000,"total_dividends":1200,"notes":"Q1"}'

curl -s "$BASE/api/portfolios/1/snapshots"

curl -s -X PATCH "$BASE/api/portfolios/snapshots/1" \
  -H "Content-Type: application/json" \
  -d '{"notes":"Q1 revised"}'
```

---

## 5. Dividends (`/api/dividends`)

```bash
# Calendario paginado
curl -s "$BASE/api/dividends/calendar?start_date=2026-01-01&end_date=2026-12-31&page=1&page_size=50"

# Próximos / stats
curl -s "$BASE/api/dividends/upcoming?days=30"
curl -s "$BASE/api/dividends/stats"

# Notas de calendario
curl -s "$BASE/api/dividends/calendar-notes?start_date=2026-01-01&end_date=2026-12-31"

curl -s -X POST "$BASE/api/dividends/calendar-notes" \
  -H "Content-Type: application/json" \
  -d '{"note_date":"2026-03-15","title":"Ex-div watch","body":"Check TSX names"}'

curl -s -X PATCH "$BASE/api/dividends/calendar-notes/1" \
  -H "Content-Type: application/json" \
  -d '{"title":"Updated","body":"new note"}'

curl -s -X DELETE "$BASE/api/dividends/calendar-notes/1" -w "\nHTTP %{http_code}\n"

# Dividendo manual
curl -s -X POST "$BASE/api/dividends/calendar/manual" \
  -H "Content-Type: application/json" \
  -d '{"div_date":"2026-04-01","ticker_yf":"RY.TO","amount":1.42,"currency":"CAD","company_name":"Royal Bank"}'

curl -s -X PATCH "$BASE/api/dividends/calendar/manual/1" \
  -H "Content-Type: application/json" \
  -d '{"amount":1.50,"note":"corrected"}'

curl -s -X DELETE "$BASE/api/dividends/calendar/manual/1" -w "\nHTTP %{http_code}\n"

# Refresh forward projections
curl -s -X POST "$BASE/api/dividends/refresh-forward" \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2026-01-01","end_date":"2026-12-31","weeks_ahead":8,"max_stocks":50}'
```

---

## 6. Analytics (`/api/analytics`)

```bash
curl -s "$BASE/api/analytics/dashboard"
curl -s "$BASE/api/analytics/week-proximity?weeks=4"
curl -s "$BASE/api/analytics/top-dividend-yields?limit=20"
curl -s "$BASE/api/analytics/top-dividend-yields?exchange=NYSE&limit=10"
```

---

## 7. Arbitrage (`/api/arbitrage`)

```bash
# Rates
curl -s "$BASE/api/arbitrage/rates"
curl -s "$BASE/api/arbitrage/rates/cached?minutes=10"
curl -s "$BASE/api/arbitrage/summary"
curl -s "$BASE/api/arbitrage/history?pair=USDT/COP&hours=24"
curl -s "$BASE/api/arbitrage/sources"

# P2P book
curl -s "$BASE/api/arbitrage/p2p/book?asset=USDT&fiat=COP&trade_type=BUY&rows=20"

# Operations
curl -s "$BASE/api/arbitrage/operations?limit=50"
curl -s "$BASE/api/arbitrage/operations/stats"

curl -s -X POST "$BASE/api/arbitrage/operations" \
  -H "Content-Type: application/json" \
  -d '{"pair":"USDT/COP","buy_source":"binance","sell_source":"local","buy_price":4100,"sell_price":4150,"amount_usdt":100,"fee_total":2.5,"notes":"test"}'

curl -s -X PATCH "$BASE/api/arbitrage/operations/1" \
  -H "Content-Type: application/json" \
  -d '{"notes":"closed","fee_total":3.0}'
```

---

## 8. Journal / Bitácora (`/api/journal`)

```bash
curl -s "$BASE/api/journal/hub?start_date=2026-01-01&end_date=2026-12-31"

curl -s -X POST "$BASE/api/journal/entries" \
  -H "Content-Type: application/json" \
  -d '{"entry_date":"2026-03-20","title":"Trade idea","body":"Watch copper miners","tags":["macro"]}'

curl -s -X PATCH "$BASE/api/journal/entries/1" \
  -H "Content-Type: application/json" \
  -d '{"body":"Updated thesis"}'

curl -s -X DELETE "$BASE/api/journal/entries/1" -w "\nHTTP %{http_code}\n"

# Patch items from other sources via journal hub
curl -s -X PATCH "$BASE/api/journal/dividend-calendar/1" \
  -H "Content-Type: application/json" \
  -d '{"body":"journal edit"}'

curl -s -X DELETE "$BASE/api/journal/dividend-calendar/1" -w "\nHTTP %{http_code}\n"
curl -s -X PATCH "$BASE/api/journal/manual-dividend/1" -H "Content-Type: application/json" -d '{"note":"fix"}'
curl -s -X PATCH "$BASE/api/journal/portfolio-snapshot/1" -H "Content-Type: application/json" -d '{"notes":"fix"}'
curl -s -X PATCH "$BASE/api/journal/arbitrage-operation/1" -H "Content-Type: application/json" -d '{"notes":"fix"}'
```

---

## 9. Market charts (`/api/market`)

```bash
curl -s "$BASE/api/market/sector-charts?period=1y"
curl -s "$BASE/api/market/sector-equity-charts?period=6mo"
```

---

## 10. Forex (`/api/forex`)

```bash
curl -s "$BASE/api/forex/dashboard"
curl -s "$BASE/api/forex/pairs"
```

---

## 11. News & feeds

```bash
curl -s "$BASE/api/news-sentiment/stock/1"
curl -s "$BASE/api/x-feeds"
```

---

## 12. Limitless & Polymarket

```bash
curl -s "$BASE/api/limitless/finance-markets"
curl -s "$BASE/api/limitless/stock/1"

curl -s "$BASE/api/polymarket/search?q=trump"
curl -s "$BASE/api/polymarket/stock/1"
```

---

## 13. Cluster Explorer (`/api/cluster`)

```bash
# Inspect / metadata
curl -s "$BASE/api/cluster/inspect"
curl -s "$BASE/api/cluster/features"
curl -s "$BASE/api/cluster/universes"

curl -s -X POST "$BASE/api/cluster/universes" \
  -H "Content-Type: application/json" \
  -d '{"id":"my_watchlist","name":"My Watchlist","tickers":["AAPL","MSFT","NVDA"]}'

# Coverage / dataset
curl -s "$BASE/api/cluster/coverage?universe_id=dow30&period_days=365"
curl -s "$BASE/api/cluster/dataset?universe_id=dow30&period_days=365&feature_profile=ALL_CLUSTERING_ELIGIBLE_FEATURES"

# Custom profile
curl -s -X POST "$BASE/api/cluster/profiles/custom" \
  -H "Content-Type: application/json" \
  -d '{"name":"momentum_pack","display_name":"Momentum","features":["rsi_14","macd","div_yield_ttm"]}'

curl -s "$BASE/api/cluster/profiles/custom"

# Validate / refresh / analyze
curl -s -X POST "$BASE/api/cluster/validate" \
  -H "Content-Type: application/json" \
  -d '{"universe_id":"dow30","period_days":365,"feature_profile":"ALL_CLUSTERING_ELIGIBLE_FEATURES"}'

curl -s -X POST "$BASE/api/cluster/refresh-missing?universe_id=dow30"

curl -s -X POST "$BASE/api/cluster/analyze" \
  -H "Content-Type: application/json" \
  -d '{"universe_id":"dow30","mode":"feature","period_days":365,"k_min":2,"k_max":8}'

curl -s -X POST "$BASE/api/cluster/analyze" \
  -H "Content-Type: application/json" \
  -d '{"universe_id":"dow30","mode":"correlation","period_days":180,"correlation_method":"pearson"}'

# Runs / export
curl -s "$BASE/api/cluster/runs?limit=10"
curl -s "$BASE/api/cluster/runs/RUN_ID_HERE"
curl -s "$BASE/api/cluster/dataset/export?universe_id=dow30&period_days=365" -o cluster_dataset.json
curl -s "$BASE/api/cluster/runs/RUN_ID_HERE/export" -o cluster_run_export.json
curl -s "$BASE/api/cluster/runs/RUN_ID_HERE/export/validate"
```

---

## 14. Postman / import rápido

Importa todos los endpoints automáticamente:

```
https://stock-portfolio-api-zecl.onrender.com/openapi.json
```

o en local:

```
http://localhost:8000/openapi.json
```

---

## 15. Script de prueba automatizado

```bash
python scripts/test_api.py --url http://localhost:8000
python scripts/test_api.py --url https://stock-portfolio-api-zecl.onrender.com --quick
```

---

## Notas

- Reemplaza `1`, `RUN_ID_HERE`, fechas y tickers con valores reales de tu DB.
- En Render free el primer request puede tardar ~30–60 s (cold start).
- Algunos endpoints externos (Limitless, Polymarket, X feeds) requieren API keys en `.env`.
- `POST /api/etl/run` solo si la DB está vacía; en producción usas la DB del GitHub Release.
