"""
Servicio simple para verificación de correo por código.

Guarda códigos en memoria del proceso y envía el correo usando SMTP
si las variables de entorno están configuradas.
"""
from __future__ import annotations

import os
import random
import secrets
import smtplib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional


@dataclass
class VerificationEntry:
    cliente_id: str
    correo: str
    nombre: str
    codigo: str
    expires_at: datetime


_VERIFICATION_LOCK = threading.Lock()
_VERIFICATION_CODES: Dict[str, VerificationEntry] = {}


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def generate_code() -> str:
    return f"{random.randint(100000, 999999)}"


def create_verification(cliente_id: str, correo: str, nombre: str, ttl_minutes: Optional[int] = None) -> Dict[str, str]:
    ttl = int(ttl_minutes or os.environ.get("EMAIL_VERIFICATION_TTL_MINUTES", "10"))
    token = secrets.token_urlsafe(16)
    entry = VerificationEntry(
        cliente_id=cliente_id,
        correo=normalize_email(correo),
        nombre=(nombre or "").strip(),
        codigo=generate_code(),
        expires_at=datetime.utcnow() + timedelta(minutes=ttl),
    )
    with _VERIFICATION_LOCK:
        _VERIFICATION_CODES[token] = entry
    return {"verification_token": token, "codigo": entry.codigo, "ttl_minutes": str(ttl)}


def cleanup_expired() -> None:
    now = datetime.utcnow()
    with _VERIFICATION_LOCK:
        expired = [token for token, entry in _VERIFICATION_CODES.items() if entry.expires_at <= now]
        for token in expired:
            _VERIFICATION_CODES.pop(token, None)


def consume_verification(token: str, codigo: str) -> Optional[VerificationEntry]:
    cleanup_expired()
    with _VERIFICATION_LOCK:
        entry = _VERIFICATION_CODES.get(token)
        if not entry:
            return None
        if entry.codigo != codigo:
            return None
        return _VERIFICATION_CODES.pop(token, None)


def get_verification(token: str) -> Optional[VerificationEntry]:
    cleanup_expired()
    with _VERIFICATION_LOCK:
        return _VERIFICATION_CODES.get(token)


def build_message(nombre: str, codigo: str, ttl_minutes: int) -> str:
    destinatario = nombre or "Hola"
    return f"{destinatario}, tu código de verificación es {codigo}. Expira en {ttl_minutes} minutos."


def send_verification_email(destinatario: str, nombre: str, codigo: str, ttl_minutes: int) -> bool:
    host = os.environ.get("EMAIL_SMTP_HOST", "").strip()
    port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    user = os.environ.get("EMAIL_SMTP_USER", "").strip()
    password = os.environ.get("EMAIL_SMTP_PASSWORD", "").strip()
    from_email = os.environ.get("EMAIL_FROM", user).strip()

    if not host or not user or not password:
        print(f"[EMAIL_VERIFICATION] SMTP no configurado; código para {destinatario}: {codigo}")
        return False

    message = MIMEMultipart()
    message["From"] = from_email
    message["To"] = destinatario
    message["Subject"] = "Verifica tu correo"
    body = build_message(nombre, codigo, ttl_minutes)
    message.attach(MIMEText(body, "plain", "utf-8"))

    server = smtplib.SMTP(host, port, timeout=20)
    try:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_email, [destinatario], message.as_string())
        return True
    finally:
        try:
            server.quit()
        except Exception:
            pass
