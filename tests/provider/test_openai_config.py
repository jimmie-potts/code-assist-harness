from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from code_assist_harness.provider.openai_config import (
    DEFAULT_OPENAI_TEXT_STREAM_MODEL,
    DEFAULT_PROVIDER,
    INVALID_OPENAI_API_KEY_MESSAGE,
    MODEL_FOR_MOCK_MESSAGE,
    OPENAI_MODEL_REQUIRED_MESSAGE,
    SUPPORTED_OPENAI_TEXT_STREAM_MODELS,
    SUPPORTED_PROVIDERS,
    UNSUPPORTED_OPENAI_ENVIRONMENT_MESSAGE,
    UNSUPPORTED_OPENAI_MODEL_MESSAGE,
    UNSUPPORTED_PROVIDER_MESSAGE,
    OpenAIProviderConfiguration,
    ProviderConfigurationError,
    resolve_provider_configuration,
    validate_openai_environment,
    validate_openai_model,
    validate_provider_name,
    validate_provider_selection,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROVIDER_MODELS_FIXTURE = (
    REPOSITORY_ROOT
    / "protocol"
    / "fixtures"
    / "runtime-configuration"
    / "v1"
    / "provider-models.json"
)
VALID_MODEL = "gpt-5.6-luna"
FAKE_API_KEY = "FAKE_CAH_OPENAI_KEY_023"


def test_python_provider_constants_match_the_hand_reviewed_cross_language_fixture() -> None:
    fixture = json.loads(PROVIDER_MODELS_FIXTURE.read_text(encoding="utf-8"))

    assert fixture == {
        "default_provider": "mock",
        "supported_providers": ["mock", "openai"],
        "supported_openai_text_stream_models": [VALID_MODEL],
    }
    assert fixture["default_provider"] == DEFAULT_PROVIDER
    assert set(fixture["supported_providers"]) == set(SUPPORTED_PROVIDERS)
    assert set(fixture["supported_openai_text_stream_models"]) == set(
        SUPPORTED_OPENAI_TEXT_STREAM_MODELS
    )
    assert DEFAULT_OPENAI_TEXT_STREAM_MODEL == VALID_MODEL


@pytest.mark.parametrize(
    "provider",
    ["anthropic", "OPENAI", "", 1, True, None, [], {}, {"mock"}],
)
def test_provider_name_rejection_is_fixed_and_does_not_echo_candidate(provider: object) -> None:
    with pytest.raises(ProviderConfigurationError) as captured:
        validate_provider_name(provider)

    assert str(captured.value) == UNSUPPORTED_PROVIDER_MESSAGE
    if isinstance(provider, str) and provider:
        assert provider not in str(captured.value)


def test_mock_is_the_environment_independent_default_and_rejects_a_model() -> None:
    ambient_values = {
        "OPENAI_API_KEY": FAKE_API_KEY,
        "OPENAI_BASE_URL": "https://must-not-be-inspected.example",
    }

    assert validate_provider_selection("mock", None) == ("mock", None)
    assert resolve_provider_configuration("mock", None, ambient_values) is None
    with pytest.raises(ProviderConfigurationError, match="^--model") as captured:
        validate_provider_selection("mock", VALID_MODEL)
    assert str(captured.value) == MODEL_FOR_MOCK_MESSAGE


def test_openai_requires_the_explicit_exact_model() -> None:
    with pytest.raises(ProviderConfigurationError) as captured:
        validate_provider_selection("openai", None)

    assert str(captured.value) == OPENAI_MODEL_REQUIRED_MESSAGE
    assert validate_provider_selection("openai", VALID_MODEL) == ("openai", VALID_MODEL)


@pytest.mark.parametrize(
    "model",
    [
        "",
        "gpt-5.6",
        "o3-2025-04-16",
        "ft:gpt-5.6-luna:example",
        "unknown-model",
        f"{VALID_MODEL}\u00a0",
        f"{VALID_MODEL}\n",
        f"{VALID_MODEL}\u200b",
        f"{VALID_MODEL}\ud800",
        "x" * 257,
        "é" * 129,
        1,
        True,
        None,
    ],
)
def test_model_rejection_is_fixed_for_shape_and_allowlist_failures(model: object) -> None:
    with pytest.raises(ProviderConfigurationError) as captured:
        validate_openai_model(model)

    assert str(captured.value) == UNSUPPORTED_OPENAI_MODEL_MESSAGE
    assert VALID_MODEL in str(captured.value)


def test_valid_openai_configuration_hides_and_freezes_the_credential() -> None:
    configuration = resolve_provider_configuration(
        "openai",
        VALID_MODEL,
        {"OPENAI_API_KEY": FAKE_API_KEY},
    )

    assert configuration == OpenAIProviderConfiguration(
        model=VALID_MODEL,
        api_key=FAKE_API_KEY,
    )
    assert configuration is not None
    assert configuration.api_key == FAKE_API_KEY
    assert FAKE_API_KEY not in repr(configuration)
    with pytest.raises(FrozenInstanceError):
        configuration.api_key = "replacement"  # type: ignore[misc]


@pytest.mark.parametrize(
    "api_key",
    [
        None,
        "",
        "has whitespace",
        "line\nbreak",
        "zero\u200bwidth",
        "category\ud800surrogate",
        "x" * 4097,
        1,
    ],
)
def test_missing_or_malformed_api_key_uses_one_non_echoing_error(api_key: object) -> None:
    environment = {} if api_key is None else {"OPENAI_API_KEY": api_key}

    with pytest.raises(ProviderConfigurationError) as captured:
        resolve_provider_configuration(
            "openai",
            VALID_MODEL,
            environment,  # type: ignore[arg-type]
        )

    assert str(captured.value) == INVALID_OPENAI_API_KEY_MESSAGE
    if isinstance(api_key, str) and api_key:
        assert api_key not in str(captured.value)


def test_api_key_has_no_provider_prefix_assumption() -> None:
    configuration = resolve_provider_configuration(
        "openai",
        VALID_MODEL,
        {"OPENAI_API_KEY": "locally-valid-without-a-prefix"},
    )

    assert configuration is not None
    assert configuration.api_key == "locally-valid-without-a-prefix"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OPENAI_BASE_URL", "https://redirect.example/v1"),
        ("OPENAI_ORG_ID", "org-secret"),
        ("OPENAI_PROJECT_ID", "project-secret"),
        ("OPENAI_CUSTOM_HEADERS", "x-secret: value"),
        ("OPENAI_LOG", "debug"),
        ("OPENAI_FUTURE_OPTION", ""),
        ("SSLKEYLOGFILE", "/tmp/tls-keys.log"),
    ],
)
def test_unsupported_network_environment_name_is_rejected_without_echoing_it(
    name: str,
    value: str,
) -> None:
    with pytest.raises(ProviderConfigurationError) as captured:
        resolve_provider_configuration(
            "openai",
            VALID_MODEL,
            {"OPENAI_API_KEY": FAKE_API_KEY, name: value},
        )

    assert str(captured.value) == UNSUPPORTED_OPENAI_ENVIRONMENT_MESSAGE
    if name != "SSLKEYLOGFILE":
        assert name not in str(captured.value)
    if value:
        assert value not in str(captured.value)


