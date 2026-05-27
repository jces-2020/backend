from flask import Blueprint, jsonify, request
import os, json, base64, hmac, hashlib, time
from app.services.supabase_client import supabase

clientes_bp = Blueprint('clientes', __name__)

def _b64url_decode(data: str) -> bytes:
    # Rellenar padding '=' si falta
    rem = len(data) % 4
    if rem:
        data += '=' * (4 - rem)
    return base64.urlsafe_b64decode(data)

def verify_jwt(token: str):
    """Devuelve el payload si el token es válido; de lo contrario None."""
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
        # Verificar expiración
        if payload.get('exp') and int(payload['exp']) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

def _build_jwt_for_cliente(cliente):
    """Genera un token JWT HS256 para el cliente."""
    secret = os.environ.get('JWT_SECRET', 'vidriobras-secret')
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": cliente['id_cliente'],
        "email": cliente.get('correo'),
        "name": cliente.get('nombre'),
        "exp": int(time.time()) + 7 * 24 * 3600,
        "aud": "cliente"
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(payload).encode())}"
    signature = hmac.new(secret.encode('utf-8'), signing_input.encode('utf-8'), hashlib.sha256).digest()
    return signing_input + "." + b64url(signature)

@clientes_bp.route('/api/clientes', methods=['GET'])
def get_clientes():
    # Allow optional filtering by documento or nombre
    documento = request.args.get('documento', None)
    filtro = request.args.get('filtro', None)
    if documento:
        response = supabase.table('cliente').select(
            'id_cliente, nombre, documento'
        ).eq('documento', documento).limit(1).execute()
        return jsonify(response.data or [])
    if filtro:
        # simple ilike on nombre or documento
        response = supabase.table('cliente').select(
            'id_cliente, nombre, documento'
        ).or_(
            f'nombre.ilike.%{filtro}%,documento.ilike.%{filtro}%'
        ).limit(5).execute()
        return jsonify(response.data or [])

    # default: list all for admin or other uses
    response = supabase.table('cliente').select(
        'id_cliente, numero, correo, contraseña, nombre, tipo_cliente_id, estado_cliente_id, documento'
    ).execute()
    clientes = response.data
    return jsonify(clientes)

# Endpoint para agregar un cliente (POST)
@clientes_bp.route('/api/clientes', methods=['POST'])
def add_cliente():
    data = request.json
    correo = (data.get('correo') or '').strip().lower()
    contraseña = (data.get('contraseña') or '').strip()
    nombre = (data.get('nombre') or '').strip()
    numero = (data.get('numero') or '').strip()

    if not correo or not contraseña or not nombre or not numero:
        return jsonify({'success': False, 'message': 'Faltan datos obligatorios.'}), 400

    existe = supabase.table('cliente').select('id_cliente').eq('correo', correo).limit(1).execute()
    if existe.data:
        return jsonify({'success': False, 'message': 'El correo ya está registrado.'}), 409

    # Resolver tipo_cliente_id desde la descripción (DNI / RUC)
    tipo_documento_desc = (data.get('tipo_documento') or '').strip().upper()
    tipo_cliente_id = None
    if tipo_documento_desc:
        td = supabase.table('tipo_documento').select('id_tipo').ilike('descripcion', tipo_documento_desc).limit(1).execute()
        if td.data:
            tipo_cliente_id = td.data[0]['id_tipo']
    # Si no se resolvió por descripción, usar el UUID directo (fallback)
    if not tipo_cliente_id:
        tipo_cliente_id = data.get('tipo_cliente_id') or None

    nuevo_cliente = {
        'numero': numero,
        'correo': correo,
        'contraseña': contraseña,
        'nombre': nombre,
        'documento': data.get('documento'),
        'tipo_cliente_id': tipo_cliente_id
    }
    try:
        response = supabase.table('cliente').insert(nuevo_cliente).execute()
        if response.data:
            cliente = response.data[0]
            token = _build_jwt_for_cliente(cliente)
            return jsonify({'success': True, 'cliente': cliente, 'token': token, 'token_type': 'Bearer'}), 201
        else:
            err = response.error or {}
            msg = str(err.get('message') or err)
            print(f"[CLIENTES] Error al registrar: {msg}")
            return jsonify({'success': False, 'message': 'Error al registrar. Intenta con otros datos.'}), 400
    except Exception as e:
        print("Exception:", e)  # Mostrar excepción en consola
        return jsonify({'success': False, 'message': 'No se pudo registrar el cliente.'}), 500

@clientes_bp.route('/api/clientes/login', methods=['POST'])
def login_cliente():
    data = request.json
    correo = (data.get('correo') or '').strip().lower()
    contraseña = data.get('contraseña')
    # Busca el cliente por correo
    response = supabase.table('cliente').select('id_cliente, correo, contraseña, nombre, numero, documento, "tipo cliente"').eq('correo', correo).execute()
    clientes = response.data
    if not clientes:
        return jsonify({'success': False, 'message': 'Correo incorrecto'}), 404
    cliente = clientes[0]
    # Verificar contraseña primero: si es correcta, permitir acceso sin importar el método de registro
    if cliente['contraseña'] == contraseña:
        token = _build_jwt_for_cliente(cliente)
        return jsonify({'success': True, 'cliente': cliente, 'token': token, 'token_type': 'Bearer'}), 200
    # Contraseña incorrecta: verificar si es usuario Google para personalizar el mensaje
    tipo_cliente_label = cliente.get('tipo cliente')
    if isinstance(tipo_cliente_label, str) and tipo_cliente_label.lower() == 'google':
        return jsonify({'success': False, 'message': 'Este usuario fue registrado con Google. Vuelve a iniciar sesión con Google.'}), 403
    return jsonify({'success': False, 'message': 'Contraseña incorrecta'}), 401

@clientes_bp.route('/api/clientes/me', methods=['GET'])
def get_cliente_actual():
    """Devuelve los datos del cliente autenticado usando el JWT enviado en Authorization: Bearer <token>."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'success': False, 'message': 'Falta token'}), 401
    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    if not payload:
        return jsonify({'success': False, 'message': 'Token inválido o expirado'}), 401
    try:
        cid = payload.get('sub')
        res = supabase.table('cliente').select('id_cliente, correo, nombre, numero, documento').eq('id_cliente', cid).limit(1).execute()
        if not res.data:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404
        return jsonify({'success': True, 'cliente': res.data[0]}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@clientes_bp.route('/api/clientes/temp-access/<cliente_id>', methods=['GET'])
def get_cliente_temp_access(cliente_id):
    """Devuelve credenciales temporales + jwt para mostrar QR post-comprobante."""
    try:
        cid = (cliente_id or '').strip()
        if not cid:
            return jsonify({'success': False, 'message': 'cliente_id requerido'}), 400

        res = supabase.table('cliente').select(
            'id_cliente, correo, contraseña, nombre, documento, cuenta_temporal'
        ).eq('id_cliente', cid).limit(1).execute()

        if not res.data:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404

        cliente = res.data[0]
        if not bool(cliente.get('cuenta_temporal')):
            return jsonify({'success': False, 'message': 'Cliente sin cuenta temporal'}), 404

        jwt_temporal = _build_jwt_for_cliente(cliente)
        return jsonify({
            'success': True,
            'data': {
                'cliente_id': cliente.get('id_cliente'),
                'nombre': cliente.get('nombre') or '',
                'correo': cliente.get('correo') or '',
                'contrasena': cliente.get('contraseña') or cliente.get('documento') or '',
                'documento': cliente.get('documento') or '',
                'jwt_temporal': jwt_temporal,
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500