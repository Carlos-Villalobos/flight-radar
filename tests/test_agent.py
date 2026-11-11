import datetime as dt
from email.message import EmailMessage

import pytest

from flight_radar import agent, source, store
from flight_radar.source import Offer

CFG = {"origins": ["GDL", "QRO"], "destinations": ["MAD"], "passengers": 4, "currency": "mxn",
       "dates": {"outbound": dt.date(2027, 6, 11), "return": dt.date(2027, 6, 27)},
       "cities": {"GDL": ["Guadalajara"], "QRO": ["Querétaro", "Queretaro"], "MAD": ["Madrid"]},
       "email_price": "total", "max_price_per_person": None, "min_drop_pct": 3}


def offer(price, origin="GDL"):
    return Offer(origin, "MAD", dt.date(2027, 6, 11), dt.date(2027, 6, 27), price, "", None,
                 "https://www.google.com/travel/flights", f"<{origin}-{price}@google.com>")


def mail(subject, body_html, msg_id="<1@google.com>"):
    m = EmailMessage()
    m["Subject"], m["From"], m["Message-ID"] = subject, "Google Flights <noreply-travel@google.com>", msg_id
    m.set_content(body_html, subtype="html")
    return m


@pytest.fixture
def con(tmp_path):
    return store.connect(tmp_path / "p.sqlite")


def test_is_drop():
    assert agent.is_drop(20000, None, CFG)              # first time
    assert agent.is_drop(19000, 20000, CFG)             # -5 %
    assert not agent.is_drop(19800, 20000, CFG)         # -1 %: noise
    assert not agent.is_drop(21000, 20000, CFG)
    assert not agent.is_drop(20000, None, {**CFG, "max_price_per_person": 15000})


def test_parse_spanish_alert():
    m = mail("Bajó el precio de tu vuelo a Madrid",
             '<p>Guadalajara a Madrid</p><p>vie, 11 jun – dom, 27 jun · 4 pasajeros</p>'
             '<p><s>MX$120,000</s> <b>MX$100,000</b></p>'
             '<a href="https://www.google.com/travel/flights?tfs=abc&amp;hl=es">Ver vuelos</a>')
    [o] = source.parse_message(m, CFG)
    assert (o.origin, o.destination, o.price) == ("GDL", "MAD", 25000)       # total ÷ 4, the lowest
    assert o.link == "https://www.google.com/travel/flights?tfs=abc&hl=es"
    assert o.msg_id == "<1@google.com>" and o.outbound == dt.date(2027, 6, 11)


def test_parse_english_alert_per_person():
    m = mail("Prices dropped for your trip", "<p>Queretaro to Madrid</p><p>$27,500 MXN</p>")
    [o] = source.parse_message(m, {**CFG, "email_price": "per_person"})
    assert o.origin == "QRO" and o.price == 27500


def test_parse_ignores_other_emails():
    assert source.parse_message(mail("Your receipt", "<p>Total $1,500 MXN</p>"), CFG) == []
    assert source.parse_message(mail("Flight to Lima", "<p>Guadalajara to Lima MX$9,000</p>"), CFG) == []


def test_check_stores_history_and_notifies_only_drops(con):
    sent = []
    send = lambda t: sent.append(t) or True
    alerts = [offer(25000, "GDL"), offer(30000, "QRO")]
    assert len(agent.check(CFG, con, lambda cfg: alerts, send)) == 2         # starting prices
    alerts += [offer(25100, "GDL"), offer(27000, "QRO")]                      # old ones are re-read
    notes = agent.check(CFG, con, lambda cfg: alerts, send)
    assert len(notes) == 1 and "QRO → MAD" in notes[0] and "-10 %" in notes[0]
    assert "108,000 MXN for 4" in notes[0]
    assert con.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 4      # no duplicates
    assert store.lowest_before(con, "QRO", "MAD") == 27000


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
