from services.supabase_client import supabase
from services.pago_balance_service import sumar_monto_empresa
from datetime import date
from typing import Optional

def registrar_venta(total: float, metodo: str, caja_id: Optional[str] = None) -> bool:
    """
    Registra una venta en la tabla venta y actualiza el subtotal en la tabla caja.
    """
    fecha_actual = date.today().isoformat()
    
    # 1. Insertar venta
    venta_payload = {
        "monto": total,
        "fecha_venta": fecha_actual,
        "metodo": metodo,
        "caja_id": caja_id
    }
    res = supabase.table("venta").insert(venta_payload).execute()
    venta_ok = bool(res.data)
    
    if not venta_ok:
        return False
    
    # 2. Actualizar tabla caja: buscar registro de hoy
    try:
        caja_res = supabase.table("caja").select("*").eq("fecha", fecha_actual).execute()
        cajas = caja_res.data or []
        
        if cajas:
            # Existe registro de caja para hoy: actualizar sumando el total
            caja_actual = cajas[0]
            nuevo_subtotal = float(caja_actual.get("subtotal") or 0) + total
            supabase.table("caja").update({
                "subtotal": nuevo_subtotal
            }).eq("id_caja", caja_actual["id_caja"]).execute()
        else:
            # No existe registro de caja para hoy: crear uno nuevo
            supabase.table("caja").insert({
                "fecha": fecha_actual,
                "turno": "diurno",  # Valor por defecto
                "subtotal": total
            }).execute()
    except Exception as exc:
        print(f"[venta_service] Error actualizando tabla caja: {exc}")
        # No fallar la venta si hay error en caja

    # 3. Actualizar saldo acumulado en tabla pago (monto empresa en tiempo real)
    try:
        sumar_monto_empresa(float(total))
    except Exception as exc:
        print(f"[venta_service] Error actualizando tabla pago (saldo empresa): {exc}")

    return True
