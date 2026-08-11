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


# ──────────────────────────────────────────────────────────────────────────
# Part A -- custom/canned reports (Data API v1beta, analytics.readonly).
# ──────────────────────────────────────────────────────────────────────────


class DateRangeParams(AccountParam):
    property_id: str = Field("", description="GA4 property ID; omit to use the selected property.")
    start_date: str = Field("7daysAgo", description="GA4 start date, e.g. 7daysAgo or 2026-08-01.")
    end_date: str = Field("yesterday", description="GA4 end date, e.g. yesterday or 2026-08-02.")
    limit: int = Field(10, description="Max rows to return (1-100).")


class ReportRow(sdl.Entity):
    values: dict = {}


class ReportRowList(sdl.EntityList[ReportRow]):
    pass


class RunCustomReportParams(DateRangeParams):
    dimensions: list[str] = Field(default_factory=list, description="GA4 dimension API names, e.g. ['pagePath', 'country'].")
    metrics: list[str] = Field(default_factory=list, description="GA4 metric API names, e.g. ['activeUsers', 'sessions'].")


class RunRealtimeReportParams(AccountParam):
    property_id: str = Field("", description="GA4 property ID; omit to use the selected property.")
    dimensions: list[str] = Field(default_factory=list, description="GA4 realtime dimension API names, e.g. ['country', 'unifiedScreenName'].")
    metrics: list[str] = Field(default_factory=lambda: ["activeUsers"], description="GA4 realtime metric API names.")
    limit: int = Field(10, description="Max rows to return (1-100).")


class RunPivotReportParams(DateRangeParams):
    row_dimension: str = Field(..., description="Dimension for pivot rows, e.g. 'country'.")
    column_dimension: str = Field(..., description="Dimension for pivot columns, e.g. 'deviceCategory'.")
    metrics: list[str] = Field(default_factory=lambda: ["activeUsers"], description="GA4 metric API names.")


class BatchReportSpec(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)


class BatchRunReportsParams(DateRangeParams):
    reports: list[BatchReportSpec] = Field(..., description="Up to 5 dimension/metric combinations to run together.")


class CheckCompatibilityParams(AccountParam):
    property_id: str = Field("", description="GA4 property ID; omit to use the selected property.")
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)


class CompatibilityItem(sdl.Entity):
    api_name: str = ""
    compatibility: str = ""


class CompatibilityCheck(sdl.Entity):
    property_id: str = ""
    dimensions: list[CompatibilityItem] = []
    metrics: list[CompatibilityItem] = []


class ReportMetadataParams(AccountParam):
    property_id: str = Field("", description="GA4 property ID; omit to use the selected property.")


class MetadataField(sdl.Entity):
    api_name: str = ""
    ui_name: str = ""
    description: str = ""


class ReportMetadata(sdl.Entity):
    property_id: str = ""
    dimensions: list[MetadataField] = []
    metrics: list[MetadataField] = []


class ComparePeriodsParams(AccountParam):
    property_id: str = Field("", description="GA4 property ID; omit to use the selected property.")
    metrics: list[str] = Field(default_factory=lambda: ["activeUsers", "sessions", "conversions"],
                               description="GA4 metric API names to compare.")
    start_date: str = Field("7daysAgo", description="Current period start date.")
    end_date: str = Field("yesterday", description="Current period end date.")
    compare_start_date: str = Field("14daysAgo", description="Previous period start date.")
    compare_end_date: str = Field("8daysAgo", description="Previous period end date.")


class MetricComparison(sdl.Entity):
    metric: str = ""
    current_value: float = 0.0
    previous_value: float = 0.0
    change_pct: float = 0.0


class PeriodComparison(sdl.Entity):
    property_id: str = ""
    start_date: str = ""
    end_date: str = ""
    compare_start_date: str = ""
    compare_end_date: str = ""
    metrics: list[MetricComparison] = []


class ExportReportCsvParams(RunCustomReportParams):
    pass


class ReportCsv(sdl.Entity):
    property_id: str = ""
    row_count: int = 0
    csv: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Part B -- account/property structure (Admin API v1beta, GET/LIST only).
# ──────────────────────────────────────────────────────────────────────────


class GaAccountEntity(sdl.Entity):
    account_id: str = ""
    display_name: str = ""


