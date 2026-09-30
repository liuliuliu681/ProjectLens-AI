import json

import pytest

from core.experiment_parser import normalize_ratio, parse_experiments, parse_file


def test_single_experiment_csv(tmp_path):
    path = tmp_path / "single.csv"
    path.write_text("name,precision,recall,f1,map50,map50_95\nA,0.6,0.5,0.55,0.7,0.4\n", encoding="utf-8")
    result = parse_file(path)
    assert result.status == "success"
    assert result.experiments[0].metrics.recall == pytest.approx(0.5)


def test_multiple_experiments_and_changed_field_order(tmp_path):
    path = tmp_path / "multi.csv"
    path.write_text("map50,name,recall,precision,f1,map50_95\n70,A,52.13,62,61.19,40\n75.98,B,69.22,64,63.18,45\n", encoding="utf-8")
    result = parse_file(path)
    assert result.status == "success"
    assert [run.name for run in result.experiments] == ["A", "B"]
    assert result.experiments[1].metrics.map50 == pytest.approx(0.7598)


def test_field_aliases():
    result = parse_experiments({"name": "A", "P": "52.13%", "R": 0.6, "F1": 0.55, "mAP_50": 0.7, "mAP50:95": 0.4})
    assert result.status == "success"
    assert result.experiments[0].metrics.precision == pytest.approx(0.5213)


def test_flat_json(tmp_path):
    path = tmp_path / "flat.json"
    path.write_text(json.dumps({"name": "A", "recall": 0.5}), encoding="utf-8")
    result = parse_file(path)
    assert result.status == "partial"
    assert result.experiments[0].metrics.recall == pytest.approx(0.5)


def test_nested_json_multiple(tmp_path):
    path = tmp_path / "nested.json"
    path.write_text(json.dumps({"experiments": [{"name": "A", "metrics": {"recall": 0.5}}, {"name": "B", "metrics": {"recall": 0.6}}]}), encoding="utf-8")
    result = parse_file(path)
    assert len(result.experiments) == 2
    assert result.status == "partial"


def test_missing_metric_uses_none():
    result = parse_experiments({"name": "A", "P": 0.5})
    assert result.status == "partial"
    assert result.experiments[0].metrics.f1 is None
    assert any("缺失指标" in warning for warning in result.warnings)


def test_unknown_field_warning():
    result = parse_experiments({"name": "A", "mystery": 9})
    assert result.status == "partial"
    assert any("mystery" in warning for warning in result.warnings)


def test_invalid_metric_is_reported():
    result = parse_experiments({"name": "A", "recall": 101})
    assert result.status == "partial"
    assert result.experiments[0].metrics.recall is None
    assert any("recall" in warning for warning in result.warnings)


def test_unrecognized_structure():
    assert parse_experiments({"experiments": "wrong"}).status == "unrecognized"
    assert parse_experiments({"recall": 0.5}).status == "unrecognized"
    assert parse_experiments([]).status == "unrecognized"


@pytest.mark.parametrize("value,expected", [(0, 0), (1, 1), (0.5213, 0.5213), (52.13, 0.5213), (100, 1), ("52.13%", 0.5213)])
def test_normalize_ratio(value, expected):
    assert normalize_ratio(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", [-1, 101, "not a number", float("nan"), True])
def test_normalize_ratio_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        normalize_ratio(value)


def test_non_ratio_metrics_are_not_percent_normalized():
    result = parse_experiments({"name": "A", "loss": 52.13, "parameters": 100, "gflops": 2.5})
    metrics = result.experiments[0].metrics
    assert metrics.loss == pytest.approx(52.13)
    assert metrics.parameters == pytest.approx(100)
    assert metrics.gflops == pytest.approx(2.5)
