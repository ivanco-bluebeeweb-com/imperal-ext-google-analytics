"""Offline tests for connected-account status mapping (no live Google calls)."""

import asyncio
from types import SimpleNamespace

from handlers_accounts import live_status


def _doc(email="user@example.com", created_at="2026-08-01T00:00:00Z"):
    return SimpleNamespace(id="acc1", data={"email": email, "created_at": created_at})


def _patch_properties(monkeypatch, result):
    import handlers_accounts
    monkeypatch.setattr(handlers_accounts.ga4, "properties", lambda ctx, doc: _async_return(result))


async def _async_return(value):
    return value


def test_connected_when_properties_reachable(monkeypatch):
    _patch_properties(monkeypatch, {"ok": True, "properties": [{"property_id": "1"}, {"property_id": "2"}]})
    account = asyncio.run(live_status(SimpleNamespace(), _doc()))
    assert account.status == "connected"
    assert account.property_count == 2
    assert account.account == "user@example.com"
    assert account.is_active is False


def test_live_status_reports_is_active_true(monkeypatch):
    _patch_properties(monkeypatch, {"ok": True, "properties": [{"property_id": "1"}]})
    doc = SimpleNamespace(id="acc1", data={"email": "user@example.com", "created_at": "", "is_active": True})
    account = asyncio.run(live_status(SimpleNamespace(), doc))
    assert account.is_active is True


def test_insufficient_access_when_zero_properties(monkeypatch):
    _patch_properties(monkeypatch, {"ok": True, "properties": []})
    account = asyncio.run(live_status(SimpleNamespace(), _doc()))
    assert account.status == "insufficient_access"
    assert account.property_count == 0


def test_reconnect_required_on_token_rejected(monkeypatch):
    _patch_properties(monkeypatch, {"ok": False, "code": "TOKEN_REJECTED", "error": "nope"})
    account = asyncio.run(live_status(SimpleNamespace(), _doc()))
    assert account.status == "reconnect_required"


def test_insufficient_access_on_permission_denied(monkeypatch):
    _patch_properties(monkeypatch, {"ok": False, "code": "PERMISSION_DENIED", "error": "nope"})
    account = asyncio.run(live_status(SimpleNamespace(), _doc()))
    assert account.status == "insufficient_access"


def test_generic_error_maps_to_error_status(monkeypatch):
    _patch_properties(monkeypatch, {"ok": False, "code": "UNREACHABLE", "error": "nope"})
    account = asyncio.run(live_status(SimpleNamespace(), _doc()))
    assert account.status == "error"


def test_never_reports_unknown_status():
    """Guards the plan's invariant: no connection may ever be labeled 'unknown'."""
    import inspect
    import handlers_accounts
    source = inspect.getsource(handlers_accounts)
    assert 'status="unknown"' not in source
