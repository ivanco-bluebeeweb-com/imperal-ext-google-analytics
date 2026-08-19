"""Plausible Scenario Tests (PST) -- Google Analytics.

Method: Docs/session-notes/SCENARIO_TESTING_STANDARD.md. This app has 59
chat functions and 104 existing tests across 13 files with real breadth
(admin, alerts, reports, accounts, panels, pricing). A name-based coverage
audit (does any test file call this exact function name?) found 12
functions genuinely never exercised anywhere:

  Reports (Part A):  get_top_referrers, get_landing_pages_report,
                      get_conversions_report, get_ecommerce_overview,
                      get_geo_breakdown, get_device_breakdown,
                      get_campaign_performance
  Alerts (Part C):   create_alert_rule, list_alert_rules, delete_alert_rule
                      (destructive!)
  Admin:             list_properties
  Diagnostics:       debug_dump_raw_accounts, debug_purge_unresolved_accounts

This file targets exactly those, following the existing suite's own
FakeStore/monkeypatch conventions (test_reports.py, test_alert_management.py).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import handlers_reports as hr
import handlers_alerts as ha
import handlers as h
import handlers_accounts as hacc
from models import (
    RunCustomReportParams, CreateAlertParams, AccountParam, AlertIdParams, AccountAction,
)


def _account_doc(email="user@example.com", is_active=True):
    return SimpleNamespace(id="acc1", data={"email": email, "is_active": is_active})


class _FakeReportStore:
    """Mirrors test_reports.py's _FakeStore -- account doc + property selection."""

    def __init__(self, docs, selection=None):
        self._docs = {doc.id: doc for doc in docs}
        self._selection = selection or []

    async def query(self, collection, where=None, limit=100):
        if collection == "google_analytics_selections":
            return SimpleNamespace(data=self._selection[:limit])
        docs = list(self._docs.values())
        if where:
            docs = [d for d in docs if all((d.data or {}).get(k) == v for k, v in where.items())]
        return SimpleNamespace(data=docs[:limit])


def _report_ctx(property_id="123456"):
    doc = _account_doc()
    selection = [SimpleNamespace(id="s1", data={"email": "user@example.com", "property_id": property_id})]
    return SimpleNamespace(store=_FakeReportStore([doc], selection))


REPORT_BODY = {
    "dimensionHeaders": [{"name": "sessionSource"}],
    "metricHeaders": [{"name": "sessions"}],
    "rows": [{"dimensionValues": [{"value": "google"}], "metricValues": [{"value": "10"}]}],
}


def _patch_ga4_report(monkeypatch, result):
    async def _fake_resolve(ctx, account):
        return {"ok": True, "account": _account_doc()}

    async def _fake_report(*args, **kwargs):
        return result

    monkeypatch.setattr(hr.ga4, "resolve_account", _fake_resolve)
    monkeypatch.setattr(hr.ga4, "report", _fake_report)


# ── happy: every previously-untested canned report ─────────────────────────

def test_happy_get_top_referrers(monkeypatch):
    _patch_ga4_report(monkeypatch, {"ok": True, "data": REPORT_BODY})
    ctx = _report_ctx()
    result = asyncio.run(hr.get_top_referrers(
        ctx, RunCustomReportParams(account="", property_id="", start_date="7daysAgo", end_date="today", limit=10)))
    assert result.error is None
    assert result.data.items


def test_happy_get_landing_pages_report(monkeypatch):
    _patch_ga4_report(monkeypatch, {"ok": True, "data": REPORT_BODY})
    ctx = _report_ctx()
    result = asyncio.run(hr.get_landing_pages_report(
        ctx, RunCustomReportParams(account="", property_id="", start_date="7daysAgo", end_date="today", limit=10)))
    assert result.error is None


def test_happy_get_conversions_report(monkeypatch):
    _patch_ga4_report(monkeypatch, {"ok": True, "data": REPORT_BODY})
    ctx = _report_ctx()
    result = asyncio.run(hr.get_conversions_report(
        ctx, RunCustomReportParams(account="", property_id="", start_date="7daysAgo", end_date="today", limit=10)))
    assert result.error is None


