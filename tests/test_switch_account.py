"""Offline tests for the active-account concept: resolve_account/active_account
(ga4_client) and the switch_account chat function (handlers_accounts) —
the exact pattern the Google Search Console connector uses.
"""

import asyncio
from types import SimpleNamespace

import ga4_client as ga4
from handlers_accounts import switch_account
from models import AccountAction


class _Page:
    def __init__(self, data):
        self.data = data


class _FakeStore:
    """Minimal in-memory ext_store stand-in: query(where=...) + update()."""

    def __init__(self, docs):
        self._docs = {doc.id: doc for doc in docs}

    async def query(self, collection, where=None, limit=100):
        docs = list(self._docs.values())
        if where:
            docs = [d for d in docs if all((d.data or {}).get(k) == v for k, v in where.items())]
        return _Page(docs[:limit])

    async def update(self, collection, doc_id, data):
        self._docs[doc_id] = SimpleNamespace(id=doc_id, data=data)


def _doc(doc_id, email, is_active=False):
    return SimpleNamespace(id=doc_id, data={"email": email, "is_active": is_active})


def _ctx(docs):
    return SimpleNamespace(store=_FakeStore(docs))


def test_active_account_returns_marked_account():
    docs = [_doc("a", "one@example.com", is_active=False), _doc("b", "two@example.com", is_active=True)]
    ctx = _ctx(docs)
    active = asyncio.run(ga4.active_account(ctx))
    assert active.id == "b"


def test_active_account_falls_back_to_first_when_none_marked():
    docs = [_doc("a", "one@example.com"), _doc("b", "two@example.com")]
    ctx = _ctx(docs)
    active = asyncio.run(ga4.active_account(ctx))
    assert active.id == "a"


def test_active_account_none_when_no_accounts():
    ctx = _ctx([])
    assert asyncio.run(ga4.active_account(ctx)) is None


def test_resolve_account_without_email_uses_active_account():
    docs = [_doc("a", "one@example.com"), _doc("b", "two@example.com", is_active=True)]
    ctx = _ctx(docs)
    resolved = asyncio.run(ga4.resolve_account(ctx))
    assert resolved["ok"] is True
    assert resolved["account"].id == "b"


def test_resolve_account_with_multiple_accounts_no_longer_ambiguous():
    """Regression: connecting a second account must not break every account-omitting read."""
    docs = [_doc("a", "one@example.com"), _doc("b", "two@example.com")]
    ctx = _ctx(docs)
    resolved = asyncio.run(ga4.resolve_account(ctx))
    assert resolved["ok"] is True
    assert resolved.get("code") != "ACCOUNT_AMBIGUOUS"


def test_resolve_account_missing_when_none_connected():
    resolved = asyncio.run(ga4.resolve_account(_ctx([])))
    assert resolved["ok"] is False
    assert resolved["code"] == "ACCOUNT_MISSING"


def test_switch_account_marks_target_active_and_others_inactive():
    docs = [_doc("a", "one@example.com", is_active=True), _doc("b", "two@example.com", is_active=False)]
    ctx = _ctx(docs)
    result = asyncio.run(switch_account(ctx, AccountAction(account="two@example.com")))
    assert result.status == "success"
    assert result.data.active == "two@example.com"
    assert ctx.store._docs["a"].data["is_active"] is False
    assert ctx.store._docs["b"].data["is_active"] is True


def test_switch_account_clears_prior_current_property_context():
    accounts = [_doc("a", "one@example.com", is_active=True), _doc("b", "two@example.com", is_active=False)]
    selection = SimpleNamespace(id="selection", data={
        "email": "one@example.com", "property_id": "111", "is_current": True,
    })
    ctx = _ctx([*accounts, selection])
    # This fixture uses one store for the compact test double; the production
    # code queries distinct collections, so expose only selection rows there.
    original_query = ctx.store.query

    async def query(collection, where=None, limit=100):
        if collection == "google_analytics_selections":
            docs = [ctx.store._docs["selection"]]
            return _Page(docs)
        return await original_query(collection, where=where, limit=limit)

    ctx.store.query = query
    result = asyncio.run(switch_account(ctx, AccountAction(account="two@example.com")))

    assert result.status == "success"
    assert ctx.store._docs["selection"].data["is_current"] is False


def test_switch_account_restores_target_accounts_last_property_context():
    accounts = [_doc("a", "one@example.com", is_active=True), _doc("b", "two@example.com", is_active=False)]
    first_selection = SimpleNamespace(id="first-selection", data={
        "email": "one@example.com", "property_id": "111", "is_current": True,
    })
    target_selection = SimpleNamespace(id="target-selection", data={
        "email": "two@example.com", "property_id": "222", "is_current": False,
    })
    ctx = _ctx([*accounts, first_selection, target_selection])
    original_query = ctx.store.query

    async def query(collection, where=None, limit=100):
        if collection == "google_analytics_selections":
            return _Page([ctx.store._docs["first-selection"], ctx.store._docs["target-selection"]])
        return await original_query(collection, where=where, limit=limit)

    ctx.store.query = query
    result = asyncio.run(switch_account(ctx, AccountAction(account="two@example.com")))

    assert result.status == "success"
    assert "Restored this account's last selected GA4 property" in result.summary
    assert ctx.store._docs["first-selection"].data["is_current"] is False
    assert ctx.store._docs["target-selection"].data["is_current"] is True
    assert result.refresh_panels == ["analytics", "analytics_nav"]


def test_switch_account_without_saved_property_leaves_clean_start_state():
    accounts = [_doc("a", "one@example.com", is_active=True), _doc("b", "two@example.com", is_active=False)]
    selection = SimpleNamespace(id="selection", data={
        "email": "one@example.com", "property_id": "111", "is_current": True,
    })
    ctx = _ctx([*accounts, selection])
    original_query = ctx.store.query

    async def query(collection, where=None, limit=100):
        if collection == "google_analytics_selections":
            return _Page([ctx.store._docs["selection"]])
        return await original_query(collection, where=where, limit=limit)

    ctx.store.query = query
    result = asyncio.run(switch_account(ctx, AccountAction(account="two@example.com")))

    assert result.status == "success"
    assert result.summary == "Switched to two@example.com. Select one of this account's GA4 properties."
    assert ctx.store._docs["selection"].data["is_current"] is False
    assert result.refresh_panels == ["analytics", "analytics_nav"]


def test_switch_account_errors_when_account_not_connected():
    ctx = _ctx([_doc("a", "one@example.com", is_active=True)])
    result = asyncio.run(switch_account(ctx, AccountAction(account="missing@example.com")))
    assert result.status == "error"
    assert result.error_code == "ACCOUNT_MISSING"
