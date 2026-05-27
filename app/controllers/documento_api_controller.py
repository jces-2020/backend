import requests
from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase
import os

bp = Blueprint('documento_api', __name__)

APISPERU_TOKEN = os.environ.get('APISPERU_TOKEN', 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImkyNDE1OTE0QGNvbnRpbmVudGFsLmVkdS5wZSJ9.e9EuekJUwsqKvAGuELbs-0P65QkqdeMranSkV-Tqb9Y')

@bp.route('/api/validar_documento', methods=['POST'])
def validar_documento():
    data = request.json
    tipo = data.get('tipo')  # 'DNI' o 'RUC'
    numero = data.get('numero')
    if not tipo or not numero:
        return jsonify({'success': False, 'message': 'Faltan datos'}), 400
    if tipo == 'DNI':
        url = f'https://dniruc.apisperu.com/api/v1/dni/{numero}?token={APISPERU_TOKEN}'
    elif tipo == 'RUC':
        url = f'https://dniruc.apisperu.com/api/v1/ruc/{numero}?token={APISPERU_TOKEN}'
    else:
        return jsonify({'success': False, 'message': 'Tipo de documento inválido'}), 400
    try:
        r = requests.get(url, timeout=8)
        j = r.json()
        if 'error' in j:
            return jsonify({'success': False, 'message': 'No encontrado en RENIEC/SUNAT', 'error': j['error']}), 404
        # Guardar o actualizar en la base de datos si es necesario
        # Ejemplo: supabase.table('documentos').upsert({...})
        return jsonify({'success': True, 'data': j}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': 'Error consultando APISPERU', 'error': str(e)}), 500
