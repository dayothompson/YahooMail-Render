from __future__ import annotations

import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .auth import AppPasswordCredentials
from .exceptions import AuthError, SendError
from .models import Email

SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = 465


class SmtpClient:
    def __init__(self, credentials: AppPasswordCredentials) -> None:
        self._credentials = credentials

    def send_email(
        self,
        to: list[str],
        subject: str,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[list[tuple[str, bytes, str]]] = None,
        reply_to: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> None:
        """Send an email via Yahoo SMTP.

        attachments: list of (filename, data_bytes, mime_type) tuples.
        """
        msg = self._build_message(
            from_addr=self._credentials.username,
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc or [],
            reply_to=reply_to,
            in_reply_to=in_reply_to,
            references=references,
            attachments=attachments or [],
        )

        all_recipients = list(to) + (cc or []) + (bcc or [])
        self._send(msg, all_recipients)

    def reply(self, original: Email, body_text: Optional[str] = None, body_html: Optional[str] = None) -> None:
        subject = original.subject if original.subject.lower().startswith("re:") else f"Re: {original.subject}"
        to = [original.from_.email]
        self.send_email(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            in_reply_to=original.message_id,
            references=original.message_id,
        )

    def forward(self, original: Email, to: list[str]) -> None:
        subject = original.subject if original.subject.lower().startswith("fwd:") else f"Fwd: {original.subject}"
        body = f"\n\n---------- Forwarded message ----------\n"
        body += f"From: {original.from_}\n"
        body += f"Subject: {original.subject}\n\n"
        body += original.body_text or ""

        attachment_data: list[tuple[str, bytes, str]] = [
            (att.filename, att.data, att.content_type) for att in original.attachments
        ]

        self.send_email(
            to=to,
            subject=subject,
            body_text=body,
            body_html=original.body_html,
            attachments=attachment_data,
        )

    # ------------------------------------------------------------------

    def _build_message(
        self,
        from_addr: str,
        to: list[str],
        subject: str,
        body_text: Optional[str],
        body_html: Optional[str],
        cc: list[str],
        reply_to: Optional[str],
        in_reply_to: Optional[str],
        references: Optional[str],
        attachments: list[tuple[str, bytes, str]],
    ) -> MIMEMultipart:
        msg = MIMEMultipart("mixed")
        msg["From"] = from_addr
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject

        if cc:
            msg["Cc"] = ", ".join(cc)
        if reply_to:
            msg["Reply-To"] = reply_to
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        # Body part
        if body_html and body_text:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body_text, "plain", "utf-8"))
            alt.attach(MIMEText(body_html, "html", "utf-8"))
            msg.attach(alt)
        elif body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        elif body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Attachments
        for filename, data, mime_type in attachments:
            main_type, sub_type = mime_type.split("/", 1) if "/" in mime_type else ("application", "octet-stream")
            part = MIMEBase(main_type, sub_type)
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)

        return msg

    def _send(self, msg: MIMEMultipart, recipients: list[str]) -> None:
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(self._credentials.username, self._credentials.app_password)
                server.sendmail(self._credentials.username, recipients, msg.as_string())
        except smtplib.SMTPAuthenticationError as exc:
            raise AuthError(f"SMTP authentication failed: {exc}") from exc
        except smtplib.SMTPException as exc:
            raise SendError(f"Failed to send email: {exc}") from exc
