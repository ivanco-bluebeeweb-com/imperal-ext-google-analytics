"""Google Analytics 4 read-only extension declaration."""

from imperal_sdk import ChatExtension, Extension

APP_ID = "google-analytics-bluebee"

ext = Extension(
    APP_ID,
    version="0.1.0",
    display_name="Google Analytics",
    description="Read-only Google Analytics 4 reporting: properties, overview metrics, traffic and page performance.",
    icon="icon.svg",
    capabilities=["google-analytics:read", "google-analytics:settings"],
    actions_explicit=True,
)

chat = ChatExtension(
    ext,
    tool_name="google_analytics",
    description="Read Google Analytics 4 properties and reports without changing Google Analytics settings or data.",
)

# The connection is deliberately read-only. Identity scopes prevent a connection
# record without a usable account label from being treated as ready.
ext.oauth(
    "google",
    collection="google_analytics_accounts",
    scopes=[
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/analytics.readonly",
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
