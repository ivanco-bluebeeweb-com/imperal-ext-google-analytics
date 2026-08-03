"""GA4 alert rules — MVP notify-only anomaly detection.

Alerts never change GA4 settings, budgets, or campaigns. They only read GA4
report data on a schedule and, when a rule's condition is met, send an Imperal
notification. Nothing here writes to Google.
"""

from imperal_sdk import ActionResult

import ga4_client as ga4
from app import chat, ext
from models import (ALERT_CONDITIONS, ALERT_METRICS, ALERT_SCHEDULES, AccountParam, AlertIdParams,
                    CreateAlertParams, GA4Alert, GA4AlertList)

ALERTS = "google_analytics_alerts"

_METRIC_API_NAMES = {
    "active_users": "activeUsers",
    "sessions": "sessions",
    "conversions": "conversions",
    "total_revenue": "totalRevenue",
}

_METRIC_LABELS = {
    "active_users": "Active users",
    "sessions": "Sessions",
    "conversions": "Key events",
    "total_revenue": "Total revenue",
}

_PERIODS = {
    "daily": {"current": ("yesterday", "yesterday"), "previous": ("2daysAgo", "2daysAgo")},
    "weekly": {"current": ("7daysAgo", "yesterday"), "previous": ("14daysAgo", "8daysAgo")},
}


def _to_alert(doc) -> GA4Alert:
    data = doc.data or {}
    return GA4Alert(id=doc.id, title=f"{_METRIC_LABELS.get(data.get('metric'), data.get('metric'))} {data.get('condition')}",
                    account=str(data.get("email") or ""), property_id=str(data.get("property_id") or ""),
                    metric=str(data.get("metric") or ""), condition=str(data.get("condition") or ""),
                    threshold=float(data.get("threshold") or 0.0), schedule=str(data.get("schedule") or "daily"),
                    enabled=bool(data.get("enabled", True)), last_triggered_at=str(data.get("last_triggered_at") or ""))


@chat.function("create_alert_rule", "Create a notify-only GA4 alert rule that watches one metric on a schedule.",
               action_type="write", effects=["alert.create"],
               event="google-analytics-bluebee.alert.created", data_model=GA4Alert)
async def create_alert_rule(ctx, params: CreateAlertParams) -> ActionResult:
    """Persist an alert rule locally. Never touches Google Analytics settings."""
    if params.metric not in ALERT_METRICS:
        return ActionResult.error(f"Unknown metric. Choose one of: {', '.join(ALERT_METRICS)}.", retryable=False,
                                  code="GA4_ALERT_METRIC_INVALID")
    if params.condition not in ALERT_CONDITIONS:
        return ActionResult.error(f"Unknown condition. Choose one of: {', '.join(ALERT_CONDITIONS)}.", retryable=False,
                                  code="GA4_ALERT_CONDITION_INVALID")
    if params.schedule not in ALERT_SCHEDULES:
        return ActionResult.error(f"Unknown schedule. Choose one of: {', '.join(ALERT_SCHEDULES)}.", retryable=False,
                                  code="GA4_ALERT_SCHEDULE_INVALID")
    resolved = await ga4.resolve_account(ctx, params.account)
    if not resolved.get("ok"):
        return ActionResult.error(resolved.get("error") or "Connect a Google account first.", retryable=False,
                                  code=resolved.get("code") or "ACCOUNT_MISSING")
    doc = resolved["account"]
    email = str((doc.data or {}).get("email") or "").lower()
    properties = await ga4.properties(ctx, doc)
    if not properties.get("ok"):
        return ActionResult.error(properties.get("error") or "Could not verify GA4 property access.",
                                  retryable=bool(properties.get("retryable")), code=properties.get("code") or "RESPONSE_UNEXPECTED")
    if params.property_id not in {row["property_id"] for row in properties["properties"]}:
        return ActionResult.error("That GA4 property is not available to this Google account.", retryable=False,
                                  code="GA4_PROPERTY_NOT_FOUND")
    record = {"email": email, "property_id": params.property_id, "metric": params.metric, "condition": params.condition,
              "threshold": params.threshold, "schedule": params.schedule, "enabled": True, "last_triggered_at": ""}
    created = await ctx.store.create(ALERTS, record)
    return ActionResult.success(_to_alert(created), summary="Alert rule created. It runs notify-only — nothing in Google Analytics changes.",
                                refresh_panels=["analytics"])


@chat.function("list_alert_rules", "List the user's GA4 alert rules.",
               action_type="read", data_model=GA4AlertList)
async def list_alert_rules(ctx, params: AccountParam) -> ActionResult:
    """List alert rules, optionally scoped to one connected account."""
    where = {}
    if params.account:
        where["email"] = params.account.lower()
    page = await ctx.store.query(ALERTS, where=where, limit=100) if where else await ctx.store.query(ALERTS, limit=100)
    alerts = [_to_alert(doc) for doc in page.data]
    return ActionResult.success(GA4AlertList(items=alerts), summary=f"{len(alerts)} alert rule(s).")


