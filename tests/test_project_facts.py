from core.calculator import compare_experiments
from core.markdown_renderer import render_markdown
from core.prompt_builder import PromptBuilder
from models.schemas import (
    ExperimentRun, MetricSet, ProjectFacts, ReportDraft, SoftwareAnalysis,
    TestSummary as _TestSummary,
)


def test_combined_facts_reach_prompt_and_renderer():
    comparison = compare_experiments(
        ExperimentRun(name="B0", metrics=MetricSet(recall=0.42)),
        ExperimentRun(name="C1", metrics=MetricSet(recall=0.5909090909090909)),
    )
    software = SoftwareAnalysis(parse_status="success", framework="godot",
                                test_summary=_TestSummary(unit="test_group", total=51, passed=51, failed=0))
    facts = ProjectFacts(comparison=comparison, software=[software])
    _, user = PromptBuilder().build("engineering", facts, "本轮说明")
    assert '"comparison"' in user and '"software"' in user
    assert "本轮说明" in user
    draft = ReportDraft(progress=[], findings=[], issues=[], risks=[], next_steps=[])
    markdown = render_markdown("engineering", facts, draft)
    assert "+17.09 pp" in markdown
    assert "Test groups — Total: 51；Passed: 51" in markdown
