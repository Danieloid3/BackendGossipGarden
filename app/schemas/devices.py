from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DeviceTokenCreate(BaseModel):
    token: str = Field(..., min_length=1)
    platform: Literal["ios", "android", "web"]


class DeviceTokenResponse(BaseModel):
    id: str
    user_id: str
    token: str
    platform: str
    created_at: datetime
    last_used_at: datetime
