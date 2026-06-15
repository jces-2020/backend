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


@cliente_api_bp.route('/validar-email', methods=['POST'])
def validar_email_api():
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
        data = request.get_json() or {}
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


@cliente_api_bp.route('/registrar', methods=['POST'])
def registrar_cliente_api():
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
        data = request.get_json() or {}
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

        # 1. Crear usuario en Supabase Auth
        print(f"[DEBUG] Creando usuario de auth para: {correo}")
        auth_user = supabase.auth.admin.create_user({
            "email": correo,
            "password": contraseña,
            "email_confirm": False
        })
        auth_id = auth_user.user.id
        print(f"[DEBUG] Usuario de auth creado: {auth_id}")

        # Forzar envío de email de confirmación
        try:
            supabase.auth.admin.send_user_confirmation_email(auth_id)
            print(f"[EMAIL] Email de confirmación enviado a {correo}")
        except Exception as e:
            print(f"[EMAIL ERROR] Error enviando email: {e}")
            # Si falla el envío, eliminar el usuario de auth creado
            try:
                supabase.auth.admin.delete_user(auth_id)
                print(f"[DEBUG] Usuario de auth eliminado por error de email: {auth_id}")
            except Exception as delete_error:
                print(f"[ERROR] No se pudo eliminar usuario de auth: {delete_error}")
            return jsonify({'success': False, 'message': 'Correo inválido. Verifica la dirección e intenta con otro.'}), 400

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
