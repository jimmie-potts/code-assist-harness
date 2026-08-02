from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

import code_assist_harness.runtime as runtime_module
from code_assist_harness.loop_limits import LoopLimits
from code_assist_harness.provider import ProviderRequest
from code_assist_harness.provider.openai_config import (
    INVALID_OPENAI_API_KEY_MESSAGE,
    MODEL_FOR_MOCK_MESSAGE,
    OPENAI_MODEL_REQUIRED_MESSAGE,
    UNSUPPORTED_OPENAI_MODEL_MESSAGE,
    UNSUPPORTED_PROVIDER_MESSAGE,
    OpenAIProviderConfiguration,
    ProviderConfigurationError,
)

VALID_MODEL = "gpt-5.6-luna"
FAKE_API_KEY = "FAKE_CAH_RUNTIME_OPENAI_KEY_023"


class _StubProvider:
    """Structural provider used only to inspect composition-root wiring."""

    def start(self, _request: ProviderRequest) -> object:
        raise AssertionError("configuration tests must not start provider work")


def _runtime_arguments(workspace: Path, *extra: str) -> tuple[str, ...]:
    return ("--workspace", str(workspace), "--no-transcript", *extra)


def _clear_openai_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(runtime_module.os.environ):
        if name.startswith("OPENAI_"):
            monkeypatch.delenv(name, raising=False)


def test_python_options_default_to_mock_and_accept_an_explicit_mock(tmp_path: Path) -> None:
    default = runtime_module._parse_runtime_options(_runtime_arguments(tmp_path))
    explicit = runtime_module._parse_runtime_options(
        _runtime_arguments(tmp_path, "--provider", "mock")
    )

    assert default.provider == "mock"
    assert default.model is None
    assert explicit.provider == "mock"
    assert explicit.model is None


@pytest.mark.parametrize(
    "arguments",
    [
        ("--provider", "openai", "--model", VALID_MODEL),
        ("--model", VALID_MODEL, "--provider", "openai"),
    ],
)
def test_python_options_accept_the_openai_pair_in_either_order(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    options = runtime_module._parse_runtime_options(_runtime_arguments(tmp_path, *arguments))

    assert options.provider == "openai"
    assert options.model == VALID_MODEL


@pytest.mark.parametrize(
    ("arguments", "expected_message", "untrusted_value"),
    [
        (("--provider", "PRIVATE_PROVIDER_VALUE"), UNSUPPORTED_PROVIDER_MESSAGE, "PRIVATE"),
        (("--model", VALID_MODEL), MODEL_FOR_MOCK_MESSAGE, None),
        (("--provider", "openai"), OPENAI_MODEL_REQUIRED_MESSAGE, None),
        (
            ("--provider", "openai", "--model", "PRIVATE_MODEL_VALUE"),
            UNSUPPORTED_OPENAI_MODEL_MESSAGE,
            "PRIVATE_MODEL_VALUE",
        ),
        (
            ("--provider", "mock", "--provider", "openai"),
            "--provider NAME may be provided at most once",
            None,
        ),
        (
            ("--provider", "openai", "--model", VALID_MODEL, "--model", "private"),
            "--model MODEL may be provided at most once",
            "private",
        ),
    ],
)
def test_python_options_reject_invalid_pairs_with_fixed_non_echoing_errors(
    tmp_path: Path,
    arguments: tuple[str, ...],
    expected_message: str,
    untrusted_value: str | None,
) -> None:
    with pytest.raises(runtime_module.RuntimeConfigurationError) as captured:
        runtime_module._parse_runtime_options(_runtime_arguments(tmp_path, *arguments))

    assert str(captured.value) == expected_message
    if untrusted_value is not None:
        assert untrusted_value not in str(captured.value)


def test_mock_composition_ignores_ambient_openai_values_and_never_loads_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = runtime_module._parse_runtime_options(
        _runtime_arguments(tmp_path, "--provider", "mock")
    )

    def fail_if_loaded(_configuration: OpenAIProviderConfiguration) -> _StubProvider:
        raise AssertionError("mock composition must not load the OpenAI adapter")

    monkeypatch.setattr(runtime_module, "_create_openai_provider", fail_if_loaded)

    assert (
        runtime_module._compose_provider(
            options,
            {
                "OPENAI_API_KEY": FAKE_API_KEY,
                "OPENAI_BASE_URL": "https://ambient-route.example/v1",
            },
        )
        is None
    )


def test_invalid_openai_environment_fails_before_adapter_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = runtime_module._parse_runtime_options(
        _runtime_arguments(tmp_path, "--provider", "openai", "--model", VALID_MODEL)
    )
    constructed = False

    def capture_construction(_configuration: OpenAIProviderConfiguration) -> _StubProvider:
        nonlocal constructed
        constructed = True
        return _StubProvider()

    monkeypatch.setattr(runtime_module, "_create_openai_provider", capture_construction)

    with pytest.raises(ProviderConfigurationError) as captured:
        runtime_module._compose_provider(options, {})

    assert str(captured.value) == INVALID_OPENAI_API_KEY_MESSAGE
    assert constructed is False


def test_valid_openai_composition_passes_only_validated_adapter_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = runtime_module._parse_runtime_options(
        _runtime_arguments(tmp_path, "--provider", "openai", "--model", VALID_MODEL)
    )
    captured: list[OpenAIProviderConfiguration] = []
    provider = _StubProvider()

    def capture_construction(configuration: OpenAIProviderConfiguration) -> _StubProvider:
        captured.append(configuration)
        return provider

    monkeypatch.setattr(runtime_module, "_create_openai_provider", capture_construction)

    assert (
        runtime_module._compose_provider(
            options,
            {"OPENAI_API_KEY": FAKE_API_KEY},
        )
        is provider
    )
    assert captured == [OpenAIProviderConfiguration(model=VALID_MODEL, api_key=FAKE_API_KEY)]
    assert FAKE_API_KEY not in repr(captured)


def test_concrete_adapter_module_is_imported_only_by_the_deferred_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "code_assist_harness.provider.openai_responses"
    fake_module = ModuleType(module_name)
    constructed: list[OpenAIProviderConfiguration] = []
    provider = _StubProvider()

    class StubOpenAIResponsesProvider:
        def __new__(
            cls,
            configuration: OpenAIProviderConfiguration,
        ) -> _StubProvider:
            del cls
            constructed.append(configuration)
            return provider

    fake_module.OpenAIResponsesProvider = StubOpenAIResponsesProvider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, fake_module)
    configuration = OpenAIProviderConfiguration(model=VALID_MODEL, api_key=FAKE_API_KEY)

    assert runtime_module._create_openai_provider(configuration) is provider
    assert constructed == [configuration]


