"""The web app is static files served by the API. Its behaviour in a browser
is not tested here; these tests cover that it is served, and served safely."""

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_web_app_is_served_at_the_root(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Expense Tracker</title>" in response.text


def test_web_app_needs_no_token_to_load(client):
    # The page is public. The data it shows comes from the API, which is not.
    assert client.get("/").status_code == 200
    assert client.get("/expenses").status_code == 401


def test_web_app_has_a_content_security_policy(client):
    policy = client.get("/").headers["content-security-policy"]

    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/static/app.js", "javascript"),
        ("/static/app.css", "text/css"),
        ("/static/favicon.svg", "image/svg+xml"),
    ],
)
def test_static_files_are_served(client, path, content_type):
    response = client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]


def test_missing_static_file_uses_the_json_error_format(client):
    response = client.get("/static/nope.js")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_static_folder_cannot_be_escaped(client):
    for path in ("/static/../config.py", "/static/%2e%2e/config.py", "/static/..%2fconfig.py"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert "JWT_SECRET" not in response.text


def test_page_loads_everything_from_this_server():
    """No CDN: the page must work offline and satisfy its own policy."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    sources = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert sources, "expected the page to reference its script and styles"
    assert all(source.startswith("/static/") for source in sources), sources


def test_page_has_no_inline_script_or_event_handlers():
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    assert re.findall(r"<script(?![^>]*\bsrc=)", html) == []
    assert re.findall(r"\son[a-z]+\s*=", html) == []
    assert "style=" not in html


def test_script_never_builds_html_from_strings():
    """User text (notes, category names) must reach the page as text only."""
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", script, flags=re.DOTALL)
    code = "\n".join(line for line in code.splitlines() if not line.strip().startswith("//"))

    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in code, forbidden


def test_web_app_is_not_in_the_api_schema(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/" not in paths
    assert not any(path.startswith("/static") for path in paths)
