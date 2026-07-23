"""Centralized runtime configuration for the DaaS API Gateway.

All secrets are sourced from environment variables. Defaults are provided so
the demo stack keeps working out-of-the-box via docker-compose, but a clear
warning is logged whenever a production-sensitive default is in effect so it
is not silently carried into a real deployment.
"""
import logging
import os

logger = logging.getLogger("API_Config")

# --- JWT / Auth ---
_DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    JWT_SECRET_KEY = _DEV_JWT_SECRET
    logger.warning(
        "JWT_SECRET_KEY não definido no ambiente. Usando segredo de desenvolvimento "
        "inseguro. Defina JWT_SECRET_KEY antes de qualquer deploy real."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# --- Admin credentials (single demo user) ---
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")

# Bcrypt hash for the default password "adminpassword" — used only when
# ADMIN_PASSWORD_HASH is not set, so local/demo runs keep working.
_DEV_ADMIN_PASSWORD_HASH = "$2b$12$Nb3s.jxCa0NDAdZlU.SczO5p23g0e4BwzaxxHaVFLSRYaNVabQoJe"
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
if not ADMIN_PASSWORD_HASH:
    ADMIN_PASSWORD_HASH = _DEV_ADMIN_PASSWORD_HASH
    logger.warning(
        "ADMIN_PASSWORD_HASH não definido no ambiente. Usando hash de desenvolvimento "
        "para a senha padrão 'adminpassword'. Defina ADMIN_PASSWORD_HASH em produção."
    )

# --- Login rate limiting (basic brute-force mitigation) ---
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "60"))

# --- CORS ---
_default_origins = "http://localhost:5173,http://localhost:4173,http://localhost:3000"
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

# --- Downstream services ---
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6389"))
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6335"))

# --- AI Copilot (Claude) ---
# O SDK da Anthropic resolve a credencial via ANTHROPIC_API_KEY (ou perfil de
# login). Sem credencial, o Copilot fica desabilitado e a API responde 503.
COPILOT_ENABLED = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
COPILOT_MODEL = os.environ.get("COPILOT_MODEL", "claude-opus-4-8")
COPILOT_MAX_TOKENS = int(os.environ.get("COPILOT_MAX_TOKENS", "8192"))
COPILOT_MAX_TOOL_ITERATIONS = int(os.environ.get("COPILOT_MAX_TOOL_ITERATIONS", "6"))
COPILOT_SQL_ROW_LIMIT = int(os.environ.get("COPILOT_SQL_ROW_LIMIT", "50"))
