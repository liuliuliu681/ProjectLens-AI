"""Minimal OpenAI-compatible Chat Completions HTTP client."""

import math
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv
from core.paths import env_path


class LLMClientError(RuntimeError):
    """An LLM request or configuration failed."""


class LLMAuthenticationError(LLMClientError):
    """The API rejected the configured credentials."""


class LLMRateLimitError(LLMClientError):
    """The API rate limit persisted after retrying."""


class LLMServerError(LLMClientError):
    """The API server did not recover after retrying."""


class LLMTimeoutError(LLMClientError):
    """The API timed out after retrying."""


class LLMResponseError(LLMClientError):
    """The HTTP response did not contain usable assistant text."""


class LLMClient:
    """Send only system and user messages with bounded retries."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        load_dotenv(env_path())
        self.api_key = api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
        configured_url = base_url if base_url is not None else os.getenv("LLM_BASE_URL", "")
        self.model = model if model is not None else os.getenv("LLM_MODEL", "")
        raw_timeout = timeout if timeout is not None else os.getenv("LLM_TIMEOUT", "30")
        try:
            self.timeout = float(raw_timeout)
        except (TypeError, ValueError) as exc:
            raise LLMClientError("LLM_TIMEOUT 必须是正数") from exc
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise LLMClientError("LLM_TIMEOUT 必须是正的有限数")
        if not self.api_key or not self.model or not configured_url:
            raise LLMClientError("缺少 LLM_API_KEY、LLM_BASE_URL 或 LLM_MODEL 配置")
        self.base_url = configured_url.rstrip("/")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LLMClientError("LLM_BASE_URL 必须是有效的 HTTP(S) URL")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return assistant content, retrying only transient failures."""

        if not system_prompt.strip() or not user_prompt.strip():
            raise ValueError("system_prompt 和 user_prompt 不能为空")
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(3):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            except requests.Timeout as exc:
                if attempt == 2:
                    raise LLMTimeoutError("LLM API 请求超时（已尝试 3 次）") from exc
            except requests.ConnectionError as exc:
                if attempt == 2:
                    raise LLMClientError("LLM API 连接失败（已尝试 3 次）") from exc
            except requests.RequestException as exc:
                raise LLMClientError("LLM API 请求失败") from exc
            else:
                status = response.status_code
                if status == 401:
                    raise LLMAuthenticationError("API authentication failed")
                if status in {400, 403, 404}:
                    raise LLMClientError(f"LLM API 返回 HTTP {status}")
                if status == 429:
                    if attempt == 2:
                        raise LLMRateLimitError("LLM API 限流（已尝试 3 次）")
                elif status in {500, 502, 503, 504}:
                    if attempt == 2:
                        raise LLMServerError(f"LLM API 返回 HTTP {status}（已尝试 3 次）")
                elif status != 200:
                    raise LLMClientError(f"LLM API 返回 HTTP {status}")
                else:
                    return self._content(response)
            time.sleep(0.5 * 2**attempt)
        raise LLMClientError("LLM API 请求失败")

    @staticmethod
    def _content(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMResponseError("HTTP 200 响应不是 JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("choices"), list) or not body["choices"]:
            raise LLMResponseError("LLM 响应缺少非空 choices")
        choice = body["choices"][0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise LLMResponseError("LLM 响应缺少 message")
        content = choice["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("LLM 响应 content 为空")
        return content.strip()
