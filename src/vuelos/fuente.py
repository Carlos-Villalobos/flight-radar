"""Precios de las alertas de Google Flights leídas por IMAP en modo SOLO LECTURA (no marca, mueve ni borra correos).

Sin API ni scraping: tú creas en Google Flights el seguimiento de precio de cada ruta (con las fechas y los
pasajeros del viaje) y Google te manda un correo cuando el precio cambia. Este módulo lee esos correos.

PROVISIONAL: el formato del correo no está documentado. El parser busca la ruta por nombre de ciudad, el precio
en MXN y el enlace a Google Flights; hay que afinarlo con un correo real (.eml) en tests/correos/.
"""
import datetime as dt
import email
import html
import imaplib
import re
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import Message

from vuelos.config import env

REMITENTE = "google.com"          # p. ej. noreply-travel@google.com; se filtra además por el contenido
PRECIO = re.compile(r"(?:MX\$|MXN\s?\$?|\$)\s?(\d{1,3}(?:[,.]\d{3})+|\d{4,})(?:\s?MXN)?")
ENLACE = re.compile(r"https://www\.google\.com/travel/flights[^\s\"'<>]*")


class FuenteError(RuntimeError):
    pass


@dataclass(frozen=True)
class Oferta:
    origen: str
    destino: str
    salida: dt.date
    regreso: dt.date | None
    precio: float          # por persona
    aerolinea: str
    escalas: int | None
    enlace: str
    msg_id: str = ""


def _texto(msg: Message) -> tuple[str, str]:
    """(texto legible, HTML crudo). El texto es el text/plain si existe; si no, el HTML sin etiquetas."""
    partes = {}
    for part in msg.walk() if msg.is_multipart() else [msg]:
        tipo = part.get_content_type()
        if tipo in ("text/plain", "text/html") and tipo not in partes:
            payload = part.get_payload(decode=True) or b""
            partes[tipo] = payload.decode(part.get_content_charset() or "utf-8", "replace")
    crudo = partes.get("text/html", "")
    plano = partes.get("text/plain") or html.unescape(re.sub(r"<[^>]+>", " ", re.sub(
        r"<(style|script)[^>]*>.*?</\1>", " ", crudo, flags=re.S | re.I)))
    return re.sub(r"[ \t\xa0]+", " ", plano), crudo


def _sin_acentos(s: str) -> str:
    return s.lower().translate(str.maketrans("áéíóúü", "aeiouu"))


def _precio(m: re.Match) -> float:
    return float(re.sub(r"[,.]", "", m.group(1)))


def parse_message(msg: Message, cfg: dict) -> list[Oferta]:
    """Ofertas de un correo de alerta: una por ruta del config que aparezca en él. Ignora el resto de correos."""
    asunto = str(make_header(decode_header(msg.get("Subject", ""))))
    legible, crudo = _texto(msg)
    plano = _sin_acentos(asunto + "\n" + legible)
    if not any(p in plano for p in ("flight", "vuelo", "trip", "viaje")):
        return []
    ciudades = cfg["ciudades"]
    presentes = lambda c: any(_sin_acentos(n) in plano for n in ciudades[c]) or c.lower() in plano.split()
    precios = [_precio(m) for m in PRECIO.finditer(plano)]
    if not precios:
        return []
    # Ante la duda (precio anterior tachado + precio nuevo), se queda con el más bajo
    precio = min(precios) / (cfg["pasajeros"] if cfg["precio_del_correo"] == "total" else 1)
    enlace = next(iter(ENLACE.findall(crudo + legible)), "https://www.google.com/travel/flights")
    f = cfg["fechas"]
    return [Oferta(o, d, f["salida"], f.get("regreso"), precio, "", None, html.unescape(enlace),
                   msg.get("Message-ID", "").strip())
            for o in cfg["origenes"] for d in cfg["destinos"] if presentes(o) and presentes(d)]


def leer(cfg: dict, dias: int = 7) -> list[Oferta]:
    """Ofertas de las alertas de los últimos `dias` días. Requiere IMAP_USER e IMAP_PASSWORD (contraseña de app)."""
    user, password = env("IMAP_USER"), env("IMAP_PASSWORD")
    if not user or not password:
        raise FuenteError("Faltan IMAP_USER / IMAP_PASSWORD en .env")
    desde = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dias)).strftime("%d-%b-%Y")
    ofertas: list[Oferta] = []
    try:
        with imaplib.IMAP4_SSL(env("IMAP_HOST", "imap.gmail.com")) as box:
            box.login(user, password)
            box.select(env("IMAP_FOLDER", "INBOX"), readonly=True)
            _, data = box.search(None, f'(FROM "{REMITENTE}" SINCE {desde})')
            for num in data[0].split():
                _, msg_data = box.fetch(num, "(BODY.PEEK[])")  # PEEK: no marca como leído
                ofertas.extend(parse_message(email.message_from_bytes(msg_data[0][1]), cfg))
    except (imaplib.IMAP4.error, OSError) as e:
        raise FuenteError(f"IMAP falló ({type(e).__name__})") from None
    return ofertas
