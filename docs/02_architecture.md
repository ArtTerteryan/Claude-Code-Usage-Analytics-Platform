# Architecture Document: Claude Code Telemetry Analytics Platform

## 1. System Overview

The platform runs as a single Docker container that:
1. Generates synthetic telemetry data (on first run)
2. Ingests it into a SQLite database
3. Serves an interactive Streamlit dashboard

```
docker compose up
       │
       ▼
┌─────────────────────────────────────────────────┐
│  Docker Container                                │
│                                                  │
│  entrypoint.sh                                   │
│  ├── generate_fake_data.py  (if data missing)    │
│  ├── python -m src.ingestion.pipeline  (if DB    │
│  │   missing)                                    │
│  └── streamlit run src/dashboard/app.py          │
│                                                  │
│  Volumes:                                        │
│  ├── db-data:/app/data       (SQLite DB)         │
│  └── telemetry-output:/app/output  (JSONL + CSV) │
└─────────────────────────────────────────────────┘
```

## 2. Project Structure

```
.
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── pyproject.toml
├── .streamlit/config.toml
│
├── src/
│   ├── config.py                      # Paths, thresholds, constants
│   │
│   ├── ingestion/                     # Data ingestion pipeline
│   │   ├── parser.py                  # JSONL streaming, two-stage JSON extraction
│   │   ├── validators.py              # Type coercion + typed record dataclasses
│   │   ├── loader.py                  # Batch INSERT OR IGNORE into SQLite
│   │   └── pipeline.py               # Orchestrator: parse → validate → load
│   │
│   ├── database/                      # Database layer
│   │   ├── schema.py                  # DDL for 7 tables + 20 indexes
│   │   └── connection.py              # Thread-safe read-only SQLite connection
│   │
│   ├── analytics/                     # Query layer
│   │   └── queries.py                 # All SQL queries for the dashboard
│   │
│   └── dashboard/                     # Streamlit UI
│       ├── app.py                     # Entry point + sidebar navigation
│       ├── components/
│       │   ├── charts.py              # Reusable Plotly chart builders
│       │   ├── filters.py             # Sidebar filter widgets
│       │   └── metrics.py             # KPI card rendering + formatters
│       └── pages/
│           ├── overview.py            # Executive Summary
│           ├── cost_analysis.py       # Model Analytics
│           ├── tool_usage.py          # Tool Usage
│           ├── team_insights.py       # Team Insights
│           ├── error_analysis.py      # Errors & Reliability
│           └── advanced_insights.py   # Anomaly Detection & Forecasting
│
├── tests/
│   ├── test_parser.py                 # JSONL parsing tests (10 tests)
│   ├── test_validators.py             # Type coercion + validation tests (17 tests)
│   ├── test_loader.py                 # Batch insert + session building tests (13 tests)
│   └── test_analytics.py             # Z-score, anomaly, forecasting tests (11 tests)
│
├── claude_code_telemetry/
│   └── generate_fake_data.py          # Synthetic data generator
│
└── docs/
    ├── 01_requirements_analysis.md
    └── 02_architecture.md             # This document
```

### Layer Responsibilities

| Layer | Module | Purpose |
|-------|--------|---------|
| **Ingestion** | `src/ingestion/*` | Parse JSONL → validate → batch-load into SQLite |
| **Database** | `src/database/*` | Schema DDL, connection management |
| **Analytics** | `src/analytics/queries.py` | Parameterized SQL queries with dynamic filters |
| **Dashboard** | `src/dashboard/*` | Streamlit UI, Plotly charts, sidebar filters |

Dependency flow: `Dashboard → Analytics → Database ← Ingestion`

---

## 3. Database Schema

### 3.1 Tables

The database uses a star schema with 7 tables:
- **4 fact tables:** `api_requests`, `tool_events`, `api_errors`, `user_prompts`
- **2 dimension tables:** `employees`, `sessions`
- **1 pre-aggregated table:** `daily_cost_summary`

### 3.2 Entity-Relationship Diagram

