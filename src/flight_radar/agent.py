"""One check: read the Google Flights alerts, store the history and decide what to notify. Runs and exits (systemd)."""
import logging

from flight_radar import notify, source, store
from flight_radar.source import Offer

log = logging.getLogger("flight_radar")


def _money(v: float, currency: str) -> str:
    return f"{v:,.0f} {currency.upper()}"


def is_drop(new: float, previous: float | None, cfg: dict) -> bool:
    """First time (no history) or a drop of at least min_drop_pct below the lowest price seen."""
    cap = cfg.get("max_price_per_person")
    if cap is not None and new > cap:
        return False
    if previous is None:
        return True
    return new <= previous * (1 - cfg["min_drop_pct"] / 100)


def message(o: Offer, previous: float | None, cfg: dict) -> str:
    c, n = cfg["currency"], cfg["passengers"]
    head = (f"✈️ First tracked price {o.origin} → {o.destination}" if previous is None else
            f"📉 Price drop {o.origin} → {o.destination}: {_money(previous, c)} → {_money(o.price, c)} "
            f"(-{(1 - o.price / previous) * 100:.0f} %)")
    dates = o.outbound.strftime("%a %d %b %Y") + (f" → {o.inbound.strftime('%a %d %b %Y')}" if o.inbound else "")
    return (f"{head}\n{dates} · Google Flights alert\n"
            f"{_money(o.price, c)} per person · {_money(o.price * n, c)} for {n}\n{o.link}")


def check(cfg: dict, con, read=source.read, send=notify.telegram) -> list[str]:
    """Read new alerts, store them and notify drops. Returns the notifications."""
    try:
        offers = [o for o in read(cfg) if not store.seen(con, o.msg_id)]
    except source.SourceError as e:
        log.error("%s", e)
        return []
    sent = []
    for origin in cfg["origins"]:
        for destination in cfg["destinations"]:
            route = sorted((o for o in offers if (o.origin, o.destination) == (origin, destination)),
                           key=lambda o: o.price)
            if not route:
                log.info("%s→%s: no new alerts", origin, destination)
                continue
            previous = store.lowest_before(con, origin, destination)
            store.save(con, route, cfg["currency"])
            best = route[0]
            log.info("%s→%s: best %s (previous low %s), %d alert(s)", origin, destination, best.price, previous,
                     len(route))
            if is_drop(best.price, previous, cfg):
                text = message(best, previous, cfg)
                if not send(text):
                    log.error("Telegram notification failed: %s", notify.last_error)
                sent.append(text)
    return sent
