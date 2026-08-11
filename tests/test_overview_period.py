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

    monkeypatch.setattr(panels, "cached_overview", no_cached_overview)
    page = asyncio.run(panels._overview(object(), "123"))
    rendered = _text(page)

    assert "Show results for" in rendered
    assert "Last 30 days" in rendered
    assert "Load last 7 days" not in rendered
    assert "auto_action" in page.props
    auto_action = str(page.props["auto_action"])
    assert "load_overview_period" in auto_action
    assert "30days" in auto_action


def test_overview_period_selector_offers_requested_ranges(monkeypatch):
    async def cached(ctx, property_id, start_date, end_date):
        return {"loaded_at": "2026-08-11T12:00:00Z", "active_users": 1, "sessions": 1,
                "views": 1, "conversions": 0, "total_revenue": 0.0}

    monkeypatch.setattr(panels, "cached_overview", cached)
    page = asyncio.run(panels._overview(object(), "123", "12months"))
    rendered = _text(page)

    for label in ("Today", "Yesterday", "Last 7 days", "Last 15 days", "Last 30 days",
                  "Last 90 days", "Last 6 months", "Last 12 months", "This month"):
        assert label in rendered
    assert "Updated 2026-08-11T12:00:00Z · Last 12 months" in rendered
