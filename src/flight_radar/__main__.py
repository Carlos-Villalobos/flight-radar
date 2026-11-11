"""CLI: python -m flight_radar check | history | test-telegram"""
import argparse
import logging

from flight_radar import agent, notify, store
from flight_radar.config import db_path, load_config


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="flight_radar")
    p.add_argument("command", choices=["check", "history", "test-telegram"])
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if args.command == "test-telegram":
        ok = notify.telegram("✅ flight-radar: Telegram connection OK", silent=True)
        raise SystemExit(0 if ok else f"Telegram failed: {notify.last_error}")
    con = store.connect(db_path())
    if args.command == "check":
        sent = agent.check(cfg, con)
        print(f"Check finished: {len(sent)} notification(s)")
    else:
        for o in cfg["origins"]:
            for d in cfg["destinations"]:
                print(f"{o} → {d}")
                for ts, price in store.history(con, o, d):
                    print(f"  {ts}  {price:,.0f} {cfg['currency'].upper()}")


if __name__ == "__main__":
    main()
