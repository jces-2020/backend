"""
Servicio para obtener cortes personalizados para producción.
Se usa para mostrar los cortes que debe realizar el personal.
"""
from app.services.supabase_client import supabase
from typing import Optional, Dict, Any, List


def obtener_cortes_por_carrito(carrito_id: str) -> Dict[str, Any]:
    """
    Obtiene todos los cortes asociados a un carrito específico.
    
    Args:
        carrito_id: UUID del carrito
    
    Returns:
        dict con {success: bool, cortes: list, error?: str}
    """
    try:
        # Obtener cortes con información del producto
        cortes_result = supabase.table("cortes") \
            .select("*, productos(nombre, codigo, descripcion, categoria_id, categoria(descripcion), almacen(fila, columna))") \
            .eq("carrito_id", carrito_id) \
            .execute()
        
        cortes = cortes_result.data or []
        
        # Si la consulta compleja falla, intentar simple
        if not cortes:
            cortes_result = supabase.table("cortes") \
                .select("*") \
                .eq("carrito_id", carrito_id) \
                .execute()
            
            cortes = cortes_result.data or []
        
        # Formatear datos para facilitar uso en frontend
        cortes_formateados = []
        for corte in cortes:
            producto = corte.get("productos") or {}
            categoria = producto.get("categoria") or {} if isinstance(producto, dict) else {}
            almacen = producto.get("almacen") or {} if isinstance(producto, dict) else {}
            
            cortes_formateados.append({
                "id_corte": corte.get("id_corte"),
                "ancho_cm": corte.get("ancho_cm"),
                "alto_cm": corte.get("alto_cm"),
                "cantidad": corte.get("cantidad"),
                "estado": corte.get("estado"),
                "fecha_registro": corte.get("fecha_registro"),
                "producto_id": corte.get("producto_id"),
                "producto_nombre": producto.get("nombre") if isinstance(producto, dict) else None,
                "producto_codigo": producto.get("codigo") if isinstance(producto, dict) else None,
                "producto_descripcion": producto.get("descripcion") if isinstance(producto, dict) else None,
                "categoria_id": producto.get("categoria_id") if isinstance(producto, dict) else None,
                "categoria": categoria.get("descripcion") if isinstance(categoria, dict) else None,
                "producto_almacen_fila": almacen.get("fila") if isinstance(almacen, dict) else None,
                "producto_almacen_columna": almacen.get("columna") if isinstance(almacen, dict) else None,
                "area_m2": round((corte.get("ancho_cm", 0) * corte.get("alto_cm", 0)) / 10000, 4)
            })
        
        return {
            "success": True,
            "cortes": cortes_formateados,
            "total": len(cortes_formateados)
        }
    
    except Exception as e:
        import traceback
        print(f"[ERROR] obtener_cortes_por_carrito({carrito_id}): {str(e)}")
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "cortes": []
        }


