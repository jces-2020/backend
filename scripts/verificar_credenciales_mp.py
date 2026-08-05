# -*- coding: utf-8 -*-
"""
Diagnostico aislado de credenciales de Mercado Pago.

NO es un endpoint HTTP (no se expone en produccion). Se ejecuta manualmente
en el servidor para separar dos causas posibles del error PA_UNAUTHORIZED_RESULT_FROM_POLICIES:

  A) El Access Token es invalido / no corresponde a ninguna cuenta -> este script fallara (401/403).
  B) El Access Token es valido y pertenece a la cuenta correcta, pero el motor de riesgo
     de Mercado Pago (PolicyAgent) bloquea la operacion de PAGO especificamente -> este
     script funcionara OK (200) aunque /v1/payments siga devolviendo el bloqueo.

Uso (desde backend/, con el venv activado):
    python scripts/verificar_credenciales_mp.py
"""
import os
import re
import sys

import requests
from dotenv import load_dotenv

load_dotenv()


def _mask_email(email):
    if not email:
        return None
    return re.sub(r"^(.).*(@.*)$", r"\1***\2", email)


def main():
    access_token = os.getenv("MERCADO_PAGO_ACCESS_TOKEN")
    public_key = os.getenv("MERCADO_PAGO_PUBLIC_KEY")

    if not access_token:
        print("[VERIFICAR_MP] FALLO: MERCADO_PAGO_ACCESS_TOKEN no esta definido en este proceso.")
        sys.exit(1)

    credential_env = "production" if access_token.startswith("APP_USR-") else "sandbox"
    print(
        f"[VERIFICAR_MP] access_token_presente=True "
        f"access_token_prefix={access_token[:9]}... "
        f"access_token_length={len(access_token)} "
        f"ambiente={credential_env}"
    )
    if public_key:
        print(f"[VERIFICAR_MP] public_key_prefix={public_key[:9]}... public_key_length={len(public_key)}")

    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get("https://api.mercadopago.com/users/me", headers=headers, timeout=15)

    print(f"[VERIFICAR_MP] GET /users/me -> HTTP {resp.status_code}")

    if resp.status_code != 200:
        print(f"[VERIFICAR_MP] Respuesta (saneada): {resp.text[:300]}")
        print(
            "[VERIFICAR_MP] DIAGNOSTICO: el Access Token es invalido o fue "
            "rechazado por Mercado Pago a nivel de autenticacion (no es un tema de payments/policy)."
        )
        sys.exit(1)

    data = resp.json()
    print(
        f"[VERIFICAR_MP] OK cuenta identificada: "
        f"user_id={data.get('id')} email={_mask_email(data.get('email'))} "
        f"site_id={data.get('site_id')} "
        f"live_mode={not data.get('live_mode') is False}"
    )
    print(
        "[VERIFICAR_MP] DIAGNOSTICO: el Access Token es valido y esta autenticando correctamente. "
        "Si /v1/payments sigue devolviendo PA_UNAUTHORIZED_RESULT_FROM_POLICIES, el bloqueo es "
        "especifico de la operacion de pago (politica de riesgo/cumplimiento de la cuenta), "
        "no un problema de credenciales ni de headers."
    )


if __name__ == "__main__":
    main()
