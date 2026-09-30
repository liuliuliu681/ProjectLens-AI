from datetime import datetime

import pytest

from core.calculator import compare_experiments
from core.ui_helpers import (
    EXPERIMENT_SUFFIXES, MAX_UPLOAD_BYTES, analysis_result, build_download_filename,
    comparison_rows, validate_upload,
)
from models.schemas import ExperimentRun, MetricSet, SoftwareAnalysis, TestSummary as _TestSummary


def test_upload_validation():
    assert validate_upload("example.JSON", 100, EXPERIMENT_SUFFIXES) == ".json"
    with pytest.raises(ValueError):
        validate_upload("program.exe", 100, EXPERIMENT_SUFFIXES)
    with pytest.raises(ValueError, match="10 MB"):
        validate_upload("data.csv", MAX_UPLOAD_BYTES + 1, EXPERIMENT_SUFFIXES)


def test_comparison_rows_use_calculator_result():
    baseline = ExperimentRun(name="B0", metrics=MetricSet(recall=0.42))
    current = ExperimentRun(name="C1", metrics=MetricSet(recall=0.5909090909090909))
    rows = comparison_rows(compare_experiments(baseline, current))
    assert rows == [{"指标": "Recall", "Baseline": "42.00%", "Current": "59.09%", "变化": "+17.09 pp"}]


def test_software_unit_and_skips_are_retained():
    analysis = SoftwareAnalysis(parse_status="success", framework="flutter",
                                test_summary=_TestSummary(unit="test", total=257, passed=242, failed=0, skipped=15))
    result = analysis_result(analysis)
    assert (result["Unit"], result["Total"], result["Passed"], result["Skipped"]) == ("test", 257, 242, 15)


def test_download_name():
    assert build_download_filename(datetime(2026, 9, 30, 22, 30)) == "projectlens_report_20260930_223000.md"
