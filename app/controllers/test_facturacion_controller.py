from flask import Blueprint, render_template, request, jsonify
from services.facturacion_service import FacturacionService

test_facturacion_bp = Blueprint(
    'test_facturacion_bp',
    __name__
)

# ===============================
# FORMULARIO
# ===============================

@test_facturacion_bp.route('/test-facturacion')
def formulario():

    print("[CONTROLLER] Abriendo formulario test-facturacion")

    return render_template(
        'test_facturacion.html'
    )

# ===============================
# API EMISION
# ===============================

@test_facturacion_bp.route(
    '/api/test-facturacion',
    methods=['POST']
)
def emitir():

    try:

        print("\n==============================")
        print("CONTROLLER: INICIO EMISION")
        print("==============================")

        data = request.get_json()

        tipo = data.get("tipo_comprobante")

        cliente = {
            "nombre": data.get("nombre"),
            "documento": data.get("documento"),
            "direccion": data.get("direccion"),
            "provincia": data.get("provincia"),
            "departamento": data.get("departamento"),
            "distrito": data.get("distrito"),
            "ubigeo": data.get("ubigeo"),
            "correo": data.get("correo")
        }

        productos = data.get("productos", [])

        print("Tipo:", tipo)
        print("Cliente:", cliente)
        print("Productos:", productos)

        # ===============================
        # EMITIR
        # ===============================

        if tipo == "factura":
            respuesta = FacturacionService.generar_factura(
                cliente,
                productos,
                None  # totales calculados automáticamente
            )
        else:
            respuesta = FacturacionService.generar_boleta(
                cliente,
                productos,
                None  # totales calculados automáticamente
            )

        print("\n==============================")
        print("RESPUESTA APISPERU:")
        print(respuesta)
        print("==============================")

        # ===============================
        # ERROR
        # ===============================

        if not respuesta.get("success"):

            return jsonify({

                "success": False,

                "error": respuesta.get("error"),

                "respuesta_completa": respuesta

            }), 500

        # ===============================
        # DEVOLVER JSON CON XML Y PDF
        # ===============================
        
        xml = respuesta.get("xml")
        
        if not xml:
            return jsonify({
                "success": False,
                "error": "No se generó XML"
            }), 500

        # Intentar generar PDF (opcional)
        resultado_json = {
            "success": True,
            "tipo": respuesta.get("tipo"),
            "serie": respuesta.get("serie"),
            "correlativo": respuesta.get("correlativo"),
            "hash": respuesta.get("hash"),
            "xml": xml,
            "payload": respuesta.get("payload"),
            "sunat_response": respuesta.get("sunat_response"),
            "mensaje": f"{respuesta.get('tipo')} {respuesta.get('serie')}-{respuesta.get('correlativo')} generada exitosamente"
        }

        return jsonify(resultado_json), 200

    except Exception as e:

        print("\n==============================")
        print("ERROR CONTROLLER:")
        print(str(e))
        print("==============================")

        return jsonify({

            "success": False,

            "error": str(e)

        }), 500
