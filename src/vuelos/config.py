"""Rutas, variables de entorno y configuración del viaje. Los secretos viven en .env (nunca en git)."""
import datetime as dt
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

CONFIG_FILE = ROOT / "config" / "viaje.yaml"


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def db_path() -> Path:
    return Path(env("VUELOS_DATA", str(ROOT / "data"))) / "precios.sqlite"


def _fecha(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


def load_config(path: Path = CONFIG_FILE) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg["fechas"] = {k: _fecha(v) for k, v in cfg["fechas"].items() if v}
    cfg.setdefault("ida_y_vuelta", True)
    cfg.setdefault("pasajeros", 1)
    cfg.setdefault("moneda", "mxn")
    cfg.setdefault("bajada_minima_pct", 3)
    cfg.setdefault("precio_del_correo", "total")
    cfg.setdefault("ciudades", {})
    for codigo in cfg["origenes"] + cfg["destinos"]:
        cfg["ciudades"].setdefault(codigo, [codigo])
    cfg.setdefault("precio_maximo_por_persona", None)
    return cfg
