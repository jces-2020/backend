from flask import Blueprint, jsonify, request
from app.controllers.tipo_personal_controller import verify_jwt

personal_nombre_api = Blueprint('personal_nombre_api', __name__)

@personal_nombre_api.route('/api/personal/nombre', methods=['GET'])
def get_nombre_personal():
    """Obtiene el nombre del personal autenticado"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'success': False, 'message': 'Falta token'}), 401
    
    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    
    if not payload or payload.get('aud') != 'personal':
        return jsonify({'success': False, 'message': 'Token inválido o expirado'}), 401
    
    return jsonify({
        'success': True,
        'nombre': payload.get('name', 'Personal')
    }), 200
