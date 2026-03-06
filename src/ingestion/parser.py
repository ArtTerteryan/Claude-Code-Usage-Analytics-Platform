"""JSONL parser for CloudWatch-style telemetry log batches.

Handles two-stage JSON parsing: each JSONL line is a batch containing
logEvents whose 'message' field is itself a JSON-encoded string.
Yields flat event dicts suitable for validation and loading.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)


def parse_jsonl(path: Path) -> Generator[dict, None, None]:
    """Stream-parse a JSONL telemetry file, yielding one flat dict per event.

    Each yielded dict contains:
        - event_id: str (from logEvent.id)
        - body: str (event type, e.g. 'claude_code.api_request')
        - attributes: dict (flat key-value pairs)
        - resource: dict (host/env info)
        - scope_version: str (CLI version)

    Malformed lines or messages are logged and skipped.
    """
    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                batch = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Skipping malformed JSON at line %d: %s", line_num, e)
                continue

            yield from _parse_batch(batch, line_num)


def _parse_batch(batch: dict, line_num: int = 0) -> Generator[dict, None, None]:
    """Extract individual events from a CloudWatch log batch."""
    log_events = batch.get("logEvents", [])
    if not log_events:
        return

    for event in log_events:
        event_id = event.get("id", "")
        message_str = event.get("message", "")

        parsed = _parse_event_message(message_str)
        if parsed is None:
            logger.warning(
                "Skipping malformed event message at line %d, event_id=%s",
                line_num,
                event_id,
            )
            continue

        yield {
            "event_id": event_id,
            "body": parsed.get("body", ""),
            "attributes": parsed.get("attributes", {}),
            "resource": parsed.get("resource", {}),
            "scope_version": parsed.get("scope", {}).get("version", ""),
        }


def _parse_event_message(message_str: str) -> dict | None:
    """Parse the JSON-encoded message string from a logEvent.

    Returns parsed dict with keys: body, attributes, scope, resource.
    None if parsing fails.
    """
    try:
        return json.loads(message_str)
    except (json.JSONDecodeError, TypeError):
        return None
