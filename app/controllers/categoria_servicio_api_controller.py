from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase

categoria_servicio_api_bp = Blueprint('categoria_servicio_api', __name__)

@categoria_servicio_api_bp.route('/api/tipo_categoria', methods=['GET', 'POST'])
def tipo_categoria():
    if request.method == 'GET':
        try:
            resp = supabase.table('tipo_categoria').select('id_tipo_categoria, descripcion').execute()
            err = getattr(resp, 'error', None) if resp is not None else None
            data = getattr(resp, 'data', None) if resp is not None else None
            if err:
                return jsonify({'error': str(err)}), 500
            return jsonify(data or [])
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        try:
            data = request.get_json()
            if not data or not data.get('descripcion'):
                return jsonify({'error': 'Descripción requerida'}), 400
            payload = {'descripcion': data.get('descripcion')}
            resp = supabase.table('tipo_categoria').insert(payload).execute()
            err = getattr(resp, 'error', None) if resp is not None else None
            data_resp = getattr(resp, 'data', None) if resp is not None else None
            if err:
                return jsonify({'error': str(err)}), 500
            return jsonify({'mensaje': 'Tipo de categoría registrada', 'data': data_resp or resp}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@categoria_servicio_api_bp.route('/api/categoria_servicio', methods=['GET', 'POST'])
def categoria_servicio():
    if request.method == 'GET':
        try:
            # Obtener todas las categorías de servicio
            resp = supabase.table('categoria_servicio') \
                .select('*') \
                .execute()
            err = getattr(resp, 'error', None) if resp is not None else None
            data = getattr(resp, 'data', None) if resp is not None else None
            
            if err:
                return jsonify({'error': str(err)}), 500
            
            categorias = data or []
            
            # Obtener todos los tipos de servicio para el mapeo
            tipos_resp = supabase.table('tipo_servicio').select('id_tipo, descripcion').execute()
            tipos_data = getattr(tipos_resp, 'data', None) if tipos_resp is not None else None
            tipos_map = {t['id_tipo']: t['descripcion'] for t in (tipos_data or [])}
            
            # También obtener tipos de categoría para compatibilidad
            tipos_cat_resp = supabase.table('tipo_categoria').select('id_tipo_categoria, descripcion').execute()
            tipos_cat_data = getattr(tipos_cat_resp, 'data', None) if tipos_cat_resp is not None else None
            tipos_cat_map = {t['id_tipo_categoria']: t['descripcion'] for t in (tipos_cat_data or [])}
            
            # Enriquecer cada categoría con el nombre del tipo
            for c in categorias:
                if 'tipo_servicio_id' in c and c.get('tipo_servicio_id'):
                    c['tipo_nombre'] = tipos_map.get(c['tipo_servicio_id'], c['tipo_servicio_id'])
                elif 'tipo_categoria_id' in c and c.get('tipo_categoria_id'):
                    c['tipo_nombre'] = tipos_cat_map.get(c['tipo_categoria_id'], c['tipo_categoria_id'])
                else:
                    c['tipo_nombre'] = 'Sin tipo'
            
            return jsonify(categorias)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        try:
            data = request.get_json() or {}
            descripcion = (data.get('descripcion') or '').strip()
            tipo_servicio_id = data.get('tipo_servicio_id') or data.get('tipo_categoria_id')

            if not descripcion or not tipo_servicio_id:
                return jsonify({'error': 'Descripción y tipo_servicio_id requeridos'}), 400

            # Intentar esquema nuevo (tipo_servicio_id).
            try:
                payload = {
                    'descripcion': descripcion,
                    'tipo_servicio_id': tipo_servicio_id
                }
                resp = supabase.table('categoria_servicio').insert(payload).execute()
                err = getattr(resp, 'error', None) if resp is not None else None
                data_resp = getattr(resp, 'data', None) if resp is not None else None
                if err:
                    raise Exception(str(err))
                return jsonify({'mensaje': 'Categoría de servicio registrada', 'data': data_resp or resp}), 201
            except Exception:
                # Fallback para esquemas antiguos (tipo_categoria_id).
                payload = {
                    'descripcion': descripcion,
                    'tipo_categoria_id': tipo_servicio_id
                }
                resp = supabase.table('categoria_servicio').insert(payload).execute()
                err = getattr(resp, 'error', None) if resp is not None else None
                data_resp = getattr(resp, 'data', None) if resp is not None else None
                if err:
                    return jsonify({'error': str(err)}), 500
                return jsonify({'mensaje': 'Categoría de servicio registrada', 'data': data_resp or resp}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500
