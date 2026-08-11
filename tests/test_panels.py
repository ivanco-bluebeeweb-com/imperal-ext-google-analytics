"""Regression coverage for the property-first Google Analytics panel flow."""

import asyncio
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
    assert "Select a GA4 property" not in rendered


def test_connected_sidebar_shows_accounts_and_property_selector_before_menu(monkeypatch):
    async def fake_properties(ctx, doc):
        return {"ok": True, "properties": [{"property_id": "123", "title": "Example site"}]}

    async def no_selection(ctx):
        return {}

    monkeypatch.setattr(panels.ga4, "properties", fake_properties)
    monkeypatch.setattr(panels.ga4, "global_selected_property", no_selection)
    node = asyncio.run(panels.analytics_nav(_Ctx([_doc("account-1", email="owner@example.com", is_active=True)])))
    rendered = _text(node)
    assert "owner@example.com" in rendered
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
