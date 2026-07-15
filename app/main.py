import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .deps import cache
from .routers import auth, catalog, delta, kpis, lineage, ml, quality, search
from domains.common.paths import get_db_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("API_Gateway")

app = FastAPI(
    title="Data-as-a-Service (DaaS) API Gateway",
    description="Exposição segura e cacheada de produtos de dados e KPIs do central Data Warehouse",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(kpis.router)
app.include_router(ml.router)
app.include_router(search.router)
app.include_router(quality.router)
app.include_router(delta.router)
app.include_router(lineage.router)
app.include_router(catalog.router)


@app.get("/")
def read_root():
    db_path = get_db_path()
    return {
        "status": "healthy",
        "api_version": "1.0.0",
        "database_connected": os.path.exists(db_path),
        "database_path": db_path,
        "cache_type": "Redis" if cache.enabled else "In-Memory Fallback",
    }
