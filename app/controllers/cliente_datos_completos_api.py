from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase
from app.controllers.clientes_controller import verify_jwt

bp = Blueprint('cliente_datos_completos_api', __name__)

@bp.route('/api/clientes/datos_completos', methods=['GET'])
def datos_completos():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'success': False, 'message': 'Falta token'}), 401
    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    if not payload:
        return jsonify({'success': False, 'message': 'Token inválido o expirado'}), 401
    try:
        cid = payload.get('sub')
        res = supabase.table('cliente').select('id_cliente, correo, contraseña, nombre, numero, documento').eq('id_cliente', cid).limit(1).execute()
        if not res.data:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404
        cliente = res.data[0]
        # Validar que todos los campos requeridos estén presentes y no vacíos
        campos = ['nombre', 'correo', 'contraseña', 'documento', 'numero']
        incompletos = [campo for campo in campos if not cliente.get(campo)]
        if incompletos:
            return jsonify({'success': True, 'completo': False, 'faltan': incompletos, 'cliente': cliente}), 200
        return jsonify({'success': True, 'completo': True, 'cliente': cliente}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
