"""Prices from Google Flights price-tracking emails, read over IMAP in READ-ONLY mode (never marks, moves or deletes).

No API and no scraping: you turn on price tracking in Google Flights for each route (with the trip's dates and
passengers) and Google emails you when the price changes. This module reads those emails.

Two kinds of alert are parsed (prices in EUR, per adult): "tracked flight" emails list "City to City / dates /
price (increased from old price)" blocks; "tracked route" emails list several date options with "GDL–MAD".
"""
import datetime as dt
import email
import html
import imaplib
import re
from dataclasses import dataclass
from email.message import Message
from email.utils import parsedate_to_datetime

from flight_radar.config import env

SENDER = "noreply-travel@google.com"
# "Fri, Jun 11 – Mon, Jun 21": one trip option per date range; the year is not in the email
DATES = re.compile(r"\w{3}, (\w{3} \d{1,2}) [–-] \w{3}, (\w{3} \d{1,2})")
CURRENCY = "EUR"                                   # the parser only reads € prices
PRICE = re.compile(r"€\s?([\d,]+)")
ROUTE = re.compile(r"([A-Z]{3})[–-]([A-Z]{3})")           # "GDL–MAD" in route emails
TO = re.compile(r"^\s*(?:from )?(.+?) to (.+?)[,.]?\s*$", re.M | re.I)  # "Guadalajara to Madrid"
ADULTS = re.compile(r"(\d+) adults?")
LINK = re.compile(r"https://www\.google\.com/travel/flights\?tfs=[^\s)>\]]+")


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


def _code(name: str, cfg: dict) -> str | None:
    """IATA code of a city name from the email, using `cities` in the config."""
    name = _fold(name)
    return next((c for c, names in cfg["cities"].items() if any(_fold(n) in name for n in names)), None)


def _date(text: str, sent: dt.date) -> dt.date:
    """'Jun 11' → the first Jun 11 on or after the email date."""
    d = dt.datetime.strptime(f"{text} {sent.year}", "%b %d %Y").date()
    return d if d >= sent else d.replace(year=d.year + 1)


def parse_message(msg: Message, cfg: dict) -> list[Offer]:
    """Every trip option (route + dates + price per person) in a Google Flights alert email."""
    text, _ = _text(msg)
    try:
        sent = parsedate_to_datetime(msg["Date"]).date()
    except (TypeError, ValueError):
        sent = dt.date.today()
    msg_id = msg.get("Message-ID", "").strip()
    starts = [m for m in DATES.finditer(text)]
    offers = []
    for i, m in enumerate(starts):
        block = text[m.end():starts[i + 1].start() if i + 1 < len(starts) else len(text)]
        before = text[:m.start()]
        price = PRICE.search(block)
        if not price:
            continue
        codes = ROUTE.search(block)
        if codes:
            origin, destination = codes.groups()
        else:
            to = list(TO.finditer(before))
            if not to:
                continue
            origin, destination = (_code(x, cfg) for x in to[-1].groups())
        if origin not in cfg["origins"] or destination not in cfg["destinations"]:
            continue
        adults = ADULTS.findall(before + block[:200])
        per_person = float(price.group(1).replace(",", "")) / int(adults[-1] if adults else 1)
        link = LINK.search(block)
        offers.append(Offer(origin, destination, _date(m.group(1), sent), _date(m.group(2), sent), per_person,
                            "", None, link.group(0) if link else "https://www.google.com/travel/flights", msg_id))
    return offers


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
            folder = env("IMAP_FOLDER", "INBOX").strip("\"'")
            box.select(f'"{folder}"', readonly=True)  # quoted: Gmail folder names have spaces
            _, data = box.search(None, f'(FROM "{SENDER}" SINCE {since})')
            for num in data[0].split():
                _, msg_data = box.fetch(num, "(BODY.PEEK[])")  # PEEK: does not mark as read
                offers.extend(parse_message(email.message_from_bytes(msg_data[0][1]), cfg))
    except (imaplib.IMAP4.error, OSError) as e:
        raise SourceError(f"IMAP failed ({type(e).__name__})") from None
    return offers
