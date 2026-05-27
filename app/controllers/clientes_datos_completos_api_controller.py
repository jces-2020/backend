from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase
import os, json

clientes_datos_completos_api = Blueprint('clientes_datos_completos_api', __name__)

def verify_jwt(token: str):
    # Copiado de carrito_compras_api_controller para consistencia
    import base64, hmac, hashlib, time
    def _b64url_decode(data: str) -> bytes:
        rem = len(data) % 4
        if rem:
            data += '=' * (4 - rem)
        return base64.urlsafe_b64decode(data)
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header = json.loads(_b64url_decode(parts[0]).decode('utf-8'))
        payload = json.loads(_b64url_decode(parts[1]).decode('utf-8'))
        signature = parts[2]
        if header.get('alg') != 'HS256':
            return None
        secret = os.environ.get('JWT_SECRET', 'vidriobras-secret')
        signing_input = parts[0] + '.' + parts[1]
        expected = hmac.new(secret.encode('utf-8'), signing_input.encode('utf-8'), hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b'=').decode('utf-8')
        if not hmac.compare_digest(signature, expected_b64):
            return None
        if payload.get('exp') and int(payload['exp']) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

@clientes_datos_completos_api.route('/api/clientes/datos_completos', methods=['GET'])
def verificar_datos_completos():
    """
    Verifica si el cliente autenticado tiene todos los datos obligatorios completos.
    Requiere Authorization: Bearer <token>
    """
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    if not payload or payload.get('aud') != 'cliente':
        return jsonify({'success': False, 'message': 'Token inválido'}), 401
    cliente_id = payload.get('sub')
    if not cliente_id:
        return jsonify({'success': False, 'message': 'Token sin sub'}), 401
    try:
        res = supabase.table('cliente').select('*').eq('id_cliente', cliente_id).limit(1).execute()
        if not res.data:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404
        cli = res.data[0]
        # Campos obligatorios (ajustado: tipo_documento_id en vez de tipo_cliente_id)
        campos = ['nombre', 'correo', 'contraseña', 'numero', 'documento', 'tipo_documento_id']
        faltantes = [c for c in campos if not cli.get(c)]
        datos_completos = len(faltantes) == 0
        return jsonify({'success': True, 'datos_completos': datos_completos, 'faltantes': faltantes}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Endpoint para exponer los tipos de documento
@clientes_datos_completos_api.route('/api/tipo_documento', methods=['GET'])
def listar_tipos_documento():
    try:
        res = supabase.table('tipo_documento').select('*').execute()
        tipos = res.data or []
        return jsonify({'success': True, 'tipos': tipos}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500