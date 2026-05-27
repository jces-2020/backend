"""
Servicio para productos de entrega.
"""
import json
import re
import traceback
from typing import Dict, Any, List
from app.services.supabase_client import supabase
from app.services.entrega_reporte_service import obtener_reporte_temporal


def _obtener_carrito_id_por_cliente_fallback(notificacion_id: str, descripcion: str) -> str:
    """
    Fallback inteligente: busca el carrito del cliente que mejor coincida
    con los productos mencionados en la descripcion.
    """
    try:
        # Obtener id_cliente/cliente_id de la notificacion (compatibilidad)
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
        
        # Buscar todos los carritos activos del cliente
        carritos = supabase.table("carrito_compras") \
            .select("id_carrito, estado") \
            .eq("cliente_id", cliente_id) \
            .in_("estado", ["pendiente", "pagado", "instalado", "en proceso", "inicio", "listo"]) \
            .execute().data or []
        
        if not carritos:
            return ""
        
        if len(carritos) == 1:
            return carritos[0]["id_carrito"]
        
        # Si hay multiples carritos, calcular score basado en coincidencia de productos
        mejor_carrito = None
        mejor_score = -1
        
        # Extraer nombres de productos de la descripcion
        desc_lower = descripcion.lower()
        palabras_desc = set(re.findall(r'\b\w+\b', desc_lower))
        
        for carrito in carritos:
            carrito_id = carrito["id_carrito"]
            estado = carrito["estado"]
            
            # Obtener productos del carrito
            items = supabase.table("productos_carrito") \
                .select("producto_id") \
                .eq("carrito_id", carrito_id) \
                .execute().data or []
            
            if not items:
                continue
            
            producto_ids = [it["producto_id"] for it in items if it.get("producto_id")]
            
            if producto_ids:
                productos = supabase.table("productos") \
                    .select("nombre") \
                    .in_("id_producto", producto_ids) \
                    .execute().data or []
                
                # Calcular score
                score = 0
                for prod in productos:
                    nombre = (prod.get("nombre") or "").lower()
                    # 5 puntos si el nombre completo esta en la descripcion
                    if nombre and nombre in desc_lower:
                        score += 5
                    # 1 punto por cada palabra que coincida
                    else:
                        palabras_prod = set(re.findall(r'\b\w+\b', nombre))
                        score += len(palabras_prod & palabras_desc)
                
                # Bonus por estado (preferir 'pagado' > 'instalado' > 'pendiente')
                if estado == "pagado":
                    score += 2
                elif estado == "instalado":
                    score += 1
                
                # Bonus por cantidad de items
                score += len(items) * 0.5
                
                if score > mejor_score:
                    mejor_score = score
                    mejor_carrito = carrito_id
        
        return mejor_carrito or ""
    
    except Exception as e:
        print(f"Error en fallback de carrito: {e}")
        return ""


def _obtener_carrito_id(notificacion_id: str) -> str:
    notif_result = supabase.table("notificacion") \
        .select("descripcion") \
        .eq("id_notificacion", notificacion_id) \
        .limit(1) \
        .execute()

    if not notif_result.data:
        return ""

    descripcion = (notif_result.data[0] or {}).get("descripcion", "{}")

    # Si Supabase devuelve el campo como dict (columna JSONB), leerlo directo
    if isinstance(descripcion, dict):
        carrito_id = descripcion.get("carrito_id") or ""
        if carrito_id:
            return carrito_id
        # Dict sin carrito_id (p.ej. solo metadatos de lock): usar fallback por cliente
        return _obtener_carrito_id_por_cliente_fallback(notificacion_id, "")

    # Intentar JSON primero
    try:
        meta = json.loads(descripcion)
        if isinstance(meta, dict):
            carrito_id = meta.get("carrito_id") or ""
            if carrito_id:
                return carrito_id
    except Exception:
        pass

    # Fallback para descripciones como: "Pago ... (Carrito: <uuid>)"
    if isinstance(descripcion, str):
        match = re.search(r"Carrito:\s*([0-9a-fA-F-]{36})", descripcion)
        if match:
            return match.group(1)

    # Fallback inteligente por cliente
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
                "carrito_id": ""
            }

        items = supabase.table("productos_carrito") \
            .select("producto_id, cantidad") \
            .eq("carrito_id", carrito_id) \
            .execute().data or []

        producto_ids = [it.get("producto_id") for it in items if it.get("producto_id")]
        productos = []
        productos_map = {}

        if producto_ids:
            datos = supabase.table("productos") \
                .select("id_producto, nombre, descripcion, codigo, grosor, cantidad, precio_unitario, categoria_id, categoria(descripcion), almacen(fila, columna)") \
                .in_("id_producto", producto_ids) \
                .execute().data or []
            productos_map = {p.get("id_producto"): p for p in datos}

        for it in items:
            pid = it.get("producto_id")
            prod = productos_map.get(pid, {})
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
                "cantidad_cliente": it.get("cantidad") or 0,
                "stock_cantidad": prod.get("cantidad") or 0,
                "origen": "plancha"
            })

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
                    prod = supabase.table("productos") \
                        .select("id_producto, nombre, descripcion, codigo, grosor, cantidad, precio_unitario, categoria_id, categoria(descripcion), almacen(fila, columna)") \
                        .eq("id_producto", pid) \
                        .limit(1) \
                        .execute().data or [{}]
                    prod = prod[0] if prod else {}

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
                    "origen": "corte_sin_merma"
                })

        if not productos:
            # Intentar obtener productos desde cortes asociados al carrito
            try:
                cortes_data = supabase.table("cortes") \
                    .select("producto_id, cantidad") \
                    .eq("carrito_id", carrito_id) \
                    .execute().data or []

                # Agrupar por producto_id sumando cantidades
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
                            "origen": "corte"
                        })
            except Exception:
                pass

        if not productos:
            return {
                "success": True,
                "solo_cortes": False,
                "message": "El cliente no agrego productos",
                "data": [],
                "carrito_id": carrito_id
            }

        # Determinar si todos los productos vienen de cortes
        solo_cortes = all(p.get("origen") == "corte" for p in productos)

        return {"success": True, "data": productos, "solo_cortes": solo_cortes, "carrito_id": carrito_id}
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
            nuevo = int(max(actual - cantidad, 0))  # Convertir a int

            supabase.table("productos") \
                .update({"cantidad": nuevo}) \
                .eq("id_producto", producto_id) \
                .execute()

            actualizados += 1

        return {"success": True, "actualizados": actualizados}
    except Exception as exc:
        return {"success": False, "message": str(exc), "actualizados": 0}
