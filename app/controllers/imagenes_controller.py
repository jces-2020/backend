# -*- coding: utf-8 -*-
"""
Controlador de imágenes de productos.
Gestiona: subida, procesamiento, edición, movimiento y listado de imágenes en Supabase Storage.
"""
from flask import Blueprint, request, jsonify
from app.services.supabase_client import supabase, IS_SERVICE
from app.services.imagen_procesamiento_service import ImagenProcesimientoService
from werkzeug.utils import secure_filename
import mimetypes
import tempfile
import os
import uuid
import logging

logger = logging.getLogger(__name__)

imagenes_bp = Blueprint('imagenes', __name__, url_prefix='/api/productos')


# ──────────────────────────── helpers ────────────────────────────

def _normalizar_categoria(cat):
    """Fuerza la categoría a solo las 3 carpetas válidas: vidrios, aluminios, accesorios."""
    c = (cat or '').lower().strip()
    if 'vidrio' in c:
        return 'vidrios'
    if 'aluminio' in c:
        return 'aluminios'
    if 'accesorio' in c:
        return 'accesorios'
    return 'accesorios'


def _get_public_url(url_obj):
    """Extrae URL pública del objeto retornado por Supabase."""
    if isinstance(url_obj, str):
        return url_obj
    if isinstance(url_obj, dict):
        return url_obj.get('publicUrl') or url_obj.get('publicURL') or url_obj.get('public_url')
    return getattr(url_obj, 'publicUrl', None) or getattr(url_obj, 'publicURL', None)


def _upload_with_retry(remote_path, file_bytes, content_type='image/png'):
    """Sube bytes a Supabase; si ya existe, elimina y reintenta."""
    try:
        return supabase.storage.from_('IMG').upload(
            path=remote_path,
            file=file_bytes,
            file_options={'content-type': content_type}
        )
    except Exception as e:
        msg = str(e)
        if 'already exists' in msg or '409' in msg or 'Duplicate' in msg:
            supabase.storage.from_('IMG').remove([remote_path])
            return supabase.storage.from_('IMG').upload(
                path=remote_path,
                file=file_bytes,
                file_options={'content-type': content_type}
            )
        raise


# ──────────────────────────── rutas ────────────────────────────

