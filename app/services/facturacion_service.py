import requests
import os
from datetime import datetime
from typing import Optional


class FacturacionService:
    """
    Servicio de Facturación Electrónica APISPeru
    """

    # URL CORRECTA (el ambiente beta/producción se define al crear la empresa)
    URL = "https://facturacion.apisperu.com/api/v1/invoice/send"

    # TOKEN desde .env (token de empresa)
    TOKEN = os.getenv("APISPERU_TOKEN")
    RUC = os.getenv("RUC", "20614120798")

    @staticmethod
    def generar_boleta(cliente, productos, totales=None):
        """
        Genera una boleta electrónica (tipoDoc=03)
        Usa la misma estructura que funcionó en Postman
        """
        return FacturacionService._generar_comprobante(
            cliente=cliente,
            productos=productos,
            totales=totales,
            tipo_doc="03",
            serie="B001"
        )

    @staticmethod
    def generar_factura(cliente, productos, totales=None):
        """
        Genera una factura electrónica (tipoDoc=01)
        """
        return FacturacionService._generar_comprobante(
            cliente=cliente,
            productos=productos,
            totales=totales,
            tipo_doc="01",
            serie="F001"
        )

    @staticmethod
    def _generar_comprobante(cliente, productos, totales, tipo_doc, serie):
        """
        Método interno que genera el payload EXACTAMENTE como en Postman
        """
        try:
            # VALIDACIÓN TOKEN
            if not FacturacionService.TOKEN:
                return {
                    "success": False,
                    "error": "APISPERU_TOKEN no configurado en .env"
                }

            if not productos or len(productos) == 0:
                return {
                    "success": False,
                    "error": "No hay productos"
                }

            # CALCULAR TOTALES (precio_unitario incluye IGV)
            if totales:
                mto_oper_gravadas = float(totales.get("subtotal", 0))
                mto_igv = float(totales.get("igv", 0))
                mto_imp_venta = float(totales.get("total", 0))
            else:
                # Base imponible sin IGV
                mto_oper_gravadas = 0.0
                for p in productos:
                    cantidad = int(p.get("cantidad", 1))
                    precio_unitario = float(p.get("precio_unitario", 0))
                    valor_unitario = round(precio_unitario / 1.18, 2)
                    mto_oper_gravadas += round(valor_unitario * cantidad, 2)
                mto_oper_gravadas = round(mto_oper_gravadas, 2)
                mto_igv = round(mto_oper_gravadas * 0.18, 2)
                mto_imp_venta = round(mto_oper_gravadas + mto_igv, 2)

            # CORRELATIVO (SUNAT: max 8 digitos)
            correlativo = f"{int(datetime.now().timestamp()) % 100000000:08d}"

            # FECHA EMISIÓN
            fecha_emision = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-05:00")

            # =============================
            # PAYLOAD IDÉNTICO A POSTMAN
            # =============================
            payload = {
                "ublVersion": "2.1",
                "tipoOperacion": "0101",
                "tipoDoc": tipo_doc,
                "serie": serie,
                "correlativo": correlativo,
                "fechaEmision": fecha_emision,
                "formaPago": {
                    "moneda": "PEN",
                    "tipo": "Contado"
                },
                "tipoMoneda": "PEN",

                # CLIENTE
                "client": {
                    "tipoDoc": "6" if len(str(cliente.get("documento", ""))) == 11 else "1",
                    "numDoc": int(cliente.get("documento", 0)),
                    "rznSocial": cliente.get("nombre", "Cliente"),
                    "address": {
                        "direccion": cliente.get("direccion", "Lima"),
                        "provincia": cliente.get("provincia", "LIMA"),
                        "departamento": cliente.get("departamento", "LIMA"),
                        "distrito": cliente.get("distrito", "LIMA"),
                        "ubigeo": cliente.get("ubigeo", "150101"),
                        "ubigueo": cliente.get("ubigeo", "150101")
                    }
                },

                # EMPRESA (sin usuarioSOL ni claveSOL - el token ya los tiene)
                "company": {
                    "ruc": int(FacturacionService.RUC),
                    "razonSocial": "VIDRIOBRAS ELESCANO E.I.R.L.",
                    "nombreComercial": "ELESCANITO",
                    "address": {
                        "direccion": "JR. COMUNEROS NRO. 292 (ENTRE ICA Y LEANDRA TORRES)",
                        "provincia": "JUNIN",
                        "departamento": "HUANCAYO",
                        "distrito": "HUANCAYO",
                        "ubigeo": "150101",
                        "ubigueo": "150101"
                    }
                },

                # TOTALES
                "mtoOperGravadas": mto_oper_gravadas,
                "mtoIGV": mto_igv,
                "valorVenta": mto_oper_gravadas,
                "totalImpuestos": mto_igv,
                "subTotal": mto_imp_venta,
                "mtoImpVenta": mto_imp_venta,

                # DETALLE DE PRODUCTOS
                "details": [],

                # LEYENDAS
                "legends": [
                    {
                        "code": "1000",
                        "value": f"SON {FacturacionService._numero_a_letras(mto_imp_venta)} CON 00/100 SOLES"
                    }
                ]
            }

            # CONSTRUIR DETAILS
            for producto in productos:
                cantidad = int(producto.get("cantidad", 1))
                precio_unitario = float(producto.get("precio_unitario", 0))

                # Calcular valores base (sin IGV)
                mto_valor_unitario = round(precio_unitario / 1.18, 2)
                mto_valor_venta = round(mto_valor_unitario * cantidad, 2)
                igv = round(mto_valor_venta * 0.18, 2)

                payload["details"].append({
                    "codProducto": producto.get("codigo", "P001"),
                    "unidad": "NIU",
                    "descripcion": producto.get("descripcion", "Producto"),
                    "cantidad": cantidad,
                    "mtoValorUnitario": mto_valor_unitario,
                    "mtoValorVenta": mto_valor_venta,
                    "mtoBaseIgv": mto_valor_venta,
                    "porcentajeIgv": 18,
                    "igv": igv,
                    "tipAfeIgv": 10,
                    "totalImpuestos": igv,
                    "mtoPrecioUnitario": precio_unitario
                })

            # HEADERS
            headers = {
                "Authorization": f"Bearer {FacturacionService.TOKEN}",
                "Content-Type": "application/json"
            }

            # ENVIAR REQUEST
            print("\n" + "="*50)
            print("ENVIANDO A APISPERU")
            print("="*50)
            print(f"URL: {FacturacionService.URL}")
            print(f"Tipo: {tipo_doc} - Serie: {serie}")
            print("="*50)

            response = requests.post(
                FacturacionService.URL,
                json=payload,
                headers=headers,
                timeout=30
            )

            print(f"STATUS: {response.status_code}")
            print(f"RESPUESTA: {response.text[:500]}")

            # VALIDAR RESPUESTA
            if response.status_code in (200, 201):
                resp_data = response.json()
                
                return {
                    "success": True,
                    "tipo": "Boleta" if tipo_doc == "03" else "Factura",
                    "serie": serie,
                    "correlativo": correlativo,
                    "xml": resp_data.get("xml"),
                    "hash": resp_data.get("hash"),
                    "cdr": resp_data.get("sunatResponse", {}).get("cdrZip"),
                    "sunat_response": resp_data.get("sunatResponse"),
                    "payload": payload,
                    "data": resp_data
                }

            # ERROR
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }

        except Exception as e:
            print(f"ERROR INTERNO: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def _numero_a_letras(numero):
        """Convierte número a letras (simplificado)"""
        # Para producción usar librería como num2words
        return f"{int(numero)}"

    @staticmethod
    def generar_pdf(payload):
        """
        Genera PDF a partir del payload de factura/boleta
        """
        try:
            if not FacturacionService.TOKEN:
                return {
                    "success": False,
                    "error": "APISPERU_TOKEN no configurado"
                }

            headers = {
                "Authorization": f"Bearer {FacturacionService.TOKEN}",
                "Content-Type": "application/json"
            }

            # Usar endpoint /invoice/pdf
            url = "https://facturacion.apisperu.com/api/v1/invoice/pdf"

            print(f"\n[PDF] Generando PDF desde APISPeru...")
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )

            print(f"[PDF] Status: {response.status_code}")

            if response.status_code in (200, 201):
                # APISPeru devuelve el PDF como base64 o binario
                if response.headers.get('content-type') == 'application/pdf':
                    # Si es PDF binario, convertir a base64
                    import base64
                    pdf_base64 = base64.b64encode(response.content).decode('utf-8')
                    return {
                        "success": True,
                        "pdf": pdf_base64
                    }
                else:
                    # Si es JSON
                    resp_data = response.json()
                    return {
                        "success": True,
                        "pdf": resp_data.get("pdf")
                    }

            return {
                "success": False,
                "error": response.text
            }

        except Exception as e:
            print(f"[PDF] ERROR: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }