from flask import Blueprint, request, jsonify
from typing import Optional, Dict, Any, Tuple
from app.services.supabase_client import supabase
from app.controllers.tipo_personal_controller import verify_jwt
from app.services.reportes_productos_service import (
    registrar_creacion_producto,
    registrar_edicion_producto,
    registrar_eliminacion_producto,
    obtener_reportes,
    obtener_resumen_reportes
)
from app.services.pusher_service import notificar_nuevo_producto
from app.controllers.producto_detalle_controller import DETALLE_FIELDS, _upsert_detalle_producto
from werkzeug.utils import secure_filename
import mimetypes
import tempfile
import os
import re
import unicodedata

productos_flutter_bp = Blueprint('productos_flutter', __name__, url_prefix='/api/flutter/productos')

# ── Reglas de validación de campos ──────────────────────────────────────────
CODIGO_MAX_LEN = 50
DESCRIPCION_MAX_LEN = 500
SERIE_MAX_LEN = 50

# Código de producto: letras, números, punto, guion y guion bajo (ej. "VT-001").
CODIGO_PATTERN = re.compile(r'^[A-Za-z0-9._-]+$')
FORMAS_VALIDAS = {'L', 'U', 'H', 'riel', 'otro'}

# Número válido: admite 0 como valor, pero rechaza ceros redundantes a la
# izquierda (ej. "000000", "007"). Sí admite decimales (ej. "0.5", "120.75").
NUMERO_PATTERN = re.compile(r'^(0|[1-9]\d*)(\.\d+)?$')

# Campos numéricos de detalle_producto (especificaciones técnicas): no admiten
# valores negativos ni texto.
DETALLE_NUMERIC_FIELDS = {
    'rebaje_mm', 'cara_visible_mm', 'canal_ancho_mm', 'barra_largo_cm',
    'tolerancia_mm', 'espesor_mm', 'plancha_ancho_cm', 'plancha_alto_cm',
}

# Ancho/alto de plancha (vidrio) y largo de barra (aluminio): mismo límite,
# no pueden superar 5 metros.
MEDIDA_LARGA_MAX_CM = 500
CAMPOS_MEDIDA_LARGA = {'plancha_ancho_cm', 'plancha_alto_cm', 'barra_largo_cm'}

ETIQUETAS_DETALLE = {
    'rebaje_mm': 'El rebaje',
    'cara_visible_mm': 'La cara visible',
    'canal_ancho_mm': 'El canal ancho',
    'barra_largo_cm': 'El largo de barra',
    'tolerancia_mm': 'La tolerancia',
    'espesor_mm': 'El espesor',
    'plancha_ancho_cm': 'La plancha ancho',
    'plancha_alto_cm': 'La plancha alto',
}


def _extraer_detalle(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extrae del payload los campos de especificaciones técnicas (detalle_producto).

    Mismos campos que usa el sitio web (ver producto_detalle_controller.DETALLE_FIELDS).
    """
    return {k: data[k] for k in DETALLE_FIELDS if data.get(k) not in (None, '')}


def _validar_numero_medida(
    valor: Any, etiqueta: str, *, maximo: Optional[float] = None
) -> Tuple[bool, Optional[str]]:
    """Valida un número de medida (mm/cm): admite 0, rechaza signos negativos y
    formatos con ceros redundantes (ej. "000000"), y opcionalmente un máximo.
    """
    texto = str(valor).strip()
    if not NUMERO_PATTERN.match(texto):
        return False, f"{etiqueta} tiene un formato inválido"
    numero = float(texto)
    if maximo is not None and numero > maximo:
        return False, f"{etiqueta} no puede superar {maximo:g} cm (5 metros)"
    return True, None


def _validar_grosor(valor: Any) -> Tuple[bool, Optional[str]]:
    """El grosor se mide en milímetros: número desde 0, sin guiones ni texto."""
    if valor in (None, ''):
        return True, None
    texto = str(valor).strip()
    if not texto:
        return True, None
    return _validar_numero_medida(texto, "El grosor")


def _validar_detalle_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Valida las especificaciones técnicas (detalle_producto) si vinieron en el payload."""
    for campo in DETALLE_NUMERIC_FIELDS:
        valor = data.get(campo)
        if valor in (None, ''):
            continue
        maximo = MEDIDA_LARGA_MAX_CM if campo in CAMPOS_MEDIDA_LARGA else None
        ok, mensaje = _validar_numero_medida(valor, ETIQUETAS_DETALLE.get(campo, campo), maximo=maximo)
        if not ok:
            return False, mensaje

    serie = data.get('serie')
    if serie not in (None, '') and len(str(serie).strip()) > SERIE_MAX_LEN:
        return False, f"La serie no puede superar {SERIE_MAX_LEN} caracteres"

    forma = data.get('forma')
    if forma not in (None, '') and str(forma) not in FORMAS_VALIDAS:
        return False, "Forma inválida"

    return True, None


def _env_enabled(name: str, default: str = '1') -> bool:
    return os.getenv(name, default).strip().lower() in ('1', 'true', 'yes', 'si')


def _normalize_text(value: str) -> str:
    if not value:
        return ''
    normalized = unicodedata.normalize('NFD', str(value))
    normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
    return normalized.upper().strip()


def _require_mobile_personal_access(allowed_areas=None):
    """Seguridad para API Flutter de productos.

    Variables de entorno:
    - FLUTTER_PRODUCTOS_REQUIRE_AUTH=1|0 (default 1)
    - MOBILE_API_KEY=<valor> para exigir header X-Mobile-Key
    """
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'success': False, 'message': 'No autorizado: falta token Bearer'}), 401

    token = auth.split(' ', 1)[1]
    payload = verify_jwt(token)
    if not payload or payload.get('aud') != 'personal':
        return jsonify({'success': False, 'message': 'Token inválido o expirado'}), 401

    required_mobile_key = os.getenv('MOBILE_API_KEY', '').strip()
    if required_mobile_key:
        provided_mobile_key = request.headers.get('X-Mobile-Key', '').strip()
        if provided_mobile_key != required_mobile_key:
            return jsonify({'success': False, 'message': 'Acceso denegado: cliente móvil no válido'}), 403

    if allowed_areas:
        area = _normalize_text(payload.get('area', ''))
        allowed = [_normalize_text(a) for a in allowed_areas]
        if area not in allowed:
            return jsonify({'success': False, 'message': 'Área no autorizada'}), 403

    return None


