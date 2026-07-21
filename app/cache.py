import json
import logging
from typing import Any

import redis

logger = logging.getLogger("API_Cache")

class RedisCacheWrapper:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.enabled = False
        self.r = None
        self.local_cache = {}  # Fallback in-memory cache

        try:
            # Short timeout to fail fast if Redis is not running
            self.r = redis.Redis(host=host, port=port, db=db, socket_timeout=1.0)
            # Ping to verify connection
            self.r.ping()
            self.enabled = True
            logger.info("Conexão estabelecida com o servidor Redis com sucesso. Caching ativado.")
        except (redis.ConnectionError, redis.TimeoutError):
            logger.warning("Não foi possível conectar ao Redis. Caching em memória ativado como fallback.")
            self.enabled = False

    def get(self, key: str) -> Any | None:
        if self.enabled:
            try:
                val = self.r.get(key)
                if val:
                    logger.info(f"[CACHE HIT] Obtendo chave '{key}' do Redis.")
                    return json.loads(val)
            except Exception as e:
                logger.error(f"Erro ao ler do Redis: {e}")

        # Fallback local cache
        if key in self.local_cache:
            logger.info(f"[CACHE HIT] Obtendo chave '{key}' do Cache em Memória local.")
            return self.local_cache[key]

        logger.info(f"[CACHE MISS] Chave '{key}' não encontrada no cache.")
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 60):
        if self.enabled:
            try:
                self.r.setex(key, ttl_seconds, json.dumps(value))
                logger.info(f"[CACHE SET] Salva chave '{key}' no Redis com TTL de {ttl_seconds}s.")
                return
            except Exception as e:
                logger.error(f"Erro ao salvar no Redis: {e}")

        # Fallback local cache
        self.local_cache[key] = value
        logger.info(f"[CACHE SET] Salva chave '{key}' no Cache em Memória local.")

    def clear(self):
        if self.enabled:
            try:
                self.r.flushdb()
                logger.info("Cache do Redis limpo com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao limpar Redis: {e}")
        self.local_cache.clear()
        logger.info("Cache em memória local limpo.")
