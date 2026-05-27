# -*- coding: utf-8 -*-
"""
Script de Verificación de Estructura
Ejecutar en el VPS: python verify_structure.py
"""
import os
import sys
from pathlib import Path

def verificar_archivos():
    """Verifica que todos los archivos necesarios existan"""

    base_path = Path(__file__).parent.parent

    archivos_requeridos = {
        'Core': [
            'core/__init__.py',
            'core/exceptions.py',
            'core/base_model.py',
            'core/base_repository.py',
            'core/base_service.py',
            'core/blueprint_factory.py',
        ],
        'Models': [
            'models/__init__.py',
            'models/cliente.py',
            'models/producto.py',
        ],
        'Repositories': [
            'repositories/__init__.py',
            'repositories/cliente_repository.py',
            'repositories/producto_repository.py',
        ],
        'Services': [
            'services/__init__.py',
            'services/cliente_service.py',
            'services/producto_service.py',
        ],
        'Controllers': [
            'controllers/cliente_api_controller.py',
            'controllers/producto_api_controller.py',
        ]
    }

    print("=" * 60)
    print("VERIFICACIÓN DE ESTRUCTURA")
    print("=" * 60)

    total_archivos = 0
    archivos_ok = 0
    errores = []

    for categoria, archivos in archivos_requeridos.items():
        print(f"\n{categoria}:")
        for archivo in archivos:
            ruta = base_path / archivo
            total_archivos += 1

            if ruta.exists():
                tamaño = ruta.stat().st_size
                print(f"  ✓ {archivo:45} ({tamaño:,} bytes)")
                archivos_ok += 1
            else:
                print(f"  ✗ {archivo:45} FALTA")
                errores.append(f"{archivo}: No existe")

    print("\n" + "=" * 60)
    print(f"Resultado: {archivos_ok}/{total_archivos} archivos OK")
    print("=" * 60)

    if errores:
        print("\nERRORES ENCONTRADOS:")
        for error in errores:
            print(f"  - {error}")
        return False
    else:
        print("\nTODOS LOS ARCHIVOS ESTÁN EN SU LUGAR ✓")
        return True

def verificar_imports():
    """Intenta importar los módulos para verificar que no hay errores"""

    print("\n" + "=" * 60)
    print("VERIFICACIÓN DE IMPORTS")
    print("=" * 60)

    imports_a_verificar = [
        ('app.core', 'Core module'),
        ('app.models.cliente', 'Cliente model'),
        ('app.models.producto', 'Producto model'),
        ('app.repositories', 'Repositories'),
        ('app.services.cliente_service', 'ClienteService'),
        ('app.services.producto_service', 'ProductoService'),
        ('app.controllers.cliente_api_controller', 'Cliente API Controller'),
        ('app.controllers.producto_api_controller', 'Producto API Controller'),
    ]

    ok = 0
    errores = []

    for modulo, nombre in imports_a_verificar:
        try:
            __import__(modulo)
            print(f"  ✓ {nombre:40} ({modulo})")
            ok += 1
        except ImportError as e:
            print(f"  ✗ {nombre:40} ERROR")
            errores.append(f"{nombre}: {str(e)}")
        except Exception as e:
            print(f"  ✗ {nombre:40} ERROR")
            errores.append(f"{nombre}: {str(e)}")

    print(f"\nImports: {ok}/{len(imports_a_verificar)} OK")

    if errores:
        print("\nERRORES EN IMPORTS:")
        for error in errores:
            print(f"  - {error}")
        return False
    else:
        print("\nTODOS LOS IMPORTS SON VÁLIDOS ✓")
        return True

def main():
    print("\n" + "=" * 60)
    print("VERIFICACIÓN COMPLETA DE ARQUITECTURA")
    print("=" * 60)

    # Verificar archivos
    archivos_ok = verificar_archivos()

    # Verificar imports
    try:
        imports_ok = verificar_imports()
    except Exception as e:
        print(f"\n✗ Error durante verificación de imports: {str(e)}")
        imports_ok = False

    # Resumen final
    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)

    if archivos_ok and imports_ok:
        print("\n✓ ARQUITECTURA VERIFICADA Y LISTA PARA PRODUCCIÓN")
        return 0
    else:
        print("\n✗ ERRORES ENCONTRADOS - REVISAR ARRIBA")
        return 1

if __name__ == '__main__':
    sys.exit(main())
