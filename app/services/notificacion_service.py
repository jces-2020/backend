"""
Servicio para gestión de notificaciones de trabajo/servicios.
Registra nuevas notificaciones y las emite por Pusher en tiempo real.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from app.services.supabase_client import supabase
from app.services.pusher_service import enviar_evento_pusher


# ─────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────

def _obtener_nombre_cliente(id_cliente: str) -> Optional[str]:
    """Obtiene el nombre del cliente desde la tabla cliente."""
    try:
        resp = (
            supabase.table('cliente')
            .select('nombre')
            .eq('id_cliente', id_cliente)
            .single()
            .execute()
        )
        data = getattr(resp, 'data', None)
        return data.get('nombre') if isinstance(data, dict) else None
    except Exception as e:
        print(f"[notificacion_service] Error obteniendo cliente: {e}")
        return None


def _obtener_nombre_estado(estado_id: str) -> Optional[str]:
    """Obtiene la descripción del estado de notificación."""
    try:
        resp = (
            supabase.table('estado_notificacion')
            .select('descripcion')
            .eq('id_estado', estado_id)
            .single()
            .execute()
        )
        data = getattr(resp, 'data', None)
        return data.get('descripcion') if isinstance(data, dict) else None
    except Exception as e:
        print(f"[notificacion_service] Error obteniendo estado: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Pusher helpers
# ─────────────────────────────────────────────────────────────

def notificar_nuevo_servicio(
    nombre: Optional[str],
    descripcion: Optional[str] = None,
    tipo: Optional[str] = None,
    nombre_cliente: Optional[str] = None,
    id_notificacion: Optional[str] = None,
) -> bool:
    """Dispara evento Pusher cuando se crea una nueva notificación de servicio."""
    mensaje = f"Nuevo servicio: {nombre or 'Sin nombre'}"
    if nombre_cliente:
        mensaje = f"Nuevo servicio para {nombre_cliente}: {nombre or 'Sin nombre'}"

    return enviar_evento_pusher({
        "tipo": "notificacion_creada",
        "accion": "NUEVO_SERVICIO",
        "mensaje": mensaje,
        "nombre": nombre,
        "descripcion": descripcion,
        "tipo_servicio": tipo,
        "cliente": nombre_cliente,
        "id_notificacion": id_notificacion,
        "timestamp": datetime.utcnow().isoformat(),
    })


def notificar_estado_actualizado(
    nombre: Optional[str],
    estado: Optional[str] = None,
    nombre_cliente: Optional[str] = None,
    id_notificacion: Optional[str] = None,
) -> bool:
    """Dispara evento Pusher cuando cambia el estado de una notificación."""
    mensaje = f"Servicio actualizado: {nombre or 'Sin nombre'}"
    if estado:
        mensaje = f"Servicio '{nombre or 'Sin nombre'}' cambió a: {estado}"

    return enviar_evento_pusher({
        "tipo": "notificacion_actualizada",
        "accion": "ESTADO_ACTUALIZADO",
        "mensaje": mensaje,
        "nombre": nombre,
        "estado": estado,
        "cliente": nombre_cliente,
        "id_notificacion": id_notificacion,
        "timestamp": datetime.utcnow().isoformat(),
    })


# ─────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────

def crear_notificacion(datos: Dict[str, Any]) -> Dict[str, Any]:
    """Crea una nueva notificación en la base de datos y emite evento Pusher."""
    try:
        payload = {
            'nombre': datos.get('nombre'),
            'descripcion': datos.get('descripcion'),
            'tipo': datos.get('tipo'),
            'estado_notificacion_id': datos.get('estado_notificacion_id'),
            'id_cliente': datos.get('id_cliente'),
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        resp = supabase.table('notificacion').insert(payload).execute()
        err = getattr(resp, 'error', None)
        data = getattr(resp, 'data', None)

        if err:
            print(f"[notificacion_service] Error insertando: {err}")
            return {'success': False, 'message': str(err)}

        notificacion = (data[0] if isinstance(data, list) and data else data) or {}

        nombre_cliente = None
        if datos.get('id_cliente'):
            nombre_cliente = _obtener_nombre_cliente(datos['id_cliente'])

        notificar_nuevo_servicio(
            nombre=notificacion.get('nombre') or datos.get('nombre'),
            descripcion=notificacion.get('descripcion') or datos.get('descripcion'),
            tipo=notificacion.get('tipo') or datos.get('tipo'),
            nombre_cliente=nombre_cliente,
            id_notificacion=str(notificacion.get('id_notificacion', '')),
        )

        print(f"[notificacion_service] Notificación creada: {notificacion.get('id_notificacion')}")
        return {'success': True, 'data': notificacion, 'message': 'Notificación creada exitosamente'}

    except Exception as e:
        print(f"[notificacion_service] Error en crear_notificacion: {e}")
        return {'success': False, 'message': str(e)}


def obtener_notificaciones(
    limite: int = 50,
    offset: int = 0,
    estado_id: Optional[str] = None,
    id_cliente: Optional[str] = None,
    tipo: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista notificaciones con filtros opcionales."""
    try:
        query = supabase.table('notificacion').select('*')

        if estado_id:
            query = query.eq('estado_notificacion_id', estado_id)
        if id_cliente:
            query = query.eq('id_cliente', id_cliente)
        if tipo:
            query = query.eq('tipo', tipo)

        resp = query.order('id_notificacion', desc=True).range(offset, offset + limite - 1).execute()
        err = getattr(resp, 'error', None)
        data = getattr(resp, 'data', None)

        if err:
            print(f"[notificacion_service] Error listando: {err}")
            return []

        print(f"[notificacion_service] Obtenidas {len(data or [])} notificaciones")
        return data or []

    except Exception as e:
        print(f"[notificacion_service] Error en obtener_notificaciones: {e}")
        return []


