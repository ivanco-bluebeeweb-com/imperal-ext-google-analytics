"""Part A -- custom and canned GA4 reports (Data API v1beta).

Every function here only ever calls Google's read-only Data API endpoints
(runReport, batchRunReports, runPivotReport, runRealtimeReport,
checkCompatibility, getMetadata). Nothing here writes to Google Analytics.
"""

from __future__ import annotations

import csv
import io

from imperal_sdk import ActionResult

import ga4_client as ga4
from app import chat
from models import (BatchRunReportsParams, CheckCompatibilityParams, CompatibilityCheck, CompatibilityItem,
                    ComparePeriodsParams, ExportReportCsvParams, MetadataField, MetricComparison, PeriodComparison,
                    ReportCsv, ReportMetadata, ReportMetadataParams, ReportRow, ReportRowList,
                    RunCustomReportParams, RunPivotReportParams, RunRealtimeReportParams)


def _error(out: dict) -> ActionResult:
    return ActionResult.error(out.get("error") or "Google Analytics request failed.",
                              retryable=bool(out.get("retryable")), code=out.get("code") or "RESPONSE_UNEXPECTED")


async def _resolve(ctx, account: str, property_id: str):
    """Resolve the connected account + effective property id, or an error dict."""
    resolved = await ga4.resolve_account(ctx, account)
    if not resolved.get("ok"):
        return None, None, resolved
    doc = resolved["account"]
    email = str((doc.data or {}).get("email") or "")
    pid = property_id or await ga4.selected_property_id(ctx, email)
    if not pid:
        return None, None, ga4.fail("VALIDATION_FAILED", "No GA4 property selected. Pass property_id or call select_property first.")
    return doc, pid, None


def _row_list(report_body: dict, limit: int) -> ReportRowList:
    items = [ReportRow(id=str(i), title=f"Row {i + 1}", values=row)
             for i, row in enumerate(ga4.rows(report_body)[:limit])]
    return ReportRowList(items=items, total=len(items))


@chat.function("run_custom_report", "Run a GA4 report with any dimensions and metrics you choose, for a date range.",
               action_type="read", data_model=ReportRowList)
async def run_custom_report(ctx, params: RunCustomReportParams) -> ActionResult:
    """Run any dimension/metric combination through Google's runReport endpoint."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    if not params.metrics:
        return ActionResult.error("Pass at least one metric.", retryable=False, code="VALIDATION_FAILED")
    body = {
        "dateRanges": [{"startDate": params.start_date, "endDate": params.end_date}],
        "dimensions": [{"name": d} for d in params.dimensions],
        "metrics": [{"name": m} for m in params.metrics],
        "limit": str(max(1, min(params.limit, 100))),
    }
    out = await ga4.report(ctx, doc, pid, body)
    if not out.get("ok"):
        return _error(out)
    result = _row_list(out["data"], params.limit)
    return ActionResult.success(result, summary=f"{len(result)} rows for property {pid}.")


@chat.function("run_realtime_report", "Read GA4 realtime data -- active users and events from roughly the last 30 minutes.",
               action_type="read", data_model=ReportRowList)
async def run_realtime_report(ctx, params: RunRealtimeReportParams) -> ActionResult:
    """Read GA4 realtime data via runRealtimeReport -- events from roughly the last 30 minutes."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {
        "dimensions": [{"name": d} for d in params.dimensions],
        "metrics": [{"name": m} for m in (params.metrics or ["activeUsers"])],
        "limit": str(max(1, min(params.limit, 100))),
    }
    out = await ga4.realtime_report(ctx, doc, pid, body)
    if not out.get("ok"):
        return _error(out)
    result = _row_list(out["data"], params.limit)
    return ActionResult.success(result, summary=f"{len(result)} realtime rows for property {pid}.")


@chat.function("run_pivot_report", "Run a GA4 report shaped as a pivot table: one dimension as rows, another as columns.",
               action_type="read", data_model=ReportRowList)
