"""Explicit shapes and metric scopes for supported experiment files."""

from typing import Any

import pandas as pd


STANDARD_ALIASES = {
    "precision": ("precision", "Precision", "P"),
    "recall": ("recall", "Recall", "R"),
    "f1": ("f1", "F1", "f1_score"),
    "map50": ("map50", "mAP50", "mAP_50"),
    "map50_95": ("map50_95", "mAP50-95", "mAP50_95", "mAP50:95"),
    "loss": ("loss",),
    "parameters": ("parameters",),
    "gflops": ("gflops",),
}
SCOPED_PREFIXES = ("mask", "box", "mask_bone_spike", "mask_rib")
SCOPED_ALIASES = {
    scope: {metric: (f"{scope}_{metric}",) for metric in ("precision", "recall", "f1", "map50", "map50_95")}
    for scope in SCOPED_PREFIXES
}
SCOPED_ALIASES["box"].pop("f1")  # The observed YOLO box summaries do not report F1.
REQUIRED_METRICS = {
    "generic": ("precision", "recall", "f1", "map50", "map50_95"),
    "mask": ("precision", "recall", "f1", "map50", "map50_95"),
    "box": ("precision", "recall", "map50", "map50_95"),
    "mask_bone_spike": ("precision", "recall", "f1", "map50", "map50_95"),
    "mask_rib": ("precision", "recall", "f1", "map50", "map50_95"),
    "threshold_sweep": ("precision", "recall", "f1"),
}
KNOWN_METADATA = frozenset({
    "model", "data", "epochs", "imgsz", "batch", "input", "channels", "fusion",
    "rgb_branch", "depth_branch", "ultralytics_version", "gate_input",
    "initial_gate", "valid_images", "class_mapping", "checkpoint",
})
SWEEP_COLUMNS = frozenset({
    "model", "threshold", "tp", "fp", "fn", "gt_total", "pred_total",
    "precision", "recall", "f1",
})


def identify_profile(data: Any) -> str:
    """Select only profiles with distinctive, explicit structural markers."""

    if isinstance(data, pd.DataFrame) and {"model", "threshold"} <= set(data.columns):
        return "threshold_sweep"
    if isinstance(data, dict):
        if {"diagnostic_thresholds", "model_summaries", "instance_rows"} <= data.keys():
            return "instance_diagnostic"
        if {"diagnostic_settings", "all_rows", "model_summaries"} <= data.keys():
            return "threshold_sweep"
        if "raw_summaries" in data and isinstance(data["raw_summaries"], dict):
            return "multiseed_summary"
        records = data.get("experiments", [data])
        if isinstance(records, list) and any(
            isinstance(record, dict) and any(
                field in record for aliases in SCOPED_ALIASES.values()
                for names in aliases.values() for field in names
            ) for record in records
        ):
            return "yolo_segmentation"
    return "standard"
