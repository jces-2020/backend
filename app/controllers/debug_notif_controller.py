"""
Endpoint de debug para diagnosticar notificaciones
"""
from flask import Blueprint, jsonify, request
from app.services.supabase_client import supabase

debug_notif_bp = Blueprint('debug_notif', __name__)

@debug_notif_bp.route('/api/debug/notificaciones-tablas', methods=['GET'])
def debug_notificaciones():
    """Debug: devuelve contenido de ambas tablas y estado general."""
    try:
        # Tabla notificacion (nueva, para ENTREGA)
        notific_res = supabase.table('notificacion').select('*').execute()
        notific_data = getattr(notific_res, 'data', []) or []
        
        # Tabla notificacion (antigua)
        notif_trabajo_res = supabase.table('notificacion').select('*').execute()
        notif_trabajo_data = getattr(notif_trabajo_res, 'data', []) or []
        
        # Tabla estado_notificacion
        estado_res = supabase.table('estado_notificacion').select('*').execute()
        estado_data = getattr(estado_res, 'data', []) or []
        
        # Tabla carrito_compras con estado 'proceso'
        carrito_res = supabase.table('carrito_compras').select('*').execute()
        carrito_data = getattr(carrito_res, 'data', []) or []
        
        return jsonify({
            'success': True,
            'notificacion_count': len(notific_data),
            'notificacion_count': len(notif_trabajo_data),
            'estado_notificacion': estado_data,
            'carrito_proceso_count': len([c for c in carrito_data if c.get('estado') == 'proceso']),
            'notificacion_sample': notific_data[:3] if notific_data else [],
            'notificacion_sample': notif_trabajo_data[:3] if notif_trabajo_data else [],
            'carrito_sample': carrito_data[:3] if carrito_data else []
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@debug_notif_bp.route('/api/debug/notificaciones', methods=['GET'])
def debug_list_notificaciones():
    """Debug: simula /api/admin/notificaciones con logs detallados."""
    try:
        tipo_filter = (request.args.get('tipo') or 'ENTREGA').strip().upper()
        
        if tipo_filter == 'ENTREGA':
            res = supabase.table('notificacion').select('*').execute()
            tabla_usada = 'notificacion'
        else:
            res = supabase.table('notificacion').select('*').execute()
            tabla_usada = 'notificacion'
        
        notifs_raw = getattr(res, 'data', []) or []
        
        return jsonify({
            'success': True,
            'tabla_usada': tabla_usada,
            'tipo_filter': tipo_filter,
            'total_notificaciones': len(notifs_raw),
            'notificaciones': notifs_raw
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

