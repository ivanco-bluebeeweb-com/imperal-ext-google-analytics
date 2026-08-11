"""Google Analytics 4 read-only extension declaration."""

from imperal_sdk import ChatExtension, Extension

APP_ID = "google-analytics-bluebee"

ext = Extension(
    APP_ID,
    version="0.4.0",
    display_name="Google Analytics",
    description="Google Analytics 4 reporting plus optional property editing: properties, overview metrics, "
                "traffic, page performance, and -- once you reconnect with edit access -- custom "
                "dimensions/metrics, key events, Google Ads links, and data streams.",
    icon="icon.svg",
    capabilities=["google-analytics:read", "google-analytics:write", "google-analytics:settings", "notify:push"],
    actions_explicit=True,
)

chat = ChatExtension(
    ext,
    tool_name="google_analytics",
    description="Read Google Analytics 4 properties and reports, and -- for accounts connected with edit access -- "
                "manage custom dimensions/metrics, key events, Google Ads links, property settings, and data streams.",
)

# Parts A/B/C only ever read. Part D (handlers_admin_write.py) writes to the
# user's actual GA4 property, so it needs analytics.edit on top of
# analytics.readonly. Google treats analytics.edit as a sensitive (not
# restricted) scope: no annual security assessment, but OAuth apps serving
# more than the ~100-user testing cap must pass Google's verification review
# (a form plus a short screen recording of the scope in use) before every
# user can grant it. Accounts that connected before this scope existed only
# hold analytics.readonly and MUST reconnect (disconnect_google_account then
# connect_google_analytics again) to accept the new consent screen -- no
# code change here can grant a scope retroactively to an old token. Even
# with the scope granted, Google Analytics still enforces its own property
# role: the account also needs Editor or Administrator on that GA4 property
# (set inside Google Analytics itself, not here) or Part D calls get
# PERMISSION_DENIED regardless of OAuth scope.
#
# gmail.readonly was tried as a workaround for the platform's OAuth callback
# resolving account email via a Gmail-specific getProfile call for the
# "google" provider on every extension, not just Mail. Root-caused via
# debug_dump_raw_accounts: the Gmail call itself succeeds (the saved record
# gains an unread_count field), but email still lands as the "unknown"
# placeholder even with the scope granted -- most likely the platform reads
# a field named "email" out of the Gmail getProfile response, which actually
# returns the address under "emailAddress". That is a platform bug, not
# something this app's requested scopes can fix. Reverted: no reason to ask
# for extra Gmail access that doesn't solve the problem.
ext.oauth(
    "google",
    collection="google_analytics_accounts",
    scopes=[
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/analytics.edit",
    ],
)

ext.secret(
    "google_client_id",
    "Google OAuth client ID for Google Analytics.",
    required=True,
    scope="app",
)(lambda: None)
ext.secret(
    "google_client_secret",
    "Google OAuth client secret for Google Analytics.",
    required=True,
    scope="app",
)(lambda: None)


@ext.on_install
async def on_install(ctx) -> dict:
    """No setup writes are needed; OAuth credentials are configured in Secrets."""
    return {"status": "ready"}


@ext.health_check
async def health_check(ctx) -> dict:
    """Configuration-only health check; it never calls Google."""
    try:
        accounts = await ctx.store.query("google_analytics_accounts", limit=1)
        count = len(accounts.data)
    except Exception:
        count = 0
    return {
        "healthy": count > 0,
        "accounts_configured": count,
        "detail": "Google Analytics account connected." if count else "No Google Analytics account connected yet.",
        "version": "0.1.0",
    }
