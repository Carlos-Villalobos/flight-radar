"""Telegram notifications: one retry and a plain-language reason on failure, never logging the URL with the token.

Only SENDS (sendMessage). It never reads the bot (getUpdates), so it does not compete with any listener.
"""
import time

import requests

from flight_radar.config import env

LIMIT = 4000
last_error = ""


def _reason(e: Exception | None = None, r=None) -> str:
    if r is not None:
        if r.status_code == 429:
            return "Telegram rate-limited the bot"
        return f"Telegram {'server error' if r.status_code >= 500 else 'rejected the request'} (HTTP {r.status_code})"
    if isinstance(e, requests.Timeout):
        return "Telegram took too long to respond"
    if isinstance(e, requests.ConnectionError):
        return "could not connect to Telegram"
    return type(e).__name__ if e else "unknown reason"


def _send(payload: dict) -> bool:
    global last_error
    token = env("TELEGRAM_BOT_TOKEN")
    for attempt in range(2):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=60)
            if r.ok:
                return True
            last_error = _reason(r=r)
            if r.status_code < 500 and r.status_code != 429:
                return False
        except requests.RequestException as e:
            last_error = _reason(e)
        if not attempt:
            time.sleep(3)
    return False


def telegram(text: str, silent: bool = False) -> bool:
    global last_error
    if not env("TELEGRAM_BOT_TOKEN") or not env("TELEGRAM_CHAT_ID"):
        last_error = "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in .env"
        return False
    return all(_send({"chat_id": env("TELEGRAM_CHAT_ID"), "text": text[i:i + LIMIT],
                      "disable_web_page_preview": True, "disable_notification": silent})
               for i in range(0, len(text), LIMIT))
