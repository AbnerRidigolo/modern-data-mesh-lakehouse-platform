"""Authentication primitives: password hashing, JWT issuance/validation and a
lightweight in-memory rate limiter for the login endpoint.
"""
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from . import config

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de autenticação inválido ou expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except jwt.PyJWTError:
        raise credentials_exception


class LoginRateLimiter:
    """Simple per-username sliding-window lockout to slow down brute-force attempts.

    Single-process, in-memory only — sufficient for this demo's single
    uvicorn worker; a real deployment would back this with Redis instead.
    """

    def __init__(self, max_attempts: int, lockout_seconds: int):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, list[float]] = {}

    def check(self, identifier: str) -> None:
        now = time.time()
        attempts = [t for t in self._failures.get(identifier, []) if now - t < self.lockout_seconds]
        self._failures[identifier] = attempts
        if len(attempts) >= self.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Muitas tentativas de login falhas. Tente novamente em {self.lockout_seconds}s.",
            )

    def record_failure(self, identifier: str) -> None:
        now = time.time()
        self._failures.setdefault(identifier, []).append(now)

    def record_success(self, identifier: str) -> None:
        self._failures.pop(identifier, None)


login_rate_limiter = LoginRateLimiter(config.LOGIN_MAX_ATTEMPTS, config.LOGIN_LOCKOUT_SECONDS)
