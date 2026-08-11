"""Offline tests for Part B Admin API structure functions (no live Google calls)."""

import asyncio
from types import SimpleNamespace

from handlers_admin import (get_account_summary, get_data_stream_details, get_property_details, list_custom_dimensions,
                            list_custom_metrics, list_data_streams, list_ga_accounts, list_google_ads_links,
                            list_key_events)
from models import AccountParam, DataStreamDetailParams, PropertyDetailParams


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


def _patch_admin_list(monkeypatch, items, item_key="items"):
    import handlers_admin

    async def fake_list(ctx, doc, path, *, item_key=None, params=None):
        return {"ok": True, "items": items}

    monkeypatch.setattr(handlers_admin.ga4, "admin_list", fake_list)


def _patch_admin_get(monkeypatch, data):
    import handlers_admin

    async def fake_get(ctx, doc, path):
        return {"ok": True, "data": data}

    monkeypatch.setattr(handlers_admin.ga4, "admin_get", fake_get)


def test_list_ga_accounts_maps_names(monkeypatch):
    _patch_admin_list(monkeypatch, [{"name": "accounts/111", "displayName": "Acme Inc"}])
    ctx = _ctx()
    result = asyncio.run(list_ga_accounts(ctx, AccountParam()))
    assert result.status == "success"
    assert result.data.items[0].account_id == "111"
    assert result.data.items[0].display_name == "Acme Inc"


def test_get_account_summary_nests_properties(monkeypatch):
    _patch_admin_list(monkeypatch, [{
        "account": "accounts/111", "displayName": "Acme Inc",
        "propertySummaries": [{"property": "properties/222", "displayName": "Acme Site"}],
    }])
    ctx = _ctx()
    result = asyncio.run(get_account_summary(ctx, AccountParam()))
    assert result.status == "success"
    summary = result.data.items[0]
    assert summary.account_id == "111"
    assert summary.properties[0].property_id == "222"


def test_get_property_details_maps_fields(monkeypatch):
    _patch_admin_get(monkeypatch, {
        "displayName": "Acme Site", "timeZone": "America/Los_Angeles", "currencyCode": "USD",
        "industryCategory": "RETAIL", "createTime": "2024-01-01T00:00:00Z",
    })
    ctx = _ctx()
    result = asyncio.run(get_property_details(ctx, PropertyDetailParams()))
    assert result.status == "success"
    assert result.data.time_zone == "America/Los_Angeles"
    assert result.data.currency_code == "USD"


def test_list_data_streams_extracts_measurement_id(monkeypatch):
    _patch_admin_list(monkeypatch, [{
        "name": "properties/222/dataStreams/333", "displayName": "Web stream", "type": "WEB_DATA_STREAM",
        "webStreamData": {"measurementId": "G-ABC123", "defaultUri": "https://example.com"},
    }])
    ctx = _ctx()
    result = asyncio.run(list_data_streams(ctx, PropertyDetailParams()))
    assert result.status == "success"
    assert result.data.items[0].stream_id == "333"
    assert result.data.items[0].measurement_id == "G-ABC123"


def test_get_data_stream_details(monkeypatch):
    _patch_admin_get(monkeypatch, {
        "displayName": "Web stream", "type": "WEB_DATA_STREAM",
        "webStreamData": {"measurementId": "G-ABC123", "defaultUri": "https://example.com"},
    })
    ctx = _ctx()
    result = asyncio.run(get_data_stream_details(ctx, DataStreamDetailParams(stream_id="333")))
    assert result.status == "success"
    assert result.data.measurement_id == "G-ABC123"


def test_list_custom_dimensions(monkeypatch):
    _patch_admin_list(monkeypatch, [{
        "parameterName": "plan_tier", "displayName": "Plan tier", "scope": "USER", "description": "Subscription tier",
    }])
    ctx = _ctx()
    result = asyncio.run(list_custom_dimensions(ctx, PropertyDetailParams()))
    assert result.status == "success"
    assert result.data.items[0].parameter_name == "plan_tier"
    assert result.data.items[0].scope == "USER"


def test_list_custom_metrics(monkeypatch):
    _patch_admin_list(monkeypatch, [{
        "parameterName": "cart_value", "displayName": "Cart value", "measurementUnit": "CURRENCY", "scope": "EVENT",
    }])
    ctx = _ctx()
    result = asyncio.run(list_custom_metrics(ctx, PropertyDetailParams()))
    assert result.status == "success"
    assert result.data.items[0].measurement_unit == "CURRENCY"


def test_list_key_events(monkeypatch):
    _patch_admin_list(monkeypatch, [{"eventName": "purchase", "custom": False, "countingMethod": "ONCE_PER_EVENT"}])
    ctx = _ctx()
    result = asyncio.run(list_key_events(ctx, PropertyDetailParams()))
    assert result.status == "success"
    assert result.data.items[0].event_name == "purchase"
    assert result.data.items[0].custom is False


def test_list_google_ads_links(monkeypatch):
    _patch_admin_list(monkeypatch, [{
        "name": "properties/222/googleAdsLinks/444", "customerId": "123-456-7890",
        "canManageClients": True, "adsPersonalizationEnabled": False,
    }])
    ctx = _ctx()
    result = asyncio.run(list_google_ads_links(ctx, PropertyDetailParams()))
    assert result.status == "success"
    assert result.data.items[0].customer_id == "123-456-7890"
    assert result.data.items[0].can_manage_clients is True


def test_property_details_no_property_selected():
    ctx = SimpleNamespace(store=_FakeStore([_account_doc()], selection=[]))
    result = asyncio.run(get_property_details(ctx, PropertyDetailParams()))
    assert result.status == "error"
    assert result.error_code == "VALIDATION_FAILED"


def test_admin_error_is_surfaced(monkeypatch):
    import handlers_admin

    async def fake_list_error(ctx, doc, path, *, item_key=None, params=None):
        return {"ok": False, "error": "denied", "code": "PERMISSION_DENIED"}

    monkeypatch.setattr(handlers_admin.ga4, "admin_list", fake_list_error)
    ctx = _ctx()
    result = asyncio.run(list_ga_accounts(ctx, AccountParam()))
    assert result.status == "error"
    assert result.error_code == "PERMISSION_DENIED"
