from pathlib import Path

import pytest

from core.config import LLMConfig, load_llm_config, resolve_llm_config, save_llm_config


def test_missing_env_and_save(tmp_path: Path):
    path = tmp_path / ".env"
    assert load_llm_config(path) == LLMConfig()
    config = resolve_llm_config(LLMConfig(), api_key="new-secret", base_url="https://api.example/v1/",
                                model="model-a", timeout="30")
    save_llm_config(config, path)
    assert path.exists()
    assert load_llm_config(path) == config
    assert "LLM_API_KEY=" in path.read_text(encoding="utf-8")


def test_existing_key_preserved_and_fields_changed(tmp_path: Path):
    path = tmp_path / ".env"
    original = LLMConfig("old-secret", "https://old.example/v1", "old-model", 30)
    save_llm_config(original, path)
    saved = load_llm_config(path)
    updated = resolve_llm_config(saved, api_key="", base_url="https://new.example/v1",
                                 model="new-model", timeout="45")
    save_llm_config(updated, path)
    reloaded = load_llm_config(path)
    assert reloaded.api_key == "old-secret"
    assert reloaded.base_url == "https://new.example/v1"
    assert reloaded.model == "new-model"
    assert reloaded.timeout == 45
    assert "old-secret" not in repr(reloaded)


def test_new_key_overwrites_old(tmp_path: Path):
    path = tmp_path / ".env"
    save_llm_config(LLMConfig("old-secret", "https://api.example/v1", "model", 30), path)
    updated = resolve_llm_config(load_llm_config(path), api_key="new-secret",
                                 base_url="https://api.example/v1", model="model", timeout=30)
    save_llm_config(updated, path)
    assert load_llm_config(path).api_key == "new-secret"


@pytest.mark.parametrize("timeout", ["bad", "0", "-1", "nan", "inf"])
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="Timeout"):
        resolve_llm_config(LLMConfig("key"), api_key="", base_url="https://api.example/v1",
                           model="model", timeout=timeout)


def test_env_example_has_no_secret():
    text = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
    assert text.splitlines() == ["LLM_API_KEY=", "LLM_BASE_URL=", "LLM_MODEL=", "LLM_TIMEOUT=30"]
