"""Parse explicitly supported CSV/JSON experiment structures."""

import math
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from core.file_loader import FileLoadError, load_file
from models.schemas import ExperimentRun, MetricSet, ParseResult


ALIASES: dict[str, str] = {
    "precision": "precision", "Precision": "precision", "P": "precision",
    "recall": "recall", "Recall": "recall", "R": "recall",
    "f1": "f1", "F1": "f1", "f1_score": "f1",
    "map50": "map50", "mAP50": "map50", "mAP_50": "map50",
    "map50_95": "map50_95", "mAP50-95": "map50_95",
    "mAP50_95": "map50_95", "mAP50:95": "map50_95",
    "loss": "loss", "parameters": "parameters", "gflops": "gflops",
    "mask_precision": "precision", "mask_recall": "recall", "mask_f1": "f1",
    "mask_map50": "map50", "mask_map50_95": "map50_95",
}
RATIO_METRICS = ("precision", "recall", "f1", "map50", "map50_95")


def normalize_ratio(value: Any) -> float:
    """Convert a ratio, 0..100 number, or explicit percent string to 0..1."""

    if isinstance(value, bool):
        raise ValueError("布尔值不是有效指标")
    percent = isinstance(value, str) and value.strip().endswith("%")
    raw = value.strip()[:-1].strip() if percent else value
    try:
        number = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无效比例指标: {value!r}") from exc
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise ValueError(f"比例指标超出 0~100 范围: {value!r}")
    return number / 100 if percent or number > 1 else number


def _normalize_non_ratio(value: Any) -> float:
    if isinstance(value, bool) or (isinstance(value, str) and "%" in value):
        raise ValueError(f"无效非比例指标: {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无效非比例指标: {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"非比例指标必须是非负有限数: {value!r}")
    return number


def _is_missing(value: Any) -> bool:
    if value is None or isinstance(value, str) and not value.strip():
        return True
    return isinstance(value, float) and math.isnan(value)


def _records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, pd.DataFrame):
        return data.to_dict(orient="records")
    if isinstance(data, dict):
        if "experiments" in data:
            records = data["experiments"]
            if not isinstance(records, list):
                raise ValueError("experiments 必须是实验对象列表")
            return records
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError("JSON 顶层必须是实验对象、实验对象列表或 experiments 列表")


def parse_experiments(data: Any) -> ParseResult:
    """Parse loaded data into experiment runs and diagnostic status."""

    try:
        records = _records(data)
    except ValueError as exc:
        return ParseResult(status="unrecognized", errors=[str(exc)])
    if not records:
        return ParseResult(status="unrecognized", errors=["没有实验数据行"])

    runs: list[ExperimentRun] = []
    warnings: list[str] = []
    errors: list[str] = []
    incomplete = False
    for index, record in enumerate(records, start=1):
        label = f"第 {index} 条实验"
        if not isinstance(record, dict):
            errors.append(f"{label}: 必须是对象")
            continue
        name = record.get("name", record.get("experiment"))
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}: 缺少有效的 name 或 experiment")
            continue
        name = name.strip()
        nested = record.get("metrics")
        if nested is not None and not isinstance(nested, dict):
            errors.append(f"{label} ({name}): metrics 必须是对象")
            continue
        fields = {
            key: value for key, value in record.items()
            if key not in {"name", "experiment", "split", "seed", "metrics"}
        }
        if nested is not None:
            fields.update(nested)
        values: dict[str, float] = {}
        seen: set[str] = set()
        for source_name, raw_value in fields.items():
            metric_name = ALIASES.get(source_name)
            if metric_name is None:
                warnings.append(f"{label} ({name}): 未识别字段 {source_name!r}")
                continue
            if metric_name in seen:
                warnings.append(f"{label} ({name}): 重复指标 {metric_name}，保留第一个值")
                incomplete = True
                continue
            seen.add(metric_name)
            if _is_missing(raw_value):
                continue
            try:
                values[metric_name] = (
                    normalize_ratio(raw_value) if metric_name in RATIO_METRICS
                    else _normalize_non_ratio(raw_value)
                )
            except ValueError as exc:
                warnings.append(f"{label} ({name}) 的 {source_name}: {exc}")
                incomplete = True
        missing = [metric for metric in RATIO_METRICS if metric not in values]
        if missing:
            warnings.append(f"{label} ({name}): 缺失指标 {', '.join(missing)}")
            incomplete = True
        try:
            runs.append(ExperimentRun(
                name=name,
                split=record.get("split"),
                seed=record.get("seed"),
                metrics=MetricSet(**values),
            ))
        except ValidationError as exc:
            errors.append(f"{label} ({name}): 实验元数据无效: {exc}")

    if not runs:
        return ParseResult(status="unrecognized", warnings=warnings, errors=errors)
    return ParseResult(
        status="partial" if incomplete or errors else "success",
        experiments=runs, warnings=warnings, errors=errors,
    )


def parse_file(path: str | Path) -> ParseResult:
    """Load and parse a CSV or JSON file without exposing input errors."""

    if Path(path).suffix.lower() not in {".csv", ".json"}:
        return ParseResult(status="unrecognized", errors=["不支持该实验数据文件类型；仅支持 .csv 和 .json"])
    try:
        return parse_experiments(load_file(path))
    except FileLoadError as exc:
        return ParseResult(status="unrecognized", errors=[str(exc)])
