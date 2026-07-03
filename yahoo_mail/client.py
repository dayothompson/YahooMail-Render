from __future__ import annotations

from datetime import date, datetime
from types import TracebackType
from typing import Optional

from .auth import AppPasswordCredentials
from .calendar import CalendarClient
from .imap import ImapClient
from .models import Calendar, CalendarEvent, Email, Folder
from .smtp import SmtpClient


class YahooMailClient:
    """Unified client for Yahoo Mail — email, folders, attachments, and calendar.

    Usage (context manager — recommended):

        credentials = AppPasswordCredentials(
            username="you@yahoo.com",
            app_password="xxxx-xxxx-xxxx-xxxx",
        )

        with YahooMailClient(credentials) as client:
            emails = client.list_emails("INBOX", limit=10)
            for email in emails:
                print(email.subject, email.from_)

    Usage (manual):

        client = YahooMailClient(credentials)
        client.connect()
        try:
            ...
        finally:
            client.disconnect()
    """

    def __init__(self, credentials: AppPasswordCredentials) -> None:
        self._credentials = credentials
        self._imap = ImapClient(credentials)
        self._smtp = SmtpClient(credentials)
        self._calendar = CalendarClient(credentials)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        self._imap.connect()

    def disconnect(self) -> None:
        self._imap.disconnect()

    def __enter__(self) -> "YahooMailClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Folders
    # ------------------------------------------------------------------

    def list_folders(self) -> list[Folder]:
        """Return all folders/labels in the mailbox."""
        return self._imap.list_folders()

    def create_folder(self, name: str) -> Folder:
        """Create a new folder and return it."""
        return self._imap.create_folder(name)

    def delete_folder(self, name: str) -> None:
        """Permanently delete a folder."""
        self._imap.delete_folder(name)

    def rename_folder(self, old_name: str, new_name: str) -> None:
        """Rename an existing folder."""
        self._imap.rename_folder(old_name, new_name)

    # ------------------------------------------------------------------
    # Email reading
    # ------------------------------------------------------------------

    def list_emails(self, folder: str = "INBOX", limit: int = 50) -> list[Email]:
        """List the most recent `limit` emails in `folder`."""
        return self._imap.list_emails(folder, limit)

    def fetch_email(self, uid: int, folder: str = "INBOX") -> Email:
        """Fetch a single email by UID, including full body and attachments."""
        return self._imap.fetch_email(uid, folder)

    def search_emails(
        self,
        folder: str = "INBOX",
        from_: Optional[str] = None,
        subject: Optional[str] = None,
        since: Optional[date] = None,
        before: Optional[date] = None,
        unread_only: bool = False,
    ) -> list[Email]:
        """Search emails by criteria. All filters are AND-combined."""
        return self._imap.search_emails(
            folder=folder,
            from_=from_,
            subject=subject,
            since=since,
            before=before,
            unread_only=unread_only,
        )

    def download_attachment(self, email: Email, index: int) -> bytes:
        """Return the raw bytes of the attachment at `index` in the email."""
        if index < 0 or index >= len(email.attachments):
            raise IndexError(f"Attachment index {index} out of range (email has {len(email.attachments)})")
        return email.attachments[index].data

    # ------------------------------------------------------------------
    # Email actions
    # ------------------------------------------------------------------

    def move_email(self, uid: int, from_folder: str, to_folder: str) -> None:
        """Move an email from one folder to another."""
        self._imap.move_email(uid, from_folder, to_folder)

    def copy_email(self, uid: int, from_folder: str, to_folder: str) -> None:
        """Copy an email to another folder (original remains)."""
        self._imap.copy_email(uid, from_folder, to_folder)

    def delete_email(self, uid: int, folder: str) -> None:
        """Permanently delete an email."""
        self._imap.delete_email(uid, folder)

    def mark_read(self, uid: int, folder: str) -> None:
        """Mark an email as read."""
        self._imap.mark_read(uid, folder)

    def mark_unread(self, uid: int, folder: str) -> None:
        """Mark an email as unread."""
        self._imap.mark_unread(uid, folder)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_email(
        self,
        to: list[str],
        subject: str,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[list[tuple[str, bytes, str]]] = None,
    ) -> None:
        """Send a new email.

        attachments: list of (filename, data_bytes, mime_type).
          e.g. [("report.pdf", pdf_bytes, "application/pdf")]
        """
        self._smtp.send_email(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
        )

    def reply(
        self,
        original: Email,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
    ) -> None:
        """Reply to an email."""
        self._smtp.reply(original, body_text=body_text, body_html=body_html)

    def forward(self, original: Email, to: list[str]) -> None:
        """Forward an email to new recipients."""
        self._smtp.forward(original, to)

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------

    def list_calendars(self) -> list[Calendar]:
        """Return all calendars on the Yahoo account."""
        return self._calendar.list_calendars()

    def list_events(
        self, calendar_url: str, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Return events in a calendar between `start` and `end`."""
        return self._calendar.list_events(calendar_url, start, end)

    def get_event(self, calendar_url: str, event_uid: str) -> CalendarEvent:
        """Fetch a single calendar event by UID."""
        return self._calendar.get_event(calendar_url, event_uid)

    def create_event(self, calendar_url: str, event: CalendarEvent) -> CalendarEvent:
        """Create a new calendar event and return the saved version."""
        return self._calendar.create_event(calendar_url, event)

    def delete_event(self, calendar_url: str, event_uid: str) -> None:
        """Delete a calendar event by UID."""
        self._calendar.delete_event(calendar_url, event_uid)
