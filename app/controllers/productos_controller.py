# -*- coding: utf-8 -*-
"""
Controlador CRUD de productos.
Gestiona: listado, creación, actualización, eliminación y búsquedas.
"""
from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase
import logging

logger = logging.getLogger(__name__)

productos_bp = Blueprint('productos', __name__, url_prefix='/api/productos')


# ──────────────────────────── helpers ────────────────────────────

def _extract_storage_path(url):
    """Extrae el path dentro del bucket IMG desde URL pública de Supabase."""
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return None
    marker = '/object/public/IMG/'
    idx = url.find(marker)
    if idx == -1:
        return None
    return url[idx + len(marker):].split('?')[0] or None


def _delete_storage_image(url):
    """Elimina una imagen del bucket IMG dado su URL pública. Silencia errores."""
    path = _extract_storage_path(url)
    if not path:
        return
    try:
        supabase.storage.from_('IMG').remove([path])
        logger.info(f"🗑️ Imagen eliminada de storage: {path}")
    except Exception as e:
        logger.warning(f"No se pudo eliminar imagen {path}: {e}")


def _map_producto(p):
    """Mapea el join de categoría y almacén al producto."""
    cat_obj = p.get('categoria')
    if isinstance(cat_obj, dict):
        p['categoria'] = cat_obj.get('descripcion')
    elif isinstance(cat_obj, list) and cat_obj:
        p['categoria'] = cat_obj[0].get('descripcion')
    else:
        p['categoria'] = None

    alm_obj = p.get('almacen')
    if isinstance(alm_obj, dict):
        p['almacen'] = alm_obj
    elif isinstance(alm_obj, list) and alm_obj:
        p['almacen'] = alm_obj[0]
    else:
        p['almacen'] = None
    return p


# ──────────────────────────── rutas ────────────────────────────

