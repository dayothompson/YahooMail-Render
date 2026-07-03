class YahooMailError(Exception):
    """Base exception for all Yahoo Mail SDK errors."""


class AuthError(YahooMailError):
    """Raised when authentication with Yahoo Mail fails."""


class ConnectionError(YahooMailError):
    """Raised when a connection to Yahoo Mail servers cannot be established."""


class NotFoundError(YahooMailError):
    """Raised when a requested resource (folder, email, event) does not exist."""


class SendError(YahooMailError):
    """Raised when sending an email fails."""


class CalendarError(YahooMailError):
    """Raised when a calendar operation fails."""
