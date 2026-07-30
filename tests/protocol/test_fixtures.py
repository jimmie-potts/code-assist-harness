from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from code_assist_harness.protocol import (
    CommandLineReader,
    EventLineReader,
    ProtocolParseErrorCode,
    ProtocolParseFailure,
    parse_command_line,
    parse_event_line,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "protocol" / "fixtures" / "v1"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", MANIFEST["valid"], ids=lambda case: case["id"])
def test_shared_valid_fixture(case: dict[str, Any]) -> None:
    fixture = (FIXTURE_ROOT / case["path"]).read_bytes()

    assert case["format"] == "ndjson_line"
    assert fixture.endswith(b"\n")
    assert not fixture.endswith(b"\r\n")
    assert fixture.count(b"\n") == 1

    parser = parse_command_line if case["direction"] == "command" else parse_event_line
    result = parser(fixture[:-1])

    assert not isinstance(result, ProtocolParseFailure)
    assert result.type == case["type"]


@pytest.mark.parametrize("case", MANIFEST["invalid"], ids=lambda case: case["id"])
def test_shared_invalid_fixture_has_the_declared_classification(case: dict[str, Any]) -> None:
    fixture = (FIXTURE_ROOT / case["path"]).read_bytes()
    expected = ProtocolParseErrorCode(case["classification"])

    if case["format"] == "ndjson_stream":
        reader = CommandLineReader() if case["direction"] == "command" else EventLineReader()
        results = [*reader.feed(fixture), *reader.finish()]
        assert len(results) == 1
        result = results[0]
    else:
        assert case["format"] == "ndjson_line"
        assert fixture.endswith(b"\n")
        parser = parse_command_line if case["direction"] == "command" else parse_event_line
        result = parser(fixture[:-1])

    assert isinstance(result, ProtocolParseFailure)
    assert result.code is expected


def test_fixture_manifest_documents_the_implemented_protocol_version_and_timestamp() -> None:
    assert MANIFEST["protocol_version"] == 1
    assert MANIFEST["timestamp_format"] == "YYYY-MM-DDTHH:mm:ss.SSSZ"
