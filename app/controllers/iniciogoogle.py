import os
import json
import datetime
import jwt
from flask import Blueprint, request, jsonify, current_app
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from app.services.supabase_client import supabase

JWT_SECRET = os.environ.get('JWT_SECRET', 'vidriobras-secret')
JWT_EXP_MINUTES = 60

bp = Blueprint('google_login', __name__)

# Cargar el client_id desde el JSON de Google
CLIENT_SECRET_PATH = os.path.join(os.path.dirname(__file__), '..', 'client_secret_1000681433446-mgbmp68bol11vjn56rfsb2ai9l732tbb.apps.googleusercontent.com.json')
with open(CLIENT_SECRET_PATH, 'r') as f:
    google_creds = json.load(f)
GOOGLE_CLIENT_ID = google_creds['web']['client_id']

@bp.route('/api/auth/google-login', methods=['POST'])
def google_login():
    """Solo permite login si el usuario ya existe."""
    data = request.json
    token = data.get('credential')
    if not token:
        return jsonify({'success': False, 'message': 'Falta el token de Google'}), 400
    try:
        print('[DEBUG][google-login] Token recibido:', token)
        idinfo = id_token.verify_oauth2_token(token, grequests.Request(), GOOGLE_CLIENT_ID)
        print('[DEBUG][google-login] idinfo:', idinfo)
        email = idinfo.get('email')
        nombre = idinfo.get('name')
        sub = idinfo.get('sub')
        user_resp = supabase.table('cliente').select('*').eq('correo', email).execute()
        user = user_resp.data[0] if user_resp.data else None
        if not user:
            print('[DEBUG][google-login] Usuario no registrado:', email)
            return jsonify({'success': False, 'message': 'Usuario no registrado. Usa el registro con Google.'}), 404
        id_cliente = user['id_cliente'] if 'id_cliente' in user else None
        payload = {
            'email': email,
            'nombre': user.get('nombre', nombre),
            'sub': id_cliente,
            'exp': int((datetime.datetime.utcnow() + datetime.timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
            'aud': 'cliente'
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')
        print('[DEBUG][google-login] Login exitoso para:', email)
        # Retornar todos los datos relevantes del cliente
        cliente_data = {
            'id_cliente': user.get('id_cliente'),
            'correo': user.get('correo'),
            'nombre': user.get('nombre'),
            'numero': user.get('numero'),
            'documento': user.get('documento'),
            'tipo_cliente_id': user.get('tipo_cliente_id'),
            'tipo_cliente': user.get('tipo cliente'),
            'estado_cliente_id': user.get('estado_cliente_id')
        }
        return jsonify({
            'success': True,
            'token': token,
            'cliente': cliente_data
        })
    except Exception as e:
        import traceback
        print('[ERROR][google-login] Error validando token de Google:', str(e))
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Token de Google inválido', 'error': str(e)}), 401
