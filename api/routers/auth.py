"""Authentication endpoints — JWT login, refresh, logout (with revocation)."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.dependencies import get_current_user
from api.schemas.auth import LoginRequest, TokenResponse, UserInfo
from utils.crypto import create_token, revoke_token

log = logging.getLogger("hard_workers.api.routers.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def _get_admin_creds(request: Request) -> tuple[str, str]:
    config = getattr(request.app.state, "config", None)
    cfg_api = getattr(config, "api", None)
    username = getattr(cfg_api, "admin_username", "admin") if cfg_api else "admin"
    password = getattr(cfg_api, "admin_password", "admin") if cfg_api else "admin"
    return username, password


def _get_jwt_secret(request: Request) -> str:
    config = getattr(request.app.state, "config", None)
    cfg_api = getattr(config, "api", None)
    return (
        getattr(cfg_api, "jwt_secret", "dev-secret-change-in-production")
        if cfg_api
        else "dev-secret-change-in-production"
    )


def _get_token_expiry(request: Request) -> timedelta:
    config = getattr(request.app.state, "config", None)
    cfg_api = getattr(config, "api", None)
    hours = getattr(cfg_api, "jwt_expire_hours", 24) if cfg_api else 24
    return timedelta(hours=hours)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    admin_user, admin_pass = _get_admin_creds(request)
    if body.username != admin_user or body.password != admin_pass:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    secret = _get_jwt_secret(request)
    expires = _get_token_expiry(request)
    token = create_token({"sub": body.username}, secret, expires)
    return TokenResponse(access_token=token, expires_in=int(expires.total_seconds()))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, user: dict = Depends(get_current_user)):
    secret = _get_jwt_secret(request)
    expires = _get_token_expiry(request)
    token = create_token({"sub": user["username"]}, secret, expires)
    return TokenResponse(access_token=token, expires_in=int(expires.total_seconds()))


@router.post("/logout")
async def logout(request: Request, user: dict = Depends(get_current_user)):
    """Revoke the current JWT token by its ``jti`` claim."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from utils.crypto import verify_token as vt

            payload = vt(token, _get_jwt_secret(request))
            if payload and "jti" in payload:
                revoke_token(payload["jti"])
                log.info("Token revoked: jti=%s user=%s", payload["jti"], user.get("username"))
        except Exception:
            pass
    return {"ok": True}


@router.get("/me", response_model=UserInfo)
async def me(user: dict = Depends(get_current_user)):
    return UserInfo(username=user["username"], role=user["role"])
