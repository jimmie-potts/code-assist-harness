"""Repository-wide pytest options for explicitly selected live-provider checks."""

from __future__ import annotations

import os

import pytest

_LIVE_PROVIDER_CONFIGURATION = pytest.StashKey[object]()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register live-provider controls without making credentials an implicit selector."""
    group = parser.getgroup("live-provider")
    group.addoption(
        "--run-live-provider",
        action="store_true",
        default=False,
        help="allow explicitly selected live-provider tests to make one bounded request",
    )
    group.addoption(
        "--live-provider-model",
        action="store",
        default=None,
        metavar="MODEL",
        help="exact repository-allowlisted model snapshot for a live-provider test",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live tests by default or validate their configuration before test setup."""
    live_items = [item for item in items if item.get_closest_marker("live_provider")]
    if not live_items:
        return

    if not config.getoption("run_live_provider"):
        reason = "live provider tests require --run-live-provider"
        for item in live_items:
            item.add_marker(pytest.mark.skip(reason=reason))
        return

    from code_assist_harness.provider.openai_config import (
        ProviderConfigurationError,
        resolve_provider_configuration,
    )

    try:
        configuration = resolve_provider_configuration(
            "openai",
            config.getoption("live_provider_model"),
            os.environ,
        )
    except ProviderConfigurationError as error:
        raise pytest.UsageError(str(error)) from None
    if configuration is None:
        raise pytest.UsageError("live provider configuration did not select OpenAI")
    config.stash[_LIVE_PROVIDER_CONFIGURATION] = configuration


@pytest.fixture
def live_provider_configuration(pytestconfig: pytest.Config) -> object:
    """Return configuration validated before an opted-in live test can execute."""
    try:
        return pytestconfig.stash[_LIVE_PROVIDER_CONFIGURATION]
    except KeyError:
        pytest.skip("live provider configuration was not selected")
