from __future__ import annotations

import os
from datetime import date, datetime
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .auth import AppPasswordCredentials
from .client import YahooMailClient
from .models import CalendarEvent

load_dotenv()

mcp = FastMCP("Yahoo Mail")


def _get_client() -> YahooMailClient:
    """Return a fresh connected client. Caller must use as context manager or disconnect."""
    creds = AppPasswordCredentials(
        username=os.environ["YAHOO_USERNAME"],
        app_password=os.environ["YAHOO_APP_PASSWORD"],
    )
    return YahooMailClient(creds)


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


@mcp.tool()
def list_folders() -> list[dict]:
    """List all folders in the Yahoo Mail mailbox with message counts."""
    with _get_client() as client:
        return [f.model_dump() for f in client.list_folders()]


@mcp.tool()
def create_folder(name: str) -> dict:
    """Create a new folder in the mailbox."""
    with _get_client() as client:
        return client.create_folder(name).model_dump()


@mcp.tool()
def delete_folder(name: str) -> str:
    """Permanently delete a folder from the mailbox."""
    with _get_client() as client:
        client.delete_folder(name)
    return f"Folder '{name}' deleted."


@mcp.tool()
def rename_folder(old_name: str, new_name: str) -> str:
    """Rename an existing folder."""
    with _get_client() as client:
        client.rename_folder(old_name, new_name)
    return f"Folder '{old_name}' renamed to '{new_name}'."


# ---------------------------------------------------------------------------
# Reading emails
# ---------------------------------------------------------------------------


def _email_summary(email) -> dict:
    """Return a lightweight dict — no attachment bytes."""
    return {
        "uid": email.uid,
        "message_id": email.message_id,
        "subject": email.subject,
        "from_": str(email.from_),
        "to": [str(a) for a in email.to],
        "cc": [str(a) for a in email.cc],
        "date": email.date.isoformat() if email.date else None,
        "flags": email.flags,
        "folder": email.folder,
        "has_attachments": len(email.attachments) > 0,
        "attachment_names": [a.filename for a in email.attachments],
    }


def _email_full(email) -> dict:
    """Return full email content (no raw attachment bytes)."""
    summary = _email_summary(email)
    summary["body_text"] = email.body_text
    summary["body_html"] = email.body_html
    summary["attachments"] = [
        {"filename": a.filename, "content_type": a.content_type, "size": a.size}
        for a in email.attachments
    ]
    return summary


@mcp.tool()
def list_emails(folder: str = "Inbox", limit: int = 20) -> list[dict]:
    """List the most recent emails in a folder (summaries only, no body text).

    Args:
        folder: Folder name, e.g. 'Inbox', 'Sent', 'Bulk'. Default: 'Inbox'.
        limit: Maximum number of emails to return. Default: 20.
    """
    with _get_client() as client:
        return [_email_summary(e) for e in client.list_emails(folder, limit)]


@mcp.tool()
def fetch_email(uid: int, folder: str = "Inbox") -> dict:
    """Fetch a single email by UID, including full body text/HTML and attachment metadata.

    Args:
        uid: The email UID (from list_emails or search_emails).
        folder: Folder containing the email. Default: 'Inbox'.
    """
    with _get_client() as client:
        return _email_full(client.fetch_email(uid, folder))


@mcp.tool()
def search_emails(
    folder: str = "Inbox",
    from_: Optional[str] = None,
    subject: Optional[str] = None,
    since: Optional[str] = None,
    before: Optional[str] = None,
    unread_only: bool = False,
) -> list[dict]:
    """Search emails by criteria (all filters are AND-combined).

    Args:
        folder: Folder to search. Default: 'Inbox'.
        from_: Filter by sender address or name substring.
        subject: Filter by subject substring.
        since: Only emails on or after this date (YYYY-MM-DD).
        before: Only emails before this date (YYYY-MM-DD).
        unread_only: If true, return only unread emails.
    """
    since_date = date.fromisoformat(since) if since else None
    before_date = date.fromisoformat(before) if before else None
    with _get_client() as client:
        emails = client.search_emails(
            folder=folder,
            from_=from_,
            subject=subject,
            since=since_date,
            before=before_date,
            unread_only=unread_only,
        )
        return [_email_summary(e) for e in emails]


# ---------------------------------------------------------------------------
# Email actions
# ---------------------------------------------------------------------------


