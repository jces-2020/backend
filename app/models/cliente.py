"""
Modelo Cliente - Define estructura, validación y transformación de datos.

Responsabilidades:
- Estructura de datos del cliente
- Validaciones
- Conversión a/desde diccionarios
- Cálculos derivados (si hay)
"""
from typing import Dict, Any, List, Optional
from app.core import BaseModel
import re


class Cliente(BaseModel):
    """
    Modelo de Cliente.

    Atributos:
        id_cliente: UUID único
        nombre: Nombre completo del cliente
        correo: Email (único)
        documento: Número de documento
        numero: Número telefónico o referencia
        contraseña: Hash de contraseña (NUNCA en texto plano en prod)
        tipo_cliente_id: FK a tipo_documento
        estado_cliente_id: FK a estado_cliente
        cuenta_temporal: Boolean
    """

    def __init__(
        self,
        id_cliente: str,
        nombre: str,
        correo: str,
        documento: str,
        numero: str,
        contraseña: str = None,
        tipo_cliente_id: str = None,
        estado_cliente_id: str = None,
        cuenta_temporal: bool = False
    ):
        super().__init__()
        self.id_cliente = id_cliente
        self.nombre = nombre
        self.correo = correo
        self.documento = documento
        self.numero = numero
        self.contraseña = contraseña
        self.tipo_cliente_id = tipo_cliente_id
        self.estado_cliente_id = estado_cliente_id
        self.cuenta_temporal = cuenta_temporal

    def validate(self) -> tuple[bool, List[str]]:
        """
        Valida los datos del cliente.

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Validar nombre
        if not self.nombre or len(self.nombre.strip()) < 2:
            errors.append("Nombre debe tener al menos 2 caracteres")

        # Validar correo
        if not self._is_valid_email(self.correo):
            errors.append("Correo inválido")

        # Validar documento
        if not self.documento or len(self.documento.strip()) < 5:
            errors.append("Documento debe tener al menos 5 caracteres")

        # Validar número
        if not self.numero or len(self.numero.strip()) < 1:
            errors.append("Número requerido")

        return (len(errors) == 0, errors)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario (para JSON)"""
        return {
            "id_cliente": self.id_cliente,
            "nombre": self.nombre,
            "correo": self.correo,
            "documento": self.documento,
            "numero": self.numero,
            # NO incluir contraseña en respuestas públicas
            "tipo_cliente_id": self.tipo_cliente_id,
            "estado_cliente_id": self.estado_cliente_id,
            "cuenta_temporal": self.cuenta_temporal,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    def to_dict_completo(self) -> Dict[str, Any]:
        """Diccionario completo (solo para respuestas internas/admin)"""
        return {
            **self.to_dict(),
            "contraseña_hash": self.contraseña  # Mostrar solo a admin
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Cliente':
        """Crea instancia desde diccionario (de BD o API)"""
        return cls(
            id_cliente=data.get("id_cliente"),
            nombre=(data.get("nombre") or "").strip(),
            correo=(data.get("correo") or "").strip().lower(),
            documento=(data.get("documento") or "").strip(),
            numero=(data.get("numero") or "").strip(),
            contraseña=data.get("contraseña"),
            tipo_cliente_id=data.get("tipo_cliente_id"),
            estado_cliente_id=data.get("estado_cliente_id"),
            cuenta_temporal=data.get("cuenta_temporal", False)
        )

    # ==================== HELPERS ====================

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Valida formato de correo"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def es_activo(self) -> bool:
        """Verifica si el cliente está activo"""
        # Asumir que estado_cliente_id de "activo" es conocido
        # En prod, hacer query para obtener nombre del estado
        return self.estado_cliente_id is not None

    def tiene_cuenta_temporal(self) -> bool:
        """Verifica si tiene acceso temporal"""
        return bool(self.cuenta_temporal)

    def normalizar(self) -> None:
        """Normaliza datos (trim, lowercase, etc)"""
        self.nombre = (self.nombre or "").strip()
        self.correo = (self.correo or "").strip().lower()
        self.documento = (self.documento or "").strip()
        self.numero = (self.numero or "").strip()