@productos_flutter_bp.before_request
def _authorize_flutter_productos():
    # El preflight CORS (OPTIONS) no debe exigir Bearer.
    if request.method.upper() == 'OPTIONS':
        return None

    if not _env_enabled('FLUTTER_PRODUCTOS_REQUIRE_AUTH', '1'):
        return None

    # Lectura móvil: cualquier personal autenticado.
    # Escritura móvil: sólo ALMACEN/ADMINISTRACION.
    metodo = request.method.upper()
    if metodo in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return _require_mobile_personal_access(['ALMACEN', 'ADMINISTRACION'])
    return _require_mobile_personal_access()


def _validar_producto_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Valida que los datos del producto sean válidos.
    
    Args:
        data: Diccionario con datos del producto
    
    Returns:
        Tupla (es_valido, mensaje_error)
    """
    nombre = str(data.get('nombre') or '').strip()
    if not nombre:
        return False, "El nombre es obligatorio"

    codigo = str(data.get('codigo') or '').strip()
    if not codigo:
        return False, "El código es obligatorio"
    if len(codigo) > CODIGO_MAX_LEN:
        return False, f"El código no puede superar {CODIGO_MAX_LEN} caracteres"
    if not CODIGO_PATTERN.match(codigo):
        return False, "El código solo puede contener letras, números, puntos, guiones y guiones bajos"

    if not str(data.get('categoria_id') or '').strip():
        return False, "Selecciona una categoría"

    # Validar tipos de datos
    try:
        cantidad = float(data.get('cantidad', 0))
        precio = float(data.get('precio_unitario', 0))
    except (ValueError, TypeError):
        return False, "Cantidad y precio deben ser números válidos"

    if cantidad < 1:
        return False, "La cantidad debe ser mayor o igual a 1"
    if precio <= 0:
        return False, "El precio debe ser mayor a 0"

    ok, mensaje = _validar_grosor(data.get('grosor'))
    if not ok:
        return False, mensaje

    descripcion = data.get('descripcion')
    if descripcion not in (None, '') and len(str(descripcion)) > DESCRIPCION_MAX_LEN:
        return False, f"La descripción no puede superar {DESCRIPCION_MAX_LEN} caracteres"

    ok, mensaje = _validar_detalle_data(data)
    if not ok:
        return False, mensaje

    return True, None


def _validar_actualizacion_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Valida los campos presentes en una actualización parcial de producto.

    A diferencia de `_validar_producto_data`, aquí ningún campo es obligatorio
    (es una edición parcial): solo se valida lo que efectivamente vino en el payload.
    """
    if 'nombre' in data and data['nombre'] not in (None, ''):
        nombre = str(data['nombre']).strip()
        if not nombre:
            return False, "El nombre no puede quedar vacío"

    if 'codigo' in data and data['codigo'] not in (None, ''):
        codigo = str(data['codigo']).strip()
        if not codigo:
            return False, "El código no puede quedar vacío"
        if len(codigo) > CODIGO_MAX_LEN:
            return False, f"El código no puede superar {CODIGO_MAX_LEN} caracteres"
        if not CODIGO_PATTERN.match(codigo):
            return False, "El código solo puede contener letras, números, puntos, guiones y guiones bajos"

    if 'cantidad' in data and data['cantidad'] not in (None, ''):
        try:
            cantidad = float(data['cantidad'])
        except (ValueError, TypeError):
            return False, "La cantidad debe ser un número válido"
        if cantidad < 0:
            return False, "La cantidad no puede ser negativa"

    if 'precio_unitario' in data and data['precio_unitario'] not in (None, ''):
        try:
            precio = float(data['precio_unitario'])
        except (ValueError, TypeError):
            return False, "El precio debe ser un número válido"
        if precio <= 0:
            return False, "El precio debe ser mayor a 0"

    ok, mensaje = _validar_grosor(data.get('grosor'))
    if not ok:
        return False, mensaje

    descripcion = data.get('descripcion')
    if descripcion not in (None, '') and len(str(descripcion)) > DESCRIPCION_MAX_LEN:
        return False, f"La descripción no puede superar {DESCRIPCION_MAX_LEN} caracteres"

    ok, mensaje = _validar_detalle_data(data)
    if not ok:
        return False, mensaje

    return True, None


