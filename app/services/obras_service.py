"""
Service: Gestión de Obras
Lógica de negocio para el manejo de obras y notificaciones de trabajo.
"""
from typing import List, Dict, Any, Optional
from services.supabase_client import supabase


def get_notificaciones_by_categoria(categoria: str, ocultar_atendidas: bool = True) -> List[Dict[str, Any]]:
    """
    Obtiene las notificaciones según categoría.
    
    Args:
        categoria: SERVICIO | OPTIMIZACION | ENTREGA
        ocultar_atendidas: Si True, oculta las notificaciones finalizadas
    
    Returns:
        Lista de notificaciones
    """
    try:
        # TODO: Implementar consulta a Supabase según tipo de notificación
        # Ajustar según la estructura de tu base de datos
        
        query = supabase.table("notificaciones").select("*")
        
        # Filtrar por categoría
        query = query.eq("tipo", categoria)
        
        # Filtrar por estado si se requiere
        if ocultar_atendidas:
            query = query.neq("estado", "FINALIZADO")
        
        result = query.execute()
        return result.data or []
    
    except Exception as e:
        print(f"Error obteniendo notificaciones: {e}")
        return []


def update_estado_notificacion(notif_id: str, nuevo_estado: str) -> bool:
    """
    Actualiza el estado de una notificación.
    
    Args:
        notif_id: ID de la notificación
        nuevo_estado: Nuevo estado (PENDIENTE | EN_PROCESO | FINALIZADO)
    
    Returns:
        True si se actualizó correctamente
    """
    try:
        result = supabase.table("notificaciones").update({
            "estado": nuevo_estado
        }).eq("id", notif_id).execute()
        
        return result.data is not None
    
    except Exception as e:
        print(f"Error actualizando estado: {e}")
        return False


def get_obras_stats() -> Dict[str, int]:
    """
    Obtiene estadísticas de obras.
    
    Returns:
        Diccionario con contadores de estados
    """
    try:
        # TODO: Implementar consulta de estadísticas
        stats = {
            "pendientes": 0,
            "en_proceso": 0,
            "finalizadas": 0
        }
        
        # Consultar cada estado
        # ...
        
        return stats
    
    except Exception as e:
        print(f"Error obteniendo estadísticas: {e}")
        return {"pendientes": 0, "en_proceso": 0, "finalizadas": 0}
