# -*- coding: utf-8 -*-
"""
Controlador de pagos con Mercado Pago
"""




from flask import Blueprint, request, jsonify
from datetime import date
from app.services.mercado_pago_service import mercado_pago_service
from app.services.cortes_service import calcular_total_corte, es_material_aluminio
from app.services.supabase_client import supabase
from app.controllers.clientes_controller import verify_jwt
import uuid




pagos_mp_bp = Blueprint("pagos_mp", __name__)
bp = pagos_mp_bp  # alias para auto-registro del factory

# IDs fijos de negocio para el nuevo flujo
DEFAULT_CARRITO_ID = "2ca0f029-e8b0-4f8a-8e5e-e2ac279f957d"
DEFAULT_TIPO_VENTA_ID_PRODUCTO = "1397cefc-c5da-42bc-be75-a3ac36a2266d"
DEFAULT_ESTADO_NOTIFICACION_ID = "62369650-3a4f-4f99-9968-d4d27ae6de16"








def _to_positive_int(value, default=1):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default








def _to_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        if isinstance(value, str):
            value = value.strip().replace(',', '.')
            if not value:
                return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _resolver_producto_id_payload(prod):
    if not isinstance(prod, dict):
        return None
    pid = prod.get("producto_id") or prod.get("id_producto") or prod.get("id")
    if pid is None:
        return None
    pid = str(pid).strip()
    return pid if pid else None


def _normalizar_productos_payload(productos):
    normalizados = []
    omitidos = 0
    for prod in (productos or []):
        if not isinstance(prod, dict):
            omitidos += 1
            continue
        pid = _resolver_producto_id_payload(prod)
        if not pid:
            omitidos += 1
            continue
        prod_norm = dict(prod)
        prod_norm["producto_id"] = pid
        normalizados.append(prod_norm)
    return normalizados, omitidos








def _build_stock_deltas(productos):
    """Construye el descuento por producto considerando plancha + cortes."""
    deltas = {}
    for prod in productos or []:
        producto_id = _resolver_producto_id_payload(prod)
        if not producto_id:
            continue




        tipo_venta = (prod.get("tipo_venta") or "plancha").lower()
        if tipo_venta == "corte":
            cortes_arr = prod.get("cortes", []) or []
            total_cortes = sum(_to_positive_int(c.get("cantidad"), 1) for c in cortes_arr)
            if total_cortes > 0:
                deltas[producto_id] = deltas.get(producto_id, 0) + total_cortes
        else:
            qty = _to_positive_int(prod.get("cantidad"), 1)
            deltas[producto_id] = deltas.get(producto_id, 0) + qty
    return deltas








def _validar_stock_disponible(stock_deltas):
    if not stock_deltas:
        return True, [], {}




    producto_ids = list(stock_deltas.keys())
    productos_res = supabase.table("productos") \
        .select("id_producto, nombre, cantidad") \
        .in_("id_producto", producto_ids) \
        .execute()




    stock_map = {}
    for p in (productos_res.data or []):
        pid = str(p.get("id_producto") or "")
        if not pid:
            continue
        stock_map[pid] = _to_positive_int(p.get("cantidad"), 0)




    faltantes = []
    for pid, qty in stock_deltas.items():
        disponible = stock_map.get(pid, 0)
        if disponible < qty:
            faltantes.append({
                "producto_id": pid,
                "solicitado": qty,
                "disponible": disponible,
            })




    return len(faltantes) == 0, faltantes, stock_map








