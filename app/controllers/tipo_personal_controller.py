
from flask import Blueprint, jsonify, request
from app.services.supabase_client import supabase
import os, json, base64, hmac, hashlib, time

tipo_personal_bp = Blueprint('tipo_personal', __name__)

# Utilidades JWT (HS256 sin dependencia externa)
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

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
        secret = os.environ.get('JWT_SECRET', 'devsecret-change-me')
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

# Endpoint para login de personal: valida nombre y codigo y emite JWT
@tipo_personal_bp.route('/api/personal/login', methods=['POST'])
def login_personal():
    data = request.get_json()
    nombre = data.get('nombre')
    codigo = data.get('codigo')
    area = data.get('area')
    if not nombre or not codigo or not area:
        return jsonify({'success': False, 'error': 'Faltan par\u00e1metros'}), 400
    # Buscar en la tabla personal donde nombre y Codigo coincidan (case-insensitive)
    response = supabase.table('personal').select('*, tipo_personal:tipo_personal_id(descripcion)').ilike('nombre', nombre).eq('Codigo', codigo).execute()
    if response.data and len(response.data) > 0:
        personal = response.data[0]
        # Validar permiso: comparar area seleccionada con la descripcion del tipo_personal
        descripcion_area = None
        if 'tipo_personal' in personal and personal['tipo_personal']:
            descripcion_area = personal['tipo_personal']['descripcion'].strip().upper()
        if descripcion_area and descripcion_area == area.strip().upper():
            # Emitir un JWT para personal
            secret = os.environ.get('JWT_SECRET', 'devsecret-change-me')
            header = {"alg": "HS256", "typ": "JWT"}
            # Resolver id del personal de manera robusta
            personal_id = personal.get('id_personal') or personal.get('id') or personal.get('Id')
            payload = {
                "sub": personal_id or str(nombre),
                "name": personal.get('nombre') or nombre,
                "area": descripcion_area,  # ALMACEN, VENTAS, ADMINISTRACION, etc.
                "aud": "personal",
                # 72 horas de sesion (3 dias para desarrollo)
                "exp": int(time.time()) + 72 * 3600
            }
            signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
            signature = hmac.new(secret.encode('utf-8'), signing_input.encode('utf-8'), hashlib.sha256).digest()
            token = signing_input + "." + _b64url(signature)
            return jsonify({
                'success': True,
                'personal': personal,
                'token': token,
                'token_type': 'Bearer'
            }), 200
        else:
            return jsonify({'success': False, 'error': 'No tiene permiso para ingresar a esta area'}), 403
    else:
        return jsonify({'success': False, 'error': 'Nombre o codigo incorrecto'}), 401

# Datos del personal autenticado
@tipo_personal_bp.route('/api/personal/me', methods=['GET'])
def personal_me():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'success': False, 'message': 'Falta token'}), 401
    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    if not payload or payload.get('aud') != 'personal':
        return jsonify({'success': False, 'message': 'Token invalido o expirado'}), 401
    return jsonify({'success': True, 'personal': {
        'id': payload.get('sub'),
        'name': payload.get('name'),
        'area': payload.get('area'),
    }}), 200

# Endpoint para buscar usuarios por area/tipo
@tipo_personal_bp.route('/api/personal/buscar', methods=['GET'])
def buscar_personal_por_nombre_codigo():
    area = request.args.get('area')
    codigo = request.args.get('codigo')
    
    # Si no hay area especificada, retornar error
    if not area:
        return jsonify({'error': 'Parametro area es requerido'}), 400
    
    # Normalizar el area para manejar "OPERACIONES" como "OBRAS" o "TRABAJO"
    area_normalizada = area.strip().upper()
    if area_normalizada == 'OPERACIONES':
        area_normalizada = 'OBRAS'
    
    try:
        # Buscar el tipo_personal por descripcion
        tipo_res = supabase.table('tipo_personal').select('id_tipo').eq('descripcion', area_normalizada).execute()
        
        if not tipo_res.data:
            # Si no existe el tipo, retornar lista vacia
            return jsonify([])
        
        tipo_id = tipo_res.data[0]['id_tipo']
        
        # Buscar personal con ese tipo_personal_id
        personal_res = supabase.table('personal').select('*').eq('tipo_personal_id', tipo_id).execute()
        
        return jsonify(personal_res.data or [])
    
    except Exception as e:
        print(f"[ERROR] Error en buscar_personal_por_nombre_codigo: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tipo_personal_bp.route('/api/tipo_personal', methods=['GET'])
def get_tipo_personal():
    response = supabase.table('tipo_personal').select('id_tipo, descripcion').execute()
    return jsonify(response.data)

# Endpoint para solo descripciones (frontend)
@tipo_personal_bp.route('/api/tipo_personal/descripciones', methods=['GET'])
def get_tipo_personal_descripciones():
    response = supabase.table('tipo_personal').select('descripcion').execute()
    descripciones = [item['descripcion'] for item in response.data]
    return jsonify(descripciones)
    return jsonify(descripciones)