def obtener_cortes_por_cliente(cliente_id: str, solo_pendientes: bool = True) -> Dict[str, Any]:
    """
    Obtiene todos los cortes de un cliente específico.
    
    Args:
        cliente_id: UUID del cliente
        solo_pendientes: Si True, solo retorna cortes con estado 'pendiente'
    
    Returns:
        dict con {success: bool, cortes: list, error?: str}
    """
    try:
        # Primero obtener todos los carritos del cliente
        carritos_result = supabase.table("carrito_compras") \
            .select("id_carrito, estado") \
            .eq("cliente_id", cliente_id) \
            .execute()
        
        carrito_ids = [c.get("id_carrito") for c in (carritos_result.data or [])]
        
        if not carrito_ids:
            return {
                "success": True,
                "cortes": [],
                "total": 0
            }
        
        # Obtener cortes de esos carritos
        query = supabase.table("cortes") \
            .select("*, productos(nombre, codigo, descripcion, categoria_id, categoria(descripcion), almacen(fila, columna))") \
            .in_("carrito_id", carrito_ids)
        
        if solo_pendientes:
            query = query.eq("estado", "pendiente")
        
        cortes_result = query.execute()
        cortes = cortes_result.data or []
        
        # Si la consulta compleja falla, intentar simple
        if not cortes and len(carrito_ids) > 0:
            query = supabase.table("cortes") \
                .select("*") \
                .in_("carrito_id", carrito_ids)
            
            if solo_pendientes:
                query = query.eq("estado", "pendiente")
            
            cortes_result = query.execute()
            cortes = cortes_result.data or []
        
        # Formatear
        cortes_formateados = []
        for corte in cortes:
            producto = corte.get("productos") or {}
            categoria = producto.get("categoria") or {} if isinstance(producto, dict) else {}
            almacen = producto.get("almacen") or {} if isinstance(producto, dict) else {}
            
            cortes_formateados.append({
                "id_corte": corte.get("id_corte"),
                "ancho_cm": corte.get("ancho_cm"),
                "alto_cm": corte.get("alto_cm"),
                "cantidad": corte.get("cantidad"),
                "estado": corte.get("estado"),
                "fecha_registro": corte.get("fecha_registro"),
                "carrito_id": corte.get("carrito_id"),
                "producto_id": corte.get("producto_id"),
                "producto_nombre": producto.get("nombre") if isinstance(producto, dict) else None,
                "producto_codigo": producto.get("codigo") if isinstance(producto, dict) else None,
                "producto_descripcion": producto.get("descripcion") if isinstance(producto, dict) else None,
                "categoria_id": producto.get("categoria_id") if isinstance(producto, dict) else None,
                "categoria": categoria.get("descripcion") if isinstance(categoria, dict) else None,
                "producto_almacen_fila": almacen.get("fila") if isinstance(almacen, dict) else None,
                "producto_almacen_columna": almacen.get("columna") if isinstance(almacen, dict) else None,
                "area_m2": round((corte.get("ancho_cm", 0) * corte.get("alto_cm", 0)) / 10000, 4)
            })
        
        return {
            "success": True,
            "cortes": cortes_formateados,
            "total": len(cortes_formateados)
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "cortes": []
        }


def obtener_cortes_agrupados_por_producto(carrito_id: str) -> Dict[str, Any]:
    """
    Obtiene cortes agrupados por producto para facilitar producción.
    
    Args:
        carrito_id: UUID del carrito
    
    Returns:
        dict con {success: bool, productos: list[{producto, cortes: list}], error?: str}
    """
    try:
        resultado = obtener_cortes_por_carrito(carrito_id)
        
        if not resultado.get("success"):
            return resultado
        
        cortes = resultado.get("cortes", [])
        
        # Agrupar por producto
        productos_dict = {}
        for corte in cortes:
            producto_id = corte.get("producto_id")
            
            if producto_id not in productos_dict:
                productos_dict[producto_id] = {
                    "producto_id": producto_id,
                    "producto_nombre": corte.get("producto_nombre"),
                    "producto_codigo": corte.get("producto_codigo"),
                    "producto_descripcion": corte.get("producto_descripcion"),
                    "categoria_id": corte.get("categoria_id"),
                    "categoria": corte.get("categoria"),
                    "producto_almacen_fila": corte.get("producto_almacen_fila"),
                    "producto_almacen_columna": corte.get("producto_almacen_columna"),
                    "cortes": [],
                    "total_cortes": 0,
                    "area_total_m2": 0
                }
            
            productos_dict[producto_id]["cortes"].append({
                "id_corte": corte.get("id_corte"),
                "ancho_cm": corte.get("ancho_cm"),
                "alto_cm": corte.get("alto_cm"),
                "cantidad": corte.get("cantidad"),
                "estado": corte.get("estado"),
                "fecha_registro": corte.get("fecha_registro"),
                "area_m2": corte.get("area_m2")
            })
            
            productos_dict[producto_id]["total_cortes"] += corte.get("cantidad", 0)
            productos_dict[producto_id]["area_total_m2"] += corte.get("area_m2", 0) * corte.get("cantidad", 0)
        
        # Convertir a lista
        productos_list = list(productos_dict.values())
        
        # Redondear áreas totales
        for prod in productos_list:
            prod["area_total_m2"] = round(prod["area_total_m2"], 4)
        
        return {
            "success": True,
            "productos": productos_list,
            "total_productos": len(productos_list)
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "productos": []
        }


