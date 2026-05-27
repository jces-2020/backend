# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify
from services.supabase_client import supabase
from datetime import datetime

uno_signal_bp = Blueprint('uno_signal', __name__, url_prefix='/api/uno-signal')


@uno_signal_bp.route('/registrar-player-id', methods=['POST'])
def registrar_player_id():
    """
    Registra el Player ID de OneSignal del cliente para recibir push notifications
    """
    try:
        data = request.get_json()
        player_id = data.get('player_id')
        dispositivo = data.get('dispositivo', 'flutter')

        if not player_id:
            return jsonify({'error': 'player_id requerido'}), 400

        print(f'[uno_signal_controller] Registrando Player ID: {player_id}')

        # Guardar en Supabase (idempotente: si ya existe player_id, actualiza)
        response = supabase.table('uno_signal_tokens').upsert({
            'player_id': player_id,
            'dispositivo': dispositivo,
            'created_at': datetime.utcnow().isoformat()
        }, on_conflict='player_id').execute()

        print(f'[uno_signal_controller] Player ID registrado: {response.data}')

        return jsonify({
            'mensaje': 'Player ID registrado exitosamente',
            'player_id': player_id
        }), 201

    except Exception as e:
        print(f'[uno_signal_controller] Error registrando Player ID: {str(e)}')
        return jsonify({'error': str(e)}), 500


@uno_signal_bp.route('/player-ids', methods=['GET'])
def get_player_ids():
    """
    DEBUG: Obtener todos los Player IDs registrados
    """
    try:
        response = supabase.table('uno_signal_tokens').select('*').execute()
        player_ids = [row['player_id'] for row in response.data]

        print(f'[uno_signal_controller] Total Player IDs: {len(player_ids)}')

        return jsonify({
            'total': len(player_ids),
            'player_ids': player_ids
        }), 200

    except Exception as e:
        print(f'[uno_signal_controller] Error obteniendo Player IDs: {str(e)}')
        return jsonify({'error': str(e)}), 500
