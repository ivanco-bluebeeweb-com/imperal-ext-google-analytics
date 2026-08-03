from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text()


def test_oauth_uses_identity_and_ga4_read_only_scopes():
    source = _source("app.py")
    for scope in ('"openid"', '"email"', '"profile"', "analytics.readonly"):
        assert scope in source


def test_mvp_has_no_google_analytics_mutation_calls():
    source = "\n".join(path.read_text() for path in ROOT.glob("*.py"))
    forbidden = ["ctx.http.put(", "ctx.http.patch(", "ctx.http.delete(", "analytics.edit"]
    assert [item for item in forbidden if item in source] == []


def test_connect_and_mvp_screen_sketches_exist():
    sketch = (ROOT / "design" / "component-sketches.md").read_text().lower()
    for title in ("connect google analytics", "overview", "explore", "realtime", "properties (picker)",
                  "settings", "alerts"):
        assert title in sketch


def test_readme_states_current_read_only_api_boundary():
    readme = _source("README.md")
    assert "Google Analytics Admin and Data APIs" in readme
    assert "does not change GA4 settings" in readme
