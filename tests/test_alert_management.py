"""Offline tests for Part C alert-rule management extensions (no live Google calls)."""

import asyncio
from types import SimpleNamespace

from handlers_alerts import list_alert_history, pause_alert_rule, resume_alert_rule, update_alert_rule
from handlers_alerts import test_alert_rule as run_test_alert_rule
from models import AlertIdParams, UpdateAlertParams


class _FakeStore:
    """Minimal in-memory ext_store stand-in: get/update/create/query."""

    def __init__(self, docs):
        self._docs = {doc.id: doc for doc in docs}
        self._history = []

    async def get(self, collection, doc_id):
        return self._docs.get(doc_id)

    async def update(self, collection, doc_id, data):
        doc = SimpleNamespace(id=doc_id, data=data)
        self._docs[doc_id] = doc
        return doc

    async def create(self, collection, data):
        self._history.append(data)
        return SimpleNamespace(id=f"h{len(self._history)}", data=data)

    async def query(self, collection, where=None, limit=100, order_by=None):
        if collection == "google_analytics_alert_history":
            items = self._history
            if where:
                items = [i for i in items if all(i.get(k) == v for k, v in where.items())]
            return SimpleNamespace(data=[SimpleNamespace(id=f"h{i}", data=d) for i, d in enumerate(items[:limit])])
        docs = list(self._docs.values())
        return SimpleNamespace(data=docs[:limit])


def _alert_doc(metric="sessions", condition="decrease_pct", threshold=20.0, schedule="daily", enabled=True):
    return SimpleNamespace(id="a1", data={
        "email": "user@example.com", "property_id": "123456", "metric": metric,
        "condition": condition, "threshold": threshold, "schedule": schedule,
        "enabled": enabled, "last_triggered_at": "",
    })


def _ctx(docs):
    return SimpleNamespace(store=_FakeStore(docs))


def test_update_alert_rule_changes_threshold():
    ctx = _ctx([_alert_doc()])
    result = asyncio.run(update_alert_rule(ctx, UpdateAlertParams(alert_id="a1", threshold=50.0)))
    assert result.status == "success"
    assert result.data.threshold == 50.0


def test_update_alert_rule_rejects_unknown_condition():
    ctx = _ctx([_alert_doc()])
    result = asyncio.run(update_alert_rule(ctx, UpdateAlertParams(alert_id="a1", condition="bogus")))
    assert result.status == "error"
    assert result.error_code == "GA4_ALERT_CONDITION_INVALID"


def test_update_alert_rule_not_found():
    ctx = _ctx([])
    result = asyncio.run(update_alert_rule(ctx, UpdateAlertParams(alert_id="missing", threshold=1.0)))
    assert result.status == "error"
    assert result.error_code == "GA4_ALERT_NOT_FOUND"


def test_pause_alert_rule_disables():
    ctx = _ctx([_alert_doc(enabled=True)])
    result = asyncio.run(pause_alert_rule(ctx, AlertIdParams(alert_id="a1")))
    assert result.status == "success"
    assert result.data.enabled is False


def test_resume_alert_rule_enables():
    ctx = _ctx([_alert_doc(enabled=False)])
    result = asyncio.run(resume_alert_rule(ctx, AlertIdParams(alert_id="a1")))
    assert result.status == "success"
    assert result.data.enabled is True


def test_pause_alert_rule_not_found():
    ctx = _ctx([])
    result = asyncio.run(pause_alert_rule(ctx, AlertIdParams(alert_id="missing")))
    assert result.status == "error"
    assert result.error_code == "GA4_ALERT_NOT_FOUND"


def test_test_alert_rule_reports_would_trigger(monkeypatch):
    import handlers_alerts

    async def fake_evaluate(ctx, doc, account_doc):
        return {"ok": True, "triggered": True, "current": 40.0, "previous": 100.0}

    monkeypatch.setattr(handlers_alerts, "evaluate_alert", fake_evaluate)
    ctx = _ctx([_alert_doc()])
    result = asyncio.run(run_test_alert_rule(ctx, AlertIdParams(alert_id="a1")))
    assert result.status == "success"
    assert result.data.would_trigger is True
    assert result.data.current_value == 40.0


def test_test_alert_rule_not_found():
    ctx = _ctx([])
    result = asyncio.run(run_test_alert_rule(ctx, AlertIdParams(alert_id="missing")))
    assert result.status == "error"
    assert result.error_code == "GA4_ALERT_NOT_FOUND"


def test_list_alert_history_returns_entries():
    ctx = _ctx([_alert_doc()])
    asyncio.run(ctx.store.create("google_analytics_alert_history", {
        "alert_id": "a1", "triggered_at": "2026-08-01T00:00:00Z", "current_value": 40.0, "previous_value": 100.0,
    }))
    result = asyncio.run(list_alert_history(ctx, AlertIdParams(alert_id="a1")))
    assert result.status == "success"
    assert len(result.data.items) == 1
    assert result.data.items[0].current_value == 40.0
