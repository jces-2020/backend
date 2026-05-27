from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase

verifica_estado_cliente_api = Blueprint('verifica_estado_cliente_api', __name__)

@verifica_estado_cliente_api.route('/api/clientes/estado_cliente', methods=['GET'])
def verificar_estado_cliente():
    """
    Verifica si el cliente logueado tiene el campo estado_cliente_id relleno.
    Requiere Authorization: Bearer <token>.
    """
    try:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'No autorizado'}), 401
        token = auth.split(' ', 1)[1]
        # Decodificar JWT para obtener el id_cliente
        import os, json, base64, hmac, hashlib, time
        def _b64url_decode(data: str) -> bytes:
            rem = len(data) % 4
            if rem:
                data += '=' * (4 - rem)
            return base64.urlsafe_b64decode(data)
        def verify_jwt(token: str):
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
        payload = verify_jwt(token)
        if not payload:
            return jsonify({'success': False, 'message': 'Token inválido'}), 401
        cliente_id = payload.get('sub')
        if not cliente_id:
            return jsonify({'success': False, 'message': 'Token sin sub'}), 401
        res = supabase.table('cliente').select('estado_cliente_id').eq('id_cliente', cliente_id).limit(1).execute()
        if not res.data:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404
        estado_cliente_id = res.data[0].get('estado_cliente_id')
        return jsonify({'success': True, 'estado_cliente_id': estado_cliente_id}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
