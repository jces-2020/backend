"""
Controller: Gestión de Obras
Maneja las notificaciones de trabajo y la visualización del panel de obras.
"""
from flask import Blueprint, jsonify, request
from typing import Optional
from datetime import datetime

# TODO: Importar services cuando se creen
# from services.obras_service import (...)

obras_bp = Blueprint("obras_bp", __name__)


@obras_bp.route("/notificaciones", methods=["GET"])
def get_notificaciones():
    """
    Obtiene las notificaciones de trabajo según categoría.
    Query params:
    - categoria: SERVICIO | OPTIMIZACION | ENTREGA
    - ocultar_atendidas: bool
    """
    try:
        categoria = request.args.get("categoria", "ENTREGA")
        ocultar_atendidas = request.args.get("ocultar_atendidas", "true").lower() == "true"
        
        # TODO: Implementar lógica de obtención desde service
        # notifs = get_notificaciones_by_categoria(categoria, ocultar_atendidas)
        
        return jsonify({
            "success": True,
            "data": [],
            "message": "Endpoint en desarrollo"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@obras_bp.route("/notificaciones/<notif_id>/estado", methods=["PATCH"])
def update_notificacion_estado(notif_id: str):
    """
    Actualiza el estado de una notificación de trabajo.
    Body: { "estado": "EN_PROCESO" | "FINALIZADO" | "PENDIENTE" }
    """
    try:
        data = request.get_json()
        nuevo_estado = data.get("estado")
        
        if not nuevo_estado:
            return jsonify({"success": False, "message": "Estado requerido"}), 400
        
        # TODO: Implementar lógica de actualización
        # resultado = update_estado_notificacion(notif_id, nuevo_estado)
        
        return jsonify({
            "success": True,
            "message": f"Estado actualizado a {nuevo_estado}"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@obras_bp.route("/dashboard", methods=["GET"])
def get_dashboard_obras():
    """
    Obtiene métricas del dashboard de obras.
    """
    try:
        # TODO: Implementar métricas
        # stats = get_obras_stats()
        
        return jsonify({
            "success": True,
            "data": {
                "pendientes": 0,
                "en_proceso": 0,
                "finalizadas": 0
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
