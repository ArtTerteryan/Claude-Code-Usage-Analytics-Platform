"""Central configuration for the analytics platform.

Defines paths, constants, and thresholds used across
the ingestion pipeline, database layer, and dashboard.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
DB_PATH = DATA_DIR / "claude_code.db"
JSONL_PATH = OUTPUT_DIR / "telemetry_logs.jsonl"
CSV_PATH = OUTPUT_DIR / "employees.csv"

# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

BATCH_INSERT_SIZE = 5_000
PROGRESS_LOG_INTERVAL = 50_000

# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

ZSCORE_THRESHOLD = 3.5
IQR_MULTIPLIER = 1.5

# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

SMA_WINDOW = 7
FORECAST_HORIZON_DAYS = 7
CONFIDENCE_MULTIPLIER = 1.96
