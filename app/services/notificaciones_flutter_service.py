"""
Servicio para notificaciones desde el modulo Flutter.
"""
from typing import Tuple, List, Any, Dict
from app.services.supabase_client import supabase


def obtener_notificaciones_usuario(usuario_id: str, limite: int = 20, no_leidas: bool = False) -> Tuple[bool, List[Dict[str, Any]]]:
    """Obtiene notificaciones para un usuario (limitado)."""
    try:
        query = supabase.table('notificacion').select('*').eq('id_cliente', usuario_id)
        if no_leidas:
            # asume campo 'leida' booleano
            query = query.eq('leida', False)
        if limite:
            query = query.limit(limite)

        res = query.execute()
        data = getattr(res, 'data', []) or []
        return True, data

    except Exception as e:
        print(f"[notificaciones_flutter_service] Error obtener_notificaciones_usuario: {e}")
        return False, []


def obtener_notificaciones_no_leidas_count(usuario_id: str) -> Tuple[bool, int]:
    """Cuenta las notificaciones no leídas de un usuario."""
    try:
        res = supabase.table('notificacion').select('id_notificacion', count='exact').eq('id_cliente', usuario_id).eq('leida', False).execute()
        count = getattr(res, 'count', None)
        if count is None:
            data = getattr(res, 'data', []) or []
            count = len(data)
        return True, int(count)
    except Exception as e:
        print(f"[notificaciones_flutter_service] Error obtener_notificaciones_no_leidas_count: {e}")
        return False, 0


def marcar_notificacion_como_leida(notificacion_id: str) -> Tuple[bool, Any]:
    """Marca una notificación como leída."""
    try:
        res = supabase.table('notificacion').update({'leida': True}).eq('id_notificacion', notificacion_id).execute()
        return True, res
    except Exception as e:
        print(f"[notificaciones_flutter_service] Error marcar_notificacion_como_leida: {e}")
        return False, str(e)


def marcar_todas_como_leidas(usuario_id: str) -> Tuple[bool, Any]:
    """Marca todas las notificaciones de un usuario como leídas."""
    try:
        res = supabase.table('notificacion').update({'leida': True}).eq('id_cliente', usuario_id).execute()
        return True, res
    except Exception as e:
        print(f"[notificaciones_flutter_service] Error marcar_todas_como_leidas: {e}")
        return False, str(e)
