"""
Controlador para gestión de cortes en producción.
Endpoints para que el personal vea y actualice cortes de pedidos.
"""
from flask import Blueprint, request, jsonify
from app.services.cortes_produccion_service import (
    obtener_cortes_por_carrito,
    obtener_cortes_por_cliente,
    obtener_cortes_agrupados_por_producto,
    actualizar_estado_corte,
    actualizar_estados_cortes_carrito,
    eliminar_cortes,
    reducir_cantidad_corte
)

cortes_produccion_bp = Blueprint("cortes_produccion", __name__)


# ========================================
# OBTENER CORTES
# ========================================

@cortes_produccion_bp.route("/api/cortes/carrito/<carrito_id>", methods=["GET"])
def get_cortes_por_carrito(carrito_id):
    """
    GET /api/cortes/carrito/<carrito_id>
    Obtiene todos los cortes de un carrito específico.
    """
    try:
        resultado = obtener_cortes_por_carrito(carrito_id)
        
        if resultado.get("success"):
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "cortes": []
        }), 500


@cortes_produccion_bp.route("/api/cortes/carrito/<carrito_id>/agrupado", methods=["GET"])
def get_cortes_agrupados(carrito_id):
    """
    GET /api/cortes/carrito/<carrito_id>/agrupado
    Obtiene cortes agrupados por producto para facilitar producción.
    
    Response:
    {
        "success": true,
        "productos": [
            {
                "producto_id": "uuid",
                "producto_nombre": "Vidrio Templado 6mm",
                "producto_codigo": "VT-06",
                "categoria": "VIDRIO",
                "total_cortes": 5,
                "area_total_m2": 2.5,
                "cortes": [
                    {
                        "id_corte": "uuid",
                        "ancho_cm": 100,
                        "alto_cm": 150,
                        "cantidad": 2,
                        "estado": "pendiente",
                        "area_m2": 0.15
                    }
                ]
            }
        ]
    }
    """
    try:
        resultado = obtener_cortes_agrupados_por_producto(carrito_id)
        
        if resultado.get("success"):
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "productos": []
        }), 500


@cortes_produccion_bp.route("/api/cortes/cliente", methods=["GET"])
def get_cortes_por_nombre_cliente():
    """
    GET /api/cortes/cliente?nombre=Carlos%20Rojas
    Obtiene todos los cortes de un cliente buscando por nombre.
    
    Query params:
        nombre: Nombre del cliente (URL encoded)
    """
    try:
        nombre_cliente = request.args.get('nombre', '').strip()
        
        if not nombre_cliente:
            return jsonify({
                "success": False,
                "error": "Parámetro 'nombre' requerido",
                "cortes": []
            }), 400
        
        print(f"[CORTES] Buscando cortes por nombre de cliente: '{nombre_cliente}'")
        
        # Obtener todos los carritos
        from app.services.supabase_client import supabase
        
        # Buscar cliente por nombre (contains search)
        clientes_result = supabase.table("cliente") \
            .select("id_cliente") \
            .ilike("nombre", f"%{nombre_cliente}%") \
            .execute()
        
        cliente_ids = [c.get("id_cliente") for c in (clientes_result.data or [])]
        
        if not cliente_ids:
            print(f"[CORTES] Cliente no encontrado por tabla cliente, buscando por cortes.normbre: {nombre_cliente}")

            cortes_directos_result = supabase.table("cortes") \
                .select("id_corte, ancho_cm, alto_cm, cantidad, estado, fecha_registro, producto_id, carrito_id, normbre, productos(nombre, codigo, categoria_id, categoria(descripcion), almacen(fila, columna))") \
                .ilike("normbre", f"%{nombre_cliente}%") \
                .execute()

            cortes_directos = cortes_directos_result.data or []

            print(f"[CORTES] ✓ Se encontraron {len(cortes_directos)} cortes por normbre")

            return jsonify({
                "success": True,
                "cortes": cortes_directos,
                "total": len(cortes_directos)
            }), 200
        
        # Obtener carritos del cliente
        carritos_result = supabase.table("carrito_compras") \
            .select("id_carrito") \
            .in_("cliente_id", cliente_ids) \
            .execute()
        
        carrito_ids = [c.get("id_carrito") for c in (carritos_result.data or [])]
        
        if not carrito_ids:
            print(f"[CORTES] Cliente encontrado pero sin carritos")
            return jsonify({
                "success": True,
                "cortes": [],
                "message": "Cliente no tiene carritos"
            }), 200
        
        # Obtener cortes de esos carritos
        cortes_result = supabase.table("cortes") \
            .select("id_corte, ancho_cm, alto_cm, cantidad, estado, fecha_registro, producto_id, carrito_id, productos(nombre, codigo, categoria_id, categoria(descripcion), almacen(fila, columna))") \
            .in_("carrito_id", carrito_ids) \
            .execute()
        
        cortes = cortes_result.data or []
        
        print(f"[CORTES] ✓ Se encontraron {len(cortes)} cortes para cliente: {nombre_cliente}")
        
        return jsonify({
            "success": True,
            "cortes": cortes,
            "total": len(cortes)
        }), 200
        
    except Exception as e:
        print(f"[CORTES] ❌ Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "cortes": []
        }), 500


        solo_pendientes = request.args.get("solo_pendientes", "true").lower() == "true"
        
        resultado = obtener_cortes_por_cliente(cliente_id, solo_pendientes=solo_pendientes)
        
        if resultado.get("success"):
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "cortes": []
        }), 500


