from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase
from werkzeug.utils import secure_filename
import mimetypes
from uuid import uuid4

servicio_api_bp = Blueprint('servicio_api', __name__)

@servicio_api_bp.route('/api/tipo_servicio', methods=['GET', 'POST'])
def listar_tipos_servicio():
    if request.method == 'GET':
        try:
            resp = supabase.table('tipo_servicio').select('id_tipo, descripcion').execute()
            err = getattr(resp, 'error', None) if resp is not None else None
            data = getattr(resp, 'data', None) if resp is not None else None
            if err:
                return jsonify({'error': str(err)}), 500
            return jsonify(data or [])
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:  # POST
        try:
            data = request.get_json()
            if not data or not data.get('descripcion'):
                return jsonify({'error': 'Descripción requerida'}), 400
            payload = {'descripcion': data.get('descripcion').strip()}
            resp = supabase.table('tipo_servicio').insert(payload).execute()
            err = getattr(resp, 'error', None) if resp is not None else None
            data_resp = getattr(resp, 'data', None) if resp is not None else None
            if err:
                return jsonify({'error': str(err)}), 500
            return jsonify({'mensaje': 'Tipo de servicio registrado', 'data': data_resp or resp}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@servicio_api_bp.route('/api/tipo_servicio/<tipo_id>', methods=['DELETE'])
def eliminar_tipo_servicio(tipo_id):
    try:
        resp = supabase.table('tipo_servicio').delete().eq('id_tipo', tipo_id).execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        if err:
            return jsonify({'error': str(err)}), 500
        return jsonify({'mensaje': 'Tipo de servicio eliminado correctamente'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@servicio_api_bp.route('/api/servicio', methods=['POST'])
def registrar_servicio():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        nombre = (data.get('nombre') or '').strip()
        descripcion = (data.get('descripcion') or '').strip()
        tipo_servicio_id = (data.get('tipo_servicio_id') or '').strip()
        if tipo_servicio_id == '':
            tipo_servicio_id = None
        imagen_ref = (data.get('ING') or '').strip() or None

        if not nombre:
            return jsonify({'error': 'El nombre del servicio es obligatorio'}), 400

        payload = {
            'nombre': nombre,
            'descripcion': descripcion,
            'tipo_servicio_id': tipo_servicio_id,
            'ING': imagen_ref,
        }
        # Validar que tipo_servicio_id exista en la tabla tipo_servicio
        tipo_id = payload.get('tipo_servicio_id')
        if tipo_id:
            tipo_resp = supabase.table('tipo_servicio').select('id_tipo').eq('id_tipo', tipo_id).execute()
            tipo_data = getattr(tipo_resp, 'data', None) if tipo_resp is not None else None
            if not tipo_data or (isinstance(tipo_data, list) and len(tipo_data) == 0):
                return jsonify({'error': 'Tipo de servicio no válido'}), 400
        resp = supabase.table('servicio').insert(payload).execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        data_resp = getattr(resp, 'data', None) if resp is not None else None
        if err:
            return jsonify({'error': str(err), 'payload': payload}), 500
        return jsonify({'mensaje': 'Servicio registrado', 'data': data_resp or resp}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@servicio_api_bp.route('/api/servicio/upload-image', methods=['POST'])
def upload_servicio_image():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        tipo = request.form.get('tipo', 'otro') or 'otro'
        filename = secure_filename(file.filename)
        if filename == '':
            return jsonify({'error': 'Invalid filename'}), 400
        if not file.mimetype or not file.mimetype.startswith('image/'):
            return jsonify({'error': 'Solo se permiten imagenes'}), 400

        file_bytes = file.read()
        max_bytes = 10 * 1024 * 1024
        if len(file_bytes) > max_bytes:
            return jsonify({'error': 'La imagen supera 10MB'}), 413

        content_type, _ = mimetypes.guess_type(filename)
        if content_type is None:
            content_type = file.mimetype or 'application/octet-stream'

        ext = ''
        if '.' in filename:
            ext = '.' + filename.rsplit('.', 1)[-1].lower()
        safe_tipo = secure_filename(str(tipo)) or 'otro'
        unique_name = f"{uuid4().hex}{ext}"
        remote_path = f"SERVICIOS/{safe_tipo}/{unique_name}"

        up = supabase.storage.from_('IMG').upload(
            path=remote_path,
            file=file_bytes,
            file_options={'content-type': content_type, 'upsert': 'true'}
        )
        err_up = getattr(up, 'error', None) if up is not None else None
        if err_up:
            return jsonify({'error': str(err_up)}), 500
        url_obj = supabase.storage.from_('IMG').get_public_url(remote_path)
        url = None
        if isinstance(url_obj, str):
            url = url_obj
        elif hasattr(url_obj, 'public_url'):
            url = url_obj.public_url
        elif isinstance(url_obj, dict):
            url = url_obj.get('publicUrl') or url_obj.get('publicURL') or url_obj.get('public_url')
        return jsonify({'mensaje': 'Subida completa', 'url': url, 'path': remote_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
