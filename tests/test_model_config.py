"""Tests for common/model_config.py (models.json resolution)."""
import json

import pytest

from common.model_config import FALLBACK_API_KEY_ENV, resolve_model

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
OPENROUTER_URL = "https://openrouter.ai/api/v1"


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({
        "default": {"provider": "gemini", "model": "gemini-3.6-flash"},
        "providers": {
            "gemini": {
                "base_url": GEMINI_URL,
                "api_key_env": "GOOGLE_API_KEY",
                "models": ["gemini-3.6-flash", "gemini-other"],
            },
            "openrouter": {
                "base_url": OPENROUTER_URL + "/",  # trailing slash on purpose
                "api_key_env": "OPENROUTER_API_KEY",
                "models": ["openrouter/free"],
            },
        },
    }))
    return str(path)


def test_provider_url_takes_key_env_from_matching_provider(config_path):
    assert resolve_model(config_path, model_name="m", provider_url=GEMINI_URL + "/") == (
        "m", GEMINI_URL + "/", "GOOGLE_API_KEY",
    )


def test_provider_url_without_matching_provider_falls_back(config_path):
    url = "https://api.example.com/v1"
    assert resolve_model(config_path, model_name="m", provider_url=url) == (
        "m", url, FALLBACK_API_KEY_ENV,
    )


def test_explicit_api_key_env_always_wins(config_path):
    _, _, key_env = resolve_model(
        config_path, model_name="m", provider_url=GEMINI_URL, api_key_env="MY_KEY"
    )
    assert key_env == "MY_KEY"
    _, _, key_env = resolve_model(config_path, provider="gemini", api_key_env="MY_KEY")
    assert key_env == "MY_KEY"


def test_provider_url_requires_model_name(config_path):
    with pytest.raises(ValueError, match="--model-name"):
        resolve_model(config_path, provider_url=GEMINI_URL)


def test_model_name_with_slash_is_passed_unchanged(config_path):
    assert resolve_model(config_path, provider="openrouter", model_name="openrouter/free") == (
        "openrouter/free", OPENROUTER_URL + "/", "OPENROUTER_API_KEY",
    )


def test_provider_alone_uses_its_first_model(config_path):
    assert resolve_model(config_path, provider="gemini") == (
        "gemini-3.6-flash", GEMINI_URL, "GOOGLE_API_KEY",
    )


def test_no_arguments_uses_default(config_path):
    assert resolve_model(config_path) == ("gemini-3.6-flash", GEMINI_URL, "GOOGLE_API_KEY")


def test_model_name_alone_uses_default_provider(config_path):
    assert resolve_model(config_path, model_name="gemini-other") == (
        "gemini-other", GEMINI_URL, "GOOGLE_API_KEY",
    )


def test_unlisted_model_is_not_rejected(config_path):
    model, _, _ = resolve_model(config_path, provider="gemini", model_name="not-in-the-list")
    assert model == "not-in-the-list"


def test_unknown_provider_lists_available_ones(config_path):
    with pytest.raises(ValueError, match="available: gemini, openrouter"):
        resolve_model(config_path, provider="groq")


def test_missing_config_still_allows_provider_url(tmp_path):
    missing = str(tmp_path / "nope.json")
    assert resolve_model(missing, model_name="m", provider_url=OPENROUTER_URL) == (
        "m", OPENROUTER_URL, FALLBACK_API_KEY_ENV,
    )
    with pytest.raises(ValueError, match="no model config"):
        resolve_model(missing, provider="gemini")


def test_repository_models_json_is_valid():
    # The models.json shipped at the repository root must load and resolve.
    model, url, key_env = resolve_model("models.json")
    assert model and url.startswith("https://") and key_env
