"""Settings and configuration endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from api.dependencies import get_settings_service
from api.schemas.settings import SettingsResponse, UpdateSettingsRequest
from settings.service import SettingsService

log = logging.getLogger("hard_workers.api.routers.settings")

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(ss: SettingsService = Depends(get_settings_service)):
    raw = ss.raw()
    return SettingsResponse(settings=raw)


@router.patch("", response_model=SettingsResponse)
async def update_settings(
    body: UpdateSettingsRequest,
    ss: SettingsService = Depends(get_settings_service),
):
    for key, value in body.patch.items():
        section = _resolve_section(key)
        if section:
            getattr(ss, f"set_{section}", lambda: None)({key: value})
        else:
            log.warning("Unknown settings key: %s", key)
    raw = ss.raw()
    return SettingsResponse(settings=raw)


def _resolve_section(key: str) -> str | None:
    """Map a flat settings key to the set_* method name."""
    mapping = {
        "theme": "appearance",
        "language": "appearance",
        "font_size": "appearance",
        "default_model": "models",
        "max_tokens": "models",
        "temperature": "models",
    }
    if key in mapping:
        return mapping[key]
    return None
