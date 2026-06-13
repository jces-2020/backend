# ✉️ Migración: Agregar Campo Email a Personal

## Resumen
Se agrega la columna `email` a la tabla `personal` para almacenar el correo electrónico de cada empleado.

## Estado Actual
- ✅ Backend actualizado para leer/escribir `email`
- ✅ Frontend ya está leyendo el campo `email`
- ⏳ **Falta:** Ejecutar la migración SQL en la base de datos

## Cómo Ejecutar

### Opción 1: Usar Supabase Dashboard (Recomendado)
1. Ir a [Supabase Dashboard](https://app.supabase.com/)
2. Seleccionar tu proyecto
3. Ir a **SQL Editor** → **New Query**
4. Copiar el contenido de `migrations/001_add_email_to_personal.sql`
5. Ejecutar el query

### Opción 2: Usar Script de Migración
```bash
# En la terminal, desde la carpeta backend/
python -m app.scripts.run_migrations
```

## SQL Que Se Ejecuta
```sql
ALTER TABLE personal ADD COLUMN IF NOT EXISTS email TEXT;
```

## Después de la Migración
Una vez ejecutado:
- ✅ El frontend leerá automáticamente el `email` de nuevos/existentes personal
- ✅ Al crear un personal, se guardará el `email` en la DB
- ✅ El campo `correo` del formulario ya mapea a `email` en la BD

## Datos Existentes
Los registros de personal ya existentes **no tendrán email** hasta que se agregue manualmente o se cree uno nuevo.

## Opcional: Hacer Email Único
Si deseas que no haya emails duplicados:
```sql
ALTER TABLE personal ADD CONSTRAINT unique_personal_email UNIQUE(email);
```

Descomenta la línea en `migrations/001_add_email_to_personal.sql` si lo necesitas.
