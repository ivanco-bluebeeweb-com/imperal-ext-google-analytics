"""MVP screens for the read-only Google Analytics 4 application."""

from imperal_sdk import ui

from app import APP_ID, ext

REDIRECT_URI = f"https://panel.imperal.io/v1/ext/{APP_ID}/oauth/google/callback"
GOOGLE_ANALYTICS_ADMIN_URL = "https://analytics.google.com/analytics/web/"
GOOGLE_CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials"
IMPERAL_SECRETS_URL = f"https://panel.imperal.io/ext/{APP_ID}/secrets"


def _setup_page():
    return ui.Page(title="Set up Google Analytics", subtitle="One-time setup for the app owner", children=[
        ui.Alert("Google OAuth credentials are not configured yet.", title="Setup required", type="warning"),
        ui.Section(title="1. Create a Google OAuth client", children=[
            ui.Text("Create a Web application OAuth client and add this Authorized redirect URI:"),
            ui.Code(REDIRECT_URI),
            ui.Button("Open Google credentials", icon="ExternalLink", on_click=ui.Open(GOOGLE_CREDENTIALS_URL)),
        ]),
        ui.Section(title="2. Save credentials in Imperal", children=[
            ui.Text("Save the client ID and client secret as google_client_id and google_client_secret."),
            ui.Button("Open Imperal Secrets", icon="ExternalLink", on_click=ui.Open(IMPERAL_SECRETS_URL)),
            ui.Text("Never paste the client secret into chat or source code.", variant="caption"),
        ]),
    ])


async def _connect(ctx):
    client_id = await ctx.secrets.get("google_client_id")
    client_secret = await ctx.secrets.get("google_client_secret")
    if not client_id or not client_secret:
        return _setup_page()
    try:
        url = await ctx.oauth_authorize_url("google")
    except Exception:
        return ui.Page(title="Connect Google Analytics", children=[
            ui.Alert("Imperal could not create the Google authorization link. Recheck the OAuth client and redirect URI.",
                     title="OAuth configuration error", type="error"),
            ui.Button("Open setup", icon="Settings", on_click=ui.Call("__panel__analytics", view="connect")),
        ])
    return ui.Page(title="Connect Google Analytics", children=[
        ui.Alert("This app has read-only access. It cannot change GA4 settings, events, audiences or data.", type="info"),
        ui.Card(title="What Webbee can read", content=ui.Stack(children=[
            ui.Text("GA4 properties you can access"),
            ui.Text("Traffic, page and conversion reports"),
            ui.Text("Comparison periods you choose"),
        ])),
        ui.Button("Connect Google account", icon="ExternalLink", on_click=ui.Open(url)),
        ui.Text("Google handles authorization. Imperal never asks for your Google password.", variant="caption"),
    ])


@ext.panel("analytics_nav", slot="left", title="Google Analytics", icon="ChartNoAxesCombined",
           default_width=280, min_width=220, max_width=400)
async def analytics_nav(ctx, **kwargs):
    return ui.Stack(children=[
        ui.List(items=[
            ui.ListItem(id="overview", title="Overview", icon="LayoutDashboard",
                        on_click=ui.Call("__panel__analytics", view="overview")),
            ui.ListItem(id="explore", title="Explore", icon="ChartColumn",
                        on_click=ui.Call("__panel__analytics", view="explore")),
            ui.ListItem(id="realtime", title="Realtime", icon="Activity",
                        on_click=ui.Call("__panel__analytics", view="realtime")),
            ui.ListItem(id="saved", title="Saved reports", icon="Bookmark",
                        on_click=ui.Call("__panel__analytics", view="saved")),
            ui.ListItem(id="settings", title="Properties & settings", icon="Settings",
                        on_click=ui.Call("__panel__analytics", view="settings")),
        ]),
        ui.Button("Connect Google account", icon="Plus", variant="ghost",
                  on_click=ui.Call("__panel__analytics", view="connect")),
    ])


@ext.panel("analytics", slot="center", title="Google Analytics", icon="ChartNoAxesCombined", center_overlay=True)
async def analytics(ctx, view="overview", **kwargs):
    if view == "connect":
        return await _connect(ctx)
    page = await ctx.store.query("google_analytics_accounts", limit=1)
    if not page.data:
        return await _connect(ctx)
    if view == "overview":
        return await _overview(ctx)
    if view == "explore":
        return _coming_soon("Explore", "Choose dimensions, metrics and filters after selecting a GA4 property.")
    if view == "realtime":
        return _coming_soon("Realtime", "Realtime reports arrive after property selection and GA4 Data API wiring.")
    if view == "saved":
        return _coming_soon("Saved reports", "Saved report definitions will be stored in Imperal, never in Google Analytics.")
    return _settings()


async def _overview(ctx):
    selection = await ctx.store.query("google_analytics_selections", limit=1)
    if not selection.data:
        return _overview_empty()
    property_id = str((selection.data[0].data or {}).get("property_id") or "")
    if not property_id:
        return _overview_empty()
    return ui.Page(title="Overview", subtitle="Last 7 completed days", children=[
        ui.Alert(f"Selected GA4 property: {property_id}", title="Read-only reporting", type="info"),
        ui.Button("Load overview", icon="RefreshCw",
                  on_click=ui.Call("get_overview", property_id=property_id,
                                   start_date="7daysAgo", end_date="yesterday")),
        ui.Text("Loads active users, sessions, views, conversions and total revenue. Nothing in Google Analytics is changed.",
                variant="caption"),
    ])


def _overview_empty():
    return ui.Page(title="Overview", children=[
        ui.Alert("Google account connected. Use the chat command “list properties”, then select one to load reporting data.",
                 title="Choose a property", type="info"),
        ui.Empty("No GA4 property selected yet."),
        ui.Button("Open Google Analytics", icon="ExternalLink", on_click=ui.Open(GOOGLE_ANALYTICS_ADMIN_URL)),
    ])


def _coming_soon(title, detail):
    return ui.Page(title=title, children=[ui.Empty(detail)])


def _settings():
    return ui.Page(title="Properties & settings", children=[
        ui.Card(title="Read-only connection", content=ui.Text(
            "GA4 settings, events, audiences and data are never changed by this app."
        )),
        ui.Empty("Property discovery and selection will appear here in the next implementation step."),
    ])
