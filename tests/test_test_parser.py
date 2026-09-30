"""Tests for deterministic software log extraction."""

from pathlib import Path

import pytest

from core.file_loader import FileLoadError, load_file
from core.test_parser import parse_test_file, parse_test_log


@pytest.mark.parametrize("suffix", [".txt", ".log", ".md"])
def test_load_utf8_text(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"output{suffix}"
    path.write_text("Tests: 2\nPassed: 2\nFailed: 0", encoding="utf-8")
    assert load_file(path).startswith("Tests: 2")
    assert parse_test_file(path).test_summary.total == 2


def test_load_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "output.log"
    path.write_bytes(b"\xef\xbb\xbfTests: 2\nPassed: 2\nFailed: 0")
    assert load_file(path).startswith("Tests:")
    assert parse_test_file(path).parse_status == "success"


@pytest.mark.parametrize("content", ["", " \n\t "])
def test_empty_text_has_clear_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "empty.log"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(FileLoadError, match="为空"):
        load_file(path)
    assert parse_test_file(path).parse_status == "unrecognized"


def test_text_encoding_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.log"
    path.write_bytes(b"\xff\xfe")
    result = parse_test_file(path)
    assert result.parse_status == "unrecognized"
    assert result.parse_warnings


def test_flutter_all_passed() -> None:
    result = parse_test_log("00:12 +182: All tests passed!")
    assert result.framework == "flutter"
    assert result.parse_status == "success"
    assert result.test_summary.model_dump() == {"unit": "test", "total": 182, "passed": 182, "failed": 0, "skipped": 0}


def test_flutter_real_terminal_format_with_skips() -> None:
    result = parse_test_log("00:10 +242 ~15: All tests passed!")
    assert result.parse_status == "success"
    assert result.test_summary.total == 257
    assert result.test_summary.passed == 242
    assert result.test_summary.failed == 0
    assert result.test_summary.skipped == 15


@pytest.mark.parametrize("failed,passed", [(1, 181), (3, 179)])
def test_flutter_failures(failed: int, passed: int) -> None:
    result = parse_test_log(f"00:12 +{passed} -{failed}: Some tests failed.")
    assert result.parse_status == "success"
    assert result.test_summary.total == passed + failed
    assert result.test_summary.failed == failed


def test_flutter_all_passed_without_count_is_partial() -> None:
    result = parse_test_log("All tests passed!")
    assert result.parse_status == "partial"
    assert result.test_summary.total is None
    assert result.test_summary.passed is None
    assert result.test_summary.failed == 0


def test_flutter_conflicting_outcome_is_partial() -> None:
    result = parse_test_log("00:12 +5 -1: All tests passed!")
    assert result.parse_status == "partial"
    assert result.test_summary.failed == 1


def test_analyze_no_issues() -> None:
    result = parse_test_log("Analyzing app...\nNo issues found! (ran in 1.2s)")
    assert result.framework == "flutter"
    assert result.parse_status == "success"
    assert result.static_analysis.errors == 0
    assert result.static_analysis.warnings == 0


def test_analyze_explicit_zero_counts() -> None:
    result = parse_test_log("Errors: 0\nWarnings: 0")
    assert result.parse_status == "success"
    assert result.static_analysis.errors == 0
    assert result.static_analysis.warnings == 0


def test_analyze_one_reported_severity_is_partial() -> None:
    result = parse_test_log("Warnings: 1")
    assert result.parse_status == "partial"
    assert result.static_analysis.errors is None
    assert result.static_analysis.warnings == 1


@pytest.mark.parametrize("line,errors,warnings", [
    ("warning • unused variable • lib/main.dart:1:2 • unused_local_variable", 0, 1),
    ("error - undefined name - lib/main.dart:1:2 - undefined_identifier", 1, 0),
])
def test_analyze_single_diagnostic(line: str, errors: int, warnings: int) -> None:
    result = parse_test_log(f"Analyzing app...\n{line}")
    assert result.parse_status == "success"
    assert result.static_analysis.errors == errors
    assert result.static_analysis.warnings == warnings


def test_analyze_error_warning_and_info() -> None:
    result = parse_test_log(
        "error • broken symbol • lib/a.dart:1:2 • code\n"
        "warning • unused variable • lib/a.dart:2:2 • code\n"
        "info • style note • lib/a.dart:3:2 • code"
    )
    assert result.static_analysis.errors == 1
    assert result.static_analysis.warnings == 1
    assert result.static_analysis.infos == 1
    assert result.error_messages == ["broken symbol • lib/a.dart:1:2 • code"]


def test_analyze_explicit_pair() -> None:
    result = parse_test_log("1 error / 2 warnings")
    assert result.static_analysis.errors == 1
    assert result.static_analysis.warnings == 2


def test_analyze_conflicting_counts_are_preserved() -> None:
    result = parse_test_log("Warnings: 2\nwarning • one • lib/a.dart:1:2 • code")
    assert result.parse_status == "partial"
    assert result.static_analysis.warnings == 2
    assert result.parse_warnings


def test_godot_count_first_summary() -> None:
    result = parse_test_log("27 test groups\n26 passed\n1 failed")
    assert result.framework == "godot"
    assert result.parse_status == "success"
    assert result.test_summary.model_dump() == {"unit": "test_group", "total": 27, "passed": 26, "failed": 1, "skipped": None}


def test_godot_real_script_result_markers() -> None:
    result = parse_test_log(
        "Godot Engine v4.7.stable\nCORE_TESTS_OK\n"
        "Godot Engine v4.7.stable\nJOURNAL_UI_TESTS_OK failures=0\n"
        "Godot Engine v4.7.stable\nEXIT_CONFIRMATION_TESTS_FAILED failures=1"
    )
    assert result.framework == "godot"
    assert result.parse_status == "success"
    assert result.test_summary.unit == "test_group"
    assert result.test_summary.total == 3
    assert result.test_summary.passed == 2
    assert result.test_summary.failed == 1


def test_godot_missing_result_marker_is_partial() -> None:
    result = parse_test_log("Godot Engine v4.7.stable\nCORE_TESTS_OK\nGodot Engine v4.7.stable\nERROR: Test crashed")
    assert result.parse_status == "partial"
    assert result.test_summary.total == 1
    assert result.parse_warnings


def test_godot_case_and_spacing() -> None:
    result = parse_test_log(" 27   Test Groups \n 26   PASSED\n 1   FAILED ")
    assert result.parse_status == "success"
    assert result.test_summary.unit == "test_group"


def test_godot_colon_summary() -> None:
    result = parse_test_log("Test Groups: 27\nPassed: 26\nFailed: 1")
    assert result.framework == "godot"
    assert result.test_summary.total == 27


def test_godot_failed_item() -> None:
    result = parse_test_log(
        "27 test groups\n26 passed\n1 failed\n"
        "FAILED: exit_confirmation_text\nExpected: Exit?\nActual: Leave?\nText differed."
    )
    assert len(result.failed_items) == 1
    item = result.failed_items[0]
    assert item.name == "exit_confirmation_text"
    assert item.expected == "Exit?"
    assert item.actual == "Leave?"
    assert item.message == "Text differed."


def test_godot_partial_statistics() -> None:
    result = parse_test_log("Failed: 1")
    assert result.parse_status == "partial"
    assert result.test_summary.unit == "unknown"
    assert result.test_summary.total is None
    assert result.test_summary.passed is None
    assert result.test_summary.failed == 1
    assert result.failed_items == []


def test_generic_tests_summary() -> None:
    result = parse_test_log("Tests: 182\nPassed: 182\nFailed: 0")
    assert result.framework == "generic"
    assert result.test_summary.unit == "test"
    assert result.test_summary.total == 182
    assert result.parse_status == "success"


def test_generic_total_summary() -> None:
    result = parse_test_log("Total: 182\nPassed: 182\nFailed: 0")
    assert result.test_summary.unit == "test"
    assert result.parse_status == "success"


def test_conflicting_total_is_not_corrected() -> None:
    result = parse_test_log("Tests: 182\nPassed: 180\nFailed: 1")
    assert result.parse_status == "partial"
    assert result.test_summary.total == 182
    assert result.test_summary.passed == 180
    assert result.test_summary.failed == 1
    assert "Reported total does not equal passed + failed + skipped." in result.parse_warnings


@pytest.mark.parametrize("content", [
    "", "just ordinary text", "这次基本都过了，就一个弹窗文案有问题",
    "Version 27 had 26 fixes and 1 regression.", "looks good", "Some tests failed.",
])
def test_unrecognized_text(content: str) -> None:
    result = parse_test_log(content)
    assert result.parse_status == "unrecognized"
    assert result.test_summary is None


def test_unsupported_test_file(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text("{}", encoding="utf-8")
    assert parse_test_file(path).parse_status == "unrecognized"
