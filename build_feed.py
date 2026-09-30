"""Build an RSS feed of the White House public schedule from Factba.se data.

Runs hourly via GitHub Actions and writes docs/feed.xml (served by GitHub Pages).
Standard library only.
"""
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timedelta
from email.utils import format_datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

SOURCE = "https://media-cdn.factba.se/rss/json/trump/calendar-full.json"
CALENDAR_PAGE = "https://rollcall.com/factbase/trump/calendar/"
OUT = "docs/feed.xml"
DAYS_BACK = 14
MAX_ITEMS = 150
NY = ZoneInfo("America/New_York")

# Routine entries that carry no news. Edit this list to taste.
NOISE = re.compile(
    r"Executive Time|Pool Call Time|\blid\b|\barrives\b|\bdeparts\b|"
    r"Policy Meeting|Intelligence Briefing|Signing Time|^TBD:",
    re.IGNORECASE,
)


def fetch():
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "wh-schedule-feed/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def event_time(e):
    t = e.get("time") or "00:00:00"
    return datetime.strptime(f"{e['date']} {t}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=NY)


def build(events):
    cutoff = (datetime.now(NY) - timedelta(days=DAYS_BACK)).date().isoformat()
    kept = []
    for e in events:
        details = (e.get("details") or "").strip()
        if not details or e.get("date", "") < cutoff:
            continue
        is_briefing = "Briefing" in (e.get("type") or "")
        if not is_briefing and NOISE.search(details):
            continue
        kept.append(e)
    kept.sort(key=event_time, reverse=True)
    kept = kept[:MAX_ITEMS]

    items = []
    for e in kept:
        when = event_time(e)
        details = e["details"].strip()
        prefix = "[Briefing] " if "Briefing" in (e.get("type") or "") else ""
        title = f"{prefix}{when:%a %b} {when.day} · {e.get('time_formatted') or ''} · {details}"
        link = e.get("url") or e.get("video_url") or f"{CALENDAR_PAGE}?date={e['date']}"
        guid = hashlib.sha1(f"{e['date']}|{e.get('time')}|{details}".encode()).hexdigest()
        desc_bits = [details]
        for label, key in (("Location", "location"), ("Coverage", "coverage"), ("Source", "type")):
            if e.get(key):
                desc_bits.append(f"{label}: {e[key]}")
        items.append(
            "<item>"
            f"<title>{escape(title)}</title>"
            f"<link>{escape(link)}</link>"
            f'<guid isPermaLink="false">{guid}</guid>'
            f"<pubDate>{format_datetime(when)}</pubDate>"
            f"<description>{escape('<br>'.join(escape(b) for b in desc_bits))}</description>"
            "</item>"
        )

    # Use the newest event time, not the clock, so the file only changes when the schedule does.
    now = format_datetime(event_time(kept[0])) if kept else format_datetime(datetime.now(NY))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>White House Schedule (via Factba.se)</title>"
        f"<link>{CALENDAR_PAGE}</link>"
        "<description>The President's public schedule and press briefings, routine entries removed. Data: Roll Call Factba.se.</description>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        "<ttl>60</ttl>"
        + "".join(items)
        + "</channel></rss>\n"
    )


if __name__ == "__main__":
    xml = build(fetch())
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Wrote {OUT} with {xml.count('<item>')} items")
