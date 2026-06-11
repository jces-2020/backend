import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import List, Optional, Union


def _get_config():
    # Preferir variables genéricas SMTP_*; mantener compatibilidad con HOSTINGER_* y EMAIL_FROM
    server = os.getenv('SMTP_SERVER', os.getenv('HOSTINGER_SMTP_HOST', 'smtp.elasticemail.com'))
    port = int(os.getenv('SMTP_PORT', os.getenv('HOSTINGER_SMTP_PORT', '587')))
    user = os.getenv('SMTP_USERNAME', os.getenv('HOSTINGER_SMTP_USER', ''))
    password = os.getenv('SMTP_PASS', os.getenv('HOSTINGER_SMTP_PASS', ''))
    from_email = os.getenv('SMTP_SENDER', os.getenv('EMAIL_FROM', user))

    # Flags: si no se especifica, inferir por puerto (465 -> SSL, 587 -> TLS)
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
        # Opcionalmente incluir Bcc en headers (no siempre necesario)
        msg['Bcc'] = ", ".join(bcc_list)

    if html_body:
        if text_body:
            msg.set_content(text_body)
        else:
            msg.set_content('')
        msg.add_alternative(html_body, subtype='html')
    else:
        msg.set_content(text_body or '')

    # Adjuntos (opcional)
    if attachments:
        for filename, content, maintype, subtype in attachments:
            msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    recipients = to_list + cc_list + bcc_list

    # Envío
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


def send_test_email(to: Optional[str] = None) -> None:
    cfg = _get_config()
    dest = to or cfg['from_email']
    send_email(
        to=dest,
        subject='Prueba de correo desde backend',
        text_body='Este es un correo de prueba enviado desde la aplicación.',
        html_body='<p>Este es un <strong>correo de prueba</strong> enviado desde la aplicación.</p>'
    )
