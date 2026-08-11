"""Offline tests for Part D write/edit functions (no live Google calls)."""

import asyncio
from types import SimpleNamespace

from handlers_admin_write import (archive_custom_dimension, archive_custom_metric, create_custom_dimension,
                                  create_custom_metric, create_data_stream, create_google_ads_link,
                                  create_key_event, delete_data_stream, delete_google_ads_link, delete_key_event,
                                  update_data_stream, update_google_ads_link, update_key_event,
                                  update_property_details)
from models import (ArchiveCustomDimensionParams, ArchiveCustomMetricParams, CreateCustomDimensionParams,
                    CreateCustomMetricParams, CreateDataStreamParams, CreateGoogleAdsLinkParams,
                    CreateKeyEventParams, DeleteDataStreamParams, DeleteGoogleAdsLinkParams, DeleteKeyEventParams,
                    UpdateDataStreamParams, UpdateGoogleAdsLinkParams, UpdateKeyEventParams,
                    UpdatePropertyDetailsParams)


def _account_doc():
    return SimpleNamespace(id="acc1", data={"email": "user@example.com", "is_active": True})


class _FakeStore:
    def __init__(self, docs, selection=None):
        self._docs = {doc.id: doc for doc in docs}
        self._selection = selection or []

    async def query(self, collection, where=None, limit=100):
        if collection == "google_analytics_selections":
            return SimpleNamespace(data=self._selection[:limit])
        docs = list(self._docs.values())
        if where:
            docs = [d for d in docs if all((d.data or {}).get(k) == v for k, v in where.items())]
        return SimpleNamespace(data=docs[:limit])


def _ctx(property_id="123456"):
    doc = _account_doc()
    selection = [SimpleNamespace(id="s1", data={"email": "user@example.com", "property_id": property_id})]
    return SimpleNamespace(store=_FakeStore([doc], selection))


def _patch_create(monkeypatch, data):
    import handlers_admin_write

    async def fake_create(ctx, doc, path, body, *, query=None):
        return {"ok": True, "data": data}

    monkeypatch.setattr(handlers_admin_write.ga4, "admin_create", fake_create)


def _patch_patch(monkeypatch, data):
    import handlers_admin_write

    async def fake_patch(ctx, doc, path, body, *, update_mask=""):
        return {"ok": True, "data": data}

    monkeypatch.setattr(handlers_admin_write.ga4, "admin_patch", fake_patch)


def _patch_delete(monkeypatch):
    import handlers_admin_write

    async def fake_delete(ctx, doc, path):
        return {"ok": True, "data": {}}

    monkeypatch.setattr(handlers_admin_write.ga4, "admin_delete", fake_delete)


def _patch_action(monkeypatch):
    import handlers_admin_write

    async def fake_action(ctx, doc, path, body=None):
        return {"ok": True, "data": {}}

    monkeypatch.setattr(handlers_admin_write.ga4, "admin_action", fake_action)


def test_create_custom_dimension(monkeypatch):
    _patch_create(monkeypatch, {"parameterName": "plan_tier", "displayName": "Plan tier", "scope": "USER"})
    ctx = _ctx()
    result = asyncio.run(create_custom_dimension(
        ctx, CreateCustomDimensionParams(parameter_name="plan_tier", display_name="Plan tier", scope="USER")))
    assert result.status == "success"
    assert result.data.parameter_name == "plan_tier"


def test_archive_custom_dimension(monkeypatch):
    _patch_action(monkeypatch)
    ctx = _ctx()
    result = asyncio.run(archive_custom_dimension(ctx, ArchiveCustomDimensionParams(parameter_name="plan_tier")))
    assert result.status == "success"


def test_create_custom_metric(monkeypatch):
    _patch_create(monkeypatch, {"parameterName": "cart_value", "displayName": "Cart value",
                                "measurementUnit": "CURRENCY", "scope": "EVENT"})
    ctx = _ctx()
    result = asyncio.run(create_custom_metric(
        ctx, CreateCustomMetricParams(parameter_name="cart_value", display_name="Cart value",
                                      measurement_unit="CURRENCY")))
    assert result.status == "success"
    assert result.data.measurement_unit == "CURRENCY"


def test_archive_custom_metric(monkeypatch):
    _patch_action(monkeypatch)
    ctx = _ctx()
    result = asyncio.run(archive_custom_metric(ctx, ArchiveCustomMetricParams(parameter_name="cart_value")))
    assert result.status == "success"


def test_create_key_event(monkeypatch):
    _patch_create(monkeypatch, {"eventName": "purchase", "custom": False, "countingMethod": "ONCE_PER_EVENT"})
    ctx = _ctx()
    result = asyncio.run(create_key_event(ctx, CreateKeyEventParams(event_name="purchase")))
    assert result.status == "success"
    assert result.data.event_name == "purchase"