# ========================================
# ACTUALIZAR ESTADOS
# ========================================

@cortes_produccion_bp.route("/api/cortes/<corte_id>/estado", methods=["PUT"])
def actualizar_estado_corte_endpoint(corte_id):
    """
    PUT /api/cortes/<corte_id>/estado
    Body: {"estado": "en_proceso" | "completado" | "pendiente"}
    
    Actualiza el estado de un corte específico.
    """
    try:
        data = request.get_json() or {}
        nuevo_estado = data.get("estado")
        
        if not nuevo_estado:
            return jsonify({
                "success": False,
                "error": "Falta el campo 'estado'"
            }), 400
        
        resultado = actualizar_estado_corte(corte_id, nuevo_estado)
        
        if resultado.get("success"):
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@cortes_produccion_bp.route("/api/cortes/eliminar", methods=["POST"])
def eliminar_cortes_endpoint():
    """
    POST /api/cortes/eliminar
    Body: {"ids": ["uuid", ...]}
    """
    try:
        data = request.get_json() or {}
        ids = data.get("ids") or []

        resultado = eliminar_cortes(ids)
        if resultado.get("success"):
            return jsonify({"success": True, "eliminados": resultado.get("eliminados", 0)}), 200

        return jsonify({
            "success": False,
            "error": resultado.get("error", "Error al eliminar cortes")
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@cortes_produccion_bp.route("/api/cortes/<corte_id>/descontar", methods=["POST"])
def descontar_corte_endpoint(corte_id):
    """
    POST /api/cortes/<corte_id>/descontar
    Body: {"cantidad": 1}

    Descuenta cantidad del corte. Si queda en 0, elimina el registro.
    """
    try:
        data = request.get_json() or {}
        cantidad = int(data.get("cantidad", 1))

        if cantidad <= 0:
            return jsonify({
                "success": False,
                "error": "La cantidad debe ser mayor a 0"
            }), 400

        resultado = reducir_cantidad_corte(corte_id, cantidad)

        if resultado.get("success"):
            return jsonify(resultado), 200

        return jsonify(resultado), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@cortes_produccion_bp.route("/api/cortes/carrito/<carrito_id>/estado", methods=["PUT"])
def actualizar_estados_carrito_endpoint(carrito_id):
    """
    PUT /api/cortes/carrito/<carrito_id>/estado
    Body: {"estado": "completado"}
    
    Actualiza el estado de todos los cortes de un carrito.
    Útil para marcar todo como completado cuando se termina el trabajo.
    """
    try:
        data = request.get_json() or {}
        nuevo_estado = data.get("estado")
        
        if not nuevo_estado:
            return jsonify({
                "success": False,
                "error": "Falta el campo 'estado'"
            }), 400
        
        resultado = actualizar_estados_cortes_carrito(carrito_id, nuevo_estado)
        
        if resultado.get("success"):
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========================================
# OBTENER CORTES POR NOTIFICACIÓN
# ========================================

@cortes_produccion_bp.route("/api/cortes/notificacion/<notificacion_id>", methods=["GET"])
def get_cortes_por_notificacion(notificacion_id):
    """
    GET /api/cortes/notificacion/<notificacion_id>
    
    Obtiene los cortes asociados a una notificación de entrega.
    Lee el carrito_id desde el campo descripcion (JSON) de la notificación.
    """
    try:
        from app.services.supabase_client import supabase
        import json
        import re
        
        # 1. Obtener notificación
        notif_result = supabase.table("notificacion") \
            .select("descripcion, id_cliente") \
            .eq("id_notificacion", notificacion_id) \
            .limit(1) \
            .execute()
        
        if not notif_result.data:
            return jsonify({
                "success": False,
                "error": "Notificación no encontrada"
            }), 404
        
        notif = notif_result.data[0]
        descripcion = notif.get("descripcion", "{}")
        
        # 2. Obtener carrito_id desde JSON o texto libre
        carrito_id = None
        try:
            meta = json.loads(descripcion)
            if isinstance(meta, dict):
                carrito_id = meta.get("carrito_id")
        except Exception:
            carrito_id = None

        # Fallback: descripcion tipo "Pago ... (Carrito: <uuid>)"
        if not carrito_id and isinstance(descripcion, str):
            match = re.search(r"Carrito:\s*([0-9a-fA-F-]{36})", descripcion)
            if match:
                carrito_id = match.group(1)
        
        if not carrito_id:
            return jsonify({
                "success": True,
                "message": "El cliente no agregó cortes",
                "productos": [],
                "total_productos": 0,
                "cliente_id": notif.get("id_cliente"),
                "carrito_id": None
            }), 200
        
        # 3. Obtener cortes del carrito agrupados por producto
        resultado = obtener_cortes_agrupados_por_producto(carrito_id)
        
        if resultado.get("success"):
            # Agregar información de cliente
            resultado["cliente_id"] = notif.get("id_cliente")
            resultado["carrito_id"] = carrito_id
            if not resultado.get("productos"):
                resultado["message"] = "El cliente no agregó cortes"
            return jsonify(resultado), 200

        return jsonify({
            "success": True,
            "message": "El cliente no agregó cortes",
            "productos": [],
            "total_productos": 0,
            "cliente_id": notif.get("id_cliente"),
            "carrito_id": carrito_id
        }), 200
    
    except Exception as e:
        import traceback
        print(f"[ERROR] get_cortes_por_notificacion({notificacion_id}): {str(e)}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "productos": []
        }), 500
