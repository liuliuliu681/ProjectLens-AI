"""Run one real API check after configuring .env; no credentials are printed."""

from core.llm_client import LLMClient, LLMClientError
from core.markdown_renderer import render_markdown
from core.prompt_builder import PromptBuilder
from core.response_validator import ReportValidationError, validate_report_draft
from models.schemas import SoftwareAnalysis, TestSummary


def main() -> int:
    facts = SoftwareAnalysis(
        parse_status="success",
        framework="flutter",
        test_summary=TestSummary(unit="test", total=257, passed=242, failed=0, skipped=15),
    )
    try:
        system_prompt, user_prompt = PromptBuilder().build("engineering", facts)
        raw_response = LLMClient().generate(system_prompt, user_prompt)
        draft = validate_report_draft(raw_response)
        markdown = render_markdown("engineering", facts, draft)
    except (LLMClientError, ReportValidationError) as exc:
        print(f"Smoke test failed: {exc}")
        return 1
    if "Total: 257" not in markdown:
        print("Smoke test failed: deterministic facts missing from Markdown")
        return 1
    print("Smoke test passed: HTTP, content, JSON, Pydantic, Markdown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
