"""
Controlador para confirmar productos entregados
"""
from flask import Blueprint, request, jsonify
from app.services.entrega_productos_confirmar_service import confirmar_productos_entregados

entrega_productos_confirmar_bp = Blueprint('entrega_productos_confirmar', __name__, url_prefix='/api/entrega')


@entrega_productos_confirmar_bp.route('/productos/confirmar', methods=['POST'])
def confirmar_productos():
    """
    POST /api/entrega/productos/confirmar
    Body: {
      "carrito_id": "uuid",
      "items": [{"producto_id": "uuid", "cantidad": 1}, ...]
    }
    """
    try:
        data = request.get_json()
        carrito_id = data.get('carrito_id')
        items = data.get('items', [])
        
        if not carrito_id or not items:
            return jsonify({
                "success": False,
                "message": "Carrito e items requeridos"
            }), 400
        
        # Obtener notificación para tener el ID
        from app.services.supabase_client import supabase
        notif_result = supabase.table("notificacion") \
            .select("id_notificacion") \
            .eq("descripcion", f'{{"carrito_id": "{carrito_id}"}}') \
            .limit(1) \
            .execute()
        
        notificacion_id = notif_result.data[0].get("id_notificacion") if notif_result.data else None
        
        result = confirmar_productos_entregados(carrito_id, items)
        
        if result.get("success"):
            result["notificacion_id"] = notificacion_id
        
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
        
    except Exception as e:
        print(f"Error en confirmar_productos: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
