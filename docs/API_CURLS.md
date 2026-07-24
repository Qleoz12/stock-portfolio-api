# API cURL reference

Ver también: [README](../README.md) · [Arquitectura](./ARCHITECTURE.md)

Base URLs:

```bash
export BASE="http://localhost:8000"                              # local
export BASE="https://stock-portfolio-api-zecl.onrender.com"      # producción
```

Docs: `$BASE/docs` · OpenAPI: `$BASE/openapi.json`

---

## 0. Smoke test

```bash
curl -s "$BASE/api/health"
```

---

## 1. Core / ETL / Export

```bash
curl -s "$BASE/api/health"
curl -s -X POST "$BASE/api/etl/run"
curl -s "$BASE/api/export/stocks" -o stocks_export.csv
```

---

## 2. Stocks (`/api/stocks`)

```bash
curl -s "$BASE/api/stocks?page=1&page_size=20"
curl -s "$BASE/api/stocks?search=AAPL"
curl -s "$BASE/api/stocks/exchanges"
curl -s "$BASE/api/stocks/sectors"
curl -s "$BASE/api/stocks/sector-stats"
curl -s "$BASE/api/stocks/search?q=bank"
curl -s "$BASE/api/stocks/by-ticker/AAPL"
curl -s "$BASE/api/stocks/1"

curl -s -X POST "$BASE/api/stocks" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"NFLX","enrich":true}'

curl -s "$BASE/api/stocks/enrich/status"
curl -s -X POST "$BASE/api/stocks/enrich/batch" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":10,"mode":"missing_prices"}'
```

---

## 3. Charts & Fair value

```bash
STOCK_ID=1
curl -s "$BASE/api/stocks/$STOCK_ID/ohlcv?period=1y"
curl -s "$BASE/api/stocks/$STOCK_ID/fair-value-summary"
curl -s "$BASE/api/stocks/$STOCK_ID/valuation"
curl -s "$BASE/api/stocks/$STOCK_ID/prediction-compare"
```

---

## 4. Portfolios

```bash
curl -s "$BASE/api/portfolios"
curl -s -X POST "$BASE/api/portfolios" \
  -H "Content-Type: application/json" \
  -d '{"name":"Growth","broker":"IBKR"}'
curl -s "$BASE/api/portfolios/1"
```

---

## 5. Dividends

```bash
curl -s "$BASE/api/dividends/calendar?start_date=2026-01-01&end_date=2026-12-31&page=1&page_size=50"
curl -s "$BASE/api/dividends/stats"
curl -s "$BASE/api/dividends/upcoming?days=30"
```

---

## 6. Analytics

```bash
curl -s "$BASE/api/analytics/dashboard"
curl -s "$BASE/api/analytics/week-proximity?weeks=4"
curl -s "$BASE/api/analytics/top-dividend-yields?limit=20"
```

---

## 7. Arbitrage

```bash
curl -s "$BASE/api/arbitrage/rates"
curl -s "$BASE/api/arbitrage/summary"
curl -s "$BASE/api/arbitrage/p2p/book?asset=USDT&fiat=COP"
curl -s "$BASE/api/arbitrage/operations/stats"
```

---

## 8. Journal

```bash
curl -s "$BASE/api/journal/hub?start_date=2026-01-01&end_date=2026-12-31"
```

---

## 9. Market / Forex / News

```bash
curl -s "$BASE/api/market/sector-charts?period=1y"
curl -s "$BASE/api/forex/dashboard"
curl -s "$BASE/api/news-sentiment/stock/1"
curl -s "$BASE/api/x-feeds"
```

---

## 10. Limitless / Polymarket

```bash
curl -s "$BASE/api/limitless/finance-markets"
curl -s "$BASE/api/limitless/stock/1"
curl -s "$BASE/api/polymarket/search?q=trump"
curl -s "$BASE/api/polymarket/stock/1"
```

---

## 11. Cluster Explorer

```bash
curl -s "$BASE/api/cluster/inspect"
curl -s "$BASE/api/cluster/universes"
curl -s -X POST "$BASE/api/cluster/analyze" \
  -H "Content-Type: application/json" \
  -d '{"universe_id":"dow30","mode":"feature","period_days":365}'
curl -s "$BASE/api/cluster/runs?limit=10"
```

---

## Postman

Import: `https://stock-portfolio-api-zecl.onrender.com/openapi.json`

---

## Script automatizado

```bash
python scripts/test_api.py --url http://localhost:8000
python scripts/test_api.py --url https://stock-portfolio-api-zecl.onrender.com --quick
```

Lista completa: [API_CURLS_FULL.md](./API_CURLS_FULL.md)
