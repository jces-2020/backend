"""
Controller para Cliente API - Maneja HTTP requests/responses.

Patrón: Controller (MVC) - Solo orquesta HTTP
Responsabilidades:
- Recibir requests HTTP
- Delegar a servicio
- Formatear respuestas
- Manejo de errores HTTP

NO hace:
- Queries a BD (usa servicio)
- Validaciones complejas (usa servicio)
- Lógica de negocio (usa servicio)
"""
from flask import Blueprint, request, jsonify
import re
import uuid
import os
import json
import base64
import hmac
import hashlib
import time
from app.services.cliente_service import ClienteService
from app.repositories.cliente_repository import ClienteRepository
from app.services.supabase_client import supabase
from app.core.exceptions import (
    AppException,
    EntityNotFoundException,
    InvalidDataException,
    DuplicateEntityException
)

# ==================== SETUP ====================

cliente_api_bp = Blueprint(
    'cliente_api',
    __name__,
    url_prefix='/api/clientes'
)

# Inyección de dependencias
_repository = ClienteRepository(supabase)
_service = ClienteService(_repository)

# ==================== HELPERS ====================


def _error_response(exc: AppException, status_code: int = None):
    """Convierte excepción a respuesta JSON"""
    status = status_code or exc.code
    return jsonify({
        'success': False,
        'message': exc.message
    }), status


def _success_response(data: any, message: str = None, status_code: int = 200):
    """Formatea respuesta exitosa"""
    return jsonify({
        'success': True,
        'message': message,
        'data': data
    }), status_code


def _resolver_tipo_cliente_id(data: dict) -> str | None:
    """Resuelve tipo_cliente_id desde tipo_documento o usa el UUID recibido."""
    tipo_documento_desc = (data.get('tipo_documento') or '').strip().upper()
    if tipo_documento_desc:
        td = supabase.table('tipo_documento')\
            .select('id_tipo')\
            .ilike('descripcion', tipo_documento_desc)\
            .limit(1)\
            .execute()
        if td.data:
            return td.data[0].get('id_tipo')
    raw = (data.get('tipo_cliente_id') or '').strip()
    if not raw or raw.lower() in ('null', 'none', 'undefined'):
        return None
    try:
        uuid.UUID(raw)
        return raw
    except Exception:
        return None


