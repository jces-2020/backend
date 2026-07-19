from flask import Blueprint, request, jsonify, render_template
from services.supabase_client import supabase
from controllers.carrito_compras_api_controller import verify_jwt
from typing import Optional
from services.servicio_finalizacion_service import guardar_servicio_completado
import os
import json

barra_progreso_api = Blueprint('barra_progreso_api', __name__)
bp = barra_progreso_api  # alias para auto-registro del factory
DEBUG_BARRA_LOGS = os.environ.get('DEBUG_BARRA_LOGS', '').strip().lower() in ('1', 'true', 'yes', 'si')
TIPO_VENTA_ID_PRODUCTO = "1397cefc-c5da-42bc-be75-a3ac36a2266d"


def _dbg(msg: str):
    if DEBUG_BARRA_LOGS:
        print(msg)


def _map_estado_pedido(estado_raw: Optional[str]):
    estado = (estado_raw or '').strip().lower()
    if estado == 'inicio':
        return 'Inicio', 33
    if estado == 'en proceso':
        return 'En proceso', 66
    if estado in ('listo', 'entregado'):
        return 'Entregado', 100
    return 'Inicio', 33


def _map_estado_servicio(estado_raw: Optional[str]):
    estado = (estado_raw or '').strip().lower()
    if estado == 'inicio':
        return 'Inicio', 33
    if estado in ('realizando',):
        return 'Realizando', 66
    if estado in ('instalacion',):
        return 'Instalacion', 85
    if estado in ('instalado',):
        return 'Instalado', 100
    if estado in ('en proceso', 'proceso'):
        return 'En proceso', 66
    if estado in ('entregado', 'finalizado', 'completado', 'listo'):
        return 'Finalizado', 100
    return 'Inicio', 33


def _resolver_cliente_id(cliente_id: Optional[str], cliente_nombre: Optional[str], cliente_correo: Optional[str]) -> Optional[str]:
    """Resuelve un cliente existente en tabla cliente y devuelve su id_cliente."""
    # 1) Por cliente_id explícito
    if cliente_id:
        try:
            cli_by_id = supabase.table('cliente').select('id_cliente').eq('id_cliente', cliente_id).limit(1).execute()
            if cli_by_id.data:
                return cli_by_id.data[0].get('id_cliente')
        except Exception:
            pass

    # 2) Por correo
    if cliente_correo:
        try:
            cli_by_mail = supabase.table('cliente').select('id_cliente').eq('correo', cliente_correo).limit(1).execute()
            if cli_by_mail.data:
                return cli_by_mail.data[0].get('id_cliente')
        except Exception:
            pass

    # 3) Por nombre (fallback)
    if cliente_nombre:
        try:
            cli_by_name = supabase.table('cliente').select('id_cliente').eq('nombre', cliente_nombre).limit(1).execute()
            if cli_by_name.data:
                return cli_by_name.data[0].get('id_cliente')
        except Exception:
            pass

    return None


def _vincular_notificacion_servicio(notificacion_id: Optional[str], carrito_id: Optional[str]):
    """Guarda metadatos mínimos para enlazar la notificación de servicio con su carrito."""
    if not notificacion_id or not carrito_id:
        return
    try:
        nres = supabase.table('notificacion').select('descripcion').eq('id_notificacion', notificacion_id).limit(1).execute()
        notif = (getattr(nres, 'data', None) or [None])[0] or {}
        descripcion_actual = notif.get('descripcion')

        meta = {}
        texto = ''
        if isinstance(descripcion_actual, dict):
            meta = dict(descripcion_actual)
            texto = str(meta.get('texto') or '').strip()
        elif isinstance(descripcion_actual, str):
            raw = descripcion_actual.strip()
            if raw:
                try:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        meta = loaded
                        texto = str(meta.get('texto') or '').strip()
                    else:
                        texto = raw
                except Exception:
                    texto = raw

        if texto:
            meta['texto'] = texto
        meta['carrito_id'] = carrito_id

        supabase.table('notificacion').update({
            'descripcion': json.dumps(meta, ensure_ascii=False)
        }).eq('id_notificacion', notificacion_id).execute()
    except Exception as exc:
        print(f"[WARN] No se pudo vincular notificación de servicio {notificacion_id} al carrito {carrito_id}: {exc}")


