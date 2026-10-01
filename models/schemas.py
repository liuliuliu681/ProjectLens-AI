"""Validated internal representation of experiments and comparisons."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MetricSet(BaseModel):
    """Ratios use 0..1; absent measurements use None."""

    model_config = ConfigDict(extra="forbid")

    precision: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    recall: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    f1: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    map50: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    map50_95: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    loss: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    parameters: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    gflops: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ExperimentRun(BaseModel):
    """One named experiment with its available measurements."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    split: str | None = None
    seed: int | None = None
    metric_scope: Literal["generic", "mask", "box", "mask_bone_spike", "mask_rib", "threshold_sweep"] = "generic"
    metrics: MetricSet


class MetricDelta(BaseModel):
    """Difference for one metric present in both experiments."""

    baseline_value: float
    current_value: float
    absolute_delta: float
    percentage_points: float | None = None
    relative_percent: float | None = None


class ExperimentComparison(BaseModel):
    """Comparison of a selected baseline and current experiment."""

    baseline: ExperimentRun
    current: ExperimentRun
    deltas: dict[str, MetricDelta]


class ParseResult(BaseModel):
    """Parser outcome with actionable diagnostics."""

    status: Literal["success", "partial", "unrecognized"]
    profile: str | None = None
    experiments: list[ExperimentRun] = Field(default_factory=list)
    infos: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TestSummary(BaseModel):
    """Explicit test counts with their original counting unit."""

    unit: Literal["test", "test_group", "unknown"]
    total: int | None = Field(default=None, ge=0)
    passed: int | None = Field(default=None, ge=0)
    failed: int | None = Field(default=None, ge=0)
    skipped: int | None = Field(default=None, ge=0)


class StaticAnalysisSummary(BaseModel):
    """Counts reported by or extracted from static analyzer output."""

    errors: int | None = Field(default=None, ge=0)
    warnings: int | None = Field(default=None, ge=0)
    infos: int | None = Field(default=None, ge=0)


class FailedItem(BaseModel):
    """Failure details explicitly present in a log."""

    name: str = Field(min_length=1)
    message: str | None = None
    expected: str | None = None
    actual: str | None = None


class SoftwareAnalysis(BaseModel):
    """Validated facts extracted from one software test or analyze log."""

    type: Literal["software_analysis"] = "software_analysis"
    framework: Literal["flutter", "godot", "generic", "unknown"] = "unknown"
    test_summary: TestSummary | None = None
    static_analysis: StaticAnalysisSummary | None = None
    failed_items: list[FailedItem] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    parse_status: Literal["success", "partial", "unrecognized"]
    parse_warnings: list[str] = Field(default_factory=list)


class ProjectFacts(BaseModel):
    """Validated facts from existing experiment and software parsers."""

    model_config = ConfigDict(extra="forbid")

    comparison: ExperimentComparison | None = None
    software: list[SoftwareAnalysis] = Field(default_factory=list)


class ReportDraft(BaseModel):
    """LLM-authored analysis text; verified numbers remain in Python facts."""

    model_config = ConfigDict(extra="forbid", strict=True)

    progress: list[str]
    findings: list[str]
    issues: list[str]
    risks: list[str]
    next_steps: list[str]
    summary: str | None = None
