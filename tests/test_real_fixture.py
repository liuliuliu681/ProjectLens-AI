"""Acceptance test for anonymized research results."""

from pathlib import Path

import pytest

from core.calculator import compare_experiments
from core.experiment_parser import parse_file


FIXTURE = Path(__file__).parent / "fixtures" / "real_experiments.json"


def test_real_experiment_comparison() -> None:
    result = parse_file(FIXTURE)
    assert result.status == "success", (result.warnings, result.errors)
    assert not result.warnings
    assert not result.errors
    assert len(result.experiments) == 2

    baseline, current = result.experiments
    assert baseline.name == "B0_rgb_baseline"
    assert current.name == "C1_rgbd_dual_p3p4"
    assert baseline.split == current.split == "test"
    assert baseline.seed == current.seed == 42

    comparison = compare_experiments(baseline, current)
    assert comparison.deltas["recall"].percentage_points == pytest.approx(17.0909090909)
    assert comparison.deltas["f1"].percentage_points == pytest.approx(1.9906745759)
    assert comparison.deltas["map50"].percentage_points == pytest.approx(5.9813436605)
