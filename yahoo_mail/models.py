from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EmailAddress(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    email: str

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>" if self.name else self.email


class Attachment(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    content_type: str
    data: bytes
    size: int


class Email(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: int
    message_id: str
    subject: str
    from_: EmailAddress
    to: list[EmailAddress]
    cc: list[EmailAddress]
    date: Optional[datetime]
    body_text: Optional[str]
    body_html: Optional[str]
    attachments: list[Attachment]
    flags: list[str]
    folder: str


class Folder(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    full_path: str
    message_count: int
    unseen_count: int


class Calendar(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    url: str
    color: Optional[str]


class CalendarEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str
    title: str
    description: Optional[str]
    start: datetime
    end: datetime
    location: Optional[str]
    attendees: list[str]
    status: Optional[str]
