"""Price history in SQLite: one row per offer seen in each alert email."""
import datetime as dt
import sqlite3
from pathlib import Path

from flight_radar.source import Offer

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    seen_at     TEXT NOT NULL,      -- ISO UTC of the check
    origin      TEXT NOT NULL,
    destination TEXT NOT NULL,
    outbound    TEXT NOT NULL,
    inbound     TEXT,
    price       REAL NOT NULL,      -- per person
    currency    TEXT NOT NULL,
    airline     TEXT,
    stops       INTEGER,
    link        TEXT,
    msg_id      TEXT                -- Message-ID of the alert email
);
CREATE INDEX IF NOT EXISTS ix_route ON prices (origin, destination, seen_at);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def seen(con, msg_id: str) -> bool:
    """Was this email already processed? (each check re-reads the last few days)."""
    return bool(msg_id) and con.execute("SELECT 1 FROM prices WHERE msg_id=? LIMIT 1", (msg_id,)).fetchone() is not None


def lowest_before(con, origin: str, destination: str) -> float | None:
    """Lowest per-person price seen before on this route."""
    (v,) = con.execute("SELECT MIN(price) FROM prices WHERE origin=? AND destination=?",
                       (origin, destination)).fetchone()
    return v


def save(con, offers: list[Offer], currency: str, now: dt.datetime | None = None) -> None:
    ts = (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds")
    con.executemany(
        "INSERT INTO prices VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(ts, o.origin, o.destination, o.outbound.isoformat(), o.inbound.isoformat() if o.inbound else None,
          o.price, currency, o.airline, o.stops, o.link, o.msg_id) for o in offers])
    con.commit()


def history(con, origin: str, destination: str, n: int = 10) -> list[tuple[str, float]]:
    """Best price per check, newest first."""
    return con.execute("SELECT seen_at, MIN(price) FROM prices WHERE origin=? AND destination=? "
                       "GROUP BY seen_at ORDER BY seen_at DESC LIMIT ?", (origin, destination, n)).fetchall()
