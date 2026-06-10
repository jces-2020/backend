"""
Servicio de Cliente - Lógica de negocio, validaciones, y CRUDs.

Patrón: Service Layer (refactoring.guru)
Responsabilidades:
- Validar datos
- Aplicar reglas de negocio
- Orquestar operaciones
- NO hace queries directas a BD (usa repository)
"""
from typing import Dict, Any, Optional, List
from app.core import BaseService
from app.repositories.cliente_repository import ClienteRepository
from app.models.cliente import Cliente
from app.core.exceptions import (
    InvalidDataException,
    DuplicateEntityException,
    EntityNotFoundException
)


class ClienteService(BaseService):
    """
    Servicio para gestionar clientes.
    Contiene toda la lógica de negocio relacionada a clientes.
    """

    def __init__(self, repository: ClienteRepository):
        """
        Args:
            repository: Inyección de dependencia del repositorio
        """
        super().__init__(repository)
        self.repository: ClienteRepository = repository

    # ==================== CREATE ====================
    def crear_cliente(self, data: Dict[str, Any]) -> Cliente:
        """
        Crea un nuevo cliente tras validaciones.

        Args:
            data: Datos del cliente {nombre, correo, documento, numero, contraseña, etc}

        Returns:
            Cliente creado

        Raises:
            InvalidDataException: Si datos inválidos
            DuplicateEntityException: Si correo/documento ya existen
        """
        # 1. Validar datos básicos
        errors = self._validate_input(data, mode="create")
        if errors:
            raise InvalidDataException("; ".join(errors))

        # 2. Verificar que correo no exista
        correo = data.get('correo', '').strip().lower()
        if self.repository.find_by_correo(correo):
            raise DuplicateEntityException("Cliente", "correo", correo)

        # 3. Verificar que documento no exista (si aplica)
        documento = data.get('documento', '').strip()
        if documento and self.repository.find_by_documento(documento):
            raise DuplicateEntityException("Cliente", "documento", documento)

        # 4. Preparar datos
        prepared = self._prepare_data_for_create(data)

        # 5. Crear en BD
        cliente = self.repository.create(prepared)

        # 6. Post-procesamiento
        self._after_create(cliente)

        return cliente

    # ==================== READ ====================
    def obtener_cliente(self, cliente_id: str) -> Optional[Cliente]:
        """
        Obtiene un cliente por ID.

        Args:
            cliente_id: ID del cliente

        Returns:
            Cliente o None

        Raises:
            EntityNotFoundException: Si cliente no existe (opcional)
        """
        cliente = self.repository.get_by_id(cliente_id, id_field="id_cliente")
        if cliente:
            self._after_read(cliente)
        return cliente

    def obtener_cliente_o_error(self, cliente_id: str) -> Cliente:
        """
        Obtiene un cliente o lanza excepción si no existe.

        Args:
            cliente_id: ID del cliente

        Returns:
            Cliente

        Raises:
            EntityNotFoundException: Si cliente no existe
        """
        cliente = self.obtener_cliente(cliente_id)
        if not cliente:
            raise EntityNotFoundException("Cliente", cliente_id)
        return cliente

    def obtener_todos_clientes(self, limit: int = 100, offset: int = 0) -> List[Cliente]:
        """
        Obtiene todos los clientes (paginado).

        Args:
            limit: Máximo de registros
            offset: Desplazamiento

        Returns:
            Lista de clientes
        """
        return self.repository.get_all(limit, offset)

    def buscar_cliente_por_correo(self, correo: str) -> Optional[Cliente]:
        """Busca cliente por correo"""
        cliente = self.repository.find_by_correo(correo)
        if cliente:
            self._after_read(cliente)
        return cliente

    def buscar_cliente_por_documento(self, documento: str) -> Optional[Cliente]:
        """Busca cliente por documento"""
        cliente = self.repository.find_by_documento(documento)
        if cliente:
            self._after_read(cliente)
        return cliente

    def buscar_clientes(self, patron: str) -> List[Cliente]:
        """Búsqueda flexible por nombre o documento"""
        return self.repository.buscar_por_nombre(patron)

    def obtener_clientes_activos(self, limit: int = 100) -> List[Cliente]:
        """Obtiene solo clientes activos"""
        return self.repository.get_activos(limit)

    # ==================== UPDATE ====================
    def actualizar_cliente(self, cliente_id: str, data: Dict[str, Any]) -> Cliente:
        """
        Actualiza un cliente existente.

        Args:
            cliente_id: ID del cliente a actualizar
            data: Nuevos datos (nombre, correo, etc)

        Returns:
            Cliente actualizado

        Raises:
            InvalidDataException: Si datos inválidos
            EntityNotFoundException: Si cliente no existe
            DuplicateEntityException: Si correo ya está en uso
        """
        # 1. Verificar que cliente existe
        cliente = self.obtener_cliente_o_error(cliente_id)

        # 2. Validar nuevos datos
        errors = self._validate_input(data, mode="update")
        if errors:
            raise InvalidDataException("; ".join(errors))

        # 3. Verificar que correo no esté en uso por otro
        nuevo_correo = data.get('correo')
        if nuevo_correo:
            nuevo_correo = nuevo_correo.strip().lower()
            if nuevo_correo != cliente.correo:
                otro = self.repository.find_by_correo(nuevo_correo)
                if otro:
                    raise DuplicateEntityException("Cliente", "correo", nuevo_correo)

        # 4. Verificar documento único
        nuevo_doc = data.get('documento')
        if nuevo_doc:
            nuevo_doc = nuevo_doc.strip()
            if nuevo_doc != cliente.documento:
                otro = self.repository.find_by_documento(nuevo_doc)
                if otro:
                    raise DuplicateEntityException("Cliente", "documento", nuevo_doc)

        # 5. Preparar datos
        prepared = self._prepare_data_for_update(data)

        # 6. Actualizar en BD
        cliente_actualizado = self.repository.update(
            cliente_id,
            prepared,
            id_field="id_cliente"
        )

        # 7. Post-procesamiento
        self._after_update(cliente_actualizado)

        return cliente_actualizado

    # ==================== DELETE ====================
    def eliminar_cliente(self, cliente_id: str) -> bool:
        """
        Elimina un cliente.

        Args:
            cliente_id: ID del cliente a eliminar

        Returns:
            True si se eliminó

        Raises:
            EntityNotFoundException: Si cliente no existe
        """
        # 1. Validaciones pre-eliminación
        self._before_delete(cliente_id)

        # 2. Eliminar de BD
        success = self.repository.delete(cliente_id, id_field="id_cliente")

        # 3. Post-eliminación
        if success:
            self._after_delete(cliente_id)

        return success

    # ==================== BÚSQUEDAS Y FILTROS ====================

    def contar_clientes(self) -> int:
        """Cuenta total de clientes"""
        return self.repository.count()

    def contar_clientes_por_estado(self, estado_id: str) -> int:
        """Cuenta clientes en un estado específico"""
        return self.repository.contar_por_estado(estado_id)

    def obtener_clientes_por_estado(self, estado_id: str) -> List[Cliente]:
        """Obtiene clientes por estado"""
        return self.repository.find_by_estado(estado_id)

    # ==================== VALIDACIONES (hooks de BaseService) ====================

    def _validate_input(self, data: Dict[str, Any], mode: str = "create") -> List[str]:
        """
        Valida datos de entrada.

        Args:
            data: Datos a validar
            mode: "create" o "update"

        Returns:
            Lista de errores (vacía si válido)
        """
        errors = []

        # En modo CREATE, todos los campos son requeridos
        if mode == "create":
            if not data.get('nombre', '').strip():
                errors.append("Nombre requerido")
            if not data.get('correo', '').strip():
                errors.append("Correo requerido")
            if not data.get('documento', '').strip():
                errors.append("Documento requerido")
            if not data.get('numero', '').strip():
                errors.append("Número requerido")

        # En modo UPDATE, campos son opcionales (pero se validan si vienen)
        if data.get('nombre'):
            if len(data['nombre'].strip()) < 2:
                errors.append("Nombre debe tener al menos 2 caracteres")

        if data.get('correo'):
            if not Cliente._is_valid_email(data['correo']):
                errors.append("Correo inválido")

        if data.get('documento'):
            if len(data['documento'].strip()) < 5:
                errors.append("Documento debe tener al menos 5 caracteres")

        return errors

    def _prepare_data_for_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepara datos antes de insertar"""
        # Crear modelo temporal para normalizar
        cliente = Cliente.from_dict(data)
        cliente.normalizar()

        # Convertir a diccionario para BD
        return {
            'nombre': cliente.nombre,
            'correo': cliente.correo,
            'documento': cliente.documento,
            'numero': cliente.numero,
            'contraseña': data.get('contraseña'),  # En prod, hashear!
            'tipo_cliente_id': data.get('tipo_cliente_id'),
            'estado_cliente_id': data.get('estado_cliente_id'),
            'cuenta_temporal': data.get('cuenta_temporal', False),
            'registro_completo': data.get('registro_completo', False)
        }

    def _prepare_data_for_update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepara datos antes de actualizar"""
        prepared = {}

        if 'nombre' in data:
            prepared['nombre'] = data['nombre'].strip()

        if 'correo' in data:
            prepared['correo'] = data['correo'].strip().lower()

        if 'documento' in data:
            prepared['documento'] = data['documento'].strip()

        if 'numero' in data:
            prepared['numero'] = data['numero'].strip()

        if 'estado_cliente_id' in data:
            prepared['estado_cliente_id'] = data['estado_cliente_id']

        if 'cuenta_temporal' in data:
            prepared['cuenta_temporal'] = data['cuenta_temporal']

        if 'registro_completo' in data:
            prepared['registro_completo'] = data['registro_completo']

        return prepared

    def _after_create(self, cliente: Cliente) -> None:
        """Post-creación: logs, eventos, etc"""
        print(f"✓ Cliente creado: {cliente.id_cliente} - {cliente.nombre}")
        # TODO: Enviar email de bienvenida
        # TODO: Registrar evento en audit log

    def _after_read(self, cliente: Cliente) -> Cliente:
        """Post-lectura: enriquecimiento de datos"""
        # Podrías agregar datos derivados aquí
        return cliente

    def _after_update(self, cliente: Cliente) -> None:
        """Post-actualización"""
        print(f"✓ Cliente actualizado: {cliente.id_cliente}")

    def _before_delete(self, cliente_id: str) -> None:
        """Pre-eliminación: validaciones"""
        # Podrías validar que el cliente no tenga órdenes pendientes, etc
        pass

    def _after_delete(self, cliente_id: str) -> None:
        """Post-eliminación: logs, eventos"""
        print(f"✓ Cliente eliminado: {cliente_id}")
        # TODO: Registrar en audit log
