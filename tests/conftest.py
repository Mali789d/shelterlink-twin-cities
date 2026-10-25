"""Shared test fixtures."""
import pytest

import app.main as main
from app.idempotency import ReplyCache
from app.throttle import ReplyThrottle


@pytest.fixture(autouse=True)
def fresh_reply_throttle(monkeypatch):
    """ReplyThrottle state must not leak between tests in one process."""
    monkeypatch.setattr(main, "reply_throttle", ReplyThrottle())


@pytest.fixture(autouse=True)
def fresh_reply_cache(monkeypatch):
    """ReplyCache state must not leak between tests in one process."""
    monkeypatch.setattr(main, "reply_cache", ReplyCache())
