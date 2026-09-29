# -*- coding: utf-8 -*-
"""
Controlador CRUD de productos.
Gestiona: listado, creación, actualización, eliminación y búsquedas.
"""
from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase
from app.services.reportes_productos_service import (
    registrar_creacion_producto,
    registrar_edicion_producto,
    registrar_eliminacion_producto,
)
import logging

logger = logging.getLogger(__name__)

productos_bp = Blueprint('productos', __name__, url_prefix='/api/productos')

# Estados de carrito_compras que significan "todavía no se concreta la venta":
# mientras un producto esté en un carrito con uno de estos estados, no se
# puede eliminar. Listo/Pagado (o sin carrito) se consideran venta concluida.
CARRITO_ESTADOS_ACTIVOS = {'pendiente', 'proceso'}


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


def _estado_ventas_producto(id_producto):
    """Devuelve (tiene_venta_activa, tiene_venta_concluida) para las ventas de un producto.

    "Activa" = el carrito de esa venta sigue en Pendiente/Proceso (aún no se
    concreta). El resto (Listo, Pagado, o venta sin carrito) se considera
    concluida: se puede eliminar el producto perdiendo la trazabilidad.
    """
    ventas = supabase.table('venta').select('id_venta, carrito_id').eq('producto_id', id_producto).execute()
    filas = ventas.data or []
    if not filas:
        return False, False

    carrito_ids = list({v['carrito_id'] for v in filas if v.get('carrito_id')})
    carritos_activos = set()
    if carrito_ids:
        carritos = supabase.table('carrito_compras').select('id_carrito, estado').in_('id_carrito', carrito_ids).execute()
        for c in (carritos.data or []):
            if str(c.get('estado') or '').strip().lower() in CARRITO_ESTADOS_ACTIVOS:
                carritos_activos.add(c['id_carrito'])

    tiene_activa = any(v.get('carrito_id') in carritos_activos for v in filas)
    tiene_concluida = any(v.get('carrito_id') not in carritos_activos for v in filas)
    return tiene_activa, tiene_concluida


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
            'id_producto, codigo, nombre, cantidad, precio_unitario, precio_tienda, descripcion, '
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

        codigo = data.get('codigo')

        payload = {
            'codigo':          codigo,
            'nombre':          data.get('nombre'),
            'cantidad':        data.get('cantidad'),
            'precio_unitario': data.get('precio_unitario'),
            'precio_tienda':   data.get('precio_tienda') or None,
            'descripcion':     data.get('descripcion'),
            'grosor':          data.get('grosor'),
            'categoria_id':    data.get('categoria_id'),
            'almacen_id':      almacen_id,
            'stock_id':        data.get('stock_id'),
            'IMG_P':           data.get('IMG_P') or data.get('imagen_url'),
        }

        if codigo:
            dup = supabase.table('productos').select('id_producto').eq('codigo', codigo).limit(1).execute()
            if dup.data:
                return jsonify({'error': f"Ya existe un producto con el código '{codigo}'"}), 409

        try:
            resp = supabase.table('productos').insert(payload).execute()
        except Exception as insert_err:
            if 'productos_codigo_key' in str(insert_err) or 'duplicate key' in str(insert_err).lower():
                return jsonify({'error': f"Ya existe un producto con el código '{codigo}'"}), 409
            raise

        if getattr(resp, 'error', None):
            return jsonify({'error': str(resp.error)}), 500

        producto_creado = resp.data[0] if isinstance(resp.data, list) and resp.data else resp.data
        if isinstance(producto_creado, dict) and producto_creado.get('id_producto'):
            registrar_creacion_producto(producto_creado['id_producto'], producto_creado)

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

        fields = ['codigo', 'nombre', 'cantidad', 'precio_unitario', 'precio_tienda', 'descripcion',
                  'grosor', 'categoria_id', 'stock_id', 'IMG_P']
        payload = {f: body.get(f, curr.get(f)) for f in fields}
        payload['almacen_id'] = almacen_id

        old_img = curr.get('IMG_P')
        new_img = payload.get('IMG_P')

        resp = supabase.table('productos').update(payload).eq('id_producto', id_producto).execute()
        if getattr(resp, 'error', None):
            return jsonify({'error': str(resp.error)}), 500

        # Eliminar imagen anterior solo tras confirmar que el update se guardó:
        # borrarla antes dejaba IMG_P apuntando a un archivo ya inexistente si
        # el update fallaba (imagen rota en web y móvil).
        if old_img and new_img and old_img != new_img:
            _delete_storage_image(old_img)

        producto_actualizado = resp.data[0] if isinstance(resp.data, list) and resp.data else resp.data
        if isinstance(producto_actualizado, dict):
            registrar_edicion_producto(id_producto, curr, producto_actualizado)

        return jsonify({'success': True, 'data': resp.data}), 200
    except Exception as e:
        logger.error(f"Error en actualizar_producto: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@productos_bp.route('/<id_producto>', methods=['DELETE'])
def eliminar_producto(id_producto):
    try:
        curr_resp = supabase.table('productos').select('*').eq('id_producto', id_producto).single().execute()
        curr = curr_resp.data
        if not curr:
            return jsonify({'error': 'Producto no encontrado'}), 404

        tiene_activa, tiene_concluida = _estado_ventas_producto(id_producto)
        if tiene_activa:
            return jsonify({
                'error': 'No se puede eliminar: el producto tiene una venta en proceso (carrito activo).'
            }), 409

        forzar = str(request.args.get('forzar', '')).strip().lower() in ('1', 'true')
        if tiene_concluida and not forzar:
            return jsonify({
                'error': 'Este producto tiene ventas registradas. Si lo eliminas, ya no se podrá '
                         'identificar en el historial de esas ventas. ¿Deseas continuar?',
                'requiere_confirmacion': True
            }), 409

        if curr.get('IMG_P'):
            _delete_storage_image(curr['IMG_P'])
        registrar_eliminacion_producto(id_producto, curr)

        # detalle_producto referencia a productos por llave foránea: hay que
        # borrar esa fila primero o Postgres rechaza el DELETE de productos.
        supabase.table('detalle_producto').delete().eq('producto_id', id_producto).execute()

        try:
            resp = supabase.table('productos').delete().eq('id_producto', id_producto).execute()
        except Exception as delete_err:
            msg = str(delete_err)
            if 'foreign key constraint' not in msg.lower() and 'violates foreign key' not in msg.lower():
                raise
            return jsonify({
                'error': 'No se puede eliminar: la base de datos aún bloquea productos con ventas '
                         '(falta aplicar el ajuste de la FK/trigger de venta.producto_id en Supabase).'
            }), 409

        if getattr(resp, 'error', None):
            return jsonify({'error': str(resp.error)}), 500
        return jsonify({'success': True, 'message': 'Producto eliminado'}), 200
    except Exception as e:
        logger.error(f"Error en eliminar_producto: {e}", exc_info=True)
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
        resp = supabase.table('productos').select('*, detalle_producto(*)').ilike('nombre', f'%{nombre_producto}%').execute()
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
