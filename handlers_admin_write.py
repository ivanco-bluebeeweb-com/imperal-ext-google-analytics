"""Part D -- write/edit extensions (Admin API v1beta).

Every function here changes something real in the user's Google Analytics
property: creates a custom dimension, marks an event as a conversion, links
a Google Ads account, edits property settings, or manages data streams.

This is a deliberately different trust boundary from Parts A/B/C, which
never write anything. Two things outside this app's control gate every
call here and are surfaced as ordinary error codes, not new failure modes:

1. The connected Google account must have granted the analytics.edit scope.
   Accounts connected before this scope existed only hold analytics.readonly
   and must reconnect (disconnect_google_account then connect_google_analytics
   again, accepting the new consent screen) before any function below can
   succeed -- Google will reject the call with TOKEN_REJECTED/PERMISSION_DENIED
   regardless of what this code does.
2. The connected Google account's role ON THE GA4 PROPERTY ITSELF (set inside
   Google Analytics, not here) must be Editor or Administrator. Viewer/Analyst
   roles will get PERMISSION_DENIED even with the right OAuth scope granted.
"""

from __future__ import annotations

from imperal_sdk import ActionResult

import ga4_client as ga4
from app import chat
from handlers_admin import _error, _resolve_property
from models import (ArchiveCustomDimensionParams, ArchiveCustomMetricParams, CreateCustomDimensionParams,
                    CreateCustomMetricParams, CreateDataStreamParams, CreateGoogleAdsLinkParams,
                    CreateKeyEventParams, CustomDimensionEntity, CustomMetricEntity, DataStreamEntity,
                    DeleteDataStreamParams, DeleteGoogleAdsLinkParams, DeleteKeyEventParams, GoogleAdsLinkEntity,
                    KeyEventEntity, PropertyDetail, UpdateDataStreamParams, UpdateGoogleAdsLinkParams,
                    UpdateKeyEventParams, UpdatePropertyDetailsParams)


@chat.function("create_custom_dimension",
               "Register a new custom dimension on a GA4 property so an event/user parameter shows up in reports. "
               "Requires the connected account to have Editor access on the property.",
               action_type="write", data_model=CustomDimensionEntity)
