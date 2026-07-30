from __future__ import annotations

import json
import re
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
WALKING_SKELETON_GUIDE = Path(__file__).resolve().parents[2] / "docs" / "walking-skeleton.md"


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


@pytest.mark.parametrize("scenario", MANIFEST["teaching_scenarios"], ids=lambda case: case["id"])
@pytest.mark.parametrize(
    ("direction", "path_key"),
    [("command", "command_path"), ("event", "event_path")],
)
def test_teaching_scenario_validates_every_physical_line(
    scenario: dict[str, Any], direction: str, path_key: str
) -> None:
    fixture = (FIXTURE_ROOT / scenario[path_key]).read_bytes()

    assert fixture.endswith(b"\n")
    assert b"\r" not in fixture
    lines = fixture.removesuffix(b"\n").split(b"\n")
    assert lines

    parser = parse_command_line if direction == "command" else parse_event_line
    results = [parser(line) for line in lines]

    assert all(not isinstance(result, ProtocolParseFailure) for result in results)


def test_walking_skeleton_guide_ndjson_blocks_match_teaching_scenarios_exactly() -> None:
    guide = WALKING_SKELETON_GUIDE.read_text(encoding="utf-8")
    documented_blocks = re.findall(r"```ndjson\n(.*?)```", guide, flags=re.DOTALL)
    documented_fixture_blocks = re.findall(
        r"<!-- fixture: ([^\n]+) -->\n```ndjson\n(.*?)```", guide, flags=re.DOTALL
    )
    fixture_blocks = [
        (
            scenario[path_key],
            (FIXTURE_ROOT / scenario[path_key]).read_text(encoding="utf-8"),
        )
        for scenario in MANIFEST["teaching_scenarios"]
        for path_key in ("command_path", "event_path")
    ]

    assert [block for _path, block in documented_fixture_blocks] == documented_blocks
    assert documented_fixture_blocks == fixture_blocks


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
