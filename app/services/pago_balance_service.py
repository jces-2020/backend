from datetime import date
from typing import Any, Dict, Optional

from services.supabase_client import supabase


def ajustar_monto_empresa(delta: float) -> Optional[Dict[str, Any]]:
    """
    Ajusta el monto acumulado de la empresa en tabla pago.

    - Si existe un registro, actualiza ese mismo registro sumando/restando delta.
    - Si no existe, crea uno nuevo con el valor delta.
    """
    try:
        fecha_hoy = date.today().isoformat()

        # Tomamos un registro base para mantener la tabla con un solo saldo activo.
        current_res = (
            supabase.table("pago")
            .select("id_pago, monto, fecha")
            .order("fecha", desc=True)
            .limit(1)
            .execute()
        )
        rows = current_res.data or []

        if rows:
            row = rows[0]
            monto_actual = float(row.get("monto") or 0)
            nuevo_monto = monto_actual + float(delta)

            update_res = (
                supabase.table("pago")
                .update({"monto": nuevo_monto, "fecha": fecha_hoy})
                .eq("id_pago", row.get("id_pago"))
                .execute()
            )
            data = update_res.data or []
            return data[0] if data else None

        insert_res = (
            supabase.table("pago")
            .insert({"monto": float(delta), "fecha": fecha_hoy})
            .execute()
        )
        data = insert_res.data or []
        return data[0] if data else None

    except Exception as exc:  # noqa: BLE001
        print(f"[pago_balance_service] error ajustando monto empresa: {exc}")
        return None


def sumar_monto_empresa(monto: float) -> Optional[Dict[str, Any]]:
    return ajustar_monto_empresa(abs(float(monto)))


def restar_monto_empresa(monto: float) -> Optional[Dict[str, Any]]:
    return ajustar_monto_empresa(-abs(float(monto)))
