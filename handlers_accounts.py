"""Connected-account management: status, reconnect support, and disconnect.

Read-only towards Google — this module never calls Google's write APIs. It only
manages the *local* Imperal record of which Google accounts are connected.
"""

from imperal_sdk import ActionResult

import ga4_client as ga4
from app import chat
from models import AccountAction, GA4Account, GA4AccountList, RawAccountDump, RawAccountRecord

ACCOUNTS = "google_analytics_accounts"
SELECTIONS = "google_analytics_selections"
ALERTS = "google_analytics_alerts"


async def live_status(ctx, doc) -> GA4Account:
    """Check one connected account against Google right now. Never fabricates a status."""
    email = str((doc.data or {}).get("email") or "")
    connected_at = str((doc.data or {}).get("created_at") or (doc.data or {}).get("connected_at") or "")
    out = await ga4.properties(ctx, doc)
    if not out.get("ok"):
        code = out.get("code") or ""
        status = "reconnect_required" if code == "TOKEN_REJECTED" else (
            "insufficient_access" if code == "PERMISSION_DENIED" else "error")
        return GA4Account(id=email, title=email, account=email, connected_at=connected_at,
                          property_count=0, status=status)
    count = len(out.get("properties") or [])
    status = "connected" if count > 0 else "insufficient_access"
    return GA4Account(id=email, title=email, account=email, connected_at=connected_at,
                      property_count=count, status=status)


@chat.function("check_account_access", "Check whether a connected Google account can currently read Google Analytics data.",
               action_type="read", data_model=GA4Account)
async def check_account_access(ctx, params: AccountAction) -> ActionResult:
    """Live-check one connected account's GA4 access. Read-only."""
    resolved = await ga4.resolve_account(ctx, params.account)
    if not resolved.get("ok"):
        return ActionResult.error(resolved.get("error") or "That Google account is not connected.",
                                  retryable=False, code=resolved.get("code") or "ACCOUNT_MISSING")
    account = await live_status(ctx, resolved["account"])
    return ActionResult.success(account, summary=f"{account.account}: {account.status}, {account.property_count} propert{'y' if account.property_count == 1 else 'ies'}.",
                                refresh_panels=["analytics"])


@chat.function("disconnect_google_account", "Disconnect a Google account from Google Analytics. Google itself is never changed.",
               action_type="destructive", effects=["oauth.disconnect"],
               event="google-analytics-bluebee.account.disconnected", data_model=GA4Account,
               id_projection="account")
async def disconnect_google_account(ctx, params: AccountAction) -> ActionResult:
    """Permanently remove the local connection record, saved property selection and alerts for one account.

    This does not revoke Google's own OAuth grant and does not touch GA4 data.
    """
    resolved = await ga4.resolve_account(ctx, params.account)
    if not resolved.get("ok"):
        return ActionResult.error(resolved.get("error") or "That Google account is not connected.",
                                  retryable=False, code=resolved.get("code") or "ACCOUNT_MISSING")
    doc = resolved["account"]
    email = str((doc.data or {}).get("email") or "").lower()
    await ctx.store.delete(ACCOUNTS, doc.id)
    selections = await ctx.store.query(SELECTIONS, where={"email": email}, limit=1)
    for row in selections.data:
        await ctx.store.delete(SELECTIONS, row.id)
    alerts = await ctx.store.query(ALERTS, where={"email": email}, limit=100)
    for row in alerts.data:
        await ctx.store.delete(ALERTS, row.id)
    return ActionResult.success(GA4Account(id=email, title=email, account=email, status="disconnected"),
                                summary=f"Disconnected {email}. Reconnect any time — your Google account and GA4 data are unchanged.",
                                refresh_panels=["analytics"])


@chat.function("list_connected_accounts", "List every Google account connected to Google Analytics, with live access status.",
               action_type="read", data_model=GA4AccountList)
async def list_connected_accounts(ctx, params: AccountAction) -> ActionResult:
    """Live-check every connected account. Read-only, no caching of stale status."""
    docs = await ga4.list_accounts(ctx)
    accounts = [await live_status(ctx, doc) for doc in docs]
    return ActionResult.success(GA4AccountList(items=accounts), summary=f"{len(accounts)} connected Google account(s).")


@chat.function("debug_dump_raw_accounts",
               "TEMPORARY DIAGNOSTIC: dump the raw, unfiltered account records saved by the OAuth "
               "callback, including ones this app normally hides (empty/unknown email). Read-only; "
               "never calls Google. Remove once the OAuth email-resolution issue is understood.",
               action_type="read", data_model=RawAccountDump)
async def debug_dump_raw_accounts(ctx, params: AccountAction) -> ActionResult:
    """Read every raw account doc as stored, bypassing the usable-email filter, for diagnosis."""
    page = await ctx.store.query(ACCOUNTS, limit=100)
    rows = []
    lines = []
    for doc in page.data:
        data = doc.data or {}
        rec = RawAccountRecord(
            id=doc.id, title=str(data.get("email") or "(no email)"),
            email=str(data.get("email") or ""),
            provider=str(data.get("provider") or ""),
            is_active=bool(data.get("is_active")),
            has_access_token=bool(data.get("access_token")),
            has_refresh_token=bool(data.get("refresh_token")),
            expires_at=str(data.get("expires_at") or ""),
            created_at=str(data.get("created_at") or data.get("connected_at") or ""),
            all_keys=", ".join(sorted(data.keys())),
        )
        rows.append(rec)
        lines.append(
            f"doc={doc.id} email={rec.email!r} provider={rec.provider!r} "
            f"is_active={rec.is_active} has_access_token={rec.has_access_token} "
            f"has_refresh_token={rec.has_refresh_token} expires_at={rec.expires_at!r} "
            f"created_at={rec.created_at!r} all_keys=[{rec.all_keys}]"
        )
    summary = f"{len(rows)} raw account record(s) in store.\n" + "\n".join(lines) if lines else "0 raw account records in store."
    return ActionResult.success(RawAccountDump(items=rows), summary=summary)
