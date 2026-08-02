from ga4_client import _error, rows


def test_properties_error_mapping_is_safe_and_specific():
    assert _error(401, {})["code"] == "TOKEN_REJECTED"
    assert _error(403, {"error": {"message": "Permission denied"}})["code"] == "PERMISSION_DENIED"
    assert _error(429, {})["code"] == "RATE_LIMITED"


def test_quota_error_is_rate_limited():
    out = _error(403, {"error": {"message": "Quota exceeded"}})
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
    assert rows(report) == [{
        "sessionDefaultChannelGroup": "Organic Search",
        "sessions": "12",
        "activeUsers": "9",
    }]
