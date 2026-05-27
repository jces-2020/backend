from flask import Blueprint, request, jsonify
from app.services.cortes_service import calcular_precio_cortes, COSTO_CORTE

cortes_bp = Blueprint('cortes', __name__)


@cortes_bp.route('/api/cortes/config', methods=['GET'])
def obtener_config_cortes():
    return jsonify({
        "success": True,
        "costo_corte": COSTO_CORTE
    }), 200


@cortes_bp.route('/api/cortes/calcular', methods=['POST'])
def calcular_cortes():
    data = request.get_json(silent=True) or {}
    cortes = data.get('cortes') or []
    precio_unitario = data.get('precio_unitario')

    if precio_unitario is None:
        return jsonify({
            "success": False,
            "message": "precio_unitario es requerido"
        }), 400

    try:
        resultado = calcular_precio_cortes(cortes, float(precio_unitario))
        return jsonify({
            "success": True,
            "data": resultado
        }), 200
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500
