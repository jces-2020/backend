"""
Controlador para guardar reporte temporal de entrega.
"""
from flask import Blueprint, jsonify, request
from app.services.entrega_reporte_service import guardar_reporte_temporal, obtener_reporte_temporal

entrega_reporte_bp = Blueprint("entrega_reporte", __name__)


@entrega_reporte_bp.route("/api/entrega/reporte-temp", methods=["POST"])
def guardar_reporte_temporal_endpoint():
    """
    POST /api/entrega/reporte-temp
    Body: JSON con datos del reporte
    """
    try:
        data = request.get_json() or {}
        resultado = guardar_reporte_temporal(data)

        if resultado.get("success"):
            return jsonify({"success": True}), 200

        return jsonify({
            "success": False,
            "message": resultado.get("message", "Error al guardar reporte")
        }), 400
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@entrega_reporte_bp.route("/api/entrega/reporte-temp/<notificacion_id>", methods=["GET"])
def obtener_reporte_temporal_endpoint(notificacion_id):
    """
    GET /api/entrega/reporte-temp/<notificacion_id>
    """
    try:
        resultado = obtener_reporte_temporal(notificacion_id)
        if resultado.get("success"):
            return jsonify({"success": True, "data": resultado.get("data")}), 200

        return jsonify({
            "success": False,
            "message": resultado.get("message", "Reporte no encontrado")
        }), 404
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500
