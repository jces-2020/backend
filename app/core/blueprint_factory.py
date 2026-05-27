"""
Factory Pattern para registro automático de blueprints.
Elimina la necesidad de imports manuales en main.py.

Patrón: Factory Method (refactoring.guru)
Beneficio: Agregar feature = crear archivo, listo. Sin editar main.py
"""
import os
import importlib
from pathlib import Path
from flask import Flask, Blueprint
from typing import List


def auto_register_blueprints(app: Flask, controllers_path: str = None) -> None:
    """
    Registra automáticamente todos los blueprints desde la carpeta controllers.

    Cómo usar:
        auto_register_blueprints(app)

    Requisito: Cada archivo de controller debe tener una variable llamada 'bp' o terminar con '_bp'

    Args:
        app: Aplicación Flask
        controllers_path: Path a la carpeta de controllers (default: app/controllers)

    Ejemplo de estructura:
        controllers/
        ├── cliente_controller.py     # Must export 'cliente_bp'
        ├── producto_controller.py    # Must export 'producto_bp'
        └── servicio_controller.py    # Must export 'servicio_bp'
    """

    # Determinar path de controllers
    if controllers_path is None:
        base_path = Path(__file__).parent.parent  # app/
        controllers_path = base_path / "controllers"
    else:
        controllers_path = Path(controllers_path)

    if not controllers_path.exists():
        print(f"[!] Controllers path no existe: {controllers_path}")
        return

    # Encontrar todos los archivos .py
    controller_files = list(controllers_path.glob("*_controller.py"))
    print(f"\n[*] Auto-registrando {len(controller_files)} blueprints...")

    registered = 0
    errors = []

    for file_path in sorted(controller_files):
        module_name = file_path.stem  # Nombre sin extensión
        try:
            # Importar dinámicamente
            module = importlib.import_module(f"controllers.{module_name}")

            # Buscar blueprint (por convención: nombre_bp)
            blueprint_name = f"{module_name.replace('_controller', '')}_bp"
            if hasattr(module, blueprint_name):
                blueprint = getattr(module, blueprint_name)
                app.register_blueprint(blueprint)
                registered += 1
                print(f"  [OK] {module_name} -> {blueprint_name}")
            # Fallback 1: buscar 'bp'
            elif hasattr(module, 'bp'):
                app.register_blueprint(module.bp)
                registered += 1
                print(f"  [OK] {module_name} -> bp")
            # Fallback 2: buscar cualquier Blueprint en el módulo
            else:
                found = [
                    v for v in vars(module).values()
                    if isinstance(v, Blueprint)
                ]
                if found:
                    app.register_blueprint(found[0])
                    registered += 1
                    print(f"  [OK] {module_name} -> {found[0].name} (auto-detected)")
                else:
                    errors.append(f"{module_name}: No se encontró blueprint")

        except ImportError as e:
            errors.append(f"{module_name}: Error de importación - {str(e)}")
        except Exception as e:
            errors.append(f"{module_name}: Error - {str(e)}")

    print(f"\n[SUCCESS] Registrados: {registered} blueprints")

    if errors:
        print(f"\n[!] Errores ({len(errors)}):")
        for error in errors:
            print(f"   - {error}")

    print()


def get_all_blueprints(controllers_path: str = None) -> List:
    """
    Devuelve lista de todos los blueprints disponibles (útil para debugging).

    Returns:
        Lista de tuplas (nombre_archivo, nombre_blueprint)
    """
    if controllers_path is None:
        base_path = Path(__file__).parent.parent
        controllers_path = base_path / "controllers"
    else:
        controllers_path = Path(controllers_path)

    blueprints = []
    for file_path in sorted(controllers_path.glob("*_controller.py")):
        module_name = file_path.stem
        try:
            module = importlib.import_module(f"controllers.{module_name}")
            blueprint_name = f"{module_name.replace('_controller', '')}_bp"

            if hasattr(module, blueprint_name):
                blueprints.append((module_name, blueprint_name))
            elif hasattr(module, 'bp'):
                blueprints.append((module_name, 'bp'))
        except:
            pass

    return blueprints
