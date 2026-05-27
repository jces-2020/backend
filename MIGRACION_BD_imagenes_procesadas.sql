-- ============================================================
-- MIGRACION: Crear tabla para almacenar imágenes procesadas
-- ============================================================
-- Ejecutar en Supabase SQL Editor:
-- https://app.supabase.com/project/zoafuvjfzawhvdrwnydo/sql/new

CREATE TABLE IF NOT EXISTS producto_imagenes_procesadas (
  -- ID única
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Relación con producto
  id_producto UUID NOT NULL,
  FOREIGN KEY (id_producto) REFERENCES productos(id_producto) ON DELETE CASCADE,

  -- URLs en Supabase Storage
  imagen_original_url VARCHAR(500),      -- URL imagen original
  imagen_sin_fondo_url VARCHAR(500),     -- URL imagen procesada (sin fondo, PNG)

  -- Metadata del procesamiento
  metadata JSONB DEFAULT '{}'::jsonb,    -- Metadata completa:
                                          -- {
                                          --   "metadata_fondo": {...},
                                          --   "segmentacion": {...},
                                          --   "clasificacion": {...},
                                          --   "tiempo_procesamiento": 2.5,
                                          --   "fecha_procesamiento": "2026-04-26T14:30:00Z"
                                          -- }

  -- Estado del procesamiento
  estado VARCHAR(50) DEFAULT 'pendiente', -- pendiente, procesando, completado, error
  error_mensaje VARCHAR(500),             -- Si estado=error, aquí va el error

  -- Auditoría
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  procesado_en TIMESTAMP,                 -- Cuándo se procesó

  -- Índices para queries frecuentes
  CONSTRAINT estado_check CHECK (estado IN ('pendiente', 'procesando', 'completado', 'error'))
);

-- Crear índices
CREATE INDEX idx_producto_imagenes_id_producto ON producto_imagenes_procesadas(id_producto);
CREATE INDEX idx_producto_imagenes_estado ON producto_imagenes_procesadas(estado);
CREATE INDEX idx_producto_imagenes_created_at ON producto_imagenes_procesadas(created_at DESC);

-- Comentarios
COMMENT ON TABLE producto_imagenes_procesadas IS 'Almacena imágenes procesadas (sin fondo, segmentadas, clasificadas)';
COMMENT ON COLUMN producto_imagenes_procesadas.metadata IS 'Metadata en JSON del procesamiento: fondo, segmentación, clasificación, tiempos, etc';
COMMENT ON COLUMN producto_imagenes_procesadas.estado IS 'Estado: pendiente → procesando → completado (o error)';

-- ============================================================
-- Ejemplo de INSERT (para testing)
-- ============================================================
--
-- INSERT INTO producto_imagenes_procesadas (
--   id_producto,
--   imagen_original_url,
--   imagen_sin_fondo_url,
--   estado,
--   metadata
-- ) VALUES (
--   'ID_DEL_PRODUCTO_AQUI',
--   'https://..../productos/original.jpg',
--   'https://..../productos/procesado.png',
--   'completado',
--   '{
--     "metadata_fondo": {
--       "tamaño_original": [1920, 1080],
--       "formato_salida": "PNG",
--       "tiene_transparencia": true
--     },
--     "segmentacion": {
--       "num_objetos": 2,
--       "confianza_promedio": 0.91
--     },
--     "clasificacion": {
--       "categoria": "vidrio_transparente",
--       "confianza": 0.92
--     },
--     "tiempo_procesamiento": 2.34
--   }'::jsonb
-- );

-- ============================================================
-- Para modificar si ya existe (agregar columnas)
-- ============================================================
--
-- ALTER TABLE producto_imagenes_procesadas ADD COLUMN IF NOT EXISTS estado VARCHAR(50);
-- ALTER TABLE producto_imagenes_procesadas ADD CONSTRAINT estado_check CHECK (estado IN ('pendiente', 'procesando', 'completado', 'error'));
