"""
Clase base para Repository Pattern.
Abstrae todas las operaciones de BD y proporciona interfaz común.

Patrón: Repository (refactoring.guru) + Adapter Pattern
Beneficio: Si cambias de Supabase a otra BD, solo actualizas los repositorios
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generic, TypeVar
from .exceptions import RepositoryException, EntityNotFoundException

T = TypeVar('T')  # Tipo genérico


class BaseRepository(ABC, Generic[T]):
    """
    Clase base genérica para todos los repositorios.

    Métodos CRUD (Create, Read, Update, Delete) comunes.
    Cada repositorio específico implementa las queries concretas.
    """

    def __init__(self, table_name: str, db_client: Any):
        """
        Args:
            table_name: Nombre de la tabla en Supabase
            db_client: Cliente de Supabase (inyectado)
        """
        self.table_name = table_name
        self.db = db_client

    # ==================== CREATE ====================
    def create(self, data: Dict[str, Any]) -> T:
        """
        Crea un nuevo registro en la BD.

        Args:
            data: Datos a insertar

        Returns:
            Instancia del modelo creado

        Raises:
            RepositoryException: Si hay error en BD
        """
        try:
            response = self.db.table(self.table_name).insert(data).execute()
            if response.data:
                return self._map_to_model(response.data[0])
            raise RepositoryException(f"No se pudo crear registro en {self.table_name}")
        except Exception as e:
            raise RepositoryException(f"Error al crear: {str(e)}")

    # ==================== READ ====================
    def get_by_id(self, id_value: str, id_field: str = "id") -> Optional[T]:
        """
        Obtiene un registro por ID.

        Args:
            id_value: Valor del ID
            id_field: Nombre del campo ID (default: 'id')

        Returns:
            Instancia del modelo o None
        """
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .eq(id_field, id_value)\
                .limit(1)\
                .execute()

            if response.data:
                return self._map_to_model(response.data[0])
            return None
        except Exception as e:
            raise RepositoryException(f"Error al obtener por ID: {str(e)}")

    def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """
        Obtiene todos los registros (paginado).

        Args:
            limit: Máximo de registros
            offset: Desplazamiento para paginación

        Returns:
            Lista de instancias del modelo
        """
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .range(offset, offset + limit - 1)\
                .execute()

            return [self._map_to_model(item) for item in (response.data or [])]
        except Exception as e:
            raise RepositoryException(f"Error al obtener todos: {str(e)}")

    def find_by_field(self, field: str, value: Any) -> List[T]:
        """
        Busca registros por un campo específico.

        Args:
            field: Nombre del campo
            value: Valor a buscar

        Returns:
            Lista de instancias encontradas
        """
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .eq(field, value)\
                .execute()

            return [self._map_to_model(item) for item in (response.data or [])]
        except Exception as e:
            raise RepositoryException(f"Error al buscar por {field}: {str(e)}")

    def search(self, field: str, pattern: str) -> List[T]:
        """
        Busca registros usando ILIKE (case-insensitive).

        Args:
            field: Campo donde buscar
            pattern: Patrón de búsqueda (% = wildcard)

        Returns:
            Lista de registros encontrados
        """
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .ilike(field, f"%{pattern}%")\
                .execute()

            return [self._map_to_model(item) for item in (response.data or [])]
        except Exception as e:
            raise RepositoryException(f"Error en búsqueda: {str(e)}")

    # ==================== UPDATE ====================
    def update(self, id_value: str, data: Dict[str, Any], id_field: str = "id") -> Optional[T]:
        """
        Actualiza un registro existente.

        Args:
            id_value: ID del registro a actualizar
            data: Nuevos datos
            id_field: Nombre del campo ID

        Returns:
            Instancia actualizada o None si no existe

        Raises:
            EntityNotFoundException: Si el registro no existe
        """
        try:
            # Verificar que existe
            existing = self.get_by_id(id_value, id_field)
            if not existing:
                raise EntityNotFoundException(self.table_name, id_value)

            response = self.db.table(self.table_name)\
                .update(data)\
                .eq(id_field, id_value)\
                .execute()

            if response.data:
                return self._map_to_model(response.data[0])
            raise RepositoryException(f"No se pudo actualizar registro en {self.table_name}")
        except Exception as e:
            if isinstance(e, EntityNotFoundException):
                raise
            raise RepositoryException(f"Error al actualizar: {str(e)}")

    # ==================== DELETE ====================
    def delete(self, id_value: str, id_field: str = "id") -> bool:
        """
        Elimina un registro.

        Args:
            id_value: ID del registro a eliminar
            id_field: Nombre del campo ID

        Returns:
            True si se eliminó, False si no existía

        Raises:
            RepositoryException: Si hay error en BD
        """
        try:
            # Verificar que existe
            existing = self.get_by_id(id_value, id_field)
            if not existing:
                raise EntityNotFoundException(self.table_name, id_value)

            response = self.db.table(self.table_name)\
                .delete()\
                .eq(id_field, id_value)\
                .execute()

            return bool(response.data or response.count)
        except Exception as e:
            if isinstance(e, EntityNotFoundException):
                raise
            raise RepositoryException(f"Error al eliminar: {str(e)}")

    # ==================== HELPERS ====================
    @abstractmethod
    def _map_to_model(self, data: Dict[str, Any]) -> T:
        """
        Mapea diccionario de BD a modelo.
        Debe implementarse en cada repositorio específico.
        """
        pass

    def count(self) -> int:
        """Cuenta total de registros en la tabla"""
        try:
            response = self.db.table(self.table_name)\
                .select("*", count="exact")\
                .execute()
            return response.count or 0
        except Exception as e:
            raise RepositoryException(f"Error al contar: {str(e)}")
