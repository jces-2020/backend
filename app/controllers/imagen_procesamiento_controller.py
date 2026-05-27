# -*- coding: utf-8 -*-
"""
Controller - Endpoints de Procesamiento de Imágenes

Patrón: Factory Pattern - auto-registro de blueprints
Responsabilidades:
- Recibir imágenes del cliente
- Validar
- Llamar servicio de procesamiento
- Devolver imagen procesada
- Guardar en Supabase Storage (luego)
"""
from flask import Blueprint, request, jsonify
from app.services.imagen_procesamiento_service import ImagenProcesimientoService
from app.core.exceptions import AppException
import logging

logger = logging.getLogger(__name__)

# Crear blueprint (convención: nombre_bp)
imagen_procesamiento_bp = Blueprint(
    'imagen_procesamiento',
    __name__,
    url_prefix='/api/imagenes'
)

# Instanciar servicio
_servicio = ImagenProcesimientoService()


# ==================== HELPERS ====================

def _error_response(mensaje: str, status_code: int = 400):
    """Respuesta de error estándar"""
    return jsonify({
        'success': False,
        'message': mensaje
    }), status_code


def _success_response(data: dict = None, mensaje: str = None, status_code: int = 200):
    """Respuesta de éxito estándar"""
    return jsonify({
        'success': True,
        'message': mensaje,
        'data': data
    }), status_code


# ==================== ENDPOINTS ====================

@imagen_procesamiento_bp.route('/procesar-imagen', methods=['POST'])
def procesar_imagen():
    """
    Procesa una imagen: elimina fondo, segmenta y clasifica.

    **Request**:
    - file: Imagen (multipart/form-data)
    - incluir_segmentacion: bool (opcional, default=true)
    - incluir_clasificacion: bool (opcional, default=true)
    - confianza_minima: float (opcional, default=0.5)

    **Response**:
    ```json
    {
      "success": true,
      "message": "Imagen procesada correctamente",
      "data": {
        "imagen_sin_fondo": "base64...",
        "segmentacion": {...},
        "clasificacion": {...},
        "tiempo_procesamiento": 2.5
      }
    }
    ```
    """
    try:
        # Validar que hay archivo
        if 'file' not in request.files:
            return _error_response('No se proporcionó archivo', 400)

        archivo = request.files['file']
        if archivo.filename == '':
            return _error_response('Nombre de archivo vacío', 400)

        # Validar tipo de archivo
        tipo_permitido = archivo.content_type.startswith('image/')
        if not tipo_permitido:
            return _error_response(f'Tipo de archivo no permitido: {archivo.content_type}', 400)

        # Leer bytes
        imagen_bytes = archivo.read()
        if not imagen_bytes:
            return _error_response('Archivo vacío', 400)

        logger.info(f"Procesando imagen: {archivo.filename} ({len(imagen_bytes)} bytes)")

        # Parámetros opcionales
        incluir_segmentacion = request.args.get('incluir_segmentacion', 'true').lower() == 'true'
        incluir_clasificacion = request.args.get('incluir_clasificacion', 'true').lower() == 'true'
        confianza_minima = float(request.args.get('confianza_minima', 0.5))

        # Llamar al servicio
        resultado = _servicio.procesar_imagen_desde_bytes(
            imagen_bytes,
            incluir_segmentacion=incluir_segmentacion,
            incluir_clasificacion=incluir_clasificacion,
            confianza_minima=confianza_minima
        )

        # Procesar resultado
        if resultado['success']:
            return _success_response(
                data=resultado['data'],
                mensaje='Imagen procesada correctamente'
            )
        else:
            return _error_response(resultado['error'], 500)

    except ValueError as e:
        logger.error(f"Error validando parámetros: {str(e)}")
        return _error_response(f"Parámetro inválido: {str(e)}", 400)
    except Exception as e:
        logger.error(f"Error procesando imagen: {str(e)}", exc_info=True)
        return _error_response(f"Error inesperado: {str(e)}", 500)


@imagen_procesamiento_bp.route('/solo-fondo', methods=['POST'])
def solo_eliminar_fondo():
    """
    Solo elimina el fondo (más rápido si no necesitas segmentación).

    Request: file (imagen)
    """
    try:
        if 'file' not in request.files:
            return _error_response('No se proporcionó archivo', 400)

        archivo = request.files['file']
        if not archivo or archivo.filename == '':
            return _error_response('Archivo inválido', 400)

        imagen_bytes = archivo.read()
        if not imagen_bytes:
            return _error_response('Archivo vacío', 400)

        logger.info(f"Eliminando fondo: {archivo.filename}")

        resultado = _servicio.solo_eliminar_fondo(imagen_bytes)

        if resultado['success']:
            return _success_response(
                data=resultado['data'],
                mensaje='Fondo eliminado correctamente'
            )
        else:
            return _error_response(resultado['error'], 500)

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return _error_response(str(e), 500)


@imagen_procesamiento_bp.route('/estado-backend-reconocimiento', methods=['GET'])
def estado_backend():
    """
    Verifica si el backend de reconocimiento está disponible.

    Útil para debugging.
    """
    try:
        disponible = _servicio._verificar_backend_disponible()
        if disponible:
            return _success_response(
                data={'estado': 'disponible'},
                mensaje='Backend reconocimiento operacional'
            )
        else:
            return _error_response('Backend reconocimiento no disponible', 503)
    except Exception as e:
        return _error_response(str(e), 500)
