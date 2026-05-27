from flask import Blueprint, request, jsonify
from services.venta_service import registrar_venta

venta_api = Blueprint('venta_api', __name__)

@venta_api.route('/api/venta/registrar', methods=['POST'])
def api_registrar_venta():
    data = request.get_json()
    total = data.get('total')
    metodo = data.get('metodo')
    caja_id = data.get('caja_id')
    if total is None or not metodo:
        return jsonify({"success": False, "message": "Faltan datos obligatorios"}), 400
    ok = registrar_venta(total, metodo, caja_id)
    if ok:
        return jsonify({"success": True}), 200
    else:
        return jsonify({"success": False, "message": "Error al registrar venta"}), 500
