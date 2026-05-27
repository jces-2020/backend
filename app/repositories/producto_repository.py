# -*- coding: utf-8 -*-
"""
Repositorio de Producto - Acceso a datos de productos.

Patrón: Repository (refactoring.guru)
Responsabilidades: Solo queries a BD, sin lógica de negocio
"""
from typing import Dict, Any, Optional, List
from app.core import BaseRepository
from app.models.producto import Producto


class ProductoRepository(BaseRepository):
    """
    Repositorio para gestionar productos en Supabase.
    Hereda CRUD básico de BaseRepository.
    """

    def __init__(self, db_client: Any):
        super().__init__(table_name="productos", db_client=db_client)

    def _map_to_model(self, data: Dict[str, Any]) -> Producto:
        """Mapea diccionario de BD a modelo Producto"""
        return Producto.from_dict(data)

    # ==================== QUERIES ESPECÍFICAS ====================

    def find_by_codigo(self, codigo: str) -> Optional[Producto]:
        """
        Busca producto por código (SKU).

        Args:
            codigo: Código del producto

        Returns:
            Producto o None

        Raises:
            RepositoryException: Error de BD
        """
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .eq("codigo", codigo.upper())\
                .limit(1)\
                .execute()

            if response.data:
                return self._map_to_model(response.data[0])
            return None
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error buscando por código: {str(e)}")

    def find_by_categoria(self, categoria_id: str, limit: int = 100) -> List[Producto]:
        """Busca productos por categoría"""
        return self.find_by_field("categoria_id", categoria_id)

    def find_by_almacen(self, almacen_id: str) -> List[Producto]:
        """Busca productos en un almacén específico"""
        return self.find_by_field("almacen_id", almacen_id)

    def buscar_por_nombre(self, nombre: str) -> List[Producto]:
        """Búsqueda flexible por nombre"""
        return self.search("nombre", nombre)

    def obtener_con_stock(self, limit: int = 100) -> List[Producto]:
        """Obtiene solo productos con stock disponible"""
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .gt("cantidad", 0)\
                .range(0, limit - 1)\
                .execute()

            return [self._map_to_model(item) for item in (response.data or [])]
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error obteniendo con stock: {str(e)}")

    def obtener_sin_stock(self, limit: int = 100) -> List[Producto]:
        """Obtiene productos sin stock (agotados)"""
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .eq("cantidad", 0)\
                .range(0, limit - 1)\
                .execute()

            return [self._map_to_model(item) for item in (response.data or [])]
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error obteniendo sin stock: {str(e)}")

    def obtener_por_rango_precio(self, min_precio: float, max_precio: float) -> List[Producto]:
        """Obtiene productos en rango de precio"""
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .gte("precio_unitario", min_precio)\
                .lte("precio_unitario", max_precio)\
                .execute()

            return [self._map_to_model(item) for item in (response.data or [])]
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error obteniendo por precio: {str(e)}")

    def contar_por_categoria(self, categoria_id: str) -> int:
        """Cuenta productos en una categoría"""
        try:
            response = self.db.table(self.table_name)\
                .select("id_producto", count="exact")\
                .eq("categoria_id", categoria_id)\
                .execute()
            return response.count or 0
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error contando por categoría: {str(e)}")

    def obtener_valor_inventario_total(self) -> float:
        """Calcula el valor total del inventario"""
        try:
            productos = self.get_all(limit=10000)
            total = sum(p.calcular_total_valor() for p in productos)
            return total
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error calculando inventario: {str(e)}")

    def actualizar_cantidad(self, producto_id: str, nueva_cantidad: int) -> Optional[Producto]:
        """Actualiza solo la cantidad de un producto"""
        try:
            response = self.db.table(self.table_name)\
                .update({"cantidad": nueva_cantidad})\
                .eq("id_producto", producto_id)\
                .execute()

            if response.data:
                return self._map_to_model(response.data[0])
            return None
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error actualizando cantidad: {str(e)}")
