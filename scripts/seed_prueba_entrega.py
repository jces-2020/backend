# -*- coding: utf-8 -*-
"""
Genera datos de prueba para el flujo de Entrega (OBRAS):
- 1 cliente de prueba (o reutiliza uno existente)
- 1 carrito_compras
- N productos distintos (ya existentes en la tabla productos)
- 30 cortes repartidos entre esos productos, cada uno con su venta asociada
- 1 notificacion tipo 'entrega' apuntando al carrito

Replica el mismo flujo que backend/app/services/compra_service.py
(guardar_flujo_compra) para que Entrega.jsx / /api/cortes/notificacion/<id>
puedan leer los datos sin tocar nada mas.

Uso (desde backend/, con el venv activado):
    python scripts/seed_prueba_entrega.py
"""
import os
import sys
import time
import random

_base = os.path.dirname(os.path.abspath(__file__))   # backend/scripts
_root = os.path.dirname(_base)                        # backend
_app = os.path.join(_root, "app")                      # backend/app
for _p in [_app, _root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.services.supabase_client import supabase

DEFAULT_TIPO_VENTA_ID_PRODUCTO = "1397cefc-c5da-42bc-be75-a3ac36a2266d"
DEFAULT_ESTADO_NOTIFICACION_ID = "62369650-3a4f-4f99-9968-d4d27ae6de16"

CLIENTE_CORREO = "prueba.entrega@vidriobras.com"
CLIENTE_NOMBRE = "Cliente Prueba Entrega"
NUM_PRODUCTOS = 4
TOTAL_CORTES = 30


def _obtener_o_crear_cliente():
    existente = supabase.table("cliente").select("id_cliente, nombre").eq("correo", CLIENTE_CORREO).limit(1).execute()
    if existente.data:
        return existente.data[0]

    creado = supabase.table("cliente").insert({
        "correo": CLIENTE_CORREO,
        "contraseña": "prueba123",
        "nombre": CLIENTE_NOMBRE,
        "cuenta_temporal": True,
        "registro_completo": True,
    }).execute()
    return creado.data[0]


def _obtener_productos(cantidad):
    res = supabase.table("productos") \
        .select("id_producto, nombre, precio_unitario") \
        .not_.is_("precio_unitario", "null") \
        .limit(cantidad) \
        .execute()
    productos = [p for p in (res.data or []) if p.get("precio_unitario")]
    if len(productos) < 2:
        raise RuntimeError("Se necesitan al menos 2 productos con precio_unitario en la tabla 'productos'.")
    return productos[:cantidad]


def main():
    cliente = _obtener_o_crear_cliente()
    cliente_id = cliente["id_cliente"]
    print(f"[SEED] Cliente: {cliente.get('nombre')} ({cliente_id})")

    productos = _obtener_productos(NUM_PRODUCTOS)
    print(f"[SEED] Productos usados: {[p['nombre'] for p in productos]}")

    carrito_res = supabase.table("carrito_compras").insert({"estado": "inicio"}).execute()
    carrito_id = carrito_res.data[0]["id_carrito"]
    print(f"[SEED] Carrito: {carrito_id}")

    # Repartir 30 cortes entre los productos elegidos (al menos 1 por producto)
    reparto = [1] * len(productos)
    restante = TOTAL_CORTES - len(productos)
    while restante > 0:
        reparto[random.randrange(len(productos))] += 1
        restante -= 1

    venta_ids = []
    cortes_insertados = 0
    fecha_hoy = time.strftime("%Y-%m-%d")

    for producto, num_cortes in zip(productos, reparto):
        precio = float(producto.get("precio_unitario") or 0)
        for _ in range(num_cortes):
            ancho_cm = round(random.uniform(30, 180), 1)
            alto_cm = round(random.uniform(30, 180), 1)
            monto = round(((ancho_cm * alto_cm / 10000.0) * precio) + 10.0, 2)

            venta_res = supabase.table("venta").insert({
                "cliente_id": cliente_id,
                "producto_id": producto["id_producto"],
                "carrito_id": carrito_id,
                "cantidad": 1,
                "monto": monto,
                "metodo": "al contado",
                "fecha_venta": fecha_hoy,
                "tipo_venta_id": DEFAULT_TIPO_VENTA_ID_PRODUCTO,
            }).execute()
            venta_id = venta_res.data[0]["id_venta"]
            venta_ids.append(venta_id)

            supabase.table("cortes").insert({
                "venta_id": venta_id,
                "ancho_cm": ancho_cm,
                "alto_cm": alto_cm,
                "cantidad": 1,
                "estado": "pendiente",
                "normbre": producto["nombre"],
            }).execute()
            cortes_insertados += 1

    print(f"[SEED] Cortes insertados: {cortes_insertados}")

    nombres_productos = ", ".join(p["nombre"] for p in productos)
    notif_res = supabase.table("notificacion").insert({
        "tipo": "entrega",
        "nombre": cliente["nombre"],
        "descripcion": f"{nombres_productos} (Carrito: {carrito_id})",
        "estado_notificacion_id": DEFAULT_ESTADO_NOTIFICACION_ID,
        "venta_id": venta_ids[0],
    }).execute()
    notificacion_id = notif_res.data[0]["id_notificacion"]

    print(f"[SEED] Notificacion creada: {notificacion_id}")
    print(f"[SEED] Prueba en frontend con GET /api/cortes/notificacion/{notificacion_id}")


if __name__ == "__main__":
    main()
