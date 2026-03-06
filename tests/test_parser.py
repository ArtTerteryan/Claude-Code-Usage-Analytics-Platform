"""Tests for the JSONL parser."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.ingestion.parser import _parse_batch, _parse_event_message, parse_jsonl


def _make_message(body: str = "claude_code.api_request", attrs: dict | None = None) -> str:
    return json.dumps({
        "body": body,
        "attributes": attrs or {"key": "val"},
        "resource": {"os.type": "linux"},
        "scope": {"version": "1.0.0"},
    })


def _make_batch(*messages: str) -> dict:
    return {
        "logEvents": [
            {"id": f"evt-{i}", "message": msg}
            for i, msg in enumerate(messages)
        ]
    }


def _write_jsonl(lines: list[str]) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for line in lines:
        tmp.write(line + "\n")
    tmp.close()
    return Path(tmp.name)


class TestParseJsonl:
    def test_parses_valid_batch_with_single_event(self) -> None:
        batch = _make_batch(_make_message())
        path = _write_jsonl([json.dumps(batch)])
        events = list(parse_jsonl(path))
        assert len(events) == 1

    def test_parses_batch_with_multiple_events(self) -> None:
        batch = _make_batch(_make_message(), _make_message(), _make_message())
        path = _write_jsonl([json.dumps(batch)])
        events = list(parse_jsonl(path))
        assert len(events) == 3

    def test_skips_malformed_json_line(self) -> None:
        good_batch = _make_batch(_make_message())
        path = _write_jsonl(["NOT VALID JSON", json.dumps(good_batch)])
        events = list(parse_jsonl(path))
        assert len(events) == 1

    def test_skips_malformed_event_message(self) -> None:
        batch = {"logEvents": [{"id": "bad", "message": "NOT JSON"}]}
        path = _write_jsonl([json.dumps(batch)])
        events = list(parse_jsonl(path))
        assert len(events) == 0

    def test_yields_correct_fields(self) -> None:
        batch = _make_batch(_make_message("claude_code.api_request", {"k": "v"}))
        path = _write_jsonl([json.dumps(batch)])
        event = list(parse_jsonl(path))[0]
        assert event["event_id"] == "evt-0"
        assert event["body"] == "claude_code.api_request"
        assert event["attributes"] == {"k": "v"}
        assert event["resource"] == {"os.type": "linux"}
        assert event["scope_version"] == "1.0.0"

    def test_empty_file_yields_nothing(self) -> None:
        path = _write_jsonl([])
        assert list(parse_jsonl(path)) == []


class TestParseBatch:
    def test_extracts_event_id_from_log_event(self) -> None:
        batch = _make_batch(_make_message())
        events = list(_parse_batch(batch))
        assert events[0]["event_id"] == "evt-0"

    def test_handles_empty_log_events_array(self) -> None:
        assert list(_parse_batch({"logEvents": []})) == []
        assert list(_parse_batch({})) == []


class TestParseEventMessage:
    def test_returns_none_for_invalid_json(self) -> None:
        assert _parse_event_message("not json") is None
        assert _parse_event_message("") is None

    def test_extracts_body_and_attributes(self) -> None:
        msg = _make_message("test.body", {"a": 1})
        result = _parse_event_message(msg)
        assert result["body"] == "test.body"
        assert result["attributes"] == {"a": 1}
