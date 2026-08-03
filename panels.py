"""Screens for the read-only Google Analytics 4 application."""

from imperal_sdk import ui

import ga4_client as ga4
from app import APP_ID, ext
from handlers import cached_overview
from handlers_accounts import live_status
from handlers_alerts import ALERT_CONDITIONS, ALERT_METRICS, ALERT_SCHEDULES, _METRIC_LABELS

REDIRECT_URI = f"https://panel.imperal.io/v1/ext/{APP_ID}/oauth/google/callback"
GOOGLE_ANALYTICS_ADMIN_URL = "https://analytics.google.com/analytics/web/"
GOOGLE_CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials"
IMPERAL_SECRETS_URL = f"https://panel.imperal.io/ext/{APP_ID}/secrets"

_STATUS_COLOR = {"connected": "green", "reconnect_required": "red",
                 "insufficient_access": "yellow", "error": "red"}
_STATUS_LABEL = {"connected": "Connected", "reconnect_required": "Reconnect needed",
                 "insufficient_access": "Insufficient access", "error": "Error"}


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
            ui.ListItem(id="properties", title="Properties", icon="Database",
                        on_click=ui.Call("__panel__analytics", view="properties")),
            ui.ListItem(id="explore", title="Explore", icon="ChartColumn",
                        on_click=ui.Call("__panel__analytics", view="explore")),
            ui.ListItem(id="realtime", title="Realtime", icon="Activity",
                        on_click=ui.Call("__panel__analytics", view="realtime")),
            ui.ListItem(id="saved", title="Saved reports", icon="Bookmark",
                        on_click=ui.Call("__panel__analytics", view="saved")),
            ui.ListItem(id="alerts", title="Alerts", icon="BellRing",
                        on_click=ui.Call("__panel__analytics", view="alerts")),
            ui.ListItem(id="settings", title="Settings", icon="Settings",
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
    if view == "properties":
        return await _properties(ctx)
    if view == "explore":
        return _coming_soon("Explore", "Choose dimensions, metrics and filters after selecting a GA4 property.")
    if view == "realtime":
        return _coming_soon("Realtime", "Realtime reports arrive after property selection and GA4 Data API wiring.")
    if view == "saved":
        return _coming_soon("Saved reports", "Saved report definitions will be stored in Imperal, never in Google Analytics.")
    if view == "alerts":
        return await _alerts(ctx)
    return await _settings(ctx)


# ── Overview ──────────────────────────────────────────────────────────────

async def _overview(ctx):
    selection = await ctx.store.query("google_analytics_selections", limit=1)
    if not selection.data:
        return _overview_empty()
    property_id = str((selection.data[0].data or {}).get("property_id") or "")
    if not property_id:
        return _overview_empty()
    cached = await cached_overview(ctx, property_id)
    children = [
        ui.Alert(f"Selected GA4 property: {property_id}", title="Read-only reporting", type="info"),
        ui.Row(children=[
            ui.Button("Load last 7 days", icon="RefreshCw",
                      on_click=ui.Call("get_overview", property_id=property_id,
                                       start_date="7daysAgo", end_date="yesterday")),
            ui.Button("Change property", icon="Database", variant="ghost",
                      on_click=ui.Call("__panel__analytics", view="properties")),
        ]),
    ]
    if cached:
        children.append(ui.Text(f"Updated {cached.get('loaded_at', '')} · {cached.get('start_date')} to {cached.get('end_date')}",
                                variant="caption"))
        children.append(ui.Stats(columns=3, children=[
            ui.Stat(label="Active users", value=cached.get("active_users", 0), icon="👥"),
            ui.Stat(label="Sessions", value=cached.get("sessions", 0), icon="📈"),
            ui.Stat(label="Views", value=cached.get("views", 0), icon="👁️"),
            ui.Stat(label="Conversions", value=cached.get("conversions", 0), icon="🎯"),
            ui.Stat(label="Total revenue", value=f"${cached.get('total_revenue', 0):,.2f}", icon="💰"),
        ]))
    else:
        children.append(ui.Empty("No overview loaded yet. Click “Load last 7 days” to fetch it from Google Analytics."))
    children.append(ui.Text("Nothing in Google Analytics is changed by loading this data.", variant="caption"))
    return ui.Page(title="Overview", subtitle="Last 7 completed days", children=children)


def _overview_empty():
    return ui.Page(title="Overview", children=[
        ui.Alert("Google account connected. Choose a GA4 property to load reporting data.",
                 title="Choose a property", type="info"),
        ui.Empty("No GA4 property selected yet."),
        ui.Button("Choose a property", icon="Database", on_click=ui.Call("__panel__analytics", view="properties")),
    ])


def _coming_soon(title, detail):
    return ui.Page(title=title, children=[ui.Empty(detail)])


# ── Properties (the picker) ─────────────────────────────────────────────

async def _properties(ctx):
    accounts_page = await ctx.store.query("google_analytics_accounts", limit=100)
    usable = [doc for doc in accounts_page.data if str((doc.data or {}).get("email") or "").lower() not in {"", "unknown"}]
    if not usable:
        return ui.Page(title="Properties", children=[
            ui.Empty("No usable Google account connected yet."),
            ui.Button("Connect Google account", icon="Plus", on_click=ui.Call("__panel__analytics", view="connect")),
        ])
    cards = []
    any_properties = False
    for doc in usable:
        email = str((doc.data or {}).get("email") or "")
        selected = await ga4.selected_property_id(ctx, email)
        out = await ga4.properties(ctx, doc)
        if not out.get("ok"):
            cards.append(ui.Alert(f"{email}: {out.get('error')}", title="Could not load properties", type="warning"))
            continue
        rows = out.get("properties") or []
        if not rows:
            continue
        any_properties = True
        for row in rows:
            is_selected = row["property_id"] == selected
            cards.append(ui.Card(
                title=row["title"], subtitle=f"{row['property_id']} · {email}",
                content=ui.Badge("Selected", color="green") if is_selected else None,
                on_click=None if is_selected else ui.Call("select_property", account=email, property_id=row["property_id"]),
                footer=ui.Row(children=[
                    ui.Button("Use this property", variant="primary", disabled=is_selected,
                              on_click=ui.Call("select_property", account=email, property_id=row["property_id"])),
                    ui.Button("Open in Google Analytics", variant="ghost", icon="ExternalLink",
                              on_click=ui.Open(f"{GOOGLE_ANALYTICS_ADMIN_URL}#/p{row['property_id']}/reports")),
                ]),
            ))
    if not any_properties and not cards:
        return ui.Page(title="Properties", children=[
            ui.Empty("This Google account has no GA4 properties, or Analytics access was not granted."),
            ui.Button("Check access", icon="ShieldCheck", on_click=ui.Call("__panel__analytics", view="settings")),
        ])
    return ui.Page(title="Properties", subtitle="Pick the GA4 property Overview and Explore will use",
                   children=[ui.Grid(columns=2, gap=3, children=cards)])


# ── Settings — connected accounts ───────────────────────────────────────

async def _settings(ctx):
    accounts_page = await ctx.store.query("google_analytics_accounts", limit=100)
    usable = [doc for doc in accounts_page.data if str((doc.data or {}).get("email") or "").lower() not in {"", "unknown"}]
    if not usable:
        return ui.Page(title="Settings", children=[
            ui.Card(title="Read-only connection", content=ui.Text(
                "GA4 settings, events, audiences and data are never changed by this app.")),
            ui.Empty("No Google account connected yet."),
            ui.Button("Connect Google account", icon="Plus", on_click=ui.Call("__panel__analytics", view="connect")),
        ])
    rows = []
    for doc in usable:
        account = await live_status(ctx, doc)
        rows.append(ui.ListItem(
            id=account.account, title=account.account,
            subtitle=f"{account.property_count} propert{'y' if account.property_count == 1 else 'ies'}"
                     + (f" · connected {account.connected_at}" if account.connected_at else ""),
            badge=ui.Badge(_STATUS_LABEL.get(account.status, account.status), color=_STATUS_COLOR.get(account.status, "gray")),
            actions=[
                {"label": "Check access", "icon": "RefreshCw",
                 "on_click": ui.Call("check_account_access", account=account.account)},
                {"label": "Reconnect", "icon": "LogIn",
                 "on_click": ui.Call("__panel__analytics", view="connect")},
                {"label": "Disconnect", "icon": "Unplug",
                 "on_click": ui.Call("disconnect_google_account", account=account.account),
                 "confirm": f"Disconnect {account.account}? Saved property selection and alert rules for it are removed. Google's own OAuth grant is not revoked."},
            ],
        ))
    return ui.Page(title="Settings", subtitle="Connected Google accounts", children=[
        ui.Card(title="Read-only connection", content=ui.Text(
            "This app only requests openid, email, profile and analytics.readonly. "
            "GA4 settings, events, audiences and data are never changed.")),
        ui.List(items=rows),
        ui.Button("Connect another Google account", icon="Plus", variant="ghost",
                  on_click=ui.Call("__panel__analytics", view="connect")),
    ])


# ── Alerts ────────────────────────────────────────────────────────────────

async def _alerts(ctx):
    accounts_page = await ctx.store.query("google_analytics_accounts", limit=100)
    usable = [doc for doc in accounts_page.data if str((doc.data or {}).get("email") or "").lower() not in {"", "unknown"}]
    if not usable:
        return ui.Page(title="Alerts", children=[
            ui.Empty("Connect a Google account first to create alert rules."),
            ui.Button("Connect Google account", icon="Plus", on_click=ui.Call("__panel__analytics", view="connect")),
        ])
    account_options = [{"value": str((doc.data or {}).get("email") or ""), "label": str((doc.data or {}).get("email") or "")}
                       for doc in usable]
    alerts_page = await ctx.store.query("google_analytics_alerts", limit=100)
    rows = []
    for doc in alerts_page.data:
        data = doc.data or {}
        metric_label = _METRIC_LABELS.get(data.get("metric"), data.get("metric"))
        condition_label = {"increase_pct": "rises by", "decrease_pct": "drops by", "above_value": "goes above",
                           "below_value": "goes below"}.get(data.get("condition"), data.get("condition"))
        threshold = data.get("threshold")
        unit = "%" if data.get("condition") in {"increase_pct", "decrease_pct"} else ""
        rows.append(ui.ListItem(
            id=doc.id, title=f"{metric_label} {condition_label} {threshold}{unit}",
            subtitle=f"{data.get('email', '')} · property {data.get('property_id', '')} · {data.get('schedule', 'daily')}",
            badge=ui.Badge("On", color="green") if data.get("enabled", True) else ui.Badge("Off", color="gray"),
            actions=[
                {"label": "Delete", "icon": "Trash2", "on_click": ui.Call("delete_alert_rule", alert_id=doc.id),
                 "confirm": "Delete this alert rule? This cannot be undone."},
            ],
        ))
    return ui.Page(title="Alerts", subtitle="Notify-only. Alerts never change GA4 settings, budgets or campaigns.", children=[
        ui.Section(title="Create alert", collapsible=True, children=[
            ui.Form(
                action="create_alert_rule", submit_label="Create alert",
                defaults={"schedule": "daily", "condition": "decrease_pct"},
                children=[
                    ui.Select(options=account_options, placeholder="Google account", param_name="account"),
                    ui.Input(placeholder="GA4 property ID", param_name="property_id"),
                    ui.Select(options=[{"value": m, "label": _METRIC_LABELS.get(m, m)} for m in ALERT_METRICS],
                              placeholder="Metric", param_name="metric"),
                    ui.Select(options=[
                        {"value": "decrease_pct", "label": "Drops by (%)"},
                        {"value": "increase_pct", "label": "Rises by (%)"},
                        {"value": "below_value", "label": "Goes below (value)"},
                        {"value": "above_value", "label": "Goes above (value)"},
                    ], value="decrease_pct", param_name="condition"),
                    ui.Input(placeholder="Threshold, e.g. 20", param_name="threshold"),
                    ui.Select(options=[{"value": "daily", "label": "Daily"}, {"value": "weekly", "label": "Weekly"}],
                              value="daily", param_name="schedule"),
                ],
            ),
        ]),
        ui.List(items=rows) if rows else ui.Empty("No alert rules yet."),
    ])
