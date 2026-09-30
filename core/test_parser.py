"""Deterministic parsing of explicit software test and analyzer output."""

import re
from pathlib import Path

from core.file_loader import FileLoadError, load_file
from models.schemas import FailedItem, SoftwareAnalysis, StaticAnalysisSummary, TestSummary as _TestSummary


FLUTTER_PROGRESS = re.compile(
    r"^\s*\d{2}:\d{2}(?::\d{2})?\s+\+(\d+)(?:\s+-(\d+))?(?:\s+~(\d+))?:\s*"
    r"(All tests passed!|Some tests failed\.)\s*$",
    re.IGNORECASE,
)
ALL_PASSED = re.compile(r"^\s*All tests passed!\s*$", re.IGNORECASE)
NO_ISSUES = re.compile(r"^\s*No issues found!\s*(?:\([^\n]*\))?\s*$", re.IGNORECASE)
DIAGNOSTIC = re.compile(r"^\s*(error|warning|info)\s*[•-]\s*(.+?)\s*$", re.IGNORECASE)
COUNT_FIELD = re.compile(r"^\s*(Test Groups|Tests|Total|Passed|Failed)\s*:\s*(\d+)\s*$", re.IGNORECASE)
COUNT_FIRST = re.compile(r"^\s*(\d+)\s+(test groups|tests|passed|failed)\s*$", re.IGNORECASE)
ANALYZE_FIELD = re.compile(r"^\s*(Errors|Warnings|Infos)\s*:\s*(\d+)\s*$", re.IGNORECASE)
ANALYZE_PAIR = re.compile(r"^\s*(\d+)\s+errors?\s*[,/]\s*(\d+)\s+warnings?\s*$", re.IGNORECASE)
FAILED_ITEM = re.compile(r"^\s*FAILED:\s*(\S.*?)\s*$", re.IGNORECASE)
GODOT_RESULT = re.compile(
    r"^\s*([A-Z][A-Z0-9_]*)_TESTS_(OK|FAILED)(?:\s+failures=(\d+))?\s*$",
    re.IGNORECASE,
)
EXPECTED = re.compile(r"^\s*Expected:\s*(.*)$", re.IGNORECASE)
ACTUAL = re.compile(r"^\s*Actual:\s*(.*)$", re.IGNORECASE)


def _failed_items(lines: list[str]) -> list[FailedItem]:
    items: list[FailedItem] = []
    current: FailedItem | None = None
    messages: list[str] = []

    def finish() -> None:
        if current is not None:
            current.message = "\n".join(messages) or None
            items.append(current)

    for line in lines:
        if COUNT_FIELD.fullmatch(line):
            finish()
            current = None
            messages = []
            continue
        failure = FAILED_ITEM.fullmatch(line)
        if failure:
            finish()
            current = FailedItem(name=failure.group(1))
            messages = []
            continue
        if current is None:
            continue
        if not line.strip() or COUNT_FIELD.fullmatch(line) or COUNT_FIRST.fullmatch(line):
            finish()
            current = None
            messages = []
            continue
        expected = EXPECTED.fullmatch(line)
        actual = ACTUAL.fullmatch(line)
        if expected:
            current.expected = expected.group(1)
        elif actual:
            current.actual = actual.group(1)
        else:
            messages.append(line.strip())
    finish()
    return items


def _validate_counts(summary: _TestSummary, warnings: list[str]) -> str:
    if summary.total is None or summary.passed is None or summary.failed is None:
        return "partial"
    if summary.passed + summary.failed + (summary.skipped or 0) != summary.total:
        warnings.append("Reported total does not equal passed + failed + skipped.")
        return "partial"
    return "success"


def _parse_analyze(lines: list[str]) -> SoftwareAnalysis | None:
    no_issues = any(NO_ISSUES.fullmatch(line) for line in lines)
    diagnostics = [match for line in lines if (match := DIAGNOSTIC.fullmatch(line))]
    fields: dict[str, int] = {}
    for line in lines:
        field = ANALYZE_FIELD.fullmatch(line)
        if field:
            fields[field.group(1).lower()] = int(field.group(2))
        pair = ANALYZE_PAIR.fullmatch(line)
        if pair:
            fields["errors"] = int(pair.group(1))
            fields["warnings"] = int(pair.group(2))
    if not no_issues and not diagnostics and not fields:
        return None

    counts: dict[str, int | None] = (
        {"errors": 0, "warnings": 0, "infos": 0}
        if no_issues or diagnostics else {"errors": None, "warnings": None, "infos": None}
    )
    error_messages: list[str] = []
    for diagnostic in diagnostics:
        severity = diagnostic.group(1).lower() + "s"
        counts[severity] = (counts[severity] or 0) + 1
        if severity == "errors":
            error_messages.append(diagnostic.group(2))
    warnings: list[str] = []
    if no_issues and (diagnostics or any(fields.values())):
        warnings.append("No issues found conflicts with reported diagnostics.")
    for kind, reported in fields.items():
        if diagnostics and reported != counts[kind]:
            warnings.append(f"Reported {kind} does not equal listed diagnostics.")
        counts[kind] = reported

    summary = StaticAnalysisSummary(**counts)
    return SoftwareAnalysis(
        framework="flutter", static_analysis=summary,
        error_messages=error_messages,
        parse_status="partial" if warnings or summary.errors is None or summary.warnings is None else "success",
        parse_warnings=warnings,
    )


