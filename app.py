"""Google Analytics 4 read-only extension declaration."""

from imperal_sdk import ChatExtension, Extension

APP_ID = "google-analytics-bluebee"

ext = Extension(
    APP_ID,
    version="0.2.0",
    display_name="Google Analytics",
    description="Read-only Google Analytics 4 reporting: properties, overview metrics, traffic and page performance.",
    icon="icon.svg",
    capabilities=["google-analytics:read", "google-analytics:settings", "notify:push"],
    actions_explicit=True,
)

chat = ChatExtension(
    ext,
    tool_name="google_analytics",
    description="Read Google Analytics 4 properties and reports without changing Google Analytics settings or data.",
)

# The connection is deliberately read-only. Identity scopes prevent a connection
# record without a usable account label from being treated as ready.
#
# gmail.readonly is a platform-resolution workaround, not a feature scope: the
# web-kernel's OAuth callback resolves the connected account's email via a
# Gmail-specific profile call for the "google" provider on ANY extension, not
# just Mail. Without a Gmail scope that call fails and the account is saved
# with an "unknown" email placeholder -- which this app then correctly refuses
# to treat as connected. This extension never calls Gmail; it exists purely so
# the platform's own account-resolution step succeeds. See also: Google Drive
# Connector hits the identical "unknown"/reconnect_required symptom without it.
ext.oauth(
    "google",
    collection="google_analytics_accounts",
    scopes=[
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/gmail.readonly",
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