```
┌────────────────┐       ┌──────────────────┐
│   employees    │       │     sessions      │
│────────────────│       │──────────────────│
│ email (PK)     │◄──┐   │ session_id (PK)  │
│ full_name      │   └───│ user_email (FK)   │
│ practice       │       │ start_time        │
│ level          │       │ end_time          │
│ location       │       │ duration_seconds  │
│ level_numeric  │       │ num_turns         │
└────────────────┘       │ terminal_type     │
        ▲                │ os_type           │
        │                │ host_arch         │
        │                │ os_version        │
        │                │ service_version   │
        │                │ organization_id   │
        │                └──────┬────────────┘
        │                       │
        │          ┌────────────┼─────────────────┐
        │          │            │                  │
        │          ▼            ▼                  ▼
        │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │  │ api_requests  │ │ tool_events  │ │ api_errors   │
        │  │──────────────│ │──────────────│ │──────────────│
        │  │ event_id (UQ)│ │ event_id (UQ)│ │ event_id (UQ)│
        │  │ session_id FK│ │ event_type   │ │ session_id FK│
        │  │ timestamp    │ │ session_id FK│ │ timestamp    │
        │  │ model        │ │ timestamp    │ │ model        │
        │  │ cost_usd     │ │ tool_name    │ │ error_message│
        │  │ duration_ms  │ │ decision     │ │ status_code  │
        │  │ input_tokens │ │ success      │ │ duration_ms  │
        │  │ output_tokens│ │ duration_ms  │ │ attempt      │
        │  │ cache tokens │ │ result_size  │ │ date, hour   │
        │  │ date, hour   │ │ date, hour   │ └──────────────┘
        │  └──────────────┘ └──────────────┘
        │
        │  ┌──────────────┐    ┌─────────────────────┐
        │  │ user_prompts │    │ daily_cost_summary   │
        │  │──────────────│    │─────────────────────│
        │  │ event_id (UQ)│    │ date, model,         │
        │  │ session_id FK│    │ practice (PK)        │
        │  │ timestamp    │    │ total_cost           │
        │  │ prompt_length│    │ total_requests       │
        │  │ date, hour   │    │ total tokens         │
        │  └──────────────┘    │ avg_duration_ms      │
        │                      └─────────────────────┘
```

### 3.3 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Separate fact tables per event type | Each type has distinct columns; a single wide table would be 60%+ NULL |
| `date` and `hour` as derived columns | Enables fast GROUP BY without runtime parsing in SQLite |
| `event_id` UNIQUE constraint | Enables idempotent re-ingestion via `INSERT OR IGNORE` |
| `status_code` as TEXT | Cannot be integer due to `"undefined"` values in error events |
| `level_numeric` on employees | Enables numeric sorting without string parsing |
| Pre-aggregated `daily_cost_summary` | The most common dashboard query avoids scanning ~450K rows |
| `tool_events` stores both decisions and results | Distinguished by `event_type` column, avoids complex temporal matching |

---

## 4. Ingestion Pipeline

### 4.1 Pipeline Flow

```
telemetry_logs.jsonl ──► Parser ──► Validator ──► Loader ──► SQLite
                                                     ▲
employees.csv ──────────────────────────────────────►─┘
```

### 4.2 Parser (`src/ingestion/parser.py`)

Streams the JSONL file line-by-line and handles the two-stage JSON extraction:

1. `json.loads(line)` → CloudWatch batch object
2. For each `logEvent` in `batch["logEvents"]`: `json.loads(logEvent["message"])` → event payload
3. Yields flat dicts with `event_id`, `body`, `attributes`, `resource`, `scope_version`

Malformed JSON lines or messages are logged and skipped — the pipeline never crashes on bad data.

### 4.3 Validator (`src/ingestion/validators.py`)

Coerces string-encoded values to proper types. All numeric attributes in the telemetry data arrive as strings.

| Field | Coercion |
|-------|----------|
| `cost_usd` | `float(x)`, rounded to 6 decimal places |
| `duration_ms`, `*_tokens`, `prompt_length`, `attempt` | `int(float(x))` — float first to handle "100.0" |
| `success` | `"true" → True`, `"false" → False` |
| `status_code` | Kept as string (handles `"undefined"`) |
| `tool_result_size_bytes` | `int(float(x))` if present, else `None` |

Produces typed dataclass records: `ApiRequestRecord`, `ToolEventRecord`, `ApiErrorRecord`, `UserPromptRecord`, `EmployeeRecord`.

### 4.4 Loader (`src/ingestion/loader.py`)

- Accumulates records in memory buffers (one per table)
- Flushes to SQLite using `executemany()` every 5,000 records
- Uses `INSERT OR IGNORE` for idempotent re-runs
- After all events are loaded, builds derived tables:
  - `sessions` — aggregated from all event tables (MIN/MAX timestamp, turn count, etc.)
  - `daily_cost_summary` — pre-aggregated cost metrics by date/model/practice

### 4.5 Pipeline Orchestrator (`src/ingestion/pipeline.py`)

Wires parser → validator → loader and reports progress every 50,000 events.

```bash
# Invoked by entrypoint.sh:
python3 -m src.ingestion.pipeline \
    --telemetry output/telemetry_logs.jsonl \
    --employees output/employees.csv \
    --db data/claude_code.db
```

---

## 5. Analytics Layer (`src/analytics/queries.py`)

A single module containing all SQL queries used by the dashboard. Each function:
- Accepts a SQLite connection + filter parameters (date range, practices, levels, models)
- Builds parameterized SQL with dynamic WHERE clauses
- Returns a pandas DataFrame

Queries are organized by dashboard page: overview KPIs, cost breakdowns, tool statistics, error rates, team comparisons, anomaly detection data.

---

## 6. Dashboard (`src/dashboard/`)

### 6.1 Navigation

Six-page Streamlit app using `st.navigation` (Streamlit 1.36+):

