"""
Service: Entrega de Pedidos
Lógica de negocio para la gestión de entregas de pedidos.
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from services.supabase_client import supabase


def registrar_productos_entrega(pedido_id: str, productos: List[Dict[str, Any]]) -> bool:
    """
    Registra los productos seleccionados para una entrega.
    
    Args:
        pedido_id: ID del pedido
        productos: Lista de productos con id y cantidad
    
    Returns:
        True si se registró correctamente
    """
    try:
        # TODO: Actualizar tabla de entregas o pedidos
        for producto in productos:
            entrega_data = {
                "pedido_id": pedido_id,
                "producto_id": producto.get("id"),
                "cantidad": producto.get("cantidad"),
                "fecha_registro": datetime.now().isoformat()
            }
            
            supabase.table("entregas_productos").insert(entrega_data).execute()
        
        return True
    
    except Exception as e:
        print(f"Error registrando productos entrega: {e}")
        return False


def confirmar_entrega_pedido(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Confirma la entrega de un pedido al cliente.
    
    Args:
        data: Datos de la entrega
    
    Returns:
        Datos de la entrega confirmada o None si falla
    """
    try:
        pedido_id = data.get("pedido_id")
        
        # Actualizar estado del pedido a ENTREGADO
        supabase.table("carrito").update({
            "estado": "ENTREGADO",
            "fecha_entrega": data.get("fecha") or datetime.now().isoformat()
        }).eq("id", pedido_id).execute()
        
        # Registrar entrega
        entrega_data = {
            "pedido_id": pedido_id,
            "cliente": data.get("cliente"),
            "fecha_entrega": data.get("fecha"),
            "productos_entregados": data.get("productos_entregados", []),
            "observaciones": data.get("observaciones", ""),
            "estado": "COMPLETADO"
        }
        
        result = supabase.table("entregas").insert(entrega_data).execute()
        return result.data[0] if result.data else None
    
    except Exception as e:
        print(f"Error confirmando entrega: {e}")
        return None


def get_entrega_by_pedido_id(pedido_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene el detalle de una entrega por ID de pedido.
    
    Args:
        pedido_id: ID del pedido
    
    Returns:
        Datos de la entrega o None si no existe
    """
    try:
        result = supabase.table("entregas").select("*").eq("pedido_id", pedido_id).execute()
        return result.data[0] if result.data else None
    
    except Exception as e:
        print(f"Error obteniendo entrega: {e}")
        return None


def get_historial_entregas(fecha_inicio: Optional[str] = None, 
                           fecha_fin: Optional[str] = None,
                           cliente: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Obtiene el historial de entregas con filtros opcionales.
    
    Args:
        fecha_inicio: Fecha de inicio del filtro (YYYY-MM-DD)
        fecha_fin: Fecha fin del filtro (YYYY-MM-DD)
        cliente: Nombre del cliente para filtrar
    
    Returns:
        Lista de entregas
    """
    try:
        query = supabase.table("entregas").select("*")
        
        if fecha_inicio:
            query = query.gte("fecha_entrega", fecha_inicio)
        
        if fecha_fin:
            query = query.lte("fecha_entrega", fecha_fin)
        
        if cliente:
            query = query.ilike("cliente", f"%{cliente}%")
        
        result = query.order("fecha_entrega", desc=True).execute()
        return result.data or []
    
    except Exception as e:
        print(f"Error obteniendo historial: {e}")
        return []


def validar_stock_productos(productos: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Valida que haya stock suficiente de productos para entrega.
    
    Args:
        productos: Lista de productos con id y cantidad
    
    Returns:
        Tupla (es_valido, mensaje)
    """
    try:
        for producto in productos:
            producto_id = producto.get("id")
            cantidad_requerida = producto.get("cantidad", 0)
            
            # Consultar stock actual
            result = supabase.table("producto").select("stock").eq("id", producto_id).execute()
            
            if not result.data:
                return False, f"Producto {producto_id} no encontrado"
            
            stock_actual = result.data[0].get("stock", 0)
            
            if stock_actual < cantidad_requerida:
                return False, f"Stock insuficiente para producto {producto_id}"
        
        return True, "Stock disponible"
    
    except Exception as e:
        print(f"Error validando stock: {e}")
        return False, str(e)
