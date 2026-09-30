"""Small, testable formatting and upload helpers for the single-page UI."""

from datetime import datetime
from pathlib import Path

from core.markdown_renderer import METRIC_LABELS
from models.schemas import ExperimentComparison, SoftwareAnalysis


EXPERIMENT_SUFFIXES = {".csv", ".json"}
SOFTWARE_SUFFIXES = {".txt", ".log", ".md"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


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
