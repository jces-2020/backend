"""
Servicio para productos de entrega.
"""
import json
import re
import traceback
from typing import Dict, Any, List
from app.services.supabase_client import supabase
from app.services.entrega_reporte_service import obtener_reporte_temporal
from app.services.venta_detalle_service import (
    obtener_carrito_ids_por_cliente,
    obtener_detalle_venta_por_carrito,
)


def _obtener_carrito_id_por_cliente_fallback(notificacion_id: str, descripcion: str) -> str:
    """
    Fallback inteligente: busca el carrito más reciente del cliente.
    """
    _ = descripcion
    try:
        notif = supabase.table("notificacion") \
            .select("id_cliente, cliente_id") \
            .eq("id_notificacion", notificacion_id) \
            .limit(1) \
            .execute()

        if not notif.data:
            return ""

        row = notif.data[0] or {}
        cliente_id = row.get("id_cliente") or row.get("cliente_id")
        if not cliente_id:
            return ""

        carrito_ids = obtener_carrito_ids_por_cliente(cliente_id)
        if not carrito_ids:
            return ""
        return carrito_ids[0]

    except Exception as e:
        print(f"Error en fallback de carrito: {e}")
        return ""


def _obtener_carrito_id(notificacion_id: str) -> str:
    notif_result = supabase.table("notificacion") \
        .select("descripcion, venta_id") \
        .eq("id_notificacion", notificacion_id) \
        .limit(1) \
        .execute()

    if not notif_result.data:
        return ""

    row = notif_result.data[0] or {}
    descripcion = row.get("descripcion", "{}")
    venta_id_directa = row.get("venta_id") or ""
    if venta_id_directa:
        venta = supabase.table("venta") \
            .select("carrito_id") \
            .eq("id_venta", venta_id_directa) \
            .limit(1) \
            .execute()
        if getattr(venta, "data", None):
            return venta.data[0].get("carrito_id") or ""

    if isinstance(descripcion, dict):
        carrito_id = descripcion.get("carrito_id") or ""
        if carrito_id:
            return carrito_id
        venta_id = descripcion.get("venta_id") or ""
        if venta_id:
            venta = supabase.table("venta") \
                .select("carrito_id") \
                .eq("id_venta", venta_id) \
                .limit(1) \
                .execute()
            if getattr(venta, "data", None):
                return venta.data[0].get("carrito_id") or ""
        return _obtener_carrito_id_por_cliente_fallback(notificacion_id, "")

    try:
        meta = json.loads(descripcion)
        if isinstance(meta, dict):
            carrito_id = meta.get("carrito_id") or ""
            if carrito_id:
                return carrito_id
            venta_id = meta.get("venta_id") or ""
            if venta_id:
                venta = supabase.table("venta") \
                    .select("carrito_id") \
                    .eq("id_venta", venta_id) \
                    .limit(1) \
                    .execute()
                if getattr(venta, "data", None):
                    return venta.data[0].get("carrito_id") or ""
    except Exception:
        pass

    if isinstance(descripcion, str):
        match = re.search(r"Carrito:\s*([0-9a-fA-F-]{36})", descripcion)
        if match:
            return match.group(1)

    if isinstance(descripcion, str):
        carrito_id = _obtener_carrito_id_por_cliente_fallback(notificacion_id, descripcion)
        if carrito_id:
            return carrito_id

    return ""


