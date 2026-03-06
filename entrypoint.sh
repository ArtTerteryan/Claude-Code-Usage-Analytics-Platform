#!/bin/bash
set -e

# -------------------------------------------------------
# Step 1: Generate synthetic data if not already present
# -------------------------------------------------------
if [ ! -f "output/telemetry_logs.jsonl" ] || [ ! -f "output/employees.csv" ]; then
    echo "==> Generating synthetic telemetry data..."
    python3 generate_fake_data.py \
        --num-users 100 \
        --num-sessions 5000 \
        --days 60 \
        --output-dir output
    echo "==> Data generation complete."
fi

# -------------------------------------------------------
# Step 2: Ingest into SQLite if DB does not exist
# -------------------------------------------------------
if [ ! -f "data/claude_code.db" ]; then
    echo "==> Running ingestion pipeline..."
    python3 -m src.ingestion.pipeline \
        --telemetry output/telemetry_logs.jsonl \
        --employees output/employees.csv \
        --db data/claude_code.db
    echo "==> Ingestion complete."
fi

# -------------------------------------------------------
# Step 3: Start the Streamlit dashboard
# -------------------------------------------------------
echo "==> Starting dashboard on port 8501..."
exec streamlit run src/dashboard/app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
