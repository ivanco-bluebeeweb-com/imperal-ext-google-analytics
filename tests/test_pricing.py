"""Per-tool prices for the Google Analytics extension.

WHY THIS EXISTS. Google's own GA4 Data API and Admin API are free of direct
per-call Google Cloud billing -- Google meters usage in request-quota units,
not money. So this price table is NOT a pass-through of a Google Cloud bill;
it prices OUR OWN engineering work, support burden, and liability per call,
so the extension can carry a margin instead of running at zero revenue while
every other Imperal extension (Mail, Media Hub, WordPress Hub, ...) charges
for its own calls.

Same discipline as Media Studio's tests/test_pricing.py and Slack Connector's
tests/test_pricing.py -- this repo's own prior art for what a price-list test
suite looks like.
"""

import json
import pathlib

MANIFEST = pathlib.Path(__file__).resolve().parent.parent / "imperal.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _pricing() -> dict:
    pricing = _manifest().get("pricing")
    assert pricing, "manifest has no pricing block"
    return pricing


def test_every_tool_has_a_price_and_no_price_is_orphaned():
    """THE INVARIANT THAT SURVIVES THE NEXT FEATURE.

    Checked in both directions. A missing price means a new tool ships
    unpriced (billed by accident, or not at all). An orphaned price means
    the table still mentions a tool that no longer exists.
    """
    tools = {t["name"] for t in _manifest()["tools"]}
    priced = set(_pricing()["tool_prices"])

    missing = tools - priced
    orphaned = priced - tools

    assert not missing, f"tools with no price: {sorted(missing)}"
    assert not orphaned, f"prices for tools that don't exist: {sorted(orphaned)}"


def test_onboarding_and_account_plumbing_stay_free():
    """Connecting, switching, and diagnosing account access must never gate
    a user out of getting started, so these stay at 0 regardless of any
    future re-tiering elsewhere in the table."""
    free_required = {
        "connect_google_analytics",
        "disconnect_google_account",
        "list_connected_accounts",
        "switch_account",
        "select_property",
        "check_account_access",
        "list_ga_accounts",
    }
    prices = _pricing()["tool_prices"]
    for name in free_required:
        assert prices[name] == 0, f"{name} must stay free (onboarding/account plumbing)"


def test_live_property_mutations_cost_more_than_a_plain_read():
    """Any tool that actually writes to the user's live GA4 property
    (custom dimensions/metrics, key events, Google Ads links, data streams)
    carries real liability and Google's edit-scope review requirements, so
    it must be priced strictly above a same-shaped read-only report call."""
    prices = _pricing()["tool_prices"]
    read_baseline = prices["get_overview"]

    mutating_tools = [
        "create_custom_dimension", "archive_custom_dimension",
        "create_custom_metric", "archive_custom_metric",
        "create_key_event", "delete_key_event",
        "create_google_ads_link", "delete_google_ads_link",
        "create_data_stream", "delete_data_stream",
    ]
    for name in mutating_tools:
        assert prices[name] > read_baseline, (
            f"{name} (writes to the live GA4 property) must cost more than "
            f"a plain report read ({read_baseline})"
        )


def test_heaviest_multi_call_reports_cost_the_most():
    """batch_run_reports (up to 5 reports in one call) and export_report_csv
    (report plus file assembly) do the most work per call and must sit at
    the top of the scale."""
    prices = _pricing()["tool_prices"]
    heaviest = {"batch_run_reports", "export_report_csv"}
    ceiling = max(prices.values())
    for name in heaviest:
        assert prices[name] == ceiling, f"{name} must be priced at the table's ceiling ({ceiling})"


def test_pricing_notes_do_not_claim_a_pass_through_google_bill():
    """Google does not charge per GA4 API call -- it meters request-quota
    units, not money. The notes must stay honest about that, so nobody
    later 'corrects' the price table to chase a Google Cloud bill that
    does not exist for this API."""
    notes = _pricing().get("notes", "")
    assert "free of direct per-call" in notes or "NOT a pass-through" in notes
