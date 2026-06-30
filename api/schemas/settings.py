"""User settings schemas."""

from __future__ import annotations

from pydantic import BaseModel


class UpdateSettingsRequest(BaseModel):
    patch: dict


class SettingsResponse(BaseModel):
    settings: dict
