"""Regression tests for observed research result formats."""

import csv
import json
from collections import Counter
from pathlib import Path

import pytest
import pandas as pd

from core.experiment_parser import parse_experiments, parse_file


FIXTURES = Path(__file__).parent / "fixtures"


def test_yolo_summary_keeps_mask_box_and_class_scopes_separate():
    result = parse_file(FIXTURES / "yolo_c2_valid_summary.json")
    assert result.profile == "yolo_segmentation"
    assert result.status == "success"
    assert not result.warnings
    assert len(result.experiments) == 4
    scopes = {run.metric_scope: run for run in result.experiments}
    assert set(scopes) == {"mask", "box", "mask_bone_spike", "mask_rib"}
    assert all(run.name == "C2_rgbd_gated_p3p4" for run in scopes.values())
    assert all(run.split == "val" and run.seed == 42 for run in scopes.values())
    assert scopes["mask"].metrics.recall == pytest.approx(0.5421414033499763)
    assert scopes["mask"].metrics.map50 == pytest.approx(0.579766573295985)
    assert scopes["box"].metrics.map50 != scopes["mask"].metrics.map50
    assert scopes["box"].metrics.f1 is None
    assert scopes["mask_bone_spike"].metrics.f1 == pytest.approx(0.9394432116714683)
    assert scopes["mask_rib"].metrics.recall == pytest.approx(0.1)
    assert any("忽略" in info for info in result.infos)


def test_yolo_missing_real_metric_is_partial():
    data = json.loads((FIXTURES / "yolo_c2_valid_summary.json").read_text(encoding="utf-8"))
    data.pop("mask_f1")
    result = parse_experiments(data)
    assert result.status == "partial"
    assert any("mask" in warning and "f1" in warning for warning in result.warnings)


def test_threshold_sweep_rows_are_explicit_model_threshold_points():
    path = FIXTURES / "rib_threshold_sweep_sample.csv"
    result = parse_file(path)
    assert result.profile == "threshold_sweep"
    assert result.status == "success"
    assert len(result.experiments) == 45
    assert Counter(run.name.split(" @ ")[0] for run in result.experiments) == {"C1": 15, "C2": 15, "C21": 15}
    first = result.experiments[0]
    assert first.name == "C1 @ threshold=0.001"
    assert first.metric_scope == "threshold_sweep"
    assert first.split is None and first.seed is None
    assert first.metrics.precision == pytest.approx(0.008456659619450317)
    assert first.metrics.recall == pytest.approx(0.4)
    assert first.metrics.map50 is None
    assert not result.warnings


def test_threshold_sweep_requires_exact_columns_and_valid_threshold():
    with (FIXTURES / "rib_threshold_sweep_sample.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    rows[0]["threshold"] = "invalid"
    result = parse_experiments({"diagnostic_settings": {}, "model_summaries": {}, "all_rows": rows})
    assert result.status == "unrecognized"
    assert "threshold" in result.errors[0]
    incomplete = parse_experiments(pd.DataFrame([{"model": "C1", "threshold": 0.1, "precision": 0.5}]))
    assert incomplete.status == "unrecognized"
    assert len(incomplete.errors) == 1
    rows[0]["threshold"] = "0.001"
    rows[0]["new_metric"] = 0.75
    extra = parse_experiments({"diagnostic_settings": {}, "model_summaries": {}, "all_rows": rows})
    assert extra.status == "partial"
    assert "new_metric" in extra.warnings[0]


def test_instance_diagnostic_is_identified_without_fake_standard_metrics():
    result = parse_file(FIXTURES / "rib_instance_diagnostic_sample.json")
    assert result.profile == "instance_diagnostic"
    assert result.status == "partial"
    assert not result.experiments
    assert len(result.warnings) == 1
    assert "诊断 recall" in result.warnings[0]
    assert "3 个模型" in result.infos[0]


def test_multiseed_summary_uses_original_runs_not_aggregate_rows():
    data = {
        "experiment": "multi", "rows": [{"seed": 1, "overall_recall": 0.5}],
        "raw_summaries": {
            "1": {"experiment": "A", "split": "test", "seed": 1,
                  "mask_precision": 0.5, "mask_recall": 0.4, "mask_f1": 0.44,
                  "mask_map50": 0.3, "mask_map50_95": 0.2},
            "2": {"experiment": "A", "split": "val", "seed": 2,
                  "mask_precision": 0.6, "mask_recall": 0.5, "mask_f1": 0.54,
                  "mask_map50": 0.4, "mask_map50_95": 0.3},
        },
    }
    result = parse_experiments(data)
    assert result.profile == "multiseed_summary"
    assert result.status == "success"
    assert [(run.split, run.seed) for run in result.experiments] == [("test", 1), ("val", 2)]


def test_unsupported_structure_remains_unrecognized():
    assert parse_experiments({"model_summaries": {"C1": {"recall": 0.5}}}).status == "unrecognized"
