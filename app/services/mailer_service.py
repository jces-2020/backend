import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import List, Optional, Union


def _get_config():
    server = os.getenv('SMTP_SERVER', os.getenv('HOSTINGER_SMTP_HOST', 'smtp.hostinger.com'))
    port = int(os.getenv('SMTP_PORT', os.getenv('HOSTINGER_SMTP_PORT', '465')))
    user = os.getenv('SMTP_USERNAME', os.getenv('HOSTINGER_SMTP_USER', ''))
    password = os.getenv('SMTP_PASS', os.getenv('HOSTINGER_SMTP_PASS', ''))
    from_email = os.getenv('SMTP_SENDER', os.getenv('EMAIL_FROM', user))

    def _bool_env(name, default=False):
        v = os.getenv(name)
        if v is None:
            return default
        return str(v).strip().lower() in ('1', 'true', 'yes', 'si')

    use_ssl = _bool_env('SMTP_USE_SSL', default=(port == 465)) or _bool_env('HOSTINGER_SMTP_USE_SSL', default=(port == 465))
    use_tls = _bool_env('SMTP_USE_TLS', default=(port == 587)) or _bool_env('HOSTINGER_SMTP_USE_TLS', default=(port == 587))

    return {
        'host': server,
        'port': port,
        'user': user,
        'password': password,
        'from_email': from_email,
        'use_ssl': use_ssl,
        'use_tls': use_tls,
    }


def send_email(
    to: Union[str, List[str]],
    subject: str,
    text_body: Optional[str] = None,
    html_body: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None,
    attachments: Optional[List[tuple]] = None,
):
    """
    Envía un correo mediante el SMTP configurado (Hostinger compatible).

    - `to`, `cc`, `bcc` pueden ser string o lista de strings.
    - `attachments` es una lista de tuplas: (filename, content_bytes, maintype, subtype).
    """

    cfg = _get_config()

    if not cfg['user'] or not cfg['password']:
        raise RuntimeError('Faltan credenciales SMTP en variables de entorno')

    def _ensure_list(v):
        if not v:
            return []
        return v if isinstance(v, list) else [v]

    to_list = _ensure_list(to)
    cc_list = _ensure_list(cc)
    bcc_list = _ensure_list(bcc)

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = cfg['from_email']
    msg['To'] = ", ".join(to_list)
    if cc_list:
        msg['Cc'] = ", ".join(cc_list)
    if bcc_list:
        msg['Bcc'] = ", ".join(bcc_list)

    if html_body:
        if text_body:
            msg.set_content(text_body)
        else:
            msg.set_content('')
        msg.add_alternative(html_body, subtype='html')
    else:
        msg.set_content(text_body or '')

    if attachments:
        for filename, content, maintype, subtype in attachments:
            msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    recipients = to_list + cc_list + bcc_list

    if cfg['use_ssl']:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg['host'], cfg['port'], context=context) as server:
            server.login(cfg['user'], cfg['password'])
            server.send_message(msg, from_addr=cfg['from_email'], to_addrs=recipients)
    else:
        with smtplib.SMTP(cfg['host'], cfg['port']) as server:
            server.ehlo()
            if cfg['use_tls']:
                server.starttls()
                server.ehlo()
            server.login(cfg['user'], cfg['password'])
            server.send_message(msg, from_addr=cfg['from_email'], to_addrs=recipients)


def send_payment_notification(to: str, nombre: str, monto: float, tipo: str = "mensual") -> None:
    """
    Envía una notificación de pago al personal.
    tipo puede ser "mensual" o "bono"
    """
    from datetime import date

    fecha_str = date.today().strftime("%d/%m/%Y")

    if tipo == "bono":
        asunto = "Notificación de pago de bono"
        titulo = "¡Bono pagado!"
        descripcion = f"Se ha registrado el pago de tu <strong>bono</strong> por un monto de <strong>S/ {monto:.2f}</strong>."
    else:
        asunto = "Notificación de pago de sueldo"
        titulo = "¡Sueldo pagado!"
        descripcion = f"Se ha registrado el pago de tu <strong>remuneración mensual</strong> por un monto de <strong>S/ {monto:.2f}</strong>."

    html_body = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{asunto}</title>
    </head>
    <body style="margin:0;padding:0;background-color:#f4f6f9;font-family:Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0;">
        <tr>
          <td align="center">
            <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
              <!-- Header -->
              <tr>
                <td style="background:#4f46e5;padding:32px 40px;text-align:center;">
                  <div style="font-size:36px;margin-bottom:8px;">💼</div>
                  <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px;">{titulo}</h1>
                </td>
              </tr>
              <!-- Body -->
              <tr>
                <td style="padding:36px 40px;">
                  <p style="margin:0 0 16px;color:#374151;font-size:16px;">Hola, <strong>{nombre}</strong> 👋</p>
                  <p style="margin:0 0 24px;color:#6b7280;font-size:15px;line-height:1.6;">
                    {descripcion}
                  </p>
                  <!-- Info card -->
                  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;margin-bottom:28px;">
                    <tr>
                      <td style="padding:20px 24px;">
                        <table width="100%" cellpadding="0" cellspacing="0">
                          <tr>
                            <td style="color:#6b7280;font-size:13px;padding-bottom:10px;">FECHA DE PAGO</td>
                            <td style="color:#111827;font-size:13px;font-weight:600;text-align:right;padding-bottom:10px;">{fecha_str}</td>
                          </tr>
                          <tr>
                            <td style="color:#6b7280;font-size:13px;padding-bottom:10px;">CONCEPTO</td>
                            <td style="color:#111827;font-size:13px;font-weight:600;text-align:right;padding-bottom:10px;">{"Bono" if tipo == "bono" else "Remuneración mensual"}</td>
                          </tr>
                          <tr>
                            <td style="border-top:1px solid #e5e7eb;padding-top:12px;color:#374151;font-size:15px;font-weight:700;">MONTO</td>
                            <td style="border-top:1px solid #e5e7eb;padding-top:12px;color:#4f46e5;font-size:18px;font-weight:800;text-align:right;">S/ {monto:.2f}</td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>
                  <p style="margin:0;color:#9ca3af;font-size:12px;line-height:1.5;">
                    Este es un mensaje automático generado por el sistema. Por favor no respondas a este correo.
                  </p>
                </td>
              </tr>
              <!-- Footer -->
              <tr>
                <td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:20px 40px;text-align:center;">
                  <p style="margin:0;color:#9ca3af;font-size:12px;">© {date.today().year} Sistema de Gestión de Personal</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """

    text_body = (
        f"Hola {nombre},\n\n"
        f"{'Tu bono ha' if tipo == 'bono' else 'Tu sueldo mensual ha'} sido pagado correctamente.\n"
        f"Monto: S/ {monto:.2f}\n"
        f"Fecha: {fecha_str}\n\n"
        f"Este es un mensaje automático."
    )

    send_email(to=to, subject=asunto, text_body=text_body, html_body=html_body)


def send_test_email(to: Optional[str] = None) -> None:
    cfg = _get_config()
    dest = to or cfg['from_email']
    send_email(
        to=dest,
        subject='Prueba de correo desde backend',
        text_body='Este es un correo de prueba enviado desde la aplicación.',
        html_body='<p>Este es un <strong>correo de prueba</strong> enviado desde la aplicación.</p>'
    )