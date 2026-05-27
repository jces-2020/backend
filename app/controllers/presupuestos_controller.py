from flask import Blueprint, request, jsonify
from services import presupuestos_service
from services.supabase_client import supabase
import json

presupuestos_bp = Blueprint('presupuestos', __name__)


@presupuestos_bp.route('/api/presupuestos/notificacion/<notificacion_id>/servicios', methods=['GET'])
def obtener_servicios_de_notificacion(notificacion_id: str):
    """
    Dado el ID de una notificación de tipo 'servicio', retorna los presupuestos
    asociados con sus datos de servicio (imagen, nombre, medidas, total).

    • Formato esperado: descripcion = JSON con {presupuesto_ids: [...]}.
    Nota: Se retorna SOLO lo asociado a esta notificación.
    """
    try:
        notif_result = supabase.table('notificacion').select('*').eq('id_notificacion', notificacion_id).limit(1).execute()
        if not notif_result.data:
            return jsonify({"success": False, "message": "Notificación no encontrada"}), 404

        notif        = notif_result.data[0]
        descripcion  = notif.get('descripcion') or ''
        cliente_id   = notif.get('id_cliente')

        # --- Intentar parsear como JSON nuevo ---
        try:
            meta = json.loads(descripcion)
            presupuesto_ids = meta.get('presupuesto_ids') or []
        except (json.JSONDecodeError, TypeError):
            presupuesto_ids = []

        if presupuesto_ids:
            # Cargar cada presupuesto con join a servicio
            items = []
            for pid in presupuesto_ids:
                pres_r = supabase.table('presupuesto').select(
                    'id_presupuesto, descripcion, total, ancho, alto, servicio_id, '
                    'servicio(id_servicio, nombre, descripcion, ING)'
                ).eq('id_presupuesto', pid).limit(1).execute()
                if pres_r.data:
                    p = pres_r.data[0]
                    srv = p.get('servicio') or {}

                    # Resolver URL de imagen del servicio
                    ing = srv.get('ING') or ''
                    if ing.startswith('http'):
                        img_url = ing
                    elif ing:
                        try:
                            img_url = supabase.storage.from_('imagenes').get_public_url(ing)
                        except Exception:
                            img_url = ''
                    else:
                        img_url = ''

                    items.append({
                        'id_presupuesto':    p.get('id_presupuesto'),
                        'servicio_id':       p.get('servicio_id'),
                        'nombre_servicio':   srv.get('nombre', ''),
                        'descripcion':       p.get('descripcion', ''),
                        'ancho':             p.get('ancho'),
                        'alto':              p.get('alto'),
                        'total':             p.get('total'),
                        'imagen_url':        img_url,
                    })

            meta_out = {
                'total_general':      meta.get('total_general'),
                'cantidad_servicios': meta.get('cantidad_servicios', len(items)),
            }
            return jsonify({
                "success":  True,
                "data":     items,
                "meta":     meta_out,
                "cliente_id": cliente_id,
            }), 200

        return jsonify({
            "success":    True,
            "data":       [],
            "meta":       {
                "descripcion_raw": descripcion,
                "message": "La notificación no contiene presupuesto_ids válidos"
            },
            "cliente_id": cliente_id,
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

@presupuestos_bp.route('/api/presupuestos', methods=['POST'])
def crear_presupuesto():
    """
    Endpoint para guardar un nuevo presupuesto
    """
    try:
        data = request.get_json()
        
        # Validar datos requeridos básicos
        if not data.get('servicio_id'):
            return jsonify({"success": False, "message": "El campo 'servicio_id' es requerido"}), 400
        # cliente_id/documento son opcionales; se pueden omitir para presupuestos anónimos
        if not data.get('cliente_id') and data.get('cliente_documento'):
            # si se envía documento intentamos buscar el id, pero no es obligatorio
            cli_resp = presupuestos_service.obtiene_cliente_por_documento(data['cliente_documento'])
            if cli_resp:
                data['cliente_id'] = cli_resp

        resultado = presupuestos_service.guardar_presupuesto(data)
        
        if resultado.get('success'):
            return jsonify(resultado), 201
        else:
            return jsonify(resultado), 400
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al crear presupuesto: {str(e)}"
        }), 500


@presupuestos_bp.route('/api/presupuestos', methods=['GET'])
def listar_presupuestos():
    """
    Endpoint para obtener la lista de presupuestos
    Soporta filtro por query param ?filtro=documento_o_razon_social
    """
    try:
        filtro = request.args.get('filtro', None)
        servicio_id = request.args.get('servicio_id', None)
        presupuestos = presupuestos_service.obtener_presupuestos(filtro, servicio_id)
        
        return jsonify({
            "success": True,
            "data": presupuestos
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al obtener presupuestos: {str(e)}"
        }), 500


@presupuestos_bp.route('/api/presupuestos/<presupuesto_id>', methods=['GET'])
def obtener_presupuesto(presupuesto_id):
    """
    Endpoint para obtener un presupuesto específico por ID
    """
    try:
        presupuesto = presupuestos_service.obtener_presupuesto_por_id(presupuesto_id)
        
        if presupuesto:
            return jsonify({
                "success": True,
                "data": presupuesto
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Presupuesto no encontrado"
            }), 404
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al obtener presupuesto: {str(e)}"
        }), 500
