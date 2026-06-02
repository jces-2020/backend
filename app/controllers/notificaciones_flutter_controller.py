"""
Controlador de Notificaciones para Flutter
Endpoints REST para obtener y gestionar notificaciones de la BD
"""

from flask import Blueprint, request, jsonify
from typing import Optional, Dict, Any
from app.services.notificaciones_flutter_service import (
    obtener_notificaciones_usuario,
    obtener_notificaciones_no_leidas_count,
    marcar_notificacion_como_leida,
    marcar_todas_como_leidas
)

notificaciones_flutter_bp = Blueprint('notificaciones_flutter', __name__, url_prefix='/api/flutter/notificaciones')


@notificaciones_flutter_bp.route('/obtener', methods=['GET'])
def obtener_notificaciones():
    """
    GET /api/flutter/notificaciones/obtener
    Obtiene las notificaciones del usuario desde la BD
    
    Query params:
        - usuario_id: ID del usuario (requerido)
        - limite: número de notificaciones (default: 20)
        - no_leidas: true/false para filtrar solo no leídas (default: false)
    
    Returns:
        {
            "success": True,
            "data": [{
                "id": "uuid",
                "titulo": "Titulo",
                "mensaje": "Mensaje",
                "tipo": "general",
                "leida": False,
                "fecha": "2026-03-20T10:30:00",
                "icono": "info"
            }],
            "total": 15,
            "no_leidas": 3
        }
    """
    try:
        usuario_id = request.args.get('usuario_id')
        if not usuario_id:
            return jsonify({
                "success": False,
                "message": "usuario_id es requerido"
            }), 400
        
        limite = int(request.args.get('limite', 20))
        no_leidas = request.args.get('no_leidas', 'false').lower() == 'true'
        
        exito, notificaciones = obtener_notificaciones_usuario(usuario_id, limite, no_leidas)
        
        if not exito:
            return jsonify({
                "success": False,
                "message": "Error obteniendo notificaciones"
            }), 500
        
        exito_cont, no_leidas_count = obtener_notificaciones_no_leidas_count(usuario_id)
        
        return jsonify({
            "success": True,
            "data": notificaciones,
            "total": len(notificaciones),
            "no_leidas": no_leidas_count if exito_cont else 0
        }), 200
    
    except Exception as e:
        print(f"[notificaciones_flutter_controller] Error: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@notificaciones_flutter_bp.route('/no-leidas-count', methods=['GET'])
def obtener_no_leidas_count():
    """
    GET /api/flutter/notificaciones/no-leidas-count
    Obtiene el contador de notificaciones no leídas
    
    Query params:
        - usuario_id: ID del usuario (requerido)
    
    Returns:
        {
            "success": True,
            "no_leidas": 3
        }
    """
    try:
        usuario_id = request.args.get('usuario_id')
        if not usuario_id:
            return jsonify({
                "success": False,
                "message": "usuario_id es requerido"
            }), 400
        
        exito, count = obtener_notificaciones_no_leidas_count(usuario_id)
        
        if not exito:
            return jsonify({
                "success": False,
                "message": "Error obteniendo contador"
            }), 500
        
        return jsonify({
            "success": True,
            "no_leidas": count
        }), 200
    
    except Exception as e:
        print(f"[notificaciones_flutter_controller] Error: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@notificaciones_flutter_bp.route('/marcar-leida', methods=['POST'])
def marcar_leida():
    """
    POST /api/flutter/notificaciones/marcar-leida
    Marca una notificación como leída
    
    Body:
        {
            "notificacion_id": "uuid"
        }
    
    Returns:
        {
            "success": True,
            "message": "Notificación marcada como leída"
        }
    """
    try:
        data = request.get_json() or {}
        notificacion_id = data.get('notificacion_id')
        
        if not notificacion_id:
            return jsonify({
                "success": False,
                "message": "notificacion_id es requerido"
            }), 400
        
        exito = marcar_notificacion_como_leida(notificacion_id)
        
        if not exito:
            return jsonify({
                "success": False,
                "message": "Error marcando notificación"
            }), 500
        
        return jsonify({
            "success": True,
            "message": "Notificación marcada como leída"
        }), 200
    
    except Exception as e:
        print(f"[notificaciones_flutter_controller] Error: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@notificaciones_flutter_bp.route('/marcar-todas-leidas', methods=['POST'])
def marcar_todas_leidas():
    """
    POST /api/flutter/notificaciones/marcar-todas-leidas
    Marca todas las notificaciones de un usuario como leídas
    
    Body:
        {
            "usuario_id": "uuid"
        }
    
    Returns:
        {
            "success": True,
            "message": "Todas las notificaciones fueron marcadas como leídas"
        }
    """
    try:
        data = request.get_json() or {}
        usuario_id = data.get('usuario_id')
        
        if not usuario_id:
            return jsonify({
                "success": False,
                "message": "usuario_id es requerido"
            }), 400
        
        exito = marcar_todas_como_leidas(usuario_id)
        
        if not exito:
            return jsonify({
                "success": False,
                "message": "Error marcando notificaciones"
            }), 500
        
        return jsonify({
            "success": True,
            "message": "Todas las notificaciones fueron marcadas como leídas"
        }), 200
    
    except Exception as e:
        print(f"[notificaciones_flutter_controller] Error: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
