"""Read-only Google Analytics Admin and Data API client."""

from __future__ import annotations

ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"
DATA_API = "https://analyticsdata.googleapis.com/v1beta"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_MESSAGES = {
    "ACCOUNT_MISSING": "No usable Google Analytics account is connected yet.",
    "ACCOUNT_AMBIGUOUS": "Several Google accounts are connected; specify the account to use.",
    "TOKEN_REJECTED": "Google rejected this connection. Reconnect the Google account and try again.",
    "PERMISSION_DENIED": "This Google account cannot access that Google Analytics property.",
    "RATE_LIMITED": "Google Analytics is rate-limiting requests; try again shortly.",
    "VALIDATION_FAILED": "Google Analytics rejected the request as invalid.",
    "UNREACHABLE": "Could not reach Google Analytics.",
    "RESPONSE_UNEXPECTED": "Google Analytics returned a response the app could not safely interpret.",
}


def fail(code: str, detail: str = "") -> dict:
    return {"ok": False, "code": code, "error": detail or _MESSAGES.get(code, "Google Analytics request failed."),
            "retryable": code in {"RATE_LIMITED", "UNREACHABLE"}}


def _body(response):
    body = response.body
    if isinstance(body, (str, bytes, bytearray)):
        try:
            return response.json()
        except Exception:
            return body
    return body


def _error(status: int, body) -> dict:
    message = ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "")
    if status == 401:
        return fail("TOKEN_REJECTED")
    if status == 403:
        return fail("RATE_LIMITED" if "quota" in message.lower() or "rate" in message.lower() else "PERMISSION_DENIED")
    if status == 400:
        return fail("VALIDATION_FAILED", f"Google Analytics rejected the request: {message}" if message else "")
    if status == 429:
        return fail("RATE_LIMITED")
    return fail("RESPONSE_UNEXPECTED" if status < 500 else "UNREACHABLE")


ACCOUNTS_COLLECTION = "google_analytics_accounts"


async def list_accounts(ctx) -> list:
    """All usable connected accounts (never the placeholder 'unknown')."""
    page = await ctx.store.query(ACCOUNTS_COLLECTION, limit=100)
    return [doc for doc in page.data if str((doc.data or {}).get("email") or "").lower() not in {"", "unknown"}]


async def active_account(ctx):
    """The account marked is_active, or the first usable one if none is marked yet.

    Mirrors the Google Search Console connector's _active_account: with several
    connected Google accounts, exactly one is "active" at a time and every read
    that omits `account` uses it — instead of erroring ACCOUNT_AMBIGUOUS the
    moment a second account is connected.
    """
    docs = await list_accounts(ctx)
    if not docs:
        return None
    return next((doc for doc in docs if bool((doc.data or {}).get("is_active"))), docs[0])


async def resolve_account(ctx, email: str = "") -> dict:
    """Resolve one usable connected account: by email if given, else the active one."""
    if email:
        page = await ctx.store.query(ACCOUNTS_COLLECTION, limit=100)
        docs = [doc for doc in page.data if str((doc.data or {}).get("email") or "").lower() == email.lower()]
        if not docs:
            return fail("ACCOUNT_MISSING")
        return {"ok": True, "account": docs[0]}
    doc = await active_account(ctx)
    if doc is None:
        return fail("ACCOUNT_MISSING")
    return {"ok": True, "account": doc}



async def selected_property_id(ctx, email: str) -> str:
    """The locally-saved default GA4 property for one Google account, if any."""
    page = await ctx.store.query("google_analytics_selections", where={"email": email.lower()}, limit=1)
    return str((page.data[0].data or {}).get("property_id") or "") if page.data else ""


async def global_selected_property(ctx) -> dict:
    """The one globally-selected property across every connected account, if any.

    The sidebar's property Select is a single flat dropdown regardless of which
    connected Google account owns the property, so the saved selection carries
    both the property_id and the owning account's email -- callers that need a
    specific account for further API calls read it from here instead of the
    active_account fallback that per-account selections use.
    """
    page = await ctx.store.query("google_analytics_selections", limit=100)
    fallback = {}
    for doc in page.data:
        data = doc.data or {}
        if not data.get("property_id"):
            continue
        selection = {"property_id": str(data["property_id"]), "email": str(data.get("email") or "")}
        if data.get("is_current"):
            return selection
        fallback = fallback or selection
    return fallback


async def account_for_property(ctx, property_id: str):
    """Find which connected account's accountSummaries includes this property_id.

    Used when the sidebar's single property Select spans every connected
    account: once a property_id is chosen, the report/detail screens need
    the actual account_doc to call Google with, not just an email guess.
    """
    for doc in await list_accounts(ctx):
        out = await properties(ctx, doc)
        if out.get("ok") and any(row["property_id"] == property_id for row in out.get("properties") or []):
            return doc
    return None


async def request(ctx, account_doc, method: str, url: str, *, params: dict | None = None, json: dict | None = None) -> dict:
    token = str((account_doc.data or {}).get("access_token") or "")
    if not token:
        return fail("TOKEN_REJECTED")
    kwargs = {"headers": {"Authorization": f"Bearer {token}", "Accept": "application/json"}, "timeout": 30}
    if params:
        kwargs["params"] = params
    if json is not None:
        kwargs["json"] = json
    try:
        response = await getattr(ctx.http, method.lower())(url, **kwargs)
    except Exception:
        return fail("UNREACHABLE")
    body = _body(response)
    if response.status_code >= 400:
        return _error(response.status_code, body)
    if not isinstance(body, dict):
        return fail("RESPONSE_UNEXPECTED")
    return {"ok": True, "data": body}


