import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from domains.common.paths import get_db_path

from . import config
from .deps import cache
from .routers import auth, catalog, copilot, delta, features, kpis, lineage, ml, quality, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("API_Gateway")

app = FastAPI(
    title="Data-as-a-Service (DaaS) API Gateway",
    description="Exposição segura e cacheada de produtos de dados e KPIs do central Data Warehouse",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.2f client=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request.client.host if request.client else "-",
    )
    return response


# Expose Prometheus metrics (request count, latency histograms, in-progress) at /metrics
Instrumentator(
    should_group_status_codes=False,
    excluded_handlers=["/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=True, tags=["observability"])

app.include_router(auth.router)
app.include_router(copilot.router)
app.include_router(kpis.router)
app.include_router(ml.router)
app.include_router(search.router)
app.include_router(quality.router)
app.include_router(delta.router)
app.include_router(lineage.router)
app.include_router(catalog.router)
app.include_router(features.router)


@app.get("/")
def read_root():
    db_path = get_db_path()
    return {
        "status": "healthy",
        "api_version": "1.1.0",
        "database_connected": os.path.exists(db_path),
        "database_path": db_path,
        "cache_type": "Redis" if cache.enabled else "In-Memory Fallback",
    }
