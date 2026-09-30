"""Small local configuration store for the Streamlit form."""

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from core.paths import env_path


DEFAULT_ENV = env_path()


@dataclass(frozen=True)
class LLMConfig:
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    model: str = ""
    timeout: float = 30.0


def load_llm_config(path: Path = DEFAULT_ENV) -> LLMConfig:
    """Read local values without exposing the stored key to the UI."""

    values = dotenv_values(path) if path.exists() else {}
    raw_timeout = values.get("LLM_TIMEOUT") or "30"
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = float("nan")
    return LLMConfig(
        api_key=values.get("LLM_API_KEY") or "",
        base_url=values.get("LLM_BASE_URL") or "",
        model=values.get("LLM_MODEL") or "",
        timeout=timeout,
    )


def resolve_llm_config(
    saved: LLMConfig, *, api_key: str, base_url: str, model: str, timeout: str | float
) -> LLMConfig:
    """Validate current form values; a blank key preserves the saved key."""

    try:
        numeric_timeout = float(timeout)
    except (TypeError, ValueError) as exc:
        raise ValueError("Timeout 必须是正数") from exc
    if not math.isfinite(numeric_timeout) or numeric_timeout <= 0:
        raise ValueError("Timeout 必须是正的有限数")
    url = base_url.strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Base URL 必须是有效的 HTTP(S) 地址")
    selected_model = model.strip()
    if not selected_model:
        raise ValueError("Model 不能为空")
    selected_key = api_key.strip() or saved.api_key
    if not selected_key:
        raise ValueError("请先输入 API Key")
    return LLMConfig(selected_key, url, selected_model, numeric_timeout)


def save_llm_config(config: LLMConfig, path: Path = DEFAULT_ENV) -> None:
    """Atomically save only the four supported settings to the local .env."""

    values = {
        "LLM_API_KEY": config.api_key,
        "LLM_BASE_URL": config.base_url,
        "LLM_MODEL": config.model,
        "LLM_TIMEOUT": str(int(config.timeout)) if float(config.timeout).is_integer() else str(config.timeout),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text("".join(f"{key}={json.dumps(value, ensure_ascii=False)}\n" for key, value in values.items()), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
