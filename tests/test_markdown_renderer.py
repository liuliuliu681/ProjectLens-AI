import pytest

from core.calculator import compare_experiments
from core.markdown_renderer import render_markdown
from models.schemas import ExperimentRun, MetricSet, ReportDraft, SoftwareAnalysis, StaticAnalysisSummary, TestSummary as _TestSummary


def draft(**overrides):
    values = dict(progress=["已完成一轮实验"], findings=["观察到召回变化"], issues=[], risks=["仍需复验"], next_steps=["增加随机种子"])
    values.update(overrides)
    return ReportDraft(**values)


def comparison():
    baseline = ExperimentRun(name="B0", metrics=MetricSet(recall=0.42, f1=0.5827866346542556, map50=0.5401886384256683))
    current = ExperimentRun(name="C1", metrics=MetricSet(recall=0.5909090909090909, f1=0.6026933804129154, map50=0.6000020750308102))
    return compare_experiments(baseline, current)


def test_research_table_and_sections():
    markdown = render_markdown("research", comparison(), draft())
    assert "| Recall | 42.00% | 59.09% | +17.09 pp |" in markdown
    assert "| F1 | 58.28% | 60.27% | +1.99 pp |" in markdown
    assert "| mAP50 | 54.02% | 60.00% | +5.98 pp |" in markdown
    assert "## 风险与局限" in markdown
    assert "仍需复验" in markdown


def test_llm_false_number_does_not_replace_python_table():
    markdown = render_markdown("research", comparison(), draft(findings=["Recall 提升了 99.99 个百分点"]))
    table = markdown.split("## 数据结果\n", 1)[1].split("## 本轮进展", 1)[0]
    assert "+17.09 pp" in table
    assert "99.99" not in table
    assert "99.99" in markdown


def test_engineering_test_unit_and_skips():
    flutter = SoftwareAnalysis(parse_status="success", framework="flutter", test_summary=_TestSummary(unit="test", total=257, passed=242, failed=0, skipped=15))
    godot = SoftwareAnalysis(parse_status="success", framework="godot", test_summary=_TestSummary(unit="test_group", total=51, passed=51, failed=0))
    analyze = SoftwareAnalysis(parse_status="success", framework="flutter", static_analysis=StaticAnalysisSummary(errors=0, warnings=0, infos=7))
    markdown = render_markdown("engineering", [flutter, analyze, godot], draft())
    assert "Tests — Total: 257；Passed: 242；Failed: 0；Skipped: 15" in markdown
    assert "Test groups — Total: 51；Passed: 51；Failed: 0" in markdown
    assert "Errors: 0；Warnings: 0；Infos: 7" in markdown
    assert "## 本轮完成" in markdown
    assert "## 下一步" in markdown


def test_short_summary_keeps_python_facts():
    markdown = render_markdown("short", comparison(), draft(summary="本轮取得进展。"))
    assert "本轮取得进展。" in markdown
    assert "+17.09 pp" in markdown
    assert "## 数据结果" not in markdown


def test_research_decline_uses_signed_percentage_points():
    baseline = ExperimentRun(name="B0", metrics=MetricSet(recall=0.6))
    current = ExperimentRun(name="C1", metrics=MetricSet(recall=0.5488))
    markdown = render_markdown("research", compare_experiments(baseline, current), draft())
    assert "-5.12 pp" in markdown


def test_report_labels_scoped_metrics_and_split():
    baseline = ExperimentRun(name="C1", split="val", metric_scope="mask_rib", metrics=MetricSet(recall=0.1))
    current = ExperimentRun(name="C2", split="val", metric_scope="mask_rib", metrics=MetricSet(recall=0.2))
    facts = compare_experiments(baseline, current)
    assert "指标口径：mask_rib；数据划分：val" in render_markdown("research", facts, draft())
    assert "指标口径 mask_rib" in render_markdown("short", facts, draft(summary="本轮取得进展。"))


def test_mismatched_fact_type_is_rejected():
    analysis = SoftwareAnalysis(parse_status="success", framework="flutter")
    with pytest.raises(ValueError):
        render_markdown("research", analysis, draft())
