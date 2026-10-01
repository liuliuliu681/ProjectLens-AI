"""Assemble reports with deterministic facts and validated LLM prose."""

from core.prompt_builder import ReportType, StructuredFacts
from models.schemas import ExperimentComparison, MetricDelta, ProjectFacts, ReportDraft, SoftwareAnalysis


METRIC_LABELS = {
    "precision": "Precision", "recall": "Recall", "f1": "F1",
    "map50": "mAP50", "map50_95": "mAP50-95",
    "loss": "Loss", "parameters": "Parameters", "gflops": "GFLOPs",
}


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _points(value: float) -> str:
    return f"{value:+.2f} pp"


def _plain(value: float, signed: bool = False) -> str:
    return f"{value:+.2f}" if signed else f"{value:.2f}"


def _count(value: int | None) -> str:
    return str(value) if value is not None else "未提供"


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _section(title: str, items: list[str]) -> str:
    body = "\n".join(f"- {_one_line(item)}" for item in items) if items else "- 无明确内容"
    return f"## {title}\n\n{body}"


def _research_facts(comparison: ExperimentComparison) -> str:
    lines = [
        "## 数据结果", "",
        f"Baseline：{comparison.baseline.name}；Current：{comparison.current.name}",
        f"指标口径：{comparison.baseline.metric_scope}；数据划分：{comparison.baseline.split or '未提供'}", "",
        "| 指标 | Baseline | Current | 变化 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, delta in comparison.deltas.items():
        lines.append(_metric_row(name, delta))
    return "\n".join(lines)


def _metric_row(name: str, delta: MetricDelta) -> str:
    label = METRIC_LABELS.get(name, name)
    if delta.percentage_points is not None:
        baseline = _percent(delta.baseline_value)
        current = _percent(delta.current_value)
        change = _points(delta.percentage_points)
    else:
        baseline = _plain(delta.baseline_value)
        current = _plain(delta.current_value)
        change = _plain(delta.absolute_delta, signed=True)
    return f"| {label} | {baseline} | {current} | {change} |"


def _engineering_facts(analyses: list[SoftwareAnalysis]) -> str:
    lines = ["## 验证结果", ""]
    for analysis in analyses:
        lines.append(f"### {analysis.framework.title()}")
        lines.append("")
        lines.append(f"解析状态：{analysis.parse_status}")
        if summary := analysis.test_summary:
            unit = {"test": "Tests", "test_group": "Test groups", "unknown": "Unit unknown"}[summary.unit]
            lines.append(f"{unit} — Total: {_count(summary.total)}；Passed: {_count(summary.passed)}；Failed: {_count(summary.failed)}；Skipped: {_count(summary.skipped)}")
        if static := analysis.static_analysis:
            lines.append(f"Static analysis — Errors: {_count(static.errors)}；Warnings: {_count(static.warnings)}；Infos: {_count(static.infos)}")
        for item in analysis.failed_items:
            detail = [f"Failed item: {_one_line(item.name)}"]
            if item.expected is not None:
                detail.append(f"Expected: {_one_line(item.expected)}")
            if item.actual is not None:
                detail.append(f"Actual: {_one_line(item.actual)}")
            if item.message is not None:
                detail.append(f"Message: {_one_line(item.message)}")
            lines.append("；".join(detail))
        for message in analysis.error_messages:
            lines.append(f"Error: {_one_line(message)}")
        for warning in analysis.parse_warnings:
            lines.append(f"Parse warning: {_one_line(warning)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _short_facts(structured_facts: StructuredFacts) -> str:
    if isinstance(structured_facts, ProjectFacts):
        parts = []
        if structured_facts.comparison is not None:
            parts.append(_short_facts(structured_facts.comparison).removeprefix("已验证数据："))
        if structured_facts.software:
            parts.append(_short_facts(structured_facts.software).removeprefix("已验证数据："))
        return "已验证数据：" + "；".join(parts)
    if isinstance(structured_facts, ExperimentComparison):
        details = []
        for name, delta in structured_facts.deltas.items():
            change = _points(delta.percentage_points) if delta.percentage_points is not None else _plain(delta.absolute_delta, signed=True)
            details.append(f"{METRIC_LABELS.get(name, name)} {change}")
        return f"已验证数据：指标口径 {structured_facts.baseline.metric_scope}；" + "；".join(details)
    analyses = [structured_facts] if isinstance(structured_facts, SoftwareAnalysis) else structured_facts
    details = []
    for analysis in analyses:
        if summary := analysis.test_summary:
            unit = "tests" if summary.unit == "test" else "test groups" if summary.unit == "test_group" else "units"
            details.append(f"{analysis.framework}: {unit} {_count(summary.total)}，通过 {_count(summary.passed)}，失败 {_count(summary.failed)}，跳过 {_count(summary.skipped)}")
        if static := analysis.static_analysis:
            details.append(f"{analysis.framework} analyze: errors {_count(static.errors)}，warnings {_count(static.warnings)}，infos {_count(static.infos)}")
    return "已验证数据：" + "；".join(details)


def render_markdown(
    report_type: ReportType, structured_facts: StructuredFacts, draft: ReportDraft
) -> str:
    """Render factual sections only from Python models; prose only from ReportDraft."""

    if not isinstance(draft, ReportDraft):
        raise TypeError("draft 必须是已验证的 ReportDraft")
    if isinstance(structured_facts, ProjectFacts):
        if structured_facts.comparison is None and not structured_facts.software:
            raise ValueError("项目总结至少需要一项已验证事实")
        fact_sections = []
        if structured_facts.comparison is not None:
            fact_sections.append(_research_facts(structured_facts.comparison))
        if structured_facts.software:
            fact_sections.append(_engineering_facts(structured_facts.software))
        facts = "\n\n".join(fact_sections)
        research = structured_facts.comparison is not None
    elif isinstance(structured_facts, ExperimentComparison):
        facts = _research_facts(structured_facts)
        research = True
    elif isinstance(structured_facts, SoftwareAnalysis):
        facts = _engineering_facts([structured_facts])
        research = False
    elif isinstance(structured_facts, (list, tuple)) and structured_facts and all(
        isinstance(item, SoftwareAnalysis) for item in structured_facts
    ):
        facts = _engineering_facts(list(structured_facts))
        research = False
    else:
        raise TypeError("structured_facts 必须是已验证的事实模型")

    if report_type == "research":
        if not research:
            raise ValueError("科研报告需要 ExperimentComparison")
        sections = [
            "# 阶段实验报告", facts,
            _section("本轮进展", draft.progress),
            _section("主要发现", draft.findings),
            _section("当前问题", draft.issues),
            _section("风险与局限", draft.risks),
            _section("下一步建议", draft.next_steps),
        ]
    elif report_type == "engineering":
        if research and not isinstance(structured_facts, ProjectFacts):
            raise ValueError("工程报告需要 SoftwareAnalysis")
        sections = [
            "# 工程阶段报告", _section("本轮完成", draft.progress),
            facts, _section("验证说明", draft.findings),
            _section("当前问题", draft.issues),
            _section("风险", draft.risks),
            _section("下一步", draft.next_steps),
        ]
    elif report_type == "short":
        prose = draft.summary or " ".join(draft.progress + draft.findings + draft.issues + draft.risks + draft.next_steps)
        sections = ["# 简短总结", _one_line(prose), _short_facts(structured_facts)]
    else:
        raise ValueError(f"不支持的报告类型: {report_type}")
    return "\n\n".join(sections).rstrip() + "\n"
