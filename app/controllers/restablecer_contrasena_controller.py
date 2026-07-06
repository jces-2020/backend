from flask import Blueprint, request, jsonify
import os
import re
from app.services.supabase_client import supabase
from app.repositories.cliente_repository import ClienteRepository

restablecer_contrasena_bp = Blueprint('restablecer_contrasena', __name__)
_repository = ClienteRepository(supabase)


def _email_formato_valido(correo: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', correo or ''))


def _password_reset_redirect() -> str:
    """URL de retorno para recuperación de contraseña desde correo de Supabase."""
    return (os.getenv('FRONTEND_RESET_PASSWORD_URL') or os.getenv('FRONTEND_URL') or 'https://vidriobras.com').rstrip('/') + '/login/reset-password'


def _extraer_auth_user(access_token: str):
    """Obtiene user de Supabase Auth a partir del access_token del enlace."""
    try:
        user_resp = supabase.auth.get_user(access_token)
        user = getattr(user_resp, 'user', None)
        if user is None and isinstance(user_resp, dict):
            user = user_resp.get('user')
        return user
    except Exception:
        return None


@restablecer_contrasena_bp.route('/api/clientes/password-reset/request', methods=['POST'])
def solicitar_reset_password_api():
    """Solicita correo de recuperación vía Supabase Auth."""
    try:
        data = request.get_json() or {}
        correo = (data.get('correo') or '').strip().lower()
        if not correo:
            return jsonify({'success': False, 'message': 'Correo requerido.'}), 400
        if not _email_formato_valido(correo):
            return jsonify({'success': False, 'message': 'Formato de correo inválido.'}), 400

        cliente = _repository.find_by_correo(correo)
        if not cliente:
            return jsonify({'success': False, 'message': 'No existe una cuenta con ese correo.'}), 404

        redirect_to = _password_reset_redirect()
        try:
            supabase.auth.reset_password_email(correo, {'redirect_to': redirect_to})
        except TypeError:
            supabase.auth.reset_password_email(correo)

        return jsonify({'success': True, 'message': 'Correo de recuperación enviado.'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'No se pudo enviar el correo: {str(e)}'}), 500


@restablecer_contrasena_bp.route('/api/clientes/password-reset/confirm', methods=['POST'])
def confirmar_reset_password_api():
    """Confirma nueva contraseña usando access_token del correo de recuperación."""
    try:
        data = request.get_json() or {}
        access_token = (data.get('access_token') or '').strip()
        nueva = (data.get('nueva_contrasena') or '').strip()

        if not access_token:
            return jsonify({'success': False, 'message': 'Falta access_token.'}), 400
        if len(nueva) < 6:
            return jsonify({'success': False, 'message': 'La contraseña debe tener al menos 6 caracteres.'}), 400

        auth_user = _extraer_auth_user(access_token)
        if not auth_user:
            return jsonify({'success': False, 'message': 'Token inválido o expirado.'}), 401

        user_id = (getattr(auth_user, 'id', None) if not isinstance(auth_user, dict) else auth_user.get('id')) or ''
        email = (getattr(auth_user, 'email', None) if not isinstance(auth_user, dict) else auth_user.get('email')) or ''
        email = email.strip().lower()
        if not user_id or not email:
            return jsonify({'success': False, 'message': 'No se pudo identificar al usuario.'}), 400

        supabase.auth.admin.update_user_by_id(user_id, {'password': nueva})

        # Mantener sincronizada la contraseña de la tabla local cliente.
        supabase.table('cliente').update({'contraseña': nueva}).eq('correo', email).execute()

        return jsonify({'success': True, 'message': 'Contraseña restablecida correctamente.'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'No se pudo restablecer la contraseña: {str(e)}'}), 500
