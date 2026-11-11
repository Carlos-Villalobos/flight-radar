"""Histórico de precios en SQLite: una fila por oferta vista en cada revisión."""
import datetime as dt
import sqlite3
from pathlib import Path

from vuelos.fuente import Oferta

ESQUEMA = """
CREATE TABLE IF NOT EXISTS precios (
    visto_en   TEXT NOT NULL,      -- ISO UTC de la revisión
    origen     TEXT NOT NULL,
    destino    TEXT NOT NULL,
    salida     TEXT NOT NULL,
    regreso    TEXT,
    precio     REAL NOT NULL,      -- por persona
    moneda     TEXT NOT NULL,
    aerolinea  TEXT,
    escalas    INTEGER,
    enlace     TEXT,
    msg_id     TEXT       -- Message-ID del correo de alerta
);
CREATE INDEX IF NOT EXISTS ix_ruta ON precios (origen, destino, visto_en);
"""


def conectar(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(ESQUEMA)
    if "msg_id" not in [c[1] for c in con.execute("PRAGMA table_info(precios)")]:  # bases de la versión anterior
        con.execute("ALTER TABLE precios ADD COLUMN msg_id TEXT")
    return con


def visto(con, msg_id: str) -> bool:
    """¿Ya se procesó este correo? (cada revisión relee los últimos días)."""
    return bool(msg_id) and con.execute("SELECT 1 FROM precios WHERE msg_id=? LIMIT 1", (msg_id,)).fetchone() is not None


def minimo_previo(con, origen: str, destino: str) -> float | None:
    """Mejor precio por persona visto antes en esta ruta ."""
    (v,) = con.execute("SELECT MIN(precio) FROM precios WHERE origen=? AND destino=?", (origen, destino)).fetchone()
    return v


def guardar(con, ofertas: list[Oferta], moneda: str, ahora: dt.datetime | None = None) -> None:
    ts = (ahora or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds")
    con.executemany(
        "INSERT INTO precios VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(ts, o.origen, o.destino, o.salida.isoformat(), o.regreso.isoformat() if o.regreso else None,
          o.precio, moneda, o.aerolinea, o.escalas, o.enlace, o.msg_id) for o in ofertas])
    con.commit()


def historial(con, origen: str, destino: str, n: int = 10) -> list[tuple[str, float]]:
    """Mejor precio por revisión, de la más reciente a la más antigua."""
    return con.execute("SELECT visto_en, MIN(precio) FROM precios WHERE origen=? AND destino=? "
                       "GROUP BY visto_en ORDER BY visto_en DESC LIMIT ?", (origen, destino, n)).fetchall()