def _subir_imagen_a_storage(file, categoria: str = 'productos') -> Tuple[bool, Optional[str], Optional[str]]:
    """Sube una imagen al bucket IMG de Supabase Storage.
    
    Args:
        file: Archivo Flask FileStorage
        categoria: Categoría/carpeta donde guardar la imagen
    
    Returns:
        Tupla (success, url_publica, mensaje_error)
    """
    try:
        if not file or file.filename == '':
            return False, None, "No hay archivo"
        
        filename = secure_filename(file.filename)
        if not filename:
            return False, None, "Nombre de archivo inválido"
        
        # Determinar content-type
        content_type, _ = mimetypes.guess_type(filename)
        if content_type is None:
            content_type = 'application/octet-stream'
        
        # Ruta en Supabase: PRODUCTOS/{categoria}/{filename}
        remote_path = f"PRODUCTOS/{categoria}/{filename}"
        file_bytes = file.read()
        file.seek(0)  # Reset para por si se necesita releer
        
        # Intentar subir, si existe, eliminar y reintentar
        try:
            up = supabase.storage.from_('IMG').upload(
                path=remote_path,
                file=file_bytes,
                file_options={'content-type': content_type}
            )
        except Exception as e:
            msg = str(e)
            if 'already exists' in msg or '409' in msg or 'Duplicate' in msg:
                try:
                    supabase.storage.from_('IMG').remove([remote_path])
                    up = supabase.storage.from_('IMG').upload(
                        path=remote_path,
                        file=file_bytes,
                        file_options={'content-type': content_type}
                    )
                except Exception as e2:
                    return False, None, f"Error al sobreescribir: {str(e2)}"
            else:
                return False, None, f"Error en Supabase Storage: {str(e)}"
        
        # Verificar errores en la respuesta
        err_up = getattr(up, 'error', None) if up is not None else None
        if err_up:
            if 'already exists' in str(err_up) or '409' in str(err_up):
                try:
                    supabase.storage.from_('IMG').remove([remote_path])
                    up = supabase.storage.from_('IMG').upload(
                        path=remote_path,
                        file=file_bytes,
                        file_options={'content-type': content_type}
                    )
                    err_up = getattr(up, 'error', None) if up is not None else None
                    if err_up:
                        return False, None, str(err_up)
                except Exception as e2:
                    return False, None, f"Error al sobreescribir: {str(e2)}"
            else:
                return False, None, str(err_up)
        
        # Obtener URL pública
        url_obj = supabase.storage.from_('IMG').get_public_url(remote_path)
        url = None
        
        if isinstance(url_obj, str):
            url = url_obj
        elif hasattr(url_obj, 'public_url'):
            url = url_obj.public_url
        elif isinstance(url_obj, dict):
            url = url_obj.get('publicUrl') or url_obj.get('publicURL') or url_obj.get('public_url')
        
        if not url:
            return False, None, "No se pudo obtener URL pública"
        
        return True, url, None
        
    except Exception as e:
        return False, None, f"Error interno: {str(e)}"


def _crear_almacen(fila: Optional[str], columna: Optional[str]) -> Optional[str]:
    """Crea un registro en la tabla almacén si se proporcionan fila/columna.
    
    Args:
        fila: Fila del almacén (opcional)
        columna: Columna del almacén (opcional)
    
    Returns:
        ID del almacén creado o None
    """
    if not fila and not columna:
        return None
    
    try:
        almacen_payload = {
            'fila': fila,
            'columna': columna,
        }
        almacen_resp = supabase.table('almacen').insert(almacen_payload).execute()
        err_alm = getattr(almacen_resp, 'error', None) if almacen_resp is not None else None
        data_alm = getattr(almacen_resp, 'data', None) if almacen_resp is not None else None
        
        if err_alm:
            print(f"Error creando almacén: {err_alm}")
            return None
        
        if isinstance(data_alm, list) and len(data_alm) > 0:
            return data_alm[0].get('id_almacen')
        elif isinstance(data_alm, dict):
            return data_alm.get('id_almacen')
        
        return None
    except Exception as e:
        print(f"Excepción creando almacén: {str(e)}")
        return None


