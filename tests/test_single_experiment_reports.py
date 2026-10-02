"""Single experiment reports use parsed facts and never invent comparisons."""

import json
from pathlib import Path

import pytest

from core.calculator import compare_experiments
from core.experiment_parser import parse_experiments, parse_file
from core.markdown_renderer import render_markdown
from core.prompt_builder import PromptBuilder
from core.response_validator import (
    ReportValidationError, validate_experiment_draft_numbers, validate_single_experiment_draft,
)
from core.ui_helpers import experiment_reportable, group_experiments, report_disabled_reason
from models.schemas import ExperimentFacts, ExperimentRun, MetricSet, ReportDraft


FIXTURES = Path(__file__).parent / "fixtures"


def draft(**kwargs):
    values = dict(progress=["本轮完成了模型评估"], findings=["已记录各指标口径"],
                  issues=[], risks=["需要更多随机种子验证"], next_steps=["继续验证"],
                  summary="已完成当前实验的指标记录。")
    values.update(kwargs)
    return ReportDraft(**values)


def test_multi_scope_summary_becomes_one_logical_experiment():
    parsed = parse_file(FIXTURES / "yolo_c2_valid_summary.json")
    groups = group_experiments(parsed.experiments)
    assert len(groups) == 1
    facts = groups[0]
    assert (facts.experiments[0].name, facts.experiments[0].split, facts.experiments[0].seed) == (
        "C2_rgbd_gated_p3p4", "val", 42)
    assert {item.metric_scope for item in facts.experiments} == {
        "mask", "box", "mask_bone_spike", "mask_rib"}


@pytest.mark.parametrize("style", ["research", "short"])
def test_single_report_prompt_and_renderer(style):
    facts = group_experiments(parse_file(FIXTURES / "yolo_c2_valid_summary.json").experiments)[0]
    system, user = PromptBuilder().build(style, facts)
    payload = json.loads(user.split("[已验证事实]\n", 1)[1].split("\n\n[用户补充说明", 1)[0])
    assert payload["profile"] == "single"
    assert len(payload["experiments"]) == 4
    assert "没有 Baseline" in system
    report = render_markdown(style, facts, draft())
    assert "C2_rgbd_gated_p3p4" in report
    if style == "short":
        assert "mask_bone_spike" in report and "mask_rib" in report
    else:
        assert "Bone Spike Mask" in report and "Rib Mask" in report
    assert "Baseline" not in report and " pp" not in report
    if style == "research":
        assert "| Recall | 54.21% |" in report
        assert "Split：val" in report and "Seed：42" in report


def test_single_report_rejects_invented_comparison():
    facts = group_experiments(parse_file(FIXTURES / "yolo_c2_valid_summary.json").experiments)[0]
    bad = draft(findings=["相比基线提升 17.09 pp，优于另一模型"])
    with pytest.raises(ReportValidationError):
        validate_single_experiment_draft(bad)
    with pytest.raises(ReportValidationError):
        render_markdown("research", facts, bad)


def test_llm_numeric_claims_are_rejected_for_experiment_reports():
    for summary in ("Recall 为 59.09%", "建议阈值 0.03", "seed 42 的结果"):
        with pytest.raises(ReportValidationError):
            validate_experiment_draft_numbers(draft(summary=summary))


def test_original_comparison_still_uses_calculator():
    runs = parse_file(FIXTURES / "real_experiments.json").experiments
    comparison = compare_experiments(*runs)
    assert comparison.deltas["recall"].percentage_points == pytest.approx(17.0909090909)
    assert "+17.09 pp" in render_markdown("research", comparison, draft())


def test_threshold_sweep_can_be_summarized_without_map():
    parsed = parse_file(FIXTURES / "rib_threshold_sweep_sample.csv")
    facts = group_experiments(parsed.experiments)[0]
    assert facts.profile == "threshold_sweep"
    assert len(facts.experiments) == 45
    system, _ = PromptBuilder().build("short", facts)
    report = render_markdown("short", facts, draft())
    assert "不得补造 mAP" in system
    assert "45 个阈值点" in report
    assert "mAP50" not in report


def test_safe_partial_is_reportable_and_diagnostic_is_not():
    result = parse_file(FIXTURES / "rib_instance_diagnostic_sample.json")
    assert result.status == "partial" and not result.experiments
    assert group_experiments(result.experiments) == []
    assert not experiment_reportable(result)
    assert report_disabled_reason(None, True, has_upload=False, diagnostic=True) == "当前诊断文件没有标准模型指标"
    source = json.loads((FIXTURES / "yolo_c2_valid_summary.json").read_text(encoding="utf-8"))
    source.pop("mask_f1")
    partial = parse_experiments(source)
    assert partial.status == "partial" and experiment_reportable(partial)
    facts = group_experiments(partial.experiments, partial.warnings)[0]
    assert "缺失指标 f1" in render_markdown("research", facts, draft())


def test_single_facts_reject_mixed_identity_and_duplicate_scope():
    left = ExperimentRun(name="C1", split="test", seed=42, metric_scope="mask",
                         metrics=MetricSet(recall=0.5))
    right = ExperimentRun(name="C2", split="test", seed=42, metric_scope="mask",
                          metrics=MetricSet(recall=0.6))
    with pytest.raises(ValueError):
        ExperimentFacts(experiments=[left, right])
    assert len(group_experiments([left, left])) == 2


def test_disabled_reasons_are_specific():
    assert "上传" in report_disabled_reason(None, True, has_upload=False)
    assert "两个兼容实验" in report_disabled_reason(None, True, has_upload=True, comparison_mode=True)
    assert "API" in report_disabled_reason(object(), False, has_upload=True)
    assert report_disabled_reason(object(), True, has_upload=True) is None
