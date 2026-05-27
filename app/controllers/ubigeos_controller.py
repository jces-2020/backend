from flask import Blueprint, jsonify
from services.ubigeos_service import obtener_todo_ubigeos, obtener_provincias, obtener_distritos

ubigeos_api = Blueprint('ubigeos_api', __name__, url_prefix='/api/ubigeos')


@ubigeos_api.route('/obtener', methods=['GET'])
def obtener_ubigeos():
    """
    Endpoint para obtener todos los datos de ubigeos
    Retorna: departamentos, provincias_por_departamento, distritos_por_provincia
    """
    try:
        datos = obtener_todo_ubigeos()
        return jsonify({"success": True, "data": datos}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@ubigeos_api.route('/provincias/<departamento>', methods=['GET'])
def obtener_provincias_por_dept(departamento):
    """
    Endpoint para obtener provincias de un departamento específico
    """
    try:
        provincias = obtener_provincias(departamento)
        return jsonify({"success": True, "data": provincias}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@ubigeos_api.route('/distritos/<provincia>', methods=['GET'])
def obtener_distritos_por_prov(provincia):
    """
    Endpoint para obtener distritos de una provincia específica
    """
    try:
        distritos = obtener_distritos(provincia)
        return jsonify({"success": True, "data": distritos}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
