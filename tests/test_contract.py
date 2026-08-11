from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text()


def test_oauth_uses_identity_and_ga4_scopes():
    source = _source("app.py")
    for scope in ('"openid"', '"email"', '"profile"', "analytics.readonly", "analytics.edit"):
        assert scope in source


def test_parts_abc_have_no_google_analytics_mutation_calls():
    """Parts A (reports), B (structure), C (alerts) must stay read-only.

    Only Part D (handlers_admin_write.py) is allowed to write to Google --
    that boundary is explicit and deliberate, not accidental.
    """
    read_only_files = ["handlers.py", "handlers_accounts.py", "handlers_admin.py", "handlers_alerts.py",
                       "handlers_reports.py", "ga4_client.py"]
    source = "\n".join((ROOT / name).read_text() for name in read_only_files)
    forbidden = ["ctx.http.put(", "ctx.http.patch(", "ctx.http.delete("]
    assert [item for item in forbidden if item in source] == []


def test_part_d_write_functions_are_isolated_in_their_own_module():
    """Every write/destructive Admin API call lives in handlers_admin_write.py, not scattered elsewhere."""
    write_source = _source("handlers_admin_write.py")
    assert "admin_create(" in write_source or "admin_patch(" in write_source or "admin_delete(" in write_source
    for name in ["handlers.py", "handlers_accounts.py", "handlers_admin.py", "handlers_alerts.py",
                "handlers_reports.py"]:
        other_source = _source(name)
        assert "admin_create(" not in other_source
        assert "admin_patch(" not in other_source
        assert "admin_delete(" not in other_source


def test_connect_and_mvp_screen_sketches_exist():
    sketch = (ROOT / "design" / "component-sketches.md").read_text().lower()
    for title in ("connect google analytics", "overview", "explore", "realtime", "properties (picker)",
                  "settings", "alerts"):
        assert title in sketch


def test_readme_states_current_api_boundary():
    readme = _source("README.md")
    assert "Google Analytics Admin and Data APIs" in readme
    assert "Part D" in readme