@productos_bp.route('', methods=['GET'])
def listar_productos():
    try:
        patron = request.args.get('buscar', '').strip()
        query = supabase.table('productos').select(
            'id_producto, codigo, nombre, cantidad, precio_unitario, descripcion, '
            'grosor, categoria_id, almacen_id, stock_id, IMG_P, '
            'categoria:categoria_id (descripcion), '
            'almacen:almacen_id (fila, columna)'
        )
        if patron:
            query = query.ilike('nombre', f'%{patron}%')
        resp = query.execute()
        return jsonify([_map_producto(p) for p in (resp.data or [])]), 200
    except Exception as e:
        logger.error(f"Error en listar_productos: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@productos_bp.route('', methods=['POST'])
def crear_producto():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        almacen_id = None
        if data.get('fila') or data.get('columna'):
            alm_resp = supabase.table('almacen').insert({
                'fila': data.get('fila'),
                'columna': data.get('columna'),
            }).execute()
            alm_data = getattr(alm_resp, 'data', None)
            if isinstance(alm_data, list) and alm_data:
                almacen_id = alm_data[0].get('id_almacen')
            elif isinstance(alm_data, dict):
                almacen_id = alm_data.get('id_almacen')

        payload = {
            'codigo':          data.get('codigo'),
            'nombre':          data.get('nombre'),
            'cantidad':        data.get('cantidad'),
            'precio_unitario': data.get('precio_unitario'),
            'descripcion':     data.get('descripcion'),
            'grosor':          data.get('grosor'),
            'categoria_id':    data.get('categoria_id'),
            'almacen_id':      almacen_id,
            'stock_id':        data.get('stock_id'),
            'IMG_P':           data.get('IMG_P') or data.get('imagen_url'),
        }

        resp = supabase.table('productos').insert(payload).execute()
        if getattr(resp, 'error', None):
            return jsonify({'error': str(resp.error)}), 500
        return jsonify({'success': True, 'data': resp.data}), 201
    except Exception as e:
        logger.error(f"Error en crear_producto: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@productos_bp.route('/<id_producto>', methods=['GET'])
def obtener_producto(id_producto):
    try:
        resp = supabase.table('productos').select('*').eq('id_producto', id_producto).single().execute()
        if not resp.data:
            return jsonify({'error': 'Producto no encontrado'}), 404
        return jsonify(resp.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@productos_bp.route('/<id_producto>', methods=['PUT'])
def actualizar_producto(id_producto):
    try:
        body = request.get_json() or {}
        curr_resp = supabase.table('productos').select('*').eq('id_producto', id_producto).single().execute()
        if not curr_resp.data:
            return jsonify({'error': 'Producto no encontrado'}), 404
        curr = curr_resp.data

        almacen_id = curr.get('almacen_id')
        if body.get('fila') or body.get('columna'):
            alm_payload = {'fila': body.get('fila'), 'columna': body.get('columna')}
            if almacen_id:
                supabase.table('almacen').update(alm_payload).eq('id_almacen', almacen_id).execute()
            else:
                alm_resp = supabase.table('almacen').insert(alm_payload).execute()
                alm_data = getattr(alm_resp, 'data', None)
                if isinstance(alm_data, list) and alm_data:
                    almacen_id = alm_data[0].get('id_almacen')

        fields = ['codigo', 'nombre', 'cantidad', 'precio_unitario', 'descripcion',
                  'grosor', 'categoria_id', 'stock_id', 'IMG_P']
        payload = {f: body.get(f, curr.get(f)) for f in fields}
        payload['almacen_id'] = almacen_id

        # Eliminar imagen anterior si cambia
        old_img = curr.get('IMG_P')
        new_img = payload.get('IMG_P')
        if old_img and new_img and old_img != new_img:
            _delete_storage_image(old_img)

        resp = supabase.table('productos').update(payload).eq('id_producto', id_producto).execute()
        if getattr(resp, 'error', None):
            return jsonify({'error': str(resp.error)}), 500
        return jsonify({'success': True, 'data': resp.data}), 200
    except Exception as e:
        logger.error(f"Error en actualizar_producto: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@productos_bp.route('/<id_producto>', methods=['DELETE'])
def eliminar_producto(id_producto):
    try:
        curr_resp = supabase.table('productos').select('IMG_P').eq('id_producto', id_producto).single().execute()
        if curr_resp.data and curr_resp.data.get('IMG_P'):
            _delete_storage_image(curr_resp.data['IMG_P'])

        resp = supabase.table('productos').delete().eq('id_producto', id_producto).execute()
        if getattr(resp, 'error', None):
            return jsonify({'error': str(resp.error)}), 500
        return jsonify({'success': True, 'message': 'Producto eliminado'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@productos_bp.route('/detalles', methods=['POST'])
def detalles_productos():
    """Devuelve datos básicos de una lista de IDs (usado por el carrito)."""
    ids = (request.json or {}).get('ids', [])
    if not ids:
        return jsonify([])
    resp = supabase.table('productos').select(
        'id_producto, nombre, grosor, codigo, descripcion, precio_unitario'
    ).in_('id_producto', ids).execute()
    return jsonify(resp.data or [])


@productos_bp.route('/codigo/<codigo>', methods=['GET'])
def buscar_por_codigo(codigo):
    try:
        resp = supabase.table('productos').select('*').eq('codigo', codigo).limit(1).execute()
        if not resp.data:
            return jsonify({'error': 'Producto no encontrado'}), 404
        return jsonify(resp.data[0]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@productos_bp.route('/por-nombre/<nombre_producto>', methods=['GET'])
def obtener_producto_por_nombre(nombre_producto):
    try:
        resp = supabase.table('productos').select('*').ilike('nombre', f'%{nombre_producto}%').execute()
        if not resp.data:
            return jsonify({'success': False, 'message': 'Producto no encontrado'}), 404
        return jsonify({'success': True, 'producto': resp.data[0]}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@productos_bp.route('/stock/disponibles', methods=['GET'])
def obtener_con_stock():
    """Devuelve productos con stock > 0 en formato simplificado para el carrito."""
    try:
        resp = supabase.table('productos').select(
            'id_producto, codigo, nombre, precio_unitario, cantidad, IMG_P'
        ).gt('cantidad', 0).execute()
        return jsonify(resp.data or []), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@productos_bp.route('/stats', methods=['GET'])
def obtener_estadisticas():
    try:
        resp = supabase.table('productos').select('cantidad, precio_unitario').execute()
        data = resp.data or []
        total = len(data)
        con_stock = sum(1 for p in data if (p.get('cantidad') or 0) > 0)
        return jsonify({
            'total': total,
            'con_stock': con_stock,
            'sin_stock': total - con_stock,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
