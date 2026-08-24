from services.supabase_client import supabase
from typing import Optional, Dict, Any, List
import uuid
import os
import json
import base64
import hmac
import hashlib
import time
import re

# Constante para tipo de venta de productos
DEFAULT_TIPO_VENTA_ID_PRODUCTO = "1397cefc-c5da-42bc-be75-a3ac36a2266d"
DEFAULT_ESTADO_NOTIFICACION_ID = "62369650-3a4f-4f99-9968-d4d27ae6de16"

# -- JWT helper (para cuentas temporales) --------------------------------------
def _build_jwt_temporal(cliente: dict) -> str:
    """Genera un JWT HS256 para una cuenta temporal de cliente."""
    secret = os.environ.get('JWT_SECRET', 'vidriobras-secret')
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(cliente['id_cliente']),
        "email": cliente.get('correo', ''),
        "name": cliente.get('nombre', ''),
        "exp": int(time.time()) + 7 * 24 * 3600,
        "aud": "cliente"
    }
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')
    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(payload).encode())}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + b64url(sig)


# Buscar cliente por documento

def buscar_cliente_por_documento(documento: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("cliente").select("*").eq("documento", documento).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None


def _es_uuid(valor: str) -> bool:
    try:
        uuid.UUID(str(valor))
        return True
    except Exception:
        return False


def _resolver_producto_uuid(valor: str) -> Optional[str]:
    """
    Acepta UUID o codigo de producto y retorna siempre UUID valido.
    """
    if not valor:
        return None

    if _es_uuid(valor):
        return str(valor)

    try:
        res = supabase.table("productos").select("id_producto").eq("codigo", str(valor)).limit(1).execute()
        if res.data and len(res.data) > 0:
            pid = res.data[0].get("id_producto")
            if pid and _es_uuid(pid):
                return pid
    except Exception:
        return None

    return None


def _descontar_stock_venta(productos_agrupados: Dict[str, float], cortes_payload: List[dict]) -> None:
    """
    Descuenta productos.cantidad por cada producto vendido (planchas + cortes).
    Espeja exactamente lo que el frontend hace de forma optimista en
    aplicarDescuentoStockLocal (CotizacionProductos.jsx): suma por producto_id
    entre productos y cortes, y resta del stock real.
    """
    deltas: Dict[str, float] = {}
    for pid, cantidad in (productos_agrupados or {}).items():
        if not pid:
            continue
        deltas[pid] = deltas.get(pid, 0.0) + float(cantidad or 0)

    for corte in (cortes_payload or []):
        pid = corte.get("producto_id")
        if not pid:
            continue
        deltas[pid] = deltas.get(pid, 0.0) + float(corte.get("cantidad") or 0)

    for pid, cantidad_vendida in deltas.items():
        if cantidad_vendida <= 0:
            continue
        try:
            prod = supabase.table("productos").select("cantidad, nombre, codigo").eq("id_producto", pid).limit(1).execute()
            if not prod.data:
                continue
            producto = prod.data[0]
            actual = float(producto.get("cantidad") or 0)
            nueva = max(0, actual - cantidad_vendida)
            supabase.table("productos").update({"cantidad": nueva}).eq("id_producto", pid).execute()

            # Notificar stock bajo/agotado a la app movil (Pusher + OneSignal),
            # igual que hace el resto de flujos que descuentan stock.
            try:
                from services.pusher_service import notificar_stock_actualizado
                notificar_stock_actualizado(
                    producto_id=str(pid),
                    nombre=producto.get('nombre', ''),
                    cantidad_nueva=int(nueva),
                    cantidad_anterior=int(actual),
                    codigo=producto.get('codigo'),
                )
            except Exception as _pe:
                print(f"[COMPRA_SERVICE] Pusher omitido: {_pe}")
        except Exception as e:
            print(f"[COMPRA_SERVICE] [!] Error descontando stock de {pid}: {str(e)}")


def _limpiar_nombre_cliente(nombre: str, documento: str) -> str:
    """Remueve prefijos tipo '12345678 - Nombre' y deja solo nombre/razon social."""
    base = str(nombre or "").strip()
    if not base:
        return ""

    doc = str(documento or "").strip()
    if doc:
        base = re.sub(rf"^{re.escape(doc)}\s*[-:|]\s*", "", base, flags=re.IGNORECASE)

    base = re.sub(r"^\d{8,11}\s*[-:|]\s*", "", base, flags=re.IGNORECASE)
    return base.strip()


def _slug_nombre_para_correo(nombre: str) -> str:
    """Genera slug de correo solo a partir de letras del nombre."""
    base = (nombre or "").lower().strip()
    reemplazos = str.maketrans({
        "\u00e1": "a", "\u00e9": "e", "\u00ed": "i", "\u00f3": "o", "\u00fa": "u", "\u00f1": "n"
    })
    base = base.translate(reemplazos)
    base = re.sub(r"[^a-z\s]", "", base)
    base = re.sub(r"\s+", "", base)
    return base[:24] or "cliente"


def _guardar_lineas_venta(
    productos_agrupados: Dict[str, float],
    carrito_id: str,
    cliente_id: str,
    metodo_pago: str,
) -> Dict[str, Any]:
    """Guarda líneas de venta (planchas) en la tabla venta y retorna total + id de ventas creadas."""
    total_venta = 0.0
    lineas = []

    for pid, cantidad in (productos_agrupados or {}).items():
        prod_info = supabase.table("productos").select("precio_unitario").eq("id_producto", pid).limit(1).execute()
        if not prod_info.data:
            continue
        precio = float(prod_info.data[0].get("precio_unitario", 0) or 0)
        monto = round(precio * float(cantidad or 0), 2)
        total_venta += monto
        lineas.append({
            "cliente_id": cliente_id,
            "producto_id": pid,
            "carrito_id": carrito_id,
            "cantidad": float(cantidad or 0),
            "monto": monto,
            "metodo": metodo_pago,
            "fecha_venta": time.strftime("%Y-%m-%d"),
            "tipo_venta_id": DEFAULT_TIPO_VENTA_ID_PRODUCTO,
        })

    venta_ids = []
    if lineas:
        insert_res = supabase.table("venta").insert(lineas).execute()
        venta_ids = [str(v.get("id_venta")) for v in (insert_res.data or []) if v.get("id_venta")]

    return {
        "total": round(total_venta, 2),
        "venta_ids": venta_ids,
    }


def _guardar_cortes_como_venta(
    cortes_payload: List[dict],
    carrito_id: str,
    cliente_id: str,
    metodo_pago: str,
) -> Dict[str, Any]:
    """
    Crea una venta por cada corte y recién con ese id_venta guarda el corte en
    'cortes' (venta_id es la única FK que tiene esa tabla; ya no existen
    carrito_id/producto_id en 'cortes').
    """
    total_venta = 0.0
    venta_ids = []
    cortes_db = []

    for corte in (cortes_payload or []):
        pid_corte = str(corte.get("producto_id") or "").strip()
        if not pid_corte:
            continue
        prod_info = supabase.table("productos").select("precio_unitario").eq("id_producto", pid_corte).limit(1).execute()
        if not prod_info.data:
            continue
        precio = float(prod_info.data[0].get("precio_unitario", 0) or 0)
        ancho_cm = float(corte.get("ancho_cm") or 0)
        alto_cm = float(corte.get("alto_cm") or 0)
        cantidad = float(corte.get("cantidad") or 1)
        categoria = str(corte.get("_categoria") or "")
        if "ALUMIN" in categoria:
            largo_cm = ancho_cm if ancho_cm > 0 else alto_cm
            monto = (((largo_cm / 100.0) * precio) + 10.0) * cantidad
        elif ancho_cm > 0 and alto_cm > 0:
            monto = (((ancho_cm * alto_cm / 10000.0) * precio) + 10.0) * cantidad
        else:
            monto = precio * cantidad
        monto = round(monto, 2)
        total_venta += monto

        venta_res = supabase.table("venta").insert({
            "cliente_id": cliente_id,
            "producto_id": pid_corte,
            "carrito_id": carrito_id,
            "cantidad": cantidad,
            "monto": monto,
            "metodo": metodo_pago,
            "fecha_venta": time.strftime("%Y-%m-%d"),
            "tipo_venta_id": DEFAULT_TIPO_VENTA_ID_PRODUCTO,
        }).execute()
        venta_row = (venta_res.data or [None])[0]
        if not venta_row or not venta_row.get("id_venta"):
            continue
        venta_ids.append(str(venta_row.get("id_venta")))

        cortes_db.append({
            "venta_id": venta_row.get("id_venta"),
            "ancho_cm": ancho_cm,
            "alto_cm": alto_cm,
            "cantidad": int(cantidad) if cantidad else 1,
            "estado": "pendiente",
            "normbre": corte.get("normbre") or "",
        })

    if cortes_db:
        supabase.table("cortes").insert(cortes_db).execute()

    return {
        "total": round(total_venta, 2),
        "venta_ids": venta_ids,
    }


# Guardar flujo de compra

def guardar_flujo_compra(cliente: Optional[dict], productos: List[dict], cortes: List[dict], metodo_pago: str, documento: str = "", nombre_api_peru: str = "") -> Dict[str, Any]:
    nombres_productos = ", ".join([p["nombre"] for p in productos])
    
    # Determinar metodo de pago normalizado
    metodo_normalizado = "al contado"  # default
    if metodo_pago:
        mp_lower = metodo_pago.lower()
        if "yape" in mp_lower:
            metodo_normalizado = "por yape"
        elif "tarjeta" in mp_lower:
            metodo_normalizado = "por tarjeta"
        else:
            metodo_normalizado = "al contado"
    
    # Si existe cliente
    if cliente:
        # 1. Crear un carrito_compras nuevo por cada compra (una barra de progreso por compra)
        carrito_payload = {
            "estado": "inicio"
        }
        carrito_res = supabase.table("carrito_compras").insert(carrito_payload).execute()
        if not carrito_res.data:
            return False
        id_carrito = carrito_res.data[0]["id_carrito"]
        
        # 2. Consolidar productos para guardarlos luego en venta
        # Consolidar por producto_id para evitar conflicto de PK compuesta
        productos_agrupados = {}
        for p in productos:
            pid = _resolver_producto_uuid(p.get("id_producto"))
            if not pid:
                continue
            cantidad = float(p.get("cantidad") or 0)
            if cantidad <= 0:
                cantidad = 1
            productos_agrupados[pid] = float(productos_agrupados.get(pid, 0)) + cantidad

        # 3. Preparar cortes (se guardan más abajo, enlazados a su venta_id)
        cortes_payload = []
        for c in cortes:
            pid_corte = _resolver_producto_uuid(c.get("producto_id"))
            if not pid_corte:
                continue

            try:
                ancho_cm = float(c.get("ancho_cm") or 0)
            except Exception:
                ancho_cm = 0.0

            try:
                alto_cm = float(c.get("alto_cm") or 0)
            except Exception:
                alto_cm = 0.0

            try:
                cantidad_corte = int(c.get("cantidad") or 1)
            except Exception:
                cantidad_corte = 1

            if cantidad_corte <= 0:
                cantidad_corte = 1

            # Evitar filas basura sin medidas
            if ancho_cm <= 0 and alto_cm <= 0:
                continue

            cortes_payload.append({
                "ancho_cm": ancho_cm,
                "alto_cm": alto_cm,
                "cantidad": cantidad_corte,
                "producto_id": pid_corte,
                "normbre": c.get("nombre", ""),
                "_categoria": str(c.get("categoria") or "").upper(),
            })

        # 4. Guardar líneas de venta: planchas primero, cortes después (cada
        # corte crea su propia venta y recién con ese id_venta se inserta en
        # 'cortes', que solo se relaciona por venta_id).
        try:
            venta_result = _guardar_lineas_venta(
                productos_agrupados=productos_agrupados,
                carrito_id=id_carrito,
                cliente_id=cliente["id_cliente"],
                metodo_pago=metodo_normalizado,
            )
            cortes_result = _guardar_cortes_como_venta(
                cortes_payload=cortes_payload,
                carrito_id=id_carrito,
                cliente_id=cliente["id_cliente"],
                metodo_pago=metodo_normalizado,
            )
            total_venta = venta_result.get("total", 0.0) + cortes_result.get("total", 0.0)
            todas_las_ventas = (venta_result.get("venta_ids") or []) + (cortes_result.get("venta_ids") or [])
            primera_venta_id = todas_las_ventas[0] if todas_las_ventas else None
            print(f"[COMPRA_SERVICE] Total venta: S/ {total_venta:.2f}, Metodo: {metodo_normalizado}")
        except Exception as e:
            print(f"[COMPRA_SERVICE] [!] Error guardando venta: {str(e)}")
            return {"ok": False, "error": str(e)}

        # 5. Crear notificacion vinculada a la venta creada -- solo si de verdad
        # se guardo algo. Si todos los items fueron filtrados (producto_id
        # invalido/inexistente, medidas en 0, etc.) no hay nada que entregar:
        # crear la notificacion igual deja una tarjeta fantasma sin pedidos.
        if not primera_venta_id:
            print(f"[COMPRA_SERVICE] [!] Sin ventas validas, no se crea notificacion (carrito {id_carrito})")
            try:
                supabase.table("carrito_compras").delete().eq("id_carrito", id_carrito).execute()
            except Exception:
                pass
            return {"ok": False, "error": "No se pudo procesar ningun producto/corte valido"}

        _descontar_stock_venta(productos_agrupados, cortes_payload)

        notif_payload = {
            "tipo": "entrega",
            "nombre": cliente["nombre"],
            "descripcion": f"{nombres_productos} (Carrito: {id_carrito})",
            "estado_notificacion_id": DEFAULT_ESTADO_NOTIFICACION_ID,
            "venta_id": primera_venta_id,
        }
        supabase.table("notificacion").insert(notif_payload).execute()

        try:
            from services.notificacion_service import notificar_operacion_creada
            notificar_operacion_creada(
                nombre=cliente["nombre"],
                descripcion=nombres_productos,
                tipo="entrega",
            )
        except Exception as _ne:
            print(f"[COMPRA_SERVICE] Notificacion tiempo real/push omitida: {_ne}")

        return {"ok": True, "cuenta_temporal": False}
    else:
        # Si NO existe cliente
        nombre_limpio = _limpiar_nombre_cliente(nombre_api_peru, documento) or documento
        nombre_completo = nombre_limpio

        # -- Crear / recuperar cuenta temporal ----------------------------------
        nombre_base = _slug_nombre_para_correo(nombre_limpio)
        correo_temp = f"{nombre_base}@vidriobras.com"
        contrasena_temp = documento

        # Evitar colisiones de correo sin usar el documento.
        for i in range(0, 50):
            candidato = correo_temp if i == 0 else f"{nombre_base}{i}@vidriobras.com"
            existente_temp = supabase.table("cliente").select("id_cliente,correo,nombre").eq("correo", candidato).limit(1).execute()
            if existente_temp.data:
                continue
            correo_temp = candidato
            break

        existente_mismo_doc = supabase.table("cliente").select("id_cliente,correo,nombre,cuenta_temporal,registro_completo").eq("documento", documento).limit(1).execute()
        if existente_mismo_doc.data:
            cliente_temp = existente_mismo_doc.data[0]
            correo_existente = str(cliente_temp.get("correo") or "").strip().lower()
            nombre_existente = str(cliente_temp.get("nombre") or "").strip()
            es_temp = bool(cliente_temp.get("cuenta_temporal"))

            update_payload = {}

            # Si la cuenta es temporal, mantener nombre limpio sin prefijo de documento.
            if es_temp and nombre_limpio and nombre_limpio != nombre_existente:
                update_payload["nombre"] = nombre_limpio

            # Si el correo temporal existente trae numeros, lo normalizamos solo con nombre.
            if es_temp and (re.search(r"\d", correo_existente) or not correo_existente.endswith("@vidriobras.com")):
                correo_candidato = f"{nombre_base}@vidriobras.com"
                for i in range(0, 50):
                    candidato = correo_candidato if i == 0 else f"{nombre_base}{i}@vidriobras.com"
                    existe_correo = supabase.table("cliente").select("id_cliente").eq("correo", candidato).limit(1).execute()
                    if existe_correo.data and str(existe_correo.data[0].get("id_cliente")) != str(cliente_temp.get("id_cliente")):
                        continue
                    update_payload["correo"] = candidato
                    break

            if update_payload:
                upd = supabase.table("cliente").update(update_payload).eq("id_cliente", cliente_temp["id_cliente"]).execute()
                if upd.data:
                    cliente_temp = upd.data[0]

            correo_temp = str(cliente_temp.get("correo") or correo_temp)
        else:
            nuevo_temp = supabase.table("cliente").insert({
                "correo": correo_temp,
                "contrase\u00f1a": contrasena_temp,
                "nombre": nombre_limpio,
                "documento": documento,
                "cuenta_temporal": True,
                "registro_completo": False,
            }).execute()
            if not nuevo_temp.data:
                return {"ok": False}
            cliente_temp = nuevo_temp.data[0]

        jwt_temp = _build_jwt_temporal(cliente_temp)
        # -----------------------------------------------------------------------

        # 1. Crear carrito_compras (sin cliente_id, ese dato va en venta)
        carrito_payload = {
            "estado": "inicio"
        }
        carrito_res = supabase.table("carrito_compras").insert(carrito_payload).execute()
        if not carrito_res.data:
            return False
        id_carrito = carrito_res.data[0]["id_carrito"]
        # 2. Consolidar productos para guardarlos luego en venta
        # Consolidar por producto_id para evitar conflicto de PK compuesta
        productos_agrupados = {}
        for p in productos:
            pid = _resolver_producto_uuid(p.get("id_producto"))
            if not pid:
                continue
            cantidad = float(p.get("cantidad") or 0)
            if cantidad <= 0:
                cantidad = 1
            productos_agrupados[pid] = float(productos_agrupados.get(pid, 0)) + cantidad

        # 3. Preparar cortes (se guardan más abajo, enlazados a su venta_id)
        cortes_payload = []
        for c in cortes:
            pid_corte = _resolver_producto_uuid(c.get("producto_id"))
            if not pid_corte:
                continue

            try:
                ancho_cm = float(c.get("ancho_cm") or 0)
            except Exception:
                ancho_cm = 0.0

            try:
                alto_cm = float(c.get("alto_cm") or 0)
            except Exception:
                alto_cm = 0.0

            try:
                cantidad_corte = int(c.get("cantidad") or 1)
            except Exception:
                cantidad_corte = 1

            if cantidad_corte <= 0:
                cantidad_corte = 1

            if ancho_cm <= 0 and alto_cm <= 0:
                continue

            cortes_payload.append({
                "ancho_cm": ancho_cm,
                "alto_cm": alto_cm,
                "cantidad": cantidad_corte,
                "producto_id": pid_corte,
                "normbre": nombre_completo,
                "_categoria": str(c.get("categoria") or "").upper(),
            })

        # 4. Guardar líneas de venta: planchas primero, cortes después (cada
        # corte crea su propia venta y recién con ese id_venta se inserta en
        # 'cortes', que solo se relaciona por venta_id).
        try:
            venta_result = _guardar_lineas_venta(
                productos_agrupados=productos_agrupados,
                carrito_id=id_carrito,
                cliente_id=cliente_temp["id_cliente"],
                metodo_pago=metodo_normalizado,
            )
            cortes_result = _guardar_cortes_como_venta(
                cortes_payload=cortes_payload,
                carrito_id=id_carrito,
                cliente_id=cliente_temp["id_cliente"],
                metodo_pago=metodo_normalizado,
            )
            total_venta = venta_result.get("total", 0.0) + cortes_result.get("total", 0.0)
            todas_las_ventas = (venta_result.get("venta_ids") or []) + (cortes_result.get("venta_ids") or [])
            primera_venta_id = todas_las_ventas[0] if todas_las_ventas else None
            print(f"[COMPRA_SERVICE] Total venta: S/ {total_venta:.2f}, Metodo: {metodo_normalizado}")
        except Exception as e:
            print(f"[COMPRA_SERVICE] [!] Error guardando venta: {str(e)}")
            return {"ok": False, "error": str(e)}

        # 5. Crear notificacion vinculada a la venta creada -- solo si de verdad
        # se guardo algo (ver comentario equivalente en la rama de cliente existente).
        if not primera_venta_id:
            print(f"[COMPRA_SERVICE] [!] Sin ventas validas, no se crea notificacion (carrito {id_carrito})")
            try:
                supabase.table("carrito_compras").delete().eq("id_carrito", id_carrito).execute()
            except Exception:
                pass
            return {"ok": False, "error": "No se pudo procesar ningun producto/corte valido"}

        _descontar_stock_venta(productos_agrupados, cortes_payload)

        notif_payload = {
            "tipo": "entrega",
            "nombre": nombre_completo,
            "descripcion": f"{nombres_productos} (Carrito: {id_carrito})",
            "estado_notificacion_id": DEFAULT_ESTADO_NOTIFICACION_ID,
            "venta_id": primera_venta_id,
        }
        supabase.table("notificacion").insert(notif_payload).execute()

        try:
            from services.notificacion_service import notificar_operacion_creada
            notificar_operacion_creada(
                nombre=nombre_completo,
                descripcion=nombres_productos,
                tipo="entrega",
            )
        except Exception as _ne:
            print(f"[COMPRA_SERVICE] Notificacion tiempo real/push omitida: {_ne}")

        return {
            "ok": True,
            "cuenta_temporal": True,
            "correo_temporal": correo_temp,
            "contrasena_temporal": contrasena_temp,
            "jwt_temporal": jwt_temp,
            "cliente_id": str(cliente_temp["id_cliente"])
        }
