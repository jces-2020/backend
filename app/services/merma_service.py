"""Servicio para consultas de mermas."""
from typing import Dict, Any, List
from app.services.supabase_client import supabase




def obtener_merma_por_categoria(categoria_id: str) -> Dict[str, Any]:
    """
    Obtiene registros de merma por categoria.


    Args:
        categoria_id: UUID de categoria.


    Returns:
        dict con {success: bool, data: list, message?: str}
    """
    try:
        resultado = supabase.table("merma") \
            .select("id_merma, id_categoria, ancho_cm, alto_cm, lugar, nombre, descripci\u00f3n, cantidad, area, fecha_registro") \
            .eq("id_categoria", categoria_id) \
            .execute()


        data = resultado.data or []
        return {
            "success": True,
            "data": data,
            "total": len(data)
        }
    except Exception as exc:
        import traceback
        print(f"[ERROR] obtener_merma_por_categoria({categoria_id}): {str(exc)}")
        traceback.print_exc()
        return {
            "success": False,
            "message": str(exc),
            "data": []
        }




def eliminar_mermas(ids_merma: List[str]) -> Dict[str, Any]:
    """
    Elimina mermas por lista de IDs.


    Args:
        ids_merma: Lista de UUIDs.


    Returns:
        dict con {success: bool, eliminados: int, message?: str}
    """
    try:
        if not ids_merma:
            return {"success": False, "message": "Lista de mermas vacia", "eliminados": 0}


        result = supabase.table("merma") \
            .delete() \
            .in_("id_merma", ids_merma) \
            .execute()


        eliminados = len(result.data or [])
        return {"success": True, "eliminados": eliminados}
    except Exception as exc:
        return {"success": False, "message": str(exc), "eliminados": 0}




def buscar_merma_por_medidas(ancho_cm: float, alto_cm: float, tolerancia: float = 10.0, id_categoria: str = None) -> Dict[str, Any]:
    """
    Busca merma disponible por medidas con tolerancia.


    Args:
        ancho_cm: Ancho requerido en cm
        alto_cm: Alto requerido en cm
        tolerancia: Tolerancia en cm (default: 10cm)
        id_categoria: UUID de categoria (opcional)


    Returns:
        dict con {success: bool, mermas: list, total: int}
    """
    try:
        print(f"[MERMA_SERVICE] Buscando merma: ancho={ancho_cm}+/-{tolerancia}, alto={alto_cm}+/-{tolerancia}")


        # Calcular rangos con tolerancia
        ancho_min = ancho_cm
        ancho_max = ancho_cm + tolerancia
        alto_min = alto_cm
        alto_max = alto_cm + tolerancia


        # Construir query
        query = supabase.table("merma") \
            .select("id_merma, ancho_cm, alto_cm, lugar, nombre, cantidad, descripci\u00f3n, area, fecha_registro, id_categoria, categoria!fk_merma_categoria(descripcion)") \
            .gte("ancho_cm", ancho_min) \
            .lte("ancho_cm", ancho_max) \
            .gte("alto_cm", alto_min) \
            .lte("alto_cm", alto_max) \
            .gt("cantidad", 0)


        # Filtrar por categoria si se especifica
        if id_categoria:
            query = query.eq("id_categoria", id_categoria)


        # Ordenar por area (mas pequeno primero para optimizar uso)
        query = query.order("area", desc=False)


        result = query.execute()
        mermas = result.data or []


        print(f"[MERMA_SERVICE] OK Encontradas {len(mermas)} mermas disponibles")


        return {
            "success": True,
            "mermas": mermas,
            "total": len(mermas)
        }


    except Exception as e:
        print(f"[MERMA_SERVICE] ERROR: {str(e)}")
        return {
            "success": False,
            "message": str(e),
            "mermas": [],
            "total": 0
        }




def reducir_cantidad_merma(id_merma: str, cantidad: int = 1) -> Dict[str, Any]:
    """
    Reduce la cantidad de una merma en 'cantidad' unidades.
    Si la cantidad resultante es <= 0, elimina el registro.


    Args:
        id_merma: UUID de la merma.
        cantidad: Unidades a descontar (default: 1).


    Returns:
        dict con {success: bool, eliminado: bool, nueva_cantidad: int}
    """
    try:
        r = supabase.table("merma") \
            .select("id_merma, cantidad") \
            .eq("id_merma", id_merma) \
            .single() \
            .execute()


        if not r.data:
            return {"success": False, "message": "Merma no encontrada"}


        nueva = int(r.data.get("cantidad", 0) or 0) - cantidad


        if nueva <= 0:
            supabase.table("merma").delete().eq("id_merma", id_merma).execute()
            return {"success": True, "eliminado": True, "nueva_cantidad": 0}
        else:
            supabase.table("merma").update({"cantidad": nueva}).eq("id_merma", id_merma).execute()
            return {"success": True, "eliminado": False, "nueva_cantidad": nueva}


    except Exception as exc:
        return {"success": False, "message": str(exc)}




def obtener_categorias_merma() -> Dict[str, Any]:
    """
    Obtiene todas las categorias disponibles.


    Returns:
        dict con {success: bool, categorias: list}
    """
    try:
        result = supabase.table("categoria").select("id_categoria, descripcion").execute()
        return {
            "success": True,
            "categorias": result.data or []
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "categorias": []
        }




