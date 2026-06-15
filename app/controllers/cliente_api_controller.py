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
from app.services.supabase_client import supabase
from app.controllers.clientes_controller import _build_jwt_for_cliente
from app.services.email_verification_service import create_verification, send_verification_email
from app.core.exceptions import (
    AppException,
    EntityNotFoundException,
    InvalidDataException,
    DuplicateEntityException
)

EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# ==================== SETUP ====================

cliente_api_bp = Blueprint(
    'cliente_api',
    __name__,
    url_prefix='/api/clientes'
)

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

# ==================== VALIDACIÓN DE EMAIL ====================


@cliente_api_bp.route('/test', methods=['POST', 'GET'])
def test_endpoint():
    """Endpoint de prueba"""
    print("[TEST] Se ejecutó el endpoint de prueba")
    if request.method == 'POST':
        data = request.get_json() or {}
        print(f"[TEST] Data recibida: {data}")
        return jsonify({'success': True, 'message': 'Test POST OK', 'data': data}), 200
    return jsonify({'success': True, 'message': 'Test GET OK'}), 200


@cliente_api_bp.route('/validar-email', methods=['POST'])
def validar_email_api():
    """
    POST /api/clientes/validar-email
    Valida que el email tenga formato correcto y no esté registrado.
    """
    print("[VALIDAR EMAIL] Recibida solicitud")
    try:
        data = request.get_json() or {}
        correo = (data.get('correo') or '').strip().lower()

        if not correo:
            return jsonify({'success': False, 'email_valido': False, 'message': 'Correo requerido.'}), 400

        if not EMAIL_PATTERN.match(correo):
            return jsonify({'success': False, 'email_valido': False, 'message': 'Correo electrónico inválido.'}), 400

        existe = supabase.table('cliente').select('id_cliente').eq('correo', correo).limit(1).execute()
        if existe.data:
            return jsonify({'success': False, 'email_valido': False, 'message': 'El correo ya está registrado.'}), 409

        return jsonify({'success': True, 'email_valido': True, 'message': 'Correo válido.'}), 200

    except Exception as e:
        print(f"[VALIDAR EMAIL] EXCEPCIÓN: {e}")
        return jsonify({'success': False, 'email_valido': False, 'message': f'Error al validar email: {str(e)}'}), 500

# ==================== REGISTRO COMPLETO ====================


