from flask import Blueprint, jsonify, request
import os, json, base64, hmac, hashlib, time, re
from app.services.supabase_client import supabase

EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def _friendly_signup_error_message(raw_error: Exception) -> tuple[str, int]:
    msg = str(raw_error or "").strip()
    low = msg.lower()

    if "already registered" in low or "user already exists" in low:
        return 'Este correo ya está registrado en el sistema de autenticación.', 409

    if (
        "error sending confirmation email" in low
        or "invalid email" in low
        or "email address" in low and "invalid" in low
        or "unable to validate email address" in low
    ):
        return 'Correo no encontrado o inválido. Usa un Gmail real y vuelve a intentar.', 400

    return f'No se pudo crear la cuenta: {msg or "error desconocido"}', 500

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

# Endpoint para agregar un cliente (POST) - Usa Supabase Auth para verificación de correo
@clientes_bp.route('/api/clientes', methods=['POST'])
def add_cliente():
    data = request.json
    correo = (data.get('correo') or '').strip().lower()
    contraseña = (data.get('contraseña') or '').strip()
    nombre = (data.get('nombre') or '').strip()
    numero = (data.get('numero') or '').strip()

    if not correo or not contraseña or not nombre or not numero:
        return jsonify({'success': False, 'message': 'Faltan datos obligatorios.'}), 400

    if not EMAIL_PATTERN.match(correo):
        return jsonify({'success': False, 'message': 'Correo electrónico inválido.'}), 400

    existe = supabase.table('cliente').select('id_cliente').eq('correo', correo).limit(1).execute()
    if existe.data:
        return jsonify({'success': False, 'message': 'El correo ya está registrado.'}), 409

    try:
        print(f"[DEBUG] Intentando crear usuario de auth para: {correo}")

        # 1. Crear usuario en Supabase Auth (envía email automáticamente)
        try:
            auth_user = supabase.auth.admin.create_user({
                "email": correo,
                "password": contraseña,
                "email_confirm": False
            })
            auth_id = auth_user.user.id
            print(f"[DEBUG] Usuario de auth creado: {auth_id}")
        except Exception as auth_error:
            print(f"[ERROR AUTH] {auth_error}")
            raise auth_error

        # 2. Resolver tipo_cliente_id desde la descripción (DNI / RUC)
        tipo_documento_desc = (data.get('tipo_documento') or '').strip().upper()
        tipo_cliente_id = None
        if tipo_documento_desc:
            try:
                td = supabase.table('tipo_documento').select('id_tipo').ilike('descripcion', tipo_documento_desc).limit(1).execute()
                if td.data:
                    tipo_cliente_id = td.data[0]['id_tipo']
                    print(f"[DEBUG] tipo_cliente_id encontrado: {tipo_cliente_id}")
            except Exception as e:
                print(f"[DEBUG] Error buscando tipo_documento: {e}")
                pass

        if not tipo_cliente_id:
            tipo_cliente_id = data.get('tipo_cliente_id') or None
            print(f"[DEBUG] tipo_cliente_id final: {tipo_cliente_id}")

        # 3. Crear registro en tabla cliente
        nuevo_cliente = {
            'numero': numero,
            'correo': correo,
            'contraseña': contraseña,
            'nombre': nombre,
            'documento': data.get('documento'),
            'tipo_cliente_id': tipo_cliente_id,
            'registro_completo': False,
            'auth_id': auth_id
        }
        print(f"[DEBUG] Insertando cliente: {nuevo_cliente}")
        response = supabase.table('cliente').insert(nuevo_cliente).execute()

        if response.data:
            cliente = response.data[0]
            print(f"[DEBUG] Cliente creado exitosamente: {cliente.get('id_cliente')}")
            return jsonify({
                'success': True,
                'message': 'Cuenta creada. Verifica tu correo para continuar.',
                'cliente': cliente,
            }), 201
        else:
            err = response.error or {}
            msg = str(err.get('message') if isinstance(err, dict) else err)
            print(f"[ERROR DB] Error al registrar: {msg}")
            return jsonify({'success': False, 'message': 'Error al registrar. Intenta con otros datos.'}), 400

    except Exception as e:
        import traceback
        print(f"[EXCEPTION COMPLETA] {e}")
        traceback.print_exc()
        user_msg, status = _friendly_signup_error_message(e)
        return jsonify({'success': False, 'message': user_msg}), status

