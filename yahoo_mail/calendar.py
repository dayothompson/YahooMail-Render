from __future__ import annotations

import base64
import re
import ssl
import urllib.request
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import caldav  # type: ignore
from caldav import error as caldav_error  # type: ignore

from .auth import AppPasswordCredentials
from .exceptions import CalendarError, NotFoundError
from .models import Calendar, CalendarEvent

CALDAV_BASE = "https://caldav.calendar.yahoo.com"
_SSL_CTX = ssl.create_default_context()


# ---------------------------------------------------------------------------
# Raw HTTP helpers (Yahoo blocks caldav REPORT requests)
# ---------------------------------------------------------------------------


def _basic_auth(credentials: AppPasswordCredentials) -> str:
    return base64.b64encode(
        f"{credentials.username}:{credentials.app_password}".encode()
    ).decode()


def _propfind(url: str, auth: str, depth: str = "1") -> str:
    body = b"""<?xml version="1.0" encoding="utf-8"?>
<propfind xmlns="DAV:"><prop><getcontenttype/><resourcetype/><displayname/></prop></propfind>"""
    req = urllib.request.Request(url, data=body, method="PROPFIND")
    req.add_header("Authorization", f"Basic {auth}")
    req.add_header("Depth", depth)
    req.add_header("Content-Type", "application/xml; charset=utf-8")
    return urllib.request.urlopen(req, context=_SSL_CTX).read().decode()


def _http_get(url: str, auth: str) -> str:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {auth}")
    return urllib.request.urlopen(req, context=_SSL_CTX).read().decode()


def _parse_dt(val: str, tzid: str | None) -> datetime:
    fmt = "%Y%m%dT%H%M%S" if "T" in val else "%Y%m%d"
    dt = datetime.strptime(val, fmt)
    if tzid:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tzid))
        except Exception:
            dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ical_field(ical: str, name: str) -> str | None:
    m = re.search(rf"^{name}[^:\n]*:(.*)", ical, re.MULTILINE)
    return m.group(1).strip() if m else None


def _parse_ical_event(ical: str) -> CalendarEvent:
    m_start = re.search(r"^DTSTART(?:;TZID=([^:]+))?:(\d+(?:T\d+)?)", ical, re.MULTILINE)
    start = (
        _parse_dt(m_start.group(2), m_start.group(1))
        if m_start
        else datetime.min.replace(tzinfo=timezone.utc)
    )
    m_end = re.search(r"^DTEND(?:;TZID=([^:]+))?:(\d+(?:T\d+)?)", ical, re.MULTILINE)
    end = _parse_dt(m_end.group(2), m_end.group(1)) if m_end else start
    attendees = re.findall(r"^ATTENDEE[^:]*:mailto:(.+)", ical, re.MULTILINE)
    return CalendarEvent(
        uid=_ical_field(ical, "UID") or "",
        title=_ical_field(ical, "SUMMARY") or "(no title)",
        description=_ical_field(ical, "DESCRIPTION"),
        start=start,
        end=end,
        location=_ical_field(ical, "LOCATION"),
        attendees=[a.strip() for a in attendees],
        status=_ical_field(ical, "STATUS"),
    )


# ---------------------------------------------------------------------------
# caldav helpers (used by write operations: get_event, create_event, delete_event)
# ---------------------------------------------------------------------------


def _parse_event(component: object) -> CalendarEvent:
    vevent = component.vobject_instance.vevent  # type: ignore

    def get(attr: str) -> Optional[str]:
        try:
            val = getattr(vevent, attr)
            return str(val.value) if hasattr(val, "value") else str(val)
        except AttributeError:
            return None

    def get_dt(attr: str) -> Optional[datetime]:
        try:
            val = getattr(vevent, attr).value
            if isinstance(val, datetime):
                return val
            return datetime(val.year, val.month, val.day)
        except AttributeError:
            return None

    attendees: list[str] = []
    try:
        for att in vevent.attendee_list:
            attendees.append(str(att.value).replace("mailto:", ""))
    except AttributeError:
        pass

    start = get_dt("dtstart") or datetime.min
    end = get_dt("dtend") or start
    return CalendarEvent(
        uid=get("uid") or "",
        title=get("summary") or "(no title)",
        description=get("description"),
        start=start,
        end=end,
        location=get("location"),
        attendees=attendees,
        status=get("status"),
    )


