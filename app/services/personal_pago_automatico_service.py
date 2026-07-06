"""
Servicios para pago mensual automatico y envio de comprobante por correo.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Dict, Optional

from services.supabase_client import supabase
from services.personal_service import (
    create_gasto_personal,
    create_gasto_personal_bono,
    create_pago,
    get_personal_by_id,
)


def _sueldo_minimo() -> float:
    raw = (os.getenv("SUELDO_MINIMO_MENSUAL") or "1300").strip()
    try:
        value = float(raw)
        return value if value > 0 else 1300.0
    except Exception:
        return 1300.0


def _build_tipo_gasto(base_tipo: str, personal_id: str) -> str:
    return f"{base_tipo}:{personal_id}"


def _month_bounds(fecha_obj: date) -> tuple[str, str]:
    start = fecha_obj.replace(day=1)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    end = next_month.fromordinal(next_month.toordinal() - 1)
    return start.isoformat(), end.isoformat()


def _auth_redirect_base() -> str:
    return (os.getenv("FRONTEND_URL") or "https://vidriobras.com").rstrip("/")


def _send_invite_template(
    to_email: str,
    nombre: str,
    monto: float,
    fecha_pago: str,
    detalle: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispara plantilla Invite user de Supabase Auth."""
    try:
        payload = {
            "data": {
                "nombre": nombre,
                "monto": round(float(monto), 2),
                "fecha": fecha_pago,
                "detalle": (detalle or "Pago de bono").strip(),
                "tipo_pago": "bono",
            },
            "redirect_to": f"{_auth_redirect_base()}/login",
        }
        invite_resp = supabase.auth.admin.invite_user_by_email(to_email, payload)
        print(f"[personal_pago_automatico_service] invite_user enviado a {to_email}: {invite_resp}")
        return {"ok": True, "message": "Correo enviado con plantilla Invite user"}
    except Exception as exc:
        err = str(exc)
        print(f"[personal_pago_automatico_service] error invite_user: {err}")

        # Invite user solo aplica para usuarios no registrados.
        # Si el correo ya existe en Auth, se envia con la plantilla Magic link or OTP.
        if "already been registered" in err.lower() or "already registered" in err.lower():
            fallback = _send_magic_link_template(
                to_email=to_email,
                nombre=nombre,
                monto=monto,
                fecha_pago=fecha_pago,
                tipo="bono",
                detalle=(detalle or "Pago de bono"),
            )
            if fallback.get("ok"):
                return {
                    "ok": True,
                    "message": "Usuario ya registrado: correo enviado con plantilla Magic link or OTP",
                }
            return fallback

        return {
            "ok": False,
            "message": f"No se pudo enviar con Invite user: {err}",
        }


def _send_magic_link_template(
    to_email: str,
    nombre: str,
    monto: float,
    fecha_pago: str,
    tipo: str = "mensual",
    detalle: Optional[str] = None,
) -> Dict[str, Any]:
    """Envia correo con plantilla Magic link or OTP de Supabase Auth."""
    try:
        resp = supabase.auth.sign_in_with_otp({
            "email": to_email,
            "options": {
                "email_redirect_to": f"{_auth_redirect_base()}/login",
                "data": {
                    "nombre": nombre,
                    "monto": round(float(monto), 2),
                    "fecha": fecha_pago,
                    "detalle": (detalle or "Pago").strip(),
                    "tipo_pago": (tipo or "mensual"),
                },
            },
        })
        print(f"[personal_pago_automatico_service] magic_link enviado a {to_email}: {resp}")
        return {"ok": True, "message": "Correo enviado con plantilla Magic link or OTP"}
    except Exception as exc:
        print(f"[personal_pago_automatico_service] error magic_link: {exc}")
        return {"ok": False, "message": f"Error Magic link or OTP: {exc}"}


def _send_reauth_template(
    to_email: str,
    nombre: str,
    monto: float,
    fecha_pago: str,
    detalle: Optional[str] = None,
) -> Dict[str, Any]:
    """Compatibilidad: este proyecto no acepta reauthentication como link type.

    Se redirige al envio por plantilla Magic link or OTP.
    """
    return _send_magic_link_template(
        to_email=to_email,
        nombre=nombre,
        monto=monto,
        fecha_pago=fecha_pago,
        tipo="mensual",
        detalle=detalle,
    )


def enviar_comprobante_pago_email(
    to_email: str,
    nombre: str,
    monto: float,
    tipo: str,
    fecha_pago: str,
    detalle: Optional[str] = None,
) -> Dict[str, Any]:
    """Envia comprobante via plantillas de Supabase Auth.

    - tipo=bono: plantilla Invite user
    - tipo=mensual: plantilla Magic link or OTP (compatibilidad)
    """
    if not to_email:
        return {"ok": False, "message": "Personal sin correo"}

    if tipo == "bono":
        return _send_invite_template(to_email, nombre, monto, fecha_pago, detalle)

    return _send_reauth_template(to_email, nombre, monto, fecha_pago, detalle)


