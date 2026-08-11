"""Cross-account property selection for the global GA4 sidebar dropdown."""

import asyncio
from types import SimpleNamespace

import ga4_client as ga4
import handlers
from models import SelectPropertyParams


class _Page:
    def __init__(self, data):
        self.data = data


class _Store:
    def __init__(self, accounts, selections=()):
        self.accounts = {doc.id: doc for doc in accounts}
        self.selections = {doc.id: doc for doc in selections}

    async def query(self, collection, where=None, limit=100):
        docs = list(self.accounts.values()) if collection == ga4.ACCOUNTS_COLLECTION else list(self.selections.values())
        if where:
            docs = [doc for doc in docs if all((doc.data or {}).get(key) == value for key, value in where.items())]
        return _Page(docs[:limit])

    async def update(self, collection, doc_id, data):
        target = self.accounts if collection == ga4.ACCOUNTS_COLLECTION else self.selections
        target[doc_id] = SimpleNamespace(id=doc_id, data=data)

    async def create(self, collection, data):
        assert collection == handlers.SELECTIONS
        doc_id = f"selection-{len(self.selections) + 1}"
        self.selections[doc_id] = SimpleNamespace(id=doc_id, data=data)
        return self.selections[doc_id]


class _Ctx:
    def __init__(self, accounts, selections=()):
        self.store = _Store(accounts, selections)


def _doc(doc_id, **data):
    return SimpleNamespace(id=doc_id, data=data)


def test_account_for_property_finds_owner_across_connected_accounts(monkeypatch):
    accounts = [_doc("one", email="one@example.com"), _doc("two", email="two@example.com")]
    ctx = _Ctx(accounts)

    async def fake_properties(ctx, account):
        return {"ok": True, "properties": [{"property_id": "111" if account.id == "one" else "222"}]}

    monkeypatch.setattr(ga4, "properties", fake_properties)
    found = asyncio.run(ga4.account_for_property(ctx, "222"))
    assert found.id == "two"


def test_global_select_property_persists_owning_account_and_marks_it_current(monkeypatch):
    accounts = [_doc("one", email="one@example.com"), _doc("two", email="two@example.com")]
    old = _doc("old", email="one@example.com", property_id="111", is_current=True)
    ctx = _Ctx(accounts, [old])

    async def fake_properties(ctx, account):
        return {"ok": True, "properties": [{"property_id": "111" if account.id == "one" else "222"}]}

    monkeypatch.setattr(ga4, "properties", fake_properties)
    result = asyncio.run(handlers.select_property(ctx, SelectPropertyParams(account="", property_id="222")))

    assert result.summary == "GA4 property selected."
    selection = asyncio.run(ga4.global_selected_property(ctx))
    assert selection == {"property_id": "222", "email": "two@example.com"}
    assert ctx.store.selections["old"].data["is_current"] is False
