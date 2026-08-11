"""Panel behavior for the GA4 overview's automatic period loading."""

import asyncio

import panels


def _text(node):
    return str(node)


def test_overview_defaults_to_last_30_days_and_autoloads_when_uncached(monkeypatch):
    async def no_cached_overview(ctx, property_id, start_date, end_date):
        assert property_id == "123"
        assert (start_date, end_date) == ("30daysAgo", "yesterday")
        return None

    async def no_load_state(ctx, property_id, start_date, end_date):
        return None

    monkeypatch.setattr(panels, "cached_overview", no_cached_overview)
    monkeypatch.setattr(panels, "overview_load_state", no_load_state)
    page = asyncio.run(panels._overview(object(), "123", period="30days"))
    rendered = _text(page)

    assert "Show results for" in rendered
    assert "Last 30 days" in rendered
    assert "Load last 7 days" not in rendered
    assert "Loading last 30 days" in rendered
    assert "We started fetching your GA4 data" in rendered
    assert "load_overview_period" in str(rendered)
    assert "__panel__analytics" not in str(rendered)
    assert "Overview · 123" in rendered
    assert "Property ID: 123" in rendered
    assert "auto_action" not in page.props
    # Startup loading is initiated by the stable sidebar, so refreshing the
    # center panel cannot cancel its own request.


def test_overview_period_selector_offers_requested_ranges(monkeypatch):
    async def cached(ctx, property_id, start_date, end_date):
        return {"loaded_at": "2026-08-11T12:00:00Z", "active_users": 1, "sessions": 1,
                "views": 1, "conversions": 0, "total_revenue": 0.0}

    async def no_load_state(ctx, property_id, start_date, end_date):
        return None

    monkeypatch.setattr(panels, "cached_overview", cached)
    monkeypatch.setattr(panels, "overview_load_state", no_load_state)
    page = asyncio.run(panels._overview(object(), "123", period="12months"))
    rendered = _text(page)

    for label in ("Today", "Yesterday", "Last 7 days", "Last 15 days", "Last 30 days",
                  "Last 90 days", "Last 6 months", "Last 12 months", "This month"):
        assert label in rendered
    assert "Updated 2026-08-11T12:00:00Z · Last 12 months" in rendered


def test_overview_header_uses_property_name_and_google_style_property_id(monkeypatch):
    async def cached(ctx, property_id, start_date, end_date):
        return {"loaded_at": "2026-08-11T12:00:00Z", "active_users": 1, "sessions": 1,
                "views": 1, "conversions": 0, "total_revenue": 0.0}

    async def no_load_state(ctx, property_id, start_date, end_date):
        return None

    monkeypatch.setattr(panels, "cached_overview", cached)
    monkeypatch.setattr(panels, "overview_load_state", no_load_state)
    page = asyncio.run(panels._overview(object(), "123456789", "Example Shop", "30days"))
    rendered = _text(page)

    assert "Overview · Example Shop" in rendered
    assert "Property ID: 123456789" in rendered


def test_completed_empty_period_shows_recommended_available_period(monkeypatch):
    async def no_cached_overview(ctx, property_id, start_date, end_date):
        return None

    async def empty_load_state(ctx, property_id, start_date, end_date):
        return {"status": "no_data", "available_period": "Last 90 days"}

    monkeypatch.setattr(panels, "cached_overview", no_cached_overview)
    monkeypatch.setattr(panels, "overview_load_state", empty_load_state)
    page = asyncio.run(panels._overview(object(), "123", period="12months"))
    rendered = _text(page)

    assert "No data for this period" in rendered
    assert "No GA4 data is available for last 12 months" in rendered
    assert "Choose Last 90 days" in rendered
    assert "auto_action" not in page.props
    assert "Loading last 12 months" not in rendered


def test_sidebar_starts_initial_period_load_without_center_reload_loop(monkeypatch):
    class Store:
        async def query(self, *args, **kwargs):
            return type("Page", (), {"data": []})()

    class Ctx:
        store = Store()

    account = type("Account", (), {"data": {"email": "owner@example.com"}})()

    async def accounts(ctx):
        return [account]

    async def active_account(ctx):
        return account

    async def selected_property(ctx):
        return {"email": "owner@example.com", "property_id": "123"}

    async def properties(ctx, doc):
        return {"ok": True, "properties": [{"property_id": "123", "display_name": "Main"}]}

    async def no_cached(ctx, property_id, start_date, end_date):
        return None

    async def no_load_state(ctx, property_id, start_date, end_date):
        return None

    monkeypatch.setattr(panels, "_accounts", accounts)
    monkeypatch.setattr(panels.ga4, "active_account", active_account)
    monkeypatch.setattr(panels.ga4, "global_selected_property", selected_property)
    monkeypatch.setattr(panels.ga4, "properties", properties)
    monkeypatch.setattr(panels, "cached_overview", no_cached)
    monkeypatch.setattr(panels, "overview_load_state", no_load_state)
    monkeypatch.setattr(panels, "selected_overview_period", lambda ctx, property_id: _async("30days"))

    sidebar = asyncio.run(panels.analytics_nav(Ctx()))
    assert "auto_action" in sidebar.props
    assert "load_overview_period" in str(sidebar.props["auto_action"])


async def _async(value):
    return value