@cliente_api_bp.route('/registrar', methods=['POST'])
def registrar_cliente_api():
    """
    POST /api/clientes/registrar
    Registra el cliente después de validar el email.
    """
    print("[REGISTRAR] Recibida solicitud")
    try:
        data = request.get_json() or {}
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
            auth_user = supabase.auth.admin.create_user({
                "email": correo,
                "password": contraseña,
                "email_confirm": False
            })
            auth_id = auth_user.user.id
            print(f"[REGISTRAR] Usuario auth creado: {auth_id}")
        except Exception as auth_error:
            print(f"[ERROR AUTH] {auth_error}")
            if "already registered" in str(auth_error).lower() or "user already exists" in str(auth_error).lower():
                return jsonify({'success': False, 'message': 'Este correo ya está registrado.'}), 409
            return jsonify({'success': False, 'message': f'Error: {str(auth_error)}'}), 500

        # Resolver tipo_cliente_id desde la descripción (DNI / RUC)
        tipo_cliente_id_final = None
        if tipo_documento:
            try:
                td = supabase.table('tipo_documento').select('id_tipo').ilike('descripcion', tipo_documento).limit(1).execute()
                if td.data:
                    tipo_cliente_id_final = td.data[0]['id_tipo']
            except Exception:
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
            cliente_id = cliente.get('id_cliente')
            print(f"[REGISTRAR] Cliente creado: {cliente_id}")

            verification_token = None
            try:
                verificacion = create_verification(cliente_id, correo, nombre)
                verification_token = verificacion['verification_token']
                send_verification_email(correo, nombre, verificacion['codigo'], int(verificacion['ttl_minutes']))
                print(f"[REGISTRAR] Email de verificación enviado a {correo}")
            except Exception as email_error:
                print(f"[WARN EMAIL] No se pudo enviar email: {email_error}")

            return jsonify({
                'success': True,
                'message': 'Registro exitoso. Verifica tu Gmail.',
                'cliente': cliente,
                'verification_token': verification_token
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

# ==================== CRUD ENDPOINTS ====================


@cliente_api_bp.route('', methods=['POST'])
def crear_cliente():
    """
    POST /api/clientes - Usa Supabase Auth para verificación de correo
    Crea un nuevo cliente.

    Body:
    {
        "nombre": "Juan Pérez",
        "correo": "juan@example.com",
        "documento": "12345678",
        "numero": "987654321",
        "contraseña": "pass123",
        "tipo_documento": "DNI" o "RUC",
        "tipo_cliente_id": "uuid...",
        "estado_cliente_id": "uuid..."
    }
    """
    try:
        data = request.get_json() or {}
        correo = (data.get('correo') or '').strip().lower()
        contraseña = (data.get('contraseña') or '').strip()
        nombre = (data.get('nombre') or '').strip()
        numero = (data.get('numero') or '').strip()

        if not correo or not contraseña or not nombre or not numero:
            return jsonify({'success': False, 'message': 'Faltan datos obligatorios.'}), 400

        if not EMAIL_PATTERN.match(correo):
            return jsonify({'success': False, 'message': 'Correo electrónico inválido.'}), 400

        # Verificar duplicado
        existe = supabase.table('cliente').select('id_cliente').eq('correo', correo).limit(1).execute()
        if existe.data:
            return jsonify({'success': False, 'message': 'El correo ya está registrado.'}), 409

        # 1. Crear usuario en Supabase Auth — envía email de confirmación automáticamente
        print(f"[DEBUG] Creando usuario de auth para: {correo}")
        try:
            auth_user = supabase.auth.admin.create_user({
                "email": correo,
                "password": contraseña,
                "email_confirm": False
            })
            auth_id = auth_user.user.id
            print(f"[DEBUG] Usuario de auth creado: {auth_id}")

            # Enviar email de confirmación
            supabase.auth.admin.invite_user_by_email(email=correo)
            print(f"[EMAIL] Email de confirmación enviado a {correo}")
        except Exception as e:
            print(f"[ERROR] {e}")
            if "already registered" in str(e).lower() or "user already exists" in str(e).lower():
                return jsonify({'success': False, 'message': 'Este correo ya está registrado en el sistema de autenticación.'}), 409
            raise e

        # 2. Resolver tipo_cliente_id desde la descripción (DNI / RUC)
        tipo_documento_desc = (data.get('tipo_documento') or '').strip().upper()
        tipo_cliente_id = None
        if tipo_documento_desc:
            try:
                td = supabase.table('tipo_documento').select('id_tipo').ilike('descripcion', tipo_documento_desc).limit(1).execute()
                if td.data:
                    tipo_cliente_id = td.data[0]['id_tipo']
            except Exception:
                pass

        if not tipo_cliente_id:
            tipo_cliente_id = data.get('tipo_cliente_id') or None

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

        response = supabase.table('cliente').insert(nuevo_cliente).execute()
        if response.data:
            cliente = response.data[0]
            return jsonify({
                'success': True,
                'message': 'Cuenta creada. Verifica tu correo para continuar.',
                'cliente': cliente
            }), 201
        else:
            err = response.error or {}
            msg = str(err.get('message') if isinstance(err, dict) else err)
            print(f"[ERROR DB] {msg}")
            return jsonify({'success': False, 'message': 'Error al registrar.'}), 400

    except Exception as e:
        import traceback
        print(f"[EXCEPTION] {e}")
        traceback.print_exc()
        if "already registered" in str(e).lower() or "user already exists" in str(e).lower():
            return jsonify({'success': False, 'message': 'Este correo ya está registrado en el sistema de autenticación.'}), 409
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


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