@clientes_bp.route('/api/clientes/login', methods=['POST'])
def login_cliente():
    data = request.json
    correo = (data.get('correo') or '').strip().lower()
    contraseña = data.get('contraseña')

    response = supabase.table('cliente').select('id_cliente, correo, contraseña, nombre, numero, documento, registro_completo, auth_id, "tipo cliente"').eq('correo', correo).limit(1).execute()
    if not response.data:
        return jsonify({'success': False, 'message': 'Correo incorrecto'}), 404

    cliente = response.data[0]

    # Verificar contraseña
    if cliente.get('contraseña') != contraseña:
        tipo_cliente_label = cliente.get('tipo cliente')
        if isinstance(tipo_cliente_label, str) and tipo_cliente_label.lower() == 'google':
            return jsonify({'success': False, 'message': 'Este usuario fue registrado con Google. Vuelve a iniciar sesión con Google.'}), 403
        return jsonify({'success': False, 'message': 'Contraseña incorrecta'}), 401

    # Si tiene auth_id, verificar que el email esté confirmado en Supabase Auth
    auth_id = cliente.get('auth_id')
    if auth_id:
        try:
            auth_user = supabase.auth.admin.get_user(auth_id)
            if not auth_user.user.email_confirmed_at:
                return jsonify({'success': False, 'message': 'Correo pendiente de verificación. Verifica tu email para continuar.'}), 403

            # Marcar como verificado en la tabla cliente si aún no lo está
            if not cliente.get('registro_completo'):
                supabase.table('cliente').update({'registro_completo': True}).eq('id_cliente', cliente['id_cliente']).execute()
                cliente['registro_completo'] = True
        except Exception as e:
            print(f"Error verificando Supabase Auth: {e}")
            # Si falla la verificación, avisar que necesita confirmar email
            if not cliente.get('registro_completo'):
                return jsonify({'success': False, 'message': 'Verifica tu email antes de continuar.'}), 403
    else:
        # Usuario sin auth_id (ej: Google auth antiguo) - requiere verificación local
        if not bool(cliente.get('registro_completo')):
            return jsonify({'success': False, 'message': 'Correo pendiente de verificación'}), 403

    token = _build_jwt_for_cliente(cliente)
    return jsonify({'success': True, 'cliente': cliente, 'token': token, 'token_type': 'Bearer'}), 200


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