def actualizar_estado_corte(corte_id: str, nuevo_estado: str) -> Dict[str, Any]:
    """
    Actualiza el estado de un corte específico.
    
    Args:
        corte_id: UUID del corte
        nuevo_estado: Nuevo estado (ej: 'en_proceso', 'completado', 'pendiente')
    
    Returns:
        dict con {success: bool, error?: str}
    """
    try:
        # Verificar que existe
        check = supabase.table("cortes") \
            .select("id_corte") \
            .eq("id_corte", corte_id) \
            .limit(1) \
            .execute()
        
        if not check.data:
            return {"success": False, "error": "Corte no encontrado"}
        
        # Actualizar
        update_result = supabase.table("cortes") \
            .update({"estado": nuevo_estado}) \
            .eq("id_corte", corte_id) \
            .execute()
        
        return {"success": True, "estado": nuevo_estado}
    
    except Exception as e:
        return {"success": False, "error": str(e)}
def actualizar_estados_cortes_carrito(carrito_id: str, nuevo_estado: str) -> Dict[str, Any]:
    """
    Actualiza el estado de todos los cortes de un carrito.
    
    Args:
        carrito_id: UUID del carrito
        nuevo_estado: Nuevo estado para todos los cortes
    
    Returns:
        dict con {success: bool, actualizados: int, error?: str}
    """
    try:
        update_result = supabase.table("cortes") \
            .update({"estado": nuevo_estado}) \
            .eq("carrito_id", carrito_id) \
            .execute()
        
        cantidad_actualizada = len(update_result.data or [])
        
        return {
            "success": True,
            "actualizados": cantidad_actualizada,
            "estado": nuevo_estado
        }
    
    except Exception as e:
        return {"success": False, "error": str(e), "actualizados": 0}


def eliminar_cortes(ids_corte: List[str]) -> Dict[str, Any]:
    """
    Elimina cortes por lista de IDs.

    Args:
        ids_corte: Lista de UUIDs.

    Returns:
        dict con {success: bool, eliminados: int, error?: str}
    """
    try:
        if not ids_corte:
            return {"success": False, "error": "Lista de cortes vacia", "eliminados": 0}

        result = supabase.table("cortes") \
            .delete() \
            .in_("id_corte", ids_corte) \
            .execute()

        eliminados = len(result.data or [])
        return {"success": True, "eliminados": eliminados}
    except Exception as e:
        return {"success": False, "error": str(e), "eliminados": 0}


def reducir_cantidad_corte(corte_id: str, cantidad: int = 1) -> Dict[str, Any]:
    """
    Reduce la cantidad de un corte en 'cantidad' unidades.
    Si la cantidad resultante es <= 0, elimina el registro.

    Args:
        corte_id: UUID del corte.
        cantidad: Unidades a descontar (default: 1).

    Returns:
        dict con {success: bool, eliminado: bool, nueva_cantidad: int}
    """
    try:
        result = supabase.table("cortes") \
            .select("id_corte, cantidad") \
            .eq("id_corte", corte_id) \
            .single() \
            .execute()

        if not result.data:
            return {"success": False, "error": "Corte no encontrado"}

        cantidad_actual = int(result.data.get("cantidad", 0) or 0)
        nueva_cantidad = cantidad_actual - cantidad

        if nueva_cantidad <= 0:
            supabase.table("cortes") \
                .delete() \
                .eq("id_corte", corte_id) \
                .execute()
            return {"success": True, "eliminado": True, "nueva_cantidad": 0}

        supabase.table("cortes") \
            .update({"cantidad": nueva_cantidad}) \
            .eq("id_corte", corte_id) \
            .execute()

        return {"success": True, "eliminado": False, "nueva_cantidad": nueva_cantidad}
    except Exception as e:
        return {"success": False, "error": str(e)}
