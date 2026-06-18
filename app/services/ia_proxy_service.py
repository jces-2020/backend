"""
Proxy service para api-ia.
El backend actua como intermediario entre el frontend y el servicio api-ia.
"""
import os
import time
from typing import Any, Dict, List, Optional

import requests

API_IA_BASE_URL = os.getenv("API_IA_URL", "http://127.0.0.1:8001").rstrip("/")
API_IA_TIMEOUT = float(os.getenv("API_IA_TIMEOUT", "300"))
API_IA_SESSION_TIMEOUT = float(os.getenv("API_IA_SESSION_TIMEOUT", "25"))


def _ia_get(path: str) -> Dict[str, Any]:
    try:
        response = requests.get(f"{API_IA_BASE_URL}{path}", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Error contactando api-ia: {exc}") from exc


def _ia_post(
    path: str,
    payload: Dict[str, Any],
    timeout: Optional[float] = None,
    retry_attempts: int = 2,
) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(max(1, retry_attempts)):
        try:
            response = requests.post(
                f"{API_IA_BASE_URL}{path}",
                json=payload,
                timeout=timeout or API_IA_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            # Reintento rapido para mitigar picos transitorios de carga.
            if attempt < max(1, retry_attempts) - 1:
                time.sleep(0.35)
                continue
            break

    raise RuntimeError(f"Error contactando api-ia: {last_error}") from last_error


def ia_health() -> Dict[str, Any]:
    return _ia_get("/api/ia/health")


def ia_chat(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    system_prompt: Optional[str] = None,
    keep_alive: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
    }
    if model:
        payload["model"] = model
    if system_prompt:
        payload["system_prompt"] = system_prompt
    if keep_alive:
        payload["keep_alive"] = keep_alive

    return _ia_post("/api/ia/chat", payload)


def ia_session_start(keep_alive: str = "30m") -> Dict[str, Any]:
    return _ia_post(
        "/api/ia/session/start",
        {"keep_alive": keep_alive},
        timeout=API_IA_SESSION_TIMEOUT,
        retry_attempts=1,
    )


def ia_session_stop() -> Dict[str, Any]:
    return _ia_post(
        "/api/ia/session/stop",
        {},
        timeout=API_IA_SESSION_TIMEOUT,
        retry_attempts=1,
    )


__all__ = ["ia_health", "ia_chat", "ia_session_start", "ia_session_stop"]
