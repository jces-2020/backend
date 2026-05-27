# -*- coding: utf-8 -*-
from typing import Dict, Any, Optional, List
from app.core import BaseService
from app.repositories.producto_repository import ProductoRepository
from app.models.producto import Producto
from app.core.exceptions import InvalidDataException, DuplicateEntityException, EntityNotFoundException

class ProductoService(BaseService):
    def __init__(self, repository: ProductoRepository):
        super().__init__(repository)
        self.repository: ProductoRepository = repository

    def crear_producto(self, data: Dict[str, Any]) -> Producto:
        errors = self._validate_input(data, mode="create")
        if errors:
            raise InvalidDataException("; ".join(errors))
        codigo = data.get('codigo', '').strip().upper()
        if self.repository.find_by_codigo(codigo):
            raise DuplicateEntityException("Producto", "código", codigo)
        prepared = self._prepare_data_for_create(data)
        producto = self.repository.create(prepared)
        self._after_create(producto)
        return producto

    def obtener_producto(self, producto_id: str) -> Optional[Producto]:
        producto = self.repository.get_by_id(producto_id, id_field="id_producto")
        if producto:
            self._after_read(producto)
        return producto

    def obtener_todos_productos(self, limit: int = 100, offset: int = 0) -> List[Producto]:
        return self.repository.get_all(limit, offset)

    def buscar_productos(self, patron: str) -> List[Producto]:
        return self.repository.buscar_por_nombre(patron)

    def actualizar_producto(self, producto_id: str, data: Dict[str, Any]) -> Producto:
        producto = self.repository.get_by_id(producto_id, id_field="id_producto")
        if not producto:
            raise EntityNotFoundException("Producto", producto_id)
        errors = self._validate_input(data, mode="update")
        if errors:
            raise InvalidDataException("; ".join(errors))
        prepared = self._prepare_data_for_update(data)
        producto_actualizado = self.repository.update(producto_id, prepared, id_field="id_producto")
        self._after_update(producto_actualizado)
        return producto_actualizado

    def eliminar_producto(self, producto_id: str) -> bool:
        self._before_delete(producto_id)
        success = self.repository.delete(producto_id, id_field="id_producto")
        if success:
            self._after_delete(producto_id)
        return success

    def contar_productos(self) -> int:
        return self.repository.count()

    def _validate_input(self, data: Dict[str, Any], mode: str = "create") -> List[str]:
        errors = []
        if mode == "create":
            if not data.get('codigo', '').strip():
                errors.append("Código requerido")
            if not data.get('nombre', '').strip():
                errors.append("Nombre requerido")
            if data.get('precio_unitario') is None:
                errors.append("Precio requerido")
        return errors

    def _prepare_data_for_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        producto = Producto.from_dict(data)
        producto.normalizar()
        return {'codigo': producto.codigo, 'nombre': producto.nombre, 'descripcion': producto.descripcion, 'precio_unitario': producto.precio_unitario, 'cantidad': producto.cantidad, 'grosor': producto.grosor, 'categoria_id': data.get('categoria_id'), 'almacen_id': data.get('almacen_id'), 'stock_id': data.get('stock_id'), 'IMG_P': producto.IMG_P}

    def _prepare_data_for_update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        prepared = {}
        if 'codigo' in data:
            prepared['codigo'] = data['codigo'].strip().upper()
        if 'nombre' in data:
            prepared['nombre'] = data['nombre'].strip()
        if 'precio_unitario' in data:
            prepared['precio_unitario'] = float(data['precio_unitario'])
        if 'cantidad' in data:
            prepared['cantidad'] = int(data['cantidad'])
        return prepared

    def _after_create(self, producto: Producto) -> None:
        print(f"✓ Producto creado: {producto.id_producto} - {producto.nombre}")

    def _after_update(self, producto: Producto) -> None:
        print(f"✓ Producto actualizado: {producto.id_producto}")

    def _before_delete(self, producto_id: str) -> None:
        pass

    def _after_delete(self, producto_id: str) -> None:
        print(f"✓ Producto eliminado: {producto_id}")

    def buscar_producto_por_codigo(self, codigo: str) -> Optional[Producto]:
        """Busca producto por código"""
        return self.repository.find_by_codigo(codigo)

    def obtener_productos_con_stock(self) -> List[Producto]:
        """Obtiene productos con stock disponible"""
        return self.repository.obtener_con_stock()

    def obtener_estadisticas_stock(self) -> Dict[str, Any]:
        """Obtiene estadísticas del inventario"""
        total_productos = self.repository.count()
        valor_inventario = self.repository.obtener_valor_inventario_total()
        productos_sin_stock = self.repository.obtener_sin_stock(limit=10000)
        return {
            "total_productos": total_productos,
            "valor_total_inventario": valor_inventario,
            "productos_sin_stock": len(productos_sin_stock)
        }
