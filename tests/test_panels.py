"""Regression coverage for the property-first Google Analytics panel flow."""

import asyncio
import inspect
from types import SimpleNamespace

import panels


class _Page:
    def __init__(self, data):
        self.data = data


class _Store:
    def __init__(self, docs=()):
        self.docs = list(docs)

    async def query(self, collection, where=None, limit=100):
        docs = self.docs
        if where:
            docs = [doc for doc in docs if all((doc.data or {}).get(key) == value for key, value in where.items())]
        return _Page(docs[:limit])


class _Ctx:
    def __init__(self, docs=()):
        self.store = _Store(docs)


def _doc(doc_id, **data):
    return SimpleNamespace(id=doc_id, data=data)


def _text(node):
    return str(node)


def test_empty_sidebar_has_only_connect_action():
    node = asyncio.run(panels.analytics_nav(_Ctx()))
    rendered = _text(node)
    assert "Connect Google Account" in rendered
    assert "Settings" not in rendered
    assert "GA4 property" not in rendered


def test_empty_center_has_only_connect_action():
    node = asyncio.run(panels.analytics(_Ctx()))
    rendered = _text(node)
    assert "Connect Google Account" in rendered
    assert "Choose the GA4 property" not in rendered


def test_connected_account_without_property_explains_left_panel_selection(monkeypatch):
    async def no_selection(ctx):
        return {}

    monkeypatch.setattr(panels.ga4, "global_selected_property", no_selection)
    node = asyncio.run(panels.analytics(_Ctx([_doc("account-1", email="owner@example.com", is_active=True)])))
    assert "Choose the GA4 property to display in the left panel." in _text(node)


def test_center_refreshes_when_an_account_connects():
    source = inspect.getsource(panels)
    assert 'refresh="on_event:google-analytics-bluebee.account.connect' in source


def test_center_ignores_stale_property_parameter_after_account_switch(monkeypatch):
    async def no_selection_for_new_active_account(ctx):
        return {"property_id": "111", "email": "one@example.com"}

    monkeypatch.setattr(panels.ga4, "global_selected_property", no_selection_for_new_active_account)
    node = asyncio.run(panels.analytics(
        _Ctx([_doc("account-2", email="two@example.com", is_active=True)]),
        property_id="111",
    ))
    rendered = _text(node)

    assert "Choose the GA4 property to display in the left panel." in rendered
    assert "Overview ·" not in rendered


def test_sidebar_property_selector_queries_only_the_active_account(monkeypatch):
    calls = []

    async def fake_properties(ctx, doc):
        calls.append(doc.id)
        property_id = "123" if doc.id == "account-1" else "456"
        title = "Active property" if doc.id == "account-1" else "Other-account property"
        return {"ok": True, "properties": [{"property_id": property_id, "title": title}]}

    async def no_selection(ctx):
        return {}

    accounts = [
        _doc("account-1", email="owner@example.com", is_active=True),
        _doc("account-2", email="other@example.com", is_active=False),
    ]
    monkeypatch.setattr(panels.ga4, "properties", fake_properties)
    monkeypatch.setattr(panels.ga4, "global_selected_property", no_selection)
    node = asyncio.run(panels.analytics_nav(_Ctx(accounts)))
    rendered = _text(node)
    assert calls == ["account-1"]
    assert "owner@example.com" in rendered
    assert "other@example.com" in rendered
    assert "Active property" in rendered
    assert "Other-account property" not in rendered
    assert "Add another Google account" in rendered
    assert "GA4 property" in rendered
    assert "Select a GA4 property" in rendered
    # No report navigation is visible before a property is chosen.
    assert "Site reports" not in rendered
    assert "Settings" in rendered


def test_selected_property_sidebar_exposes_only_real_sections(monkeypatch):
    async def fake_properties(ctx, doc):
        return {"ok": True, "properties": [{"property_id": "123", "title": "Example site"}]}

    async def selected(ctx):
        return {"property_id": "123", "email": "owner@example.com"}

    monkeypatch.setattr(panels.ga4, "properties", fake_properties)
    monkeypatch.setattr(panels.ga4, "global_selected_property", selected)
    node = asyncio.run(panels.analytics_nav(
        _Ctx([_doc("account-1", email="owner@example.com", is_active=True)]), view="overview"
    ))
    rendered = _text(node)
    for label in ("Overview", "Explore", "Real-time", "Site reports", "Alerts", "Settings"):
        assert label in rendered
    assert "Saved reports" not in rendered
    assert "Properties" not in rendered
    assert "Coming soon" not in rendered


def test_site_report_view_uses_existing_report_handler():
    node = panels._site_reports("123", "pages")
    rendered = _text(node)
    assert "Top pages" in rendered
    assert "get_top_pages" in rendered