async def run_pivot_report(ctx, params: RunPivotReportParams) -> ActionResult:
    """Run a report shaped as a pivot table via runPivotReport."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {
        "dateRanges": [{"startDate": params.start_date, "endDate": params.end_date}],
        "dimensions": [{"name": params.row_dimension}, {"name": params.column_dimension}],
        "metrics": [{"name": m} for m in params.metrics],
        "pivots": [
            {"fieldNames": [params.row_dimension], "limit": str(max(1, min(params.limit, 100)))},
            {"fieldNames": [params.column_dimension], "limit": "20"},
        ],
    }
    out = await ga4.pivot_report(ctx, doc, pid, body)
    if not out.get("ok"):
        return _error(out)
    result = _row_list(out["data"], params.limit)
    return ActionResult.success(result, summary=f"Pivot of {params.row_dimension} x {params.column_dimension} for property {pid}.")


@chat.function("batch_run_reports", "Run up to 5 GA4 reports (different dimension/metric combinations) in one call.",
               action_type="read", data_model=ReportRowList)
async def batch_run_reports(ctx, params: BatchRunReportsParams) -> ActionResult:
    """Run several report specs in one batchRunReports call."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    if not params.reports:
        return ActionResult.error("Pass at least one report spec.", retryable=False, code="VALIDATION_FAILED")
    if len(params.reports) > 5:
        return ActionResult.error("Google allows at most 5 reports per batch.", retryable=False, code="VALIDATION_FAILED")
    requests_body = [{
        "dateRanges": [{"startDate": params.start_date, "endDate": params.end_date}],
        "dimensions": [{"name": d} for d in spec.dimensions],
        "metrics": [{"name": m} for m in spec.metrics],
        "limit": str(max(1, min(params.limit, 100))),
    } for spec in params.reports]
    out = await ga4.batch_reports(ctx, doc, pid, requests_body)
    if not out.get("ok"):
        return _error(out)
    items = []
    for i, one_report in enumerate(out["data"].get("reports") or []):
        for j, row in enumerate(ga4.rows(one_report)[:params.limit]):
            items.append(ReportRow(id=f"{i}-{j}", title=f"Report {i + 1} row {j + 1}", values=row))
    result = ReportRowList(items=items, total=len(items))
    return ActionResult.success(result, summary=f"{len(params.reports)} reports, {len(items)} total rows for property {pid}.")


@chat.function("check_report_compatibility", "Check whether chosen GA4 dimensions and metrics can be used together before running a report.",
               action_type="read", data_model=CompatibilityCheck)
async def check_report_compatibility(ctx, params: CheckCompatibilityParams) -> ActionResult:
    """Verify a dimension/metric combination is valid before spending a real report call on it."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {
        "dimensions": [{"name": d} for d in params.dimensions],
        "metrics": [{"name": m} for m in params.metrics],
        "compatibilityFilter": "COMPATIBLE",
    }
    out = await ga4.check_compatibility(ctx, doc, pid, body)
    if not out.get("ok"):
        return _error(out)
    data = out["data"]
    dims = [CompatibilityItem(id=d.get("dimensionMetadata", {}).get("apiName", ""),
                              title=d.get("dimensionMetadata", {}).get("apiName", ""),
                              api_name=d.get("dimensionMetadata", {}).get("apiName", ""),
                              compatibility=str(d.get("compatibility") or ""))
            for d in data.get("dimensionCompatibilities") or []]
    mets = [CompatibilityItem(id=m.get("metricMetadata", {}).get("apiName", ""),
                              title=m.get("metricMetadata", {}).get("apiName", ""),
                              api_name=m.get("metricMetadata", {}).get("apiName", ""),
                              compatibility=str(m.get("compatibility") or ""))
            for m in data.get("metricCompatibilities") or []]
    result = CompatibilityCheck(id=pid, title=f"Compatibility for {pid}", property_id=pid, dimensions=dims, metrics=mets)
    return ActionResult.success(result, summary=f"{len(dims)} dimensions, {len(mets)} metrics checked.")


@chat.function("get_report_metadata", "List which GA4 dimensions and metrics a property can report on.",
               action_type="read", data_model=ReportMetadata)
async def get_report_metadata(ctx, params: ReportMetadataParams) -> ActionResult:
    """List every dimension and metric a property can report on, via getMetadata."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.report_metadata(ctx, doc, pid)
    if not out.get("ok"):
        return _error(out)
    data = out["data"]
    dims = [MetadataField(id=d.get("apiName", ""), title=d.get("uiName", d.get("apiName", "")),
                          api_name=str(d.get("apiName") or ""), ui_name=str(d.get("uiName") or ""),
                          description=str(d.get("description") or "")) for d in data.get("dimensions") or []]
    mets = [MetadataField(id=m.get("apiName", ""), title=m.get("uiName", m.get("apiName", "")),
                          api_name=str(m.get("apiName") or ""), ui_name=str(m.get("uiName") or ""),
                          description=str(m.get("description") or "")) for m in data.get("metrics") or []]
    result = ReportMetadata(id=pid, title=f"Metadata for {pid}", property_id=pid, dimensions=dims, metrics=mets)
    return ActionResult.success(result, summary=f"{len(dims)} dimensions, {len(mets)} metrics available.")


async def _channel_report(ctx, account: str, property_id: str, start_date: str, end_date: str, limit: int,
                          dimension: str, metrics: list[str]):
    doc, pid, err = await _resolve(ctx, account, property_id)
    if err:
        return None, err
    body = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "dimensions": [{"name": dimension}],
        "metrics": [{"name": m} for m in metrics],
        "limit": str(max(1, min(limit, 100))),
        "orderBys": [{"metric": {"metricName": metrics[0]}, "desc": True}],
    }
    out = await ga4.report(ctx, doc, pid, body)
    if not out.get("ok"):
        return None, out
    return (pid, out["data"]), None


