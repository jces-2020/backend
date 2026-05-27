"""
Clase base para Service Pattern.
Contiene lógica de negocio, validaciones y orquestación.

Patrón: Service Layer (refactoring.guru) + Template Method
Beneficio: Separación clara entre HTTP (controllers) y lógica de negocio (services)
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generic, TypeVar
from .base_repository import BaseRepository
from .exceptions import InvalidDataException

T = TypeVar('T')  # Tipo genérico


class BaseService(ABC, Generic[T]):
    """
    Clase base genérica para todos los servicios.

    Responsabilidades:
    - Validar datos de entrada
    - Aplicar reglas de negocio
    - Orquestar operaciones de múltiples repositorios
    - Manejar transacciones
    - Cacheo (si es necesario)
    """

    def __init__(self, repository: BaseRepository):
        """
        Args:
            repository: Repositorio inyectado para acceso a datos
        """
        self.repository = repository

    # ==================== CRUD OPERATIONS ====================

    def create(self, data: Dict[str, Any]) -> T:
        """
        Crea una nueva entidad tras validación.

        Args:
            data: Datos de entrada

        Returns:
            Instancia creada

        Raises:
            InvalidDataException: Si datos no son válidos
        """
        # Validar datos
        errors = self._validate_input(data, mode="create")
        if errors:
            raise InvalidDataException("; ".join(errors))

        # Transformar/preparar datos
        prepared_data = self._prepare_data_for_create(data)

        # Crear en BD
        entity = self.repository.create(prepared_data)

        # Post-procesamiento (ej: logs, eventos, etc)
        self._after_create(entity)

        return entity

    def get_by_id(self, entity_id: str) -> Optional[T]:
        """
        Obtiene una entidad por ID.

        Args:
            entity_id: ID a buscar

        Returns:
            Entidad o None
        """
        entity = self.repository.get_by_id(entity_id)
        if entity:
            self._after_read(entity)
        return entity

    def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """
        Obtiene todas las entidades (paginadas).

        Args:
            limit: Máximo registros
            offset: Desplazamiento

        Returns:
            Lista de entidades
        """
        entities = self.repository.get_all(limit, offset)
        return [self._after_read(e) for e in entities]

    def update(self, entity_id: str, data: Dict[str, Any]) -> T:
        """
        Actualiza una entidad tras validación.

        Args:
            entity_id: ID a actualizar
            data: Nuevos datos

        Returns:
            Entidad actualizada

        Raises:
            InvalidDataException: Si datos no son válidos
        """
        # Validar datos
        errors = self._validate_input(data, mode="update")
        if errors:
            raise InvalidDataException("; ".join(errors))

        # Preparar datos
        prepared_data = self._prepare_data_for_update(data)

        # Actualizar en BD
        entity = self.repository.update(entity_id, prepared_data)

        # Post-procesamiento
        self._after_update(entity)

        return entity

    def delete(self, entity_id: str) -> bool:
        """
        Elimina una entidad.

        Args:
            entity_id: ID a eliminar

        Returns:
            True si se eliminó
        """
        # Pre-procesamiento (ej: validar que se puede eliminar)
        self._before_delete(entity_id)

        # Eliminar de BD
        success = self.repository.delete(entity_id)

        # Post-procesamiento
        if success:
            self._after_delete(entity_id)

        return success

    # ==================== BÚSQUEDAS ====================

    def search(self, field: str, pattern: str) -> List[T]:
        """
        Busca entidades por patrón.

        Args:
            field: Campo donde buscar
            pattern: Patrón de búsqueda

        Returns:
            Lista de entidades encontradas
        """
        return self.repository.search(field, pattern)

    def find_by(self, field: str, value: Any) -> List[T]:
        """
        Encuentra entidades por campo específico.

        Args:
            field: Campo a filtrar
            value: Valor a buscar

        Returns:
            Lista de entidades
        """
        return self.repository.find_by_field(field, value)

    # ==================== HOOKS PARA LÓGICA DE NEGOCIO ====================
    # Los subclases deben sobrescribir estos métodos según necesidad

    @abstractmethod
    def _validate_input(self, data: Dict[str, Any], mode: str = "create") -> List[str]:
        """
        Valida datos de entrada.

        Args:
            data: Datos a validar
            mode: "create" o "update"

        Returns:
            Lista de errores (vacía si válido)
        """
        pass

    def _prepare_data_for_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepara datos antes de insertar (limpiar, transformar, etc)"""
        return data

    def _prepare_data_for_update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepara datos antes de actualizar"""
        return data

    def _after_create(self, entity: T) -> None:
        """Hook post-creación (logs, eventos, cache, etc)"""
        pass

    def _after_read(self, entity: T) -> T:
        """Hook post-lectura (enriquecimiento de datos, transformaciones)"""
        return entity

    def _after_update(self, entity: T) -> None:
        """Hook post-actualización"""
        pass

    def _before_delete(self, entity_id: str) -> None:
        """Hook pre-eliminación (validaciones, cascadas, etc)"""
        pass

    def _after_delete(self, entity_id: str) -> None:
        """Hook post-eliminación (logs, eventos, etc)"""
        pass

    # ==================== UTILIDADES ====================

    def count(self) -> int:
        """Cuenta total de entidades"""
        return self.repository.count()
