"""Offline tests for Part A report functions (no live Google calls)."""

import asyncio
from types import SimpleNamespace

from handlers_reports import (batch_run_reports, check_report_compatibility, compare_periods, export_report_csv,
                              get_report_metadata, get_traffic_by_channel, run_custom_report, run_pivot_report,
                              run_realtime_report)
from models import (BatchReportSpec, BatchRunReportsParams, CheckCompatibilityParams, ComparePeriodsParams,
                    ExportReportCsvParams, ReportMetadataParams, RunCustomReportParams, RunPivotReportParams,
                    RunRealtimeReportParams)


def _account_doc():
    return SimpleNamespace(id="acc1", data={"email": "user@example.com", "is_active": True})


class _FakeStore:
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


def _ctx(property_id="123456"):
    doc = _account_doc()
    selection = [SimpleNamespace(id="s1", data={"email": "user@example.com", "property_id": property_id})]
    return SimpleNamespace(store=_FakeStore([doc], selection))


REPORT_BODY = {
    "dimensionHeaders": [{"name": "pagePath"}],
    "metricHeaders": [{"name": "activeUsers"}],
    "rows": [{"dimensionValues": [{"value": "/home"}], "metricValues": [{"value": "42"}]}],
}


def _patch_report(monkeypatch, body=None, ok=True):
    import handlers_reports

    async def fake_report(ctx, doc, pid, req_body):
        return {"ok": ok, "data": body or REPORT_BODY} if ok else {"ok": False, "error": "boom", "code": "RESPONSE_UNEXPECTED"}

    monkeypatch.setattr(handlers_reports.ga4, "report", fake_report)


def test_run_custom_report_maps_rows(monkeypatch):
    _patch_report(monkeypatch)
    ctx = _ctx()
    result = asyncio.run(run_custom_report(ctx, RunCustomReportParams(dimensions=["pagePath"], metrics=["activeUsers"])))
    assert result.status == "success"
    assert len(result.data.items) == 1
    assert result.data.items[0].values["pagePath"] == "/home"


def test_run_custom_report_requires_metrics(monkeypatch):
    _patch_report(monkeypatch)
    ctx = _ctx()
    result = asyncio.run(run_custom_report(ctx, RunCustomReportParams(dimensions=["pagePath"], metrics=[])))
    assert result.status == "error"
    assert result.error_code == "VALIDATION_FAILED"


def test_run_custom_report_no_property_selected():
    ctx = SimpleNamespace(store=_FakeStore([_account_doc()], selection=[]))
    result = asyncio.run(run_custom_report(ctx, RunCustomReportParams(metrics=["activeUsers"])))
    assert result.status == "error"
    assert result.error_code == "VALIDATION_FAILED"


def test_run_realtime_report(monkeypatch):
    import handlers_reports

    async def fake_realtime(ctx, doc, pid, body):
        return {"ok": True, "data": REPORT_BODY}

    monkeypatch.setattr(handlers_reports.ga4, "realtime_report", fake_realtime)
    ctx = _ctx()
    result = asyncio.run(run_realtime_report(ctx, RunRealtimeReportParams(dimensions=["country"])))
    assert result.status == "success"
    assert len(result.data.items) == 1


def test_run_pivot_report(monkeypatch):
    import handlers_reports

    async def fake_pivot(ctx, doc, pid, body):
        assert "pivots" in body
        return {"ok": True, "data": REPORT_BODY}

    monkeypatch.setattr(handlers_reports.ga4, "pivot_report", fake_pivot)
    ctx = _ctx()
    result = asyncio.run(run_pivot_report(ctx, RunPivotReportParams(row_dimension="country", column_dimension="deviceCategory")))
    assert result.status == "success"


def test_batch_run_reports_rejects_more_than_five(monkeypatch):
    _patch_report(monkeypatch)
    ctx = _ctx()
    specs = [BatchReportSpec(dimensions=["pagePath"], metrics=["activeUsers"]) for _ in range(6)]
    result = asyncio.run(batch_run_reports(ctx, BatchRunReportsParams(reports=specs)))
    assert result.status == "error"
    assert result.error_code == "VALIDATION_FAILED"


