"""Google Analytics 4 panel screens.

The UI is deliberately property-first: until a GA4 property is selected there
are no report links to click. Every visible report action maps to an existing
GA4 handler; this module never renders invented analytics data.
"""

from imperal_sdk import ui

import ga4_client as ga4
from app import APP_ID, ext
from handlers import cached_overview
from handlers_accounts import live_status
from handlers_alerts import ALERT_METRICS, _METRIC_LABELS

REDIRECT_URI = f"https://panel.imperal.io/v1/ext/{APP_ID}/oauth/google/callback"
GOOGLE_CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials"
IMPERAL_SECRETS_URL = f"https://panel.imperal.io/ext/{APP_ID}/secrets"

_STATUS_COLOR = {"connected": "green", "reconnect_required": "red",
                 "insufficient_access": "yellow", "error": "red"}
_STATUS_LABEL = {"connected": "Connected", "reconnect_required": "Reconnect needed",
                 "insufficient_access": "Insufficient access", "error": "Error"}

_REPORTS = {
    "channels": ("Traffic by channel", "get_traffic_by_channel"),
    "pages": ("Top pages", "get_top_pages"),
    "landing": ("Landing pages", "get_landing_pages_report"),
    "referrers": ("Top referrers", "get_top_referrers"),
    "conversions": ("Conversions", "get_conversions_report"),
    "ecommerce": ("E-commerce", "get_ecommerce_overview"),
    "geo": ("Locations", "get_geo_breakdown"),
    "device": ("Devices", "get_device_breakdown"),
    "campaigns": ("Campaigns", "get_campaign_performance"),
}


def _usable_accounts(page):
    return [doc for doc in page.data if str((doc.data or {}).get("email") or "").lower() not in {"", "unknown"}]


async def _accounts(ctx):
    return _usable_accounts(await ctx.store.query("google_analytics_accounts", limit=100))


def _connect_button():
    return ui.Button("Connect Google Account", icon="Plus", full_width=True,
                     on_click=ui.Call("__panel__analytics", view="connect"))


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
        ])
    return ui.Page(title="Connect Google Analytics", children=[
        ui.Button("Connect Google Account", icon="ExternalLink", on_click=ui.Open(url)),
    ])


async def _property_options(ctx, account):
    """Return only the GA4 properties accessible to the selected account."""
    out = await ga4.properties(ctx, account)
    if not out.get("ok"):
        return []
    return [
        {"value": row["property_id"], "label": str(row.get("title") or row["property_id"])}
        for row in out.get("properties") or []
    ]


def _account_options(accounts):
    return [
        {"value": str((doc.data or {}).get("email") or ""),
         "label": str((doc.data or {}).get("email") or "")}
        for doc in accounts
    ]


@ext.panel("analytics_nav", slot="left", title="Google Analytics", icon="ChartNoAxesCombined",
           default_width=280, min_width=220, max_width=400,
           refresh="on_event:google-analytics-bluebee.account.connect,google-analytics-bluebee.account.switched,google-analytics-bluebee.account.disconnected,google-analytics-bluebee.property.selected")
async def analytics_nav(ctx, view="", **kwargs):
    accounts = await _accounts(ctx)
    if not accounts:
        return ui.Stack(children=[_connect_button()])

    active = await ga4.active_account(ctx)
    active_email = str((active.data or {}).get("email") or "") if active else ""
    selection = await ga4.global_selected_property(ctx)
    # A property only remains selected when it belongs to the active account.
    property_id = selection.get("property_id", "") if selection.get("email", "").lower() == active_email.lower() else ""

    children = [
        ui.Text("Google account", variant="caption"),
        ui.Select(
            options=_account_options(accounts), value=active_email,
            placeholder="Select a connected Google account", param_name="account",
            on_change=ui.Call("switch_account", account="{{value}}"),
        ),
        ui.Button("Add another Google account", icon="Plus", variant="ghost", full_width=True,
                  on_click=ui.Call("__panel__analytics", view="connect")),
        ui.Divider(),
        ui.Text("GA4 property", variant="caption"),
    ]
    options = await _property_options(ctx, active) if active else []
    if options:
        children.append(ui.Select(
            options=options, value=property_id, placeholder="Select a GA4 property",
            param_name="property_id",
            on_change=ui.Call("select_property", account=active_email, property_id="{{value}}"),
        ))
    else:
        children.append(ui.Text("No accessible GA4 properties found for this account.", variant="caption"))

    if property_id:
        menu = [
            ("overview", "Overview", "LayoutDashboard"),
            ("explore", "Explore", "ChartColumn"),
            ("realtime", "Real-time", "Activity"),
            ("reports", "Site reports", "FileBarChart"),
            ("alerts", "Alerts", "BellRing"),
        ]
        children += [ui.Divider(), ui.List(items=[
            ui.ListItem(id=item_id, title=title, icon=icon, selected=(view == item_id),
                        on_click=ui.Call("__panel__analytics", view=item_id, property_id=property_id))
            for item_id, title, icon in menu
        ])]
    children += [ui.Divider(), ui.Button("Settings", icon="Settings", variant="secondary", full_width=True,
                                         on_click=ui.Call("__panel__analytics", view="settings", property_id=property_id))]
    return ui.Stack(children=children, gap=2)


