from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase

productos_carrito_api = Blueprint('productos_carrito_api', __name__)

@productos_carrito_api.route('/api/productos_carrito', methods=['POST'])
def agregar_producto_carrito():
    """
    DEPRECADO: Este endpoint no debe ser usado.
    Los productos se guardan SOLO en RAM (frontend) hasta que el cliente realiza el pago.
    Después del pago, los productos se guardan automáticamente en la BD.
    """
    return jsonify({
        'success': False, 
        'message': 'Este endpoint está deprecado. Los productos se guardan en RAM hasta confirmar el pago.'
    }), 410  # 410 Gone

@productos_carrito_api.route('/api/productos_carrito', methods=['PATCH'])
def actualizar_cantidad_carrito():
    """
    DEPRECADO: Los productos se actualizan SOLO en RAM hasta que se paga.
    """
    return jsonify({
        'success': False, 
        'message': 'Este endpoint está deprecado. Los productos se actualizan en RAM hasta confirmar el pago.'
    }), 410

@productos_carrito_api.route('/api/productos_carrito', methods=['DELETE'])
def eliminar_item_carrito():
    """
    DEPRECADO: Los productos se eliminan SOLO en RAM hasta que se paga.
    """
    return jsonify({
        'success': False, 
        'message': 'Este endpoint está deprecado. Los productos se eliminan en RAM hasta confirmar el pago.'
    }), 410

@productos_carrito_api.route('/api/productos_carrito/<carrito_id>', methods=['GET'])
def obtener_productos_carrito(carrito_id):
    try:
        result = supabase.table('productos_carrito').select('*').eq('carrito_id', carrito_id).execute()
        return jsonify({'success': True, 'data': result.data}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@productos_carrito_api.route('/api/carrito_items/<carrito_id>', methods=['GET'])
def obtener_items_con_detalles(carrito_id):
    """Devuelve los items del carrito con detalles del producto y subtotal.
    SELECT pc.producto_id, pc.cantidad, p.nombre, p.descripcion, p.grosor, p.codigo, p.precio_unitario
    FROM productos_carrito pc JOIN productos p ON p.id_producto = pc.producto_id
    WHERE pc.carrito_id = :carrito_id
    """
    try:
        # Obtener items base
        items = supabase.table('productos_carrito').select('*').eq('carrito_id', carrito_id).execute().data or []
        if not items:
            return jsonify({'success': True, 'data': []}), 200
        # Obtener ids únicos
        ids = [it['producto_id'] for it in items]
        # Traer detalles de productos
        productos = supabase.table('productos').select('*').in_('id_producto', ids).execute().data or []
        prod_map = {p['id_producto']: p for p in productos}
        joined = []
        for it in items:
            p = prod_map.get(it['producto_id'])
            if not p:
                continue
            precio = float(p.get('precio_unitario') or 0)
            cant = float(it.get('cantidad') or 0)
            joined.append({
                'id_producto': p['id_producto'],
                'nombre': p.get('nombre'),
                'grosor': p.get('grosor'),
                'codigo': p.get('codigo'),
                'descripcion': p.get('descripcion'),
                'precio_unitario': precio,
                'cantidad': cant,
                'subtotal': round(precio * cant, 2)
            })
        return jsonify({'success': True, 'data': joined}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
