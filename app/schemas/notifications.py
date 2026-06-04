from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NotificationEvent(BaseModel):
    event_id: str
    plant_id: str
    type: Literal["alert", "insight", "chat", "system"]
    message: str
    created_at: datetime


class NotificationsResponse(BaseModel):
    events: list[NotificationEvent]
