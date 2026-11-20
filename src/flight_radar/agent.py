"""One check: read the Google Flights alerts, store the history and decide what to notify. Runs and exits (systemd)."""
import html
import logging

import requests

from flight_radar import notify, source, store
from flight_radar.source import Offer

log = logging.getLogger("flight_radar")


def _money(v: float, currency: str) -> str:
    return f"{v:,.0f} {currency.upper()}"


def rate(to: str | None) -> float | None:
    """Today's EUR → `to` rate (ECB, via frankfurter.dev, free and keyless). None when off or unreachable."""
    if not to:
        return None
    try:
        r = requests.get("https://api.frankfurter.dev/v1/latest", params={"base": source.CURRENCY, "symbols": to},
                         timeout=15)
        return float(r.json()["rates"][to.upper()])
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("No exchange rate for %s (%s): prices only in %s", to, type(e).__name__, source.CURRENCY)
        return None


def is_drop(new: float, previous: float | None, cfg: dict) -> bool:
    """First time (no history) or a drop of at least min_drop_pct below the lowest price seen."""
    cap = cfg.get("max_price_per_person")
    if cap is not None and new > cap:
        return False
    if previous is None:
        return True
    return new <= previous * (1 - cfg["min_drop_pct"] / 100)


def message(o: Offer, previous: float | None, cfg: dict, fx: float | None = None) -> str:
    c, n, to = source.CURRENCY, cfg["passengers"], cfg.get("convert_to")
    also = lambda v: f" (≈ {_money(v * fx, to)})" if fx else ""
    head = (f"✈️ New lowest price {o.origin} → {o.destination}" if previous is None else
            f"📉 Price drop {o.origin} → {o.destination}: {_money(previous, c)} → {_money(o.price, c)} "
            f"(-{(1 - o.price / previous) * 100:.0f} %)")
    dates = o.outbound.strftime("%a %d %b %Y") + (f" → {o.inbound.strftime('%a %d %b %Y')}" if o.inbound else "")
    return (f"{head}\n{dates} · Google Flights alert\n"
            f"{_money(o.price, c)}{also(o.price)} per person · {_money(o.price * n, c)}{also(o.price * n)} for {n}\n"
            + (f"1 {c} = {fx:.2f} {to.upper()} (ECB, today)\n" if fx else "")
            + f'<a href="{html.escape(o.link)}">Open in Google Flights</a>')


def check(cfg: dict, con, read=source.read, send=notify.telegram) -> list[str]:
    """Read new alerts, store them and notify drops. Returns the notifications.

    Same route and dates seen before → notify a drop of min_drop_pct. New dates → notify only if cheaper than
    anything seen on the route, so a "tracked route" email with many dates does not flood the chat.
    """
    try:
        offers = [o for o in read(cfg) if not store.seen(con, o.msg_id)]
    except source.SourceError as e:
        log.error("%s", e)
        return []
    best: dict[tuple, Offer] = {}
    for o in offers:
        key = (o.origin, o.destination, o.outbound, o.inbound)
        if key not in best or o.price < best[key].price:
            best[key] = o
    log.info("%d new alert offer(s), %d route/date option(s)", len(offers), len(best))
    sent, fx = [], ...
    for o in sorted(best.values(), key=lambda o: o.price):
        same_dates = store.lowest_before(con, o.origin, o.destination, o.outbound, o.inbound)
        route_low = store.lowest_before(con, o.origin, o.destination)
        if same_dates is not None:
            notify_it, previous = is_drop(o.price, same_dates, cfg), same_dates
        else:
            notify_it, previous = is_drop(o.price, None, cfg) and (route_low is None or o.price < route_low), None
        store.save(con, [o], source.CURRENCY)
        if notify_it:
            if fx is ...:
                fx = rate(cfg.get("convert_to"))      # fetched once, and only when there is something to send
            text = message(o, previous, cfg, fx)
            if not send(text):
                log.error("Telegram notification failed: %s", notify.last_error)
            sent.append(text)
    store.save(con, [o for o in offers if o not in best.values()], source.CURRENCY)  # keep every email as seen
    return sent
