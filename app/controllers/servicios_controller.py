from flask import Blueprint, jsonify
from app.models.servicio_model import get_all_servicios

servicios_bp = Blueprint('servicios_api', __name__, url_prefix='/api')

@servicios_bp.route('/servicios', methods=['GET'])
def get_servicios():
    """
    Endpoint para obtener todos los servicios con sus URLs de imagen.
    """
    servicios = get_all_servicios()
    
    if servicios is not None:
        return jsonify({"ok": True, "data": servicios}), 200
    else:
        return jsonify({"ok": False, "error": "No se pudieron obtener los servicios"}), 500
