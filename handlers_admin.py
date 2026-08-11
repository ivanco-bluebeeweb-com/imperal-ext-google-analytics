"""Part B -- account/property structure (Admin API v1beta, read-only).

Every function here only ever issues GET/list calls against Google's Admin
API. Nothing here creates, updates, or deletes anything in Google Analytics.
"""

from __future__ import annotations

from imperal_sdk import ActionResult

import ga4_client as ga4
from app import chat
from models import (AccountParam, AccountSummaryEntity, AccountSummaryList, AccountSummaryProperty,
                    CustomDimensionEntity, CustomDimensionList, CustomMetricEntity, CustomMetricList,
                    DataStreamDetailParams, DataStreamEntity, DataStreamList, GaAccountEntity, GaAccountList,
                    GoogleAdsLinkEntity, GoogleAdsLinkList, KeyEventEntity, KeyEventList, PropertyDetail,
                    PropertyDetailParams)


def _error(out: dict) -> ActionResult:
    return ActionResult.error(out.get("error") or "Google Analytics request failed.",
                              retryable=bool(out.get("retryable")), code=out.get("code") or "RESPONSE_UNEXPECTED")


async def _resolve_doc(ctx, account: str):
    resolved = await ga4.resolve_account(ctx, account)
    if not resolved.get("ok"):
        return None, resolved
    return resolved["account"], None


async def _resolve_property(ctx, account: str, property_id: str):
    doc, err = await _resolve_doc(ctx, account)
    if err:
        return None, None, err
    email = str((doc.data or {}).get("email") or "")
    pid = property_id or await ga4.selected_property_id(ctx, email)
    if not pid:
        return None, None, ga4.fail("VALIDATION_FAILED", "No GA4 property selected. Pass property_id or call select_property first.")
    return doc, pid, None


@chat.function("list_ga_accounts", "List the Google Analytics accounts (not properties) the connected Google account can see.",
               action_type="read", data_model=GaAccountList)
async def list_ga_accounts(ctx, params: AccountParam) -> ActionResult:
    """List the GA accounts (accounts.list), one level above properties."""
    doc, err = await _resolve_doc(ctx, params.account)
    if err:
        return _error(err)
    out = await ga4.admin_list(ctx, doc, "accounts", item_key="accounts")
    if not out.get("ok"):
        return _error(out)
    items = [GaAccountEntity(id=a.get("name", ""), title=a.get("displayName", ""),
                             account_id=str(a.get("name", "")).replace("accounts/", ""),
                             display_name=a.get("displayName", "")) for a in out["items"]]
    return ActionResult.success(GaAccountList(items=items, total=len(items)), summary=f"{len(items)} Google Analytics accounts.")


@chat.function("get_account_summary", "Read the full tree of Google Analytics accounts and their GA4 properties in one call.",
               action_type="read", data_model=AccountSummaryList)
async def get_account_summary(ctx, params: AccountParam) -> ActionResult:
    """Read the account -> properties tree via accountSummaries.list."""
    doc, err = await _resolve_doc(ctx, params.account)
    if err:
        return _error(err)
    out = await ga4.admin_list(ctx, doc, "accountSummaries", item_key="accountSummaries")
    if not out.get("ok"):
        return _error(out)
    items = []
    for summary in out["items"]:
        props = [AccountSummaryProperty(id=p.get("property", ""), title=p.get("displayName", ""),
                                        property_id=str(p.get("property", "")).replace("properties/", ""),
                                        display_name=p.get("displayName", ""))
                for p in summary.get("propertySummaries", [])]
        items.append(AccountSummaryEntity(id=summary.get("account", ""), title=summary.get("displayName", ""),
                                          account_id=str(summary.get("account", "")).replace("accounts/", ""),
                                          display_name=summary.get("displayName", ""), properties=props))
    return ActionResult.success(AccountSummaryList(items=items, total=len(items)),
                                summary=f"{len(items)} accounts with their properties.")


@chat.function("get_property_details", "Read a GA4 property's own settings: timezone, currency, industry, creation date.",
               action_type="read", data_model=PropertyDetail)
async def get_property_details(ctx, params: PropertyDetailParams) -> ActionResult:
    """Read one property's own settings via properties.get."""
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_get(ctx, doc, f"properties/{pid}")
    if not out.get("ok"):
        return _error(out)
    data = out["data"]
    result = PropertyDetail(id=pid, title=data.get("displayName", pid), property_id=pid,
                            display_name=data.get("displayName", ""), time_zone=data.get("timeZone", ""),
                            currency_code=data.get("currencyCode", ""), industry_category=data.get("industryCategory", ""),
                            create_time=data.get("createTime", ""))
    return ActionResult.success(result, summary=f"Details for property {pid}.")


@chat.function("list_data_streams", "List the web/iOS/Android data streams feeding a GA4 property.",
               action_type="read", data_model=DataStreamList)
