import re

from flask import Blueprint, jsonify, request

from controllers.clientes_controller import verify_jwt
from services.registro_pago_comprobante_service import RegistroPagoComprobanteService
from services.supabase_client import supabase


registro_pago_comprobante_bp = Blueprint(
    "registro_pago_comprobante",
    __name__,
    url_prefix="/api/registro-pago"
)


@registro_pago_comprobante_bp.route("/guardar-comprobante", methods=["POST"])
def guardar_comprobante_registro_pago():
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401

        token = auth_header.split(" ", 1)[1]
        token_payload = verify_jwt(token)
        if not token_payload:
            return jsonify({"success": False, "message": "Token invalido"}), 401

        data = request.get_json() or {}

        cliente_id = token_payload.get("sub")
        if not cliente_id:
            return jsonify({"success": False, "message": "cliente_id no encontrado en token"}), 401
        payload_facturacion = data.get("payload")
        monto = data.get("monto")
        tipo_comprobante = data.get("tipo_comprobante")

        if payload_facturacion is None:
            return jsonify({"success": False, "message": "payload es requerido"}), 400

        if monto is None:
            return jsonify({"success": False, "message": "monto es requerido"}), 400

        if not tipo_comprobante:
            return jsonify({"success": False, "message": "tipo_comprobante es requerido"}), 400

        try:
            monto_num = float(monto)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "monto invalido"}), 400

        resultado = RegistroPagoComprobanteService.guardar_comprobante(
            payload=payload_facturacion,
            tipo_comprobante=tipo_comprobante,
            monto=monto_num,
            cliente_id=cliente_id,
            registro_pago_id=data.get("registro_pago_id"),
            metodo_pago_id=data.get("metodo_pago_id"),
            serie=data.get("serie"),
            correlativo=data.get("correlativo")
        )

        if not resultado.get("success"):
            return jsonify({
                "success": False,
                "message": resultado.get("message") or "No se pudo guardar comprobante"
            }), 500

        return jsonify({
            "success": True,
            "message": resultado.get("message"),
            "data": {
                "documento_url": resultado.get("documento_url"),
                "storage_path": resultado.get("storage_path"),
                "registro_pago": resultado.get("registro_pago"),
                "pdf": resultado.get("pdf")
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@registro_pago_comprobante_bp.route("/listar", methods=["GET"])
def listar_comprobantes_cliente():
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401

        token = auth_header.split(" ", 1)[1]
        token_payload = verify_jwt(token)
        if not token_payload:
            return jsonify({"success": False, "message": "Token invalido"}), 401

        cliente_id = token_payload.get("sub")
        if not cliente_id:
            return jsonify({"success": False, "message": "cliente_id no encontrado en token"}), 401

        fecha_inicio = (request.args.get("fecha_inicio") or "").strip()
        fecha_fin = (request.args.get("fecha_fin") or "").strip()

        iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if fecha_inicio and not iso_pattern.match(fecha_inicio):
            return jsonify({"success": False, "message": "fecha_inicio invalida"}), 400
        if fecha_fin and not iso_pattern.match(fecha_fin):
            return jsonify({"success": False, "message": "fecha_fin invalida"}), 400
        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            return jsonify({"success": False, "message": "fecha_inicio no puede ser mayor a fecha_fin"}), 400

        consulta = supabase.table("registro_pago").select(
            "id_registro, fecha, monto, documento"
        ).eq("cliente_id", cliente_id)

        if fecha_inicio:
            consulta = consulta.gte("fecha", fecha_inicio)
        if fecha_fin:
            consulta = consulta.lte("fecha", fecha_fin)

        resultado = consulta.order("fecha", desc=True).execute()

        # Consolidar posibles duplicados (uno sin documento y otro con PDF)
        # para el mismo cliente/fecha/monto, priorizando el registro con documento.
        consolidado = {}
        for reg in resultado.data or []:
            fecha_raw = str(reg.get("fecha") or "")
            try:
                monto_key = round(float(reg.get("monto") or 0), 2)
            except (TypeError, ValueError):
                monto_key = 0.0
            firma = f"{fecha_raw}|{monto_key:.2f}"

            actual = consolidado.get(firma)
            if not actual:
                consolidado[firma] = reg
                continue

            doc_actual = str(actual.get("documento") or "").strip()
            doc_nuevo = str(reg.get("documento") or "").strip()
            if doc_nuevo and not doc_actual:
                consolidado[firma] = reg

        comprobantes = []
        for reg in consolidado.values():
            documento_url = reg.get("documento") or ""

            if "BOLETAS" in documento_url.upper():
                tipo = "Boleta"
            elif "FACTURAS" in documento_url.upper():
                tipo = "Factura"
            else:
                tipo = "Desconocido"

            comprobantes.append({
                "id_registro": reg.get("id_registro"),
                "tipo": tipo,
                "fecha": reg.get("fecha"),
                "monto": reg.get("monto"),
                "documento_url": documento_url
            })

        return jsonify({
            "success": True,
            "comprobantes": comprobantes
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@registro_pago_comprobante_bp.route("/<id_registro>", methods=["DELETE"])
def eliminar_comprobante_cliente(id_registro):
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token no proporcionado"}), 401

        token = auth_header.split(" ", 1)[1]
        token_payload = verify_jwt(token)
        if not token_payload:
            return jsonify({"success": False, "message": "Token invalido"}), 401

        cliente_id = token_payload.get("sub")
        if not cliente_id:
            return jsonify({"success": False, "message": "cliente_id no encontrado en token"}), 401

        registro_res = supabase.table("registro_pago").select(
            "id_registro, cliente_id, documento"
        ).eq("id_registro", id_registro).limit(1).execute()

        if not registro_res.data:
            return jsonify({"success": False, "message": "Comprobante no encontrado"}), 404

        registro = registro_res.data[0]
        if registro.get("cliente_id") != cliente_id:
            return jsonify({"success": False, "message": "No autorizado para eliminar este comprobante"}), 403

        documento_url = registro.get("documento") or ""
        marker = "/storage/v1/object/public/COMPROBANTE/"
        if marker in documento_url:
            storage_path = documento_url.split(marker, 1)[1]
            if storage_path:
                try:
                    supabase.storage.from_("COMPROBANTE").remove([storage_path])
                except Exception:
                    # Si falla eliminación en storage, no bloquea eliminación del registro
                    pass

        supabase.table("registro_pago").delete().eq("id_registro", id_registro).execute()

        return jsonify({
            "success": True,
            "message": "Comprobante eliminado correctamente"
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