def _descontar_stock_productos(stock_deltas, stock_map):
    print(f"[pagos_mp] iniciar descuento stock_deltas={stock_deltas}", flush=True)
    descuentos = []
    for pid, qty in stock_deltas.items():
        actual = _to_positive_int(stock_map.get(pid), 0)
        nuevo = max(actual - qty, 0)
        supabase.table("productos").update({"cantidad": nuevo}).eq("id_producto", pid).execute()
        print(
            f"[pagos_mp] stock producto_id={pid} antes={actual} descontado={qty} despues={nuevo}",
            flush=True,
        )
        descuentos.append({
            "producto_id": pid,
            "antes": actual,
            "descontado": qty,
            "despues": nuevo,
        })

    # Notificar a Flutter via Pusher (no bloquea si falla)
    try:
        from app.services.pusher_service import notificar_stock_actualizado
        pids = [d["producto_id"] for d in descuentos if d["producto_id"]]
        if pids:
            prods_res = supabase.table("productos").select("id_producto, nombre, codigo, IMG_P") \
                .in_("id_producto", pids).execute()
            nombre_map = {
                str(p["id_producto"]): (p.get("nombre", ""), p.get("codigo"), p.get("IMG_P"))
                for p in (prods_res.data or [])
            }
            for d in descuentos:
                nombre, codigo, imagen_url = nombre_map.get(str(d["producto_id"]), ("", None, None))
                notificar_stock_actualizado(str(d["producto_id"]), nombre, d["despues"], d["antes"], codigo, imagen_url)
            print(f"[pagos_mp] pusher eventos enviados={len(descuentos)}", flush=True)
    except Exception as _pe:
        print(f"[pagos_mp] Pusher omitido: {_pe}", flush=True)

    return descuentos








def _build_productos_catalogo(productos):
    producto_ids = list({
        _resolver_producto_id_payload(prod)
        for prod in (productos or [])
        if _resolver_producto_id_payload(prod)
    })
    if not producto_ids:
        return {}




    productos_res = supabase.table("productos") \
        .select("*") \
        .in_("id_producto", producto_ids) \
        .execute()




    return {
        str(row.get("id_producto")): row
        for row in (productos_res.data or [])
        if row.get("id_producto")
    }








def _build_wallet_items_from_request(raw_items):
    items = []
    total = 0.0




    for raw_item in raw_items or []:
        try:
            cantidad = int(raw_item.get("cantidad") or 1)
        except (TypeError, ValueError):
            cantidad = 1




        cantidad = max(cantidad, 1)




        try:
            precio_unitario = float(raw_item.get("precio_unitario") or 0)
        except (TypeError, ValueError):
            precio_unitario = 0.0




        try:
            subtotal = float(raw_item.get("subtotal") or 0)
        except (TypeError, ValueError):
            subtotal = 0.0




        if precio_unitario <= 0 and subtotal > 0:
            precio_unitario = subtotal / cantidad




        if precio_unitario <= 0:
            continue




        nombre = raw_item.get("nombre") or raw_item.get("descripcion") or "Producto VIDRIOBRAS"
        descripcion = raw_item.get("descripcion") or f"Producto VIDRIOBRAS - {raw_item.get('tipo_venta', 'plancha')}"




        items.append({
            "title": nombre,
            "quantity": cantidad,
            "unit_price": round(precio_unitario, 2),
            "currency_id": "PEN",
            "description": descripcion
        })
        total += round(precio_unitario, 2) * cantidad




    return items, round(total, 2)


def _obtener_o_crear_caja_activa() -> str | None:
    """Retorna el id_caja del día actual; si no existe, lo crea."""
    try:
        fecha_hoy = date.today().isoformat()
        caja_res = supabase.table("caja") \
            .select("id_caja") \
            .eq("fecha", fecha_hoy) \
            .limit(1) \
            .execute()
        if caja_res.data:
            return caja_res.data[0].get("id_caja")

        nueva = supabase.table("caja").insert({
            "fecha": fecha_hoy,
            "turno": "diurno",
            "subtotal": 0,
        }).execute()
        row = (nueva.data or [None])[0]
        return (row or {}).get("id_caja")
    except Exception as exc:
        print(f"[CONFIRMAR_COMPRA] WARN No se pudo resolver caja activa: {exc}")
        return None




