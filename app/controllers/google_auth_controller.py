
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

bp = Blueprint('google_auth', __name__)

# Cargar el client_id desde el JSON de Google
CLIENT_SECRET_PATH = os.path.join(os.path.dirname(__file__), '..', 'client_secret_1000681433446-mgbmp68bol11vjn56rfsb2ai9l732tbb.apps.googleusercontent.com.json')
with open(CLIENT_SECRET_PATH, 'r') as f:
    google_creds = json.load(f)
GOOGLE_CLIENT_ID = google_creds['web']['client_id']


@bp.route('/api/clientes/actualiza_datos_google', methods=['PATCH'])
def actualiza_datos_google():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'success': False, 'message': 'Falta token'}), 401
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], options={"verify_aud": False})
        cid = payload.get('sub')
        if not cid:
            return jsonify({'success': False, 'message': 'Token inválido'}), 401
        data = request.json
        # Guardar todos los datos recibidos, sin validaciones
        print('[DEBUG][actualiza_datos_google] Datos recibidos para actualizar:', data)
        print('[DEBUG][actualiza_datos_google] Claves recibidas:', list(data.keys()))
        res = supabase.table('cliente').update(data).eq('id_cliente', cid).execute()
        print('[DEBUG][actualiza_datos_google] Respuesta de supabase:', getattr(res, 'data', None), getattr(res, 'error', None))
        return jsonify({'success': True, 'message': 'Datos actualizados', 'data': res.data}), 200
    except Exception as e:
        import traceback
        print('[ERROR][actualiza_datos_google] Excepción al actualizar datos:')
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Error actualizando datos', 'error': str(e)}), 500


@bp.route('/api/auth/google-register', methods=['POST'])
def google_register():
    """Solo permite registro si el usuario NO existe."""
    data = request.json
    token = data.get('credential')
    if not token:
        return jsonify({'success': False, 'message': 'Falta el token de Google'}), 400
    try:
        print('[DEBUG][google-register] Token recibido:', token)
        idinfo = id_token.verify_oauth2_token(token, grequests.Request(), GOOGLE_CLIENT_ID)
        print('[DEBUG][google-register] idinfo:', idinfo)
        email = idinfo.get('email')
        nombre = idinfo.get('name')
        sub = idinfo.get('sub')
        user_resp = supabase.table('cliente').select('*').eq('correo', email).execute()
        user = user_resp.data[0] if user_resp.data else None
        if user:
            print('[DEBUG][google-register] Correo ya en uso:', email)
            return jsonify({'success': False, 'message': 'Este correo ya está en uso, pruebe otro.'}), 400
        nombre_final = nombre if nombre else 'GoogleUser'
        insert_resp = supabase.table('cliente').insert({
            'correo': email,
            'contraseña': sub,
            'nombre': nombre_final,
            'numero': '',
            'documento': '',
            'tipo cliente': 'google',
            'registro_completo': True
        }).execute()
        user = insert_resp.data[0] if insert_resp.data else None
        id_cliente = user['id_cliente'] if user and 'id_cliente' in user else None
        payload = {
            'email': email,
            'nombre': nombre_final,
            'sub': id_cliente,
            'exp': int((datetime.datetime.utcnow() + datetime.timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
            'aud': 'cliente'
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')
        print('[DEBUG][google-register] Registro exitoso para:', email)
        return jsonify({
            'success': True,
            'email': email,
            'nombre': nombre_final,
            'token': token,
            'cliente': user
        })
    except Exception as e:
        import traceback
        print('[ERROR][google-register] Error validando token de Google:', str(e))
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Token de Google inválido', 'error': str(e)}), 401


@bp.route('/api/auth/google-login', methods=['POST'])
def google_login():
    """Login de usuario existente con Google."""
    data = request.json
    token = data.get('credential')
    if not token:
        return jsonify({'success': False, 'message': 'Falta el token de Google'}), 400
    try:
        print('[DEBUG][google-login] Token recibido')
        idinfo = id_token.verify_oauth2_token(token, grequests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo.get('email')
        nombre = idinfo.get('name')
        sub = idinfo.get('sub')

        # Buscar usuario por correo
        user_resp = supabase.table('cliente').select('*').eq('correo', email).execute()
        user = user_resp.data[0] if user_resp.data else None

        if not user:
            print('[DEBUG][google-login] Usuario no encontrado:', email)
            return jsonify({'success': False, 'message': 'Usuario no registrado'}), 404

        id_cliente = user['id_cliente']
        payload = {
            'email': email,
            'nombre': user.get('nombre', nombre),
            'sub': id_cliente,
            'exp': int((datetime.datetime.utcnow() + datetime.timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
            'aud': 'cliente'
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')
        print('[DEBUG][google-login] Login exitoso para:', email)
        return jsonify({
            'success': True,
            'email': email,
            'token': token,
            'cliente': user
        })
    except Exception as e:
        import traceback
        print('[ERROR][google-login] Error:', str(e))
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Token de Google inválido', 'error': str(e)}), 401
