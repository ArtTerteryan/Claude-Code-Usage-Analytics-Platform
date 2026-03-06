# Claude Code Telemetry Analytics Platform

An end-to-end analytics platform that ingests, processes, and visualizes Claude Code telemetry data. Built as an internship assignment for Provectus.

## What It Does

This platform processes CloudWatch-style JSONL telemetry logs from Claude Code sessions, stores them in a normalized SQLite database, and presents interactive analytics through a Streamlit dashboard.

### Key Features

- **Ingestion pipeline** — Streams and parses nested JSONL, validates and coerces types, batch-loads into SQLite with idempotent `INSERT OR IGNORE`
- **Star-schema database** — 7 normalized tables (api_requests, tool_events, api_errors, user_prompts, sessions, employees, daily_cost_summary) with 20 indexes
- **Interactive dashboard** — 6-page Streamlit app with global filters (date range, practice, level, model)
- **Anomaly detection** — Modified Z-score and IQR-based flagging of unusual cost and session patterns
- **Trend forecasting** — Moving-average + linear regression with 95% confidence bands
- **51 unit tests** — Full coverage of parsing, validation, loading, and analytics

## Quick Start

**Prerequisites:** [Docker](https://www.docker.com/get-started/) and [Docker Compose](https://docs.docker.com/compose/install/) must be installed.

```bash
git clone <repository-url>
cd <repository-name>
docker compose up
```

Open **http://localhost:8501** in your browser.

That's it. No Python installation, no virtual environments, no manual setup.

### What Happens on First Run

1. **Generates synthetic data** — 100 users, 5,000 sessions, 60 days of telemetry (~450K events)
2. **Ingests into SQLite** — Parses JSONL, validates types, builds sessions and daily summaries
3. **Starts the dashboard** — Streamlit launches on port 8501

On subsequent runs, steps 1-2 are skipped automatically (data persists in Docker volumes).

### Reset Data

To wipe all data and regenerate from scratch:

```bash
docker compose down -v
docker compose up
```

## Running Tests

All 51 tests run inside Docker:

```bash
docker compose run --rm --entrypoint "" dashboard python -m pytest tests/ -v
```

The `--entrypoint ""` flag overrides the default entrypoint so pytest runs directly instead of starting the dashboard.

## Project Structure

```
.
├── Dockerfile                     # Python 3.13-slim, installs deps, copies source
├── docker-compose.yml             # Single service with persistent volumes
├── entrypoint.sh                  # Auto generates data + ingests + starts Streamlit
├── pyproject.toml                 # Dependencies: streamlit, pandas, numpy, plotly
├── .streamlit/config.toml         # Dark theme, headless mode
│
├── src/
│   ├── config.py                  # Paths, thresholds, constants
│   ├── ingestion/                 # JSONL parsing, validation, batch loading
│   │   ├── parser.py              # Two-stage JSON extraction from CloudWatch batches
│   │   ├── validators.py          # Type coercion (str→int/float) + Pydantic-style records
│   │   ├── loader.py              # Batch INSERT OR IGNORE into SQLite
│   │   └── pipeline.py            # Orchestrator: parse → validate → load → build sessions
│   ├── database/                  # Schema and connections
│   │   ├── schema.py              # DDL for 7 tables + 20 indexes
│   │   └── connection.py          # Thread-safe read-only SQLite connection
│   ├── analytics/                 # SQL query layer
│   │   └── queries.py             # All dashboard queries (parameterized SQL)
│   └── dashboard/                 # Streamlit UI
│       ├── app.py                 # Entry point + sidebar navigation
│       ├── components/
│       │   ├── charts.py          # Reusable Plotly chart builders
│       │   ├── filters.py         # Sidebar filter widgets (date, practice, level, model)
│       │   └── metrics.py         # KPI card rendering + number formatters
│       └── pages/
│           ├── overview.py        # Executive Summary
│           ├── cost_analysis.py   # Model Analytics
│           ├── tool_usage.py      # Tool Usage
│           ├── team_insights.py   # Team Insights
│           ├── error_analysis.py  # Errors & Reliability
│           └── advanced_insights.py  # Anomaly Detection & Forecasting
│
├── tests/
│   ├── test_parser.py             # 10 tests — JSONL parsing, batch extraction
│   ├── test_validators.py         # 17 tests — type coercion, event validation
│   ├── test_loader.py             # 13 tests — batch insert, idempotency, sessions
│   └── test_analytics.py          # 11 tests — Z-score, anomalies, forecasting
│
├── claude_code_telemetry/
│   └── generate_fake_data.py      # Synthetic data generator (stdlib only)
│
└── docs/
    ├── 01_requirements_analysis.md   # Dataset field inventory + edge cases
    ├── 02_architecture.md            # System design + schema + pipeline details
    ├── insights_and_findings.md      # Key data insights for presentation
    ├── llm_usage_log.txt             # AI prompts used + validation approach
    └── slide_generation_prompt.txt   # Prompt to generate presentation slides
```

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Executive Summary** | KPIs, daily cost trends, hourly heatmap, model breakdown |
| **Model Analytics** | Cost by model/practice/user, latency comparison, token efficiency, cache utilization |
| **Tool Usage** | Tool popularity ranking, acceptance/success rates, execution duration |
| **Team Insights** | Practice comparison, level-based adoption, user leaderboard |
| **Errors & Reliability** | Error rates over time, type distribution, status codes, retry analysis |
| **Advanced Analytics** | Anomaly detection (Modified Z-score + IQR), 7-day cost and token forecasting |

## Architecture

```
JSONL file ──► Parser ──► Validator ──► Loader ──► SQLite ──► Queries ──► Dashboard
                                          ▲
employees.csv ────────────────────────────┘
```

**Data flow:**
1. `parser.py` streams the JSONL file line-by-line, extracting events from CloudWatch batches (two-stage JSON parsing)
2. `validators.py` coerces string-encoded numerics to proper types and produces typed records
3. `loader.py` batch-inserts records (5,000 at a time) using `INSERT OR IGNORE` for idempotency
4. `pipeline.py` orchestrates the full flow, then builds derived `sessions` and `daily_cost_summary` tables
5. `queries.py` provides parameterized SQL queries with dynamic WHERE clauses based on dashboard filters
6. Dashboard pages call queries and render results as Plotly charts

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.13 |
| Dashboard | Streamlit 1.36+ |
| Charts | Plotly 5.22+ |
| Data | pandas 2.2+, numpy 1.26+ |
| Database | SQLite (Python stdlib) |
| Testing | pytest 8.0+ |
| Containerization | Docker + Docker Compose |

## LLM Usage

This project was built entirely through iterative prompt-driven development using **Claude Code (Opus 4.6)** — Anthropic's CLI agent for software engineering.

**How it worked:** 7 key prompts directed the full implementation — from initial debugging and architecture design through testing, Dockerization, and documentation. Each prompt addressed a specific concern, and AI output was validated at every step through runtime testing, code audits, and the 51-test suite.

**Validation approach:**
- Every code change tested by running the full Docker pipeline end-to-end
- Dashboard pages manually inspected in the browser after each change
- Used grep/find to verify no dead code, unused imports, or orphaned files remained
- All 51 tests pass in the Docker container

See [docs/llm_usage_log.txt](docs/llm_usage_log.txt) for the complete prompt history and validation details.

## Documentation

- [Requirements Analysis](docs/01_requirements_analysis.md) — Complete dataset field inventory, data quality issues, and analytics questions
- [Architecture](docs/02_architecture.md) — Database schema, ingestion pipeline design, dashboard layout, and technical decisions
- [Data Insights & Findings](docs/insights_and_findings.md) — Key patterns discovered in the telemetry data
- [LLM Usage Log](docs/llm_usage_log.txt) — AI prompts used and how output was validated
- [Data Generator](claude_code_telemetry/README.md) — How the synthetic telemetry data is generated