def test_update_key_event(monkeypatch):
    _patch_patch(monkeypatch, {"eventName": "purchase", "custom": False, "countingMethod": "ONCE_PER_SESSION"})
    ctx = _ctx()
    result = asyncio.run(update_key_event(
        ctx, UpdateKeyEventParams(event_name="purchase", counting_method="ONCE_PER_SESSION")))
    assert result.status == "success"
    assert result.data.counting_method == "ONCE_PER_SESSION"


def test_delete_key_event(monkeypatch):
    _patch_delete(monkeypatch)
    ctx = _ctx()
    result = asyncio.run(delete_key_event(ctx, DeleteKeyEventParams(event_name="purchase")))
    assert result.status == "success"


def test_create_google_ads_link(monkeypatch):
    _patch_create(monkeypatch, {"name": "properties/222/googleAdsLinks/444", "customerId": "123-456-7890",
                                "canManageClients": True, "adsPersonalizationEnabled": False})
    ctx = _ctx()
    result = asyncio.run(create_google_ads_link(ctx, CreateGoogleAdsLinkParams(customer_id="123-456-7890")))
    assert result.status == "success"
    assert result.data.customer_id == "123-456-7890"


def test_update_google_ads_link_requires_a_field(monkeypatch):
    ctx = _ctx()
    result = asyncio.run(update_google_ads_link(ctx, UpdateGoogleAdsLinkParams(link_id="444")))
    assert result.status == "error"
    assert result.error_code == "VALIDATION_FAILED"


def test_update_google_ads_link(monkeypatch):
    _patch_patch(monkeypatch, {"name": "properties/222/googleAdsLinks/444", "customerId": "123-456-7890",
                               "canManageClients": True, "adsPersonalizationEnabled": True})
    ctx = _ctx()
    result = asyncio.run(update_google_ads_link(
        ctx, UpdateGoogleAdsLinkParams(link_id="444", ads_personalization_enabled=True)))
    assert result.status == "success"
    assert result.data.ads_personalization_enabled is True


def test_delete_google_ads_link(monkeypatch):
    _patch_delete(monkeypatch)
    ctx = _ctx()
    result = asyncio.run(delete_google_ads_link(ctx, DeleteGoogleAdsLinkParams(link_id="444")))
    assert result.status == "success"


def test_update_property_details_requires_a_field(monkeypatch):
    ctx = _ctx()
    result = asyncio.run(update_property_details(ctx, UpdatePropertyDetailsParams()))
    assert result.status == "error"
    assert result.error_code == "VALIDATION_FAILED"


def test_update_property_details(monkeypatch):
    _patch_patch(monkeypatch, {"displayName": "New name", "timeZone": "America/Los_Angeles",
                               "currencyCode": "USD", "industryCategory": "RETAIL"})
    ctx = _ctx()
    result = asyncio.run(update_property_details(ctx, UpdatePropertyDetailsParams(display_name="New name")))
    assert result.status == "success"
    assert result.data.display_name == "New name"


def test_create_data_stream(monkeypatch):
    _patch_create(monkeypatch, {"name": "properties/222/dataStreams/333", "displayName": "Web stream",
                                "type": "WEB_DATA_STREAM",
                                "webStreamData": {"measurementId": "G-ABC123", "defaultUri": "https://example.com"}})
    ctx = _ctx()
    result = asyncio.run(create_data_stream(
        ctx, CreateDataStreamParams(display_name="Web stream", default_uri="https://example.com")))
    assert result.status == "success"
    assert result.data.measurement_id == "G-ABC123"


def test_update_data_stream_requires_a_field(monkeypatch):
    ctx = _ctx()
    result = asyncio.run(update_data_stream(ctx, UpdateDataStreamParams(stream_id="333")))
    assert result.status == "error"
    assert result.error_code == "VALIDATION_FAILED"


def test_update_data_stream(monkeypatch):
    _patch_patch(monkeypatch, {"displayName": "Renamed stream", "type": "WEB_DATA_STREAM",
                               "webStreamData": {"measurementId": "G-ABC123", "defaultUri": "https://example.com"}})
    ctx = _ctx()
    result = asyncio.run(update_data_stream(ctx, UpdateDataStreamParams(stream_id="333", display_name="Renamed stream")))
    assert result.status == "success"
    assert result.data.display_name == "Renamed stream"


def test_delete_data_stream(monkeypatch):
    _patch_delete(monkeypatch)
    ctx = _ctx()
    result = asyncio.run(delete_data_stream(ctx, DeleteDataStreamParams(stream_id="333")))
    assert result.status == "success"


def test_write_error_is_surfaced(monkeypatch):
    import handlers_admin_write

    async def fake_create_error(ctx, doc, path, body, *, query=None):
        return {"ok": False, "error": "Editor role required", "code": "PERMISSION_DENIED"}

    monkeypatch.setattr(handlers_admin_write.ga4, "admin_create", fake_create_error)
    ctx = _ctx()
    result = asyncio.run(create_key_event(ctx, CreateKeyEventParams(event_name="purchase")))
    assert result.status == "error"
    assert result.error_code == "PERMISSION_DENIED"
