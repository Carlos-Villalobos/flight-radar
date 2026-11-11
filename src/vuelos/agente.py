"""Una revisión: lee las alertas de Google Flights, guarda el histórico y decide qué avisar. Corre y termina (lo lanza systemd)."""
import logging

from vuelos import fuente, notify, store
from vuelos.fuente import Oferta

log = logging.getLogger("vuelos")


def _dinero(v: float, moneda: str) -> str:
    return f"{v:,.0f} {moneda.upper()}"


def es_bajada(nuevo: float, previo: float | None, cfg: dict) -> bool:
    """Primera vez (sin histórico) o una bajada de al menos bajada_minima_pct respecto al mínimo visto."""
    tope = cfg.get("precio_maximo_por_persona")
    if tope is not None and nuevo > tope:
        return False
    if previo is None:
        return True
    return nuevo <= previo * (1 - cfg["bajada_minima_pct"] / 100)


def mensaje(o: Oferta, previo: float | None, cfg: dict) -> str:
    m, n = cfg["moneda"], cfg["pasajeros"]
    cab = (f"✈️ Primer precio vigilado {o.origen} → {o.destino}" if previo is None else
           f"📉 Bajó el precio {o.origen} → {o.destino}: {_dinero(previo, m)} → {_dinero(o.precio, m)} "
           f"(-{(1 - o.precio / previo) * 100:.0f} %)")
    fechas = o.salida.strftime("%a %d %b %Y") + (f" → {o.regreso.strftime('%a %d %b %Y')}" if o.regreso else "")
    return (f"{cab}\n{fechas} · alerta de Google Flights\n"
            f"{_dinero(o.precio, m)} por persona · {_dinero(o.precio * n, m)} para {n}\n{o.enlace}")


def revisar(cfg: dict, con, leer=fuente.leer, avisar=notify.telegram) -> list[str]:
    """Lee las alertas nuevas, guarda el histórico y avisa de las bajadas. Devuelve los avisos."""
    try:
        ofertas = [o for o in leer(cfg) if not store.visto(con, o.msg_id)]
    except fuente.FuenteError as e:
        log.error("%s", e)
        return []
    avisos = []
    for origen in cfg["origenes"]:
        for destino in cfg["destinos"]:
            ruta = sorted((o for o in ofertas if (o.origen, o.destino) == (origen, destino)), key=lambda o: o.precio)
            if not ruta:
                log.info("%s→%s: sin alertas nuevas", origen, destino)
                continue
            previo = store.minimo_previo(con, origen, destino)
            store.guardar(con, ruta, cfg["moneda"])
            mejor = ruta[0]
            log.info("%s→%s: mejor %s (mínimo previo %s), %d alerta(s)", origen, destino, mejor.precio, previo,
                     len(ruta))
            if es_bajada(mejor.precio, previo, cfg):
                texto = mensaje(mejor, previo, cfg)
                if not avisar(texto):
                    log.error("No se pudo avisar por Telegram: %s", notify.ultimo_error)
                avisos.append(texto)
    return avisos
