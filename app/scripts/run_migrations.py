#!/usr/bin/env python3
"""
Script para ejecutar migraciones SQL en Supabase.
Ejecuta todos los archivos .sql en la carpeta migrations/
"""

from services.supabase_client import supabase
import os
from pathlib import Path

def run_migrations():
    """Ejecuta todos los scripts SQL en la carpeta migrations."""
    migrations_dir = Path(__file__).parent / "migrations"
    
    if not migrations_dir.exists():
        print(f"❌ Carpeta de migraciones no encontrada: {migrations_dir}")
        return False
    
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        print("⚠️  No se encontraron archivos .sql en migrations/")
        return True
    
    print(f"🔄 Ejecutando {len(sql_files)} migraciones...")
    
    for sql_file in sql_files:
        try:
            with open(sql_file, "r", encoding="utf-8") as f:
                sql_content = f.read()
            
            print(f"\n📄 Ejecutando: {sql_file.name}")
            result = supabase.rpc("exec_sql", {"sql": sql_content}).execute()
            print(f"✅ {sql_file.name} ejecutada correctamente")
            
        except Exception as e:
            print(f"❌ Error en {sql_file.name}: {e}")
            return False
    
    print("\n✨ ¡Todas las migraciones completadas!")
    return True

if __name__ == "__main__":
    success = run_migrations()
    exit(0 if success else 1)