def obtener_productos_entrega_por_notificacion(notificacion_id: str) -> Dict[str, Any]:
    """
    Obtiene productos comprados del cliente (plancha) y productos por corte sin merma.
    """
    try:
        carrito_id = _obtener_carrito_id(notificacion_id)
        if not carrito_id:
            return {
                "success": True,
                "message": "El cliente no agrego productos",
                "data": [],
                "carrito_id": "",
            }

        productos, _, _ = obtener_detalle_venta_por_carrito(carrito_id)
        productos = productos or []

        productos_map = {}
        for p in productos:
            pid = p.get("producto_id")
            if pid:
                productos_map[pid] = p
            if not p.get("origen"):
                p["origen"] = "plancha"

        reporte_tmp = obtener_reporte_temporal(notificacion_id)
        if reporte_tmp.get("success"):
            planchas = (reporte_tmp.get("data") or {}).get("plancha_por_corte", [])
            for plancha in planchas:
                pid = plancha.get("producto_id")
                if not pid:
                    continue
                if any(p.get("producto_id") == pid for p in productos):
                    continue

                prod = productos_map.get(pid)
                if not prod:
                    prod_res = supabase.table("productos") \
                        .select("id_producto, nombre, descripcion, codigo, grosor, cantidad, precio_unitario, categoria_id, categoria(descripcion), almacen(fila, columna)") \
                        .eq("id_producto", pid) \
                        .limit(1) \
                        .execute().data or [{}]
                    prod = prod_res[0] if prod_res else {}

                productos.append({
                    "producto_id": pid,
                    "nombre": plancha.get("producto_nombre") or prod.get("nombre"),
                    "descripcion": plancha.get("producto_descripcion") or prod.get("descripcion"),
                    "codigo": plancha.get("producto_codigo") or prod.get("codigo"),
                    "grosor": prod.get("grosor"),
                    "precio_unitario": prod.get("precio_unitario") or 0,
                    "categoria_id": plancha.get("categoria_id") or prod.get("categoria_id"),
                    "categoria": plancha.get("categoria") or (prod.get("categoria") or {}).get("descripcion"),
                    "almacen_fila": (prod.get("almacen") or {}).get("fila"),
                    "almacen_columna": (prod.get("almacen") or {}).get("columna"),
                    "cantidad_cliente": plancha.get("cantidad") or 1,
                    "stock_cantidad": prod.get("cantidad") or 0,
                    "origen": "corte_sin_merma",
                })

        if not productos:
            try:
                cortes_data = supabase.table("cortes") \
                    .select("producto_id, cantidad") \
                    .eq("carrito_id", carrito_id) \
                    .execute().data or []

                cortes_por_prod = {}
                for corte in cortes_data:
                    pid = corte.get("producto_id")
                    if not pid:
                        continue
                    cant = int(corte.get("cantidad") or 1)
                    cortes_por_prod[pid] = cortes_por_prod.get(pid, 0) + cant

                if cortes_por_prod:
                    datos = supabase.table("productos") \
                        .select("id_producto, nombre, descripcion, codigo, grosor, cantidad, precio_unitario, categoria_id, categoria(descripcion), almacen(fila, columna)") \
                        .in_("id_producto", list(cortes_por_prod.keys())) \
                        .execute().data or []

                    for prod in datos:
                        pid = prod.get("id_producto")
                        productos.append({
                            "producto_id": pid,
                            "nombre": prod.get("nombre"),
                            "descripcion": prod.get("descripcion"),
                            "codigo": prod.get("codigo"),
                            "grosor": prod.get("grosor"),
                            "precio_unitario": prod.get("precio_unitario") or 0,
                            "categoria_id": prod.get("categoria_id"),
                            "categoria": (prod.get("categoria") or {}).get("descripcion"),
                            "almacen_fila": (prod.get("almacen") or {}).get("fila"),
                            "almacen_columna": (prod.get("almacen") or {}).get("columna"),
                            "cantidad_cliente": cortes_por_prod.get(pid, 1),
                            "stock_cantidad": prod.get("cantidad") or 0,
                            "origen": "corte",
                        })
            except Exception:
                pass

        if not productos:
            return {
                "success": True,
                "solo_cortes": False,
                "message": "El cliente no agrego productos",
                "data": [],
                "carrito_id": carrito_id,
            }

        solo_cortes = all(p.get("origen") in ("corte", "corte_sin_merma") for p in productos)

        return {
            "success": True,
            "data": productos,
            "solo_cortes": solo_cortes,
            "carrito_id": carrito_id,
        }
    except Exception as exc:
        traceback.print_exc()
        return {"success": False, "message": str(exc), "data": []}


def descontar_stock_productos(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Descuenta stock en tabla productos segun items.
    """
    try:
        if not items:
            return {"success": False, "message": "Lista vacia", "actualizados": 0}

        actualizados = 0
        for item in items:
            producto_id = item.get("producto_id")
            cantidad = float(item.get("cantidad") or 0)
            if not producto_id or cantidad <= 0:
                continue

            res = supabase.table("productos") \
                .select("cantidad") \
                .eq("id_producto", producto_id) \
                .limit(1) \
                .execute()

            if not res.data:
                continue

            actual = float(res.data[0].get("cantidad") or 0)
            nuevo = int(max(actual - cantidad, 0))

            supabase.table("productos") \
                .update({"cantidad": nuevo}) \
                .eq("id_producto", producto_id) \
                .execute()

            actualizados += 1

        return {"success": True, "actualizados": actualizados}
    except Exception as exc:
        return {"success": False, "message": str(exc), "actualizados": 0}