async def create_custom_dimension(ctx, params: CreateCustomDimensionParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {"parameterName": params.parameter_name, "displayName": params.display_name, "scope": params.scope,
            "description": params.description}
    out = await ga4.admin_create(ctx, doc, f"properties/{pid}/customDimensions", body)
    if not out.get("ok"):
        return _error(out)
    c = out["data"]
    result = CustomDimensionEntity(id=c.get("parameterName", ""), title=c.get("displayName", ""),
                                   parameter_name=c.get("parameterName", ""), display_name=c.get("displayName", ""),
                                   scope=c.get("scope", ""), description=c.get("description", ""))
    return ActionResult.success(result, summary=f"Created custom dimension '{params.display_name}' on property {pid}.")


@chat.function("archive_custom_dimension",
               "Archive a custom dimension on a GA4 property. Archiving is permanent -- GA4 does not support "
               "un-archiving, and the parameter_name cannot be reused for 1 week after archiving.",
               action_type="destructive")
async def archive_custom_dimension(ctx, params: ArchiveCustomDimensionParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_action(ctx, doc, f"properties/{pid}/customDimensions/{params.parameter_name}:archive")
    if not out.get("ok"):
        return _error(out)
    return ActionResult.success({"parameter_name": params.parameter_name},
                                summary=f"Archived custom dimension '{params.parameter_name}' on property {pid}.")


@chat.function("create_custom_metric",
               "Register a new custom metric on a GA4 property so an event parameter is tracked as a number. "
               "Requires the connected account to have Editor access on the property.",
               action_type="write", data_model=CustomMetricEntity)
async def create_custom_metric(ctx, params: CreateCustomMetricParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {"parameterName": params.parameter_name, "displayName": params.display_name,
            "measurementUnit": params.measurement_unit, "scope": params.scope, "description": params.description}
    out = await ga4.admin_create(ctx, doc, f"properties/{pid}/customMetrics", body)
    if not out.get("ok"):
        return _error(out)
    c = out["data"]
    result = CustomMetricEntity(id=c.get("parameterName", ""), title=c.get("displayName", ""),
                                parameter_name=c.get("parameterName", ""), display_name=c.get("displayName", ""),
                                measurement_unit=c.get("measurementUnit", ""), scope=c.get("scope", ""),
                                description=c.get("description", ""))
    return ActionResult.success(result, summary=f"Created custom metric '{params.display_name}' on property {pid}.")


@chat.function("archive_custom_metric",
               "Archive a custom metric on a GA4 property. Archiving is permanent -- GA4 does not support "
               "un-archiving.",
               action_type="destructive")
async def archive_custom_metric(ctx, params: ArchiveCustomMetricParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_action(ctx, doc, f"properties/{pid}/customMetrics/{params.parameter_name}:archive")
    if not out.get("ok"):
        return _error(out)
    return ActionResult.success({"parameter_name": params.parameter_name},
                                summary=f"Archived custom metric '{params.parameter_name}' on property {pid}.")


@chat.function("create_key_event",
               "Mark an existing GA4 event as a key event (conversion). The event must already be firing on "
               "the property; this only flags it as a conversion, it does not create the event itself.",
               action_type="write", data_model=KeyEventEntity)
async def create_key_event(ctx, params: CreateKeyEventParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {"eventName": params.event_name, "countingMethod": params.counting_method}
    out = await ga4.admin_create(ctx, doc, f"properties/{pid}/keyEvents", body)
    if not out.get("ok"):
        return _error(out)
    k = out["data"]
    result = KeyEventEntity(id=k.get("eventName", ""), title=k.get("eventName", ""), event_name=k.get("eventName", ""),
                            custom=bool(k.get("custom")), counting_method=k.get("countingMethod", ""))
    return ActionResult.success(result, summary=f"'{params.event_name}' is now a key event on property {pid}.")


@chat.function("update_key_event", "Change the counting method of an existing GA4 key event.",
               action_type="write", data_model=KeyEventEntity)
async def update_key_event(ctx, params: UpdateKeyEventParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {"countingMethod": params.counting_method}
    out = await ga4.admin_patch(ctx, doc, f"properties/{pid}/keyEvents/{params.event_name}", body,
                                update_mask="countingMethod")
    if not out.get("ok"):
        return _error(out)
    k = out["data"]
    result = KeyEventEntity(id=k.get("eventName", ""), title=k.get("eventName", ""), event_name=k.get("eventName", ""),
                            custom=bool(k.get("custom")), counting_method=k.get("countingMethod", ""))
    return ActionResult.success(result, summary=f"Updated key event '{params.event_name}' on property {pid}.")


@chat.function("delete_key_event",
               "Unmark a GA4 event as a key event (conversion). The underlying event keeps firing normally -- "
               "only its conversion status is removed.",
               action_type="destructive")
async def delete_key_event(ctx, params: DeleteKeyEventParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_delete(ctx, doc, f"properties/{pid}/keyEvents/{params.event_name}")
    if not out.get("ok"):
        return _error(out)
    return ActionResult.success({"event_name": params.event_name},
                                summary=f"'{params.event_name}' is no longer a key event on property {pid}.")


@chat.function("create_google_ads_link",
               "Link a Google Ads account to a GA4 property, so conversions and audiences can flow between them.",
               action_type="write", data_model=GoogleAdsLinkEntity)
async def create_google_ads_link(ctx, params: CreateGoogleAdsLinkParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {"customerId": params.customer_id, "canManageClients": params.can_manage_clients,
            "adsPersonalizationEnabled": params.ads_personalization_enabled}
    out = await ga4.admin_create(ctx, doc, f"properties/{pid}/googleAdsLinks", body)
    if not out.get("ok"):
        return _error(out)
    link = out["data"]
    result = GoogleAdsLinkEntity(id=str(link.get("name", "")).split("/")[-1], title=link.get("customerId", ""),
                                 customer_id=link.get("customerId", ""), can_manage_clients=bool(link.get("canManageClients")),
                                 ads_personalization_enabled=bool(link.get("adsPersonalizationEnabled")))
    return ActionResult.success(result, summary=f"Linked Google Ads account {params.customer_id} to property {pid}.")


@chat.function("update_google_ads_link", "Change the personalization setting of an existing Google Ads link.",
               action_type="write", data_model=GoogleAdsLinkEntity)
async def update_google_ads_link(ctx, params: UpdateGoogleAdsLinkParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    if params.ads_personalization_enabled is None:
        return ActionResult.error("Nothing to update -- pass ads_personalization_enabled.", code="VALIDATION_FAILED")
    body = {"adsPersonalizationEnabled": params.ads_personalization_enabled}
    out = await ga4.admin_patch(ctx, doc, f"properties/{pid}/googleAdsLinks/{params.link_id}", body,
                                update_mask="adsPersonalizationEnabled")
    if not out.get("ok"):
        return _error(out)
    link = out["data"]
    result = GoogleAdsLinkEntity(id=str(link.get("name", "")).split("/")[-1], title=link.get("customerId", ""),
                                 customer_id=link.get("customerId", ""), can_manage_clients=bool(link.get("canManageClients")),
                                 ads_personalization_enabled=bool(link.get("adsPersonalizationEnabled")))
    return ActionResult.success(result, summary=f"Updated Google Ads link {params.link_id} on property {pid}.")


@chat.function("delete_google_ads_link", "Remove a Google Ads link from a GA4 property.",
               action_type="destructive")
async def delete_google_ads_link(ctx, params: DeleteGoogleAdsLinkParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_delete(ctx, doc, f"properties/{pid}/googleAdsLinks/{params.link_id}")
    if not out.get("ok"):
        return _error(out)
    return ActionResult.success({"link_id": params.link_id},
                                summary=f"Removed Google Ads link {params.link_id} from property {pid}.")


@chat.function("update_property_details",
               "Change a GA4 property's own settings: display name, timezone, currency, or industry category. "
               "Only given fields change.",
               action_type="write", data_model=PropertyDetail)
async def update_property_details(ctx, params: UpdatePropertyDetailsParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body, mask = {}, []
    if params.display_name:
        body["displayName"] = params.display_name
        mask.append("displayName")
    if params.time_zone:
        body["timeZone"] = params.time_zone
        mask.append("timeZone")
    if params.currency_code:
        body["currencyCode"] = params.currency_code
        mask.append("currencyCode")
    if params.industry_category:
        body["industryCategory"] = params.industry_category
        mask.append("industryCategory")
    if not mask:
        return ActionResult.error("Nothing to update -- pass at least one field to change.", code="VALIDATION_FAILED")
    out = await ga4.admin_patch(ctx, doc, f"properties/{pid}", body, update_mask=",".join(mask))
    if not out.get("ok"):
        return _error(out)
    data = out["data"]
    result = PropertyDetail(id=pid, title=data.get("displayName", pid), property_id=pid,
                            display_name=data.get("displayName", ""), time_zone=data.get("timeZone", ""),
                            currency_code=data.get("currencyCode", ""), industry_category=data.get("industryCategory", ""),
                            create_time=data.get("createTime", ""))
    return ActionResult.success(result, summary=f"Updated settings for property {pid}.")


@chat.function("create_data_stream", "Create a new web/Android/iOS data stream on a GA4 property.",
               action_type="write", data_model=DataStreamEntity)
async def create_data_stream(ctx, params: CreateDataStreamParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body = {"displayName": params.display_name, "type": params.stream_type}
    if params.stream_type == "WEB_DATA_STREAM":
        body["webStreamData"] = {"defaultUri": params.default_uri}
    out = await ga4.admin_create(ctx, doc, f"properties/{pid}/dataStreams", body)
    if not out.get("ok"):
        return _error(out)
    s = out["data"]
    web = s.get("webStreamData") or {}
    result = DataStreamEntity(id=str(s.get("name", "")).split("/")[-1], title=s.get("displayName", ""),
                              stream_id=str(s.get("name", "")).split("/")[-1], stream_type=s.get("type", ""),
                              display_name=s.get("displayName", ""), measurement_id=web.get("measurementId", ""),
                              default_uri=web.get("defaultUri", ""))
    return ActionResult.success(result, summary=f"Created data stream '{params.display_name}' on property {pid}.")


@chat.function("update_data_stream", "Rename a data stream or change its default URL (web streams only).",
               action_type="write", data_model=DataStreamEntity)
async def update_data_stream(ctx, params: UpdateDataStreamParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    body, mask = {}, []
    if params.display_name:
        body["displayName"] = params.display_name
        mask.append("displayName")
    if params.default_uri:
        body["webStreamData"] = {"defaultUri": params.default_uri}
        mask.append("webStreamData.defaultUri")
    if not mask:
        return ActionResult.error("Nothing to update -- pass display_name or default_uri.", code="VALIDATION_FAILED")
    out = await ga4.admin_patch(ctx, doc, f"properties/{pid}/dataStreams/{params.stream_id}", body,
                                update_mask=",".join(mask))
    if not out.get("ok"):
        return _error(out)
    s = out["data"]
    web = s.get("webStreamData") or {}
    result = DataStreamEntity(id=params.stream_id, title=s.get("displayName", ""), stream_id=params.stream_id,
                              stream_type=s.get("type", ""), display_name=s.get("displayName", ""),
                              measurement_id=web.get("measurementId", ""), default_uri=web.get("defaultUri", ""))
    return ActionResult.success(result, summary=f"Updated data stream {params.stream_id} on property {pid}.")


@chat.function("delete_data_stream",
               "Permanently delete a data stream from a GA4 property. This stops data collection through it "
               "and cannot be undone.",
               action_type="destructive")
async def delete_data_stream(ctx, params: DeleteDataStreamParams) -> ActionResult:
    doc, pid, err = await _resolve_property(ctx, params.account, params.property_id)
    if err:
        return _error(err)
    out = await ga4.admin_delete(ctx, doc, f"properties/{pid}/dataStreams/{params.stream_id}")
    if not out.get("ok"):
        return _error(out)
    return ActionResult.success({"stream_id": params.stream_id},
                                summary=f"Deleted data stream {params.stream_id} from property {pid}.")