# --------------------------------------------------
# PROCESAR PAGO TEST (MODO DESARROLLO)
# --------------------------------------------------
@pagos_mp_bp.route("/api/pagos/procesar_pago_test", methods=["POST"])
def procesar_pago_test():
    """
    ENDPOINT PARA DESARROLLO - Simula un pago exitoso sin Mercado Pago real
    Usar esto para probar el flujo completo sin tarjeta real
    """
    try:
        print("[MP_TEST] ===== /api/pagos/procesar_pago_test =====", flush=True)
       
        # Validar JWT
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401




        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        if not payload:
            return jsonify({"success": False, "message": "Token invalido"}), 401




        cliente_id_token = payload.get("sub")




        # Obtener datos
        data = request.get_json() or {}
        carrito_id = data.get("carrito_id")
        cliente_id = data.get("cliente_id")
        amount = data.get("amount")
        payer_email = data.get("payer_email")




        if not carrito_id or not cliente_id or not amount or not payer_email:
            print("[MP_TEST] ERROR Datos incompletos", flush=True)
            return jsonify({
                "success": False,
                "message": "Datos incompletos: carrito_id, cliente_id, amount, payer_email requeridos"
            }), 400




        # Validar que cliente coincida
        if cliente_id != cliente_id_token:
            return jsonify({"success": False, "message": "No autorizado"}), 403




        # SIMULAR PAGO EXITOSO
        payment_id = str(uuid.uuid4())
       
        print(f"[MP_TEST] TEST Simulando pago exitoso", flush=True)
        print(f"[MP_TEST] Cliente: {cliente_id}, Monto: S/ {amount}, Email: {payer_email}", flush=True)
        print(f"[MP_TEST] OK Payment ID simulado: {payment_id}", flush=True)




        return jsonify({
            "success": True,
            "message": "Pago simulado exitosamente (MODO DESARROLLO)",
            "payment_id": payment_id,
            "status": "approved",
            "status_detail": "accredited",
            "amount": amount,
            "userMessage": "Pago Simulado Exitoso!",
            "userDetail": f"ID Pago: {payment_id} (DESARROLLO)"
        }), 200




    except Exception as e:
        print(f"[MP_TEST] ERROR: {e}", flush=True)
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500








# --------------------------------------------------
# CREAR PREFERENCIA DE PAGO
# --------------------------------------------------
@pagos_mp_bp.route("/api/pagos/crear_preferencia", methods=["POST"])
def crear_preferencia():
    try:
        # ---------------- JWT ----------------
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401




        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        if not payload:
            return jsonify({"success": False, "message": "Token invalido"}), 401




        cliente_id_token = payload.get("sub")




        # ---------------- BODY ----------------
        data = request.get_json() or {}
        carrito_id = data.get("carrito_id")
        cliente_id = data.get("cliente_id")
        items_payload = data.get("items") or []




        if not carrito_id or not cliente_id:
            return jsonify({"success": False, "message": "Faltan datos"}), 400




        if cliente_id != cliente_id_token:
            return jsonify({"success": False, "message": "No autorizado"}), 403




        # ---------------- EMAIL CLIENTE ----------------
        # Obtener email real del cliente desde Supabase
        cliente_data = supabase.table("cliente") \
            .select("correo") \
            .eq("id_cliente", cliente_id) \
            .execute().data
       
        if not cliente_data:
            return jsonify({"success": False, "message": "Cliente no encontrado"}), 404
       
        email_cliente = cliente_data[0]["correo"]




        # ---------------- ITEMS ----------------
        if str(carrito_id).startswith('temp_'):
            items, total = _build_wallet_items_from_request(items_payload)
        else:
            ventas_carrito = supabase.table("venta") \
                .select("producto_id, cantidad, monto") \
                .eq("carrito_id", carrito_id) \
                .execute().data or []




            if not ventas_carrito:
                return jsonify({"success": False, "message": "Carrito vacio"}), 400




            producto_ids = [p["producto_id"] for p in ventas_carrito if p.get("producto_id")]




            productos = supabase.table("productos") \
                .select("id_producto, nombre, precio_unitario, codigo") \
                .in_("id_producto", producto_ids) \
                .execute().data or []




            productos_map = {p["id_producto"]: p for p in productos}
            items = []
            total = 0




            for pc in ventas_carrito:
                prod = productos_map.get(pc["producto_id"])
                if not prod:
                    continue




                cantidad = int(pc.get("cantidad") or 0)
                precio = float(prod["precio_unitario"])
                subtotal = float(pc.get("monto") or (cantidad * precio))
                total += subtotal




                items.append({
                    "title": prod["nombre"],
                    "quantity": cantidad,
                    "unit_price": precio,
                    "currency_id": "PEN",
                    "description": f"Codigo: {prod.get('codigo', 'N/A')}"
                })




        if total <= 0:
            return jsonify({"success": False, "message": "Total invalido"}), 400




        # ---------------- MERCADO PAGO ----------------
        resultado = mercado_pago_service.crear_preferencia_pago(
            carrito_id=carrito_id,
            cliente_id=cliente_id,
            items=items,
            email_cliente=email_cliente,
            total=total
        )




        if resultado.get("success"):
            return jsonify({
                "success": True,
                "init_point": resultado["init_point"],
                "preference_id": resultado["preference_id"],
                "total": total
            }), 200




        return jsonify({
            "success": False,
            "message": "Error creando preferencia",
            "details": resultado
        }), 500




    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500








