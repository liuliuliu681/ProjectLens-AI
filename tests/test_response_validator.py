import json

import pytest

from core.response_validator import ReportValidationError, validate_report_draft


VALID = {"progress": ["完成解析"], "findings": [], "issues": [], "risks": [], "next_steps": []}


def test_standard_json():
    draft = validate_report_draft(json.dumps(VALID))
    assert draft.progress == ["完成解析"]
    assert draft.risks == []


def test_json_code_fence():
    draft = validate_report_draft("```json\n" + json.dumps(VALID) + "\n```")
    assert draft.progress == ["完成解析"]


@pytest.mark.parametrize("raw", [
    "not json", "", "  ", "[]", "{}",
    json.dumps({**VALID, "progress": "not a list"}),
    json.dumps({**VALID, "progress": [3]}),
    json.dumps({**VALID, "extra": "unexpected"}),
    "解释：\n" + json.dumps(VALID),
    json.dumps(VALID) + "\n额外说明",
])
def test_invalid_responses_are_rejected(raw):
    with pytest.raises(ReportValidationError):
        validate_report_draft(raw)
