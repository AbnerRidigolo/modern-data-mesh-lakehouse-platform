"""Shared FastAPI dependencies: DuckDB connections, Redis cache, Qdrant client
and the lazily-loaded FastEmbed model.
"""
import logging
import os

import duckdb
from qdrant_client import QdrantClient

from domains.common.paths import get_db_path

from . import config
from .cache import RedisCacheWrapper

logger = logging.getLogger("API_Deps")

cache = RedisCacheWrapper(host=config.REDIS_HOST, port=config.REDIS_PORT)
qdrant_client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)

_embedding_model = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        logger.info("Carregando modelo de embeddings FastEmbed no FastAPI...")
        from fastembed import TextEmbedding

        _embedding_model = TextEmbedding()
    return _embedding_model


def run_query(query: str) -> list:
    """Execute a read-only query against the analytics DuckDB database."""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Arquivo do DuckDB não encontrado em: {db_path}. Execute a pipeline primeiro.")

    conn = duckdb.connect(db_path, read_only=True)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row, strict=False)) for row in rows]
    finally:
        conn.close()
