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
    Actualiza el subtotal en la tabla caja sumando todos los registro_pago de la fecha especificada.
    Se ejecuta cada vez que se registra un nuevo pago.
    
    Flujo:
    1. Obtiene todos los registro_pago de la fecha
    2. Suma los totales
    3. Si existe caja para esa fecha, actualiza el subtotal
    4. Si no existe, crea un nuevo registro con el subtotal
    
    Retorna True si la operación fue exitosa, False en caso contrario.
    """
    try:
        # 1. Sumar todos los registro_pago de la fecha
        registros = supabase.table("registro_pago").select(
            "id_registro, total"
        ).eq("fecha", fecha).execute()
        
        registros_list = registros.data or []
        total_dia = sum(float(r.get("total", 0) or 0) for r in registros_list)
        
        print(f"[actualizar_subtotal_caja] Fecha: {fecha}, Total registro_pago: S/ {total_dia:.2f}, Registros: {len(registros_list)}")
        
        # 2. Buscar si existe caja para esa fecha
        caja_result = supabase.table("caja").select(
            "id_caja, subtotal, turno"
        ).eq("fecha", fecha).limit(1).execute()
        
        cajas = caja_result.data or []
        
        if cajas:
            # Existe caja para la fecha: actualizar subtotal
            caja_actual = cajas[0]
            print(f"[actualizar_subtotal_caja] Actualizando caja existente (id: {caja_actual.get('id_caja')})")
            
            supabase.table("caja").update({
                "subtotal": total_dia
            }).eq("id_caja", caja_actual.get("id_caja")).execute()
        else:
            # No existe caja para la fecha: crear una nueva
            print(f"[actualizar_subtotal_caja] Creando nuevo registro de caja para {fecha}")
            
            supabase.table("caja").insert({
                "fecha": fecha,
                "turno": "diurno",
                "subtotal": total_dia
            }).execute()
        
        print(f"[actualizar_subtotal_caja] OK - Subtotal actualizado a S/ {total_dia:.2f}")
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
