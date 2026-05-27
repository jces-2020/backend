"""
Repositorio de Cliente - Acceso a datos de clientes.

Patrón: Repository (refactoring.guru)
Responsabilidades: Solo queries a BD, sin lógica de negocio
"""
from typing import Dict, Any, Optional, List
from app.core import BaseRepository
from app.models.cliente import Cliente


class ClienteRepository(BaseRepository):
    """
    Repositorio para gestionar clientes en Supabase.
    Hereda CRUD básico de BaseRepository.
    """

    def __init__(self, db_client: Any):
        super().__init__(table_name="cliente", db_client=db_client)

    def _map_to_model(self, data: Dict[str, Any]) -> Cliente:
        """Mapea diccionario de BD a modelo Cliente"""
        return Cliente.from_dict(data)

    # ==================== QUERIES ESPECÍFICAS ====================
    # Agregar aquí queries más complejas que no están en BaseRepository

    def find_by_correo(self, correo: str) -> Optional[Cliente]:
        """
        Busca cliente por correo.

        Args:
            correo: Email del cliente

        Returns:
            Cliente o None

        Raises:
            RepositoryException: Error de BD
        """
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .eq("correo", correo.lower())\
                .limit(1)\
                .execute()

            if response.data:
                return self._map_to_model(response.data[0])
            return None
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error buscando por correo: {str(e)}")

    def find_by_documento(self, documento: str) -> Optional[Cliente]:
        """Busca cliente por documento"""
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .eq("documento", documento)\
                .limit(1)\
                .execute()

            if response.data:
                return self._map_to_model(response.data[0])
            return None
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error buscando por documento: {str(e)}")

    def find_by_estado(self, estado_id: str) -> List[Cliente]:
        """Busca clientes por estado"""
        return self.find_by_field("estado_cliente_id", estado_id)

    def buscar_por_nombre(self, nombre: str) -> List[Cliente]:
        """Búsqueda flexible por nombre"""
        return self.search("nombre", nombre)

    def get_activos(self, limit: int = 100) -> List[Cliente]:
        """Obtiene solo clientes activos"""
        try:
            response = self.db.table(self.table_name)\
                .select("*")\
                .neq("estado_cliente_id", None)\
                .range(0, limit - 1)\
                .execute()

            return [self._map_to_model(item) for item in (response.data or [])]
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error obteniendo activos: {str(e)}")

    def contar_por_estado(self, estado_id: str) -> int:
        """Cuenta clientes por estado"""
        try:
            response = self.db.table(self.table_name)\
                .select("id_cliente", count="exact")\
                .eq("estado_cliente_id", estado_id)\
                .execute()
            return response.count or 0
        except Exception as e:
            from app.core import RepositoryException
            raise RepositoryException(f"Error contando: {str(e)}")
