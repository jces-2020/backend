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
from app.services.cliente_service import ClienteService
from app.repositories.cliente_repository import ClienteRepository
from app.services.supabase_client import supabase
from app.controllers.clientes_controller import _build_jwt_for_cliente
from app.services.email_verification_service import (
    create_verification,
    consume_verification,
    get_verification,
    send_verification_email,
)
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
        verification = create_verification(cliente.id_cliente, cliente.correo, cliente.nombre)
        entry = get_verification(verification["verification_token"])
        if entry:
            send_verification_email(entry.correo, entry.nombre, entry.codigo, int(verification["ttl_minutes"]))

        return _success_response({
            **cliente.to_dict(),
            "verification_token": verification["verification_token"],
            "correo_verificacion_enviado": True,
            "registro_completo": False,
        }, "Cliente creado. Revisa tu correo para verificar tu cuenta.", 201)

    except InvalidDataException as e:
        return _error_response(e)
    except DuplicateEntityException as e:
        return _error_response(e)
    except Exception as e:
        print(f"Error en crear_cliente: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@cliente_api_bp.route('/verificar-correo', methods=['POST'])
def verificar_correo():
    data = request.get_json() or {}
    token = (data.get('verification_token') or '').strip()
    codigo = (data.get('codigo') or '').strip()

    if not token or not codigo:
        return jsonify({'success': False, 'message': 'Token y código son requeridos'}), 400

    entry = consume_verification(token, codigo)
    if not entry:
        return jsonify({'success': False, 'message': 'Código incorrecto o expirado'}), 400

    try:
        updated = supabase.table('cliente').update({'registro_completo': True}).eq('id_cliente', entry.cliente_id).execute()
        cliente = updated.data[0] if updated.data else None
        if not cliente:
            return jsonify({'success': False, 'message': 'No se pudo actualizar el cliente'}), 500

        return _success_response({
            'cliente': cliente,
            'token': _build_jwt_for_cliente(cliente),
            'token_type': 'Bearer'
        }, 'Correo verificado correctamente', 200)
    except Exception as e:
        print(f"Error verificando correo: {str(e)}")
        return jsonify({'success': False, 'message': 'No se pudo verificar el correo'}), 500


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
