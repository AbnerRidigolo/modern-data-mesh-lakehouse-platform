import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from .. import config
from ..security import create_access_token, login_rate_limiter, verify_password

logger = logging.getLogger("API_Auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    login_rate_limiter.check(form_data.username)

    valid_user = form_data.username == config.ADMIN_USERNAME
    valid_password = valid_user and verify_password(form_data.password, config.ADMIN_PASSWORD_HASH)

    if not valid_password:
        login_rate_limiter.record_failure(form_data.username)
        raise HTTPException(status_code=400, detail="Usuário ou senha incorretos.")

    login_rate_limiter.record_success(form_data.username)
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}