@pytest.mark.parametrize("late_name", ["OPENAI_FUTURE_OPTION", "SSLKEYLOGFILE"])
def test_environment_can_be_revalidated_after_initial_configuration(late_name: str) -> None:
    environment = {"OPENAI_API_KEY": FAKE_API_KEY}
    configuration = resolve_provider_configuration("openai", VALID_MODEL, environment)
    environment[late_name] = "late-secret-value"

    with pytest.raises(ProviderConfigurationError) as captured:
        validate_openai_environment(environment)

    assert configuration is not None
    assert str(captured.value) == UNSUPPORTED_OPENAI_ENVIRONMENT_MESSAGE
    if late_name != "SSLKEYLOGFILE":
        assert late_name not in str(captured.value)
    assert "late-secret-value" not in str(captured.value)


def test_direct_configuration_construction_preserves_validation_invariants() -> None:
    with pytest.raises(ProviderConfigurationError) as model_failure:
        OpenAIProviderConfiguration(model="gpt-5.6", api_key=FAKE_API_KEY)
    with pytest.raises(ProviderConfigurationError) as key_failure:
        OpenAIProviderConfiguration(model=VALID_MODEL, api_key="bad key")

    assert str(model_failure.value) == UNSUPPORTED_OPENAI_MODEL_MESSAGE
    assert str(key_failure.value) == INVALID_OPENAI_API_KEY_MESSAGE
