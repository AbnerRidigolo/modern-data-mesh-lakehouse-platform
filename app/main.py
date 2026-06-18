import os
import logging
import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
try:
    from .cache import RedisCacheWrapper
except (ImportError, ValueError):
    from cache import RedisCacheWrapper
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("API_Gateway")

app = FastAPI(
    title="Data-as-a-Service (DaaS) API Gateway",
    description="Exposição segura e cacheada de produtos de dados e KPIs do central Data Warehouse",
    version="1.0.0"
)

# Enable CORS for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dynamically locate DuckDB file
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
local_db = os.path.join(base_dir, "storage", "analytics.duckdb")
container_db = "/opt/airflow/storage/analytics.duckdb"

db_path = os.environ.get("DB_PATH")
if not db_path:
    db_path = container_db if os.path.exists(container_db) else local_db

logger.info(f"Conectando com o banco de dados analítico: {db_path}")

# Initialize Redis cache (connects to redis container or localhost)
redis_host = os.environ.get("REDIS_HOST", "localhost")
redis_port = int(os.environ.get("REDIS_PORT", 6389))
cache = RedisCacheWrapper(host=redis_host, port=redis_port)

def run_query(query: str) -> list:
    """Helper function to execute read-only queries on DuckDB."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Arquivo do DuckDB não encontrado em: {db_path}. Execute a pipeline primeiro.")
        
    conn = duckdb.connect(db_path, read_only=True)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        # Fetch columns
        columns = [desc[0] for desc in cursor.description]
        # Fetch records
        rows = cursor.fetchall()
        # Convert to list of dicts
        results = [dict(zip(columns, row)) for row in rows]
        return results
    finally:
        conn.close()

@app.get("/")
def read_root():
    return {
        "status": "healthy",
        "api_version": "1.0.0",
        "database_connected": os.path.exists(db_path),
        "database_path": db_path,
        "cache_type": "Redis" if cache.enabled else "In-Memory Fallback"
    }

@app.get("/api/v1/kpis")
def get_kpis():
    cache_key = "kpis_monthly"
    
    # Try getting from cache
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {
            "source": "cache",
            "data": cached_val
        }
        
    # Query Database on Cache Miss
    try:
        start_time = time.time()
        query = "SELECT * FROM dm_monthly_kpis"
        data = run_query(query)
        # Format date objects to string for JSON serialization
        for row in data:
            if "sales_month" in row and row["sales_month"]:
                row["sales_month"] = str(row["sales_month"])[:10] # YYYY-MM-DD
                
        query_time = time.time() - start_time
        logger.info(f"Query executada em {query_time:.4f}s. Salvando no cache.")
        
        # Save to cache with 60s TTL
        cache.set(cache_key, data, ttl_seconds=60)
        
        return {
            "source": "database",
            "query_time_seconds": round(query_time, 4),
            "data": data
        }
    except Exception as e:
        logger.error(f"Erro ao consultar KPIs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/customers")
def get_customers():
    cache_key = "customers_list"
    
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return {
            "source": "cache",
            "data": cached_val
        }
        
    try:
        start_time = time.time()
        query = "SELECT customer_id, customer_name, email, created_at, status FROM dim_customers LIMIT 100"
        data = run_query(query)
        for row in data:
            if "created_at" in row and row["created_at"]:
                row["created_at"] = str(row["created_at"])
                
        query_time = time.time() - start_time
        logger.info(f"Query executada em {query_time:.4f}s. Salvando no cache.")
        
        cache.set(cache_key, data, ttl_seconds=60)
        
        return {
            "source": "database",
            "query_time_seconds": round(query_time, 4),
            "data": data
        }
    except Exception as e:
        logger.error(f"Erro ao consultar clientes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/cache/clear")
def clear_cache():
    cache.clear()
    return {"message": "Todos os caches limpos."}
