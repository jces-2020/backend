from datetime import date
from typing import Any, Dict, Optional

from services.supabase_client import supabase


def ajustar_monto_empresa(
    delta: float, origen: Optional[str] = None, referencia_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Registra un movimiento en el ledger 'monto_empresa' (no existe la tabla
    'pago' que se usaba antes). 'monto_empresa' es un libro de movimientos
    (id_movimiento, monto, fecha, origen, referencia_id) -- no una fila unica
    que se actualiza in-place, asi que cada llamada inserta un movimiento
    nuevo; el saldo total es la suma de todos los movimientos.
    """
    try:
        payload: Dict[str, Any] = {
            "monto": float(delta),
            "fecha": date.today().isoformat(),
        }
        if origen:
            payload["origen"] = origen
        if referencia_id:
            payload["referencia_id"] = referencia_id

        insert_res = supabase.table("monto_empresa").insert(payload).execute()
        data = insert_res.data or []
        return data[0] if data else None

    except Exception as exc:  # noqa: BLE001
        print(f"[pago_balance_service] error registrando movimiento monto_empresa: {exc}")
        return None


def sumar_monto_empresa(
    monto: float, origen: Optional[str] = None, referencia_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    return ajustar_monto_empresa(abs(float(monto)), origen=origen, referencia_id=referencia_id)


def restar_monto_empresa(
    monto: float, origen: Optional[str] = None, referencia_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    return ajustar_monto_empresa(-abs(float(monto)), origen=origen, referencia_id=referencia_id)
