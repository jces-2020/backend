"""
scheduler.py
Tarea programada que corre cada día a la 1:00 AM y elimina las cuentas
de clientes temporales que no completaron su registro.

Un cliente temporal se identifica por:
  cuenta_temporal  = true
  registro_completo = false
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from services.supabase_client import supabase

logger = logging.getLogger(__name__)


def limpiar_cuentas_temporales() -> None:
    """
    Elimina de la tabla 'cliente' todos los registros donde
    cuenta_temporal=true y registro_completo=false.
    Se ejecuta automáticamente a la 1 AM todos los días.
    """
    try:
        resultado = (
            supabase
            .table("cliente")
            .delete()
            .eq("cuenta_temporal", True)
            .eq("registro_completo", False)
            .execute()
        )
        eliminados = len(resultado.data) if resultado.data else 0
        logger.info(f"[Scheduler 1AM] Cuentas temporales eliminadas: {eliminados}")
    except Exception as e:
        logger.error(f"[Scheduler 1AM] Error al limpiar cuentas temporales: {e}")


def iniciar_scheduler() -> BackgroundScheduler:
    """
    Crea y arranca el scheduler en segundo plano.
    Llama esta función UNA SOLA VEZ al iniciar la app Flask.
    Retorna la instancia por si necesitas detenerla manualmente.
    """
    scheduler = BackgroundScheduler(timezone="America/Lima")

    # Cron: todos los días a la 1:00 AM (hora Lima / Perú)
    scheduler.add_job(
        func=limpiar_cuentas_temporales,
        trigger=CronTrigger(hour=1, minute=0, timezone="America/Lima"),
        id="limpiar_cuentas_temporales",
        name="Limpieza diaria cuentas temporales 1AM",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("[Scheduler] Iniciado — limpieza de cuentas temporales programada a la 1:00 AM (Lima)")
    return scheduler
