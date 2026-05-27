from flask import Blueprint, request, jsonify
from services.compra_service import buscar_cliente_por_documento, guardar_flujo_compra
from controllers.clientes_controller import _build_jwt_for_cliente

compra_api = Blueprint('compra_api', __name__)


@compra_api.route('/api/compra/verificar-cliente', methods=['GET'])
def api_verificar_cliente():
    try:
        documento = (request.args.get('documento') or '').strip()
        if not documento:
            return jsonify({"success": False, "message": "Documento requerido"}), 400

        cliente = buscar_cliente_por_documento(documento)
        if cliente:
            return jsonify({
                "success": True,
                "registrado": True,
                "cliente": {
                    "id_cliente": cliente.get("id_cliente"),
                    "nombre": cliente.get("nombre"),
                    "documento": cliente.get("documento"),
                    "correo": cliente.get("correo")
                }
            }), 200

        return jsonify({"success": True, "registrado": False, "cliente": None}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@compra_api.route('/api/compra/realizar', methods=['POST'])
def api_realizar_compra():
    try:
        data = request.get_json() or {}
        documento = data.get('documento')
        productos = data.get('productos', [])
        cortes = data.get('cortes', [])
        metodo_pago = data.get('metodo_pago', '')
        nombre_api_peru = data.get('nombre_api_peru', '')
        if not documento or (not productos and not cortes):
            return jsonify({"success": False, "message": "Faltan datos"}), 400

        cliente = buscar_cliente_por_documento(documento)
        resultado = guardar_flujo_compra(cliente, productos, cortes, metodo_pago, documento, nombre_api_peru)

        # Soporta retorno dict (nuevo) o bool (legado)
        ok = resultado.get("ok") if isinstance(resultado, dict) else bool(resultado)
        if ok:
            resp = {"success": True}
            if isinstance(resultado, dict) and resultado.get("cuenta_temporal"):
                resp["cuenta_temporal"] = True
                resp["correo_temporal"]    = resultado["correo_temporal"]
                resp["contrasena_temporal"] = resultado["contrasena_temporal"]
                resp["jwt_temporal"]       = resultado["jwt_temporal"]
                resp["cliente_id"]         = resultado.get("cliente_id")
            else:
                # Cliente registrado: generar JWT del cliente para que el frontend
                # pueda usarlo en guardar-comprobante
                cliente_actualizado = buscar_cliente_por_documento(documento)
                if cliente_actualizado:
                    try:
                        resp["cliente_jwt"] = _build_jwt_for_cliente(cliente_actualizado)
                        resp["cliente_id"] = cliente_actualizado.get("id_cliente")
                    except Exception:
                        pass
            return jsonify(resp), 200
        return jsonify({"success": False, "message": "Error al guardar"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
