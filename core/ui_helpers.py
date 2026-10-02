"""Small, testable formatting and upload helpers for the single-page UI."""

from datetime import datetime
from pathlib import Path

from core.markdown_renderer import METRIC_LABELS
from models.schemas import ExperimentComparison, ExperimentFacts, ExperimentRun, ParseResult, SoftwareAnalysis


EXPERIMENT_SUFFIXES = {".csv", ".json"}
SOFTWARE_SUFFIXES = {".txt", ".log", ".md"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def experiment_reportable(result: ParseResult) -> bool:
    """A partial parse is usable only when validated runs survive without record errors."""

    return result.status in {"success", "partial"} and bool(result.experiments) and not result.errors


def group_experiments(runs: list[ExperimentRun], limitations: list[str] | None = None) -> list[ExperimentFacts]:
    """Group metric scopes by experiment identity; keep a sweep as one dataset."""

    groups: dict[tuple[str, str | None, int | None], list[list[ExperimentRun]]] = {}
    sweep = []
    for run in runs:
        if run.metric_scope == "threshold_sweep":
            sweep.append(run)
        else:
            copies = groups.setdefault((run.name, run.split, run.seed), [[]])
            target = next((copy for copy in copies if all(
                existing.metric_scope != run.metric_scope for existing in copy)), None)
            if target is None:
                target = []
                copies.append(target)
            target.append(run)
    facts = [ExperimentFacts(experiments=items, limitations=limitations or [])
             for copies in groups.values() for items in copies]
    if sweep:
        facts.append(ExperimentFacts(profile="threshold_sweep", experiments=sweep,
                                     limitations=limitations or []))
    return facts


def report_disabled_reason(facts: object, configured: bool, *, has_upload: bool,
                           diagnostic: bool = False, comparison_mode: bool = False) -> str | None:
    if diagnostic and facts is None:
        return "当前诊断文件没有标准模型指标"
    if not has_upload:
        return "请先上传有效实验文件或测试日志"
    if facts is None:
        return "对比模式需要两个兼容实验" if comparison_mode else "请选择一个实验或有效分析数据"
    if not configured:
        return "请先配置 API"
    return None


def validate_upload(filename: str, size: int, allowed: set[str]) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise ValueError("仅支持 " + "、".join(sorted(allowed)) + " 文件")
    if size > MAX_UPLOAD_BYTES:
        raise ValueError("单个文件不能超过 10 MB")
    return suffix


def comparison_rows(comparison: ExperimentComparison) -> list[dict[str, str]]:
    rows = []
    for name, delta in comparison.deltas.items():
        ratio = delta.percentage_points is not None
        rows.append({
            "指标": METRIC_LABELS.get(name, name),
            "Baseline": f"{delta.baseline_value * 100:.2f}%" if ratio else f"{delta.baseline_value:.2f}",
            "Current": f"{delta.current_value * 100:.2f}%" if ratio else f"{delta.current_value:.2f}",
            "变化": f"{delta.percentage_points:+.2f} pp" if ratio else f"{delta.absolute_delta:+.2f}",
        })
    return rows


def analysis_result(analysis: SoftwareAnalysis) -> dict[str, object]:
    result: dict[str, object] = {"Framework": analysis.framework, "解析状态": analysis.parse_status}
    if summary := analysis.test_summary:
        result.update({"Unit": summary.unit, "Total": summary.total, "Passed": summary.passed,
                       "Skipped": summary.skipped, "Failed": summary.failed})
    if static := analysis.static_analysis:
        result.update({"Errors": static.errors, "Warnings": static.warnings, "Infos": static.infos})
    return result


def build_download_filename(now: datetime | None = None, extension: str = "md") -> str:
    if extension not in {"md", "html"}:
        raise ValueError("不支持的下载格式")
    return f"projectlens_report_{(now or datetime.now()).strftime('%Y%m%d_%H%M%S')}.{extension}"
