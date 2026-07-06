from flask import Blueprint, jsonify, request
from datetime import date

from services.personal_service import (
    get_all_personal,
    get_personal_by_id,
    create_personal,
    delete_personal,
    get_bonos_personal,
    get_all_bonos,
    create_bono,
    delete_bono,
    add_bono_to_personal,
    remove_bono_from_personal,
    create_pago,
    create_gasto_personal_bono,
    create_gasto_personal,
    upload_cv_pdf,
)
from services.personal_pago_automatico_service import (
    enviar_comprobante_pago_email,
    pagar_mensual_automatico,
    pagar_bono_y_notificar,
)

personal_admin_bp = Blueprint("personal_admin_bp", __name__)


@personal_admin_bp.route("/api/personal", methods=["GET"])
def list_personal():
    """Lista todo el personal."""
    personal = get_all_personal()
    return jsonify({"success": True, "data": personal})


@personal_admin_bp.route("/api/personal", methods=["POST"])
def create_personal_endpoint():
    """Crea un nuevo registro de personal."""
    data = request.get_json() or {}
    nombre = (data.get("nombre") or "").strip()
    codigo = (data.get("codigo") or "").strip()
    tipo_personal_id = data.get("tipo_personal_id")
    correo = (data.get("correo") or "").strip().lower()
    cv = data.get("cv")
    fecha_nacimiento = data.get("fecha_nacimiento")

    if not nombre:
        return jsonify({"success": False, "message": "Nombre requerido"}), 400
    if not codigo:
        return jsonify({"success": False, "message": "Codigo requerido"}), 400

    personal = create_personal(
        nombre=nombre,
        codigo=codigo,
        tipo_personal_id=tipo_personal_id,
        correo=correo or None,
        cv=cv,
        fecha_nacimiento=fecha_nacimiento,
    )
    if personal:
        return jsonify({"success": True, "message": "Personal creado", "data": personal}), 201
    return jsonify({"success": False, "message": "Error al crear personal"}), 500


@personal_admin_bp.route("/api/personal/upload-cv", methods=["POST"])
def upload_cv():
    """Sube un archivo PDF de CV a Storage."""
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "No file selected"}), 400

    # Validar que sea PDF
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"success": False, "message": "Solo se aceptan archivos PDF"}), 400

    try:
        # Leer contenido del archivo
        file_content = file.read()
        if not file_content:
            return jsonify({"success": False, "message": "El archivo est\u00e1 vac\u00edo"}), 400

        # Subir a Storage
        url = upload_cv_pdf(file_content, file.filename)
        if url:
            return jsonify({"success": True, "data": {"url": url}})
        return jsonify({"success": False, "message": "Error al subir el archivo"}), 500
    except Exception as exc:  # noqa: BLE001
        print(f"[personal_admin_controller] error uploading CV: {exc}")
        return jsonify({"success": False, "message": "Error al procesar el archivo"}), 500
def get_personal_detail(personal_id):
    """Obtiene detalles de un personal espec\u00edfico."""
    personal = get_personal_by_id(personal_id)
    if not personal:
        return jsonify({"success": False, "message": "Personal no encontrado"}), 404
    return jsonify({"success": True, "data": personal})


@personal_admin_bp.route("/api/personal/<personal_id>", methods=["DELETE"])
def delete_personal_endpoint(personal_id):
    """Elimina un registro de personal."""
    success = delete_personal(personal_id)
    if success:
        return jsonify({"success": True, "message": "Personal eliminado"})
    return jsonify({"success": False, "message": "Error al eliminar personal"}), 500


@personal_admin_bp.route("/api/personal/<personal_id>/bonos", methods=["GET"])
def list_bonos_personal(personal_id):
    """Lista los bonos asignados a un personal."""
    bonos = get_bonos_personal(personal_id)
    return jsonify({"success": True, "data": bonos})


@personal_admin_bp.route("/api/bonos", methods=["GET"])
def list_all_bonos():
    """Lista todos los bonos disponibles."""
    bonos = get_all_bonos()
    return jsonify({"success": True, "data": bonos})


@personal_admin_bp.route("/api/bonos", methods=["POST"])
def create_bono_endpoint():
    """Crea un bono nuevo en el catalogo."""
    data = request.get_json() or {}
    descripcion = (data.get("descripcion") or "").strip()
    if not descripcion:
        return jsonify({"success": False, "message": "Descripcion requerida"}), 400

    bono = create_bono(descripcion)
    if bono:
        return jsonify({"success": True, "message": "Bono creado", "data": bono}), 201
    return jsonify({"success": False, "message": "Error al crear bono"}), 500


@personal_admin_bp.route("/api/bonos/<bono_id>", methods=["DELETE"])
def delete_bono_endpoint(bono_id):
    """Elimina un bono del catalogo."""
    success = delete_bono(bono_id)
    if success:
        return jsonify({"success": True, "message": "Bono eliminado"})
    return jsonify({"success": False, "message": "Error al eliminar bono"}), 500


@personal_admin_bp.route("/api/personal/<personal_id>/bonos", methods=["POST"])
def add_bono(personal_id):
    """Asigna un bono a un personal."""
    data = request.get_json()
    bono_id = data.get("bono_id")
    
    if not bono_id:
        return jsonify({"success": False, "message": "bono_id requerido"}), 400
    
    success = add_bono_to_personal(personal_id, bono_id)
    if success:
        return jsonify({"success": True, "message": "Bono asignado"})
    return jsonify({"success": False, "message": "Error al asignar bono"}), 500


