"""Validate the limited JSON format expected from the LLM."""

import json
import re

from pydantic import ValidationError

from models.schemas import ReportDraft


FENCE = re.compile(r"^```(?:json)?\s*\n([\s\S]*?)\n```$", re.IGNORECASE)


class ReportValidationError(ValueError):
    """The LLM response is not a usable ReportDraft."""


SINGLE_COMPARISON = re.compile(
    r"相比.{0,20}(?:基线|Baseline|模型)|优于.{0,20}模型|"
    r"(?:提升|下降|增加|减少).{0,20}(?:百分点|\bpp\b)|"
    r"较.{0,20}(?:提升|下降)", re.IGNORECASE)
EXPERIMENT_NUMBER = re.compile(r"(?<![A-Za-z_])\b\d+(?:\.\d+)?\b|\d+(?:\.\d+)?\s*(?:%|百分点|\bpp\b)", re.IGNORECASE)


def _draft_prose(draft: ReportDraft) -> list[str]:
    return [*(draft.progress), *(draft.findings), *(draft.issues), *(draft.risks),
            *(draft.next_steps), draft.summary or ""]


def validate_experiment_draft_numbers(draft: ReportDraft) -> None:
    """Keep all experiment quantities in the deterministic Renderer."""

    if any(EXPERIMENT_NUMBER.search(item) for item in _draft_prose(draft)):
        raise ReportValidationError("实验报告解释部分包含应由程序渲染的数值")


def validate_single_experiment_draft(draft: ReportDraft) -> None:
    """Reject comparison claims when no baseline was supplied."""

    if any(SINGLE_COMPARISON.search(item) for item in _draft_prose(draft)):
        raise ReportValidationError("单实验报告包含未验证的比较结论")
    validate_experiment_draft_numbers(draft)


def validate_report_draft(raw_text: str) -> ReportDraft:
    """Remove only an outer JSON fence, then strictly validate one object."""

    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ReportValidationError("LLM 响应为空")
    content = raw_text.strip()
    match = FENCE.fullmatch(content)
    if match:
        content = match.group(1).strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ReportValidationError(f"LLM 响应不是合法 JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ReportValidationError("LLM 响应顶层必须是 JSON 对象")
    try:
        return ReportDraft.model_validate(data)
    except ValidationError as exc:
        raise ReportValidationError(f"LLM 响应不符合 ReportDraft: {exc}") from exc
