"""
Clase base para todos los modelos de la aplicación.
Define interfaz común y métodos de utilidad.

Patrón: Template Method + Abstraction (refactoring.guru)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import datetime


class BaseModel(ABC):
    """
    Clase base para todos los modelos.

    Responsabilidades:
    - Definir interfaz común
    - Validación básica
    - Conversión a/desde diccionarios
    - Persistencia de metadatos (created_at, updated_at)
    """

    def __init__(self):
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()

    @abstractmethod
    def validate(self) -> tuple[bool, List[str]]:
        """
        Valida los datos del modelo.

        Returns:
            (is_valid, list_of_errors)
        """
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el modelo a diccionario (para JSON)"""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseModel':
        """Crea instancia desde diccionario (desde BD o API)"""
        pass

    def mark_updated(self):
        """Marca el modelo como modificado"""
        self.updated_at = datetime.now()

    def get_errors(self) -> List[str]:
        """Devuelve lista de errores de validación"""
        is_valid, errors = self.validate()
        return errors if not is_valid else []

    def is_valid(self) -> bool:
        """Verifica si el modelo es válido"""
        is_valid, _ = self.validate()
        return is_valid
