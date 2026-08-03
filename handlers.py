"""Read-only chat tools for Google Analytics 4."""

from datetime import datetime, timezone

from imperal_sdk import ActionResult

import ga4_client as ga4
from app import chat
from models import (AccountParam, GA4Overview, GA4Property, GA4PropertyList, NoParams,
                    OverviewParams, PropertySelection, SelectPropertyParams)

SELECTIONS = "google_analytics_selections"
OVERVIEW_CACHE = "google_analytics_overview_cache"


def _error(out: dict) -> ActionResult:
    return ActionResult.error(out.get("error") or "Google Analytics request failed.",
                              retryable=bool(out.get("retryable")), code=out.get("code") or "RESPONSE_UNEXPECTED")


def _success(data, summary: str, refresh=None) -> ActionResult:
    return ActionResult.success(data, summary=summary, refresh_panels=refresh)


async def _selection(ctx, email: str) -> str:
    page = await ctx.store.query(SELECTIONS, where={"email": email.lower()}, limit=1)
    return str((page.data[0].data or {}).get("property_id") or "") if page.data else ""


async def cached_overview(ctx, property_id: str) -> dict | None:
    """The last successfully loaded overview for one property, if any. Read-only helper for panels."""
    page = await ctx.store.query(OVERVIEW_CACHE, where={"property_id": property_id}, limit=1)
    return page.data[0].data if page.data else None


@chat.function("connect_google_analytics", "Connect another Google account to Google Analytics 4.",
               action_type="write", effects=["oauth.connect"],
               event="google-analytics-bluebee.account.connect", data_model=PropertySelection)
async def connect_google_analytics(ctx, params: NoParams) -> ActionResult:
    """Return the platform-owned Google OAuth URL when GA4 OAuth is configured."""
    client_id = await ctx.secrets.get("google_client_id")
    client_secret = await ctx.secrets.get("google_client_secret")
    if not client_id or not client_secret:
        return ActionResult.error("Google OAuth is not configured. Save the client ID and client secret in the app's Secrets.",
                                  retryable=False, code="GOOGLE_OAUTH_NOT_CONFIGURED")
    url = await ctx.oauth_authorize_url("google")
    return ActionResult.success({"authorization_url": url}, summary="Open the Google authorization link to connect Analytics.")


@chat.function("list_properties", "List GA4 properties the connected Google account can read.",
               action_type="read", data_model=GA4PropertyList)
async def list_properties(ctx, params: AccountParam) -> ActionResult:
    """List only properties returned by Google's read-only Admin API."""
    resolved = await ga4.resolve_account(ctx, params.account)
    if not resolved.get("ok"):
        return _error(resolved)
    doc = resolved["account"]
    email = str((doc.data or {}).get("email") or "")
    selected = await _selection(ctx, email)
    out = await ga4.properties(ctx, doc)
    if not out.get("ok"):
        return _error(out)
    properties = [GA4Property(id=row["property_id"], title=row["title"], property_id=row["property_id"],
                              account=row["account"], selected=row["property_id"] == selected) for row in out["properties"]]
    return _success(GA4PropertyList(items=properties), f"Found {len(properties)} GA4 propert{'y' if len(properties) == 1 else 'ies'}.")


@chat.function("select_property", "Select the GA4 property used by default for this Google account.",
               action_type="write", effects=["local.preference.update"],
               event="google-analytics-bluebee.property.selected", data_model=PropertySelection)
async def select_property(ctx, params: SelectPropertyParams) -> ActionResult:
    """Persist a local default after verifying property access with Google."""
    resolved = await ga4.resolve_account(ctx, params.account)
    if not resolved.get("ok"):
        return _error(resolved)
    doc = resolved["account"]
    email = str((doc.data or {}).get("email") or "").lower()
    properties = await ga4.properties(ctx, doc)
    if not properties.get("ok"):
        return _error(properties)
    if params.property_id not in {row["property_id"] for row in properties["properties"]}:
        return ActionResult.error("That GA4 property is not available to this Google account.", retryable=False,
                                  code="GA4_PROPERTY_NOT_FOUND")
    old = await ctx.store.query(SELECTIONS, where={"email": email}, limit=1)
    record = {"email": email, "property_id": params.property_id}
    if old.data:
        await ctx.store.update(SELECTIONS, old.data[0].id, record)
    else:
        await ctx.store.create(SELECTIONS, record)
    return _success(PropertySelection(id=params.property_id, title=params.property_id, account=email,
                                      property_id=params.property_id), "GA4 property selected.", ["analytics"])


@chat.function("get_overview", "Read headline GA4 metrics for a selected property and date range.",
               action_type="read", data_model=GA4Overview)
async def get_overview(ctx, params: OverviewParams) -> ActionResult:
    """Request headline metrics from GA4 Data API without mutating Google data."""
    resolved = await ga4.resolve_account(ctx, params.account)
    if not resolved.get("ok"):
        return _error(resolved)
    doc = resolved["account"]
    email = str((doc.data or {}).get("email") or "")
    property_id = params.property_id or await _selection(ctx, email)
    if not property_id:
        return ActionResult.error("Select a GA4 property first.", retryable=False, code="GA4_PROPERTY_NOT_SELECTED")
    body = {"dateRanges": [{"startDate": params.start_date, "endDate": params.end_date}],
            "metrics": [{"name": name} for name in ("activeUsers", "sessions", "screenPageViews", "conversions", "totalRevenue")]}
    out = await ga4.report(ctx, doc, property_id, body)
    if not out.get("ok"):
        return _error(out)
    values = (ga4.rows(out["data"]) or [{}])[0]
    def integer(name: str) -> int:
        try: return int(float(values.get(name) or 0))
        except (TypeError, ValueError): return 0
    def decimal(name: str) -> float:
        try: return float(values.get(name) or 0)
        except (TypeError, ValueError): return 0.0
    overview = GA4Overview(id=property_id, title="GA4 overview", property_id=property_id,
                           start_date=params.start_date, end_date=params.end_date,
                           active_users=integer("activeUsers"), sessions=integer("sessions"),
                           views=integer("screenPageViews"), conversions=integer("conversions"),
                           total_revenue=decimal("totalRevenue"))
    cache_record = {"property_id": property_id, "start_date": params.start_date, "end_date": params.end_date,
                    "active_users": overview.active_users, "sessions": overview.sessions, "views": overview.views,
                    "conversions": overview.conversions, "total_revenue": overview.total_revenue,
                    "loaded_at": datetime.now(timezone.utc).isoformat()}
    existing = await ctx.store.query(OVERVIEW_CACHE, where={"property_id": property_id}, limit=1)
    if existing.data:
        await ctx.store.update(OVERVIEW_CACHE, existing.data[0].id, cache_record)
    else:
        await ctx.store.create(OVERVIEW_CACHE, cache_record)
    return _success(overview, f"Loaded GA4 overview for {params.start_date} to {params.end_date}.", ["analytics"])