def _email_formato_valido(correo: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', correo or ''))


def _build_jwt_for_cliente(cliente: dict) -> str:
    """Genera JWT local para sesión del panel cliente."""
    secret = os.environ.get('JWT_SECRET', 'vidriobras-secret')
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": cliente.get('id_cliente'),
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


def _auth_sign_up(correo: str, contrasena: str, nombre: str) -> tuple[bool, str]:
    """Crea usuario en Supabase Auth y dispara correo de confirmación."""
    try:
        supabase.auth.sign_up({
            'email': correo,
            'password': contrasena,
            'options': {
                'data': {
                    'name': nombre,
                }
            }
        })
        return True, 'Correo de confirmación enviado.'
    except Exception as e:
        msg = str(e)
        if 'already registered' in msg.lower() or 'user already registered' in msg.lower():
            return False, 'already_registered'
        return False, f'No se pudo registrar en autenticación: {msg}'


def _auth_email_confirmado(correo: str, contrasena: str) -> bool:
    """Confirma estado del email intentando login en Supabase Auth."""
    try:
        supabase.auth.sign_in_with_password({
            'email': correo,
            'password': contrasena,
        })
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
        return True
    except Exception:
        return False


def _extraer_auth_user(access_token: str):
    """Obtiene user de Supabase Auth a partir del access_token del enlace."""
    try:
        user_resp = supabase.auth.get_user(access_token)
        user = getattr(user_resp, 'user', None)
        if user is None and isinstance(user_resp, dict):
            user = user_resp.get('user')
        return user
    except Exception:
        return None

# ==================== CRUD ENDPOINTS ====================


@cliente_api_bp.route('', methods=['POST'])
def crear_cliente():
    """
    POST /api/clientes
    Crea un nuevo cliente.

    Body:
    {
        "nombre": "Juan Pérez",
        "correo": "juan@example.com",
        "documento": "12345678",
        "numero": "987654321",
        "contraseña": "pass123",
        "tipo_cliente_id": "uuid...",
        "estado_cliente_id": "uuid..."
    }
    """
    try:
        data = request.get_json() or {}
        cliente = _service.crear_cliente(data)
        return _success_response(cliente.to_dict(), "Cliente creado", 201)

    except InvalidDataException as e:
        return _error_response(e)
    except DuplicateEntityException as e:
        return _error_response(e)
    except Exception as e:
        print(f"Error en crear_cliente: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@cliente_api_bp.route('', methods=['GET'])
def listar_clientes():
    """
    GET /api/clientes?limit=100&offset=0&buscar=patron
    Lista clientes.

    Query params:
    - limit: Máximo de resultados (default: 100)
    - offset: Desplazamiento para paginación (default: 0)
    - buscar: Patrón de búsqueda (busca en nombre/documento)
    """
    try:
        # Obtener parámetros
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        patron = request.args.get('buscar', '').strip()

        # Ejecutar búsqueda
        if patron:
            clientes = _service.buscar_clientes(patron)
        else:
            clientes = _service.obtener_todos_clientes(limit, offset)

        # Formatear respuesta
        data = [c.to_dict() for c in clientes]
        return _success_response(data, f"Encontrados {len(data)} clientes")

    except Exception as e:
        print(f"Error en listar_clientes: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@cliente_api_bp.route('/<cliente_id>', methods=['GET'])
def obtener_cliente(cliente_id: str):
    """
    GET /api/clientes/<cliente_id>
    Obtiene un cliente específico.
    """
    try:
        cliente = _service.obtener_cliente_o_error(cliente_id)
        return _success_response(cliente.to_dict(), "Cliente obtenido")

    except EntityNotFoundException as e:
        return _error_response(e)
    except Exception as e:
        print(f"Error en obtener_cliente: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@cliente_api_bp.route('/<cliente_id>', methods=['PUT'])
def actualizar_cliente(cliente_id: str):
    """
    PUT /api/clientes/<cliente_id>
    Actualiza un cliente.

    Body:
    {
        "nombre": "Juan García",
        "correo": "juan.new@example.com",
        ...
    }
    """
    try:
        data = request.get_json() or {}
        cliente = _service.actualizar_cliente(cliente_id, data)
        return _success_response(cliente.to_dict(), "Cliente actualizado")

    except InvalidDataException as e:
        return _error_response(e)
    except EntityNotFoundException as e:
        return _error_response(e)
    except DuplicateEntityException as e:
        return _error_response(e)
    except Exception as e:
        print(f"Error en actualizar_cliente: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@cliente_api_bp.route('/<cliente_id>', methods=['DELETE'])
def eliminar_cliente(cliente_id: str):
    """
    DELETE /api/clientes/<cliente_id>
    Elimina un cliente.
    """
    try:
        _service.eliminar_cliente(cliente_id)
        return _success_response(None, "Cliente eliminado")

    except EntityNotFoundException as e:
        return _error_response(e)
    except Exception as e:
        print(f"Error en eliminar_cliente: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== BÚSQUEDAS ESPECIALES ====================


@cliente_api_bp.route('/correo/<correo>', methods=['GET'])
def buscar_por_correo(correo: str):
    """GET /api/clientes/correo/<correo>"""
    try:
        cliente = _service.buscar_cliente_por_correo(correo)
        if not cliente:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404

        return _success_response(cliente.to_dict())
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@cliente_api_bp.route('/documento/<documento>', methods=['GET'])
def buscar_por_documento(documento: str):
    """GET /api/clientes/documento/<documento>"""
    try:
        cliente = _service.buscar_cliente_por_documento(documento)
        if not cliente:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404

        return _success_response(cliente.to_dict())
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ESTADÍSTICAS ====================


@cliente_api_bp.route('/stats', methods=['GET'])
def obtener_estadisticas():
    """GET /api/clientes/stats"""
    try:
        total = _service.contar_clientes()
        return _success_response({
            'total_clientes': total
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@cliente_api_bp.route('/validar-email', methods=['POST'])
def validar_email_api():
    """Valida si el correo está disponible para registro."""
    try:
        data = request.get_json() or {}
        correo = (data.get('correo') or '').strip().lower()
        if not correo:
            return jsonify({'email_valido': False, 'message': 'Correo requerido'}), 400
        if not _email_formato_valido(correo):
            return jsonify({'email_valido': False, 'message': 'Formato de correo inválido.'}), 200

        existente = _repository.find_by_correo(correo)
        if existente:
            return jsonify({'email_valido': False, 'message': 'El correo ya está registrado.'}), 200

        return jsonify({'email_valido': True, 'message': 'Correo disponible'}), 200
    except Exception as e:
        return jsonify({'email_valido': False, 'message': str(e)}), 500


@cliente_api_bp.route('/registrar', methods=['POST'])
def registrar_cliente_api():
    """Registro público de cliente (flujo login/registro)."""
    try:
        data = request.get_json() or {}
        correo = (data.get('correo') or '').strip().lower()
        nombre = (data.get('nombre') or '').strip()
        documento = (data.get('documento') or '').strip()
        contrasena = (data.get('contraseña') or '').strip()

        if not _email_formato_valido(correo):
            return jsonify({'success': False, 'message': 'Formato de correo inválido.'}), 400
        if not contrasena:
            return jsonify({'success': False, 'message': 'Contraseña requerida.'}), 400

        if _repository.find_by_correo(correo):
            return jsonify({'success': False, 'message': 'El correo ya está registrado.'}), 409
        if documento and _repository.find_by_documento(documento):
            return jsonify({'success': False, 'message': 'Ya existe un cliente registrado con este DNI/documento.'}), 409
        if nombre and _repository.find_by_nombre_exacto(nombre):
            return jsonify({'success': False, 'message': 'Ya existe un cliente registrado con este nombre.'}), 409

        auth_ok, auth_msg = _auth_sign_up(correo, contrasena, nombre)
        if not auth_ok:
            return jsonify({'success': False, 'message': auth_msg}), 400

        payload = {
            'nombre': nombre,
            'correo': correo,
            'documento': documento,
            'numero': (data.get('numero') or '').strip(),
            'contraseña': contrasena,
            'tipo_cliente_id': _resolver_tipo_cliente_id(data),
            'estado_cliente_id': data.get('estado_cliente_id'),
            'cuenta_temporal': data.get('cuenta_temporal', False),
        }

        cliente = _service.crear_cliente(payload)

        return jsonify({
            'success': True,
            'message': 'Registro exitoso. Mira tu Gmail para confirmar tu cuenta.',
            'cliente': cliente.to_dict(),
        }), 201

    except InvalidDataException as e:
        return jsonify({'success': False, 'message': e.message}), e.code
    except DuplicateEntityException as e:
        return jsonify({'success': False, 'message': e.message}), e.code
    except Exception as e:
        print(f"Error en registrar_cliente_api: {str(e)}")
        return jsonify({'success': False, 'message': 'No se pudo registrar el cliente.'}), 500


@cliente_api_bp.route('/confirmar-supabase', methods=['POST'])
def confirmar_supabase_api():
    """Convierte confirmación de Supabase (access_token) en JWT local y sesión cliente."""
    try:
        data = request.get_json() or {}
        access_token = (data.get('access_token') or '').strip()
        if not access_token:
            return jsonify({'success': False, 'message': 'Falta access_token'}), 400

        auth_user = _extraer_auth_user(access_token)
        if not auth_user:
            return jsonify({'success': False, 'message': 'No se pudo validar usuario de Supabase'}), 401

        email = (getattr(auth_user, 'email', None) if not isinstance(auth_user, dict) else auth_user.get('email')) or ''
        email = email.strip().lower()
        if not email:
            return jsonify({'success': False, 'message': 'Usuario sin correo en Supabase Auth'}), 400

        cliente = _repository.find_by_correo(email)
        if not cliente:
            user_id = (getattr(auth_user, 'id', None) if not isinstance(auth_user, dict) else auth_user.get('id')) or ''
            user_meta = (getattr(auth_user, 'user_metadata', None) if not isinstance(auth_user, dict) else auth_user.get('user_metadata')) or {}
            nombre = (user_meta.get('name') or email.split('@')[0]).strip()

            insert_resp = supabase.table('cliente').insert({
                'correo': email,
                'contraseña': user_id or 'supabase-auth',
                'nombre': nombre,
                'numero': '',
                'documento': '',
                'tipo_cliente_id': None,
            }).execute()
            if not insert_resp.data:
                return jsonify({'success': False, 'message': 'No se pudo crear cliente local tras confirmar correo'}), 500
            cliente_row = insert_resp.data[0]
        else:
            cliente_row = cliente.to_dict()

        token = _build_jwt_for_cliente(cliente_row)
        return jsonify({
            'success': True,
            'token': token,
            'token_type': 'Bearer',
            'cliente': cliente_row,
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error confirmando Supabase: {str(e)}'}), 500
