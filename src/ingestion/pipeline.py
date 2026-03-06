"""Ingestion pipeline orchestrator.

Wires together parser -> validator -> loader with progress reporting.
Provides a single entry point for the full ingestion workflow.
"""

from __future__ import annotations

import csv
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.config import BATCH_INSERT_SIZE, PROGRESS_LOG_INTERVAL
from src.database.connection import get_connection
from src.database.schema import drop_all_tables, initialize_database
from src.ingestion.loader import BatchLoader
from src.ingestion.parser import parse_jsonl
from src.ingestion.validators import validate_employee, validate_event

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    """Summary of an ingestion run."""

    total_events_parsed: int = 0
    events_per_type: dict[str, int] = field(default_factory=dict)
    events_loaded: int = 0
    events_rejected: int = 0
    rejection_reasons: list[str] = field(default_factory=list)
    employees_loaded: int = 0
    sessions_created: int = 0
    daily_summary_rows: int = 0
    duration_seconds: float = 0.0


def run_pipeline(
    jsonl_path: Path,
    csv_path: Path,
    db_path: Path,
    batch_size: int = BATCH_INSERT_SIZE,
    verbose: bool = False,
) -> IngestionReport:
    """Run the full ingestion pipeline: parse, validate, load.

    Steps:
        1. Initialize database schema (drop + recreate for clean load)
        2. Load employees from CSV
        3. Stream-parse JSONL, validate each event, batch-load into DB
        4. Derive sessions from loaded events
        5. Build pre-aggregated daily cost summary
        6. Run PRAGMA optimize
    """
    start = time.time()
    report = IngestionReport()

    with get_connection(db_path) as conn:
        # 1. Fresh schema
        drop_all_tables(conn)
        initialize_database(conn)
        conn.commit()

        loader = BatchLoader(conn, batch_size=batch_size)

        # 2. Load employees
        _load_employees(csv_path, loader, report)
        conn.commit()

        # 3. Parse and load telemetry events
        _load_events(jsonl_path, loader, report, verbose)
        loader.flush()
        conn.commit()

        # 4. Derive sessions
        report.sessions_created = loader.build_sessions()
        conn.commit()

        # 5. Build daily summary
        report.daily_summary_rows = loader.build_daily_summary()
        conn.commit()

        # 6. Optimize
        conn.execute("PRAGMA optimize")
        conn.execute("ANALYZE")

    report.duration_seconds = time.time() - start
    return report


def _load_employees(csv_path: Path, loader: BatchLoader, report: IngestionReport) -> None:
    """Load and validate employees from CSV."""
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = validate_employee(row)
            if record:
                loader.add_employee(record)
                report.employees_loaded += 1
            else:
                logger.warning("Skipping invalid employee row: %s", row)
    logger.info("Loaded %d employees", report.employees_loaded)


def _load_events(
    jsonl_path: Path, loader: BatchLoader, report: IngestionReport, verbose: bool
) -> None:
    """Stream-parse JSONL and load validated events."""
    for raw_event in parse_jsonl(jsonl_path):
        report.total_events_parsed += 1

        result = validate_event(raw_event)
        if result.is_valid and result.record is not None:
            loader.add(
                result.record,
                resource=raw_event.get("resource"),
                attrs=raw_event.get("attributes"),
            )
            report.events_loaded += 1
            body = raw_event.get("body", "unknown")
            report.events_per_type[body] = report.events_per_type.get(body, 0) + 1
        else:
            report.events_rejected += 1
            if result.rejection_reason:
                if len(report.rejection_reasons) < 100:
                    report.rejection_reasons.append(result.rejection_reason)

        if report.total_events_parsed % PROGRESS_LOG_INTERVAL == 0:
            _log_progress(report)


def _log_progress(report: IngestionReport) -> None:
    """Print progress to stderr."""
    parts = [f"{k.split('.')[-1]}: {v:,}" for k, v in sorted(report.events_per_type.items())]
    type_str = ", ".join(parts)
    msg = f"  Parsed {report.total_events_parsed:,} events ({type_str})"
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line entry point for the ingestion pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Claude Code telemetry data")
    parser.add_argument("--telemetry", type=Path, required=True, help="Path to telemetry_logs.jsonl")
    parser.add_argument("--employees", type=Path, required=True, help="Path to employees.csv")
    parser.add_argument("--db", type=Path, required=True, help="Path for the SQLite database")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s: %(message)s")

    report = run_pipeline(
        jsonl_path=args.telemetry,
        csv_path=args.employees,
        db_path=args.db,
        verbose=args.verbose,
    )

    print(f"\n=== Ingestion Complete ===")
    print(f"  Events parsed:    {report.total_events_parsed:,}")
    print(f"  Events loaded:    {report.events_loaded:,}")
    print(f"  Events rejected:  {report.events_rejected:,}")
    print(f"  Employees:        {report.employees_loaded:,}")
    print(f"  Sessions:         {report.sessions_created:,}")
    print(f"  Summary rows:     {report.daily_summary_rows:,}")
    print(f"  Duration:         {report.duration_seconds:.1f}s")
    for event_type, count in sorted(report.events_per_type.items()):
        print(f"    {event_type}: {count:,}")
    if report.rejection_reasons:
        print(f"\n  Sample rejections:")
        for reason in report.rejection_reasons[:5]:
            print(f"    - {reason}")


if __name__ == "__main__":
    main()