@barra_progreso_api.route('/api/barra_progreso/servicio/iniciar', methods=['POST'])
def iniciar_progreso_servicio():
    """Inicia (o reactiva) la barra de servicio para un cliente en carrito_compras.
    Si el cliente no existe en tabla cliente, no crea registro y responde success=true.
    """
    try:
        data = request.get_json(silent=True) or {}
        cliente_id = data.get('cliente_id')
        cliente_nombre = data.get('cliente_nombre')
        cliente_correo = data.get('cliente_correo')
        notificacion_id = data.get('notificacion_id')

        cliente_id_resuelto = _resolver_cliente_id(cliente_id, cliente_nombre, cliente_correo)
        if not cliente_id_resuelto:
            return jsonify({
                'success': True,
                'creado_carrito_servicio': False,
                'cliente_encontrado': False,
                'message': 'Cliente no existe en tabla cliente. No se crea carrito de servicio.'
            }), 200

        # Buscar un registro existente de tipo servicio.
        existente = supabase.table('carrito_compras') \
            .select('id_carrito, estado, nombre') \
            .eq('cliente_id', cliente_id_resuelto) \
            .eq('nombre', 'servicio') \
            .limit(1) \
            .execute()

        if existente.data:
            carrito_id = existente.data[0].get('id_carrito')
            upd = supabase.table('carrito_compras') \
                .update({'estado': 'inicio', 'nombre': 'servicio'}) \
                .eq('id_carrito', carrito_id) \
                .execute()
            _vincular_notificacion_servicio(notificacion_id, carrito_id)
            return jsonify({
                'success': True,
                'creado_carrito_servicio': True,
                'cliente_encontrado': True,
                'message': 'Servicio actualizado a inicio',
                'data': upd.data
            }), 200

        nuevo = supabase.table('carrito_compras').insert({
            'cliente_id': cliente_id_resuelto,
            'estado': 'inicio',
            'nombre': 'servicio'
        }).execute()
        try:
            carrito_id = (getattr(nuevo, 'data', None) or [None])[0].get('id_carrito') if getattr(nuevo, 'data', None) else None
        except Exception:
            carrito_id = None
        _vincular_notificacion_servicio(notificacion_id, carrito_id)
        return jsonify({
            'success': True,
            'creado_carrito_servicio': True,
            'cliente_encontrado': True,
            'message': 'Servicio iniciado',
            'data': nuevo.data
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@barra_progreso_api.route('/api/barra_progreso/servicio/estado', methods=['POST'])
def actualizar_estado_servicio():
    """Actualiza estado del servicio en carrito_compras para un cliente existente."""
    try:
        data = request.get_json(silent=True) or {}
        cliente_id = data.get('cliente_id')
        cliente_nombre = data.get('cliente_nombre')
        cliente_correo = data.get('cliente_correo')
        estado_objetivo = (data.get('estado') or 'realizando').strip().lower()

        cliente_id_resuelto = _resolver_cliente_id(cliente_id, cliente_nombre, cliente_correo)
        if not cliente_id_resuelto:
            return jsonify({
                'success': True,
                'actualizado': False,
                'cliente_encontrado': False,
                'message': 'Cliente no existe en tabla cliente. No se actualiza servicio.'
            }), 200

        # Cambiar a estado objetivo solo los servicios en inicio.
        upd = supabase.table('carrito_compras') \
            .update({'estado': estado_objetivo}) \
            .eq('cliente_id', cliente_id_resuelto) \
            .ilike('nombre', '%servicio%') \
            .eq('estado', 'inicio') \
            .execute()

        afectados = len(getattr(upd, 'data', []) or [])

        # Fallback: si no había en inicio pero sí existe servicio, forzar estado en el primero.
        if afectados == 0:
            srv = supabase.table('carrito_compras') \
                .select('id_carrito') \
                .eq('cliente_id', cliente_id_resuelto) \
                .ilike('nombre', '%servicio%') \
                .limit(1) \
                .execute()
            if srv.data:
                carrito_id = srv.data[0].get('id_carrito')
                supabase.table('carrito_compras').update({'estado': estado_objetivo}).eq('id_carrito', carrito_id).execute()
                afectados = 1

        return jsonify({
            'success': True,
            'actualizado': afectados > 0,
            'cliente_encontrado': True,
            'estado': estado_objetivo,
            'message': 'Estado de servicio actualizado' if afectados > 0 else 'No se encontró servicio para actualizar'
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@barra_progreso_api.route('/api/barra_progreso/servicio/descontar-stock', methods=['POST'])
def descontar_stock_servicio():
    """Descuenta stock de productos al guardar PRODUCTOS en servicio."""
    try:
        data = request.get_json(silent=True) or {}
        items = data.get('items') or []

        if not isinstance(items, list) or len(items) == 0:
            return jsonify({
                'success': False,
                'message': 'Debe enviar una lista de items con producto_id y cantidad'
            }), 400

        descuentos = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            producto_id = str(item.get('producto_id') or '').strip()
            if not producto_id:
                continue
            try:
                cantidad = int(float(item.get('cantidad') or 0))
            except Exception:
                cantidad = 0
            if cantidad <= 0:
                continue
            descuentos[producto_id] = int(descuentos.get(producto_id, 0)) + cantidad

        if not descuentos:
            return jsonify({
                'success': False,
                'message': 'No hay productos válidos para descontar stock'
            }), 400

        producto_ids = list(descuentos.keys())
        productos_res = supabase.table('productos') \
            .select('id_producto, nombre, cantidad') \
            .in_('id_producto', producto_ids) \
            .execute()

        productos = productos_res.data or []
        stock_map = {}
        nombre_map = {}
        for p in productos:
            pid = str(p.get('id_producto') or '').strip()
            if not pid:
                continue
            try:
                stock_map[pid] = int(float(p.get('cantidad') or 0))
            except Exception:
                stock_map[pid] = 0
            nombre_map[pid] = p.get('nombre') or pid

        faltantes = [pid for pid in producto_ids if pid not in stock_map]
        if faltantes:
            return jsonify({
                'success': False,
                'message': 'Hay productos inexistentes en la solicitud',
                'faltantes': faltantes
            }), 400

        actualizados = []
        for pid, descuento in descuentos.items():
            disponible = int(stock_map.get(pid, 0))
            nuevo = max(0, disponible - int(descuento))
            supabase.table('productos').update({'cantidad': nuevo}).eq('id_producto', pid).execute()
            actualizados.append({
                'producto_id': pid,
                'nombre': nombre_map.get(pid, pid),
                'anterior': disponible,
                'descontado': int(descuento),
                'nuevo': nuevo
            })

        return jsonify({
            'success': True,
            'message': 'Stock actualizado correctamente',
            'actualizados': actualizados
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@barra_progreso_api.route('/api/barra_progreso/servicio/<cliente_id>', methods=['GET'])
def barra_progreso_servicio(cliente_id):
    """Devuelve barra de progreso para servicios del cliente."""
    try:
        ventas_res = supabase.table('venta') \
            .select('carrito_id, tipo_venta_id, fecha_venta') \
            .eq('cliente_id', cliente_id) \
            .order('fecha_venta', desc=True) \
            .execute()

        carrito_ids = []
        seen = set()
        for row in (ventas_res.data or []):
            tipo_venta_id = str(row.get('tipo_venta_id') or '').strip()
            # Servicio: cualquier tipo_venta distinto al de producto.
            if not tipo_venta_id or tipo_venta_id == TIPO_VENTA_ID_PRODUCTO:
                continue
            cid = row.get('carrito_id')
            if not cid or cid in seen:
                continue
            seen.add(cid)
            carrito_ids.append(cid)

        if not carrito_ids:
            return jsonify({
                'success': True,
                'progreso': 0,
                'estado': None,
                'mostrar_barra': False,
                'items': []
            }), 200

        servicio_res = supabase.table('carrito_compras') \
            .select('*') \
            .in_('id_carrito', carrito_ids) \
            .execute()

        servicios = servicio_res.data or []
        estados_activos = {
            'inicio', 'realizando', 'instalacion', 'instalado',
            'en proceso', 'proceso', 'entregado', 'finalizado', 'completado', 'listo'
        }
        servicios_activos = [
            s for s in servicios
            if (s.get('estado') or '').strip().lower() in estados_activos
        ]

        if not servicios_activos:
            return jsonify({
                'success': True,
                'progreso': 0,
                'estado': None,
                'mostrar_barra': False,
                'items': []
            }), 200

        items = []
        for servicio in servicios_activos:
            estado_barra, progreso = _map_estado_servicio(servicio.get('estado'))
            items.append({
                'carrito_id': servicio.get('id_carrito'),
                'estado': estado_barra,
                'progreso': progreso,
                'mostrar_barra': True
            })

        principal = items[0]

        return jsonify({
            'success': True,
            'progreso': principal.get('progreso'),
            'estado': principal.get('estado'),
            'mostrar_barra': principal.get('mostrar_barra'),
            'carrito_id': principal.get('carrito_id'),
            'items': items
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@barra_progreso_api.route('/prueba_barra_progreso')
def prueba_barra_progreso():
    """Renderiza la página de prueba de la barra de progreso"""
    return render_template('prueba_barra_progreso.html')

@barra_progreso_api.route('/api/clientes/buscar_por_correo', methods=['POST'])
def buscar_cliente_por_correo():
    """Busca un cliente por su correo electrónico"""
    try:
        data = request.get_json()
        correo = data.get('correo')
        
        if not correo:
            return jsonify({'success': False, 'message': 'Correo no proporcionado'}), 400
            
        # Buscar el cliente por correo
        cliente_res = supabase.table('cliente').select('*').eq('correo', correo).execute()
        print(f"[DEBUG] Buscando cliente con correo {correo}:", cliente_res.data)
        
        if not cliente_res.data:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404
            
        return jsonify({
            'success': True,
            'cliente': cliente_res.data[0]
        })
    except Exception as e:
        print(f"[ERROR] Error al buscar cliente por correo: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@barra_progreso_api.route('/api/barra_progreso/<cliente_id>', methods=['GET'])
def barra_progreso(cliente_id):
    """
    Devuelve el estado de progreso basado en la tabla carrito_compras.
    Busca si existe un carrito del cliente con estado 'inicio', 'en proceso' o 'listo'.
    """
    try:
        _dbg(f"\n{'='*80}")
        _dbg(f"[DEBUG barra_progreso] Llamado para cliente_id: {cliente_id}")
        
        # Buscar carritos del cliente desde la tabla venta (modelo nuevo)
        ventas_res = supabase.table('venta') \
            .select('carrito_id, tipo_venta_id, fecha_venta') \
            .eq('cliente_id', cliente_id) \
            .order('fecha_venta', desc=True) \
            .execute()

        carrito_ids = []
        seen = set()
        for row in (ventas_res.data or []):
            tipo_venta_id = str(row.get('tipo_venta_id') or '').strip()
            # Pedido: solo ventas de tipo producto.
            if tipo_venta_id != TIPO_VENTA_ID_PRODUCTO:
                continue
            cid = row.get('carrito_id')
            if not cid or cid in seen:
                continue
            seen.add(cid)
            carrito_ids.append(cid)

        if not carrito_ids:
            _dbg("[DEBUG barra_progreso] No hay ventas con carrito para este cliente")
            return jsonify({
                'success': True,
                'progreso': 0,
                'estado': None,
                'mostrar_barra': False,
                'items': []
            })

        carrito_res = supabase.table('carrito_compras') \
            .select('*') \
            .in_('id_carrito', carrito_ids) \
            .execute()
        
        _dbg(f"[DEBUG barra_progreso] Carritos encontrados: {len(carrito_res.data) if carrito_res.data else 0}")
        
        # Mostrar TODOS los carritos con sus estados
        if carrito_res.data:
            for idx, c in enumerate(carrito_res.data):
                _dbg(f"  Carrito {idx+1}:")
                _dbg(f"    - id_carrito: {c.get('id_carrito')}")
                _dbg(f"    - estado: '{c.get('estado')}' (tipo: {type(c.get('estado'))})")
                _dbg(f"    - estado repr: {repr(c.get('estado'))}")
        
        # Filtrar carritos de pedido con estados activos (excluye seguimiento de servicio)
        carritos_activos = []
        if carrito_res.data:
            for c in carrito_res.data:
                estado = (c.get('estado') or '').strip().lower()
                nombre = (c.get('nombre') or '').strip().lower()
                _dbg(f"[DEBUG barra_progreso] Estado normalizado: '{estado}'")
                if 'servicio' in nombre:
                    continue
                if estado in ['inicio', 'en proceso', 'listo', 'entregado']:
                    carritos_activos.append(c)
                    _dbg(f"  ✓ Carrito {c.get('id_carrito')} agregado (estado: {estado})")
        
        _dbg(f"[DEBUG barra_progreso] Carritos activos: {len(carritos_activos)}")
        _dbg(f"{'='*80}\n")
        
        # Si existe al menos un carrito activo, devolver todos y mantener compatibilidad con el primero
        if carritos_activos:
            items = []
            for carrito in carritos_activos:
                estado_barra, progreso = _map_estado_pedido(carrito.get('estado'))
                items.append({
                    'carrito_id': carrito.get('id_carrito'),
                    'estado': estado_barra,
                    'progreso': progreso,
                    'mostrar_barra': True
                })

            principal = items[0]
            _dbg(f"[DEBUG] Estado principal determinado: {principal.get('estado')}, Progreso: {principal.get('progreso')}")

            return jsonify({
                'success': True,
                'progreso': principal.get('progreso'),
                'estado': principal.get('estado'),
                'mostrar_barra': principal.get('mostrar_barra'),
                'carrito_id': principal.get('carrito_id'),
                'items': items
            })
        
        # Si no existe carrito activo, no mostrar barra
        _dbg(f"[DEBUG] No hay carritos activos para mostrar")
        return jsonify({
            'success': True,
            'progreso': 0,
            'estado': None,
            'mostrar_barra': False,
            'items': []
        })
            
    except Exception as e:
        print(f"[ERROR] Error en barra_progreso: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@barra_progreso_api.route('/api/barra_progreso/servicio/finalizar', methods=['POST'])
def finalizar_servicio():
    """
    Finaliza un servicio: guarda en tabla servicio, sube foto a storage, elimina cortes/carrito/notificación.
    Espera form-data con: carrito_id, cliente_id, nombre_servicio, descripcion, foto (file)
    """
    try:
        print("\n" + "="*80)
        print("[ENDPOINT] POST /api/barra_progreso/servicio/finalizar")
        
        # Obtener datos del formulario
        carrito_id = request.form.get('carrito_id')
        cliente_id = request.form.get('cliente_id')
        notif_id = request.form.get('notif_id')
        cleanup_mode = (request.form.get('cleanup_mode') or 'deferred').strip().lower()
        cleanup_inmediata = cleanup_mode == 'immediate'
        nombre_servicio = request.form.get('nombre_servicio')
        descripcion = request.form.get('descripcion')
        archivo_foto = request.files.get('foto')
        
        print(f"[DEBUG] Datos recibidos:")
        print(f"  - carrito_id: {carrito_id}")
        print(f"  - cliente_id: {cliente_id}")
        print(f"  - notif_id: {notif_id}")
        print(f"  - cleanup_mode: {cleanup_mode}")
        print(f"  - nombre_servicio: {nombre_servicio}")
        print(f"  - descripcion: {descripcion[:50] if descripcion else None}...")
        print(f"  - archivo_foto: {archivo_foto.filename if archivo_foto else None}")
        
        # Validaciones básicas
        if not cliente_id:
            print("[ERROR] Falta cliente_id")
            return jsonify({
                'success': False,
                'message': 'cliente_id es requerido'
            }), 400
        
        if not nombre_servicio:
            nombre_servicio = "Servicio sin nombre"
        
        if not descripcion:
            descripcion = "Sin descripción"
        
        if not archivo_foto:
            print("[ERROR] No se proporcionó archivo foto")
            return jsonify({
                'success': False,
                'message': 'La foto es requerida'
            }), 400
        
        print("[DEBUG] Validaciones iniciales OK")
        
        # Llamar servicio para guardar y limpiar
        exito, mensaje, foto_url = guardar_servicio_completado(
            carrito_id=carrito_id,
            cliente_id=cliente_id,
            notif_id=notif_id,
            nombre_servicio=nombre_servicio,
            descripcion=descripcion,
            archivo_foto=archivo_foto,
            cleanup_inmediata=cleanup_inmediata,
        )
        
        print(f"[DEBUG] Resultado de guardar_servicio_completado:")
        print(f"  - exito: {exito}")
        print(f"  - mensaje: {mensaje}")
        print(f"  - foto_url: {foto_url}")
        
        if exito:
            print("[SUCCESS] Servicio guardado correctamente")
            print("="*80 + "\n")
            return jsonify({
                'success': True,
                'message': mensaje,
                'foto_url': foto_url,
                'carrito_id': carrito_id
            }), 200
        else:
            print(f"[FAIL] Error al guardar: {mensaje}")
            print("="*80 + "\n")
            return jsonify({
                'success': False,
                'message': mensaje,
                'foto_url': foto_url
            }), 400
    
    except Exception as e:
        print(f"[ERROR] Excepción en finalizar_servicio: {str(e)}")
        import traceback
        traceback.print_exc()
        print("="*80 + "\n")
        return jsonify({
            'success': False,
            'message': f'Error interno: {str(e)}'
        }), 500


@barra_progreso_api.route('/api/carrito/<carrito_id>', methods=['GET'])
def obtener_carrito_info(carrito_id):
    """Obtiene información del carrito incluyendo cliente_id."""
    try:
        print(f"[CARRITO INFO] Buscando carrito: {carrito_id}")
        result = supabase.table('carrito_compras').select('*').eq('id_carrito', carrito_id).limit(1).execute()
        
        if result and result.data:
            carrito = result.data[0]
            print(f"[CARRITO INFO] ✓ Carrito encontrado")
            return jsonify({
                'success': True,
                'data': {
                    'id_carrito': carrito.get('id_carrito'),
                    'cliente_id': carrito.get('cliente_id'),
                    'estado': carrito.get('estado')
                }
            }), 200
        else:
            print(f"[CARRITO INFO] Carrito no encontrado")
            return jsonify({
                'success': False,
                'message': 'Carrito no encontrado'
            }), 404
    except Exception as e:
        print(f"[ERROR] Error en obtener_carrito_info: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@barra_progreso_api.route('/api/cliente/buscar', methods=['GET'])
def buscar_cliente():
    """Busca cliente por nombre."""
    try:
        nombre = request.args.get('nombre', '').strip()
        if not nombre:
            return jsonify({
                'success': False,
                'message': 'Parámetro nombre requerido'
            }), 400
        
        print(f"[CLIENTE BUSCAR] Buscando cliente: {nombre}")
        
        # Intenta búsqueda exacta primero
        result = supabase.table('cliente').select('id_cliente, nombre, correo').eq('nombre', nombre).limit(1).execute()
        
        if result and result.data:
            cliente = result.data[0]
            print(f"[CLIENTE BUSCAR] ✓ Cliente encontrado (búsqueda exacta)")
            return jsonify({
                'success': True,
                'data': {
                    'id_cliente': cliente.get('id_cliente'),
                    'nombre': cliente.get('nombre'),
                    'correo': cliente.get('correo')
                }
            }), 200
        
        # Intenta búsqueda parcial si no encuentra exacta
        print(f"[CLIENTE BUSCAR] No encontrado en búsqueda exacta, intentando parcial...")
        result = supabase.table('cliente').select('id_cliente, nombre, correo').ilike('nombre', f"%{nombre}%").limit(5).execute()
        
        if result and result.data:
            clientes = result.data
            print(f"[CLIENTE BUSCAR] ✓ {len(clientes)} cliente(s) encontrado(s) (búsqueda parcial)")
            return jsonify({
                'success': True,
                'data': [{
                    'id_cliente': c.get('id_cliente'),
                    'nombre': c.get('nombre'),
                    'correo': c.get('correo')
                } for c in clientes]
            }), 200
        
        print(f"[CLIENTE BUSCAR] Cliente no encontrado")
        return jsonify({
            'success': False,
            'message': 'Cliente no encontrado'
        }), 404
    except Exception as e:
        print(f"[ERROR] Error en buscar_cliente: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


