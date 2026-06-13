from flask import Blueprint, request, jsonify
from services.mailer_service import (
    send_email,
    send_test_email,
    send_payment_notification,
    send_payment_notification_batch,
)
from services.supabase_client import supabase

hostinger_mail_bp = Blueprint('hostinger_mail', __name__, url_prefix='/mail')


@hostinger_mail_bp.route('/send', methods=['POST'])
def send():
    """
    Envío de correo genérico.
    Body JSON esperado:
    {
        "to": "correo@ejemplo.com",         # requerido
        "subject": "Asunto",                # opcional
        "text": "Cuerpo en texto plano",    # opcional
        "html": "<p>Cuerpo HTML</p>",       # opcional
        "cc": "copia@ejemplo.com",          # opcional
        "bcc": "bcc@ejemplo.com"            # opcional
    }
    """
    data = request.get_json(force=True)
    to = data.get('to')
    subject = data.get('subject', 'Sin asunto')
    text = data.get('text')
    html = data.get('html')
    cc = data.get('cc')
    bcc = data.get('bcc')

    if not to:
        return jsonify({'ok': False, 'error': 'Falta campo "to"'}), 400

    try:
        send_email(to=to, subject=subject, text_body=text, html_body=html, cc=cc, bcc=bcc)
        return jsonify({'ok': True, 'msg': 'Correo enviado correctamente'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@hostinger_mail_bp.route('/send-payment', methods=['POST'])
def send_payment():
    """
    Envía notificación de pago (sueldo o bono) a un personal.
    Body JSON esperado:
    {
        "to": "correo@ejemplo.com",   # requerido
        "nombre": "Juan Pérez",       # requerido
        "monto": 1500.00,             # requerido
        "tipo": "mensual"             # opcional: "mensual" o "bono" (default: "mensual")
    }
    """
    data = request.get_json(force=True)
    to = data.get('to')
    nombre = data.get('nombre')
    monto = data.get('monto')
    tipo = data.get('tipo', 'mensual')

    if not to:
        return jsonify({'ok': False, 'error': 'Falta campo "to"'}), 400
    if not nombre:
        return jsonify({'ok': False, 'error': 'Falta campo "nombre"'}), 400
    if monto is None:
        return jsonify({'ok': False, 'error': 'Falta campo "monto"'}), 400

    try:
        monto_float = float(monto)
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'El campo "monto" debe ser un número'}), 400

    if tipo not in ('mensual', 'bono'):
        return jsonify({'ok': False, 'error': 'El campo "tipo" debe ser "mensual" o "bono"'}), 400

    try:
        send_payment_notification(to=to, nombre=nombre, monto=monto_float, tipo=tipo)
        return jsonify({'ok': True, 'msg': f'Notificación de {tipo} enviada a {to}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@hostinger_mail_bp.route('/send-payment-all', methods=['POST'])
def send_payment_all():
    """Envía notificación de pago a todo el personal con email registrado."""
    data = request.get_json(force=True)
    monto = data.get('monto')
    tipo = data.get('tipo', 'mensual')

    if monto is None:
        return jsonify({'ok': False, 'error': 'Falta campo "monto"'}), 400

    try:
        monto_float = float(monto)
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'El campo "monto" debe ser un número'}), 400

    if tipo not in ('mensual', 'bono'):
        return jsonify({'ok': False, 'error': 'El campo "tipo" debe ser "mensual" o "bono"'}), 400

    try:
        result = supabase.table('personal').select('nombre, correo').execute()
        personal_list = result.data or []
        recipients = [
            { 'correo': p.get('correo'), 'nombre': p.get('nombre', '') }
            for p in personal_list
            if p.get('correo')
        ]

        if not recipients:
            return jsonify({'ok': False, 'error': 'No se encontró personal con correo registrado'}), 400

        stats = send_payment_notification_batch(recipients, monto_float, tipo, group_message=True)
        return jsonify({
            'ok': stats['failed'] == 0,
            'sent': stats['sent'],
            'failed': stats['failed'],
            'errors': stats['errors'],
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@hostinger_mail_bp.route('/test', methods=['GET'])
def test_send():
    """Envía un email de prueba a la dirección configurada en EMAIL_FROM / SMTP_SENDER."""
    try:
        send_test_email()
        return jsonify({'ok': True, 'msg': 'Correo de prueba enviado'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500