"""
Controlador para productos de entrega.
"""
from flask import Blueprint, jsonify, request
from app.services.entrega_productos_service import (
    obtener_productos_entrega_por_notificacion,
    descontar_stock_productos
)

entrega_productos_bp = Blueprint("entrega_productos", __name__)


@entrega_productos_bp.route("/api/entrega/productos/notificacion/<notificacion_id>", methods=["GET"])
def obtener_productos_entrega(notificacion_id):
    """
    GET /api/entrega/productos/notificacion/<notificacion_id>
    """
    try:
        resultado = obtener_productos_entrega_por_notificacion(notificacion_id)
        if resultado.get("success"):
            return jsonify({
                "success": True,
                "data": resultado.get("data", []),
                "message": resultado.get("message", ""),
                "carrito_id": resultado.get("carrito_id", ""),
                "solo_cortes": resultado.get("solo_cortes", False)
            }), 200

        return jsonify({
            "success": False,
            "message": resultado.get("message", "Error al obtener productos")
        }), 500
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@entrega_productos_bp.route("/api/entrega/productos/entregar", methods=["POST"])
def entregar_productos():
    """
    POST /api/entrega/productos/entregar
    Body: {"items": [{"producto_id": "uuid", "cantidad": 1}]}
    """
    try:
        data = request.get_json() or {}
        items = data.get("items") or []

        # Validar que items no estÃ© vacÃ­o
        if not items:
            return jsonify({
                "success": False,
                "message": "Lista de productos vacÃ­a"
            }), 400

        # Validar estructura de cada item
        items_validos = []
        for item in items:
            if not item.get("producto_id"):
                continue
            try:
                cantidad = float(item.get("cantidad") or 0)
                if cantidad > 0:
                    items_validos.append({
                        "producto_id": item.get("producto_id"),
                        "cantidad": cantidad
                    })
            except (ValueError, TypeError):
                continue

        if not items_validos:
            return jsonify({
                "success": False,
                "message": "No hay productos vÃ¡lidos para procesar"
            }), 400

        resultado = descontar_stock_productos(items_validos)
        if resultado.get("success"):
            return jsonify({"success": True, "actualizados": resultado.get("actualizados", 0)}), 200

        return jsonify({
            "success": False,
            "message": resultado.get("message", "Error al actualizar stock")
        }), 400
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500
