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
    return data.get('tipo_cliente_id') or None

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
        payload = {
            'nombre': (data.get('nombre') or '').strip(),
            'correo': (data.get('correo') or '').strip().lower(),
            'documento': (data.get('documento') or '').strip(),
            'numero': (data.get('numero') or '').strip(),
            'contraseña': (data.get('contraseña') or '').strip(),
            'tipo_cliente_id': _resolver_tipo_cliente_id(data),
            'estado_cliente_id': data.get('estado_cliente_id'),
            'cuenta_temporal': data.get('cuenta_temporal', False),
        }

        cliente = _service.crear_cliente(payload)
        return jsonify({
            'success': True,
            'message': 'Registro exitoso',
            'cliente': cliente.to_dict(),
        }), 201

    except InvalidDataException as e:
        return jsonify({'success': False, 'message': e.message}), e.code
    except DuplicateEntityException as e:
        return jsonify({'success': False, 'message': e.message}), e.code
    except Exception as e:
        print(f"Error en registrar_cliente_api: {str(e)}")
        return jsonify({'success': False, 'message': 'No se pudo registrar el cliente.'}), 500