# --------------------------------------------------
# PROCESAR PAGO (CORS OPTIONS FIX)
# --------------------------------------------------
@pagos_mp_bp.route(
    "/api/pagos/procesar_pago",
    methods=["POST", "OPTIONS"]
)
def procesar_pago():
    # -------- PRE-FLIGHT CORS --------
    if request.method == "OPTIONS":
        return "", 200




    try:
        # ---------------- JWT ----------------
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401




        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        if not payload:
            return jsonify({"success": False, "message": "Token invalido"}), 401




        data = request.get_json() or {}




        # ---------------- BODY ----------------
        token_mp = data.get("token")
        carrito_id = data.get("carrito_id")
        cliente_id = data.get("cliente_id")
        amount = data.get("amount")
        payment_method_id = data.get("payment_method_id")
        issuer_id = data.get("issuer_id")
        installments = data.get("installments", 1)
        payer_email = data.get("payer_email")
        payer_identification = data.get("payer_identification") or {}




        if not carrito_id or not cliente_id or not amount or not payment_method_id or not payer_email:
            return jsonify({
                "success": False,
                "message": "Datos incompletos"
            }), 400

        if payment_method_id != "yape" and not token_mp:
            return jsonify({
                "success": False,
                "message": "Token requerido para pagos con tarjeta",
                "error": "token_missing"
            }), 400




        # Validar que el cliente del token coincida
        cliente_id_token = payload.get("sub")
        if cliente_id != cliente_id_token:
            return jsonify({"success": False, "message": "No autorizado"}), 403




        # ---------------- MERCADO PAGO ----------------
        if payment_method_id == "yape":
            resultado = mercado_pago_service.procesar_pago_yape(
                token=token_mp,
                carrito_id=carrito_id,
                cliente_id=cliente_id,
                amount=float(amount),
                payer_email=payer_email,
                payer_identification=payer_identification,
                yape_phone=data.get("yape_phone"),
                yape_otp=data.get("yape_otp")
            )
        else:
            resultado = mercado_pago_service.procesar_pago_con_token(
                token=token_mp,
                carrito_id=carrito_id,
                cliente_id=cliente_id,
                amount=float(amount),
                payment_method_id=payment_method_id,
                issuer_id=issuer_id,
                installments=int(installments),
                payer_email=payer_email,
                payer_identification=payer_identification
            )




        if resultado.get("success"):
            return jsonify({
                "success": True,
                "message": "Pago procesado correctamente",
                "payment_id": resultado.get("payment_id"),
                "status": resultado.get("status"),
                "status_detail": resultado.get("status_detail"),
                "amount": resultado.get("amount")
            }), 200




        return jsonify({
            "success": False,
            "message": resultado.get("message") or "Pago rechazado",
            "error": resultado.get("error") or resultado.get("message"),
            "cause": resultado.get("cause"),
            "status": resultado.get("status")
        }), 400




    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500








