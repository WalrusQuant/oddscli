"""Tests for TTLCache."""

import time

from app.services.cache import TTLCache


def test_set_and_get():
    cache = TTLCache()
    cache.set("k1", [1, 2, 3], ttl=60)
    assert cache.get("k1") == [1, 2, 3]


def test_get_missing_key_returns_none():
    cache = TTLCache()
    assert cache.get("nonexistent") is None


def test_expiry(monkeypatch):
    cache = TTLCache()
    # Patch monotonic to control time
    base = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: base)
    cache.set("k1", "value", ttl=10)

    # Still valid
    monkeypatch.setattr(time, "monotonic", lambda: base + 5)
    assert cache.get("k1") == "value"

    # Expired
    monkeypatch.setattr(time, "monotonic", lambda: base + 11)
    assert cache.get("k1") is None


def test_invalidate():
    cache = TTLCache()
    cache.set("k1", "val", ttl=60)
    cache.invalidate("k1")
    assert cache.get("k1") is None


def test_invalidate_nonexistent_key():
    cache = TTLCache()
    cache.invalidate("nope")  # Should not raise


def test_clear():
    cache = TTLCache()
    cache.set("a", 1, ttl=60)
    cache.set("b", 2, ttl=60)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_overwrite():
    cache = TTLCache()
    cache.set("k1", "old", ttl=60)
    cache.set("k1", "new", ttl=60)
    assert cache.get("k1") == "new"