def test_happy_get_ecommerce_overview(monkeypatch):
    _patch_ga4_report(monkeypatch, {"ok": True, "data": REPORT_BODY})
    ctx = _report_ctx()
    result = asyncio.run(hr.get_ecommerce_overview(
        ctx, RunCustomReportParams(account="", property_id="", start_date="7daysAgo", end_date="today", limit=10)))
    assert result.error is None


def test_happy_get_geo_breakdown(monkeypatch):
    _patch_ga4_report(monkeypatch, {"ok": True, "data": REPORT_BODY})
    ctx = _report_ctx()
    result = asyncio.run(hr.get_geo_breakdown(
        ctx, RunCustomReportParams(account="", property_id="", start_date="7daysAgo", end_date="today", limit=10)))
    assert result.error is None


def test_happy_get_device_breakdown(monkeypatch):
    _patch_ga4_report(monkeypatch, {"ok": True, "data": REPORT_BODY})
    ctx = _report_ctx()
    result = asyncio.run(hr.get_device_breakdown(
        ctx, RunCustomReportParams(account="", property_id="", start_date="7daysAgo", end_date="today", limit=10)))
    assert result.error is None


def test_happy_get_campaign_performance(monkeypatch):
    _patch_ga4_report(monkeypatch, {"ok": True, "data": REPORT_BODY})
    ctx = _report_ctx()
    result = asyncio.run(hr.get_campaign_performance(
        ctx, RunCustomReportParams(account="", property_id="", start_date="7daysAgo", end_date="today", limit=10)))
    assert result.error is None


# ── error: report call fails cleanly when no property is selected ──────────

def test_error_report_without_property_selected(monkeypatch):
    async def _fake_resolve(ctx, account):
        return {"ok": True, "account": _account_doc()}
    monkeypatch.setattr(hr.ga4, "resolve_account", _fake_resolve)
    ctx = SimpleNamespace(store=_FakeReportStore([_account_doc()], selection=[]))
    result = asyncio.run(hr.get_top_referrers(
        ctx, RunCustomReportParams(account="", property_id="", start_date="7daysAgo", end_date="today", limit=10)))
    assert result.error is not None


# ── alerts: create -> list -> delete (destructive) full lifecycle ──────────

class _FakeAlertStore:
    def __init__(self):
        self._docs = {}
        self._n = 0

    async def create(self, collection, data):
        self._n += 1
        doc_id = f"a{self._n}"
        doc = SimpleNamespace(id=doc_id, data=data)
        self._docs[doc_id] = doc
        return doc

    async def get(self, collection, doc_id):
        return self._docs.get(doc_id)

    async def delete(self, collection, doc_id):
        self._docs.pop(doc_id, None)

    async def query(self, collection, where=None, limit=100, order_by=None):
        docs = list(self._docs.values())
        if where:
            docs = [d for d in docs if all((d.data or {}).get(k) == v for k, v in where.items())]
        return SimpleNamespace(data=docs[:limit])


def _alert_ctx():
    return SimpleNamespace(store=_FakeAlertStore())


def _patch_alert_resolve(monkeypatch):
    async def _fake_resolve(ctx, account):
        return {"ok": True, "account": _account_doc()}

    async def _fake_properties(ctx, doc):
        return {"ok": True, "properties": [{"property_id": "123456", "title": "Example", "account": "user@example.com"}]}

    monkeypatch.setattr(ha.ga4, "resolve_account", _fake_resolve)
    monkeypatch.setattr(ha.ga4, "properties", _fake_properties)


def test_happy_create_list_delete_alert_rule_full_lifecycle(monkeypatch):
    """The one destructive function in this gap (delete_alert_rule) --
    exercised end to end: create it, confirm it's listed, delete it,
    confirm it's gone."""
    _patch_alert_resolve(monkeypatch)
    ctx = _alert_ctx()

    created = asyncio.run(ha.create_alert_rule(ctx, CreateAlertParams(
        account="", property_id="123456", metric="sessions", condition="decrease_pct",
        threshold=20.0, schedule="daily")))
    assert created.error is None
    alert_id = created.data.id

    listed = asyncio.run(ha.list_alert_rules(ctx, AccountParam(account="")))
    assert listed.error is None
    assert any(a.id == alert_id for a in listed.data.items)

    deleted = asyncio.run(ha.delete_alert_rule(ctx, AlertIdParams(alert_id=alert_id)))
    assert deleted.error is None

    listed_after = asyncio.run(ha.list_alert_rules(ctx, AccountParam(account="")))
    assert not any(a.id == alert_id for a in listed_after.data.items)


