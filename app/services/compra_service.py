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


def _descontar_stock_productos(productos_agrupados: Dict[str, float], cortes_payload: List[dict]) -> None:
    """Descuenta stock real de la tabla productos para compras normales y cortes."""
    descuentos = {}

    for pid, cantidad in (productos_agrupados or {}).items():
        try:
            descuentos[pid] = int(descuentos.get(pid, 0)) + int(float(cantidad or 0))
        except Exception:
            continue

    for corte in (cortes_payload or []):
        pid = str(corte.get("producto_id") or "").strip()
        if not pid:
            continue
        try:
            cantidad_corte = int(float(corte.get("cantidad") or 0))
        except Exception:
            cantidad_corte = 0
        if cantidad_corte > 0:
            descuentos[pid] = int(descuentos.get(pid, 0)) + cantidad_corte

    if not descuentos:
        return

    producto_ids = list(descuentos.keys())
    productos_res = supabase.table("productos").select("id_producto, cantidad").in_("id_producto", producto_ids).execute()
    stock_map = {}
    for p in (productos_res.data or []):
        pid = str(p.get("id_producto") or "")
        if not pid:
            continue
        try:
            stock_map[pid] = int(float(p.get("cantidad") or 0))
        except Exception:
            stock_map[pid] = 0

    for pid, descuento in descuentos.items():
        disponible = int(stock_map.get(pid, 0))
        if disponible < int(descuento):
            raise ValueError(f"Stock insuficiente para producto {pid}: disponible {disponible}, solicitado {descuento}")

    stock_nuevos: dict = {}
    for pid, descuento in descuentos.items():
        if descuento <= 0:
            continue
        try:
            actual = int(stock_map.get(pid, 0))
            nuevo = max(0, actual - int(descuento))
            supabase.table("productos").update({"cantidad": nuevo}).eq("id_producto", pid).execute()
            stock_nuevos[pid] = (nuevo, actual)
        except Exception as e:
            print(f"[COMPRA_SERVICE] [!] Error descontando stock de {pid}: {str(e)}")
            raise

    # -- Notificar a Flutter via Pusher (no bloquea si falla) --
    try:
        from app.services.pusher_service import notificar_stock_actualizado
        pids = list(stock_nuevos.keys())
        if pids:
            prods_res = supabase.table("productos").select("id_producto, nombre, codigo, IMG_P") \
                .in_("id_producto", pids).execute()
            nombre_map = {
                str(p["id_producto"]): (p.get("nombre", ""), p.get("codigo"), p.get("IMG_P"))
                for p in (prods_res.data or [])
            }
            for pid, (nuevo, anterior) in stock_nuevos.items():
                nombre, codigo, imagen_url = nombre_map.get(pid, ("", None, None))
                notificar_stock_actualizado(pid, nombre, nuevo, anterior, codigo, imagen_url)
    except Exception as _pe:
        print(f"[COMPRA_SERVICE] Pusher omitido: {_pe}")

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
        # 1. Crear carrito_compras
        carrito_payload = {
            "estado": "inicio",
            "cliente_id": cliente["id_cliente"]
        }
        carrito_res = supabase.table("carrito_compras").insert(carrito_payload).execute()
        if not carrito_res.data:
            return False
        id_carrito = carrito_res.data[0]["id_carrito"]
        
        # 2. Guardar productos en productos_carrito
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

        productos_payload = [
            {
                "producto_id": pid,
                "carrito_id": id_carrito,
                "cantidad": cant
            }
            for pid, cant in productos_agrupados.items()
        ]
        if productos_payload:
            supabase.table("productos_carrito").insert(productos_payload).execute()
        
        # 3. Guardar cortes en cortes
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
                "carrito_id": id_carrito,
                "producto_id": pid_corte,
                "normbre": c.get("nombre", ""),
                "_categoria": str(c.get("categoria") or "").upper(),
            })
        if cortes_payload:
            db_cortes = [{k: v for k, v in c.items() if not k.startswith('_')} for c in cortes_payload]
            supabase.table("cortes").insert(db_cortes).execute()

        _descontar_stock_productos(productos_agrupados, cortes_payload)
        
        # 4. Crear notificacion
        notif_payload = {
            "tipo": "entrega",
            "nombre": cliente["nombre"],
            "descripcion": f"{nombres_productos} (Carrito: {id_carrito})",
            "id_cliente": cliente["id_cliente"]
        }
        supabase.table("notificacion").insert(notif_payload).execute()
        
        # 5. Calcular total y registrar venta
        try:
            from services.venta_service import registrar_venta
            
            total_venta = 0.0
            
            # Sumar productos
            for pid, cantidad in productos_agrupados.items():
                prod_info = supabase.table("productos").select("precio_unitario").eq("id_producto", pid).limit(1).execute()
                if prod_info and prod_info.data:
                    precio = float(prod_info.data[0].get("precio_unitario", 0))
                    total_venta += precio * cantidad
            
            # Sumar cortes (precio por area: igual formula que frontend)
            COSTO_CORTE = 10.0
            for corte in cortes_payload:
                pid_corte = corte["producto_id"]
                cantidad_corte = corte["cantidad"]
                ancho_cm = corte["ancho_cm"]
                alto_cm = corte["alto_cm"]
                categoria_corte = corte.get("_categoria", "")

                prod_info = supabase.table("productos").select("precio_unitario").eq("id_producto", pid_corte).limit(1).execute()
                if prod_info and prod_info.data:
                    precio = float(prod_info.data[0].get("precio_unitario", 0))
                    if "ALUMIN" in categoria_corte:
                        largo_cm = ancho_cm if ancho_cm > 0 else alto_cm
                        precio_pieza = ((largo_cm / 100.0) * precio) + COSTO_CORTE
                    elif ancho_cm > 0 and alto_cm > 0:
                        precio_pieza = ((ancho_cm * alto_cm / 10000.0) * precio) + COSTO_CORTE
                    else:
                        precio_pieza = precio
                    total_venta += precio_pieza * cantidad_corte

            print(f"[COMPRA_SERVICE] Total venta: S/ {total_venta:.2f}, Metodo: {metodo_normalizado}")
            
            if total_venta > 0:
                registrar_venta(total=total_venta, metodo=metodo_normalizado, caja_id=None)
                print(f"[COMPRA_SERVICE] [OK] Venta registrada")
        except Exception as e:
            print(f"[COMPRA_SERVICE] [!] Error registrando venta: {str(e)}")

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

        # 1. Crear carrito_compras (vinculado a cuenta temporal)
        carrito_payload = {
            "estado": "inicio",
            "cliente_id": cliente_temp["id_cliente"],
            "nombre": nombre_completo
        }
        carrito_res = supabase.table("carrito_compras").insert(carrito_payload).execute()
        if not carrito_res.data:
            return False
        id_carrito = carrito_res.data[0]["id_carrito"]
        # 2. Guardar productos en productos_carrito
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

        productos_payload = [
            {
                "producto_id": pid,
                "carrito_id": id_carrito,
                "cantidad": cant
            }
            for pid, cant in productos_agrupados.items()
        ]
        if productos_payload:
            supabase.table("productos_carrito").insert(productos_payload).execute()
        # 3. Guardar cortes en cortes (nombre especial)
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
                "carrito_id": id_carrito,
                "producto_id": pid_corte,
                "normbre": nombre_completo,
                "_categoria": str(c.get("categoria") or "").upper(),
            })
        if cortes_payload:
            db_cortes = [{k: v for k, v in c.items() if not k.startswith('_')} for c in cortes_payload]
            supabase.table("cortes").insert(db_cortes).execute()

        _descontar_stock_productos(productos_agrupados, cortes_payload)
        # 4. Crear notificacion (nombre especial)
        notif_payload = {
            "tipo": "entrega",
            "nombre": nombre_completo,
            "descripcion": f"{nombres_productos} (Carrito: {id_carrito})",
            "id_cliente": cliente_temp["id_cliente"]
        }
        supabase.table("notificacion").insert(notif_payload).execute()
        
        # 5. Calcular total y registrar venta
        try:
            from services.venta_service import registrar_venta
            
            total_venta = 0.0
            
            # Sumar productos
            for pid, cantidad in productos_agrupados.items():
                prod_info = supabase.table("productos").select("precio_unitario").eq("id_producto", pid).limit(1).execute()
                if prod_info and prod_info.data:
                    precio = float(prod_info.data[0].get("precio_unitario", 0))
                    total_venta += precio * cantidad
            
            # Sumar cortes (precio por area: igual formula que frontend)
            COSTO_CORTE = 10.0
            for corte in cortes_payload:
                pid_corte = corte["producto_id"]
                cantidad_corte = corte["cantidad"]
                ancho_cm = corte["ancho_cm"]
                alto_cm = corte["alto_cm"]
                categoria_corte = corte.get("_categoria", "")

                prod_info = supabase.table("productos").select("precio_unitario").eq("id_producto", pid_corte).limit(1).execute()
                if prod_info and prod_info.data:
                    precio = float(prod_info.data[0].get("precio_unitario", 0))
                    if "ALUMIN" in categoria_corte:
                        largo_cm = ancho_cm if ancho_cm > 0 else alto_cm
                        precio_pieza = ((largo_cm / 100.0) * precio) + COSTO_CORTE
                    elif ancho_cm > 0 and alto_cm > 0:
                        precio_pieza = ((ancho_cm * alto_cm / 10000.0) * precio) + COSTO_CORTE
                    else:
                        precio_pieza = precio
                    total_venta += precio_pieza * cantidad_corte

            print(f"[COMPRA_SERVICE] Total venta: S/ {total_venta:.2f}, Metodo: {metodo_normalizado}")
            
            if total_venta > 0:
                registrar_venta(total=total_venta, metodo=metodo_normalizado, caja_id=None)
                print(f"[COMPRA_SERVICE] [OK] Venta registrada")
        except Exception as e:
            print(f"[COMPRA_SERVICE] [!] Error registrando venta: {str(e)}")

        return {
            "ok": True,
            "cuenta_temporal": True,
            "correo_temporal": correo_temp,
            "contrasena_temporal": contrasena_temp,
            "jwt_temporal": jwt_temp,
            "cliente_id": str(cliente_temp["id_cliente"])
        }
