"""Offline tests for GA4 alert-rule evaluation logic (no live Google calls)."""

import asyncio
from types import SimpleNamespace

from handlers_alerts import evaluate_alert


class _FakeReport:
    """Fake ga4_client.report()/rows() pipeline: returns a fixed metric value per call."""

    def __init__(self, values_by_range):
        self.values_by_range = values_by_range  # {(start, end): value}
        self.calls = []

    async def report(self, ctx, account_doc, property_id, body):
        start = body["dateRanges"][0]["startDate"]
        end = body["dateRanges"][0]["endDate"]
        self.calls.append((start, end))
        value = self.values_by_range.get((start, end), 0)
        metric_name = body["metrics"][0]["name"]
        return {"ok": True, "data": {
            "metricHeaders": [{"name": metric_name}],
            "rows": [{"dimensionValues": [], "metricValues": [{"value": str(value)}]}],
        }}


def _alert_doc(metric="sessions", condition="decrease_pct", threshold=20.0, schedule="daily"):
    return SimpleNamespace(id="a1", data={
        "email": "user@example.com", "property_id": "123456", "metric": metric,
        "condition": condition, "threshold": threshold, "schedule": schedule,
        "enabled": True, "last_triggered_at": "",
    })


def _patch_ga4(monkeypatch, fake):
    import ga4_client
    monkeypatch.setattr(ga4_client, "report", fake.report)
    # evaluate_alert imports `ga4_client as ga4` inside handlers_alerts — patch that binding too.
    import handlers_alerts
    monkeypatch.setattr(handlers_alerts.ga4, "report", fake.report)


def test_decrease_pct_triggers_when_drop_exceeds_threshold(monkeypatch):
    fake = _FakeReport({("yesterday", "yesterday"): 60, ("2daysAgo", "2daysAgo"): 100})
    _patch_ga4(monkeypatch, fake)
    doc = _alert_doc(condition="decrease_pct", threshold=20.0)
    result = asyncio.run(evaluate_alert(SimpleNamespace(), doc, SimpleNamespace(data={})))
    assert result["ok"] is True
    assert result["triggered"] is True
    assert result["current"] == 60.0
    assert result["previous"] == 100.0


def test_decrease_pct_does_not_trigger_within_threshold(monkeypatch):
    fake = _FakeReport({("yesterday", "yesterday"): 90, ("2daysAgo", "2daysAgo"): 100})
    _patch_ga4(monkeypatch, fake)
    doc = _alert_doc(condition="decrease_pct", threshold=20.0)
    result = asyncio.run(evaluate_alert(SimpleNamespace(), doc, SimpleNamespace(data={})))
    assert result["ok"] is True
    assert result["triggered"] is False


def test_above_value_triggers_on_raw_threshold(monkeypatch):
    fake = _FakeReport({("yesterday", "yesterday"): 500, ("2daysAgo", "2daysAgo"): 500})
    _patch_ga4(monkeypatch, fake)
    doc = _alert_doc(metric="active_users", condition="above_value", threshold=400.0)
    result = asyncio.run(evaluate_alert(SimpleNamespace(), doc, SimpleNamespace(data={})))
    assert result["triggered"] is True


def test_weekly_schedule_uses_seven_day_windows(monkeypatch):
    fake = _FakeReport({("7daysAgo", "yesterday"): 700, ("14daysAgo", "8daysAgo"): 700})
    _patch_ga4(monkeypatch, fake)
    doc = _alert_doc(condition="above_value", threshold=100.0, schedule="weekly")
    result = asyncio.run(evaluate_alert(SimpleNamespace(), doc, SimpleNamespace(data={})))
    assert result["ok"] is True
    assert fake.calls == [("7daysAgo", "yesterday"), ("14daysAgo", "8daysAgo")]


def test_misconfigured_alert_is_reported_without_crashing(monkeypatch):
    doc = _alert_doc()
    doc.data["property_id"] = ""  # missing property -> can't run a report
    result = asyncio.run(evaluate_alert(SimpleNamespace(), doc, SimpleNamespace(data={})))
    assert result["ok"] is False
    assert "misconfigured" in result["error"].lower()
