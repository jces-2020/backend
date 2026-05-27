"""
Servicio para manejar notificaciones de entrega.
Se usa después del pago aprobado para registrar entregas pendientes.
"""
from app.services.supabase_client import supabase
import json
from typing import Optional, Dict, Any


def crear_notificacion_entrega(
    cliente_id: str,
    carrito_id: str,
    nombre_cliente: str,
    cantidad_items: int,
    descripcion: Optional[str] = None
) -> Dict[str, Any]:
    """
    Crea una notificación de entrega en la tabla 'notificacion'.
    
    Args:
        cliente_id: UUID del cliente
        carrito_id: UUID del carrito
        nombre_cliente: Nombre del cliente para la notificación
        cantidad_items: Cantidad total de productos a entregar
        descripcion: Descripción operacional (ej: "Cantidad de productos a llevar")
    
    Returns:
        dict con {success: bool, id?: str, error?: str}
    """
    try:
        # Resolver estado_notificacion_id para 'Pendiente'
        estado_id = _get_estado_id_por_nombre('Pendiente')
        
        if not descripcion:
            descripcion = f"Cantidad de productos llevar: {cantidad_items}"
        
        notif_data = {
            'nombre': nombre_cliente,
            'descripcion': descripcion,
            'estado_notificacion_id': estado_id,
            'id_cliente': cliente_id,
            'tipo': 'entrega'  # Tipo de notificación para entregas
        }
        
        # Guardar información operacional en descripcion
        descripcion_final = f"{descripcion} (Carrito: {carrito_id})"
        notif_data['descripcion'] = descripcion_final
        
        res = supabase.table('notificacion').insert(notif_data).execute()
        
        if res.data:
            notif_id = res.data[0].get('id_notificacion')
            return {
                'success': True,
                'id': notif_id,
                'notificacion': res.data[0]
            }
        else:
            return {'success': False, 'error': 'No se pudo crear la notificación'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _get_estado_id_por_nombre(nombre: str) -> Optional[str]:
    """Obtiene el ID del estado_notificacion por nombre (ej: 'Pendiente')."""
    try:
        res = supabase.table('estado_notificacion').select('id_estado, descripcion').execute()
        nombre_norm = (nombre or '').strip().upper()
        for row in getattr(res, 'data', []) or []:
            desc = (row.get('descripcion') or '').strip().upper()
            if desc == nombre_norm:
                return row.get('id_estado')
        return None
    except Exception:
        return None


def obtener_notificaciones_entrega(
    ocultar_atendidas: bool = True,
    limite: Optional[int] = None
) -> Dict[str, Any]:
    """
    Obtiene todas las notificaciones de entrega pendientes de la tabla 'notificacion'.
    
    Args:
        ocultar_atendidas: Si True, excluye las marcadas como atendidas
        limite: Máximo número de resultados
    
    Returns:
        dict con {success: bool, notificaciones: list, error?: str}
    """
    try:
        q = supabase.table('notificacion').select('*')
        
        # Filtrar por tipo para sacar solo ENTREGA
        # Leeremos todas y filtraremos en Python por el JSON en descripcion
        res = q.execute()
        notifs = []
        
        for n in getattr(res, 'data', []) or []:
            try:
                meta = json.loads(n.get('descripcion') or '{}')
                if isinstance(meta, dict) and meta.get('tipo') == 'ENTREGA':
                    notifs.append(n)
            except Exception:
                # Si no es JSON, ignorar
                pass
        
        # Filtrar atendidas si se solicita
        if ocultar_atendidas:
            estado_atendida_id = _get_estado_id_por_nombre('Atendida')
            if estado_atendida_id:
                notifs = [n for n in notifs if n.get('estado_notificacion_id') != estado_atendida_id]
        
        # Aplicar límite
        if limite:
            notifs = notifs[:limite]
        
        return {
            'success': True,
            'notificaciones': notifs
        }
    
    except Exception as e:
        return {'success': False, 'error': str(e), 'notificaciones': []}


def actualizar_estado_notificacion(notif_id: str, nuevo_estado: str) -> Dict[str, Any]:
    """
    Actualiza el estado de una notificación de entrega.
    
    Args:
        notif_id: ID de la notificación
        nuevo_estado: Nombre del estado (ej: 'En proceso', 'Finalizando', 'Atendida')
    
    Returns:
        dict con {success: bool, error?: str}
    """
    try:
        estado_id = _get_estado_id_por_nombre(nuevo_estado)
        if not estado_id:
            return {'success': False, 'error': f'Estado "{nuevo_estado}" no configurado'}
        
        # Verificar que exista la notificación
        check = supabase.table('notificacion').select('id_notificacion').eq('id_notificacion', notif_id).limit(1).execute()
        if not check.data:
            return {'success': False, 'error': 'Notificación no encontrada'}
        
        upd = supabase.table('notificacion').update({'estado_notificacion_id': estado_id}).eq('id_notificacion', notif_id).execute()
        
        return {'success': True, 'estado': nuevo_estado}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}