def obtener_notificacion_por_id(id_notificacion: str) -> Optional[Dict[str, Any]]:
    """Obtiene una notificación por su ID."""
    try:
        resp = (
            supabase.table('notificacion')
            .select('*')
            .eq('id_notificacion', id_notificacion)
            .single()
            .execute()
        )
        err = getattr(resp, 'error', None)
        data = getattr(resp, 'data', None)
        if err or not data:
            return None
        return data
    except Exception as e:
        print(f"[notificacion_service] Error en obtener_notificacion_por_id: {e}")
        return None


def actualizar_estado_notificacion(
    id_notificacion: str,
    estado_notificacion_id: str,
) -> Dict[str, Any]:
    """Actualiza el estado de una notificación y emite evento Pusher."""
    try:
        actual = obtener_notificacion_por_id(id_notificacion)
        if not actual:
            return {'success': False, 'message': 'Notificación no encontrada'}

        resp = (
            supabase.table('notificacion')
            .update({'estado_notificacion_id': estado_notificacion_id})
            .eq('id_notificacion', id_notificacion)
            .execute()
        )
        err = getattr(resp, 'error', None)
        data = getattr(resp, 'data', None)

        if err:
            return {'success': False, 'message': str(err)}

        notificacion = (data[0] if isinstance(data, list) and data else data) or actual

        nombre_estado = _obtener_nombre_estado(estado_notificacion_id)
        nombre_cliente = None
        if actual.get('id_cliente'):
            nombre_cliente = _obtener_nombre_cliente(actual['id_cliente'])

        notificar_estado_actualizado(
            nombre=actual.get('nombre'),
            estado=nombre_estado,
            nombre_cliente=nombre_cliente,
            id_notificacion=id_notificacion,
        )

        return {'success': True, 'data': notificacion, 'message': 'Estado actualizado exitosamente'}

    except Exception as e:
        print(f"[notificacion_service] Error en actualizar_estado_notificacion: {e}")
        return {'success': False, 'message': str(e)}