@ext.panel("analytics", slot="center", title="Google Analytics", icon="ChartNoAxesCombined", center_overlay=True)
async def analytics(ctx, view="overview", property_id="", report="channels", **kwargs):
    accounts = await _accounts(ctx)
    if view == "connect":
        return await _connect(ctx)
    if not accounts:
        return ui.Page(title="Google Analytics", children=[_connect_button()])

    active = await ga4.active_account(ctx)
    active_email = str((active.data or {}).get("email") or "") if active else ""
    selected = await ga4.global_selected_property(ctx)
    selected_for_active_account = (
        selected.get("property_id", "")
        if selected.get("email", "").lower() == active_email.lower()
        else ""
    )
    property_id = property_id or selected_for_active_account
    if property_id and property_id != selected_for_active_account:
        owner = await ga4.account_for_property(ctx, property_id)
        if owner:
            email = str((owner.data or {}).get("email") or "")
            await _persist_property_selection(ctx, email, property_id)
            selected_for_active_account = property_id if email.lower() == active_email.lower() else ""
            if not selected_for_active_account:
                property_id = ""
    if view == "settings":
        return await _settings(ctx)
    if not property_id:
        return ui.Page(title="Google Analytics", children=[ui.Empty("Select a GA4 property in the sidebar to load reporting.")])
    if view == "overview":
        return await _overview(ctx, property_id)
    if view == "explore":
        return _explore(property_id)
    if view == "realtime":
        return _realtime(property_id)
    if view == "reports":
        return _site_reports(property_id, report)
    if view == "alerts":
        return await _alerts(ctx, property_id)
    return await _overview(ctx, property_id)


async def _persist_property_selection(ctx, email, property_id):
    selections = await ctx.store.query("google_analytics_selections", limit=100)
    found = None
    for doc in selections.data:
        data = doc.data or {}
        if str(data.get("email") or "").lower() == email.lower():
            found = doc
        elif data.get("is_current"):
            await ctx.store.update("google_analytics_selections", doc.id, {**data, "is_current": False})
    record = {"email": email.lower(), "property_id": property_id, "is_current": True}
    if found:
        await ctx.store.update("google_analytics_selections", found.id, record)
    else:
        await ctx.store.create("google_analytics_selections", record)


async def _overview(ctx, property_id):
    cached = await cached_overview(ctx, property_id)
    children = [ui.Button("Load last 7 days", icon="RefreshCw",
                          on_click=ui.Call("get_overview", property_id=property_id,
                                           start_date="7daysAgo", end_date="yesterday"))]
    if cached:
        children += [
            ui.Text(f"Updated {cached.get('loaded_at', '')} · {cached.get('start_date')} to {cached.get('end_date')}", variant="caption"),
            ui.Stats(columns=3, children=[
                ui.Stat(label="Active users", value=cached.get("active_users", 0), icon="Users"),
                ui.Stat(label="Sessions", value=cached.get("sessions", 0), icon="ChartNoAxesCombined"),
                ui.Stat(label="Views", value=cached.get("views", 0), icon="Eye"),
                ui.Stat(label="Conversions", value=cached.get("conversions", 0), icon="Target"),
                ui.Stat(label="Revenue", value=f"{cached.get('total_revenue', 0):,.2f}", icon="CircleDollarSign"),
            ]),
        ]
    else:
        children.append(ui.Empty("No overview loaded yet. Load the last 7 days to fetch real GA4 data."))
    return ui.Page(title="Overview", subtitle=f"Property {property_id}", children=children)


def _explore(property_id):
    return ui.Page(title="Explore", subtitle="Run a real GA4 custom report", children=[
        ui.Form(action="run_custom_report", submit_label="Run report", defaults={
            "property_id": property_id, "start_date": "7daysAgo", "end_date": "yesterday", "limit": 20,
        }, children=[
            ui.TagInput(param_name="dimensions", placeholder="Add a dimension (e.g. country)"),
            ui.TagInput(param_name="metrics", placeholder="Add a metric (e.g. sessions)"),
            ui.Input(param_name="start_date", placeholder="Start date", value="7daysAgo"),
            ui.Input(param_name="end_date", placeholder="End date", value="yesterday"),
        ]),
        ui.Text("Use GA4 API names. The result is returned by the live report action; no sample data is shown here.", variant="caption"),
    ])