| Page | Key Visualizations |
|------|-------------------|
| **Executive Summary** | KPI cards, daily cost trend, hourly heatmap, model donut chart |
| **Model Analytics** | Cost by model (stacked area), latency comparison, token breakdown, cache ratio |
| **Tool Usage** | Tool frequency ranking, accept/reject rates, success rates, duration stats |
| **Team Insights** | Practice comparison, level-based metrics, top users leaderboard |
| **Errors & Reliability** | Error rate over time, error types, status codes, retry distribution |
| **Advanced Analytics** | Anomaly scatter plots (Z-score + IQR), 7-day cost/token forecasts with confidence bands |

### 6.2 Global Sidebar Filters

Present on every page, applied to all queries:
- **Date range** — start and end date pickers
- **Practice** — multi-select (Platform, Data, ML, Backend, Frontend Engineering)
- **Level** — range slider (L1 through L10)
- **Model** — multi-select (5 Claude model variants)

### 6.3 Connection Management

- `@st.cache_resource` caches the SQLite connection across reruns
- `check_same_thread=False` enables Streamlit's threaded model to share the connection
- Read-only mode (`?mode=ro`) prevents accidental writes from the dashboard

---

## 7. Advanced Analytics

### 7.1 Anomaly Detection

Two complementary methods flag a data point as anomalous if **either** triggers:

1. **Modified Z-Score** (robust to outliers):
   - Uses median and MAD (Median Absolute Deviation) instead of mean/std
   - Formula: `modified_z = 0.6745 * (x - median) / MAD`
   - Threshold: `|modified_z| > 3.5`

2. **IQR Fence** (non-parametric):
   - Q1, Q3 = 25th, 75th percentiles
   - Anomaly if `x < Q1 - 1.5*IQR` or `x > Q3 + 1.5*IQR`

Applied to daily cost totals and per-session cost values.

### 7.2 Trend Forecasting

Simple approach using only numpy (no external time-series libraries):

1. **7-day Simple Moving Average (SMA)** — smooths daily noise
2. **Linear Regression** on the SMA — `y = mx + b` via `numpy.polyfit(degree=1)`
3. **95% Confidence band** — forecast ± 1.96 * residual standard deviation
4. **Forecast horizon** — 7 days beyond the last data point

Applied to daily total cost and daily total token consumption.

---

## 8. Testing

51 tests across 4 files, all using in-memory SQLite (`:memory:`):

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_parser.py` | 10 | JSONL streaming, batch extraction, malformed data handling |
| `test_validators.py` | 17 | Type coercion, all 5 event types, edge cases, rejections |
| `test_loader.py` | 13 | Batch insert, auto-flush, idempotency, session building, daily summary |
| `test_analytics.py` | 11 | Modified Z-score, anomaly flagging, moving average, linear trend, forecasting |

Run inside Docker:
```bash
docker compose run --rm --entrypoint "" dashboard python -m pytest tests/ -v
```

---

## 9. Technology Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Python 3.13 | Runtime | Latest stable, slim Docker image |
| Streamlit | Dashboard | Rapid interactive dashboards, built-in widgets |
| Plotly | Charts | Interactive, publication-quality visualizations |
| pandas | Data manipulation | DataFrame operations for query results |
| numpy | Numerics | Anomaly detection math, linear regression |
| SQLite | Database | Zero-config, embedded, sufficient for ~450K events |
| pytest | Testing | Standard Python test framework |
| Docker | Deployment | Single command to run — no local Python setup needed |

No heavy ML libraries (no scikit-learn, Prophet, or statsmodels). All analytics use numpy and pandas only.

---

## 10. Configuration

Central configuration in `src/config.py`:

| Setting | Value | Purpose |
|---------|-------|---------|
| `DB_PATH` | `data/claude_code.db` | SQLite database location |
| `JSONL_PATH` | `output/telemetry_logs.jsonl` | Input telemetry file |
| `CSV_PATH` | `output/employees.csv` | Input employee file |
| `BATCH_INSERT_SIZE` | 5,000 | Records per batch insert |
| `ZSCORE_THRESHOLD` | 3.5 | Modified Z-score anomaly cutoff |
| `IQR_MULTIPLIER` | 1.5 | IQR fence multiplier |
| `SMA_WINDOW` | 7 | Moving average window (days) |
| `FORECAST_HORIZON_DAYS` | 7 | Forecast period |
| `CONFIDENCE_MULTIPLIER` | 1.96 | 95% confidence band |

---

## 11. Error Handling

| Layer | Error Type | Handling |
|-------|-----------|----------|
| Parser | Malformed JSON line | Log warning, skip line, continue |
| Parser | Malformed event message | Log warning, skip event, continue |
| Validator | Failed type coercion | Log warning, skip event, continue |
| Loader | Duplicate event_id | `INSERT OR IGNORE` (idempotent) |
| Dashboard | Empty query result | Shows "No data available" message |
| Dashboard | Database not found | Clear error with instructions to run ingestion |