def test_batch_run_reports_maps_multiple_reports(monkeypatch):
    import handlers_reports

    async def fake_batch(ctx, doc, pid, requests_body):
        return {"ok": True, "data": {"reports": [REPORT_BODY, REPORT_BODY]}}

    monkeypatch.setattr(handlers_reports.ga4, "batch_reports", fake_batch)
    ctx = _ctx()
    specs = [BatchReportSpec(dimensions=["pagePath"], metrics=["activeUsers"]) for _ in range(2)]
    result = asyncio.run(batch_run_reports(ctx, BatchRunReportsParams(reports=specs)))
    assert result.status == "success"
    assert len(result.data.items) == 2


def test_check_report_compatibility(monkeypatch):
    import handlers_reports

    async def fake_compat(ctx, doc, pid, body):
        return {"ok": True, "data": {
            "dimensionCompatibilities": [{"dimensionMetadata": {"apiName": "pagePath"}, "compatibility": "COMPATIBLE"}],
            "metricCompatibilities": [{"metricMetadata": {"apiName": "activeUsers"}, "compatibility": "COMPATIBLE"}],
        }}

    monkeypatch.setattr(handlers_reports.ga4, "check_compatibility", fake_compat)
    ctx = _ctx()
    result = asyncio.run(check_report_compatibility(ctx, CheckCompatibilityParams(dimensions=["pagePath"], metrics=["activeUsers"])))
    assert result.status == "success"
    assert result.data.dimensions[0].compatibility == "COMPATIBLE"


def test_get_report_metadata(monkeypatch):
    import handlers_reports

    async def fake_meta(ctx, doc, pid):
        return {"ok": True, "data": {
            "dimensions": [{"apiName": "pagePath", "uiName": "Page path"}],
            "metrics": [{"apiName": "activeUsers", "uiName": "Active users"}],
        }}

    monkeypatch.setattr(handlers_reports.ga4, "report_metadata", fake_meta)
    ctx = _ctx()
    result = asyncio.run(get_report_metadata(ctx, ReportMetadataParams()))
    assert result.status == "success"
    assert len(result.data.dimensions) == 1
    assert len(result.data.metrics) == 1


def test_get_traffic_by_channel(monkeypatch):
    body = {
        "dimensionHeaders": [{"name": "sessionDefaultChannelGroup"}],
        "metricHeaders": [{"name": "sessions"}, {"name": "activeUsers"}, {"name": "conversions"}],
        "rows": [{"dimensionValues": [{"value": "Organic Search"}],
                 "metricValues": [{"value": "10"}, {"value": "8"}, {"value": "1"}]}],
    }
    _patch_report(monkeypatch, body=body)
    ctx = _ctx()
    result = asyncio.run(get_traffic_by_channel(ctx, RunCustomReportParams()))
    assert result.status == "success"
    assert result.data.items[0].values["sessionDefaultChannelGroup"] == "Organic Search"


def test_compare_periods_computes_percent_change(monkeypatch):
    import handlers_reports

    calls = []

    async def fake_report(ctx, doc, pid, body):
        start = body["dateRanges"][0]["startDate"]
        calls.append(start)
        value = "50" if start == "7daysAgo" else "100"
        return {"ok": True, "data": {
            "metricHeaders": [{"name": "activeUsers"}],
            "rows": [{"dimensionValues": [], "metricValues": [{"value": value}]}],
        }}

    monkeypatch.setattr(handlers_reports.ga4, "report", fake_report)
    ctx = _ctx()
    params = ComparePeriodsParams(start_date="7daysAgo", end_date="yesterday",
                                  compare_start_date="14daysAgo", compare_end_date="8daysAgo",
                                  metrics=["activeUsers"])
    result = asyncio.run(compare_periods(ctx, params))
    assert result.status == "success"
    comparison = result.data.metrics[0]
    assert comparison.current_value == 50.0
    assert comparison.previous_value == 100.0
    assert comparison.change_pct == -50.0


def test_export_report_csv_produces_header_and_rows(monkeypatch):
    _patch_report(monkeypatch)
    ctx = _ctx()
    result = asyncio.run(export_report_csv(ctx, ExportReportCsvParams(dimensions=["pagePath"], metrics=["activeUsers"])))
    assert result.status == "success"
    assert result.data.row_count == 1
    assert "pagePath" in result.data.csv
    assert "/home" in result.data.csv


def test_report_error_is_surfaced(monkeypatch):
    _patch_report(monkeypatch, ok=False)
    ctx = _ctx()
    result = asyncio.run(run_custom_report(ctx, RunCustomReportParams(metrics=["activeUsers"])))
    assert result.status == "error"
