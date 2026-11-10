"""Upcoming events from iCal (.ics) links: Google Calendar and Outlook both offer a secret iCal address.

Data: calendar.N.{title, start, end, all_day, when, location}
"""
import asyncio
from datetime import date, datetime, timedelta

import requests

from i18n import _, dates

name = "calendar"
settings = {"urls": [], "days": 7}
interval = 900

TIMEOUT = 15


def _local(dt):
    if isinstance(dt, datetime):
        return dt.astimezone() if dt.tzinfo else dt.astimezone()  # naive = local time
    return datetime(dt.year, dt.month, dt.day).astimezone()


def when(start: datetime, all_day: bool, today: date) -> str:
    d = start.date()
    if d == today:
        day = _("Today")
    elif d == today + timedelta(days=1):
        day = _("Tomorrow")
    else:
        day = f"{dates()['short'][d.weekday()]} {d.day}"
    return f"{day} · {_('all day')}" if all_day else f"{day} {start:%H:%M}"


def events_from(ics: bytes, start: datetime, end: datetime):
    import icalendar
    import recurring_ical_events
    cal = icalendar.Calendar.from_ical(ics)
    for ev in recurring_ical_events.of(cal).between(start, end):  # expands weekly meetings etc.
        s, e = ev.get("DTSTART").dt, (ev.get("DTEND").dt if ev.get("DTEND") else ev.get("DTSTART").dt)
        all_day = not isinstance(s, datetime)
        yield {"title": str(ev.get("SUMMARY", "")), "location": str(ev.get("LOCATION", "") or ""),
               "start": _local(s), "end": _local(e), "all_day": all_day}


def collect(cfg):
    urls = cfg.get("urls") or []
    if isinstance(urls, str):
        urls = [urls]
    now = datetime.now().astimezone()
    horizon = now + timedelta(days=int(cfg.get("days", 7)))
    out = []
    for url in urls:
        url = url.strip().replace("webcal://", "https://", 1)
        if not url.startswith("https://"):
            continue  # links carry private calendars: only encrypted connections
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        out.extend(e for e in events_from(r.content, now - timedelta(days=1), horizon) if e["end"] > now)
    out.sort(key=lambda e: e["start"])
    today = now.date()
    for e in out:
        e["when"] = when(e["start"], e["all_day"], today)
        e["start"], e["end"] = e["start"].isoformat(), e["end"].isoformat()
    return out


async def fetch(cfg):
    return await asyncio.to_thread(collect, cfg)
