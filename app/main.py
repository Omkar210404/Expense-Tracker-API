"""Application factory. Run with `uvicorn app.main:app`."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect

from app import __version__
from app.config import Settings, get_settings
from app.database import make_engine, make_session_factory
from app.errors import register_error_handlers
from app.routers import auth, budgets, categories, expenses, health, summary

DESCRIPTION = """
Personal expense tracking with user accounts.

Register, log in, then use the **Authorize** button with your email and password.
Every user sees and changes only their own data.

The web app that uses this API is at [/](/).
"""

STATIC_DIR = Path(__file__).parent / "static"

# The web app loads its script and styles from this server only and has no
# inline script, so injected markup has nothing to run.
WEB_APP_CSP = "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The app never creates tables itself. Say so clearly instead of failing
    # on the first request with "no such table".
    if not inspect(app.state.engine).has_table("users"):
        raise RuntimeError("The database has no tables yet. Run: alembic upgrade head")
    yield
    app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)

    app = FastAPI(
        title="Expense Tracker API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url=None,  # served by swagger_ui() below
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/docs", include_in_schema=False)
    def swagger_ui() -> HTMLResponse:
        page = get_swagger_ui_html(openapi_url=app.openapi_url, title=f"{app.title} - Swagger UI")
        # Swagger UI ships a dark theme. This class on <html> switches it on.
        html = page.body.decode("utf-8").replace("<html>", '<html class="dark-mode">', 1)
        return HTMLResponse(html)

    @app.get("/", include_in_schema=False)
    def web_app() -> FileResponse:
        """The web app: one HTML page that calls this API from the browser."""
        return FileResponse(
            STATIC_DIR / "index.html",
            headers={"Content-Security-Policy": WEB_APP_CSP, "Cache-Control": "no-cache"},
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(categories.router)
    app.include_router(expenses.router)
    app.include_router(budgets.router)
    app.include_router(summary.router)
    return app


app = create_app()
