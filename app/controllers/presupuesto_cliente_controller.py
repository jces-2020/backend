"""
Controlador para guardar presupuestos de servicio con búsqueda de cliente
y generación automática de notificaciones.
"""

from flask import Blueprint, request, jsonify
from services.presupuesto_cliente_service import (
    buscar_cliente_por_documento,
    guardar_multiples_presupuestos,
)

presupuesto_cliente_bp = Blueprint('presupuesto_cliente', __name__)


@presupuesto_cliente_bp.route('/api/presupuesto_guardar', methods=['POST'])
def guardar_presupuestos_con_cliente():
    """
    Guarda múltiples presupuestos de servicio con búsqueda/creación de cliente.

    JSON esperado:
    {
        "documento":   "12345678",
        "nombre_apis": "JUAN PEREZ",       # nombre obtenido de APIs Peru
        "presupuestos": [
            {
                "servicio_id": "uuid",
                "descripcion": "Ventana Corrediza",
                "ancho": 120,
                "alto": 90,
                "total": 350.00
            }
        ]
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "message": "No se envió datos"}), 400

        documento       = (data.get("documento") or "").strip()
        nombre_apis     = (data.get("nombre_apis") or "Cliente").strip()
        presupuestos_list = data.get("presupuestos", [])

        if not documento:
            return jsonify({"success": False, "message": "El documento es requerido"}), 400

        if not presupuestos_list:
            return jsonify({"success": False, "message": "Se requiere al menos un presupuesto"}), 400

        # El servicio busca/crea el cliente internamente
        success, msg, pres_ids, cliente, cliente_creado, jwt_temporal = guardar_multiples_presupuestos(
            presupuestos_list,
            documento,
            nombre_apis,
        )

        if success:
            respuesta = {
                "success":          True,
                "message":          msg,
                "presupuesto_ids":  pres_ids,
                "cliente_creado":   cliente_creado,
                "cliente_encontrado": not cliente_creado,
            }
            # Si se creó cuenta temporal, devolver credenciales para el QR
            if cliente_creado and cliente:
                nombre_base = (nombre_apis).lower().replace(' ', '').replace('-', '')
                respuesta["credenciales"] = {
                    "correo":     f"{nombre_base}@vidriobras.com",
                    "contrasena": documento,
                    "nombre":     cliente.get("nombre", nombre_apis.upper()),
                    "jwt_temporal": jwt_temporal,
                }
            return jsonify(respuesta), 200

        return jsonify({"success": False, "message": msg}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Error del servidor: {str(e)}"}), 500


@presupuesto_cliente_bp.route('/api/cliente/buscar_documento', methods=['POST'])
def buscar_cliente():
    """
    Endpoint para buscar cliente por documento (para usar durante la búsqueda en Datos del cliente).
    
    JSON esperado:
    {
        "documento": "20123456789"
    }
    
    Respuesta:
    {
        "success": true,
        "encontrado": true,
        "cliente": { ... datos del cliente ... } o null
    }
    """
    try:
        data = request.get_json()
        documento = data.get("documento", "").strip()
        
        if not documento:
            return jsonify({
                "success": True,
                "encontrado": False,
                "cliente": None
            }), 200
        
        cliente = buscar_cliente_por_documento(documento)
        
        return jsonify({
            "success": True,
            "encontrado": cliente is not None,
            "cliente": cliente
        }), 200
        
    except Exception as e:
        print(f"Error en buscar_cliente: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500
