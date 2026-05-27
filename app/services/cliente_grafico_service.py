import base64
import io
from calendar import monthrange
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from services.supabase_client import supabase


class ClienteGraficoService:
    @staticmethod
    def obtener_grafico_pagos_mensuales(
        cliente_id: str,
        mes: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            if not cliente_id:
                return {"success": False, "message": "cliente_id es requerido"}

            fecha_inicio, fecha_fin, mes_label = ClienteGraficoService._resolver_mes(mes)
            pagos = ClienteGraficoService._obtener_pagos(cliente_id, fecha_inicio, fecha_fin)

            if not pagos:
                return {
                    "success": True,
                    "data": {
                        "month": mes_label,
                        "image_base64": None,
                        "total_pagado": 0,
                        "dias_con_compra": 0,
                        "operaciones": 0,
                        "puntos": [],
                        "message": "No hay pagos registrados en este mes."
                    }
                }

            puntos = ClienteGraficoService._agrupar_por_dia(
                pagos,
                fecha_inicio.year,
                fecha_inicio.month
            )
            image_base64 = ClienteGraficoService._generar_grafico(puntos, mes_label)
            total_pagado = round(sum(punto["monto"] for punto in puntos), 2)
            dias_con_compra = len([punto for punto in puntos if punto["monto"] > 0])

            return {
                "success": True,
                "data": {
                    "month": mes_label,
                    "image_base64": image_base64,
                    "total_pagado": total_pagado,
                    "dias_con_compra": dias_con_compra,
                    "operaciones": len(pagos),
                    "puntos": puntos,
                    "message": "Grafico generado correctamente."
                }
            }
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    @staticmethod
    def _resolver_mes(mes: Optional[str]) -> Tuple[datetime, datetime, str]:
        meses = {
            1: "Enero",
            2: "Febrero",
            3: "Marzo",
            4: "Abril",
            5: "Mayo",
            6: "Junio",
            7: "Julio",
            8: "Agosto",
            9: "Septiembre",
            10: "Octubre",
            11: "Noviembre",
            12: "Diciembre",
        }
        if mes:
            base = datetime.strptime(mes, "%Y-%m")
        else:
            ahora = datetime.now()
            base = datetime(ahora.year, ahora.month, 1)

        ultimo_dia = monthrange(base.year, base.month)[1]
        fecha_inicio = datetime(base.year, base.month, 1)
        fecha_fin = datetime(base.year, base.month, ultimo_dia)
        nombre_mes = f"{meses[base.month]} {base.year}"
        return fecha_inicio, fecha_fin, nombre_mes

    @staticmethod
    def _obtener_pagos(
        cliente_id: str,
        fecha_inicio: datetime,
        fecha_fin: datetime
    ) -> List[Dict[str, Any]]:
        response = supabase.table("registro_pago").select(
            "fecha, monto"
        ).eq("cliente_id", cliente_id).gte(
            "fecha", fecha_inicio.date().isoformat()
        ).lte(
            "fecha", fecha_fin.date().isoformat()
        ).order("fecha").execute()

        return response.data or []

    @staticmethod
    def _agrupar_por_dia(
        pagos: List[Dict[str, Any]],
        year: int,
        month: int
    ) -> List[Dict[str, Any]]:
        acumulado = {}

        for pago in pagos:
            fecha_pago = pago.get("fecha")
            monto = ClienteGraficoService._to_float(pago.get("monto"))
            if not fecha_pago:
                continue
            dia = int(str(fecha_pago).split("-")[-1])
            acumulado[dia] = round(acumulado.get(dia, 0.0) + monto, 2)

        puntos = []
        for dia in sorted(acumulado.keys()):
            monto = round(acumulado[dia], 2)
            if monto <= 0:
                continue
            puntos.append({
                "dia": dia,
                "label": f"{dia:02d}/{month:02d}",
                "monto": monto
            })

        return puntos

    @staticmethod
    def _generar_grafico(
        puntos: List[Dict[str, Any]],
        mes_label: str
    ) -> str:
        labels = [punto["label"] for punto in puntos]
        montos = [punto["monto"] for punto in puntos]
        maximo = max(montos) if montos else 0

        colores = []
        for monto in montos:
            if monto <= 0:
                colores.append("#dbeafe")
            elif monto == maximo:
                colores.append("#c2410c")
            else:
                colores.append("#0ea5e9")

        fig_width = max(9.2, min(13.5, len(labels) * 1.3))
        fig, ax = plt.subplots(figsize=(fig_width, 5.8), dpi=220)
        fig.patch.set_facecolor("#f8fbfd")
        ax.set_facecolor("#ffffff")

        ax.bar(labels, montos, color=colores, width=0.62)
        ax.set_ylabel("Monto pagado (S/)")
        ax.set_title(f"Pagos registrados en {mes_label}", fontsize=12, pad=14)
        ax.grid(axis="y", linestyle="--", alpha=0.22)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#cbd5e1")
        ax.spines["bottom"].set_color("#cbd5e1")
        ax.tick_params(axis="x", labelrotation=0, labelsize=9, colors="#475569")
        ax.tick_params(axis="y", labelsize=9, colors="#475569")

        legend_handles = [
            Patch(facecolor="#0ea5e9", label="Días con pago"),
            Patch(facecolor="#c2410c", label="Día con mayor monto")
        ]
        ax.legend(handles=legend_handles, title="Referencia", loc="upper right")

        for idx, monto in enumerate(montos):
            if monto > 0:
                ax.text(
                    idx,
                    monto + (maximo * 0.015 if maximo else 1),
                    f"S/ {monto:.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color="#334155"
                )

        fig.tight_layout(pad=1.2)

        buffer = io.BytesIO()
        fig.savefig(
            buffer,
            format="png",
            dpi=220,
            bbox_inches="tight",
            facecolor=fig.get_facecolor()
        )
        plt.close(fig)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("utf-8")

    @staticmethod
    def _to_float(value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0