class GaAccountList(sdl.EntityList[GaAccountEntity]):
    pass


class AccountSummaryProperty(sdl.Entity):
    property_id: str = ""
    display_name: str = ""


class AccountSummaryEntity(sdl.Entity):
    account_id: str = ""
    display_name: str = ""
    properties: list[AccountSummaryProperty] = []


class AccountSummaryList(sdl.EntityList[AccountSummaryEntity]):
    pass


class PropertyDetailParams(AccountParam):
    property_id: str = Field("", description="GA4 property ID; omit to use the selected property.")


class PropertyDetail(sdl.Entity):
    property_id: str = ""
    display_name: str = ""
    time_zone: str = ""
    currency_code: str = ""
    industry_category: str = ""
    create_time: str = ""


class DataStreamEntity(sdl.Entity):
    stream_id: str = ""
    stream_type: str = ""
    display_name: str = ""
    measurement_id: str = ""
    default_uri: str = ""


class DataStreamList(sdl.EntityList[DataStreamEntity]):
    pass


class DataStreamDetailParams(PropertyDetailParams):
    stream_id: str = Field(..., description="Data stream ID from list_data_streams.")


class CustomDimensionEntity(sdl.Entity):
    parameter_name: str = ""
    display_name: str = ""
    scope: str = ""
    description: str = ""


class CustomDimensionList(sdl.EntityList[CustomDimensionEntity]):
    pass


class CustomMetricEntity(sdl.Entity):
    parameter_name: str = ""
    display_name: str = ""
    measurement_unit: str = ""
    scope: str = ""
    description: str = ""


class CustomMetricList(sdl.EntityList[CustomMetricEntity]):
    pass


class KeyEventEntity(sdl.Entity):
    event_name: str = ""
    custom: bool = False
    counting_method: str = ""


class KeyEventList(sdl.EntityList[KeyEventEntity]):
    pass


class GoogleAdsLinkEntity(sdl.Entity):
    customer_id: str = ""
    can_manage_clients: bool = False
    ads_personalization_enabled: bool = False


class GoogleAdsLinkList(sdl.EntityList[GoogleAdsLinkEntity]):
    pass


# ──────────────────────────────────────────────────────────────────────────
# Part C -- alert rule management extensions.
# ──────────────────────────────────────────────────────────────────────────


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


class UpdateAlertParams(AlertIdParams):
    threshold: float | None = Field(None, description="New threshold; omit to leave unchanged.")
    schedule: str = Field("", description="New schedule (daily/weekly); omit to leave unchanged.")
    condition: str = Field("", description="New condition; omit to leave unchanged.")


class TestAlertResult(sdl.Entity):
    alert_id: str = ""
    would_trigger: bool = False
    current_value: float = 0.0
    previous_value: float = 0.0
    threshold: float = 0.0


class AlertHistoryEntry(sdl.Entity):
    alert_id: str = ""
    triggered_at: str = ""
    current_value: float = 0.0
    previous_value: float = 0.0


class AlertHistoryList(sdl.EntityList[AlertHistoryEntry]):
    pass


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


# ──────────────────────────────────────────────────────────────────────────
# Part D -- write/edit extensions (Admin API v1beta, requires analytics.edit
# scope AND an Editor/Administrator GA4 role on the property). Every
# function here changes something real in the user's Google Analytics
# property. Nothing here is scheduled or run without an explicit call.
# ──────────────────────────────────────────────────────────────────────────


CUSTOM_DIMENSION_SCOPES = ("EVENT", "USER")
CUSTOM_METRIC_SCOPES = ("EVENT",)
CUSTOM_METRIC_UNITS = ("STANDARD", "CURRENCY", "FEET", "METERS", "KILOMETERS", "MILES", "MILLISECONDS",
                       "SECONDS", "MINUTES", "HOURS")
KEY_EVENT_COUNTING_METHODS = ("ONCE_PER_EVENT", "ONCE_PER_SESSION")
DATA_STREAM_TYPES = ("WEB_DATA_STREAM", "ANDROID_APP_DATA_STREAM", "IOS_APP_DATA_STREAM")


