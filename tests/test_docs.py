"""The auto-generated documentation pages and the OpenAPI schema."""

from app import __version__


def test_docs_page_is_served_in_the_dark_theme(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<html class="dark-mode">' in response.text
    assert "swagger-ui" in response.text
    assert "/openapi.json" in response.text


def test_redoc_page_is_served(client):
    assert client.get("/redoc").status_code == 200


def test_docs_and_schema_need_no_token(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200


def test_openapi_schema_lists_every_endpoint(client):
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "Expense Tracker API"
    assert schema["info"]["version"] == __version__
    operations = sorted(
        f"{method.upper()} {path}" for path, methods in schema["paths"].items() for method in methods
    )
    assert operations == sorted(
        [
            "GET /health",
            "POST /auth/register",
            "POST /auth/login",
            "GET /auth/me",
            "GET /categories",
            "POST /categories",
            "GET /categories/{category_id}",
            "PATCH /categories/{category_id}",
            "DELETE /categories/{category_id}",
            "POST /expenses",
            "GET /expenses",
            "GET /expenses/export",
            "GET /expenses/{expense_id}",
            "PATCH /expenses/{expense_id}",
            "DELETE /expenses/{expense_id}",
            "POST /budgets",
            "GET /budgets",
            "GET /budgets/status",
            "GET /budgets/{budget_id}",
            "PATCH /budgets/{budget_id}",
            "DELETE /budgets/{budget_id}",
            "GET /summary/monthly",
            "GET /summary/categories",
            "GET /summary/trends",
        ]
    )


def test_openapi_documents_the_real_error_format(client):
    """The 422 in the schema must be this API's error body, not FastAPI's default one."""
    schema = client.get("/openapi.json").json()

    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            for status, response in operation["responses"].items():
                if not status.startswith(("4", "5")):
                    continue
                reference = response["content"]["application/json"]["schema"]["$ref"]
                assert reference.endswith("/ErrorResponse"), f"{method} {path} {status}: {reference}"
    assert "HTTPValidationError" not in schema["components"]["schemas"]


def test_openapi_declares_the_bearer_login(client):
    schema = client.get("/openapi.json").json()

    flows = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]
    assert flows["password"]["tokenUrl"] == "/auth/login"
    assert "security" in schema["paths"]["/expenses"]["get"]
    assert "security" not in schema["paths"]["/health"]["get"]
