from flask import Blueprint, request, jsonify
from typing import Optional, Tuple, Dict, Any
from app.services.supabase_client import supabase

selector_bp = Blueprint('selector_bp', __name__, url_prefix='/api/selector')

# IDs fijos para las dos áreas solicitadas
OPERACIONES_ID = "3f31e127-c7f1-49cf-8c95-efb846882165"
ALMACEN_ID = "8426fd1a-2633-49d1-bc83-f6400bb58708"


def _validar_personal_por_area(nombre: str, area_id: str) -> Optional[Dict[str, Any]]:
    """Busca un personal por nombre y verifica que su tipo_personal_id coincida con el area_id.
    
    Args:
        nombre: Nombre del personal a buscar
        area_id: ID del área (que debe coincidir con tipo_personal_id)
    
    Returns:
        Dict con datos del personal si existe y pertenece al área, None si no existe.
    """
    try:
        # Buscar personal por nombre en tabla personal
        resp = supabase.table('personal').select('*').ilike('nombre', f'%{nombre}%').execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        data = getattr(resp, 'data', None) if resp is not None else None
        
        if err:
            print(f"Error buscando personal: {err}")
            return None
        
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        
        personal = data[0] if isinstance(data, list) else data
        
        # Obtener el tipo_personal_id del personal
        tipo_personal_id = personal.get('tipo_personal_id')
        
        if not tipo_personal_id:
            return None
        
        # Verificar que el tipo_personal_id coincida con el area_id solicitada
        # Los IDs de tipo_personal son los mismos que los IDs de área
        if tipo_personal_id == area_id:
            return personal
        else:
            # El personal existe pero no pertenece a esta área
            print(f"Personal '{nombre}' pertenece a área {tipo_personal_id}, no a {area_id}")
            return None
            
    except Exception as e:
        print(f"Error validando personal por área: {str(e)}")
        return None


def _obtener_tipo_personal(tipo_personal_id: str) -> Optional[str]:
    """Obtiene la descripción del tipo de personal.
    
    Returns:
        String con la descripción del tipo, None si no existe.
    """
    try:
        resp = supabase.table('tipo_personal').select('descripcion').eq('id_tipo', tipo_personal_id).single().execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        data = getattr(resp, 'data', None) if resp is not None else None
        
        if err or not data:
            return None
        
        return data.get('descripcion')
    except Exception:
        return None


@selector_bp.route('/areas', methods=['GET'])
def listar_areas():
    """Devuelve las áreas disponibles con sus IDs para que el frontend pueda mostrarlas."""
    areas = [
        {"id": OPERACIONES_ID, "name": "OPERACIONES", "route": "/login"},
        {"id": ALMACEN_ID, "name": "ALMACÉN", "route": "/login-almacen"},
    ]
    return jsonify({"success": True, "data": areas})


