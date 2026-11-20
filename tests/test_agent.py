import datetime as dt
from email.message import EmailMessage

import pytest

from flight_radar import agent, source, store
from flight_radar.source import Offer

CFG = {"origins": ["GDL", "QRO"], "destinations": ["MAD"], "passengers": 4,
       "dates": {"outbound": dt.date(2027, 6, 11), "return": dt.date(2027, 6, 27)},
       "cities": {"GDL": ["Guadalajara"], "QRO": ["Querétaro", "Queretaro"], "MAD": ["Madrid"]},
       "max_price_per_person": None, "min_drop_pct": 3}


def mail(body, msg_id="<1@google.com>", date="Thu, 12 Nov 2026 20:55:00 +0000"):
    m = EmailMessage()
    m["Subject"], m["From"], m["Message-ID"], m["Date"] = "Google Flights", "noreply-travel@google.com", msg_id, date
    m.set_content(body)
    return m


# Trimmed from real alerts (Nov 2026)
FLIGHT = """Hello,
There's been a price change on the following destinations and dates:
Guadalajara to Madrid
Fri, Jun 11 – Mon, Jun 21
Round trip · 1 adult
€1,137 (increased from €884)
https://www.google.com/travel/flights?tfs=AAA&curr=EUR
Santiago de Querétaro to Madrid
Fri, Jul 9 – Mon, Jul 26
Round trip · 2 adults
€2,008 (increased from €1,774)
https://www.google.com/travel/flights?tfs=BBB&curr=EUR
Prices updated November 12, 2026 at 20:55 GMT
"""
ROUTE = """Hello,
We've found the best prices available for 1-week trips in January, from
Guadalajara to Madrid.
Mon, Jan 18 - Sun, Jan 24
 From €816
Aeromexico · Nonstop · GDL–MAD · 11 hr
View
(https://www.google.com/travel/flights?tfs=CCC)
Mon, Jan 25 - Wed, Feb 3
 From €744
United · 2 stops · GDL–MAD · 21 hr
View
(https://www.google.com/travel/flights?tfs=DDD)
Prices are currently typical for January
€744 is typical
"""


@pytest.fixture
def con(tmp_path):
    return store.connect(tmp_path / "p.sqlite")


def test_is_drop():
    assert agent.is_drop(20000, None, CFG)              # first time
    assert agent.is_drop(19000, 20000, CFG)             # -5 %
    assert not agent.is_drop(19800, 20000, CFG)         # -1 %: noise
    assert not agent.is_drop(21000, 20000, CFG)
    assert not agent.is_drop(20000, None, {**CFG, "max_price_per_person": 15000})


def test_parse_tracked_flight_email():
    gdl, qro = source.parse_message(mail(FLIGHT), CFG)
    assert (gdl.origin, gdl.price, gdl.outbound, gdl.inbound) == ("GDL", 1137, dt.date(2027, 6, 11), dt.date(2027, 6, 21))
    assert gdl.link == "https://www.google.com/travel/flights?tfs=AAA&curr=EUR" and gdl.msg_id == "<1@google.com>"
    assert (qro.origin, qro.price, qro.outbound) == ("QRO", 1004, dt.date(2027, 7, 9))   # 2 adults → per person


def test_parse_tracked_route_email():
    a, b = source.parse_message(mail(ROUTE), CFG)
    assert [(o.origin, o.destination, o.price) for o in (a, b)] == [("GDL", "MAD", 816), ("GDL", "MAD", 744)]
    assert b.outbound == dt.date(2027, 1, 25) and b.inbound == dt.date(2027, 2, 3)
    assert b.link.endswith("tfs=DDD")


def test_parse_ignores_other_routes():
    assert source.parse_message(mail(FLIGHT.replace("Madrid", "Lima")), CFG) == []


def offer_on(price, origin="GDL", day=11, msg="a"):
    return Offer(origin, "MAD", dt.date(2027, 6, day), dt.date(2027, 6, 21), price, "", None, "link", f"<{msg}>")


def test_check_compares_same_dates_and_only_cheaper_new_dates(con):
    send = lambda t: True
    first = [offer_on(1000, day=11, msg="1"), offer_on(1100, day=12, msg="1"), offer_on(900, "QRO", msg="1")]
    notes = agent.check(CFG, con, lambda cfg: first, send)
    assert len(notes) == 2                                       # cheapest date per route, not every date
    later = first + [offer_on(950, day=11, msg="2"),             # same dates, -5 % → drop
                     offer_on(990, day=13, msg="2"),             # new date but not below route low (950)
                     offer_on(890, "QRO", msg="2")]              # -1 %: noise
    notes = agent.check(CFG, con, lambda cfg: later, send)
    assert len(notes) == 1 and "1,000 EUR → 950 EUR" in notes[0] and "3,800 EUR for 4" in notes[0]
    assert con.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 6         # old emails not re-saved


def test_imap_error_does_not_crash(con):
    def read(cfg):
        raise source.SourceError("IMAP failed")
    assert agent.check(CFG, con, read, lambda t: True) == []


def test_read_without_credentials(monkeypatch):
    monkeypatch.delenv("IMAP_USER", raising=False)
    with pytest.raises(source.SourceError):
        source.read(CFG)


def test_example_config_loads():
    from flight_radar.config import EXAMPLE_FILE, load_config
    cfg = load_config(EXAMPLE_FILE)
    assert cfg["origins"] and cfg["destinations"] and cfg["passengers"] >= 1
    assert isinstance(cfg["dates"]["outbound"], dt.date)
    assert all(code in cfg["cities"] for code in cfg["origins"] + cfg["destinations"])
