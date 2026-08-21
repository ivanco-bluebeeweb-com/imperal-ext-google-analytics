"""Offline tests for ga4_client: error mapping, row shaping, and the
refresh-on-401 / proactive-refresh auth retry logic (no live Google calls).

Mirrors the QueueHTTP/MockContext-style doubles used by Google Drive
Connector and YouTube Studio Hub's own client tests.
"""

import time

import pytest

import ga4_client


# --------------------------------------------------------------------------
# Existing coverage: error mapping and row shaping
# --------------------------------------------------------------------------

def test_properties_error_mapping_is_safe_and_specific():
    assert ga4_client._error(401, {})["code"] == "TOKEN_REJECTED"
    assert ga4_client._error(403, {"error": {"message": "Permission denied"}})["code"] == "PERMISSION_DENIED"
    assert ga4_client._error(429, {})["code"] == "RATE_LIMITED"


def test_quota_error_is_rate_limited():
    out = ga4_client._error(403, {"error": {"message": "Quota exceeded"}})
    assert out["code"] == "RATE_LIMITED"
    assert out["retryable"] is True


def test_run_report_rows_are_mapped_by_header_name():
    report = {
        "dimensionHeaders": [{"name": "sessionDefaultChannelGroup"}],
        "metricHeaders": [{"name": "sessions"}, {"name": "activeUsers"}],
        "rows": [{
            "dimensionValues": [{"value": "Organic Search"}],
            "metricValues": [{"value": "12"}, {"value": "9"}],
        }],
    }
    assert ga4_client.rows(report) == [{
        "sessionDefaultChannelGroup": "Organic Search",
        "sessions": "12",
        "activeUsers": "9",
    }]


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------

class _Response:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body

    def json(self):
        return self.body


class _Http:
    """Queued HTTP double: GET calls are answered from `queue`, in order.
    POST calls (token refreshes) are answered from `token_response`."""

    def __init__(self, queue, token_response=None):
        self.queue = list(queue)
        self.token_response = token_response or _Response(200, {"access_token": "fresh", "expires_in": 3600})
        self.token_calls = []
        self.bearers = []

    async def get(self, url, headers=None, **kwargs):
        self.bearers.append((headers or {}).get("Authorization", "").removeprefix("Bearer "))
        assert self.queue, f"Unexpected GET {url}"
        return self.queue.pop(0)

    async def post(self, url, **kwargs):
        if url == ga4_client.TOKEN_URL:
            self.token_calls.append(kwargs)
            return self.token_response
        assert self.queue, f"Unexpected POST {url}"
        return self.queue.pop(0)


class _Secrets:
    async def get(self, name):
        return {"google_client_id": "cid", "google_client_secret": "csecret"}.get(name)


class _Store:
    async def update(self, collection, doc_id, data):
        return None


class _Ctx:
    def __init__(self, http):
        self.http = http
        self.secrets = _Secrets()
        self.store = _Store()


class _Doc:
    def __init__(self, data):
        self.id = "acc1"
        self.data = data


def _expired_account(expires_at=None, access_token="believed-good"):
    return {
        "email": "a@example.com",
        "access_token": access_token,
        "refresh_token": "refresh-me",
        "expires_at": expires_at if expires_at is not None else int(time.time()) - 10,
    }


# --------------------------------------------------------------------------
# Proactive refresh: an expired-by-clock token is refreshed before use
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_token_is_refreshed_before_the_call():
    http = _Http([_Response(200, {})])
    ctx = _Ctx(http)
    doc = _Doc(_expired_account())

    out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

    assert out["ok"] is True
    assert http.bearers == ["fresh"]
    assert len(http.token_calls) == 1


# --------------------------------------------------------------------------
# Reactive refresh: a 401 despite a believed-good token triggers exactly one retry
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_401_triggers_exactly_one_refresh_and_retry():
    http = _Http([_Response(401, {}), _Response(200, {})])
    ctx = _Ctx(http)
    doc = _Doc(_expired_account(expires_at=int(time.time()) + 3600))

    out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

    assert out["ok"] is True
    assert http.bearers == ["believed-good", "fresh"]
    assert len(http.token_calls) == 1


@pytest.mark.asyncio
async def test_second_401_is_reported_not_retried_forever():
    """If it still 401s after a genuine refresh, that IS a reconnect."""
    http = _Http([_Response(401, {}), _Response(401, {})])
    ctx = _Ctx(http)
    doc = _Doc(_expired_account(expires_at=int(time.time()) + 3600))

    out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

    assert out["ok"] is False
    assert out["code"] == "TOKEN_REJECTED"
    assert len(http.token_calls) == 1, "exactly one retry, never a loop"


# --------------------------------------------------------------------------
# Genuine reconnects must still be reported (and be actionable)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revoked_grant_reports_a_reconnect_with_a_reason():
    """invalid_grant = the user revoked access. Reconnect is the honest answer."""
    http = _Http([], token_response=_Response(400, {"error": "invalid_grant"}))
    ctx = _Ctx(http)
    doc = _Doc(_expired_account())

    out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

    assert out["ok"] is False
    assert out["code"] == "TOKEN_REJECTED"
    assert out["error"], "the reason must reach the user, not a blanket message"


@pytest.mark.asyncio
async def test_account_without_any_token_is_rejected_up_front():
    http = _Http([])
    ctx = _Ctx(http)
    doc = _Doc({"email": "a@example.com"})

    out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

    assert out == ga4_client.fail("TOKEN_REJECTED")
    assert not http.token_calls


@pytest.mark.asyncio
async def test_account_with_only_a_refresh_token_still_recovers():
    """A doc whose access_token was cleared must refresh, not dead-end."""
    http = _Http([_Response(200, {})])
    ctx = _Ctx(http)
    doc = _Doc({"email": "a@example.com", "refresh_token": "refresh-me"})

    out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

    assert out["ok"] is True
    assert http.bearers == ["fresh"]


# --------------------------------------------------------------------------
# Unrelated behaviour must be untouched
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_auth_errors_keep_their_specific_mapping():
    """403/429/400 must not be swallowed by the new auth path."""
    for status, expected in ((403, "PERMISSION_DENIED"), (429, "RATE_LIMITED"),
                             (400, "VALIDATION_FAILED")):
        http = _Http([_Response(status, {"error": {"message": "nope"}})])
        ctx = _Ctx(http)
        doc = _Doc(_expired_account(expires_at=int(time.time()) + 3600))

        out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

        assert out["ok"] is False
        assert out["code"] == expected, f"HTTP {status} must map to {expected}"


@pytest.mark.asyncio
async def test_network_failure_is_unreachable_not_a_reconnect():
    class _Dead(_Http):
        async def get(self, url: str, **kwargs):
            raise OSError("connection reset")

    ctx = _Ctx(_Dead([]))
    doc = _Doc(_expired_account(expires_at=int(time.time()) + 3600))

    out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

    assert out["code"] == "UNREACHABLE", "a network blip must not ask for a reconnect"


@pytest.mark.asyncio
async def test_valid_token_is_used_as_is_without_a_refresh_roundtrip():
    http = _Http([_Response(200, {})])
    ctx = _Ctx(http)
    doc = _Doc(_expired_account(expires_at=int(time.time()) + 3600, access_token="good"))

    out = await ga4_client.request(ctx, doc, "get", f"{ga4_client.ADMIN_API}/x")

    assert out["ok"] is True
    assert http.token_calls == [], "a healthy token must not cost a refresh call"
    assert http.bearers == ["good"]
