from flask import Blueprint, jsonify, request

from services.clientes_admin_service import (
    get_all_clientes,
    get_cliente_by_id,
    get_cliente_ventas,
    add_cliente_descuento,
    get_clientes_stats,
)

clientes_admin_bp = Blueprint("clientes_admin_bp", __name__)


@clientes_admin_bp.route("/api/clientes_admin", methods=["GET"])
def list_clientes():
    """Lista todos los clientes de la empresa."""
    clientes = get_all_clientes()
    return jsonify({"success": True, "data": clientes})


@clientes_admin_bp.route("/api/clientes_admin/<cliente_id>", methods=["GET"])
def get_cliente(cliente_id):
    """Obtiene información detallada de un cliente."""
    cliente = get_cliente_by_id(cliente_id)
    if cliente:
        return jsonify({"success": True, "data": cliente})
    return jsonify({"success": False, "message": "Cliente no encontrado"}), 404


@clientes_admin_bp.route("/api/clientes_admin/<cliente_id>/ventas", methods=["GET"])
def get_ventas(cliente_id):
    """Obtiene las ventas/facturas de un cliente."""
    ventas = get_cliente_ventas(cliente_id)
    return jsonify({"success": True, "data": ventas})


@clientes_admin_bp.route("/api/clientes_admin/<cliente_id>/descuento", methods=["POST"])
def add_descuento(cliente_id):
    """
    Agrega un descuento o promoción a un cliente.
    Body JSON esperado:
    {
        "descripcion": "Descuento de temporada",
        "porcentaje": 15.5
    }
    """
    data = request.get_json()
    descripcion = data.get("descripcion", "")
    porcentaje = data.get("porcentaje", 0)
    
    if not descripcion or porcentaje <= 0:
        return jsonify({
            "success": False,
            "message": "Descripción y porcentaje son requeridos"
        }), 400
    
    success = add_cliente_descuento(cliente_id, descripcion, float(porcentaje))
    if success:
        return jsonify({
            "success": True,
            "message": "Descuento agregado correctamente"
        })
    return jsonify({
        "success": False,
        "message": "Error al agregar descuento"
    }), 500


@clientes_admin_bp.route("/api/clientes_admin/stats", methods=["GET"])
def get_stats():
    """Obtiene estadísticas generales de clientes."""
    stats = get_clientes_stats()
    return jsonify({"success": True, "data": stats})
