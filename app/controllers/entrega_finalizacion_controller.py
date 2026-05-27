"""
Controlador para finalizar entregas.
"""
from flask import Blueprint, jsonify, request
from app.services.entrega_finalizacion_service import (
    finalizar_entrega_completa
)

entrega_finalizacion_bp = Blueprint("entrega_finalizacion", __name__)


@entrega_finalizacion_bp.route("/api/entrega/finalizar", methods=["POST"])
def finalizar_entrega():
    """
    POST /api/entrega/finalizar
    Completa todo el proceso de entrega:
    1. Guarda cortes en reporte
    2. Elimina cortes de la tabla
    3. Marca carrito como entregado
    4. Elimina notificación
    
    Body: {"notificacion_id": "uuid", "cortes_data": {...}}
    """
    try:
        data = request.get_json() or {}
        notificacion_id = data.get("notificacion_id")
        cortes_data = data.get("cortes_data", {})

        if not notificacion_id:
            return jsonify({
                "success": False,
                "message": "Falta el ID de notificación"
            }), 400

        resultado = finalizar_entrega_completa(notificacion_id, cortes_data)
        
        if resultado.get("success"):
            return jsonify({
                "success": True,
                "message": "Entrega finalizada correctamente"
            }), 200

        return jsonify({
            "success": False,
            "message": resultado.get("message", "Error al finalizar entrega")
        }), 400
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500
