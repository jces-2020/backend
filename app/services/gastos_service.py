"""
Servicio para gestión de gastos y caja.
Consulta Supabase para obtener gastos e ingresos del día.
"""

from typing import Dict, List, Any, Optional
from datetime import date

from services.supabase_client import supabase


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
            "id_venta, total, fecha_venta, caja_id, metodo"
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
    total_ventas = sum(float(v.get("total", 0) or 0) for v in ventas)
    
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


__all__ = [
    "get_gastos_by_date",
    "get_caja_by_date",
    "get_ventas_by_date",
    "create_gasto",
    "get_resumen_dia"
]
