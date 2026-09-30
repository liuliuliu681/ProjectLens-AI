from datetime import datetime
from pathlib import Path

from core.calculator import compare_experiments
from core.experiment_parser import parse_file
from core.html_renderer import render_html
from core.markdown_renderer import render_markdown
from core.test_parser import parse_test_file
from models.schemas import ReportDraft


FIXTURES = Path(__file__).parent / "fixtures"
DRAFT = ReportDraft(progress=["本轮完成"], findings=["主要发现"], issues=["当前问题"],
                    risks=["风险与局限"], next_steps=["下一步建议"])


def test_research_html_is_standalone_and_escaped():
    runs = parse_file(FIXTURES / "real_experiments.json").experiments
    text = render_markdown("research", compare_experiments(*runs), DRAFT)
    page = render_html(text + "\n<script>alert(1)</script>", "research",
                       generated_at=datetime(2026, 9, 30, 10, 0))
    assert '<meta charset="utf-8">' in page
    assert "ProjectLens AI" in page and "2026-09-30 10:00:00" in page
    assert "+17.09 pp" in page and "+1.99 pp" in page and "+5.98 pp" in page
    assert "<table>" in page and "本轮进展" in page
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<link " not in page and "src=" not in page


def test_software_html_preserves_counts_and_units():
    flutter = parse_test_file(FIXTURES / "flutter_test_real.log")
    godot = parse_test_file(FIXTURES / "godot_test_real.log")
    page = render_html(render_markdown("engineering", [flutter, godot], DRAFT), "engineering")
    assert "Total: 257" in page and "Passed: 242" in page and "Skipped: 15" in page
    assert "Test groups — Total: 51" in page and "Passed: 51" in page


def test_html_redacts_secret_header_and_local_path():
    page = render_html("# 报告\n\nsecret-abc Authorization: Bearer token-x "
                       "LLM_API_KEY=hidden-token D:\\private\\data.log", "short",
                       secrets=("secret-abc",))
    for forbidden in ("secret-abc", "Authorization", "token-x", "hidden-token", "D:\\private"):
        assert forbidden not in page
