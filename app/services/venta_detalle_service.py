"""
Helpers para leer el detalle de una compra desde la tabla venta.

La tabla venta ahora concentra las líneas de producto/servicio. Este módulo
provee lecturas reutilizables para seguimiento de clientes, detalle de pedidos
y pantallas de entrega.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.services.cortes_service import calcular_total_corte, es_material_aluminio
from app.services.supabase_client import supabase


def obtener_ventas_por_carrito(carrito_id: str) -> List[Dict[str, Any]]:
    if not carrito_id:
        return []
    try:
        result = (
            supabase.table("venta")
            .select("id_venta,cliente_id,producto_id,carrito_id,cantidad,monto,fecha_venta,registro_pago_id,tipo_venta_id,presupuesto_id")
            .eq("carrito_id", carrito_id)
            .execute()
        )
        return getattr(result, "data", []) or []
    except Exception as exc:
        print(f"[venta_detalle_service] error obtener_ventas_por_carrito({carrito_id}): {exc}")
        return []


def obtener_venta_ids_por_cliente(cliente_id: str) -> List[str]:
    if not cliente_id:
        return []
    try:
        result = (
            supabase.table("venta")
            .select("id_venta")
            .eq("cliente_id", cliente_id)
            .execute()
        )
        return [str(row.get("id_venta")) for row in (getattr(result, "data", []) or []) if row.get("id_venta")]
    except Exception as exc:
        print(f"[venta_detalle_service] error obtener_venta_ids_por_cliente({cliente_id}): {exc}")
        return []


def obtener_carrito_ids_por_cliente(cliente_id: str) -> List[str]:
    if not cliente_id:
        return []
    try:
        result = (
            supabase.table("venta")
            .select("carrito_id")
            .eq("cliente_id", cliente_id)
            .execute()
        )
        return [str(row.get("carrito_id")) for row in (getattr(result, "data", []) or []) if row.get("carrito_id")]
    except Exception as exc:
        print(f"[venta_detalle_service] error obtener_carrito_ids_por_cliente({cliente_id}): {exc}")
        return []


def obtener_cliente_id_por_carrito(carrito_id: str) -> Optional[str]:
    ventas = obtener_ventas_por_carrito(carrito_id)
    for venta in ventas:
        cliente_id = venta.get("cliente_id")
        if cliente_id:
            return str(cliente_id)
    return None


def obtener_detalle_venta_por_carrito(carrito_id: str) -> Tuple[List[Dict[str, Any]], int, float]:
    """
    Construye el detalle de venta usando la tabla venta como fuente primaria.

    Si una venta tiene registros en cortes asociados, cada corte se expone como
    línea de corte. Si no tiene cortes, se expone como línea de plancha/producto.
    """
    ventas = obtener_ventas_por_carrito(carrito_id)
    if not ventas:
        return [], 0, 0.0

    producto_ids = [v.get("producto_id") for v in ventas if v.get("producto_id")]
    productos_map: Dict[str, Dict[str, Any]] = {}
    if producto_ids:
        try:
            productos = (
                supabase.table("productos")
                .select("id_producto,nombre,codigo,descripcion,grosor,precio_unitario,fila,columna")
                .in_("id_producto", producto_ids)
                .execute()
            )
            productos_map = {
                str(p.get("id_producto")): p
                for p in (getattr(productos, "data", []) or [])
                if p.get("id_producto")
            }
        except Exception as exc:
            print(f"[venta_detalle_service] error cargando productos: {exc}")
            productos_map = {}

    venta_ids = [v.get("id_venta") for v in ventas if v.get("id_venta")]
    cortes_por_venta: Dict[str, List[Dict[str, Any]]] = {}
    if venta_ids:
        try:
            cortes = (
                supabase.table("cortes")
                .select("id_corte,venta_id,ancho_cm,alto_cm,cantidad,estado,fecha_registro,normbre")
                .in_("venta_id", venta_ids)
                .execute()
            )
            for corte in (getattr(cortes, "data", []) or []):
                venta_key = str(corte.get("venta_id") or "")
                if not venta_key:
                    continue
                cortes_por_venta.setdefault(venta_key, []).append(corte)
        except Exception as exc:
            print(f"[venta_detalle_service] error cargando cortes: {exc}")
            cortes_por_venta = {}

    items: List[Dict[str, Any]] = []
    total_precio = 0.0

    for venta in ventas:
        venta_id = str(venta.get("id_venta") or "")
        producto_id = str(venta.get("producto_id") or "")
        producto = productos_map.get(producto_id, {})
        cantidad = float(venta.get("cantidad") or 0)
        monto = float(venta.get("monto") or 0)

        cortes = cortes_por_venta.get(venta_id, [])
        if cortes:
            for corte in cortes:
                precio_unitario = float(producto.get("precio_unitario") or 0)
                es_aluminio = es_material_aluminio(producto)
                subtotal = calcular_total_corte(corte, precio_unitario, es_aluminio)
                ancho_cm = float(corte.get("ancho_cm") or 0)
                alto_cm = float(corte.get("alto_cm") or 0)
                medida_principal_cm = ancho_cm if ancho_cm > 0 else alto_cm
                if es_aluminio:
                    medida_texto = f"Largo: {medida_principal_cm:g} cm" if medida_principal_cm > 0 else ""
                elif ancho_cm > 0 and alto_cm > 0:
                    medida_texto = f"{ancho_cm:g} x {alto_cm:g} cm"
                else:
                    medida_texto = ""

                total_precio += subtotal
                items.append({
                    "item_key": f"corte:{corte.get('id_corte') or venta_id}",
                    "tipo_item": "corte",
                    "id_venta": venta_id,
                    "id_producto": producto_id,
                    "nombre": producto.get("nombre") or "Cortes personalizados",
                    "codigo": producto.get("codigo"),
                    "cantidad": float(corte.get("cantidad") or cantidad or 0),
                    "fila": producto.get("fila"),
                    "columna": producto.get("columna"),
                    "precio_unitario": precio_unitario,
                    "subtotal": round(subtotal, 2),
                    "grosor": producto.get("grosor"),
                    "descripcion": producto.get("descripcion"),
                    "ancho_cm": ancho_cm,
                    "alto_cm": alto_cm,
                    "es_aluminio": es_aluminio,
                    "medida_principal_cm": medida_principal_cm,
                    "medida_texto": medida_texto,
                    "corte_id": corte.get("id_corte"),
                })
            continue

        subtotal = monto if monto > 0 else float(producto.get("precio_unitario") or 0) * cantidad
        total_precio += subtotal
        items.append({
            "item_key": f"venta:{venta_id}",
            "tipo_item": "plancha",
            "id_venta": venta_id,
            "id_producto": producto_id,
            "nombre": producto.get("nombre"),
            "codigo": producto.get("codigo"),
            "cantidad": cantidad,
            "fila": producto.get("fila"),
            "columna": producto.get("columna"),
            "precio_unitario": float(producto.get("precio_unitario") or 0),
            "subtotal": round(subtotal, 2),
            "grosor": producto.get("grosor"),
            "descripcion": producto.get("descripcion"),
        })

    return items, len(items), round(total_precio, 2)
