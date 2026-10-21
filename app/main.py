import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import auth, health
from app.templating import templates

logger = logging.getLogger("repair_shop")
logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    if settings.is_vercel:
        # Vercel's function filesystem is ephemeral/read-only. Persist all shop data
        # in PostgreSQL and run migrations under a database advisory lock.
        from app.deployment import upgrade_database

        upgrade_database()
    else:
        if settings.uses_sqlite:
            settings.backup_path.mkdir(parents=True, exist_ok=True)
            Path("data").mkdir(parents=True, exist_ok=True)

        # Local/Docker SQLite installs keep the existing scheduled file backups.
        try:
            from app.services.backup import (
                run_startup_catchup_backup,
                start_backup_scheduler,
            )

            if settings.uses_sqlite:
                run_startup_catchup_backup()
                scheduler = start_backup_scheduler()
        except Exception as e:
            logger.warning("Backup initialization note: %s", e)

    yield

    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Mobile Repair Shop System",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)

# Static files
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")


# Security headers middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Check if HTMX request
    if request.headers.get("HX-Request") == "true":
        if exc.headers and "HX-Redirect" in exc.headers:
            return Response(status_code=exc.status_code, headers=exc.headers)
        if exc.status_code in (409, 422):
            return HTMLResponse(
                f'<div class="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">{exc.detail}</div>',
                status_code=exc.status_code,
            )
        return HTMLResponse(
            f'<div class="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">{exc.detail}</div>',
            status_code=exc.status_code,
        )

    if exc.headers and "Location" in exc.headers:
        return Response(status_code=exc.status_code, headers=exc.headers)

    if exc.status_code == 404:
        return templates.TemplateResponse(request=request, name="errors/404.html", context={}, status_code=404)
    if exc.status_code == 403:
        return templates.TemplateResponse(
            request=request, name="errors/403.html", context={"detail": exc.detail}, status_code=403
        )

    return HTMLResponse(f"<h3>Error {exc.status_code}</h3><p>{exc.detail}</p>", status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error processing request: %s", request.url.path)
    if request.headers.get("HX-Request") == "true":
        return HTMLResponse(
            '<div class="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">An unexpected server error occurred.</div>',
            status_code=500,
        )
    return templates.TemplateResponse(request=request, name="errors/500.html", context={}, status_code=500)



# Include Routers
from app.routers import (
    audit,
    autocomplete,
    cash,
    customers,
    dashboard,
    importer,
    inventory,
    items,
    payments,
    queue,
    search,
    suppliers,
    tickets,
)
from app.routers import (
    settings as settings_router,
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(queue.router)
app.include_router(tickets.router)
app.include_router(items.router)
app.include_router(inventory.router)
app.include_router(suppliers.router)
app.include_router(payments.router)
app.include_router(search.router)
app.include_router(customers.router)
app.include_router(autocomplete.router)
app.include_router(cash.router)
app.include_router(audit.router)
app.include_router(settings_router.router)
app.include_router(importer.router)
app.include_router(dashboard.router)

