from .auth import AppPasswordCredentials
from .client import YahooMailClient
from .exceptions import (
    AuthError,
    CalendarError,
    NotFoundError,
    SendError,
    YahooMailError,
)
from .models import (
    Attachment,
    Calendar,
    CalendarEvent,
    Email,
    EmailAddress,
    Folder,
)

__all__ = [
    "AppPasswordCredentials",
    "YahooMailClient",
    # Exceptions
    "YahooMailError",
    "AuthError",
    "CalendarError",
    "NotFoundError",
    "SendError",
    # Models
    "Email",
    "EmailAddress",
    "Attachment",
    "Folder",
    "Calendar",
    "CalendarEvent",
]
