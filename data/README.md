# Data directory

Archivos de entrada para el pipeline ETL (`/api/etl/run`).

| Path | Uso |
|------|-----|
| `cache_yf/tsx_features.csv` | Acciones TSX |
| `cache_yf/nyse_features.csv` | Acciones NYSE |
| `cache_yf/lse_features.csv` | Acciones LSE |
| `cache_yf/*_div_events.csv` | Eventos de dividendos |
| `quanfury_div.json` | Dividendos Quanfury |
| `trading-os/quantfury/stocks.json` | Catálogo Quanfury |

Estos archivos se versionan en git. La base de datos SQLite se genera en runtime y no va en el repo.