@productos_flutter_bp.route('/subir-imagen', methods=['POST'])
def subir_imagen():
    """Sube una imagen a Supabase Storage y retorna la URL pública.
    
    Recibe multipart/form-data:
    - file: Archivo de imagen (requerido)
    - categoria: Categoría/carpeta donde guardar (opcional, default: 'productos')
    
    Respuesta:
    {
        "success": true,
        "url": "https://...",
        "path": "PRODUCTOS/categoria/filename",
        "message": "Imagen subida exitosamente"
    }
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                "success": False,
                "message": "No se proporcionó archivo (campo 'file')"
            }), 400
        
        file = request.files['file']
        categoria = request.form.get('categoria', 'productos') or 'productos'
        
        # Subir imagen
        success, url, error = _subir_imagen_a_storage(file, categoria)
        
        if not success:
            return jsonify({
                "success": False,
                "message": error
            }), 400
        
        return jsonify({
            "success": True,
            "url": url,
            "path": f"PRODUCTOS/{categoria}/{secure_filename(file.filename)}",
            "message": "Imagen subida exitosamente"
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/registrar', methods=['POST'])
def registrar_producto():
    """Registra un nuevo producto desde la aplicación móvil.
    
    Soporta dos formas de uso:
    
    OPCIÓN 1 - JSON (IMG_P ya existente):
    Content-Type: application/json
    {
        "codigo": "P001",
        "nombre": "Vidrio Temple 10mm",
        "cantidad": 100,
        "precio_unitario": 250.50,
        "descripcion": "Vidrio templado de 10mm espesor",
        "grosor": "10mm",
        "categoria_id": "uuid-categoria",
        "stock_id": "uuid-stock" (opcional),
        "IMG_P": "https://..." (opcional - URL ya generada),
        "fila": "A" (opcional),
        "columna": "1" (opcional)
    }
    
    OPCIÓN 2 - Multipart (Subir imagen junto con datos):
    Content-Type: multipart/form-data
    - file: Archivo de imagen
    - codigo: "P001"
    - nombre: "Vidrio Temple 10mm"
    - cantidad: "100"
    - precio_unitario: "250.50"
    - descripcion: (opcional)
    - grosor: (opcional)
    - categoria_id: "uuid-categoria"
    - stock_id: (opcional)
    - fila: (opcional)
    - columna: (opcional)
    - imagen_categoria: Categoría para guardar imagen (default: 'productos')
    
    Respuesta:
    {
        "success": true,
        "data": {
            "id_producto": "uuid",
            "codigo": "P001",
            "nombre": "Vidrio Temple 10mm",
            ...resto de campos (incluyendo IMG_P con URL generada)
        },
        "message": "Producto registrado exitosamente"
    }
    """
    try:
        # Detectar si es multipart (con archivo) o JSON
        if 'file' in request.files or request.content_type == 'multipart/form-data':
            # ===== OPCIÓN 2: Multipart (con archivo) =====
            data = request.form.to_dict()
            
            # Si hay archivo, subirlo primero
            img_url = None
            if 'file' in request.files:
                file = request.files['file']
                imagen_categoria = request.form.get('imagen_categoria', 'productos') or 'productos'
                
                success, url, error = _subir_imagen_a_storage(file, imagen_categoria)
                if not success:
                    return jsonify({
                        "success": False,
                        "message": f"Error al subir imagen: {error}"
                    }), 400
                img_url = url
            
        else:
            # ===== OPCIÓN 1: JSON =====
            data = request.get_json() or {}
            img_url = data.get('IMG_P')
        
        # Validar datos
        es_valido, error_msg = _validar_producto_data(data)
        if not es_valido:
            return jsonify({
                "success": False,
                "message": error_msg
            }), 400

        if not img_url:
            return jsonify({
                "success": False,
                "message": "La imagen del producto es obligatoria"
            }), 400

        # Crear registro en almacén si es necesario
        almacen_id = None
        if data.get('fila') or data.get('columna'):
            almacen_id = _crear_almacen(data.get('fila'), data.get('columna'))

        # Preparar payload para insertar producto
        payload = {
            'codigo': str(data.get('codigo') or '').strip(),
            'nombre': str(data.get('nombre') or '').strip(),
            'cantidad': int(float(data.get('cantidad', 0))),
            'precio_unitario': float(data.get('precio_unitario', 0)),
            'descripcion': str(data.get('descripcion') or '').strip() or None,
            'grosor': str(data.get('grosor') or '').strip() or None,
            'categoria_id': data.get('categoria_id'),
            'almacen_id': almacen_id,
            'stock_id': data.get('stock_id') or None,
            'IMG_P': img_url,  # URL generada en Supabase Storage
        }
        
        # Insertar en Supabase
        resp = supabase.table('productos').insert(payload).execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        data_resp = getattr(resp, 'data', None) if resp is not None else None
        
        if err:
            return jsonify({
                "success": False,
                "message": f"Error en base de datos: {str(err)}"
            }), 500
        
        # Retornar producto registrado
        producto = data_resp[0] if isinstance(data_resp, list) and len(data_resp) > 0 else data_resp

        # Guardar especificaciones técnicas (detalle_producto), si vinieron en el payload
        detalle_payload = _extraer_detalle(data)
        if detalle_payload and producto.get('id_producto'):
            detalle_guardado = _upsert_detalle_producto(producto['id_producto'], detalle_payload)
            if detalle_guardado:
                producto['detalle'] = detalle_guardado[0] if isinstance(detalle_guardado, list) else detalle_guardado

        # Registrar en reportes
        registrar_creacion_producto(producto.get('id_producto'), producto)

        # Notificar por Pusher (si no hay configuracion, solo omite sin romper flujo)
        notificar_nuevo_producto(
            nombre=producto.get('nombre') or data.get('nombre') or 'Sin nombre',
            codigo=producto.get('codigo') or data.get('codigo'),
        )
        
        return jsonify({
            "success": True,
            "data": producto,
            "message": "Producto registrado exitosamente"
        }), 201
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/registrar-por-pasos', methods=['POST'])
def registrar_por_pasos():
    """Registra un producto en dos pasos separados (para UX mejorada en mobile).
    
    Parámetro de query:
    - paso: '1' (subir imagen) o '2' (guardar producto)
    
    PASO 1 - Subir imagen:
    POST /api/flutter/productos/registrar-por-pasos?paso=1
    Body: multipart/form-data
    - file: Archivo de imagen
    - categoria: (opcional, default: 'productos')
    
    Respuesta:
    {
        "success": true,
        "paso": 1,
        "image_url": "https://...",
        "message": "Imagen subida, ahora envía los datos del producto"
    }
    
    PASO 2 - Guardar producto:
    POST /api/flutter/productos/registrar-por-pasos?paso=2
    Body: application/json
    {
        "codigo": "P001",
        "nombre": "Vidrio Temple",
        "cantidad": 100,
        "precio_unitario": 250.50,
        "descripcion": "...",
        "grosor": "10mm",
        "categoria_id": "uuid",
        "IMG_P": "https://..." (URL obtenida en paso 1),
        ...otros campos opcionales
    }
    
    Respuesta:
    {
        "success": true,
        "paso": 2,
        "data": {...producto creado},
        "message": "Producto registrado exitosamente"
    }
    """
    try:
        paso = request.args.get('paso', '1')
        
        if paso == '1':
            # ===== PASO 1: Subir imagen =====
            if 'file' not in request.files:
                return jsonify({
                    "success": False,
                    "paso": 1,
                    "message": "No se proporcionó archivo (campo 'file')"
                }), 400
            
            file = request.files['file']
            categoria = request.form.get('categoria', 'productos') or 'productos'
            
            success, url, error = _subir_imagen_a_storage(file, categoria)
            
            if not success:
                return jsonify({
                    "success": False,
                    "paso": 1,
                    "message": f"Error al subir imagen: {error}"
                }), 400
            
            return jsonify({
                "success": True,
                "paso": 1,
                "image_url": url,
                "message": "Imagen subida exitosamente. Ahora envía los datos del producto"
            }), 200
        
        elif paso == '2':
            # ===== PASO 2: Guardar producto =====
            data = request.get_json() or {}
            
            # Validar datos
            es_valido, error_msg = _validar_producto_data(data)
            if not es_valido:
                return jsonify({
                    "success": False,
                    "paso": 2,
                    "message": error_msg
                }), 400
            
            # Validar que IMG_P esté presente
            if not data.get('IMG_P'):
                return jsonify({
                    "success": False,
                    "paso": 2,
                    "message": "IMG_P (URL de imagen) es requerido en paso 2"
                }), 400
            
            # Crear almacén si es necesario
            almacen_id = None
            if data.get('fila') or data.get('columna'):
                almacen_id = _crear_almacen(data.get('fila'), data.get('columna'))
            
            # Preparar payload
            payload = {
                'codigo': str(data.get('codigo') or '').strip(),
                'nombre': str(data.get('nombre') or '').strip(),
                'cantidad': int(float(data.get('cantidad', 0))),
                'precio_unitario': float(data.get('precio_unitario', 0)),
                'descripcion': str(data.get('descripcion') or '').strip() or None,
                'grosor': str(data.get('grosor') or '').strip() or None,
                'categoria_id': data.get('categoria_id'),
                'almacen_id': almacen_id,
                'stock_id': data.get('stock_id') or None,
                'IMG_P': data.get('IMG_P'),  # URL subida en paso 1
            }

            # Insertar producto
            resp = supabase.table('productos').insert(payload).execute()
            err = getattr(resp, 'error', None) if resp is not None else None
            data_resp = getattr(resp, 'data', None) if resp is not None else None

            if err:
                return jsonify({
                    "success": False,
                    "paso": 2,
                    "message": f"Error al guardar producto: {str(err)}"
                }), 500

            producto = data_resp[0] if isinstance(data_resp, list) and len(data_resp) > 0 else data_resp

            # Guardar especificaciones técnicas (detalle_producto), si vinieron en el payload
            detalle_payload = _extraer_detalle(data)
            if detalle_payload and producto.get('id_producto'):
                detalle_guardado = _upsert_detalle_producto(producto['id_producto'], detalle_payload)
                if detalle_guardado:
                    producto['detalle'] = detalle_guardado[0] if isinstance(detalle_guardado, list) else detalle_guardado

            # Notificar por Pusher (si no hay configuracion, solo omite sin romper flujo)
            notificar_nuevo_producto(
                nombre=producto.get('nombre') or data.get('nombre') or 'Sin nombre',
                codigo=producto.get('codigo') or data.get('codigo'),
            )
            
            return jsonify({
                "success": True,
                "paso": 2,
                "data": producto,
                "message": "Producto registrado exitosamente"
            }), 201
        
        else:
            return jsonify({
                "success": False,
                "message": "Parámetro 'paso' debe ser '1' o '2'"
            }), 400
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500





@productos_flutter_bp.route('/listar', methods=['GET'])
def listar_productos():
    """Obtiene la lista de productos.
    
    Parámetros opcionales:
    - categoria_id: Filtrar por categoría
    - max_cantidad: Filtrar productos con cantidad menor o igual al valor enviado
    - limit: Límite de resultados (default: 50)
    - offset: Offset para paginación (default: 0)
    
    Respuesta:
    {
        "success": true,
        "data": [
            {
                "id_producto": "uuid",
                "codigo": "P001",
                "nombre": "Vidrio Temple 10mm",
                "cantidad": 100,
                "precio_unitario": 250.50,
                "descripcion": "...",
                "grosor": "10mm",
                "categoria_id": "uuid",
                "IMG_P": "url"
            },
            ...
        ],
        "total": 250
    }
    """
    try:
        categoria_id = request.args.get('categoria_id')
        max_cantidad_raw = request.args.get('max_cantidad')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        max_cantidad = None

        if max_cantidad_raw not in (None, ''):
            try:
                max_cantidad = int(max_cantidad_raw)
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "message": "El parámetro max_cantidad debe ser numérico"
                }), 400
        
        # Limitar límite a 100 para evitar sobrecarga
        limit = min(limit, 100)
        
        # Construir query
        query = supabase.table('productos').select(
            'id_producto, codigo, nombre, cantidad, precio_unitario, descripcion, grosor, categoria_id, IMG_P'
        )
        
        # Filtrar por categoría si se especifica
        if categoria_id:
            query = query.eq('categoria_id', categoria_id)

        # Filtrar por stock máximo si se especifica
        if max_cantidad is not None:
            query = query.lte('cantidad', max_cantidad)

        query = query.order('cantidad', desc=False).order('nombre', desc=False)
        
        # Aplicar paginación
        query = query.range(offset, offset + limit - 1)
        
        # Ejecutar query
        resp = query.execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        data = getattr(resp, 'data', None) if resp is not None else None
        
        if err:
            return jsonify({
                "success": False,
                "message": f"Error al obtener productos: {str(err)}"
            }), 500
        
        return jsonify({
            "success": True,
            "data": data or [],
            "total": len(data) if data else 0
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/obtener/<producto_id>', methods=['GET'])
def obtener_producto(producto_id: str):
    """Obtiene un producto específico por ID.
    
    Respuesta:
    {
        "success": true,
        "data": {
            "id_producto": "uuid",
            "codigo": "P001",
            "nombre": "Vidrio Temple 10mm",
            ...campos completos
        }
    }
    """
    try:
        resp = supabase.table('productos').select('*').eq('id_producto', producto_id).single().execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        data = getattr(resp, 'data', None) if resp is not None else None
        
        if err or not data:
            return jsonify({
                "success": False,
                "message": "Producto no encontrado"
            }), 404

        detalle_resp = supabase.table('detalle_producto').select('*').eq('producto_id', producto_id).limit(1).execute()
        detalle_data = getattr(detalle_resp, 'data', None) or []
        if detalle_data:
            data['detalle'] = detalle_data[0]

        return jsonify({
            "success": True,
            "data": data
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/<producto_id>/detalle', methods=['GET'])
def obtener_detalle_producto_flutter(producto_id: str):
    """Obtiene las especificaciones técnicas (detalle_producto) de un producto.

    Respuesta:
    {
        "success": true,
        "data": { ...campos de detalle_producto... } | null
    }
    """
    try:
        resp = supabase.table('detalle_producto').select('*').eq('producto_id', producto_id).limit(1).execute()
        data = getattr(resp, 'data', None) or []
        return jsonify({
            "success": True,
            "data": data[0] if data else None
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/actualizar/<producto_id>', methods=['PUT'])
def actualizar_producto(producto_id: str):
    """Actualiza un producto existente.
    
    Body JSON esperado:
    {
        "nombre": "Nuevo nombre",
        "cantidad": 150,
        "precio_unitario": 280.00,
        ...otros campos a actualizar
    }
    
    Respuesta:
    {
        "success": true,
        "data": {...producto actualizado}
    }
    """
    try:
        # Detectar si es multipart (con archivo nuevo) o JSON
        if 'file' in request.files or request.content_type == 'multipart/form-data':
            data = request.form.to_dict()
            if 'file' in request.files:
                file = request.files['file']
                imagen_categoria = request.form.get('imagen_categoria', 'productos') or 'productos'
                success, url, error = _subir_imagen_a_storage(file, imagen_categoria)
                if not success:
                    return jsonify({
                        "success": False,
                        "message": f"Error al subir imagen: {error}"
                    }), 400
                data['IMG_P'] = url
        else:
            data = request.get_json() or {}

        if not data:
            return jsonify({
                "success": False,
                "message": "No hay datos para actualizar"
            }), 400

        # Validar los campos que vinieron en el payload
        es_valido, error_msg = _validar_actualizacion_data(data)
        if not es_valido:
            return jsonify({
                "success": False,
                "message": error_msg
            }), 400

        # Obtener datos anteriores del producto
        resp_anterior = supabase.table('productos').select('*').eq('id_producto', producto_id).single().execute()
        datos_anteriores = getattr(resp_anterior, 'data', None) if resp_anterior is not None else None

        # Limpiar datos para actualizar
        payload = {}
        campos_permitidos = ['nombre', 'codigo', 'cantidad', 'precio_unitario', 'descripcion',
                           'grosor', 'categoria_id', 'stock_id', 'IMG_P']

        for campo in campos_permitidos:
            if campo in data and data[campo] not in (None, ''):
                if campo in ['cantidad']:
                    payload[campo] = int(float(data[campo]))
                elif campo in ['precio_unitario']:
                    payload[campo] = float(data[campo])
                elif campo in ['nombre', 'codigo', 'descripcion', 'grosor']:
                    payload[campo] = str(data[campo]).strip()
                else:
                    payload[campo] = data[campo]

        # Especificaciones técnicas (detalle_producto), si vinieron en el payload
        detalle_payload = _extraer_detalle(data)

        if not payload and not detalle_payload:
            return jsonify({
                "success": False,
                "message": "No hay campos válidos para actualizar"
            }), 400

        if payload:
            # Actualizar en Supabase
            resp = supabase.table('productos').update(payload).eq('id_producto', producto_id).execute()
            err = getattr(resp, 'error', None) if resp is not None else None
            data_resp = getattr(resp, 'data', None) if resp is not None else None

            if err:
                return jsonify({
                    "success": False,
                    "message": f"Error al actualizar: {str(err)}"
                }), 500

            if not data_resp or (isinstance(data_resp, list) and len(data_resp) == 0):
                return jsonify({
                    "success": False,
                    "message": "Producto no encontrado"
                }), 404

            producto = data_resp[0] if isinstance(data_resp, list) else data_resp
        else:
            if not datos_anteriores:
                return jsonify({
                    "success": False,
                    "message": "Producto no encontrado"
                }), 404
            producto = datos_anteriores

        if detalle_payload:
            detalle_guardado = _upsert_detalle_producto(producto_id, detalle_payload)
            if detalle_guardado:
                producto['detalle'] = detalle_guardado[0] if isinstance(detalle_guardado, list) else detalle_guardado

        # Registrar edición en reportes usando datos completos retornados por la DB
        registrar_edicion_producto(producto_id, datos_anteriores, producto)

        return jsonify({
            "success": True,
            "data": producto,
            "message": "Producto actualizado exitosamente"
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/eliminar/<producto_id>', methods=['DELETE'])
def eliminar_producto(producto_id: str):
    """Elimina un producto.
    
    Respuesta:
    {
        "success": true,
        "message": "Producto eliminado exitosamente"
    }
    """
    try:
        # Verificar que existe y obtener sus datos
        existe = supabase.table('productos').select('*').eq('id_producto', producto_id).single().execute()
        existe_data = getattr(existe, 'data', None) if existe is not None else None
        
        if not existe_data:
            return jsonify({
                "success": False,
                "message": "Producto no encontrado"
            }), 404
        
        # Registrar eliminación en reportes (antes de eliminar)
        registrar_eliminacion_producto(producto_id, existe_data)
        
        # Eliminar
        resp = supabase.table('productos').delete().eq('id_producto', producto_id).execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        
        if err:
            return jsonify({
                "success": False,
                "message": f"Error al eliminar: {str(err)}"
            }), 500
        
        return jsonify({
            "success": True,
            "message": "Producto eliminado exitosamente"
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/categorias', methods=['GET'])
def listar_categorias():
    """Obtiene la lista de categorías de productos.
    
    Respuesta:
    {
        "success": true,
        "data": [
            {
                "id_categoria": "uuid",
                "descripcion": "Vidrios"
            },
            ...
        ]
    }
    """
    try:
        resp = supabase.table('categoria').select('id_categoria, descripcion').execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        data = getattr(resp, 'data', None) if resp is not None else None
        
        if err:
            return jsonify({
                "success": False,
                "message": f"Error al obtener categorías: {str(err)}"
            }), 500
        
        return jsonify({
            "success": True,
            "data": data or []
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/buscar', methods=['GET'])
def buscar_producto():
    """Busca productos por código o nombre.
    
    Parámetros:
    - q: String de búsqueda (requerido)
    - limit: Límite de resultados (default: 20)
    
    Respuesta:
    {
        "success": true,
        "data": [
            {...},
            ...
        ]
    }
    """
    try:
        query_str = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 20))
        
        if not query_str or len(query_str) < 2:
            return jsonify({
                "success": False,
                "message": "Búsqueda debe tener al menos 2 caracteres"
            }), 400
        
        limit = min(limit, 50)
        
        # Buscar en código (case-insensitive)
        resp1 = supabase.table('productos').select(
            'id_producto, codigo, nombre, cantidad, precio_unitario, grosor, categoria_id, IMG_P'
        ).ilike('codigo', f'%{query_str}%').limit(limit).execute()
        
        # Buscar en nombre (case-insensitive)
        resp2 = supabase.table('productos').select(
            'id_producto, codigo, nombre, cantidad, precio_unitario, grosor, categoria_id, IMG_P'
        ).ilike('nombre', f'%{query_str}%').limit(limit).execute()
        
        err1 = getattr(resp1, 'error', None) if resp1 is not None else None
        err2 = getattr(resp2, 'error', None) if resp2 is not None else None
        
        if err1 or err2:
            return jsonify({
                "success": False,
                "message": "Error en búsqueda"
            }), 500
        
        data1 = getattr(resp1, 'data', None) if resp1 is not None else []
        data2 = getattr(resp2, 'data', None) if resp2 is not None else []
        
        # Combinar resultados sin duplicados basado en id_producto
        resultados = {}
        for item in (data1 or []):
            resultados[item['id_producto']] = item
        for item in (data2 or []):
            resultados[item['id_producto']] = item
        
        return jsonify({
            "success": True,
            "data": list(resultados.values())[:limit]
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/reportes', methods=['GET'])
def obtener_reportes_productos():
    """Obtiene los reportes de cambios en productos.
    
    Parámetros opcionales:
    - limit: Límite de resultados (default: 100)
    - offset: Offset para paginación (default: 0)
    - tipo: Filtrar por tipo (CREAR, EDITAR, ELIMINAR)
    - producto_id: Filtrar por producto
    
    Respuesta:
    {
        "success": true,
        "data": [
            {
                "id_reporte": "uuid",
                "tipo": "CREAR",
                "producto_id": "uuid",
                "datos_anteriores": null,
                "datos_nuevos": {...},
                "fecha_cambio": "2026-03-02T10:30:00"
            },
            ...
        ]
    }
    """
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        tipo = request.args.get('tipo')  # CREAR, EDITAR, ELIMINAR
        producto_id = request.args.get('producto_id')
        
        # Limitar a máximo 100
        limit = min(limit, 100)
        
        reportes = obtener_reportes(
            limite=limit,
            offset=offset,
            tipo=tipo,
            producto_id=producto_id
        )
        
        return jsonify({
            "success": True,
            "data": reportes
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500


@productos_flutter_bp.route('/reportes/resumen', methods=['GET'])
def obtener_resumen_reportes_productos():
    """Obtiene un resumen de los cambios en productos.
    
    Parámetros opcionales:
    - dias: Número de días hacia atrás (default: 30)
    
    Respuesta:
    {
        "success": true,
        "data": {
            "CREAR": 25,
            "EDITAR": 10,
            "ELIMINAR": 2,
            "TOTAL": 37
        }
    }
    """
    try:
        dias = int(request.args.get('dias', 30))
        
        resumen = obtener_resumen_reportes(dias=dias)
        
        return jsonify({
            "success": True,
            "data": resumen
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error interno: {str(e)}"
        }), 500