class CreateCustomDimensionParams(PropertyDetailParams):
    parameter_name: str = Field(..., description="The event/user parameter name this dimension tracks, e.g. 'plan_tier'. Cannot be changed after creation.")
    display_name: str = Field(..., description="Human-readable name shown in GA4 reports.")
    scope: str = Field("EVENT", description="EVENT or USER. Cannot be changed after creation.")
    description: str = Field("", description="Optional description shown in the GA4 UI.")


class ArchiveCustomDimensionParams(PropertyDetailParams):
    parameter_name: str = Field(..., description="parameter_name of the custom dimension to archive, from list_custom_dimensions.")


class CreateCustomMetricParams(PropertyDetailParams):
    parameter_name: str = Field(..., description="The event parameter name this metric tracks, e.g. 'cart_value'. Cannot be changed after creation.")
    display_name: str = Field(..., description="Human-readable name shown in GA4 reports.")
    measurement_unit: str = Field("STANDARD", description="STANDARD, CURRENCY, FEET, METERS, SECONDS, etc.")
    scope: str = Field("EVENT", description="Only EVENT is currently supported by GA4 for custom metrics.")
    description: str = Field("", description="Optional description shown in the GA4 UI.")


class ArchiveCustomMetricParams(PropertyDetailParams):
    parameter_name: str = Field(..., description="parameter_name of the custom metric to archive, from list_custom_metrics.")


class CreateKeyEventParams(PropertyDetailParams):
    event_name: str = Field(..., description="Exact GA4 event name to mark as a key event (conversion), e.g. 'purchase'.")
    counting_method: str = Field("ONCE_PER_EVENT", description="ONCE_PER_EVENT (every occurrence counts) or ONCE_PER_SESSION.")


class UpdateKeyEventParams(PropertyDetailParams):
    event_name: str = Field(..., description="Event name of the existing key event to update, from list_key_events.")
    counting_method: str = Field(..., description="ONCE_PER_EVENT or ONCE_PER_SESSION.")


class DeleteKeyEventParams(PropertyDetailParams):
    event_name: str = Field(..., description="Event name of the key event to unmark, from list_key_events. The underlying GA4 event itself is untouched -- only its conversion status is removed.")


class CreateGoogleAdsLinkParams(PropertyDetailParams):
    customer_id: str = Field(..., description="Google Ads customer ID to link, e.g. '1234567890' (no dashes).")
    can_manage_clients: bool = Field(False, description="Whether this link can manage Google Ads manager-account clients.")
    ads_personalization_enabled: bool = Field(True, description="Whether GA4 data can be used for Google Ads personalization.")


class UpdateGoogleAdsLinkParams(PropertyDetailParams):
    link_id: str = Field(..., description="Google Ads link id, from list_google_ads_links.")
    ads_personalization_enabled: bool | None = Field(None, description="New value; omit to leave unchanged.")


class DeleteGoogleAdsLinkParams(PropertyDetailParams):
    link_id: str = Field(..., description="Google Ads link id, from list_google_ads_links.")


class UpdatePropertyDetailsParams(PropertyDetailParams):
    display_name: str = Field("", description="New property display name; omit to leave unchanged.")
    time_zone: str = Field("", description="New IANA timezone, e.g. 'America/Los_Angeles'; omit to leave unchanged.")
    currency_code: str = Field("", description="New ISO currency code, e.g. 'USD'; omit to leave unchanged.")
    industry_category: str = Field("", description="New GA4 industry category enum value; omit to leave unchanged.")


class CreateDataStreamParams(PropertyDetailParams):
    display_name: str = Field(..., description="Name for the new data stream.")
    default_uri: str = Field(..., description="The site's root URL, e.g. 'https://example.com'. Required for WEB_DATA_STREAM.")
    stream_type: str = Field("WEB_DATA_STREAM", description="WEB_DATA_STREAM, ANDROID_APP_DATA_STREAM, or IOS_APP_DATA_STREAM. Cannot be changed after creation.")


class WriteConfirmation(sdl.Entity):
    """Generic confirmation entity for destructive Part D calls that remove something from GA4."""
    detail: str = ""


class UpdateDataStreamParams(DataStreamDetailParams):
    display_name: str = Field("", description="New display name; omit to leave unchanged.")
    default_uri: str = Field("", description="New root URL (web streams only); omit to leave unchanged.")


class DeleteDataStreamParams(DataStreamDetailParams):
    pass