# --------------------------------------------------
# CONFIRMAR PAGO Y GUARDAR CARRITO + PRODUCTOS
# --------------------------------------------------
@pagos_mp_bp.route("/api/pagos/confirmar_compra", methods=["POST"])
def confirmar_compra():
    """
    Despues de que el pago es exitoso, este endpoint:
    1. Usa el carrito_id existente
    2. Guarda productos PLANCHA en venta
    3. Guarda productos CORTE en tabla cortes
    4. Crea notificacion de entrega
   
    Body: {
        "carrito_id": "uuid",
        "cliente_id": "uuid",
        "productos": [
            {
                "producto_id": "uuid",
                "cantidad": 2,
                "tipo_venta": "plancha"
            },
            {
                "producto_id": "uuid",
                "tipo_venta": "corte",
                "cortes": [
                    {"ancho_cm": 100, "alto_cm": 200, "cantidad": 1},
                    {"ancho_cm": 150, "alto_cm": 300, "cantidad": 2}
                ]
            }
        ],
        "payment_id": "12345"
    }
    """
    try:
        # Validar JWT
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401




        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        if not payload:
            return jsonify({"success": False, "message": "Token invalido"}), 401




        cliente_id_token = payload.get("sub")




        # Obtener data
        data = request.get_json() or {}
        carrito_id = data.get("carrito_id")
        cliente_id = data.get("cliente_id")
        productos = data.get("productos", [])
        payment_id = data.get("payment_id")




        if not carrito_id or not cliente_id or not productos or not payment_id:
            return jsonify({
                "success": False,
                "message": "Datos incompletos: carrito_id, cliente_id, productos, payment_id requeridos"
            }), 400

        productos, productos_omitidos = _normalizar_productos_payload(productos)
        print(
            f"[CONFIRMAR_COMPRA] productos recibidos={len(data.get('productos', []) or [])} "
            f"normalizados={len(productos)} omitidos={productos_omitidos}",
            flush=True,
        )
        if not productos:
            return jsonify({
                "success": False,
                "message": "No se pudo identificar producto_id en los productos enviados",
            }), 400




        # Validar stock antes de confirmar compra
        stock_deltas = _build_stock_deltas(productos)
        print(f"[CONFIRMAR_COMPRA] stock_deltas={stock_deltas}", flush=True)
        stock_ok, faltantes, stock_map = _validar_stock_disponible(stock_deltas)
        if not stock_ok:
            return jsonify({
                "success": False,
                "message": "Stock insuficiente para completar la compra",
                "stock_faltante": faltantes,
            }), 400




        # Validar que el cliente del token coincida
        if cliente_id != cliente_id_token:
            return jsonify({"success": False, "message": "No autorizado"}), 403

        # Determinar metodo de pago desde el payload para guardarlo en venta
        metodo_pago_raw = str(data.get("metodo_pago") or "").strip().lower()
        payment_method_id = str(data.get("payment_method_id") or data.get("metodo_pago_id") or "").strip().lower()
        payment_id_norm = str(payment_id or "").strip().lower()
        metodo_pago = "por tarjeta"
        if (
            "yape" in payment_method_id or
            "yape" in metodo_pago_raw or
            "yape" in payment_id_norm
        ):
            metodo_pago = "por yape"
        elif (
            "pagoefectivo" in payment_method_id or
            "cash" in payment_method_id or
            "efectivo" in payment_method_id or
            "contado" in payment_method_id or
            "atm" in payment_method_id or
            "efectivo" in metodo_pago_raw or
            "contado" in metodo_pago_raw or
            "manual" in payment_id_norm
        ):
            metodo_pago = "al contado"
        elif (
            "debit" in payment_method_id or
            "credit" in payment_method_id or
            "visa" in payment_method_id or
            "master" in payment_method_id or
            "amex" in payment_method_id or
            "card" in payment_method_id or
            "tarjeta" in metodo_pago_raw
        ):
            metodo_pago = "por tarjeta"
        elif metodo_pago_raw:
            metodo_pago = metodo_pago_raw




        # Regla de negocio: usar carrito fijo para la barra de progreso cliente.
        carrito_id = DEFAULT_CARRITO_ID
        print(f"[CONFIRMAR_COMPRA] Usando carrito fijo de progreso: {carrito_id}")




        # 1. Verificar/Crear carrito si no existe
        try:
            carrito_check = supabase.table("carrito_compras") \
                .select("id_carrito") \
                .eq("id_carrito", carrito_id) \
                .limit(1) \
                .execute()
           
            if not carrito_check.data:
                # Crear nuevo carrito si no existe
                print(f"[CONFIRMAR_COMPRA] Creando carrito: {carrito_id} para cliente: {cliente_id}")
                carrito_data = {
                    "id_carrito": carrito_id,
                    "estado": "inicio",
                    "nombre": "progreso_cliente"
                }
                carrito_insert = supabase.table("carrito_compras").insert(carrito_data).execute()
                print(f"[CONFIRMAR_COMPRA] OK Carrito creado exitosamente")
            else:
                print(f"[CONFIRMAR_COMPRA] Carrito ya existe: {carrito_id}")
                # Asegurar estado visible para barra de seguimiento en compras nuevas
                supabase.table("carrito_compras") \
                    .update({"estado": "inicio"}) \
                    .eq("id_carrito", carrito_id) \
                    .execute()
                print(f"[CONFIRMAR_COMPRA] Estado de carrito actualizado a inicio")
        except Exception as e:
            print(f"[CONFIRMAR_COMPRA] ERROR verificando/creando carrito: {str(e)}")
            return jsonify({
                "success": False,
                "message": f"Error verificando/creando carrito: {str(e)}"
            }), 500




        # 2. Separar productos en PLANCHA y CORTE
        productos_plancha = []
        cortes_personalizados = []
        ventas_creadas = []
        catalogo_productos = _build_productos_catalogo(productos)




        print(f"[CONFIRMAR_COMPRA] Procesando {len(productos)} productos del carrito")
       
        for idx, prod in enumerate(productos):
            producto_id = prod.get("producto_id")
            tipo_venta = prod.get("tipo_venta", "plancha")
            producto_base = catalogo_productos.get(producto_id) or prod or {}
            producto_es_aluminio = es_material_aluminio(producto_base)
           
            print(f"[CONFIRMAR_COMPRA] Producto {idx}: ID={producto_id}, Tipo={tipo_venta}")
           
            if not producto_id:
                print(f"[CONFIRMAR_COMPRA] WARN Producto {idx} sin ID, saltando")
                continue
           
            if tipo_venta == "plancha":
                try:
                    cantidad = int(prod.get("cantidad", 1))
                except (ValueError, TypeError):
                    cantidad = 1
               
                if cantidad <= 0:
                    cantidad = 1
               
                print(f"[CONFIRMAR_COMPRA] OK Plancha: producto_id={producto_id}, cantidad={cantidad}")
                productos_plancha.append({
                    "producto_id": producto_id,
                    "carrito_id": carrito_id,
                    "cantidad": cantidad
                })
           
            elif tipo_venta == "corte":
                cortes_arr = prod.get("cortes", [])
                print(f"[CONFIRMAR_COMPRA] Corte: {len(cortes_arr)} especificaciones")
               
                for corte_idx, corte in enumerate(cortes_arr):
                    # Convertir a float para validacion
                    ancho_cm = _to_float(
                        corte.get("ancho_cm", corte.get("ancho", corte.get("largo_cm", 0))),
                        0.0,
                    )
                    alto_cm = _to_float(
                        corte.get("alto_cm", corte.get("alto", 0)),
                        0.0,
                    )
                   
                    try:
                        cantidad = int(corte.get("cantidad", 1))
                    except (ValueError, TypeError):
                        cantidad = 1
                   
                    # Validaciones por tipo de material
                    if producto_es_aluminio:
                        medida_principal = ancho_cm if ancho_cm > 0 else alto_cm
                        if medida_principal <= 0:
                            print(f"[CONFIRMAR_COMPRA] WARN Corte {corte_idx}: aluminio sin medida valida, saltando")
                            continue
                        ancho_guardado = float(medida_principal)
                        alto_guardado = 0.0
                    else:
                        if ancho_cm <= 0:
                            print(f"[CONFIRMAR_COMPRA] WARN Corte {corte_idx}: ancho_cm <= 0, saltando")
                            continue
                        if alto_cm <= 0:
                            print(f"[CONFIRMAR_COMPRA] WARN Corte {corte_idx}: alto_cm <= 0, saltando")
                            continue
                        ancho_guardado = float(ancho_cm)
                        alto_guardado = float(alto_cm)




                    if cantidad <= 0:
                        cantidad = 1
                   
                    print(f"[CONFIRMAR_COMPRA] OK Corte: {ancho_guardado}x{alto_guardado}cm, cantidad={cantidad}")
                    cortes_personalizados.append({
                        "carrito_id": carrito_id,
                        "producto_id": producto_id,
                        "ancho_cm": ancho_guardado,
                        "alto_cm": alto_guardado,
                        "cantidad": int(cantidad),
                        "estado": "pendiente"
                    })




        # 3. Insertar PLANCHAS en venta (agrupar por producto_id)
        if productos_plancha:
            try:
                # Agrupar por producto_id para sumar cantidades si hay duplicados
                productos_agrupados = {}
                for pp in productos_plancha:
                    prod_id = pp["producto_id"]
                    if prod_id not in productos_agrupados:
                        productos_agrupados[prod_id] = pp
                    else:
                        # Si el mismo producto aparece dos veces, sumar cantidad
                        productos_agrupados[prod_id]["cantidad"] += pp["cantidad"]
               
                productos_plancha_final = list(productos_agrupados.values())
                print(f"[CONFIRMAR_COMPRA] Insertando {len(productos_plancha_final)} productos plancha unicos")

                ventas_payload = []
                for pp in productos_plancha_final:
                    prod_id = pp["producto_id"]
                    cantidad = int(pp.get("cantidad") or 1)
                    prod_info = supabase.table("productos") \
                        .select("precio_unitario") \
                        .eq("id_producto", prod_id) \
                        .limit(1) \
                        .execute()
                    precio = 0.0
                    if prod_info and prod_info.data:
                        precio = float(prod_info.data[0].get("precio_unitario", 0) or 0)

                    ventas_payload.append({
                        "cliente_id": cliente_id,
                        "producto_id": prod_id,
                        "carrito_id": carrito_id,
                        "cantidad": cantidad,
                        "monto": round(precio * cantidad, 2),
                        "metodo": metodo_pago,
                        "tipo_venta_id": DEFAULT_TIPO_VENTA_ID_PRODUCTO,
                        "fecha_venta": date.today().isoformat(),
                    })

                if ventas_payload:
                    insert_res = supabase.table("venta").insert(ventas_payload).execute()
                    ventas_creadas.extend(insert_res.data or [])
                print(f"[CONFIRMAR_COMPRA] OK Productos plancha guardados en venta")
            except Exception as e:
                print(f"[CONFIRMAR_COMPRA] ERROR guardando productos plancha: {str(e)}")
                return jsonify({
                    "success": False,
                    "message": f"Error guardando productos plancha en venta: {str(e)}",
                    "carrito_id": carrito_id
                }), 500




        # 4. Insertar CORTES vinculados a venta
        if cortes_personalizados:
            try:
                print(f"[CONFIRMAR_COMPRA] Insertando {len(cortes_personalizados)} cortes")
                cortes_payload_db = []
                for corte in cortes_personalizados:
                    prod_id = corte.get("producto_id")
                    if not prod_id:
                        continue

                    producto_base = catalogo_productos.get(prod_id)
                    if not producto_base:
                        prod_info = supabase.table("productos") \
                            .select("*") \
                            .eq("id_producto", prod_id) \
                            .limit(1) \
                            .execute()
                        if prod_info and prod_info.data:
                            producto_base = prod_info.data[0]
                            catalogo_productos[prod_id] = producto_base

                    precio = float((producto_base or {}).get("precio_unitario", 0) or 0)
                    monto_corte = calcular_total_corte(corte, precio, es_material_aluminio(producto_base or {}))

                    venta_payload_corte = {
                        "cliente_id": cliente_id,
                        "producto_id": prod_id,
                        "carrito_id": carrito_id,
                        "cantidad": 1,
                        "monto": round(float(monto_corte or 0), 2),
                        "metodo": metodo_pago,
                        "tipo_venta_id": DEFAULT_TIPO_VENTA_ID_PRODUCTO,
                        "fecha_venta": date.today().isoformat(),
                    }
                    venta_res = supabase.table("venta").insert(venta_payload_corte).execute()
                    venta_row = (venta_res.data or [None])[0]
                    if not venta_row:
                        continue

                    ventas_creadas.append(venta_row)
                    cortes_payload_db.append({
                        "venta_id": venta_row.get("id_venta"),
                        "ancho_cm": float(corte.get("ancho_cm") or 0),
                        "alto_cm": float(corte.get("alto_cm") or 0),
                        "cantidad": int(corte.get("cantidad") or 1),
                        "estado": "pendiente",
                    })

                if cortes_payload_db:
                    supabase.table("cortes").insert(cortes_payload_db).execute()
                print(f"[CONFIRMAR_COMPRA] OK Cortes guardados")
            except Exception as e:
                print(f"[CONFIRMAR_COMPRA] ERROR guardando cortes: {str(e)}")
                return jsonify({
                    "success": False,
                    "message": f"Error guardando cortes: {str(e)}",
                    "carrito_id": carrito_id
                }), 500




        # 5. Calcular total de la venta desde registros creados en venta
        total_venta = 0.0
        try:
            total_venta = sum(float(v.get("monto") or 0) for v in (ventas_creadas or []))
            print(f"[CONFIRMAR_COMPRA] Total calculado: S/ {total_venta:.2f}")
        except Exception as e:
            print(f"[CONFIRMAR_COMPRA] WARN Error calculando total: {str(e)}")
            total_venta = 0.0




        # 6. El registro de pago (fecha/total/documento) se persiste al generar comprobante.
        registro_pago_id = None




        # 7. Crear notificacion de entrega
        try:
            # Obtener nombre del cliente
            cli = supabase.table("cliente").select("nombre").eq("id_cliente", cliente_id).limit(1).execute()
            nombre_cliente = None
            if cli and cli.data:
                nombre_cliente = cli.data[0].get("nombre")




            total_items = 0
            total_items += sum(pp.get("cantidad", 0) for pp in productos_plancha)
            total_items += sum(c.get("cantidad", 0) for c in cortes_personalizados)




            descripcion = f"Pago {payment_id} - items: {total_items}"
            primera_venta_id = (ventas_creadas[0].get("id_venta") if ventas_creadas else None)
            notif_payload = {
                "nombre": nombre_cliente or "Cliente",
                "descripcion": f"{descripcion} (Carrito: {carrito_id})",
                "estado_notificacion_id": DEFAULT_ESTADO_NOTIFICACION_ID,
                "tipo": "entrega",
                "venta_id": primera_venta_id,
            }
            notif_res = supabase.table("notificacion").insert(notif_payload).execute()
            if not (notif_res.data or []):
                print("[CONFIRMAR_COMPRA] WARN Notificacion no creada")
        except Exception as e:
            # Log pero no fallar
            print(f"[CONFIRMAR_COMPRA] Error creando notificacion: {str(e)}")




        # 8. Descontar stock de productos vendidos (plancha + cortes)
        descuentos_stock = []
        try:
            descuentos_stock = _descontar_stock_productos(stock_deltas, stock_map)
            print(
                f"[CONFIRMAR_COMPRA] OK Stock descontado en {len(descuentos_stock)} producto(s)",
                flush=True,
            )
        except Exception as e:
            print(f"[CONFIRMAR_COMPRA] WARN Error descontando stock: {str(e)}", flush=True)




        return jsonify({
            "success": True,
            "message": "Compra confirmada exitosamente",
            "carrito_id": carrito_id,
            "registro_pago_id": locals().get("registro_pago_id"),
            "productos_plancha_guardados": len(productos_plancha),
            "cortes_guardados": len(cortes_personalizados),
            "venta_registrada": total_venta > 0,
            "stock_descuento": descuentos_stock,
            "stock_deltas": stock_deltas,
        }), 200




    except Exception as e:
        print(f"[ERROR CONFIRMAR_COMPRA] {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error procesando compra: {str(e)}"
        }), 500