def _realtime(property_id):
    return ui.Page(title="Real-time", subtitle="The most recent approximately 30 minutes", children=[
        ui.Form(action="run_realtime_report", submit_label="Load real-time data", defaults={
            "property_id": property_id, "metrics": ["activeUsers"], "limit": 20,
        }, children=[
            ui.TagInput(param_name="dimensions", placeholder="Optional dimension (e.g. eventName)"),
            ui.TagInput(param_name="metrics", values=["activeUsers"], placeholder="Add a metric"),
        ]),
    ])


def _site_reports(property_id, report):
    report = report if report in _REPORTS else "channels"
    title, action = _REPORTS[report]
    items = [ui.ListItem(id=key, title=label, selected=(key == report),
                         on_click=ui.Call("__panel__analytics", view="reports", report=key, property_id=property_id))
             for key, (label, _) in _REPORTS.items()]
    return ui.Page(title="Site reports", subtitle=f"Property {property_id}", children=[
        ui.List(items=items),
        ui.Divider(),
        ui.Section(title=title, children=[
            ui.Form(action=action, submit_label=f"Load {title.lower()}", defaults={
                "property_id": property_id, "start_date": "7daysAgo", "end_date": "yesterday", "limit": 20,
            }, children=[
                ui.Input(param_name="start_date", placeholder="Start date", value="7daysAgo"),
                ui.Input(param_name="end_date", placeholder="End date", value="yesterday"),
            ]),
        ]),
    ])


async def _settings(ctx):
    accounts = await _accounts(ctx)
    rows = []
    for doc in accounts:
        account = await live_status(ctx, doc)
        subtitle = f"{account.property_count} propert{'y' if account.property_count == 1 else 'ies'}"
        subtitle += " · Active" if account.is_active else " · Inactive"
        actions = [{"label": "Check access", "icon": "RefreshCw", "on_click": ui.Call("check_account_access", account=account.account)}]
        if not account.is_active:
            actions.append({"label": "Switch to this account", "icon": "ArrowLeftRight", "on_click": ui.Call("switch_account", account=account.account)})
        actions.append({"label": "Disconnect", "icon": "Unplug", "on_click": ui.Call("disconnect_google_account", account=account.account),
                        "confirm": f"Disconnect {account.account}? Saved property selections and alert rules for it are removed. Google's OAuth grant is not revoked."})
        rows.append(ui.ListItem(id=account.account, title=account.account, subtitle=subtitle,
                                badge=ui.Badge(_STATUS_LABEL.get(account.status, account.status), color=_STATUS_COLOR.get(account.status, "gray")), actions=actions))
    return ui.Page(title="Settings", subtitle="Connected Google accounts", children=[ui.List(items=rows),
        ui.Button("Add another Google account", icon="Plus", variant="secondary", on_click=ui.Call("__panel__analytics", view="connect"))])


async def _alerts(ctx, property_id):
    accounts = await _accounts(ctx)
    selected = await ga4.global_selected_property(ctx)
    account_options = [{"value": str((doc.data or {}).get("email") or ""), "label": str((doc.data or {}).get("email") or "")} for doc in accounts]
    alerts_page = await ctx.store.query("google_analytics_alerts", limit=100)
    rows = []
    for doc in alerts_page.data:
        data = doc.data or {}
        rows.append(ui.ListItem(id=doc.id, title=f"{_METRIC_LABELS.get(data.get('metric'), data.get('metric'))} alert",
                                subtitle=f"Property {data.get('property_id', '')} · {data.get('schedule', 'daily')}",
                                actions=[{"label": "Delete", "icon": "Trash2", "on_click": ui.Call("delete_alert_rule", alert_id=doc.id),
                                          "confirm": "Delete this alert rule? This cannot be undone."}]))
    return ui.Page(title="Alerts", subtitle="Notify-only. Alerts never change GA4 data or settings.", children=[
        ui.Section(title="Create alert", collapsible=True, children=[ui.Form(action="create_alert_rule", submit_label="Create alert", defaults={
            "account": selected.get("email", ""), "property_id": property_id, "schedule": "daily", "condition": "decrease_pct",
        }, children=[
            ui.Select(options=account_options, value=selected.get("email", ""), param_name="account", placeholder="Google account"),
            ui.Input(param_name="property_id", value=property_id, placeholder="GA4 property ID"),
            ui.Select(options=[{"value": metric, "label": _METRIC_LABELS.get(metric, metric)} for metric in ALERT_METRICS], param_name="metric", placeholder="Metric"),
            ui.Select(options=[{"value": "decrease_pct", "label": "Drops by (%)"}, {"value": "increase_pct", "label": "Rises by (%)"}, {"value": "below_value", "label": "Goes below"}, {"value": "above_value", "label": "Goes above"}], value="decrease_pct", param_name="condition"),
            ui.Input(param_name="threshold", placeholder="Threshold, e.g. 20"),
            ui.Select(options=[{"value": "daily", "label": "Daily"}, {"value": "weekly", "label": "Weekly"}], value="daily", param_name="schedule"),
        ])]),
        ui.List(items=rows) if rows else ui.Empty("No alert rules yet."),
    ])
