"""Acceptance tests for raw output from the real projects."""

from pathlib import Path

from core.test_parser import parse_test_file


FIXTURES = Path(__file__).parent / "fixtures"


def test_flutter_test_real() -> None:
    path = FIXTURES / "flutter_test_real.log"
    result = parse_test_file(path)
    assert result.parse_status == "success", result.parse_warnings
    assert result.framework == "flutter"
    assert result.test_summary.unit == "test"
    assert result.test_summary.total == 257
    assert result.test_summary.passed == 242
    assert result.test_summary.failed == 0
    assert result.test_summary.skipped == 15


def test_flutter_analyze_real() -> None:
    path = FIXTURES / "flutter_analyze_real.log"
    result = parse_test_file(path)
    assert result.parse_status == "success", result.parse_warnings
    assert result.framework == "flutter"
    assert result.static_analysis is not None
    assert result.static_analysis.errors == 0
    assert result.static_analysis.warnings == 0
    assert result.static_analysis.infos == 7


def test_godot_test_real() -> None:
    path = FIXTURES / "godot_test_real.log"
    result = parse_test_file(path)
    assert result.parse_status == "success", result.parse_warnings
    assert result.framework == "godot"
    assert result.test_summary.unit == "test_group"
    assert result.test_summary.total == 51
    assert result.test_summary.passed == 51
    assert result.test_summary.failed == 0
    assert result.failed_items == []