@clientes_bp.route('/api/clientes/confirmar-supabase', methods=['POST'])
def confirmar_supabase():
    """Convierte una sesión o código de Supabase en el JWT propio del sistema."""
    try:
        data = request.json or {}
        access_token = (data.get('access_token') or '').strip()
        auth_code = (data.get('auth_code') or '').strip()

        if auth_code and not access_token:
            try:
                exchange = supabase.auth.exchange_code_for_session({"auth_code": auth_code})
                session = getattr(exchange, 'session', None) or getattr(exchange, 'data', None) or exchange
                access_token = getattr(session, 'access_token', None) or (session.get('access_token') if isinstance(session, dict) else None) or access_token
            except Exception as exc:
                return jsonify({'success': False, 'message': f'No se pudo intercambiar el código de Supabase: {exc}'}), 400

        if not access_token:
            return jsonify({'success': False, 'message': 'Falta access_token o auth_code.'}), 400

        try:
            auth_response = supabase.auth.get_user(access_token)
            supabase_user = getattr(auth_response, 'user', None) or (auth_response.get('user') if isinstance(auth_response, dict) else None)
        except Exception as exc:
            return jsonify({'success': False, 'message': f'No se pudo validar la sesión de Supabase: {exc}'}), 401

        if not supabase_user:
            return jsonify({'success': False, 'message': 'No se pudo obtener el usuario de Supabase.'}), 401

        auth_id = getattr(supabase_user, 'id', None) or (supabase_user.get('id') if isinstance(supabase_user, dict) else None)
        correo = getattr(supabase_user, 'email', None) or (supabase_user.get('email') if isinstance(supabase_user, dict) else None)

        cliente = None
        if auth_id:
            res = supabase.table('cliente').select('id_cliente, correo, nombre, numero, documento, registro_completo, auth_id').eq('auth_id', auth_id).limit(1).execute()
            if res.data:
                cliente = res.data[0]

        if not cliente and correo:
            res = supabase.table('cliente').select('id_cliente, correo, nombre, numero, documento, registro_completo, auth_id').eq('correo', correo).limit(1).execute()
            if res.data:
                cliente = res.data[0]

        if not cliente:
            return jsonify({'success': False, 'message': 'No se encontró un cliente asociado a esta cuenta.'}), 404

        if not cliente.get('registro_completo'):
            supabase.table('cliente').update({'registro_completo': True}).eq('id_cliente', cliente['id_cliente']).execute()
            cliente['registro_completo'] = True

        if auth_id and not cliente.get('auth_id'):
            supabase.table('cliente').update({'auth_id': auth_id}).eq('id_cliente', cliente['id_cliente']).execute()
            cliente['auth_id'] = auth_id

        token = _build_jwt_for_cliente(cliente)
        return jsonify({'success': True, 'cliente': cliente, 'token': token, 'token_type': 'Bearer'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@clientes_bp.route('/api/clientes/validar-email', methods=['POST'])
def validar_email():
    """Valida que el email sea válido y no esté registrado."""
    data = request.json
    correo = (data.get('correo') or '').strip().lower()

    if not correo:
        return jsonify({'success': False, 'email_valido': False, 'message': 'Correo requerido'}), 400

    if not EMAIL_PATTERN.match(correo):
        return jsonify({'success': False, 'email_valido': False, 'message': 'Correo electrónico inválido.'}), 400

    existe = supabase.table('cliente').select('id_cliente').eq('correo', correo).limit(1).execute()
    if existe.data:
        return jsonify({'success': False, 'email_valido': False, 'message': 'Este correo ya está registrado.'}), 409

    return jsonify({'success': True, 'email_valido': True, 'message': 'Correo válido'}), 200

@clientes_bp.route('/api/clientes/registrar', methods=['POST'])
def registrar_cliente():
    """Registra el cliente después de validación de email."""
    data = request.json
    correo = (data.get('correo') or '').strip().lower()
    contraseña = (data.get('contraseña') or '').strip()
    nombre = (data.get('nombre') or '').strip()
    numero = (data.get('numero') or '').strip()
    documento = (data.get('documento') or '').strip()
    tipo_documento = (data.get('tipo_documento') or '').strip().upper()
    tipo_cliente_id = data.get('tipo_cliente_id')

    if not correo or not contraseña or not nombre or not numero or not documento:
        return jsonify({'success': False, 'message': 'Faltan datos obligatorios.'}), 400

    if not EMAIL_PATTERN.match(correo):
        return jsonify({'success': False, 'message': 'Correo electrónico inválido.'}), 400

    existe = supabase.table('cliente').select('id_cliente').eq('correo', correo).limit(1).execute()
    if existe.data:
        return jsonify({'success': False, 'message': 'El correo ya está registrado.'}), 409

    try:
        print(f"[DEBUG] Intentando crear usuario de auth para: {correo}")

        try:
            auth_user = supabase.auth.admin.create_user({
                "email": correo,
                "password": contraseña,
                "email_confirm": False
            })
            auth_id = auth_user.user.id
            print(f"[DEBUG] Usuario de auth creado: {auth_id}")
        except Exception as auth_error:
            print(f"[ERROR AUTH] {auth_error}")
            raise auth_error

        tipo_cliente_id_final = None
        if tipo_documento:
            try:
                td = supabase.table('tipo_documento').select('id_tipo').ilike('descripcion', tipo_documento).limit(1).execute()
                if td.data:
                    tipo_cliente_id_final = td.data[0]['id_tipo']
            except:
                pass

        if not tipo_cliente_id_final:
            tipo_cliente_id_final = tipo_cliente_id

        nuevo_cliente = {
            'numero': numero,
            'correo': correo,
            'contraseña': contraseña,
            'nombre': nombre,
            'documento': documento,
            'tipo_cliente_id': tipo_cliente_id_final,
            'registro_completo': False,
            'auth_id': auth_id
        }

        response = supabase.table('cliente').insert(nuevo_cliente).execute()

        if response.data:
            cliente = response.data[0]
            print(f"[DEBUG] Cliente creado exitosamente: {cliente.get('id_cliente')}")
            return jsonify({
                'success': True,
                'message': 'Registro exitoso. Verifica tu Gmail.',
                'cliente': cliente,
            }), 201
        else:
            err = response.error or {}
            msg = str(err.get('message') if isinstance(err, dict) else err)
            print(f"[ERROR DB] Error al registrar: {msg}")
            return jsonify({'success': False, 'message': 'Error al registrar. Intenta con otros datos.'}), 400

    except Exception as e:
        import traceback
        print(f"[EXCEPTION COMPLETA] {e}")
        traceback.print_exc()
        if "already registered" in str(e).lower() or "user already exists" in str(e).lower():
            return jsonify({'success': False, 'message': 'Este correo ya está registrado en el sistema de autenticación.'}), 409
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

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
        