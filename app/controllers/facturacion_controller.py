"""
Controller de Facturacion Electronica
Endpoints:

POST   /api/facturacion/emitir
GET    /api/facturacion/listar/<cliente_id>
GET    /api/facturacion/pdf/<comprobante_id>
GET    /api/facturacion/xml/<comprobante_id>
"""

from flask import Blueprint, request, jsonify
from services.facturacion_service import FacturacionService
from services.supabase_client import supabase

bp = Blueprint(
    'facturacion',
    __name__,
    url_prefix='/api/facturacion'
)


# ============================================
# EMITIR COMPROBANTE
# ============================================

@bp.route('/emitir', methods=['POST'])
def emitir_comprobante():

    try:

        datos = request.get_json()

        if not datos:
            return jsonify({
                "success": False,
                "message": "No se enviaron datos"
            }), 400


        # ========================================
        # VALIDAR CLIENTE
        # ========================================

        cliente_data = datos.get("cliente_data")

        if not cliente_data:
            return jsonify({
                "success": False,
                "message": "cliente_data es requerido"
            }), 400


        documento = cliente_data.get("documento")

        if not documento:
            return jsonify({
                "success": False,
                "message": "Documento requerido"
            }), 400


        if not documento.isdigit():
            return jsonify({
                "success": False,
                "message": "Documento debe ser numerico"
            }), 400


        if len(documento) not in (8, 11):
            return jsonify({
                "success": False,
                "message": "Documento debe ser DNI (8) o RUC (11)"
            }), 400


        # ========================================
        # VALIDAR PRODUCTOS
        # ========================================

        productos = datos.get("productos")

        if not productos or len(productos) == 0:
            return jsonify({
                "success": False,
                "message": "Debe enviar al menos un producto"
            }), 400


        # ========================================
        # VALIDAR TOTALES
        # ========================================

        totales = datos.get("totales")

        if not totales:
            return jsonify({
                "success": False,
                "message": "Totales requeridos"
            }), 400


        # ========================================
        # DETERMINAR TIPO Y GENERAR COMPROBANTE
        # ========================================

        es_boleta = len(documento) == 8

        if es_boleta:
            resultado = FacturacionService.generar_boleta(
                cliente_data,
                productos,
                totales
            )
        else:
            resultado = FacturacionService.generar_factura(
                cliente_data,
                productos,
                totales
            )


        # ========================================
        # VALIDAR RESPUESTA APISPERU
        # ========================================

        if not resultado.get("success"):

            return jsonify({
                "success": False,
                "message": resultado.get("error"),
                "status_code": resultado.get("status_code")
            }), 500


        # ========================================
        # GUARDAR EN BASE DE DATOS
        # ========================================

        try:

            comprobante_insert = supabase.table(
                "comprobante_electronico"
            ).insert({

                "tipo": resultado.get("tipo"),

                "serie": resultado.get("serie"),

                "correlativo": resultado.get("correlativo"),

                "cliente_documento": documento,

                "xml_firmado": resultado.get("xml"),

                "pdf_base64": resultado.get("pdf"),

            }).execute()


            if comprobante_insert.data:

                resultado["comprobante_id"] = \
                    comprobante_insert.data[0].get("id_comprobante")

        except Exception as e:

            print("Error guardando comprobante:", str(e))


        # ========================================
        # RESPUESTA FINAL
        # ========================================

        return jsonify({

            "success": True,

            "message":
                f'{resultado.get("tipo")} '
                f'{resultado.get("serie")}-'
                f'{resultado.get("correlativo")} generada',

            "data": resultado

        }), 200


    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================
# LISTAR COMPROBANTES
# ============================================

@bp.route('/listar/<cliente_documento>', methods=['GET'])
def listar(cliente_documento):

    try:

        res = supabase.table(
            "comprobante_electronico"
        ).select("*").eq(
            "cliente_documento",
            cliente_documento
        ).execute()


        return jsonify({
            "success": True,
            "data": res.data
        })


    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================
# DESCARGAR PDF
# ============================================

@bp.route('/pdf/<comprobante_id>', methods=['GET'])
def pdf(comprobante_id):

    try:

        res = supabase.table(
            "comprobante_electronico"
        ).select(
            "pdf_base64"
        ).eq(
            "id_comprobante",
            comprobante_id
        ).execute()


        if not res.data:

            return jsonify({
                "success": False,
                "message": "No encontrado"
            }), 404


        return jsonify({

            "success": True,

            "pdf": res.data[0]["pdf_base64"]

        })


    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================
# DESCARGAR XML
# ============================================

@bp.route('/xml/<comprobante_id>', methods=['GET'])
def xml(comprobante_id):

    try:

        res = supabase.table(
            "comprobante_electronico"
        ).select(
            "xml_firmado"
        ).eq(
            "id_comprobante",
            comprobante_id
        ).execute()


        if not res.data:

            return jsonify({
                "success": False,
                "message": "No encontrado"
            }), 404


        return jsonify({

            "success": True,

            "xml": res.data[0]["xml_firmado"]

        })


    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# ============================================
# GENERAR PDF
# ============================================

@bp.route('/generar-pdf', methods=['POST'])
def generar_pdf():
    """
    Genera PDF a partir de payload de factura/boleta
    """
    try:
        payload = request.get_json()
        
        if not payload:
            return jsonify({
                "success": False,
                "message": "Payload requerido"
            }), 400

        resultado = FacturacionService.generar_pdf(payload)

        if not resultado.get("success"):
            return jsonify({
                "success": False,
                "message": resultado.get("error")
            }), 500

        return jsonify({
            "success": True,
            "pdf": resultado.get("pdf")
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
