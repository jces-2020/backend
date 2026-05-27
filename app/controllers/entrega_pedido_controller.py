"""
Controller: Entrega de Pedidos
Maneja el workflow de entrega de pedidos al cliente (RETASOS/PRODUCTOS).
"""
from flask import Blueprint, jsonify, request
from typing import Optional

# TODO: Importar services cuando se creen
# from services.entrega_pedido_service import (...)

entrega_pedido_bp = Blueprint("entrega_pedido_bp", __name__)


@entrega_pedido_bp.route("/productos/seleccionar", methods=["POST"])
def seleccionar_productos_entrega():
    """
    Registra los productos seleccionados para entrega.
    Body: {
        "pedido_id": str,
        "productos": [{ "id": str, "cantidad": int }]
    }
    """
    try:
        data = request.get_json()
        pedido_id = data.get("pedido_id")
        productos = data.get("productos", [])
        
        if not pedido_id:
            return jsonify({"success": False, "message": "Pedido ID requerido"}), 400
        
        # TODO: Registrar selección
        # resultado = registrar_productos_entrega(pedido_id, productos)
        
        return jsonify({
            "success": True,
            "message": "Productos registrados para entrega"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@entrega_pedido_bp.route("/confirmar", methods=["POST"])
def confirmar_entrega():
    """
    Confirma la entrega de un pedido al cliente.
    Body: {
        "pedido_id": str,
        "cliente": str,
        "fecha": str,
        "productos_entregados": [],
        "observaciones": str (opcional)
    }
    """
    try:
        data = request.get_json()
        pedido_id = data.get("pedido_id")
        
        if not pedido_id:
            return jsonify({"success": False, "message": "Pedido ID requerido"}), 400
        
        # TODO: Confirmar entrega y actualizar estado
        # resultado = confirmar_entrega_pedido(data)
        
        return jsonify({
            "success": True,
            "message": "Entrega confirmada correctamente"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@entrega_pedido_bp.route("/<pedido_id>", methods=["GET"])
def get_detalle_entrega(pedido_id: str):
    """
    Obtiene el detalle de una entrega específica.
    """
    try:
        # TODO: Obtener detalle de entrega
        # entrega = get_entrega_by_pedido_id(pedido_id)
        
        return jsonify({
            "success": True,
            "data": {},
            "message": "Endpoint en desarrollo"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@entrega_pedido_bp.route("/historial", methods=["GET"])
def get_historial_entregas():
    """
    Obtiene el historial de entregas realizadas.
    Query params:
    - fecha_inicio: str (opcional)
    - fecha_fin: str (opcional)
    - cliente: str (opcional)
    """
    try:
        fecha_inicio = request.args.get("fecha_inicio")
        fecha_fin = request.args.get("fecha_fin")
        cliente = request.args.get("cliente")
        
        # TODO: Consultar historial
        # entregas = get_historial_entregas(fecha_inicio, fecha_fin, cliente)
        
        return jsonify({
            "success": True,
            "data": [],
            "message": "Endpoint en desarrollo"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
