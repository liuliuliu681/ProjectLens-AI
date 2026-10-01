"""Parse explicitly supported CSV/JSON experiment structures."""

import math
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from core.experiment_profiles import (
    KNOWN_METADATA, REQUIRED_METRICS, SCOPED_ALIASES, STANDARD_ALIASES,
    SWEEP_COLUMNS, identify_profile,
)
from core.file_loader import FileLoadError, load_file
from models.schemas import ExperimentRun, MetricSet, ParseResult


RATIO_METRICS = frozenset({"precision", "recall", "f1", "map50", "map50_95"})
ALL_METRIC_FIELDS = frozenset(
    field for aliases in (STANDARD_ALIASES, *SCOPED_ALIASES.values())
    for names in aliases.values() for field in names
)


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


def _sweep_records(data: Any) -> list[dict[str, Any]]:
    rows = data.to_dict(orient="records") if isinstance(data, pd.DataFrame) else data.get("all_rows")
    if not isinstance(rows, list):
        raise ValueError("阈值扫描的 all_rows 必须是列表")
    split = data.get("split") if isinstance(data, dict) else None
    records = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not SWEEP_COLUMNS <= row.keys():
            raise ValueError(f"阈值扫描第 {index} 行缺少明确字段")
        model, threshold = row["model"], row["threshold"]
        try:
            numeric_threshold = float(threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"阈值扫描第 {index} 行的 threshold 无效") from exc
        if not isinstance(model, str) or not model.strip() or not math.isfinite(numeric_threshold) or not 0 <= numeric_threshold <= 1:
            raise ValueError(f"阈值扫描第 {index} 行的 model 或 threshold 无效")
        records.append({
            "name": f"{model.strip()} @ threshold={str(threshold).strip()}",
            "split": split,
            "metrics": {metric: row[metric] for metric in REQUIRED_METRICS["threshold_sweep"]},
        })
    return records


def _metric_values(fields: dict[str, Any], aliases: dict[str, tuple[str, ...]], label: str,
                   warnings: list[str]) -> tuple[dict[str, float], bool]:
    values = {}
    incomplete = False
    for metric, source_names in aliases.items():
        present = [name for name in source_names if name in fields and not _is_missing(fields[name])]
        if len(present) > 1:
            warnings.append(f"{label}: 重复指标 {metric}（{', '.join(present)}），按明确别名优先级使用 {present[0]}")
            incomplete = True
        if not present:
            continue
        try:
            values[metric] = (normalize_ratio(fields[present[0]]) if metric in RATIO_METRICS
                              else _normalize_non_ratio(fields[present[0]]))
        except ValueError as exc:
            warnings.append(f"{label} 的 {present[0]}: {exc}")
            incomplete = True
    return values, incomplete


def _parse_record(record: Any, index: int, profile: str, warnings: list[str],
                  errors: list[str], infos: list[str]) -> tuple[list[ExperimentRun], bool]:
    label = f"第 {index} 条实验"
    if not isinstance(record, dict):
        errors.append(f"{label}: 必须是对象")
        return [], True
    name = record.get("name", record.get("experiment"))
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{label}: 缺少有效的 name 或 experiment")
        return [], True
    name = name.strip()
    nested = record.get("metrics")
    if nested is not None and not isinstance(nested, dict):
        errors.append(f"{label} ({name}): metrics 必须是对象")
        return [], True
    fields = {key: value for key, value in record.items()
              if key not in {"name", "experiment", "split", "seed", "metrics"}}
    if nested:
        fields.update(nested)

    ignored = [key for key in fields if key in KNOWN_METADATA]
    if ignored:
        infos.append(f"{label} ({name}): 忽略 {len(ignored)} 个已知配置字段")
    unknown = [key for key, value in fields.items()
               if key not in ALL_METRIC_FIELDS and key not in KNOWN_METADATA
               and (isinstance(value, (int, float)) or key.startswith(("mask_", "box_")))]
    if unknown:
        warnings.append(f"{label} ({name}): 未识别的数值或指标字段 {', '.join(unknown)}")

    if profile == "threshold_sweep":
        scopes = ("threshold_sweep",)
    else:
        scopes = tuple(scope for scope, aliases in SCOPED_ALIASES.items()
                       if any(field in fields for names in aliases.values() for field in names))
        if any(field in fields for names in STANDARD_ALIASES.values() for field in names):
            scopes = ("generic", *scopes)
        if not scopes:
            scopes = ("generic",)

    runs = []
    incomplete = False
    for scope in scopes:
        aliases = STANDARD_ALIASES if scope in {"generic", "threshold_sweep"} else SCOPED_ALIASES[scope]
        scope_label = f"{label} ({name}, {scope})"
        values, invalid = _metric_values(fields, aliases, scope_label, warnings)
        missing = [metric for metric in REQUIRED_METRICS[scope] if metric not in values]
        if missing:
            warnings.append(f"{scope_label}: 缺失指标 {', '.join(missing)}")
        incomplete |= invalid or bool(missing)
        try:
            runs.append(ExperimentRun(name=name, split=record.get("split"), seed=record.get("seed"),
                                      metric_scope=scope, metrics=MetricSet(**values)))
        except ValidationError as exc:
            errors.append(f"{scope_label}: 实验元数据无效: {exc}")
            incomplete = True
    return runs, incomplete