def _parse_flutter_test(lines: list[str]) -> SoftwareAnalysis | None:
    progress = next((match for line in reversed(lines) if (match := FLUTTER_PROGRESS.fullmatch(line))), None)
    if progress:
        passed = int(progress.group(1))
        failed = int(progress.group(2)) if progress.group(2) is not None else None
        skipped = int(progress.group(3)) if progress.group(3) is not None else 0
        all_passed = progress.group(4).lower().startswith("all")
        if all_passed and failed is None:
            failed = 0
        summary = _TestSummary(
            unit="test", total=passed + failed + skipped if failed is not None else None,
            passed=passed, failed=failed, skipped=skipped,
        )
        warnings: list[str] = []
        if all_passed and failed != 0 or not all_passed and failed == 0:
            warnings.append("Flutter result text conflicts with failure count.")
        status = _validate_counts(summary, warnings)
        if warnings:
            status = "partial"
        return SoftwareAnalysis(
            framework="flutter", test_summary=summary,
            failed_items=_failed_items(lines), parse_status=status, parse_warnings=warnings,
        )
    if any(ALL_PASSED.fullmatch(line) for line in lines):
        return SoftwareAnalysis(
            framework="flutter",
            test_summary=_TestSummary(unit="test", failed=0),
            parse_status="partial",
            parse_warnings=["Flutter reports all tests passed without a test count."],
        )
    return None


def _parse_godot_results(lines: list[str]) -> SoftwareAnalysis | None:
    """Count only explicit result lines emitted by existing Godot scripts."""

    results = [match for line in lines if (match := GODOT_RESULT.fullmatch(line))]
    if not results:
        return None
    passed = sum(match.group(2).upper() == "OK" for match in results)
    failed = len(results) - passed
    warnings: list[str] = []
    if any(match.group(2).upper() == "OK" and match.group(3) not in {None, "0"} for match in results):
        warnings.append("A Godot OK marker reports nonzero failures.")
    engine_starts = sum(line.startswith("Godot Engine v") for line in lines)
    if engine_starts and engine_starts != len(results):
        warnings.append("Godot invocations do not equal explicit test group results.")
    return SoftwareAnalysis(
        framework="godot",
        test_summary=_TestSummary(unit="test_group", total=len(results), passed=passed, failed=failed),
        failed_items=_failed_items(lines),
        parse_status="partial" if warnings else "success",
        parse_warnings=warnings,
    )


def _parse_explicit_summary(lines: list[str]) -> SoftwareAnalysis | None:
    counts: dict[str, int] = {}
    unit = "unknown"
    warnings: list[str] = []
    godot_format = False
    for line in lines:
        match = COUNT_FIELD.fullmatch(line)
        count_first = COUNT_FIRST.fullmatch(line) if match is None else None
        if match:
            label, value = match.group(1).lower(), int(match.group(2))
        elif count_first:
            value, label = int(count_first.group(1)), count_first.group(2).lower()
        else:
            continue
        if label in {"test groups", "tests", "total"}:
            key = "total"
            next_unit = "test_group" if label == "test groups" else "test"
            if unit != "unknown" and unit != next_unit:
                warnings.append("Conflicting test counting units.")
            unit = next_unit
            godot_format = godot_format or label == "test groups"
        else:
            key = label
        if key in counts and counts[key] != value:
            warnings.append(f"Conflicting reported {key} values.")
        else:
            counts[key] = value
    items = _failed_items(lines)
    if not counts and not items:
        return None
    summary = _TestSummary(unit=unit, **counts)
    status = _validate_counts(summary, warnings)
    if warnings:
        status = "partial"
    return SoftwareAnalysis(
        framework="godot" if godot_format else "generic",
        test_summary=summary, failed_items=items,
        parse_status=status, parse_warnings=warnings,
    )


def parse_test_log(text: str) -> SoftwareAnalysis:
    """Extract only explicit facts, applying fixed format precedence."""

    if not isinstance(text, str) or not text.strip():
        return SoftwareAnalysis(parse_status="unrecognized", parse_warnings=["日志为空"])
    lines = text.replace("\r", "\n").splitlines()
    for parser in (_parse_analyze, _parse_flutter_test, _parse_godot_results, _parse_explicit_summary):
        result = parser(lines)
        if result is not None:
            return result
    return SoftwareAnalysis(parse_status="unrecognized", parse_warnings=["未识别明确的测试或静态分析格式"])


def parse_test_file(path: str | Path) -> SoftwareAnalysis:
    """Read a TXT, LOG, or MD file and parse its software testing facts."""

    if Path(path).suffix.lower() not in {".txt", ".log", ".md"}:
        return SoftwareAnalysis(parse_status="unrecognized", parse_warnings=["测试日志仅支持 .txt、.log 和 .md"])
    try:
        content = load_file(path)
    except FileLoadError as exc:
        return SoftwareAnalysis(parse_status="unrecognized", parse_warnings=[str(exc)])
    return parse_test_log(content)
