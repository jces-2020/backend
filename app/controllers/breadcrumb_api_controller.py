from flask import Blueprint, request, jsonify
from typing import List, Dict

# Simulación de historial de navegación en backend
# Usando una lista global para demo (en producción usar session o DB)

global_history: List[Dict[str, str]] = []

breadcrumb_api = Blueprint('breadcrumb_api', __name__)

# Estructura: [{'path': '/ruta', 'label': 'Nombre'}]

@breadcrumb_api.route('/api/breadcrumbs', methods=['GET'])
def get_breadcrumbs():
    # Obtener historial de navegación
    filtered = [b for b in global_history if b['path'] != '/']
    if len(filtered) > 4:
        filtered = filtered[-4:]
    return jsonify({"success": True, "data": filtered})

@breadcrumb_api.route('/api/breadcrumbs', methods=['POST'])
def add_breadcrumb():
    # Agregar nueva ruta al historial
    data = request.get_json()
    path = data.get('path')
    label = data.get('label')
    if not path or not label:
        return jsonify({"success": False, "message": "Datos inválidos"}), 400
    # Evitar duplicados consecutivos
    if global_history and global_history[-1]['path'] == path:
        return jsonify({"success": True, "data": global_history})
    global_history.append({'path': path, 'label': label})
    return jsonify({"success": True, "data": global_history})
