-- Migración: Agregar columna email a tabla personal
-- Fecha: 2026-06-12
-- Descripción: Agrega el campo email para contacto del personal

ALTER TABLE personal ADD COLUMN IF NOT EXISTS email TEXT;

-- Opcional: descomentar si quieres que email sea único
-- ALTER TABLE personal ADD CONSTRAINT unique_personal_email UNIQUE(email);