@imagenes_bp.route('/upload-image', methods=['POST'])
def upload_image():
    """Recibe multipart/form-data con 'file' y 'categoria' y sube al bucket IMG."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        categoria = _normalizar_categoria(request.form.get('categoria', ''))
        filename = secure_filename(file.filename)
        if not filename:
            return jsonify({'error': 'Invalid filename'}), 400

        content_type, _ = mimetypes.guess_type(filename)
        content_type = content_type or 'application/octet-stream'

        remote_path = f"PRODUCTOS/{categoria}/{filename}"
        file_bytes = file.read()

        up = _upload_with_retry(remote_path, file_bytes, content_type)
        if getattr(up, 'error', None):
            return jsonify({'error': str(up.error)}), 500

        url = _get_public_url(supabase.storage.from_('IMG').get_public_url(remote_path))
        return jsonify({'mensaje': 'Subida completa', 'url': url, 'path': remote_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@imagenes_bp.route('/procesar-imagen', methods=['POST'])
def procesar_imagen_completa():
    """
    Recibe imagen, la procesa (elimina fondo, recorta, normaliza)
    y guarda la versión procesada en Supabase.
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        categoria = _normalizar_categoria(request.form.get('categoria', ''))
        filename = secure_filename(file.filename)
        if not filename or not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
            return jsonify({'error': 'Archivo debe ser imagen JPG/PNG/GIF'}), 400

        imagen_bytes = file.read()
        if not imagen_bytes:
            return jsonify({'error': 'Archivo vacío'}), 400

        logger.info(f"Procesando imagen: {filename} ({len(imagen_bytes)} bytes)")

        imagen_service = ImagenProcesimientoService()
        resultado = imagen_service.procesar_imagen_optimizada_desde_bytes(
            imagen_bytes,
            tamaño_salida=768,
            confianza_minima=0.5,
            categoria=categoria
        )

        if not resultado.get('success'):
            return jsonify({'error': resultado.get('error')}), 500

        import base64
        imagen_procesada_bytes = base64.b64decode(resultado['data'].get('imagen_optimizada', ''))
        if not imagen_procesada_bytes:
            return jsonify({'error': 'No image data returned from processor'}), 500

        nombre_sin_ext = os.path.splitext(filename)[0]
        nombre_procesado = f"{nombre_sin_ext}_proc_{uuid.uuid4().hex[:8]}.png"
        remote_path = f"PRODUCTOS/{categoria}/{nombre_procesado}"

        up = supabase.storage.from_('IMG').upload(
            path=remote_path,
            file=imagen_procesada_bytes,
            file_options={'content-type': 'image/png'}
        )
        if getattr(up, 'error', None):
            return jsonify({'error': f'Error subiendo imagen: {str(up.error)}'}), 500

        url = _get_public_url(supabase.storage.from_('IMG').get_public_url(remote_path))
        if not url:
            return jsonify({'error': 'No se pudo obtener URL pública'}), 500

        logger.info(f"✓ Imagen procesada y guardada: {url}")

        metadata = {
            'classification': resultado['data'].get('clasificacion'),
            'processing_time': resultado['data'].get('tiempo_procesamiento'),
            'original_size': len(imagen_bytes),
            'processed_size': len(imagen_procesada_bytes),
            'segmentation_info': resultado['data'].get('segmentacion')
        }
        return jsonify({'success': True, 'url': url, 'metadata': metadata}), 200

    except Exception as e:
        logger.error(f"Error en procesar_imagen_completa: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@imagenes_bp.route('/guardar-imagen-editada', methods=['POST'])
def guardar_imagen_editada():
    """
    Recibe imagen PNG editada (recortada/ajustada en el frontend) y la sube a Supabase.
    Opcionalmente elimina la imagen anterior si se envía old_url.
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se proporcionó archivo'}), 400
        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'error': 'Archivo inválido'}), 400

        categoria = _normalizar_categoria(request.form.get('categoria', ''))
        nombre_base_raw = request.form.get('nombre_base', 'img') or 'img'
        nombre_base = secure_filename(nombre_base_raw).rsplit('.', 1)[0] or 'img'

        imagen_bytes = file.read()
        if not imagen_bytes:
            return jsonify({'error': 'Archivo vacío'}), 400

        nombre_editado = f"{nombre_base}_edit_{uuid.uuid4().hex[:8]}.png"
        remote_path = f"PRODUCTOS/{categoria}/{nombre_editado}"

        logger.info(f"Guardando imagen editada → {remote_path} ({len(imagen_bytes)} bytes)")

        up = _upload_with_retry(remote_path, imagen_bytes)
        if getattr(up, 'error', None):
            return jsonify({'error': f'Error subiendo imagen: {str(up.error)}'}), 500

        url = _get_public_url(supabase.storage.from_('IMG').get_public_url(remote_path))
        if not url:
            return jsonify({'error': 'No se pudo obtener URL pública'}), 500

        logger.info(f"✓ Imagen editada guardada: {url}")

        return jsonify({'success': True, 'url': url, 'path': remote_path}), 200

    except Exception as e:
        logger.error(f"Error en guardar_imagen_editada: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@imagenes_bp.route('/images', methods=['GET'])
def listar_imagenes():
    """Lista las imágenes del bucket IMG bajo PRODUCTOS/{categoria} y devuelve URLs públicas."""
    try:
        categoria = request.args.get('categoria', '') or ''
        path = f"PRODUCTOS/{categoria}" if categoria else 'PRODUCTOS'

        if not IS_SERVICE:
            return jsonify({'error': 'SUPABASE_SERVICE_ROLE_KEY no configurada. No se puede listar storage.'}), 403

        lista = supabase.storage.from_('IMG').list(path)
        if getattr(lista, 'error', None):
            return jsonify({'error': str(lista.error)}), 500

        files = lista if isinstance(lista, list) else getattr(lista, 'data', []) or []
        result = []
        for f in files:
            name = f.get('name') if isinstance(f, dict) else getattr(f, 'name', str(f))
            fullpath = f"{path}/{name}"
            url_obj = supabase.storage.from_('IMG').get_public_url(fullpath)
            result.append({'name': name, 'url': _get_public_url(url_obj), 'path': fullpath})

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@imagenes_bp.route('/move-image', methods=['POST'])
def move_image():
    """Mueve una imagen dentro del bucket IMG a PRODUCTOS/{categoria}/{filename}."""
    try:
        data = request.get_json() or {}
        src_path = data.get('path')
        categoria = _normalizar_categoria(data.get('categoria', ''))
        if not src_path:
            return jsonify({'error': 'No path provided'}), 400

        filename = src_path.split('/')[-1]
        dest_path = f"PRODUCTOS/{categoria}/{filename}"

        content = supabase.storage.from_('IMG').download(src_path)
        if isinstance(content, (bytes, bytearray)):
            file_bytes = content
        elif hasattr(content, 'read'):
            file_bytes = content.read()
        elif hasattr(content, 'content'):
            file_bytes = content.content
        else:
            return jsonify({'error': 'No se pudo leer el archivo origen'}), 500

        ext = os.path.splitext(filename)[1] or ''
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                tf.write(file_bytes)
                tmp_path = tf.name
            up = supabase.storage.from_('IMG').upload(dest_path, tmp_path)
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        if getattr(up, 'error', None):
            return jsonify({'error': str(up.error)}), 500

        try:
            supabase.storage.from_('IMG').remove([src_path])
        except Exception:
            pass

        url = _get_public_url(supabase.storage.from_('IMG').get_public_url(dest_path))
        return jsonify({'mensaje': 'Movido', 'url': url, 'path': dest_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@imagenes_bp.route('/fix-mime', methods=['POST'])
def fix_mime_for_productos():
    """Re-sube todos los objetos bajo PRODUCTOS para forzar el content-type correcto. Requiere clave de servicio."""
    if not IS_SERVICE:
        return jsonify({'error': 'SUPABASE_SERVICE_ROLE_KEY no configurada.'}), 403
    try:
        lista = supabase.storage.from_('IMG').list('PRODUCTOS')
        files = lista if isinstance(lista, list) else getattr(lista, 'data', []) or []
        results = []
        for f in files:
            name = f.get('name') if isinstance(f, dict) else getattr(f, 'name', str(f))
            full = f"PRODUCTOS/{name}"
            try:
                content = supabase.storage.from_('IMG').download(full)
                file_bytes = content if isinstance(content, (bytes, bytearray)) else getattr(content, 'content', None)
                if not file_bytes:
                    results.append({'file': full, 'ok': False, 'error': 'no content'})
                    continue
                ext = os.path.splitext(name)[1] or ''
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                        tf.write(file_bytes)
                        tmp_path = tf.name
                    up = supabase.storage.from_('IMG').upload(full, tmp_path)
                finally:
                    if tmp_path:
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                err = getattr(up, 'error', None)
                results.append({'file': full, 'ok': not err, 'error': str(err) if err else None})
            except Exception as e:
                results.append({'file': full, 'ok': False, 'error': str(e)})

        return jsonify({'summary': {'total': len(files), 'results': results}})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