@selector_bp.route('/login', methods=['POST'])
def login_area():
    """Valida que el `area_id` enviado esté permitido para iniciar sesión en esa área.

    Body JSON esperado: { 
        "area_id": "...",
        "nombre": "...",
        "codigo_empresa": "..."
    }
    """
    try:
        data = request.get_json() or {}
        area_id = data.get('area_id')
        nombre = data.get('nombre', '')
        codigo_empresa = data.get('codigo_empresa', '')
        
        if not area_id:
            return jsonify({"success": False, "message": "area_id requerido"}), 400

        if area_id == OPERACIONES_ID:
            area = "OPERACIONES"
        elif area_id == ALMACEN_ID:
            area = "ALMACÉN"
        else:
            return jsonify({"success": False, "message": "Acceso denegado: area_id inválido"}), 403

        # Aquí podrías validar credenciales contra la BD (nombre y codigo_empresa)
        # Por ahora, aceptamos si el area_id es válido y hay datos
        if not nombre or not codigo_empresa:
            return jsonify({"success": False, "message": "Nombre y código de empresa requeridos"}), 400

        # Generar respuesta exitosa
        response_data = {
            "area_id": area_id,
            "area": area,
            "nombre": nombre,
            "codigo_empresa": codigo_empresa,
            "token": f"token_{area}_{nombre}_{codigo_empresa}",  # fake token, integrar con JWT si es necesario
            "access_token": f"token_{area}_{nombre}_{codigo_empresa}",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        return jsonify({"success": True, "data": response_data, "message": "Acceso permitido"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@selector_bp.route('/login-operaciones', methods=['POST'])
def login_operaciones():
    """Endpoint específico para login del área de OPERACIONES.
    
    Body JSON esperado: {
        "area_id": "3f31e127-c7f1-49cf-8c95-efb846882165",
        "nombre": "...",
        "codigo_empresa": "..."
    }
    
    Solo permite login si el personal está asociado al área OPERACIONES.
    """
    try:
        data = request.get_json() or {}
        area_id = data.get('area_id')
        nombre = data.get('nombre', '').strip()
        codigo_empresa = data.get('codigo_empresa', '').strip()

        # Validar que sea la credencial correcta para OPERACIONES
        if area_id != OPERACIONES_ID:
            return jsonify({
                "success": False,
                "message": "Acceso denegado: credencial no válida para OPERACIONES"
            }), 403

        if not nombre or not codigo_empresa:
            return jsonify({
                "success": False,
                "message": "Nombre y código de empresa requeridos"
            }), 400

        # Validar contra la base de datos Y verificar que esté asociado a OPERACIONES
        personal = _validar_personal_por_area(nombre, OPERACIONES_ID)
        if not personal:
            return jsonify({
                "success": False,
                "message": f"Usuario '{nombre}' no tiene acceso al área OPERACIONES o no existe en el sistema"
            }), 401

        # Obtener tipo de personal
        tipo_personal = _obtener_tipo_personal(personal.get('tipo_personal_id'))
        
        response_data = {
            "area_id": area_id,
            "area": "OPERACIONES",
            "personal_id": personal.get('id_personal'),
            "nombre": personal.get('nombre'),
            "tipo_personal": tipo_personal,
            "codigo_empresa": codigo_empresa,
            "token": f"token_operaciones_{personal.get('id_personal')}",
            "access_token": f"token_operaciones_{personal.get('id_personal')}",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        return jsonify({"success": True, "data": response_data, "message": "Login OPERACIONES exitoso"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@selector_bp.route('/login-almacen', methods=['POST'])
def login_almacen():
    """Endpoint específico para login del área de ALMACÉN.
    
    Body JSON esperado: {
        "area_id": "8426fd1a-2633-49d1-bc83-f6400bb58708",
        "nombre": "...",
        "codigo_empresa": "..."
    }
    
    Solo permite login si el personal está asociado al área ALMACÉN.
    """
    try:
        data = request.get_json() or {}
        area_id = data.get('area_id')
        nombre = data.get('nombre', '').strip()
        codigo_empresa = data.get('codigo_empresa', '').strip()

        # Validar que sea la credencial correcta para ALMACÉN
        if area_id != ALMACEN_ID:
            return jsonify({
                "success": False,
                "message": "Acceso denegado: credencial no válida para ALMACÉN"
            }), 403

        if not nombre or not codigo_empresa:
            return jsonify({
                "success": False,
                "message": "Nombre y código de empresa requeridos"
            }), 400

        # Validar contra la base de datos Y verificar que esté asociado a ALMACÉN
        personal = _validar_personal_por_area(nombre, ALMACEN_ID)
        if not personal:
            return jsonify({
                "success": False,
                "message": f"Usuario '{nombre}' no tiene acceso al área ALMACÉN o no existe en el sistema"
            }), 401

        # Obtener tipo de personal
        tipo_personal = _obtener_tipo_personal(personal.get('tipo_personal_id'))
        
        
        response_data = {
            "area_id": area_id,
            "area": "ALMACÉN",
            "personal_id": personal.get('id_personal'),
            "nombre": personal.get('nombre'),
            "tipo_personal": tipo_personal,
            "codigo_empresa": codigo_empresa,
            "token": f"token_almacen_{personal.get('id_personal')}",
            "access_token": f"token_almacen_{personal.get('id_personal')}",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        return jsonify({"success": True, "data": response_data, "message": "Login ALMACÉN exitoso"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
