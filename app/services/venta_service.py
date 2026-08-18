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
    presupuesto_id: Optional[str] = None,
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
    if presupuesto_id:
        venta_payload["presupuesto_id"] = presupuesto_id
    res = supabase.table("venta").insert(venta_payload).execute()
    venta_ok = bool(res.data)

    if not venta_ok:
        return False

    # NOTA: 'caja.subtotal' NO se incrementa aca. Solo debe reflejar ventas con
    # comprobante emitido: eso lo hace actualizar_subtotal_caja_por_registro_pago()
    # (gastos_service.py) al emitir boleta/factura, recalculando desde
    # registro_pago. Sumar aca duplicaria el monto (ver registro_pago_comprobante_service.py).

    # 2. Actualizar saldo acumulado en tabla pago (monto empresa en tiempo real)
    id_venta = (res.data or [{}])[0].get("id_venta")
    try:
        sumar_monto_empresa(float(total), origen="venta_servicio", referencia_id=id_venta)
    except Exception as exc:
        print(f"[venta_service] Error actualizando tabla pago (saldo empresa): {exc}")

    return True