async def properties(ctx, account_doc) -> dict:
    out = await request(ctx, account_doc, "get", f"{ADMIN_API}/accountSummaries", params={"pageSize": 200})
    if not out.get("ok"):
        return out
    rows = []
    for account in out["data"].get("accountSummaries") or []:
        for prop in account.get("propertySummaries") or []:
            resource = str(prop.get("property") or "")
            property_id = resource.rsplit("/", 1)[-1]
            if property_id:
                rows.append({"property_id": property_id, "title": str(prop.get("displayName") or property_id),
                             "account": str(account.get("displayName") or "")})
    return {"ok": True, "properties": rows}


async def report(ctx, account_doc, property_id: str, body: dict) -> dict:
    return await request(ctx, account_doc, "post", f"{DATA_API}/properties/{property_id}:runReport", json=body)


async def batch_reports(ctx, account_doc, property_id: str, requests_body: list[dict]) -> dict:
    """properties.batchRunReports -- several runReport requests in one call."""
    return await request(ctx, account_doc, "post", f"{DATA_API}/properties/{property_id}:batchRunReports",
                         json={"requests": requests_body})


async def pivot_report(ctx, account_doc, property_id: str, body: dict) -> dict:
    """properties.runPivotReport -- a report shaped as a pivot table."""
    return await request(ctx, account_doc, "post", f"{DATA_API}/properties/{property_id}:runPivotReport", json=body)


async def realtime_report(ctx, account_doc, property_id: str, body: dict) -> dict:
    """properties.runRealtimeReport -- events from the last ~30 minutes."""
    return await request(ctx, account_doc, "post", f"{DATA_API}/properties/{property_id}:runRealtimeReport", json=body)


async def check_compatibility(ctx, account_doc, property_id: str, body: dict) -> dict:
    """properties.checkCompatibility -- validate a dimension+metric combination before running it."""
    return await request(ctx, account_doc, "post", f"{DATA_API}/properties/{property_id}:checkCompatibility", json=body)


async def report_metadata(ctx, account_doc, property_id: str) -> dict:
    """properties.getMetadata -- which dimensions/metrics this property can report on."""
    return await request(ctx, account_doc, "get", f"{DATA_API}/properties/{property_id}/metadata")


async def admin_list(ctx, account_doc, path: str, *, item_key: str, params: dict | None = None) -> dict:
    """Generic Admin API v1beta list call, following nextPageToken until exhausted.

    Every Admin API list method (customDimensions, customMetrics, keyEvents,
    dataStreams, googleAdsLinks, accounts, accountSummaries...) shares this
    exact pagination shape, so one helper covers all of them.
    """
    items: list[dict] = []
    page_token = ""
    base_params = dict(params or {})
    for _ in range(20):  # hard cap: never loop forever on a misbehaving API
        call_params = dict(base_params)
        call_params["pageSize"] = 200
        if page_token:
            call_params["pageToken"] = page_token
        out = await request(ctx, account_doc, "get", f"{ADMIN_API}/{path}", params=call_params)
        if not out.get("ok"):
            return out
        body = out["data"]
        items.extend(body.get(item_key) or [])
        page_token = str(body.get("nextPageToken") or "")
        if not page_token:
            break
    return {"ok": True, "items": items}


async def admin_get(ctx, account_doc, path: str) -> dict:
    """Generic Admin API v1beta single-resource GET."""
    return await request(ctx, account_doc, "get", f"{ADMIN_API}/{path}")


# ──────────────────────────────────────────────────────────────────────────
# Write helpers (Part D). Every one of these can create, change, or remove
# something in the user's actual Google Analytics property. They all go
# through the same `request()` used above -- same token, same error mapping
# -- so a missing analytics.edit scope or an Editor-less GA4 role surfaces as
# the ordinary TOKEN_REJECTED / PERMISSION_DENIED codes callers already
# handle, not a new failure mode.
# ──────────────────────────────────────────────────────────────────────────


async def admin_create(ctx, account_doc, path: str, body: dict, *, query: dict | None = None) -> dict:
    """Generic Admin API v1beta create call (POST .../parent/collection)."""
    return await request(ctx, account_doc, "post", f"{ADMIN_API}/{path}", params=query, json=body)


async def admin_patch(ctx, account_doc, path: str, body: dict, *, update_mask: str = "") -> dict:
    """Generic Admin API v1beta patch call. Google's PATCH needs updateMask as a query param."""
    params = {"updateMask": update_mask} if update_mask else None
    return await request(ctx, account_doc, "patch", f"{ADMIN_API}/{path}", params=params, json=body)


async def admin_delete(ctx, account_doc, path: str) -> dict:
    """Generic Admin API v1beta delete call."""
    return await request(ctx, account_doc, "delete", f"{ADMIN_API}/{path}")


async def admin_action(ctx, account_doc, path: str, body: dict | None = None) -> dict:
    """Generic Admin API v1beta custom-verb call, e.g. .../customDimensions/x:archive."""
    return await request(ctx, account_doc, "post", f"{ADMIN_API}/{path}", json=body or {})


def rows(report_body: dict) -> list[dict]:
    headers = [str(h.get("name") or "") for h in report_body.get("dimensionHeaders") or []] + [
        str(h.get("name") or "") for h in report_body.get("metricHeaders") or []
    ]
    result = []
    for row in report_body.get("rows") or []:
        values = [str(v.get("value") or "") for v in row.get("dimensionValues") or []] + [
            str(v.get("value") or "") for v in row.get("metricValues") or []
        ]
        result.append(dict(zip(headers, values)))
    return result