def test_error_delete_alert_rule_not_found(monkeypatch):
    _patch_alert_resolve(monkeypatch)
    ctx = _alert_ctx()
    result = asyncio.run(ha.delete_alert_rule(ctx, AlertIdParams(alert_id="ghost-alert")))
    assert result.error is not None


def test_error_create_alert_rule_invalid_metric(monkeypatch):
    """metric is validated against ALERT_METRICS -- an unknown metric must
    be rejected, not silently create a rule that will never fire."""
    _patch_alert_resolve(monkeypatch)
    ctx = _alert_ctx()
    result = asyncio.run(ha.create_alert_rule(ctx, CreateAlertParams(
        account="", property_id="123456", metric="not_a_real_metric", condition="decrease_pct",
        threshold=20.0, schedule="daily")))
    assert result.error is not None


# ── list_properties (Admin) ─────────────────────────────────────────────────

def test_happy_list_properties(monkeypatch):
    async def _fake_resolve(ctx, account):
        return {"ok": True, "account": _account_doc()}

    async def _fake_properties(ctx, doc):
        return {"ok": True, "properties": [
            {"property_id": "123456", "title": "Example Site", "account": "user@example.com"},
        ]}

    monkeypatch.setattr(h.ga4, "resolve_account", _fake_resolve)
    monkeypatch.setattr(h.ga4, "properties", _fake_properties)
    ctx = SimpleNamespace(store=_FakeReportStore([_account_doc()], selection=[]))
    result = asyncio.run(h.list_properties(ctx, AccountParam(account="")))
    assert result.error is None
    assert len(result.data.items) == 1


def test_error_list_properties_no_connected_account(monkeypatch):
    async def _fake_resolve(ctx, account):
        return {"ok": False, "error": "No connected Google account.", "code": "NOT_CONNECTED"}
    monkeypatch.setattr(h.ga4, "resolve_account", _fake_resolve)
    ctx = SimpleNamespace(store=_FakeReportStore([], selection=[]))
    result = asyncio.run(h.list_properties(ctx, AccountParam(account="")))
    assert result.error is not None


# ── diagnostic/debug functions ──────────────────────────────────────────────

def test_happy_debug_dump_raw_accounts_lists_every_stored_doc():
    """Read-only diagnostic -- never calls Google, just echoes store state
    verbatim including 'broken' rows the normal listing hides."""
    class _Store:
        async def query(self, collection, limit=100):
            return SimpleNamespace(data=[
                SimpleNamespace(id="acc1", data={"email": "user@example.com", "provider": "google",
                                                  "is_active": True, "access_token": "tok"}),
                SimpleNamespace(id="acc2", data={"email": "", "provider": "google", "is_active": False}),
            ])
    ctx = SimpleNamespace(store=_Store())
    result = asyncio.run(hacc.debug_dump_raw_accounts(ctx, AccountAction(account="")))
    assert result.error is None
    assert len(result.data.items) == 2


def test_happy_debug_purge_unresolved_accounts_removes_only_emailless_rows():
    """Destructive-flavored cleanup helper -- must remove ONLY rows with no
    usable email, never a genuinely connected account."""
    removed_ids = []

    class _Store:
        def __init__(self):
            self.docs = [
                SimpleNamespace(id="good1", data={"email": "user@example.com", "provider": "google"}),
                SimpleNamespace(id="broken1", data={"email": "", "provider": "google"}),
                SimpleNamespace(id="broken2", data={"provider": "google"}),
            ]

        async def query(self, collection, limit=100):
            return SimpleNamespace(data=self.docs)

        async def delete(self, collection, doc_id):
            removed_ids.append(doc_id)

    ctx = SimpleNamespace(store=_Store())
    result = asyncio.run(hacc.debug_purge_unresolved_accounts(ctx, AccountAction(account="")))
    assert result.error is None
    assert "good1" not in removed_ids
    assert "broken1" in removed_ids
    assert "broken2" in removed_ids
