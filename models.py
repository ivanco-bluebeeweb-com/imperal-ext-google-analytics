"""Typed GA4 read-only chat contracts."""

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    pass


class AccountParam(BaseModel):
    account: str = Field("", description="Connected Google account email; omit when only one is connected.")


class SelectPropertyParams(AccountParam):
    property_id: str = Field(..., description="GA4 property ID from list_properties.")


class OverviewParams(AccountParam):
    property_id: str = Field("", description="GA4 property ID; omit to use the selected property.")
    start_date: str = Field("7daysAgo", description="GA4 start date, e.g. 7daysAgo or 2026-08-01.")
    end_date: str = Field("yesterday", description="GA4 end date, e.g. yesterday or 2026-08-02.")


class GA4Property(sdl.Entity):
    property_id: str = ""
    account: str = ""
    selected: bool = False


class GA4PropertyList(sdl.EntityList[GA4Property]):
    pass


class GA4Overview(sdl.Entity):
    property_id: str = ""
    start_date: str = ""
    end_date: str = ""
    active_users: int = 0
    sessions: int = 0
    views: int = 0
    conversions: int = 0
    total_revenue: float = 0.0


class PropertySelection(sdl.Entity):
    account: str = ""
    property_id: str = ""


class AccountAction(AccountParam):
    pass


class GA4Account(sdl.Entity):
    account: str = ""
    connected_at: str = ""
    property_count: int = 0
    status: str = ""  # "connected" | "reconnect_required" | "insufficient_access" | "error"
    is_active: bool = False


class GA4AccountList(sdl.EntityList[GA4Account]):
    pass


class AccountSwitched(sdl.Entity):
    active: str = ""


class RawAccountRecord(sdl.Entity):
    """One unfiltered account record as stored, for OAuth email-resolution diagnostics."""
    email: str = ""
    provider: str = ""
    is_active: bool = False
    has_access_token: bool = False
    has_refresh_token: bool = False
    expires_at: str = ""
    created_at: str = ""
    all_keys: str = ""


class RawAccountDump(sdl.EntityList[RawAccountRecord]):
    pass


ALERT_METRICS = ("active_users", "sessions", "conversions", "total_revenue")
ALERT_CONDITIONS = ("increase_pct", "decrease_pct", "above_value", "below_value")
ALERT_SCHEDULES = ("daily", "weekly")


class CreateAlertParams(AccountParam):
    property_id: str = Field(..., description="GA4 property ID this alert watches.")
    metric: str = Field(..., description="Metric to watch: active_users, sessions, conversions, or total_revenue.")
    condition: str = Field(..., description="One of increase_pct, decrease_pct, above_value, below_value.")
    threshold: float = Field(..., description="Percent (0-100) for *_pct conditions, or a raw metric value for *_value conditions.")
    schedule: str = Field("daily", description="How often to evaluate: daily or weekly.")


class AlertIdParams(BaseModel):
    alert_id: str = Field(..., description="Alert rule ID from list_alert_rules.")


class GA4Alert(sdl.Entity):
    account: str = ""
    property_id: str = ""
    metric: str = ""
    condition: str = ""
    threshold: float = 0.0
    schedule: str = ""
    enabled: bool = True
    last_triggered_at: str = ""


class GA4AlertList(sdl.EntityList[GA4Alert]):
    pass