@chat.function("get_traffic_by_channel", "Read traffic broken down by channel (organic search, paid, direct, referral, social).",
               action_type="read", data_model=ReportRowList)
async def get_traffic_by_channel(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: sessions/users/conversions grouped by default channel group."""
    payload, err = await _channel_report(ctx, params.account, params.property_id, params.start_date, params.end_date,
                                         params.limit, "sessionDefaultChannelGroup", ["sessions", "activeUsers", "conversions"])
    if err:
        return _error(err)
    pid, data = payload
    result = _row_list(data, params.limit)
    return ActionResult.success(result, summary=f"Traffic by channel for property {pid}.")


@chat.function("get_top_pages", "Read the most-visited pages for a property over a date range.",
               action_type="read", data_model=ReportRowList)
async def get_top_pages(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: page views/users grouped by page path, most-visited first."""
    payload, err = await _channel_report(ctx, params.account, params.property_id, params.start_date, params.end_date,
                                         params.limit, "pagePath", ["screenPageViews", "activeUsers"])
    if err:
        return _error(err)
    pid, data = payload
    result = _row_list(data, params.limit)
    return ActionResult.success(result, summary=f"Top pages for property {pid}.")


@chat.function("get_top_referrers", "Read the top external sites sending traffic to a property.",
               action_type="read", data_model=ReportRowList)
async def get_top_referrers(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: sessions/users grouped by session source."""
    payload, err = await _channel_report(ctx, params.account, params.property_id, params.start_date, params.end_date,
                                         params.limit, "sessionSource", ["sessions", "activeUsers"])
    if err:
        return _error(err)
    pid, data = payload
    result = _row_list(data, params.limit)
    return ActionResult.success(result, summary=f"Top referrers for property {pid}.")


@chat.function("get_landing_pages_report", "Read which pages visitors land on first, with sessions and bounce rate.",
               action_type="read", data_model=ReportRowList)
async def get_landing_pages_report(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: sessions/bounce rate grouped by landing page."""
    payload, err = await _channel_report(ctx, params.account, params.property_id, params.start_date, params.end_date,
                                         params.limit, "landingPage", ["sessions", "bounceRate"])
    if err:
        return _error(err)
    pid, data = payload
    result = _row_list(data, params.limit)
    return ActionResult.success(result, summary=f"Landing pages for property {pid}.")


@chat.function("get_conversions_report", "Read GA4 key events (conversions) by event name, with counts.",
               action_type="read", data_model=ReportRowList)
async def get_conversions_report(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: event counts and key-event conversions grouped by event name."""
    payload, err = await _channel_report(ctx, params.account, params.property_id, params.start_date, params.end_date,
                                         params.limit, "eventName", ["eventCount", "conversions"])
    if err:
        return _error(err)
    pid, data = payload
    result = _row_list(data, params.limit)
    return ActionResult.success(result, summary=f"Conversions report for property {pid}.")


@chat.function("get_ecommerce_overview", "Read e-commerce headline numbers -- transactions and revenue -- if the property tracks purchases.",
               action_type="read", data_model=ReportRowList)
async def get_ecommerce_overview(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: transactions and revenue totals, if the property tracks e-commerce."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {
        "dateRanges": [{"startDate": params.start_date, "endDate": params.end_date}],
        "metrics": [{"name": m} for m in ("transactions", "purchaseRevenue", "totalRevenue", "itemRevenue")],
    }
    out = await ga4.report(ctx, doc, pid, body)
    if not out.get("ok"):
        return _error(out)
    result = _row_list(out["data"], params.limit)
    return ActionResult.success(result, summary=f"E-commerce overview for property {pid}.")


@chat.function("get_geo_breakdown", "Read traffic broken down by country and city.",
               action_type="read", data_model=ReportRowList)
async def get_geo_breakdown(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: users/sessions grouped by country and city."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {
        "dateRanges": [{"startDate": params.start_date, "endDate": params.end_date}],
        "dimensions": [{"name": "country"}, {"name": "city"}],
        "metrics": [{"name": "activeUsers"}, {"name": "sessions"}],
        "limit": str(max(1, min(params.limit, 100))),
        "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}],
    }
    out = await ga4.report(ctx, doc, pid, body)
    if not out.get("ok"):
        return _error(out)
    result = _row_list(out["data"], params.limit)
    return ActionResult.success(result, summary=f"Geo breakdown for property {pid}.")


@chat.function("get_device_breakdown", "Read traffic broken down by device category, operating system, and browser.",
               action_type="read", data_model=ReportRowList)
async def get_device_breakdown(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: users/sessions grouped by device category, OS, and browser."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {
        "dateRanges": [{"startDate": params.start_date, "endDate": params.end_date}],
        "dimensions": [{"name": "deviceCategory"}, {"name": "operatingSystem"}, {"name": "browser"}],
        "metrics": [{"name": "activeUsers"}, {"name": "sessions"}],
        "limit": str(max(1, min(params.limit, 100))),
        "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}],
    }
    out = await ga4.report(ctx, doc, pid, body)
    if not out.get("ok"):
        return _error(out)
    result = _row_list(out["data"], params.limit)
    return ActionResult.success(result, summary=f"Device breakdown for property {pid}.")


@chat.function("get_campaign_performance", "Read traffic and conversions broken down by marketing campaign (UTM campaign).",
               action_type="read", data_model=ReportRowList)
async def get_campaign_performance(ctx, params: RunCustomReportParams) -> ActionResult:
    """Canned report: sessions/conversions/revenue grouped by UTM campaign name."""
    payload, err = await _channel_report(ctx, params.account, params.property_id, params.start_date, params.end_date,
                                         params.limit, "sessionCampaignName", ["sessions", "conversions", "totalRevenue"])
    if err:
        return _error(err)
    pid, data = payload
    result = _row_list(data, params.limit)
    return ActionResult.success(result, summary=f"Campaign performance for property {pid}.")


@chat.function("compare_periods", "Compare headline GA4 metrics between a period and the equivalent previous period, with the percent change.",
               action_type="read", data_model=PeriodComparison)
async def compare_periods(ctx, params: ComparePeriodsParams) -> ActionResult:
    """Compare headline metrics between two date ranges and compute percent change."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    metrics = params.metrics or ["activeUsers", "sessions", "conversions"]

    async def _totals(start: str, end: str) -> dict[str, float]:
        body = {"dateRanges": [{"startDate": start, "endDate": end}], "metrics": [{"name": m} for m in metrics]}
        out = await ga4.report(ctx, doc, pid, body)
        if not out.get("ok"):
            return None
        rows_out = ga4.rows(out["data"])
        if not rows_out:
            return {m: 0.0 for m in metrics}
        return {m: float(rows_out[0].get(m) or 0.0) for m in metrics}

    current = await _totals(params.start_date, params.end_date)
    if current is None:
        return _error(ga4.fail("RESPONSE_UNEXPECTED"))
    previous = await _totals(params.compare_start_date, params.compare_end_date)
    if previous is None:
        return _error(ga4.fail("RESPONSE_UNEXPECTED"))

    comparisons = []
    for m in metrics:
        cur_val = current.get(m, 0.0)
        prev_val = previous.get(m, 0.0)
        change = ((cur_val - prev_val) / prev_val * 100.0) if prev_val else (100.0 if cur_val else 0.0)
        comparisons.append(MetricComparison(id=m, title=m, metric=m, current_value=cur_val,
                                            previous_value=prev_val, change_pct=round(change, 2)))
    result = PeriodComparison(id=pid, title=f"Period comparison for {pid}", property_id=pid,
                              start_date=params.start_date, end_date=params.end_date,
                              compare_start_date=params.compare_start_date, compare_end_date=params.compare_end_date,
                              metrics=comparisons)
    return ActionResult.success(result, summary=f"Compared {len(metrics)} metrics for property {pid}.")


@chat.function("export_report_csv", "Run a GA4 custom report and return it as CSV text, ready to save or paste into a spreadsheet.",
               action_type="read", data_model=ReportCsv)
async def export_report_csv(ctx, params: ExportReportCsvParams) -> ActionResult:
    """Run a custom report and return it as CSV text."""
    doc, pid, err = await _resolve(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    if not params.metrics:
        return ActionResult.error("Pass at least one metric.", retryable=False, code="VALIDATION_FAILED")
    body = {
        "dateRanges": [{"startDate": params.start_date, "endDate": params.end_date}],
        "dimensions": [{"name": d} for d in params.dimensions],
        "metrics": [{"name": m} for m in params.metrics],
        "limit": str(max(1, min(params.limit, 100))),
    }
    out = await ga4.report(ctx, doc, pid, body)
    if not out.get("ok"):
        return _error(out)
    data_rows = ga4.rows(out["data"])
    buffer = io.StringIO()
    if data_rows:
        writer = csv.DictWriter(buffer, fieldnames=list(data_rows[0].keys()))
        writer.writeheader()
        writer.writerows(data_rows)
    result = ReportCsv(id=pid, title=f"CSV export for {pid}", property_id=pid, row_count=len(data_rows), csv=buffer.getvalue())
    return ActionResult.success(result, summary=f"Exported {len(data_rows)} rows as CSV for property {pid}.")