async def list_data_streams(ctx, params: PropertyDetailParams) -> ActionResult:
    """List web/iOS/Android data streams via dataStreams.list."""
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_list(ctx, doc, f"properties/{pid}/dataStreams", item_key="dataStreams")
    if not out.get("ok"):
        return _error(out)
    items = []
    for s in out["items"]:
        web = s.get("webStreamData") or {}
        items.append(DataStreamEntity(id=str(s.get("name", "")).split("/")[-1], title=s.get("displayName", ""),
                                      stream_id=str(s.get("name", "")).split("/")[-1], stream_type=s.get("type", ""),
                                      display_name=s.get("displayName", ""), measurement_id=web.get("measurementId", ""),
                                      default_uri=web.get("defaultUri", "")))
    return ActionResult.success(DataStreamList(items=items, total=len(items)), summary=f"{len(items)} data streams for property {pid}.")


@chat.function("get_data_stream_details", "Read one GA4 data stream's Measurement ID and settings.",
               action_type="read", data_model=DataStreamEntity)
async def get_data_stream_details(ctx, params: DataStreamDetailParams) -> ActionResult:
    """Read one data stream's Measurement ID and settings via dataStreams.get."""
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_get(ctx, doc, f"properties/{pid}/dataStreams/{params.stream_id}")
    if not out.get("ok"):
        return _error(out)
    s = out["data"]
    web = s.get("webStreamData") or {}
    result = DataStreamEntity(id=params.stream_id, title=s.get("displayName", ""), stream_id=params.stream_id,
                              stream_type=s.get("type", ""), display_name=s.get("displayName", ""),
                              measurement_id=web.get("measurementId", ""), default_uri=web.get("defaultUri", ""))
    return ActionResult.success(result, summary=f"Data stream {params.stream_id} details.")


@chat.function("list_custom_dimensions", "List custom dimensions registered on a GA4 property.",
               action_type="read", data_model=CustomDimensionList)
async def list_custom_dimensions(ctx, params: PropertyDetailParams) -> ActionResult:
    """List registered custom dimensions via customDimensions.list."""
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_list(ctx, doc, f"properties/{pid}/customDimensions", item_key="customDimensions")
    if not out.get("ok"):
        return _error(out)
    items = [CustomDimensionEntity(id=c.get("parameterName", ""), title=c.get("displayName", ""),
                                   parameter_name=c.get("parameterName", ""), display_name=c.get("displayName", ""),
                                   scope=c.get("scope", ""), description=c.get("description", "")) for c in out["items"]]
    return ActionResult.success(CustomDimensionList(items=items, total=len(items)),
                                summary=f"{len(items)} custom dimensions for property {pid}.")


@chat.function("list_custom_metrics", "List custom metrics registered on a GA4 property.",
               action_type="read", data_model=CustomMetricList)
async def list_custom_metrics(ctx, params: PropertyDetailParams) -> ActionResult:
    """List registered custom metrics via customMetrics.list."""
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_list(ctx, doc, f"properties/{pid}/customMetrics", item_key="customMetrics")
    if not out.get("ok"):
        return _error(out)
    items = [CustomMetricEntity(id=c.get("parameterName", ""), title=c.get("displayName", ""),
                                parameter_name=c.get("parameterName", ""), display_name=c.get("displayName", ""),
                                measurement_unit=c.get("measurementUnit", ""), scope=c.get("scope", ""),
                                description=c.get("description", "")) for c in out["items"]]
    return ActionResult.success(CustomMetricList(items=items, total=len(items)),
                                summary=f"{len(items)} custom metrics for property {pid}.")


@chat.function("list_key_events", "List which GA4 events are marked as key events (conversions) on a property.",
               action_type="read", data_model=KeyEventList)
async def list_key_events(ctx, params: PropertyDetailParams) -> ActionResult:
    """List events marked as key events (conversions) via keyEvents.list."""
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_list(ctx, doc, f"properties/{pid}/keyEvents", item_key="keyEvents")
    if not out.get("ok"):
        return _error(out)
    items = [KeyEventEntity(id=k.get("eventName", ""), title=k.get("eventName", ""), event_name=k.get("eventName", ""),
                            custom=bool(k.get("custom")), counting_method=k.get("countingMethod", "")) for k in out["items"]]
    return ActionResult.success(KeyEventList(items=items, total=len(items)), summary=f"{len(items)} key events for property {pid}.")


@chat.function("list_google_ads_links", "List Google Ads accounts linked to a GA4 property.",
               action_type="read", data_model=GoogleAdsLinkList)
async def list_google_ads_links(ctx, params: PropertyDetailParams) -> ActionResult:
    """List linked Google Ads accounts via googleAdsLinks.list."""
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_list(ctx, doc, f"properties/{pid}/googleAdsLinks", item_key="googleAdsLinks")
    if not out.get("ok"):
        return _error(out)
    items = [GoogleAdsLinkEntity(id=str(l.get("name", "")).split("/")[-1], title=l.get("customerId", ""),
                                 customer_id=l.get("customerId", ""), can_manage_clients=bool(l.get("canManageClients")),
                                 ads_personalization_enabled=bool(l.get("adsPersonalizationEnabled"))) for l in out["items"]]
    return ActionResult.success(GoogleAdsLinkList(items=items, total=len(items)),
                                summary=f"{len(items)} Google Ads links for property {pid}.")
