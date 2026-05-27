# -*- coding: utf-8 -*-
"""
Core module - Contiene clases base y utilidades fundamentales
"""
from .exceptions import (
    AppException,
    EntityNotFoundException,
    InvalidDataException,
    DuplicateEntityException,
    UnauthorizedException,
    ForbiddenException,
    RepositoryException
)
from .base_model import BaseModel
from .base_repository import BaseRepository
from .base_service import BaseService
from .blueprint_factory import auto_register_blueprints, get_all_blueprints

__all__ = [
    'AppException',
    'EntityNotFoundException',
    'InvalidDataException',
    'DuplicateEntityException',
    'UnauthorizedException',
    'ForbiddenException',
    'RepositoryException',
    'BaseModel',
    'BaseRepository',
    'BaseService',
    'auto_register_blueprints',
    'get_all_blueprints'
]