def test_main_keeps_ambient_credentials_on_the_default_mock_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_openai_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ignored-on-mock.example/v1")
    captured: dict[str, object] = {}

    async def capture_runtime(workspace: Path, **options: object) -> None:
        captured["workspace"] = workspace
        captured.update(options)

    def fail_if_loaded(_configuration: OpenAIProviderConfiguration) -> _StubProvider:
        raise AssertionError("ambient credentials must not activate OpenAI")

    monkeypatch.setattr(runtime_module, "run_runtime", capture_runtime)
    monkeypatch.setattr(runtime_module, "_create_openai_provider", fail_if_loaded)

    result = runtime_module.main(_runtime_arguments(tmp_path))

    assert result == 0
    assert captured["workspace"] == tmp_path.resolve()
    assert captured["provider"] is None
    assert captured["loop_limits"] is None


def test_main_supplies_explicit_limits_with_the_selected_openai_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_openai_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    provider = _StubProvider()
    captured: dict[str, object] = {}

    async def capture_runtime(workspace: Path, **options: object) -> None:
        captured["workspace"] = workspace
        captured.update(options)

    monkeypatch.setattr(runtime_module, "run_runtime", capture_runtime)
    monkeypatch.setattr(
        runtime_module,
        "_create_openai_provider",
        lambda _configuration: provider,
    )

    result = runtime_module.main(
        _runtime_arguments(
            tmp_path,
            "--provider",
            "openai",
            "--model",
            VALID_MODEL,
        )
    )

    assert result == 0
    assert captured["workspace"] == tmp_path.resolve()
    assert captured["provider"] is provider
    assert captured["loop_limits"] == LoopLimits()


def test_main_reports_missing_credentials_only_on_safe_stderr_before_adapter_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_openai_environment(monkeypatch)

    def fail_if_loaded(_configuration: OpenAIProviderConfiguration) -> _StubProvider:
        raise AssertionError("invalid configuration must fail before adapter import")

    monkeypatch.setattr(runtime_module, "_create_openai_provider", fail_if_loaded)

    result = runtime_module.main(
        _runtime_arguments(
            tmp_path,
            "--provider",
            "openai",
            "--model",
            VALID_MODEL,
        )
    )
    output = capsys.readouterr()

    assert result == 2
    assert output.out == ""
    assert output.err == f"runtime configuration error: {INVALID_OPENAI_API_KEY_MESSAGE}\n"
    assert FAKE_API_KEY not in output.err
