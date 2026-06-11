from flask import Blueprint, request, jsonify
from services.mailer_service import send_email, send_test_email

hostinger_mail_bp = Blueprint('hostinger_mail', __name__, url_prefix='/mail')


@hostinger_mail_bp.route('/send', methods=['POST'])
def send():
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
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@hostinger_mail_bp.route('/test', methods=['GET'])
def test_send():
    # Envia un email de prueba a la dirección configurada en EMAIL_FROM
    try:
        send_test_email()
        return jsonify({'ok': True, 'msg': 'Correo de prueba enviado'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