class CalendarClient:
    def __init__(self, credentials: AppPasswordCredentials) -> None:
        self._credentials = credentials
        self._dav: Optional[caldav.DAVClient] = None
        self._auth = _basic_auth(credentials)

    @property
    def _local_part(self) -> str:
        return self._credentials.username.split("@")[0]

    @property
    def _client(self) -> caldav.DAVClient:
        if self._dav is None:
            # Yahoo CalDAV uses just the local part of the email (before @) in the path
            url = f"{CALDAV_BASE}/dav/{self._local_part}/Calendar/"
            self._dav = caldav.DAVClient(
                url=url,
                username=self._credentials.username,
                password=self._credentials.app_password,
            )
        return self._dav

    def list_calendars(self) -> list[Calendar]:
        """List calendars via raw PROPFIND — Yahoo blocks caldav REPORT requests."""
        try:
            root = f"{CALDAV_BASE}/dav/{self._local_part}/Calendar/"
            xml = _propfind(root, self._auth, depth="1")
        except Exception as exc:
            raise CalendarError(f"Failed to list calendars: {exc}") from exc

        root_path = f"/dav/{self._local_part}/Calendar/"
        hrefs = re.findall(r"<[^>]*href>(/dav/[^<]+/)</[^>]*href>", xml)
        results: list[Calendar] = []
        for href in hrefs:
            if href == root_path:
                continue
            name = href.rstrip("/").split("/")[-1]
            results.append(Calendar(name=name, url=f"{CALDAV_BASE}{href}", color=None))
        return results

    def list_events(self, calendar_url: str, start: datetime, end: datetime) -> list[CalendarEvent]:
        """List events via raw PROPFIND + GET — Yahoo blocks caldav date_search (REPORT)."""
        try:
            xml = _propfind(calendar_url, self._auth, depth="1")
        except Exception as exc:
            raise CalendarError(f"Failed to fetch calendar: {exc}") from exc

        parsed = urlparse(calendar_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        hrefs = re.findall(r"<[^>]*href>(/[^<]+\.ics)</[^>]*href>", xml)

        start_utc = (
            start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        ).astimezone(timezone.utc)
        end_utc = (
            end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        ).astimezone(timezone.utc)

        events: list[CalendarEvent] = []
        for href in hrefs:
            try:
                ical = _http_get(f"{base}{href}", self._auth)
                event = _parse_ical_event(ical)
                if start_utc <= event.start < end_utc:
                    events.append(event)
            except Exception:
                continue
        return events

    def get_event(self, calendar_url: str, event_uid: str) -> CalendarEvent:
        try:
            cal = self._client.calendar(url=calendar_url)
            component = cal.event_by_uid(event_uid)
        except caldav_error.NotFoundError as exc:
            raise NotFoundError(f"Event uid='{event_uid}' not found") from exc
        except Exception as exc:
            raise CalendarError(f"Failed to get event: {exc}") from exc
        return _parse_event(component)

    def create_event(self, calendar_url: str, event: CalendarEvent) -> CalendarEvent:
        ical = _event_to_ical(event)
        try:
            cal = self._client.calendar(url=calendar_url)
            component = cal.save_event(ical)
        except Exception as exc:
            raise CalendarError(f"Failed to create event: {exc}") from exc
        return _parse_event(component)

    def delete_event(self, calendar_url: str, event_uid: str) -> None:
        try:
            cal = self._client.calendar(url=calendar_url)
            component = cal.event_by_uid(event_uid)
            component.delete()
        except caldav_error.NotFoundError as exc:
            raise NotFoundError(f"Event uid='{event_uid}' not found") from exc
        except Exception as exc:
            raise CalendarError(f"Failed to delete event: {exc}") from exc


def _event_to_ical(event: CalendarEvent) -> str:
    def fmt_dt(dt: datetime) -> str:
        return dt.strftime("%Y%m%dT%H%M%SZ")

    attendee_lines = "\n".join(f"ATTENDEE:mailto:{a}" for a in event.attendees)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//yahoo-mail-sdk//EN",
        "BEGIN:VEVENT",
        f"UID:{event.uid}",
        f"SUMMARY:{event.title}",
        f"DTSTART:{fmt_dt(event.start)}",
        f"DTEND:{fmt_dt(event.end)}",
    ]
    if event.description:
        lines.append(f"DESCRIPTION:{event.description}")
    if event.location:
        lines.append(f"LOCATION:{event.location}")
    if event.status:
        lines.append(f"STATUS:{event.status}")
    if attendee_lines:
        lines.append(attendee_lines)
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines)
