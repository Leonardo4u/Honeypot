import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import requests


_LOGGER = logging.getLogger("api_error_monitor")
_DEBOUNCE_SECONDS = 60
_LAST_SENT_AT = {}
_LOCK = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_text(value: Optional[str]) -> str:
    text = str(value or "")

    # Remove segredos conhecidos vindos do ambiente.
    for env_name, env_value in os.environ.items():
        if not env_value or len(env_value) < 8:
            continue
        upper_name = env_name.upper()
        if any(k in upper_name for k in ("TOKEN", "KEY", "SECRET", "PASSWORD")):
            text = text.replace(env_value, "***")

    # Máscaras defensivas para padrões comuns de segredo.
    text = re.sub(r"bot\d+:[A-Za-z0-9_-]{20,}", "***", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password)=([^&\s]+)", r"\1=***", text)
    text = re.sub(r"\b[a-f0-9]{32,}\b", "***", text, flags=re.IGNORECASE)

    # Evita quebrar markdown simples no Telegram.
    return text.replace("*", "")


def _sanitize_endpoint(endpoint: Optional[str]) -> str:
    raw = str(endpoint or "desconhecido").strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        split = urlsplit(raw)
        safe = f"{split.netloc}{split.path}".strip()
        return _sanitize_text(safe or "desconhecido")
    return _sanitize_text(raw)


def _debounce_key(error_type: str, endpoint: str, status_code: Optional[int], error_message: str) -> str:
    compact_msg = (error_message or "")[:160]
    return f"{error_type}|{endpoint}|{status_code}|{compact_msg}"


def _is_debounced(key: str, now_monotonic: float) -> bool:
    with _LOCK:
        previous = _LAST_SENT_AT.get(key)
        if previous is not None and (now_monotonic - previous) < _DEBOUNCE_SECONDS:
            return True
        _LAST_SENT_AT[key] = now_monotonic
        return False


def report_api_error(
    *,
    error_type: str,
    error_message: str,
    endpoint: Optional[str],
    status_code: Optional[int] = None,
    timestamp: Optional[str] = None,
) -> bool:
    """Reporta erro de API ao operador via Telegram Bot API, com debounce e sanitização."""
    safe_error_type = _sanitize_text(error_type or "unknown_error")
    safe_message = _sanitize_text(error_message or "sem detalhes")
    safe_endpoint = _sanitize_endpoint(endpoint)
    safe_status = "n/a" if status_code is None else str(status_code)
    safe_timestamp = _sanitize_text(timestamp or _utc_now_iso())

    key = _debounce_key(safe_error_type, safe_endpoint, status_code, safe_message)
    if _is_debounced(key, time.monotonic()):
        _LOGGER.info(
            "api_error_alert_skipped_debounce endpoint=%s type=%s status=%s",
            safe_endpoint,
            safe_error_type,
            safe_status,
        )
        return False

    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("EDGE_API_ERROR_TELEGRAM_CHAT", "@leogg07")
    if not token or not chat_id:
        _LOGGER.error(
            "api_error_alert_send_failed endpoint=%s type=%s status=%s reason=missing_telegram_config",
            safe_endpoint,
            safe_error_type,
            safe_status,
        )
        return False

    telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"
    text = (
        "🚨 *Erro de API detectado*\n\n"
        f"📌 *Endpoint:* {safe_endpoint}\n"
        f"❌ *Erro:* {safe_error_type}: {safe_message}\n"
        f"🔢 *Status:* {safe_status}\n"
        f"🕐 *Horário:* {safe_timestamp}\n\n"
        "Verifique o sistema com urgência."
    )

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(telegram_url, json=payload, timeout=8)
        if response.status_code >= 400:
            body = _sanitize_text(response.text[:300])
            _LOGGER.error(
                "api_error_alert_send_failed endpoint=%s type=%s status=%s telegram_status=%s body=%s",
                safe_endpoint,
                safe_error_type,
                safe_status,
                response.status_code,
                body,
            )
            return False

        _LOGGER.info(
            "api_error_alert_sent endpoint=%s type=%s status=%s",
            safe_endpoint,
            safe_error_type,
            safe_status,
        )
        return True
    except Exception as exc:
        _LOGGER.error(
            "api_error_alert_send_failed endpoint=%s type=%s status=%s exception=%s",
            safe_endpoint,
            safe_error_type,
            safe_status,
            _sanitize_text(str(exc)),
        )
        return False
