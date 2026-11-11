"""Prices from Google Flights price-tracking emails, read over IMAP in READ-ONLY mode (never marks, moves or deletes).

No API and no scraping: you turn on price tracking in Google Flights for each route (with the trip's dates and
passengers) and Google emails you when the price changes. This module reads those emails.

PROVISIONAL: the email format is undocumented. The parser finds the route by city name, the price in MXN and the
Google Flights link; it should be tuned against a real alert (.eml).
"""
import datetime as dt
import email
import html
import imaplib
import re
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import Message

from flight_radar.config import env

SENDER = "google.com"          # e.g. noreply-travel@google.com; content is filtered too
PRICE = re.compile(r"(?:MX\$|MXN\s?\$?|\$)\s?(\d{1,3}(?:[,.]\d{3})+|\d{4,})(?:\s?MXN)?")
LINK = re.compile(r"https://www\.google\.com/travel/flights[^\s\"'<>]*")
TRIP_WORDS = ("flight", "vuelo", "trip", "viaje")  # alerts may arrive in English or Spanish


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Offer:
    origin: str
    destination: str
    outbound: dt.date
    inbound: dt.date | None
    price: float          # per person
    airline: str
    stops: int | None
    link: str
    msg_id: str = ""


def _text(msg: Message) -> tuple[str, str]:
    """(readable text, raw HTML). Readable text is text/plain if present, otherwise the HTML without tags."""
    parts = {}
    for part in msg.walk() if msg.is_multipart() else [msg]:
        kind = part.get_content_type()
        if kind in ("text/plain", "text/html") and kind not in parts:
            payload = part.get_payload(decode=True) or b""
            parts[kind] = payload.decode(part.get_content_charset() or "utf-8", "replace")
    raw = parts.get("text/html", "")
    plain = parts.get("text/plain") or html.unescape(re.sub(r"<[^>]+>", " ", re.sub(
        r"<(style|script)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)))
    return re.sub(r"[ \t\xa0]+", " ", plain), raw


def _fold(s: str) -> str:
    return s.lower().translate(str.maketrans("áéíóúü", "aeiouu"))


def _price(m: re.Match) -> float:
    return float(re.sub(r"[,.]", "", m.group(1)))


def parse_message(msg: Message, cfg: dict) -> list[Offer]:
    """Offers in one alert email: one per configured route that appears in it. Other emails are ignored."""
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    readable, raw = _text(msg)
    text = _fold(subject + "\n" + readable)
    if not any(w in text for w in TRIP_WORDS):
        return []
    cities = cfg["cities"]
    mentioned = lambda code: any(_fold(n) in text for n in cities[code]) or code.lower() in text.split()
    prices = [_price(m) for m in PRICE.finditer(text)]
    if not prices:
        return []
    # When unsure (old price struck through + new price), keep the lowest
    price = min(prices) / (cfg["passengers"] if cfg["email_price"] == "total" else 1)
    link = next(iter(LINK.findall(raw + readable)), "https://www.google.com/travel/flights")
    d = cfg["dates"]
    return [Offer(o, t, d["outbound"], d.get("return"), price, "", None, html.unescape(link),
                  msg.get("Message-ID", "").strip())
            for o in cfg["origins"] for t in cfg["destinations"] if mentioned(o) and mentioned(t)]


def read(cfg: dict, days: int = 7) -> list[Offer]:
    """Offers from the alerts of the last `days` days. Needs IMAP_USER and IMAP_PASSWORD (an app password)."""
    user, password = env("IMAP_USER"), env("IMAP_PASSWORD")
    if not user or not password:
        raise SourceError("IMAP_USER / IMAP_PASSWORD missing in .env")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%d-%b-%Y")
    offers: list[Offer] = []
    try:
        with imaplib.IMAP4_SSL(env("IMAP_HOST", "imap.gmail.com")) as box:
            box.login(user, password)
            box.select(env("IMAP_FOLDER", "INBOX"), readonly=True)
            _, data = box.search(None, f'(FROM "{SENDER}" SINCE {since})')
            for num in data[0].split():
                _, msg_data = box.fetch(num, "(BODY.PEEK[])")  # PEEK: does not mark as read
                offers.extend(parse_message(email.message_from_bytes(msg_data[0][1]), cfg))
    except (imaplib.IMAP4.error, OSError) as e:
        raise SourceError(f"IMAP failed ({type(e).__name__})") from None
    return offers
