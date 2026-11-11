"""Paths, environment variables and trip configuration. Secrets live in .env (never in git)."""
import datetime as dt
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Your own trip goes in config/trip.yaml (git-ignored); the example is used when it does not exist
CONFIG_FILE = ROOT / "config" / "trip.yaml"
EXAMPLE_FILE = ROOT / "config" / "trip.example.yaml"


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def db_path() -> Path:
    return Path(env("FLIGHT_RADAR_DATA", str(ROOT / "data"))) / "prices.sqlite"


def _date(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


def load_config(path: Path | None = None) -> dict:
    path = path or (CONFIG_FILE if CONFIG_FILE.exists() else EXAMPLE_FILE)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg["dates"] = {k: _date(v) for k, v in cfg["dates"].items() if v}
    cfg.setdefault("passengers", 1)
    cfg.setdefault("currency", "mxn")
    cfg.setdefault("min_drop_pct", 3)
    cfg.setdefault("max_price_per_person", None)
    cfg.setdefault("email_price", "total")
    cfg.setdefault("cities", {})
    for code in cfg["origins"] + cfg["destinations"]:
        cfg["cities"].setdefault(code, [code])
    return cfg
