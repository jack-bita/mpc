"""config/tests/test_env.py — the helpers that read settings from environment variables (config/settings/base.py).

A missing secret must stop Django at startup, never let it start half-configured.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings.base import env, env_list


def test_empty_required_variable_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    # `DJANGO_SECRET_KEY=` in a .env file is a mistake, not a choice.
    monkeypatch.setenv("DJANGO_SECRET_KEY", "")

    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        env("DJANGO_SECRET_KEY")


def test_required_list_of_only_commas_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty host list would let Django start and then refuse every request with a 400.
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", " , ")

    with pytest.raises(ImproperlyConfigured, match="DJANGO_ALLOWED_HOSTS"):
        env_list("DJANGO_ALLOWED_HOSTS")


def test_list_is_split_on_commas_and_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "demo.example, localhost ,")

    assert env_list("DJANGO_ALLOWED_HOSTS") == ["demo.example", "localhost"]
