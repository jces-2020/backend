"""
Servicio para gestión de gastos y caja.
Consulta Supabase para obtener gastos e ingresos del día.
"""

from typing import Dict, List, Any, Optional
from datetime import date, timedelta

from services.supabase_client import supabase


def _obtener_caja_activa(fecha: str) -> Optional[Dict[str, Any]]:
    """Devuelve la caja abierta más reciente para una fecha determinada."""
    try:
        result = (
            supabase.table("caja")
            .select("id_caja, fecha, turno, subtotal")
            .eq("fecha", fecha)
            .neq("turno", "cerrada")
            .order("id_caja", desc=True)
            .limit(1)
            .execute()
        )
        cajas = result.data or []
        return cajas[0] if cajas else None
    except Exception as exc:  # noqa: BLE001
        print(f"[_obtener_caja_activa] Error: {exc}")
        return None


def get_gastos_by_date(fecha: str) -> List[Dict[str, Any]]:
    """
    Obtiene los gastos de una fecha específica.
    """
    try:
        result = supabase.table("gastos").select(
            "id_gasto, monto, fecha, caja_id, tipo"
        ).eq("fecha", fecha).execute()
        print(f"[gastos_service] fetched {len(result.data or [])} gastos for {fecha}")
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        print(f"[gastos_service] error fetching gastos: {exc}")
        import traceback
        traceback.print_exc()
        return []


def get_caja_by_date(fecha: str) -> List[Dict[str, Any]]:
    """
    Obtiene las cajas (ingresos) de una fecha específica.
    """
    try:
        result = supabase.table("caja").select(
            "id_caja, fecha, turno, subtotal"
        ).eq("fecha", fecha).execute()
        print(f"[gastos_service] fetched {len(result.data or [])} cajas for {fecha}")
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        print(f"[gastos_service] error fetching caja: {exc}")
        import traceback
        traceback.print_exc()
        return []


def get_ventas_by_date(fecha: str) -> List[Dict[str, Any]]:
    """
    Obtiene todas las ventas (sin filtrar por fecha) para mostrarlas en la tabla de ventas.
    """
    try:
        result = supabase.table("venta").select(
            "id_venta, monto, fecha_venta, metodo"
        ).order("fecha_venta", desc=True).execute()
        print(f"[gastos_service] fetched {len(result.data or [])} ventas (todas)")
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        print(f"[gastos_service] error fetching ventas: {exc}")
        import traceback
        traceback.print_exc()
        return []


def create_gasto(monto: float, fecha: str, caja_id: Optional[str] = None, tipo: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Crea un nuevo gasto.
    """
    try:
        data = {
            "monto": monto,
            "fecha": fecha
        }
        if caja_id:
            data["caja_id"] = caja_id
        if tipo:
            data["tipo"] = tipo
        
        result = supabase.table("gastos").insert(data).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[gastos_service] error creating gasto: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_resumen_dia(fecha: str) -> Dict[str, Any]:
    """
    Obtiene un resumen completo del día con gastos e ingresos.
    """
    gastos = get_gastos_by_date(fecha)
    cajas = get_caja_by_date(fecha)
    ventas = get_ventas_by_date(fecha)
    
    total_gastos = sum(float(g.get("monto", 0) or 0) for g in gastos)
    total_ingresos_caja = sum(float(c.get("subtotal", 0) or 0) for c in cajas)
    total_ventas = sum(float(v.get("monto", 0) or 0) for v in ventas)
    
    # El total que debería tener es: ingresos - gastos
    total_neto = total_ingresos_caja + total_ventas - total_gastos
    
    return {
        "fecha": fecha,
        "gastos": gastos,
        "cajas": cajas,
        "ventas": ventas,
        "total_gastos": total_gastos,
        "total_ingresos_caja": total_ingresos_caja,
        "total_ventas": total_ventas,
        "total_neto": total_neto
    }


def actualizar_subtotal_caja_por_registro_pago(fecha: str) -> bool:
    """
    Actualiza el subtotal de la caja activa del día usando solo las ventas vinculadas a esa caja.
    Esto evita que una caja nueva herede el subtotal de la caja cerrada anterior.
    """
    try:
        fecha_inicio = date.fromisoformat(fecha)
        fecha_fin = (fecha_inicio + timedelta(days=1)).isoformat()

        caja_actual = _obtener_caja_activa(fecha)
        if not caja_actual or not caja_actual.get("id_caja"):
            print(f"[actualizar_subtotal_caja] No existe caja activa para {fecha}")
            return False

        caja_id_actual = caja_actual.get("id_caja")

        ventas_res = (
            supabase.table("venta")
            .select("id_venta, registro_pago_id, monto, caja_id")
            .gte("fecha_venta", fecha)
            .lt("fecha_venta", fecha_fin)
            .eq("caja_id", caja_id_actual)
            .execute()
        )
        ventas = ventas_res.data or []
        registro_ids = [row.get("registro_pago_id") for row in ventas if row.get("registro_pago_id")]

        total_caja = 0.0
        if registro_ids:
            registros = (
                supabase.table("registro_pago")
                .select("id_registro, total")
                .in_("id_registro", registro_ids)
                .execute()
            )
            registros_list = registros.data or []
            total_caja = sum(float(r.get("total", 0) or 0) for r in registros_list)
        else:
            total_caja = sum(float(v.get("monto", 0) or 0) for v in ventas)

        print(f"[actualizar_subtotal_caja] Fecha: {fecha}, Caja activa: {caja_id_actual}, Total caja: S/ {total_caja:.2f}, Ventas: {len(ventas)}")

        supabase.table("caja").update({
            "subtotal": round(total_caja, 2)
        }).eq("id_caja", caja_id_actual).execute()

        print(f"[actualizar_subtotal_caja] OK - Subtotal actualizado a S/ {total_caja:.2f}")
        return True

    except Exception as exc:  # noqa: BLE001
        print(f"[actualizar_subtotal_caja] ERROR: {exc}")
        import traceback
        traceback.print_exc()
        return False


__all__ = [
    "get_gastos_by_date",
    "get_caja_by_date",
    "get_ventas_by_date",
    "create_gasto",
    "get_resumen_dia",
    "actualizar_subtotal_caja_por_registro_pago"
]
