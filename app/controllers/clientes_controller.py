from flask import Blueprint, jsonify, request
import os, json, base64, hmac, hashlib, time, re
from app.services.supabase_client import supabase

EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

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

# ==================== VALIDACIÓN DE EMAIL ====================


@clientes_bp.route('/api/clientes/validar-email', methods=['POST'])
def validar_email():
    """
    POST /api/clientes/validar-email
    Valida que el email exista y pueda recibir el email de confirmación.

    Body: {"correo": "user@example.com", "contraseña": "pass123"}

    Response (éxito):
    {
        "success": true,
        "email_valido": true,
        "auth_id": "uuid..."
    }

    Response (error):
    {
        "success": false,
        "email_valido": false,
        "message": "Gmail inválido"
    }
    """
    try:
        print("[VALIDAR EMAIL] Recibida solicitud")
        data = request.json or {}
        print(f"[VALIDAR EMAIL] Data recibida: {data}")
        correo = (data.get('correo') or '').strip().lower()
        contraseña = (data.get('contraseña') or '').strip()

        print(f"[VALIDAR EMAIL] Correo: {correo}, Contraseña: {'*' * len(contraseña)}")

        if not correo or not contraseña:
            print("[VALIDAR EMAIL] Faltan correo o contraseña")
            return jsonify({'success': False, 'email_valido': False, 'message': 'Correo y contraseña requeridos.'}), 400

        if not EMAIL_PATTERN.match(correo):
            print(f"[VALIDAR EMAIL] Email no cumple patrón: {correo}")
            return jsonify({'success': False, 'email_valido': False, 'message': 'Correo electrónico inválido.'}), 400

        # Verificar que no esté duplicado
        existe = supabase.table('cliente').select('id_cliente').eq('correo', correo).limit(1).execute()
        if existe.data:
            print(f"[VALIDAR EMAIL] Correo ya registrado: {correo}")
            return jsonify({'success': False, 'email_valido': False, 'message': 'El correo ya está registrado.'}), 409

        # Crear usuario temporal en Supabase Auth
        print(f"[VALIDAR EMAIL] Creando usuario temporal para: {correo}")
        auth_user = supabase.auth.admin.create_user({
            "email": correo,
            "password": contraseña,
            "email_confirm": False
        })
        auth_id = auth_user.user.id
        print(f"[VALIDAR EMAIL] Usuario temporal creado: {auth_id}")

        # Intentar enviar email de confirmación
        try:
            print(f"[VALIDAR EMAIL] Intentando enviar email a: {correo}")
            supabase.auth.admin.send_user_confirmation_email(auth_id)
            print(f"[VALIDAR EMAIL] Email enviado exitosamente a {correo}")
            # Si éxito, devolver el auth_id para que el frontend lo use en el registro
            return jsonify({
                'success': True,
                'email_valido': True,
                'auth_id': auth_id,
                'message': 'Email válido. Procede a completar tu registro.'
            }), 200
        except Exception as e:
            print(f"[VALIDAR EMAIL] Error enviando email: {e}")
            # Si falla, eliminar el usuario temporal
            try:
                supabase.auth.admin.delete_user(auth_id)
                print(f"[VALIDAR EMAIL] Usuario temporal eliminado: {auth_id}")
            except Exception as delete_error:
                print(f"[VALIDAR EMAIL] Error eliminando usuario: {delete_error}")
            return jsonify({'success': False, 'email_valido': False, 'message': 'Gmail inválido. Verifica que sea correcto.'}), 400

    except Exception as e:
        print(f"[VALIDAR EMAIL] EXCEPCIÓN: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'email_valido': False, 'message': f'Error al validar email: {str(e)}'}), 500

# ==================== REGISTRO COMPLETO ====================


@clientes_bp.route('/api/clientes/registrar', methods=['POST'])
def registrar_cliente():
    """
    POST /api/clientes/registrar
    Completa el registro después de validar el email.

    Body:
    {
        "auth_id": "uuid...",
        "correo": "user@example.com",
        "nombre": "Juan Pérez",
        "documento": "12345678",
        "numero": "987654321",
        "tipo_documento": "DNI" o "RUC",
        "tipo_cliente_id": "uuid..." (opcional),
        "estado_cliente_id": "uuid..." (opcional)
    }
    """
    try:
        data = request.json or {}
        auth_id = (data.get('auth_id') or '').strip()
        correo = (data.get('correo') or '').strip().lower()
        nombre = (data.get('nombre') or '').strip()
        numero = (data.get('numero') or '').strip()
        documento = (data.get('documento') or '').strip()

        if not auth_id or not correo or not nombre or not numero:
            return jsonify({'success': False, 'message': 'Faltan datos obligatorios.'}), 400

        # Verificar que el auth_id exista en Supabase Auth
        try:
            auth_user = supabase.auth.admin.get_user(auth_id)
            print(f"[DEBUG REGISTRAR] Usuario auth verificado: {auth_id}")
        except Exception as e:
            print(f"[ERROR REGISTRAR] auth_id inválido: {e}")
            return jsonify({'success': False, 'message': 'Sesión inválida. Intenta de nuevo.'}), 400

        # Resolver tipo_cliente_id desde la descripción (DNI / RUC)
        tipo_documento_desc = (data.get('tipo_documento') or '').strip().upper()
        tipo_cliente_id = None
        if tipo_documento_desc:
            try:
                td = supabase.table('tipo_documento').select('id_tipo').ilike('descripcion', tipo_documento_desc).limit(1).execute()
                if td.data:
                    tipo_cliente_id = td.data[0]['id_tipo']
                    print(f"[DEBUG REGISTRAR] tipo_cliente_id encontrado: {tipo_cliente_id}")
            except Exception as e:
                print(f"[DEBUG REGISTRAR] Error buscando tipo_documento: {e}")
                pass

        if not tipo_cliente_id:
            tipo_cliente_id = data.get('tipo_cliente_id') or None

        # Crear registro en tabla cliente
        nuevo_cliente = {
            'numero': numero,
            'correo': correo,
            'nombre': nombre,
            'documento': documento,
            'tipo_cliente_id': tipo_cliente_id,
            'registro_completo': False,
            'auth_id': auth_id
        }

        print(f"[DEBUG REGISTRAR] Insertando cliente: {nuevo_cliente}")
        response = supabase.table('cliente').insert(nuevo_cliente).execute()

        if response.data:
            cliente = response.data[0]
            print(f"[DEBUG REGISTRAR] Cliente creado: {cliente.get('id_cliente')}")
            return jsonify({
                'success': True,
                'message': 'Cuenta creada. Verifica tu correo para continuar.',
                'cliente': cliente
            }), 201
        else:
            err = response.error or {}
            msg = str(err.get('message') if isinstance(err, dict) else err)
            print(f"[ERROR DB REGISTRAR] {msg}")
            return jsonify({'success': False, 'message': 'Error al registrar.'}), 400

    except Exception as e:
        print(f"[EXCEPTION REGISTRAR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

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

            # Forzar envío de email de confirmación
            try:
                supabase.auth.admin.send_user_invitation_email(auth_id)
                print(f"[EMAIL] Email de confirmación enviado a {correo}")
            except Exception as e:
                print(f"[EMAIL ERROR] Error enviando email: {e}")
                # Si falla el envío, eliminar el usuario de auth creado
                try:
                    supabase.auth.admin.delete_user(auth_id)
                    print(f"[DEBUG] Usuario de auth eliminado por error de email: {auth_id}")
                except Exception as delete_error:
                    print(f"[ERROR] No se pudo eliminar usuario de auth: {delete_error}")
                raise Exception('Correo inválido. Verifica la dirección e intenta con otro.')
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
        if "already registered" in str(e).lower() or "user already exists" in str(e).lower():
            return jsonify({'success': False, 'message': 'Este correo ya está registrado en el sistema de autenticación.'}), 409
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

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