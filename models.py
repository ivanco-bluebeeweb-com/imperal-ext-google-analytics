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
