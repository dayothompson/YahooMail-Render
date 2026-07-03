from __future__ import annotations

import email as stdlib_email
import email.header
from datetime import date
from email.message import Message
from typing import Optional

import imapclient  # type: ignore

from .auth import AppPasswordCredentials
from .exceptions import AuthError, ConnectionError, NotFoundError, YahooMailError
from .models import Attachment, Email, EmailAddress, Folder

IMAP_HOST = "imap.mail.yahoo.com"
IMAP_PORT = 993


def _decode_header(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for raw, charset in parts:
        if isinstance(raw, bytes):
            decoded.append(raw.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(raw)
    return "".join(decoded)


def _parse_address(raw: Optional[str]) -> EmailAddress:
    if not raw:
        return EmailAddress(name="", email="")
    raw = _decode_header(raw).strip()
    if "<" in raw and ">" in raw:
        name = raw[: raw.index("<")].strip().strip('"')
        addr = raw[raw.index("<") + 1 : raw.index(">")].strip()
        return EmailAddress(name=name, email=addr)
    return EmailAddress(name="", email=raw)


def _parse_address_list(raw: Optional[str]) -> list[EmailAddress]:
    if not raw:
        return []
    return [_parse_address(part.strip()) for part in raw.split(",") if part.strip()]


def _extract_parts(
    msg: Message,
) -> tuple[Optional[str], Optional[str], list[Attachment]]:
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    attachments: list[Attachment] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")

            if "attachment" in disposition or part.get_filename():
                filename = _decode_header(part.get_filename() or "attachment")
                data = part.get_payload(decode=True) or b""
                attachments.append(
                    Attachment(
                        filename=filename,
                        content_type=content_type,
                        data=data,
                        size=len(data),
                    )
                )
            elif content_type == "text/plain" and body_text is None:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body_text = payload.decode(charset, errors="replace") if payload else None
            elif content_type == "text/html" and body_html is None:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body_html = payload.decode(charset, errors="replace") if payload else None
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace") if payload else None
        if content_type == "text/html":
            body_html = text
        else:
            body_text = text

    return body_text, body_html, attachments


def _parse_email(uid: int, raw_bytes: bytes, folder: str) -> Email:
    msg = stdlib_email.message_from_bytes(raw_bytes)
    body_text, body_html, attachments = _extract_parts(msg)

    date_str = msg.get("Date")
    parsed_date = None
    if date_str:
        from email.utils import parsedate_to_datetime
        try:
            parsed_date = parsedate_to_datetime(date_str)
        except Exception:
            pass

    return Email(
        uid=uid,
        message_id=msg.get("Message-ID", ""),
        subject=_decode_header(msg.get("Subject")),
        from_=_parse_address(msg.get("From")),
        to=_parse_address_list(msg.get("To")),
        cc=_parse_address_list(msg.get("Cc")),
        date=parsed_date,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
        flags=[],
        folder=folder,
    )


class ImapClient:
    def __init__(self, credentials: AppPasswordCredentials) -> None:
        self._credentials = credentials
        self._client: Optional[imapclient.IMAPClient] = None

    def connect(self) -> None:
        try:
            self._client = imapclient.IMAPClient(IMAP_HOST, port=IMAP_PORT, ssl=True)
            self._client.login(self._credentials.username, self._credentials.app_password)
        except imapclient.exceptions.LoginError as exc:
            raise AuthError(f"Yahoo Mail login failed: {exc}") from exc
        except OSError as exc:
            raise ConnectionError(f"Cannot connect to {IMAP_HOST}: {exc}") from exc

    def disconnect(self) -> None:
        if self._client:
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None

    @property
    def _conn(self) -> imapclient.IMAPClient:
        if self._client is None:
            self.connect()
        assert self._client is not None
        return self._client

    # ------------------------------------------------------------------
    # Folders
    # ------------------------------------------------------------------

    def list_folders(self) -> list[Folder]:
        try:
            raw = self._conn.list_folders()
        except Exception as exc:
            raise YahooMailError(f"Failed to list folders: {exc}") from exc

        folders: list[Folder] = []
        for flags, delimiter, name in raw:
            try:
                status = self._conn.folder_status(name, ["MESSAGES", "UNSEEN"])
                message_count = status[b"MESSAGES"]
                unseen_count = status[b"UNSEEN"]
            except Exception:
                message_count = 0
                unseen_count = 0

            delimiter_str = delimiter.decode() if isinstance(delimiter, bytes) else delimiter
            short_name = name.split(delimiter_str)[-1] if delimiter_str else name

            folders.append(
                Folder(
                    name=short_name,
                    full_path=name,
                    message_count=message_count,
                    unseen_count=unseen_count,
                )
            )
        return folders

    def create_folder(self, name: str) -> Folder:
        try:
            self._conn.create_folder(name)
        except Exception as exc:
            raise YahooMailError(f"Failed to create folder '{name}': {exc}") from exc
        return Folder(name=name, full_path=name, message_count=0, unseen_count=0)

    def delete_folder(self, name: str) -> None:
        try:
            self._conn.delete_folder(name)
        except Exception as exc:
            raise YahooMailError(f"Failed to delete folder '{name}': {exc}") from exc

    def rename_folder(self, old_name: str, new_name: str) -> None:
        try:
            self._conn.rename_folder(old_name, new_name)
        except Exception as exc:
            raise YahooMailError(f"Failed to rename folder '{old_name}' -> '{new_name}': {exc}") from exc

    # ------------------------------------------------------------------
    # Email reading
    # ------------------------------------------------------------------

    def list_emails(self, folder: str = "INBOX", limit: int = 50) -> list[Email]:
        try:
            self._conn.select_folder(folder, readonly=True)
            uids = self._conn.search(["ALL"])
        except Exception as exc:
            raise YahooMailError(f"Failed to list emails in '{folder}': {exc}") from exc

        uids = uids[-limit:]  # most recent N
        return self._fetch_emails(uids, folder)

    def fetch_email(self, uid: int, folder: str = "INBOX") -> Email:
        try:
            self._conn.select_folder(folder, readonly=True)
            data = self._conn.fetch([uid], ["RFC822", "FLAGS"])
        except Exception as exc:
            raise YahooMailError(f"Failed to fetch email uid={uid}: {exc}") from exc

        if uid not in data:
            raise NotFoundError(f"Email uid={uid} not found in '{folder}'")

        raw = data[uid][b"RFC822"]
        flags = [f.decode() if isinstance(f, bytes) else str(f) for f in data[uid].get(b"FLAGS", [])]
        parsed = _parse_email(uid, raw, folder)
        return parsed.model_copy(update={"flags": flags})

    def search_emails(
        self,
        folder: str = "INBOX",
        from_: Optional[str] = None,
        subject: Optional[str] = None,
        since: Optional[date] = None,
        before: Optional[date] = None,
        unread_only: bool = False,
    ) -> list[Email]:
        criteria: list[str | bytes] = []

        if unread_only:
            criteria.append("UNSEEN")
        if from_:
            criteria += ["FROM", from_]
        if subject:
            criteria += ["SUBJECT", subject]
        if since:
            criteria += ["SINCE", since.strftime("%d-%b-%Y")]
        if before:
            criteria += ["BEFORE", before.strftime("%d-%b-%Y")]

        if not criteria:
            criteria = ["ALL"]

        try:
            self._conn.select_folder(folder, readonly=True)
            uids = self._conn.search(criteria)
        except Exception as exc:
            raise YahooMailError(f"Email search failed: {exc}") from exc

        return self._fetch_emails(uids, folder)

    def _fetch_emails(self, uids: list[int], folder: str) -> list[Email]:
        if not uids:
            return []
        try:
            data = self._conn.fetch(uids, ["RFC822", "FLAGS"])
        except Exception as exc:
            raise YahooMailError(f"Failed to fetch emails: {exc}") from exc

        results: list[Email] = []
        for uid in uids:
            if uid not in data:
                continue
            raw = data[uid][b"RFC822"]
            flags = [f.decode() if isinstance(f, bytes) else str(f) for f in data[uid].get(b"FLAGS", [])]
            parsed = _parse_email(uid, raw, folder)
            results.append(parsed.model_copy(update={"flags": flags}))
        return results

    # ------------------------------------------------------------------
    # Email actions
    # ------------------------------------------------------------------

    def move_email(self, uid: int, from_folder: str, to_folder: str) -> None:
        try:
            self._conn.select_folder(from_folder)
            self._conn.move([uid], to_folder)
        except Exception as exc:
            raise YahooMailError(f"Failed to move email uid={uid}: {exc}") from exc

    def copy_email(self, uid: int, from_folder: str, to_folder: str) -> None:
        try:
            self._conn.select_folder(from_folder)
            self._conn.copy([uid], to_folder)
        except Exception as exc:
            raise YahooMailError(f"Failed to copy email uid={uid}: {exc}") from exc

    def delete_email(self, uid: int, folder: str) -> None:
        try:
            self._conn.select_folder(folder)
            self._conn.delete_messages([uid])
            self._conn.expunge()
        except Exception as exc:
            raise YahooMailError(f"Failed to delete email uid={uid}: {exc}") from exc

    def mark_read(self, uid: int, folder: str) -> None:
        try:
            self._conn.select_folder(folder)
            self._conn.add_flags([uid], [imapclient.SEEN])
        except Exception as exc:
            raise YahooMailError(f"Failed to mark email uid={uid} as read: {exc}") from exc

    def mark_unread(self, uid: int, folder: str) -> None:
        try:
            self._conn.select_folder(folder)
            self._conn.remove_flags([uid], [imapclient.SEEN])
        except Exception as exc:
            raise YahooMailError(f"Failed to mark email uid={uid} as unread: {exc}") from exc
