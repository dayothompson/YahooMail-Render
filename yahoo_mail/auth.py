from dataclasses import dataclass


@dataclass(frozen=True)
class AppPasswordCredentials:
    """Credentials for Yahoo Mail using an app-specific password.

    To generate an app password:
    1. Enable 2-step verification on your Yahoo account.
    2. Go to Account Security → Generate app password.
    3. Use that password here — NOT your regular Yahoo password.
    """

    username: str  # full Yahoo address, e.g. user@yahoo.com
    app_password: str