@personal_admin_bp.route("/api/personal/<personal_id>/bonos/<bono_id>", methods=["DELETE"])
def remove_bono(personal_id, bono_id):
    """Elimina un bono de un personal."""
    success = remove_bono_from_personal(personal_id, bono_id)
    if success:
        return jsonify({"success": True, "message": "Bono eliminado"})
    return jsonify({"success": False, "message": "Error al eliminar bono"}), 500


@personal_admin_bp.route("/api/personal/<personal_id>/pago", methods=["POST"])
def register_pago(personal_id):
    """Registra un pago mensual para el personal (tipo: personal)."""
    data = request.get_json()
    monto = data.get("monto")
    fecha_pago = data.get("fecha") or str(date.today())
    caja_id = data.get("caja_id")
    
    if monto is None:
        return jsonify({"success": False, "message": "Monto requerido"}), 400

    try:
        monto_float = float(monto)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Monto invalido"}), 400

    if monto_float <= 0:
        return jsonify({"success": False, "message": "Monto debe ser mayor a 0"}), 400

    gasto = create_gasto_personal(monto_float, fecha_pago, caja_id)
    pago = create_pago(personal_id, monto_float, fecha_pago)

    if pago and gasto:
        personal = get_personal_by_id(personal_id) or {}
        correo_result = {"ok": False, "message": "Sin correo"}
        correo = (personal.get("correo") or "").strip().lower()
        if correo:
            correo_result = enviar_comprobante_pago_email(
                to_email=correo,
                nombre=(personal.get("nombre") or "Colaborador"),
                monto=monto_float,
                tipo="mensual",
                fecha_pago=fecha_pago,
                detalle="Pago mensual",
            )

        return jsonify({
            "success": True,
            "message": "Pago mensual registrado",
            "data": {
                "pago": pago,
                "gasto": gasto,
                "correo": correo_result,
            },
        })

    return jsonify({"success": False, "message": "Error al registrar pago"}), 500


@personal_admin_bp.route("/api/personal/<personal_id>/pago-bono", methods=["POST"])
def register_pago_bono(personal_id):
    """Registra un pago de bono para el personal (tipo: personal bono)."""
    data = request.get_json()
    monto = data.get("monto")
    fecha_pago = data.get("fecha") or str(date.today())
    caja_id = data.get("caja_id")
    
    if monto is None:
        return jsonify({"success": False, "message": "Monto requerido"}), 400

    try:
        monto_float = float(monto)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Monto invalido"}), 400

    if monto_float <= 0:
        return jsonify({"success": False, "message": "Monto debe ser mayor a 0"}), 400

    gasto = create_gasto_personal_bono(monto_float, fecha_pago, caja_id)
    pago = create_pago(personal_id, monto_float, fecha_pago)

    if pago and gasto:
        personal = get_personal_by_id(personal_id) or {}
        correo_result = {"ok": False, "message": "Sin correo"}
        correo = (personal.get("correo") or "").strip().lower()
        if correo:
            correo_result = enviar_comprobante_pago_email(
                to_email=correo,
                nombre=(personal.get("nombre") or "Colaborador"),
                monto=monto_float,
                tipo="bono",
                fecha_pago=fecha_pago,
                detalle="Pago de bono",
            )

        return jsonify({
            "success": True,
            "message": "Bono pagado",
            "data": {
                "pago": pago,
                "gasto": gasto,
                "correo": correo_result,
            },
        })

    return jsonify({"success": False, "message": "Error al pagar bono"}), 500


@personal_admin_bp.route("/api/personal/pagos/auto-ejecutar", methods=["POST"])
def ejecutar_pago_automatico():
    """Ejecuta manualmente el pago mensual automatico (util para pruebas/admin)."""
    try:
        data = request.get_json(silent=True) or {}
        fecha = (data.get("fecha") or "").strip() or None
        resultado = pagar_mensual_automatico(fecha)
        return jsonify(resultado), 200
    except Exception as exc:
        return jsonify({"success": False, "message": f"Error ejecutando pago automatico: {exc}"}), 500


@personal_admin_bp.route("/api/personal/bonos/asignar-pagar-notificar", methods=["POST"])
def asignar_pagar_notificar_bono():
    """Asigna bono, registra pago como gasto y envia comprobante por correo."""
    data = request.get_json() or {}
    personal_id = (data.get("personal_id") or "").strip()
    bono_id = (data.get("bono_id") or "").strip()
    monto = data.get("monto")
    fecha_pago = (data.get("fecha") or str(date.today())).strip()

    if not personal_id:
        return jsonify({"success": False, "message": "personal_id requerido"}), 400
    if not bono_id:
        return jsonify({"success": False, "message": "bono_id requerido"}), 400
    if monto is None:
        return jsonify({"success": False, "message": "Monto requerido"}), 400

    try:
        monto_float = float(monto)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Monto invalido"}), 400

    if monto_float <= 0:
        return jsonify({"success": False, "message": "Monto debe ser mayor a 0"}), 400

    try:
        resultado = pagar_bono_y_notificar(
            personal_id=personal_id,
            bono_id=bono_id,
            monto=monto_float,
            fecha_pago=fecha_pago,
        )
        return jsonify(resultado), 200
    except Exception as exc:
        return jsonify({"success": False, "message": f"Error procesando bono: {exc}"}), 500
