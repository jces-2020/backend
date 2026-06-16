"""
Proxy service para api-ia.
El backend actúa como intermediario entre el frontend y el servicio api-ia.
"""
import os
from typing import Any, Dict, List, Optional

import requests

API_IA_BASE_URL = os.getenv("API_IA_URL", "http://127.0.0.1:8001").rstrip("/")
API_IA_TIMEOUT = float(os.getenv("API_IA_TIMEOUT", "180"))


def _ia_get(path: str) -> Dict[str, Any]:
    try:
        response = requests.get(f"{API_IA_BASE_URL}{path}", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Error contactando api-ia: {exc}") from exc


def _ia_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = requests.post(
            f"{API_IA_BASE_URL}{path}",
            json=payload,
            timeout=API_IA_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Error contactando api-ia: {exc}") from exc


def ia_health() -> Dict[str, Any]:
    return _ia_get("/api/ia/health")


def ia_chat(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
    }
    if model:
        payload["model"] = model
    if system_prompt:
        payload["system_prompt"] = system_prompt

    return _ia_post("/api/ia/chat", payload)


__all__ = ["ia_health", "ia_chat"]
