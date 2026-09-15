from __future__ import annotations

from types import SimpleNamespace

import pytest

import backend.app.db.session as session_module
from backend.app.core.config import Settings
from backend.app.db.session import DEFAULT_LOCK_TIMEOUT_MS, DatabaseManager, _connect_args

_URL = "postgresql+psycopg://user:pw@localhost:5432/db"


def test_every_connection_bounds_its_lock_wait() -> None:
    """An unbounded lock wait is what turned one stuck holder into an outage."""

    assert _connect_args(5_000) == {"options": "-c lock_timeout=5000"}


def test_the_default_ceiling_clears_a_full_decision_run() -> None:
    # A creation holds its advisory lock while the agents run, so the ceiling
    # must not fire on legitimate work.
    assert DEFAULT_LOCK_TIMEOUT_MS >= 60_000
    assert Settings().db_lock_timeout_ms == DEFAULT_LOCK_TIMEOUT_MS


def test_zero_is_accepted_as_the_deliberate_unbounded_setting() -> None:
    assert _connect_args(0) == {"options": "-c lock_timeout=0"}


def test_a_negative_ceiling_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        _connect_args(-1)


def test_the_engine_is_built_with_the_configured_ceiling(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs: object):
        captured["url"] = url
        captured.update(kwargs)
        return SimpleNamespace(dispose=lambda: None)

    monkeypatch.setattr(session_module, "create_engine", fake_create_engine)
    monkeypatch.setattr(session_module, "sessionmaker", lambda **kwargs: None)

    DatabaseManager(_URL, lock_timeout_ms=7_500)

    assert captured["connect_args"] == {"options": "-c lock_timeout=7500"}
    assert captured["pool_pre_ping"] is True
