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
from services.personal_pago_automatico_service import pagar_mensual_automatico

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


def ejecutar_pago_mensual_personal() -> None:
    """Ejecuta el pago mensual automatico del personal (monto configurable, default S/1300)."""
    try:
        resultado = pagar_mensual_automatico()
        logger.info(
            "[Scheduler 08AM] Pago mensual personal ejecutado - procesados=%s pagados=%s omitidos=%s errores=%s",
            resultado.get("procesados"),
            resultado.get("pagados"),
            resultado.get("omitidos"),
            len(resultado.get("errores") or []),
        )
    except Exception as exc:
        logger.error(f"[Scheduler 08AM] Error en pago mensual personal: {exc}")


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

    # Cron: todos los dias a las 8:00 AM para evaluar y ejecutar pagos mensuales de personal.
    scheduler.add_job(
        func=ejecutar_pago_mensual_personal,
        trigger=CronTrigger(hour=8, minute=0, timezone="America/Lima"),
        id="pago_mensual_personal",
        name="Pago mensual automatico personal 8AM",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "[Scheduler] Iniciado - limpieza 1:00 AM y pago mensual personal 8:00 AM (Lima)"
    )
    return scheduler
