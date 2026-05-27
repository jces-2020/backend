"""
Excepciones personalizadas para la aplicación.
Facilita manejo uniforme de errores en toda la app.
"""


class AppException(Exception):
    """Excepción base de la aplicación"""
    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(self.message)


class EntityNotFoundException(AppException):
    """Se lanza cuando una entidad no es encontrada"""
    def __init__(self, entity: str, identifier: str):
        message = f"{entity} con ID '{identifier}' no encontrado"
        super().__init__(message, code=404)


class InvalidDataException(AppException):
    """Se lanza cuando los datos no son válidos"""
    def __init__(self, message: str):
        super().__init__(f"Datos inválidos: {message}", code=400)


class DuplicateEntityException(AppException):
    """Se lanza cuando se intenta crear una entidad duplicada"""
    def __init__(self, entity: str, field: str, value: str):
        message = f"{entity} con {field}='{value}' ya existe"
        super().__init__(message, code=409)


class UnauthorizedException(AppException):
    """Se lanza cuando el usuario no está autenticado"""
    def __init__(self, message: str = "No autenticado"):
        super().__init__(message, code=401)


class ForbiddenException(AppException):
    """Se lanza cuando el usuario no tiene permisos"""
    def __init__(self, message: str = "Acceso denegado"):
        super().__init__(message, code=403)


class RepositoryException(AppException):
    """Se lanza cuando hay error en la capa de datos"""
    def __init__(self, message: str):
        super().__init__(f"Error de repositorio: {message}", code=500)