@chat.function("delete_alert_rule", "Permanently delete a GA4 alert rule. This cannot be undone.",
               action_type="destructive", effects=["alert.delete"], id_projection="alert_id",
               event="google-analytics-bluebee.alert.deleted", data_model=GA4Alert)
async def delete_alert_rule(ctx, params: AlertIdParams) -> ActionResult:
    """Delete one alert rule by id. Local record only -- Google Analytics is never touched."""
    doc = await ctx.store.get(ALERTS, params.alert_id)
    if doc is None:
        return ActionResult.error("Alert rule not found.", retryable=False, code="GA4_ALERT_NOT_FOUND")
    alert = _to_alert(doc)
    await ctx.store.delete(ALERTS, params.alert_id)
    return ActionResult.success(alert, summary="Alert rule deleted.", refresh_panels=["analytics"])


async def _metric_value(ctx, account_doc, property_id: str, metric_api_name: str, start_date: str, end_date: str):
    """Fetch one metric's value for one date range. Returns (value, error_dict_or_None)."""
    out = await ga4.report(ctx, account_doc, property_id, {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "metrics": [{"name": metric_api_name}],
    })
    if not out.get("ok"):
        return 0.0, out
    values = (ga4.rows(out["data"]) or [{}])[0]
    try:
        return float(values.get(metric_api_name) or 0), None
    except (TypeError, ValueError):
        return 0.0, None


async def evaluate_alert(ctx, alert_doc, account_doc) -> dict:
    """Evaluate one alert rule against live GA4 data. Read-only. Returns a result dict, never raises."""
    data = alert_doc.data or {}
    metric = str(data.get("metric") or "")
    condition = str(data.get("condition") or "")
    threshold = float(data.get("threshold") or 0.0)
    schedule = str(data.get("schedule") or "daily")
    property_id = str(data.get("property_id") or "")
    metric_api_name = _METRIC_API_NAMES.get(metric)
    period = _PERIODS.get(schedule, _PERIODS["daily"])
    if not metric_api_name or not property_id:
        return {"ok": False, "error": "Alert rule is misconfigured."}
    current, err1 = await _metric_value(ctx, account_doc, property_id, metric_api_name, *period["current"])
    if err1:
        return {"ok": False, "error": err1.get("error") or "Could not read current GA4 data.", "code": err1.get("code")}
    previous, err2 = await _metric_value(ctx, account_doc, property_id, metric_api_name, *period["previous"])
    if err2:
        return {"ok": False, "error": err2.get("error") or "Could not read comparison GA4 data.", "code": err2.get("code")}
    triggered = False
    if condition == "increase_pct":
        triggered = current > previous * (1 + threshold / 100) if previous > 0 else current > 0
    elif condition == "decrease_pct":
        triggered = current < previous * (1 - threshold / 100) if previous > 0 else False
    elif condition == "above_value":
        triggered = current > threshold
    elif condition == "below_value":
        triggered = current < threshold
    label = _METRIC_LABELS.get(metric, metric)
    return {"ok": True, "triggered": triggered, "current": current, "previous": previous,
            "message": f"{label} is {current:g} (was {previous:g})." if condition in ("increase_pct", "decrease_pct")
                       else f"{label} is {current:g}."}


@ext.schedule("evaluate_alerts", cron="0 8 * * *")
async def evaluate_alerts(ctx) -> None:
    """Daily at 08:00 UTC: evaluate every user's alert rules and notify on trigger.

    System context -- no ctx.user, no ctx.time.now_local. Fan out explicitly via
    list_users/as_user, isolate each user (and each alert) in try/except so one
    bad rule or one bad account never blocks the rest, and guard against the
    web-kernel retrying this tick by skipping alerts already evaluated today.
    """
    import logging
    from datetime import datetime, timezone

    log = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    is_monday = now.weekday() == 0

    async for user_id in ctx.store.list_users(ALERTS):
        user_ctx = ctx.as_user(user_id)
        try:
            alerts = await user_ctx.store.query(ALERTS, where={"enabled": True}, limit=200)
            for alert_doc in alerts.data:
                data = alert_doc.data or {}
                try:
                    schedule = str(data.get("schedule") or "daily")
                    if schedule == "weekly" and not is_monday:
                        continue
                    if str(data.get("last_evaluated_on") or "") == today:
                        continue  # idempotency guard: already evaluated today, even if not triggered
                    resolved = await ga4.resolve_account(user_ctx, str(data.get("email") or ""))
                    if not resolved.get("ok"):
                        continue
                    result = await evaluate_alert(user_ctx, alert_doc, resolved["account"])
                    updates = {**data, "last_evaluated_on": today}
                    if result.get("ok") and result.get("triggered"):
                        updates["last_triggered_at"] = now.isoformat()
                        await user_ctx.notify(f"GA4 alert: {result['message']}")
                    await user_ctx.store.update(ALERTS, alert_doc.id, updates)
                except Exception as exc:  # noqa: BLE001
                    log.warning("evaluate_alerts: user %s alert %s failed: %s", user_id, alert_doc.id, exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("evaluate_alerts: user %s failed: %s", user_id, exc)