@mcp.tool()
def mark_read(uid: int, folder: str = "Inbox") -> str:
    """Mark an email as read."""
    with _get_client() as client:
        client.mark_read(uid, folder)
    return f"Email {uid} marked as read."


@mcp.tool()
def mark_unread(uid: int, folder: str = "Inbox") -> str:
    """Mark an email as unread."""
    with _get_client() as client:
        client.mark_unread(uid, folder)
    return f"Email {uid} marked as unread."


@mcp.tool()
def move_email(uid: int, from_folder: str, to_folder: str) -> str:
    """Move an email from one folder to another."""
    with _get_client() as client:
        client.move_email(uid, from_folder, to_folder)
    return f"Email {uid} moved from '{from_folder}' to '{to_folder}'."


@mcp.tool()
def delete_email(uid: int, folder: str) -> str:
    """Permanently delete an email."""
    with _get_client() as client:
        client.delete_email(uid, folder)
    return f"Email {uid} deleted from '{folder}'."


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


@mcp.tool()
def send_email(
    to: list[str],
    subject: str,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
) -> str:
    """Send a new email from the Yahoo account.

    Args:
        to: List of recipient email addresses.
        subject: Email subject line.
        body_text: Plain-text body (at least one of body_text or body_html required).
        body_html: HTML body.
        cc: CC recipients.
        bcc: BCC recipients.
    """
    client = _get_client()
    client.send_email(to=to, subject=subject, body_text=body_text,
                      body_html=body_html, cc=cc, bcc=bcc)
    return f"Email sent to {', '.join(to)}."


@mcp.tool()
def reply_to_email(uid: int, folder: str, body_text: str) -> str:
    """Reply to an email.

    Args:
        uid: UID of the email to reply to.
        folder: Folder containing the email.
        body_text: Plain-text reply body.
    """
    with _get_client() as client:
        original = client.fetch_email(uid, folder)
        client.reply(original, body_text=body_text)
    return f"Reply sent to '{original.from_}'."


@mcp.tool()
def forward_email(uid: int, folder: str, to: list[str]) -> str:
    """Forward an email to new recipients.

    Args:
        uid: UID of the email to forward.
        folder: Folder containing the email.
        to: List of recipient email addresses.
    """
    with _get_client() as client:
        original = client.fetch_email(uid, folder)
        client.forward(original, to=to)
    return f"Email forwarded to {', '.join(to)}."


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


@mcp.tool()
def list_calendars() -> list[dict]:
    """List all calendars on the Yahoo account."""
    return [c.model_dump() for c in _get_client().list_calendars()]


@mcp.tool()
def list_events(calendar_url: str, start: str, end: str) -> list[dict]:
    """List calendar events between two datetimes.

    Args:
        calendar_url: The calendar URL from list_calendars.
        start: Start datetime in ISO format (e.g. '2025-01-01T00:00:00').
        end: End datetime in ISO format (e.g. '2025-12-31T23:59:59').
    """
    events = _get_client().list_events(
        calendar_url,
        start=datetime.fromisoformat(start),
        end=datetime.fromisoformat(end),
    )
    return [e.model_dump() for e in events]


@mcp.tool()
def get_event(calendar_url: str, event_uid: str) -> dict:
    """Fetch a single calendar event by UID."""
    return _get_client().get_event(calendar_url, event_uid).model_dump()


@mcp.tool()
def create_event(
    calendar_url: str,
    title: str,
    start: str,
    end: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[list[str]] = None,
) -> dict:
    """Create a new calendar event.

    Args:
        calendar_url: The calendar URL from list_calendars.
        title: Event title.
        start: Start datetime in ISO format (e.g. '2025-06-15T10:00:00').
        end: End datetime in ISO format (e.g. '2025-06-15T11:00:00').
        description: Optional event description.
        location: Optional event location.
        attendees: Optional list of attendee email addresses.
    """
    import uuid

    event = CalendarEvent(
        uid=str(uuid.uuid4()),
        title=title,
        start=datetime.fromisoformat(start),
        end=datetime.fromisoformat(end),
        description=description,
        location=location,
        attendees=attendees or [],
        status="CONFIRMED",
    )
    return _get_client().create_event(calendar_url, event).model_dump()


@mcp.tool()
def delete_event(calendar_url: str, event_uid: str) -> str:
    """Delete a calendar event by UID."""
    _get_client().delete_event(calendar_url, event_uid)
    return f"Event '{event_uid}' deleted."
