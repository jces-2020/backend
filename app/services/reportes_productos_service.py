"""
Servicio para reportes de productos usado por el controlador Flutter.
"""
import uuid
from typing import Any, Dict, List, Optional
from app.services.supabase_client import supabase


def registrar_creacion_producto(producto_id: str, producto: Dict[str, Any]) -> bool:
    try:
        from datetime import datetime
        reporte = {
            'id_reporte': str(uuid.uuid4()),
            'tipo': 'CREAR',
            'producto_id': producto_id,
            'datos_anteriores': None,
            'datos_nuevos': producto,
            'fecha_cambio': datetime.utcnow().isoformat() + 'Z'
        }
        resp = supabase.table('reportes_productos').insert(reporte).execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        return err is None
    except Exception as e:
        print(f"[reportes_productos_service] registrar_creacion_producto: {e}")
        return False


def registrar_edicion_producto(producto_id: str, datos_anteriores: Dict[str, Any], datos_nuevos: Dict[str, Any]) -> bool:
    try:
        from datetime import datetime
        reporte = {
            'id_reporte': str(uuid.uuid4()),
            'tipo': 'EDITAR',
            'producto_id': producto_id,
            'datos_anteriores': datos_anteriores,
            'datos_nuevos': datos_nuevos,
            'fecha_cambio': datetime.utcnow().isoformat() + 'Z'
        }
        resp = supabase.table('reportes_productos').insert(reporte).execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        return err is None
    except Exception as e:
        print(f"[reportes_productos_service] registrar_edicion_producto: {e}")
        return False


def registrar_eliminacion_producto(producto_id: str, datos_anteriores: Dict[str, Any]) -> bool:
    try:
        from datetime import datetime
        reporte = {
            'id_reporte': str(uuid.uuid4()),
            'tipo': 'ELIMINAR',
            'producto_id': producto_id,
            'datos_anteriores': datos_anteriores,
            'datos_nuevos': None,
            'fecha_cambio': datetime.utcnow().isoformat() + 'Z'
        }
        resp = supabase.table('reportes_productos').insert(reporte).execute()
        err = getattr(resp, 'error', None) if resp is not None else None
        return err is None
    except Exception as e:
        print(f"[reportes_productos_service] registrar_eliminacion_producto: {e}")
        return False


def obtener_reportes(limite: int = 100, offset: int = 0, tipo: Optional[str] = None, producto_id: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        query = supabase.table('reportes_productos').select('*')
        if tipo:
            query = query.eq('tipo', tipo)
        if producto_id:
            query = query.eq('producto_id', producto_id)

        query = query.order('fecha_cambio', desc=True).range(offset, offset + limite - 1)
        resp = query.execute()
        data = getattr(resp, 'data', []) or []
        return data
    except Exception as e:
        print(f"[reportes_productos_service] obtener_reportes: {e}")
        return []


def obtener_resumen_reportes(dias: int = 30) -> Dict[str, int]:
    try:
        # Si la tabla no tiene fecha parsable, obtener todo y contar en Python
        reportes = supabase.table('reportes_productos').select('tipo').execute()
        data = getattr(reportes, 'data', []) or []

        resumen = {'CREAR': 0, 'EDITAR': 0, 'ELIMINAR': 0, 'TOTAL': 0}
        for r in data:
            t = (r.get('tipo') or '').upper()
            if t in resumen:
                resumen[t] += 1
            resumen['TOTAL'] += 1

        return resumen
    except Exception as e:
        print(f"[reportes_productos_service] obtener_resumen_reportes: {e}")
        return {'CREAR': 0, 'EDITAR': 0, 'ELIMINAR': 0, 'TOTAL': 0}
