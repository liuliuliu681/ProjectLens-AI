"""Validate the limited JSON format expected from the LLM."""

import json
import re

from pydantic import ValidationError

from models.schemas import ReportDraft


FENCE = re.compile(r"^```(?:json)?\s*\n([\s\S]*?)\n```$", re.IGNORECASE)


class ReportValidationError(ValueError):
    """The LLM response is not a usable ReportDraft."""


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