def parse_experiments(data: Any) -> ParseResult:
    """Parse loaded data into scoped experiment runs and diagnostic status."""

    profile = identify_profile(data)
    if profile == "instance_diagnostic":
        summaries = data["model_summaries"]
        if not isinstance(summaries, dict):
            return ParseResult(status="unrecognized", profile=profile, errors=["model_summaries 必须是对象"])
        return ParseResult(
            status="partial", profile=profile,
            infos=[f"已识别实例诊断文件：{len(summaries)} 个模型"],
            warnings=["当前没有可用于标准模型对比的完整 P/R/F1/mAP 指标；诊断 recall 未映射为标准 recall"],
        )
    try:
        if profile == "threshold_sweep":
            records = _sweep_records(data)
        elif profile == "multiseed_summary":
            records = list(data["raw_summaries"].values())
        else:
            records = _records(data)
    except ValueError as exc:
        return ParseResult(status="unrecognized", profile=profile, errors=[str(exc)])
    if not records:
        return ParseResult(status="unrecognized", profile=profile, errors=["没有实验数据行"])

    runs: list[ExperimentRun] = []
    warnings: list[str] = []
    errors: list[str] = []
    infos: list[str] = []
    if profile == "threshold_sweep":
        infos.append(f"已识别阈值扫描：{len(records)} 个模型阈值点；仅含 Precision、Recall、F1，无 mAP")
        source_rows = data.to_dict(orient="records") if isinstance(data, pd.DataFrame) else data["all_rows"]
        extra_columns = set().union(*(row.keys() for row in source_rows)) - SWEEP_COLUMNS
        if extra_columns:
            warnings.append(f"阈值扫描存在未支持字段: {', '.join(sorted(extra_columns))}")
    elif profile == "yolo_segmentation":
        infos.append("已识别 YOLO segmentation summary；mask、box 与类别 mask 指标分别保存")
    elif profile == "multiseed_summary":
        infos.append(f"已识别多随机种子 summary：{len(records)} 个原始实验")
    incomplete = bool(warnings)
    for index, record in enumerate(records, start=1):
        parsed, partial = _parse_record(record, index, profile, warnings, errors, infos)
        runs.extend(parsed)
        incomplete |= partial
    if not runs:
        return ParseResult(status="unrecognized", profile=profile, infos=infos, warnings=warnings, errors=errors)
    return ParseResult(status="partial" if incomplete or errors else "success", profile=profile,
                       experiments=runs, infos=infos, warnings=warnings, errors=errors)


def parse_file(path: str | Path) -> ParseResult:
    """Load and parse a CSV or JSON file without exposing input errors."""

    if Path(path).suffix.lower() not in {".csv", ".json"}:
        return ParseResult(status="unrecognized", errors=["不支持该实验数据文件类型；仅支持 .csv 和 .json"])
    try:
        return parse_experiments(load_file(path))
    except FileLoadError as exc:
        return ParseResult(status="unrecognized", errors=[str(exc)])
