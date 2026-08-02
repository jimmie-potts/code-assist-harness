"""SDK-free validation for the explicitly selected OpenAI provider."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

SUPPORTED_OPENAI_TEXT_STREAM_MODELS = frozenset({"gpt-5.6-luna"})
"""Exact model IDs whose stream shape CAH-023 validates."""

DEFAULT_OPENAI_TEXT_STREAM_MODEL = "gpt-5.6-luna"
"""Single allowlisted model named in safe configuration guidance."""

OPENAI_API_KEY_NAME = "OPENAI_API_KEY"
"""Only OpenAI-prefixed environment setting accepted by the adapter."""

UNSUPPORTED_OPENAI_MODEL_MESSAGE = "Unsupported OpenAI model. Use gpt-5.6-luna."
"""Fixed model rejection that never repeats an untrusted candidate."""

UNSUPPORTED_PROVIDER_MESSAGE = "--provider must be either mock or openai."
"""Fixed provider-name rejection that never repeats an untrusted candidate."""

MODEL_FOR_MOCK_MESSAGE = "--model is supported only with --provider openai."
"""Fixed rejection for a model supplied to the deterministic mock."""

OPENAI_MODEL_REQUIRED_MESSAGE = "--provider openai requires --model MODEL."
"""Fixed rejection for an incomplete OpenAI selection."""

UNSUPPORTED_OPENAI_ENVIRONMENT_MESSAGE = (
    "Unsupported OpenAI configuration is present. Remove every OPENAI_* variable "
    "except OPENAI_API_KEY."
)
"""Fixed rejection for ambient OpenAI SDK routing or logging configuration."""

INVALID_OPENAI_API_KEY_MESSAGE = "OPENAI_API_KEY is required and must be a valid local credential."
"""Fixed rejection for a missing or locally malformed credential."""

type ProviderName = Literal["mock", "openai"]
"""Provider names accepted by both composition roots."""

DEFAULT_PROVIDER: ProviderName = "mock"
"""Provider selected when no explicit command-line option is present."""

SUPPORTED_PROVIDERS = frozenset({"mock", "openai"})
"""Exact provider names shared with the TypeScript launcher."""


class ProviderConfigurationError(ValueError):
    """Report a fixed safe provider-selection problem before SDK import."""


@dataclass(frozen=True, slots=True)
class OpenAIProviderConfiguration:
    """Validated values required to construct the concrete adapter lazily.

    Args:
        model: Exact repository-allowlisted model ID.
        api_key: Locally validated credential retained only at the adapter boundary.
    """

    model: str
    api_key: str = field(repr=False)

    def __post_init__(self) -> None:
        """Preserve validation when adapter tests construct configuration directly."""
        validate_openai_model(self.model)
        if not _is_bounded_visible_utf8(self.api_key, maximum_bytes=4096):
            raise ProviderConfigurationError(INVALID_OPENAI_API_KEY_MESSAGE)


def validate_provider_name(value: object) -> ProviderName:
    """Return one supported provider name without echoing an invalid value.

    Args:
        value: Candidate CLI provider value.

    Returns:
        ``mock`` or ``openai``.

    Raises:
        ProviderConfigurationError: If the value is not one of the two fixed names.
    """
    if value not in SUPPORTED_PROVIDERS:
        raise ProviderConfigurationError(UNSUPPORTED_PROVIDER_MESSAGE)
    return cast(ProviderName, value)


def validate_openai_model(value: object) -> str:
    """Validate one model ID before exact allowlist membership is checked.

    Args:
        value: Candidate model supplied outside the protocol.

    Returns:
        The exact allowlisted model ID.

    Raises:
        ProviderConfigurationError: If encoding, size, characters, or membership are invalid.
    """
    if not _is_bounded_visible_utf8(value, maximum_bytes=256):
        raise ProviderConfigurationError(UNSUPPORTED_OPENAI_MODEL_MESSAGE)
    if value not in SUPPORTED_OPENAI_TEXT_STREAM_MODELS:
        raise ProviderConfigurationError(UNSUPPORTED_OPENAI_MODEL_MESSAGE)
    return cast(str, value)


def resolve_provider_configuration(
    provider: object,
    model: object | None,
    environment: Mapping[str, str],
) -> OpenAIProviderConfiguration | None:
    """Validate provider, model, and environment without importing the SDK.

    Args:
        provider: Explicit or default provider name.
        model: Optional model candidate from the process command line.
        environment: Process environment inspected only after OpenAI is selected.

    Returns:
        ``None`` for the deterministic mock or validated OpenAI adapter settings.

    Raises:
        ProviderConfigurationError: If the selected provider configuration is unsafe or incomplete.

    Security:
        Error messages name only fixed option or environment labels. They never include candidate
        model IDs, credential values, or ambient configuration values.
    """
    selected, validated_model = validate_provider_selection(provider, model)
    if selected == "mock":
        return None

    if validated_model is None:
        raise ProviderConfigurationError(OPENAI_MODEL_REQUIRED_MESSAGE)

    validate_openai_environment(environment)

    api_key = environment.get(OPENAI_API_KEY_NAME)
    if not _is_bounded_visible_utf8(api_key, maximum_bytes=4096):
        raise ProviderConfigurationError(INVALID_OPENAI_API_KEY_MESSAGE)
    return OpenAIProviderConfiguration(model=validated_model, api_key=api_key)


def validate_openai_environment(environment: Mapping[str, str]) -> None:
    """Reject ambient OpenAI SDK settings other than the selected credential.

    This check runs both at configuration resolution and immediately before lazy client
    construction. Repeating it detects ambient SDK routing, header, or logging configuration added
    during the ordinary gap after :class:`OpenAIProviderConfiguration` was created.

    Args:
        environment: Current process environment names and values. Values are never inspected or
            copied into an error.

    Raises:
        ProviderConfigurationError: If any unsupported ``OPENAI_*`` name is present.
    """
    if any(name.startswith("OPENAI_") and name != OPENAI_API_KEY_NAME for name in environment):
        raise ProviderConfigurationError(UNSUPPORTED_OPENAI_ENVIRONMENT_MESSAGE)


def validate_provider_selection(
    provider: object,
    model: object | None,
) -> tuple[ProviderName, str | None]:
    """Validate the provider/model pair without inspecting environment configuration.

    The TypeScript launcher performs the same validation for early feedback. Python repeats it as
    the authoritative child boundary before an SDK module can be imported.

    Args:
        provider: Explicit or default provider name.
        model: Optional model candidate supplied outside protocol stdin.

    Returns:
        The normalized provider name and exact OpenAI model, or ``None`` for the mock model.

    Raises:
        ProviderConfigurationError: If the pair is incomplete, mismatched, or unsupported.
    """
    selected = validate_provider_name(provider)
    if selected == "mock":
        if model is not None:
            raise ProviderConfigurationError(MODEL_FOR_MOCK_MESSAGE)
        return selected, None
    if model is None:
        raise ProviderConfigurationError(OPENAI_MODEL_REQUIRED_MESSAGE)
    return selected, validate_openai_model(model)


def _is_bounded_visible_utf8(value: object, *, maximum_bytes: int) -> bool:
    """Return whether a secret or identifier is bounded and free of ambiguous characters."""
    if not isinstance(value, str):
        return False
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    if not 1 <= len(encoded) <= maximum_bytes:
        return False
    return not any(
        character.isspace() or unicodedata.category(character).startswith("C")
        for character in value
    )


__all__ = [
    "DEFAULT_PROVIDER",
    "DEFAULT_OPENAI_TEXT_STREAM_MODEL",
    "INVALID_OPENAI_API_KEY_MESSAGE",
    "MODEL_FOR_MOCK_MESSAGE",
    "OPENAI_API_KEY_NAME",
    "OPENAI_MODEL_REQUIRED_MESSAGE",
    "OpenAIProviderConfiguration",
    "ProviderConfigurationError",
    "ProviderName",
    "SUPPORTED_PROVIDERS",
    "SUPPORTED_OPENAI_TEXT_STREAM_MODELS",
    "UNSUPPORTED_OPENAI_ENVIRONMENT_MESSAGE",
    "UNSUPPORTED_OPENAI_MODEL_MESSAGE",
    "UNSUPPORTED_PROVIDER_MESSAGE",
    "resolve_provider_configuration",
    "validate_openai_environment",
    "validate_openai_model",
    "validate_provider_name",
    "validate_provider_selection",
]
