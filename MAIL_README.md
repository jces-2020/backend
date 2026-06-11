Instrucciones rápidas para configurar envío de correo (Hostinger)

1) Copia `backend/.env.example` a `backend/.env` y completa las variables:

- `HOSTINGER_SMTP_HOST` (ej: smtp.hostinger.com)
- `HOSTINGER_SMTP_PORT` (ej: 587 o 465)
- `HOSTINGER_SMTP_USER` (tu cuenta SMTP)
- `HOSTINGER_SMTP_PASS` (contraseña SMTP o token)
- `EMAIL_FROM` (dirección que aparecerá como remitente)
- `HOSTINGER_SMTP_USE_SSL` (1 si usas SSL en puerto 465)
- `HOSTINGER_SMTP_USE_TLS` (1 si usas STARTTLS, típico en puerto 587)

2) Ejecutar la app (desde `backend`):

```bash
pip install -r requirements.txt
python -m app.main
```

3) Endpoints de prueba (la app auto-registra blueprints):

- POST /mail/send
  - Body JSON: { "to": "dest@example.com", "subject":"Hola", "text":"Hola mundo", "html":"<b>Hola</b>" }

- GET /mail/test
  - Envía un correo de prueba a `EMAIL_FROM`.

4) Notas:
- Asegúrate que Hostinger permita conexiones SMTP desde tu servidor / IP.
- Para evitar problemas, utiliza credenciales SMTP específicas (no siempre la contraseña del panel).
