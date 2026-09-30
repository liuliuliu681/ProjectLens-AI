from unittest.mock import Mock
import json

import pytest
import requests

from core.llm_client import (
    LLMAuthenticationError, LLMClient, LLMClientError,
    LLMRateLimitError, LLMResponseError, LLMServerError, LLMTimeoutError,
)
from core.markdown_renderer import render_markdown
from core.prompt_builder import PromptBuilder
from core.response_validator import validate_report_draft
from models.schemas import SoftwareAnalysis, TestSummary as _TestSummary


def client(**overrides):
    values = dict(api_key="test-secret", base_url="https://example.com/v1/", model="test-model", timeout=3)
    values.update(overrides)
    return LLMClient(**values)


def response(status=200, body=None, json_error=False):
    result = Mock(status_code=status)
    if json_error:
        result.json.side_effect = ValueError("invalid json")
    else:
        result.json.return_value = body if body is not None else {"choices": [{"message": {"content": "{\"ok\": true}"}}]}
    return result


def test_200_request_shape_and_base_url(monkeypatch):
    post = Mock(return_value=response())
    monkeypatch.setattr("core.llm_client.requests.post", post)
    output = client().generate("system", "user")
    assert output == '{"ok": true}'
    args, kwargs = post.call_args
    assert args[0] == "https://example.com/v1/chat/completions"
    assert kwargs["timeout"] == 3
    assert kwargs["json"] == {"model": "test-model", "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "user"}]}


@pytest.mark.parametrize("status", [400, 403, 404])
def test_client_errors_do_not_retry(status, monkeypatch):
    post = Mock(return_value=response(status))
    monkeypatch.setattr("core.llm_client.requests.post", post)
    with pytest.raises(LLMClientError, match=str(status)):
        client().generate("system", "user")
    assert post.call_count == 1


def test_401_does_not_retry_or_expose_key(monkeypatch):
    post = Mock(return_value=response(401))
    monkeypatch.setattr("core.llm_client.requests.post", post)
    with pytest.raises(LLMAuthenticationError, match="API authentication failed") as error:
        client().generate("system", "user")
    assert post.call_count == 1
    assert "test-secret" not in str(error.value)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_status_retries_at_most_three_times(status, monkeypatch):
    post = Mock(return_value=response(status))
    sleep = Mock()
    monkeypatch.setattr("core.llm_client.requests.post", post)
    monkeypatch.setattr("core.llm_client.time.sleep", sleep)
    expected = LLMRateLimitError if status == 429 else LLMServerError
    with pytest.raises(expected):
        client().generate("system", "user")
    assert post.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [0.5, 1.0]


def test_retry_then_success(monkeypatch):
    post = Mock(side_effect=[response(503), response(200)])
    sleep = Mock()
    monkeypatch.setattr("core.llm_client.requests.post", post)
    monkeypatch.setattr("core.llm_client.time.sleep", sleep)
    assert client().generate("system", "user") == '{"ok": true}'
    assert post.call_count == 2
    sleep.assert_called_once_with(0.5)


@pytest.mark.parametrize("failure,error_type", [(requests.Timeout, LLMTimeoutError), (requests.ConnectionError, LLMClientError)])
def test_network_errors_retry(failure, error_type, monkeypatch):
    post = Mock(side_effect=failure("network failure"))
    monkeypatch.setattr("core.llm_client.requests.post", post)
    monkeypatch.setattr("core.llm_client.time.sleep", Mock())
    with pytest.raises(error_type):
        client().generate("system", "user")
    assert post.call_count == 3


@pytest.mark.parametrize("body,json_error", [
    (None, True),
    ({}, False),
    ({"choices": []}, False),
    ({"choices": [{}]}, False),
    ({"choices": [{"message": {}}]}, False),
    ({"choices": [{"message": {"content": "  "}}]}, False),
])
def test_invalid_200_responses_fail_without_retry(body, json_error, monkeypatch):
    post = Mock(return_value=response(body=body, json_error=json_error))
    monkeypatch.setattr("core.llm_client.requests.post", post)
    with pytest.raises(LLMResponseError):
        client().generate("system", "user")
    assert post.call_count == 1


@pytest.mark.parametrize("timeout", ["bad", 0, -1, float("inf"), float("nan")])
def test_invalid_timeout(timeout):
    with pytest.raises(LLMClientError, match="LLM_TIMEOUT"):
        client(timeout=timeout)


def test_mocked_full_report_chain(monkeypatch):
    facts = SoftwareAnalysis(
        parse_status="success", framework="flutter",
        test_summary=_TestSummary(unit="test", total=257, passed=242, failed=0, skipped=15),
    )
    content = json.dumps({
        "progress": ["完成测试"], "findings": [], "issues": [],
        "risks": [], "next_steps": [],
    })
    monkeypatch.setattr("core.llm_client.requests.post", Mock(return_value=response(body={"choices": [{"message": {"content": content}}]})))
    system, user = PromptBuilder().build("engineering", facts)
    draft = validate_report_draft(client().generate(system, user))
    markdown = render_markdown("engineering", facts, draft)
    assert "完成测试" in markdown
    assert "Total: 257；Passed: 242；Failed: 0；Skipped: 15" in markdown
