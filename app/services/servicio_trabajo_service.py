"""
Service: Servicio Trabajo
Lógica de negocio para servicios técnicos.
"""
from typing import List, Dict, Any, Optional
from services.supabase_client import supabase


def buscar_productos_disponibles(busqueda: str = "", tipo: str = "PRODUCTOS") -> List[Dict[str, Any]]:
    """
    Busca productos disponibles para el servicio.
    
    Args:
        busqueda: Término de búsqueda (nombre o código)
        tipo: Tipo de sección (REMETRO | RETAZO | PRODUCTOS)
    
    Returns:
        Lista de productos
    """
    try:
        query = supabase.table("producto").select("*")
        
        if busqueda:
            # Buscar por nombre o código
            query = query.or_(f"nombre.ilike.%{busqueda}%,codigo.ilike.%{busqueda}%")
        
        result = query.execute()
        return result.data or []
    
    except Exception as e:
        print(f"Error buscando productos: {e}")
        return []


def guardar_servicio_trabajo(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Guarda un registro de servicio técnico.
    
    Args:
        data: Diccionario con datos del servicio
    
    Returns:
        Datos del servicio guardado o None si falla
    """
    try:
        # TODO: Implementar guardado en base de datos
        # Estructura sugerida:
        # - Tabla: servicios_trabajo
        # - Campos: id, cliente, fecha, productos_seleccionados, barras, cortes, etc.
        
        servicio_data = {
            "cliente": data.get("cliente"),
            "fecha": data.get("fecha"),
            "productos_seleccionados": data.get("productos_seleccionados", []),
            "estado": "PENDIENTE"
        }
        
        result = supabase.table("servicios_trabajo").insert(servicio_data).execute()
        return result.data[0] if result.data else None
    
    except Exception as e:
        print(f"Error guardando servicio: {e}")
        return None


def get_servicio_by_id(servicio_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene el detalle de un servicio por ID.
    
    Args:
        servicio_id: ID del servicio
    
    Returns:
        Datos del servicio o None si no existe
    """
    try:
        result = supabase.table("servicios_trabajo").select("*").eq("id", servicio_id).execute()
        return result.data[0] if result.data else None
    
    except Exception as e:
        print(f"Error obteniendo servicio: {e}")
        return None


def actualizar_instalacion(servicio_id: str, data: Dict[str, Any]) -> bool:
    """
    Actualiza los datos de instalación de un servicio.
    
    Args:
        servicio_id: ID del servicio
        data: Datos de instalación
    
    Returns:
        True si se actualizó correctamente
    """
    try:
        instalacion_data = {
            "fecha_instalacion": data.get("fecha"),
            "tecnico_asignado": data.get("tecnico"),
            "observaciones": data.get("observaciones"),
            "imagenes": data.get("imagenes", [])
        }
        
        result = supabase.table("servicios_trabajo").update(instalacion_data).eq("id", servicio_id).execute()
        return result.data is not None
    
    except Exception as e:
        print(f"Error actualizando instalación: {e}")
        return False
