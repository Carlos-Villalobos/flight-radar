"""Avisos por Telegram (mismo patrón que cita-previa: un reintento y el motivo en claro, sin la URL con el token).

Solo ENVÍA (sendMessage). Nunca lee el bot (getUpdates), así que no compite con ningún escuchador.
"""
import time

import requests

from vuelos.config import env

LIMITE = 4000
ultimo_error = ""


def _motivo(e: Exception | None = None, r=None) -> str:
    if r is not None:
        if r.status_code == 429:
            return "Telegram frenó los envíos por exceso de mensajes"
        return f"{'falla en los servidores de' if r.status_code >= 500 else 'rechazo de'} Telegram (HTTP {r.status_code})"
    if isinstance(e, requests.Timeout):
        return "Telegram tardó demasiado en responder"
    if isinstance(e, requests.ConnectionError):
        return "no había conexión con Telegram"
    return type(e).__name__ if e else "motivo desconocido"


def _enviar(payload: dict) -> bool:
    global ultimo_error
    token = env("TELEGRAM_BOT_TOKEN")
    for intento in range(2):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=60)
            if r.ok:
                return True
            ultimo_error = _motivo(r=r)
            if r.status_code < 500 and r.status_code != 429:
                return False
        except requests.RequestException as e:
            ultimo_error = _motivo(e)
        if not intento:
            time.sleep(3)
    return False


def telegram(text: str, silent: bool = False) -> bool:
    global ultimo_error
    if not env("TELEGRAM_BOT_TOKEN") or not env("TELEGRAM_CHAT_ID"):
        ultimo_error = "faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env"
        return False
    return all(_enviar({"chat_id": env("TELEGRAM_CHAT_ID"), "text": text[i:i + LIMITE],
                        "disable_web_page_preview": True, "disable_notification": silent})
               for i in range(0, len(text), LIMITE))