def registrar_pago_personal(
    personal_id: str,
    monto: float,
    fecha_pago: str,
    tipo: str = "mensual",
    caja_id: Optional[str] = None,
    tipo_gasto_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Registra gasto + descuento en saldo empresa para pago mensual o bono."""
    monto_float = float(monto)
    if monto_float <= 0:
        raise ValueError("Monto debe ser mayor a 0")

    if tipo == "bono":
        gasto = create_gasto_personal_bono(
            monto=monto_float,
            fecha=fecha_pago,
            caja_id=caja_id,
            tipo_gasto=tipo_gasto_override or "personal bono",
        )
    else:
        gasto = create_gasto_personal(
            monto=monto_float,
            fecha=fecha_pago,
            caja_id=caja_id,
            tipo_gasto=tipo_gasto_override or "personal",
        )

    pago = create_pago(personal_id, monto_float, fecha_pago)
    if not gasto or not pago:
        raise RuntimeError("No se pudo registrar pago/gasto")

    return {
        "gasto": gasto,
        "saldo_empresa": pago,
    }


def pagar_mensual_automatico(fecha_ejecucion: Optional[str] = None) -> Dict[str, Any]:
    """Ejecuta pagos mensuales automaticos (S/1300 por defecto) para personal vencido del dia."""
    if fecha_ejecucion:
        hoy = datetime.strptime(fecha_ejecucion, "%Y-%m-%d").date()
    else:
        hoy = date.today()

    sueldo = _sueldo_minimo()
    inicio_mes, fin_mes = _month_bounds(hoy)

    result = supabase.table("personal").select("id_personal, nombre, correo, created_at").execute()
    personal_rows = result.data or []

    procesados = 0
    pagados = 0
    omitidos = 0
    errores = []

    for p in personal_rows:
        procesados += 1
        personal_id = p.get("id_personal")
        nombre = (p.get("nombre") or "").strip()
        correo = (p.get("correo") or "").strip().lower()
        created_at = (p.get("created_at") or "").strip()

        if not personal_id:
            omitidos += 1
            continue

        try:
            if created_at:
                created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
                dia_pago = created_date.day
            else:
                dia_pago = hoy.day

            if hoy.day != dia_pago:
                omitidos += 1
                continue

            tipo_gasto = _build_tipo_gasto("personal_auto", personal_id)
            existente = (
                supabase
                .table("gastos")
                .select("id_gasto")
                .eq("tipo", tipo_gasto)
                .gte("fecha", inicio_mes)
                .lte("fecha", fin_mes)
                .limit(1)
                .execute()
            )
            if existente.data:
                omitidos += 1
                continue

            registrar_pago_personal(
                personal_id=personal_id,
                monto=sueldo,
                fecha_pago=hoy.isoformat(),
                tipo="mensual",
                tipo_gasto_override=tipo_gasto,
            )
            pagados += 1

            if correo:
                enviar_comprobante_pago_email(
                    to_email=correo,
                    nombre=nombre or "Colaborador",
                    monto=sueldo,
                    tipo="mensual",
                    fecha_pago=hoy.isoformat(),
                    detalle="Pago mensual automatico",
                )
        except Exception as exc:
            errores.append({"personal_id": personal_id, "error": str(exc)})

    return {
        "success": len(errores) == 0,
        "fecha": hoy.isoformat(),
        "sueldo_aplicado": sueldo,
        "procesados": procesados,
        "pagados": pagados,
        "omitidos": omitidos,
        "errores": errores,
    }


def pagar_bono_y_notificar(personal_id: str, bono_id: str, monto: float, fecha_pago: str) -> Dict[str, Any]:
    """Asigna bono, registra gasto/impacto en saldo y envia comprobante por correo."""
    # Asegura que la asignacion exista para conservar el flujo actual.
    from services.personal_service import add_bono_to_personal

    asignado = add_bono_to_personal(personal_id, bono_id)
    if not asignado:
        raise RuntimeError("No se pudo asignar el bono al personal")

    tipo_gasto = _build_tipo_gasto("personal_bono", personal_id)
    resultado_pago = registrar_pago_personal(
        personal_id=personal_id,
        monto=monto,
        fecha_pago=fecha_pago,
        tipo="bono",
        tipo_gasto_override=tipo_gasto,
    )

    personal = get_personal_by_id(personal_id) or {}
    correo = (personal.get("correo") or "").strip().lower()
    nombre = (personal.get("nombre") or "Colaborador").strip()

    correo_result = {"ok": False, "message": "Sin correo"}
    if correo:
        correo_result = enviar_comprobante_pago_email(
            to_email=correo,
            nombre=nombre,
            monto=float(monto),
            tipo="bono",
            fecha_pago=fecha_pago,
            detalle="Pago de bono",
        )

    return {
        "success": True,
        "pago": resultado_pago,
        "correo": correo_result,
    }
