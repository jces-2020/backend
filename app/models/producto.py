# -*- coding: utf-8 -*-
"""
Modelo Producto - Define estructura, validación y transformación de datos.

Responsabilidades:
- Estructura de datos del producto
- Validaciones de datos
- Conversión a/desde diccionarios
- Cálculos derivados (precio con impuesto, disponibilidad, etc)
"""
from typing import Dict, Any, List
from app.core import BaseModel


class Producto(BaseModel):
    """
    Modelo de Producto.

    Atributos:
        id_producto: UUID único
        codigo: Código único del producto (SKU)
        nombre: Nombre del producto
        descripcion: Descripción detallada
        precio_unitario: Precio base en soles
        cantidad: Stock total disponible
        grosor: Grosor del material (si aplica)
        categoria_id: FK a categoría
        almacen_id: FK a ubicación en almacén
        stock_id: FK a control de stock
        IMG_P: URL de imagen del producto
    """

    def __init__(
        self,
        id_producto: str,
        codigo: str,
        nombre: str,
        precio_unitario: float,
        cantidad: int,
        descripcion: str = "",
        grosor: str = "",
        categoria_id: str = None,
        almacen_id: str = None,
        stock_id: str = None,
        IMG_P: str = ""
    ):
        super().__init__()
        self.id_producto = id_producto
        self.codigo = codigo
        self.nombre = nombre
        self.precio_unitario = float(precio_unitario) if precio_unitario else 0
        self.cantidad = int(cantidad) if cantidad else 0
        self.descripcion = descripcion
        self.grosor = grosor
        self.categoria_id = categoria_id
        self.almacen_id = almacen_id
        self.stock_id = stock_id
        self.IMG_P = IMG_P

    def validate(self) -> tuple[bool, List[str]]:
        """
        Valida los datos del producto.

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Validar código
        if not self.codigo or len(self.codigo.strip()) < 2:
            errors.append("Código debe tener al menos 2 caracteres")

        # Validar nombre
        if not self.nombre or len(self.nombre.strip()) < 3:
            errors.append("Nombre debe tener al menos 3 caracteres")

        # Validar precio
        if self.precio_unitario < 0:
            errors.append("Precio no puede ser negativo")

        # Validar cantidad
        if self.cantidad < 0:
            errors.append("Cantidad no puede ser negativa")

        return (len(errors) == 0, errors)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario (para JSON)"""
        return {
            "id_producto": self.id_producto,
            "codigo": self.codigo,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "precio_unitario": self.precio_unitario,
            "cantidad": self.cantidad,
            "grosor": self.grosor,
            "categoria_id": self.categoria_id,
            "almacen_id": self.almacen_id,
            "stock_id": self.stock_id,
            "IMG_P": self.IMG_P,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    def to_dict_carrito(self) -> Dict[str, Any]:
        """Diccionario simplificado para carrito de compras"""
        return {
            "id_producto": self.id_producto,
            "codigo": self.codigo,
            "nombre": self.nombre,
            "precio_unitario": self.precio_unitario,
            "cantidad": self.cantidad,
            "IMG_P": self.IMG_P
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Producto':
        """Crea instancia desde diccionario (de BD o API)"""
        return cls(
            id_producto=data.get("id_producto"),
            codigo=(data.get("codigo") or "").strip(),
            nombre=(data.get("nombre") or "").strip(),
            precio_unitario=data.get("precio_unitario", 0),
            cantidad=data.get("cantidad", 0),
            descripcion=(data.get("descripcion") or "").strip(),
            grosor=(data.get("grosor") or "").strip(),
            categoria_id=data.get("categoria_id"),
            almacen_id=data.get("almacen_id"),
            stock_id=data.get("stock_id"),
            IMG_P=(data.get("IMG_P") or "").strip()
        )

    # ==================== HELPERS ====================

    def hay_stock(self) -> bool:
        """Verifica si hay stock disponible"""
        return self.cantidad > 0

    def obtener_stock(self) -> int:
        """Obtiene cantidad en stock"""
        return max(0, self.cantidad)

    def rebajar_stock(self, cantidad: int) -> bool:
        """
        Rebaja el stock.

        Args:
            cantidad: Cantidad a rebajar

        Returns:
            True si se pudo rebajar, False si no hay suficiente stock
        """
        if cantidad > self.cantidad:
            return False
        self.cantidad -= cantidad
        self.mark_updated()
        return True

    def agregar_stock(self, cantidad: int) -> None:
        """Agrega stock"""
        self.cantidad += cantidad
        self.mark_updated()

    def calcular_total_valor(self) -> float:
        """Calcula el valor total en inventario"""
        return self.precio_unitario * self.cantidad

    def normalizar(self) -> None:
        """Normaliza datos (trim, minúsculas, etc)"""
        self.codigo = (self.codigo or "").strip().upper()
        self.nombre = (self.nombre or "").strip()
        self.descripcion = (self.descripcion or "").strip()
        self.grosor = (self.grosor or "").strip()
        self.IMG_P = (self.IMG_P or "").strip()

    def es_disponible(self, cantidad_solicitada: int = 1) -> bool:
        """Verifica si hay cantidad suficiente disponible"""
        return self.cantidad >= cantidad_solicitada
