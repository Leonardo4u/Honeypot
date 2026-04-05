import time
from typing import Any, Dict, Optional

import requests
from services.api_error_monitor import report_api_error


def _classificar_http_error(status_code: Optional[int]) -> str:
    if status_code == 429:
        return "rate_limit"
    if status_code in (401, 403):
        return "auth_failure"
    if status_code is not None and 400 <= status_code <= 599:
        return "http_error"
    return "unknown_error"


def _reportar_erro_api(
    *,
    source_name: str,
    status_code: Optional[int],
    error_type: str,
    error_message: str,
) -> None:
    report_api_error(
        error_type=error_type,
        error_message=error_message,
        endpoint=source_name,
        status_code=status_code,
    )


def request_with_retry(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 10,
    attempts: int = 3,
    backoff_seconds: float = 0.8,
    source_name: str = "provider",
) -> Dict[str, Any]:
    """Execute a GET request with bounded retry and categorized status."""
    attempts = max(1, int(attempts))
    last_error: Optional[str] = None

    for attempt_idx in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
            status_code = response.status_code

            if status_code == 429 or 500 <= status_code <= 599:
                if attempt_idx < attempts:
                    time.sleep(backoff_seconds * attempt_idx)
                    continue
                _reportar_erro_api(
                    source_name=source_name,
                    status_code=status_code,
                    error_type=_classificar_http_error(status_code),
                    error_message=f"http_{status_code}",
                )
                return {
                    "ok": False,
                    "status": "http_error",
                    "status_code": status_code,
                    "attempts_used": attempt_idx,
                    "data": None,
                    "error": f"http_{status_code}",
                    "source": source_name,
                }

            if status_code >= 400:
                _reportar_erro_api(
                    source_name=source_name,
                    status_code=status_code,
                    error_type=_classificar_http_error(status_code),
                    error_message=f"http_{status_code}",
                )
                return {
                    "ok": False,
                    "status": "http_error",
                    "status_code": status_code,
                    "attempts_used": attempt_idx,
                    "data": None,
                    "error": f"http_{status_code}",
                    "source": source_name,
                }

            parsed = response.json()
            if parsed is None or (isinstance(parsed, (list, dict)) and len(parsed) == 0):
                _reportar_erro_api(
                    source_name=source_name,
                    status_code=status_code,
                    error_type="malformed_response",
                    error_message="empty_payload",
                )
                return {
                    "ok": False,
                    "status": "empty_payload",
                    "status_code": status_code,
                    "attempts_used": attempt_idx,
                    "data": parsed,
                    "error": "empty_payload",
                    "source": source_name,
                }

            return {
                "ok": True,
                "status": "ok",
                "status_code": status_code,
                "attempts_used": attempt_idx,
                "data": parsed,
                "error": None,
                "source": source_name,
            }
        except ValueError as exc:
            _reportar_erro_api(
                source_name=source_name,
                status_code=getattr(response, "status_code", None),
                error_type="malformed_response",
                error_message=str(exc),
            )
            return {
                "ok": False,
                "status": "unknown_error",
                "status_code": getattr(response, "status_code", None),
                "attempts_used": attempt_idx,
                "data": None,
                "error": str(exc),
                "source": source_name,
            }

        except requests.Timeout as exc:
            last_error = str(exc)
            if attempt_idx < attempts:
                time.sleep(backoff_seconds * attempt_idx)
                continue
            _reportar_erro_api(
                source_name=source_name,
                status_code=None,
                error_type="timeout",
                error_message=last_error,
            )
            return {
                "ok": False,
                "status": "timeout",
                "status_code": None,
                "attempts_used": attempt_idx,
                "data": None,
                "error": last_error,
                "source": source_name,
            }
        except requests.ConnectionError as exc:
            last_error = str(exc)
            if attempt_idx < attempts:
                time.sleep(backoff_seconds * attempt_idx)
                continue
            _reportar_erro_api(
                source_name=source_name,
                status_code=None,
                error_type="connection_error",
                error_message=last_error,
            )
            return {
                "ok": False,
                "status": "connection_error",
                "status_code": None,
                "attempts_used": attempt_idx,
                "data": None,
                "error": last_error,
                "source": source_name,
            }
        except Exception as exc:
            _reportar_erro_api(
                source_name=source_name,
                status_code=None,
                error_type="exception",
                error_message=str(exc),
            )
            return {
                "ok": False,
                "status": "unknown_error",
                "status_code": None,
                "attempts_used": attempt_idx,
                "data": None,
                "error": str(exc),
                "source": source_name,
            }

    return {
        "ok": False,
        "status": "unknown_error",
        "status_code": None,
        "attempts_used": attempts,
        "data": None,
        "error": last_error,
        "source": source_name,
    }
