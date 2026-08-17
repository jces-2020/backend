from services.supabase_client import supabase
from services.pago_balance_service import sumar_monto_empresa
from datetime import date
from typing import Optional

def registrar_venta(
    total: float,
    metodo: str,
    caja_id: Optional[str] = None,
    cliente_id: Optional[str] = None,
    tipo_venta_id: Optional[str] = None,
    carrito_id: Optional[str] = None,
) -> bool:
    """
    Registra una venta en la tabla venta y actualiza el subtotal en la tabla caja.
    """
    fecha_actual = date.today().isoformat()

    # 1. Insertar venta ('venta' no tiene columna caja_id -- esa vive en
    # 'registro_pago'; el subtotal de caja se actualiza aparte en el paso 2)
    venta_payload = {
        "monto": total,
        "fecha_venta": fecha_actual,
        "metodo": metodo,
    }
    # cliente_id/tipo_venta_id/carrito_id son opcionales: sin ellos, esta venta
    # queda invisible para _carrito_ids_servicio_de_cliente (barra de progreso
    # del cliente), que filtra ventas de servicio justamente por esos 3 campos.
    if cliente_id:
        venta_payload["cliente_id"] = cliente_id
    if tipo_venta_id:
        venta_payload["tipo_venta_id"] = tipo_venta_id
    if carrito_id:
        venta_payload["carrito_id"] = carrito_id
    res = supabase.table("venta").insert(venta_payload).execute()
    venta_ok = bool(res.data)
    
    if not venta_ok:
        return False
    
    # 2. Actualizar tabla caja: usar la caja activa del día
    try:
        caja_res = (
            supabase.table("caja")
            .select("id_caja, subtotal, turno")
            .eq("fecha", fecha_actual)
            .neq("turno", "cerrada")
            .order("id_caja", desc=True)
            .limit(1)
            .execute()
        )
        cajas = caja_res.data or []

        if cajas:
            caja_actual = cajas[0]
            nuevo_subtotal = float(caja_actual.get("subtotal") or 0) + total
            supabase.table("caja").update({
                "subtotal": round(nuevo_subtotal, 2)
            }).eq("id_caja", caja_actual["id_caja"]).execute()
        else:
            supabase.table("caja").insert({
                "fecha": fecha_actual,
                "turno": "diurno",
                "subtotal": round(total, 2)
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
