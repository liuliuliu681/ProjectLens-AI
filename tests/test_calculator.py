import pytest

from core.calculator import compare_experiments
from models.schemas import ExperimentRun, MetricSet


def run(name, **metrics):
    return ExperimentRun(name=name, metrics=MetricSet(**metrics))


def test_recall_absolute_points_and_relative_change():
    result = compare_experiments(run("baseline", recall=0.5213), run("current", recall=0.6922))
    delta = result.deltas["recall"]
    assert delta.baseline_value == pytest.approx(0.5213)
    assert delta.current_value == pytest.approx(0.6922)
    assert delta.absolute_delta == pytest.approx(0.1709)
    assert delta.percentage_points == pytest.approx(17.09)
    assert delta.relative_percent == pytest.approx(32.78, abs=0.01)


def test_zero_baseline():
    delta = compare_experiments(run("A", recall=0), run("B", recall=0.2)).deltas["recall"]
    assert delta.absolute_delta == pytest.approx(0.2)
    assert delta.percentage_points == pytest.approx(20)
    assert delta.relative_percent is None


def test_missing_metric_is_not_compared():
    result = compare_experiments(run("A", recall=0.5), run("B", precision=0.6))
    assert result.deltas == {}


def test_decrease_and_equal():
    result = compare_experiments(run("A", recall=0.7, f1=0.5), run("B", recall=0.6, f1=0.5))
    assert result.deltas["recall"].percentage_points == pytest.approx(-10)
    assert result.deltas["recall"].relative_percent == pytest.approx(-100 / 7)
    assert result.deltas["f1"].absolute_delta == pytest.approx(0)


def test_non_ratio_has_no_percentage_points():
    delta = compare_experiments(run("A", loss=2), run("B", loss=1)).deltas["loss"]
    assert delta.absolute_delta == pytest.approx(-1)
    assert delta.percentage_points is None
    assert delta.relative_percent == pytest.approx(-50)


def test_comparison_rejects_mixed_metric_scopes_and_splits():
    mask = ExperimentRun(name="A", split="val", metric_scope="mask", metrics=MetricSet(recall=0.5))
    box = ExperimentRun(name="B", split="val", metric_scope="box", metrics=MetricSet(recall=0.6))
    test_mask = ExperimentRun(name="C", split="test", metric_scope="mask", metrics=MetricSet(recall=0.7))
    with pytest.raises(ValueError, match="指标口径"):
        compare_experiments(mask, box)
    with pytest.raises(ValueError, match="split"):
        compare_experiments(mask, test_mask)
