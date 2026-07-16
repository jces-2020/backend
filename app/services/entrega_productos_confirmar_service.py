"""
Servicio para confirmar productos entregados:
- Descuenta stock
- Guarda en reporte_entregas
"""
from typing import List, Dict, Any
from app.services.supabase_client import supabase


def confirmar_productos_entregados(carrito_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Confirma productos entregados:
    1. Descuenta stock de productos
    2. Guarda en reporte_entregas
    """
    try:
        if not carrito_id or not items:
            return {"success": False, "message": "Carrito e items requeridos"}

        productos_guardados = []
        
        # 1. Procesar cada producto
        for item in items:
            try:
                producto_id = item.get("producto_id")
                cantidad = int(item.get("cantidad", 1))
                
                if not producto_id or cantidad <= 0:
                    continue

                # Obtener datos del producto
                prod_result = supabase.table("productos") \
                    .select("*") \
                    .eq("id_producto", producto_id) \
                    .limit(1) \
                    .execute()
                
                if not prod_result.data:
                    print(f"Producto {producto_id} no encontrado")
                    continue
                
                producto = prod_result.data[0]
                cantidad_actual = int(producto.get("cantidad", 0))
                cantidad_nueva = max(0, cantidad_actual - cantidad)
                
                # Actualizar cantidad en productos
                supabase.table("productos") \
                    .update({"cantidad": cantidad_nueva}) \
                    .eq("id_producto", producto_id) \
                    .execute()
                
                print(f"Stock actualizado: {producto_id} de {cantidad_actual} a {cantidad_nueva}")

                # Notificar a Flutter vía Pusher (no bloquea si falla)
                try:
                    from app.services.pusher_service import notificar_stock_actualizado
                    notificar_stock_actualizado(
                        producto_id=str(producto_id),
                        nombre=producto.get('nombre', ''),
                        cantidad_nueva=cantidad_nueva,
                        cantidad_anterior=cantidad_actual,
                        codigo=producto.get('codigo'),
                    )
                except Exception as _pe:
                    print(f"[entrega_confirmar] Pusher omitido: {_pe}")
                
                # El historial ya vive en venta; no se borra la línea confirmada.
                print(f"Confirmado en venta: {producto_id}")
                
                # Guardar datos del producto para el reporte
                productos_guardados.append({
                    "producto_id": producto_id,
                    "nombre": producto.get("nombre"),
                    "codigo": producto.get("codigo"),
                    "descripcion": producto.get("descripcion"),
                    "categoria_id": producto.get("categoria_id"),
                    "grosor": producto.get("grosor"),
                    "cantidad_entregada": cantidad
                })
                
            except Exception as e:
                print(f"Error procesando producto {item}: {str(e)}")
                continue

        # 2. Guardar en reporte_entregas
        if productos_guardados:
            try:
                # Obtener datos del carrito y cliente
                carrito_result = supabase.table("carrito_compras") \
                    .select("*") \
                    .eq("id_carrito", carrito_id) \
                    .limit(1) \
                    .execute()
                
                cliente_id = carrito_result.data[0].get("cliente_id") if carrito_result.data else None
                
                cliente_nombre = "N/A"
                if cliente_id:
                    try:
                        cliente_result = supabase.table("cliente") \
                            .select("nombre") \
                            .eq("id_cliente", cliente_id) \
                            .limit(1) \
                            .execute()
                        cliente_nombre = cliente_result.data[0].get("nombre") if cliente_result.data else "N/A"
                    except Exception as e:
                        print(f"Error obteniendo nombre cliente: {str(e)}")
                
                reporte_data = {
                    "carrito_id": carrito_id,
                    "cliente_id": cliente_id,
                    "cliente_nombre": cliente_nombre,
                    "productos_entregados": productos_guardados,
                    "estado": "parcial",
                    "fecha_confirmacion": "now()"
                }
                
                try:
                    insert_result = supabase.table("reporte_entregas").insert(reporte_data).execute()
                    print(f"Reporte guardado con {len(productos_guardados)} productos")
                except Exception as e:
                    print(f"Tabla reporte_entregas no existe o error: {str(e)}")
                    # Continuar aunque falle aquí
                
            except Exception as e:
                print(f"Error guardando reporte: {str(e)}")

        return {
            "success": True,
            "message": f"Se confirmaron {len(productos_guardados)} productos",
            "productos_confirmados": len(productos_guardados),
            "productos": productos_guardados
        }

    except Exception as exc:
        print(f"Error en confirmar_productos_entregados: {str(exc)}")
        return {
            "success": False,
            "message": str(exc)
        }
