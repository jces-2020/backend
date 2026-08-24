# -*- coding: utf-8 -*-
"""
Controlador REST para notificaciones de servicio/entrega (tabla 'notificacion').

Expone /api/notificaciones, consumido por la app móvil
(flutter_application_1/lib/services/notificacion_service.dart) para poblar
la campanita de la pantalla de Servicios.
"""
from flask import Blueprint, jsonify, request
from app.services.notificacion_service import (
    crear_notificacion,
    obtener_notificaciones,
    obtener_notificacion_por_id,
    actualizar_estado_notificacion,
)

notificacion_bp = Blueprint('notificacion', __name__, url_prefix='/api/notificaciones')


@notificacion_bp.route('', methods=['GET'])
def listar_notificaciones():
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        estado_id = request.args.get('estado_id')
        id_cliente = request.args.get('id_cliente')
        tipo = request.args.get('tipo')
        venta_id = request.args.get('venta_id')

        data = obtener_notificaciones(
            limite=limit,
            offset=offset,
            estado_id=estado_id,
            id_cliente=id_cliente,
            tipo=tipo,
            venta_id=venta_id,
        )
        return jsonify({'success': True, 'data': data}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500


@notificacion_bp.route('/<id_notificacion>', methods=['GET'])
def obtener_notificacion(id_notificacion):
    try:
        data = obtener_notificacion_por_id(id_notificacion)
        if not data:
            return jsonify({'success': False, 'message': 'Notificación no encontrada'}), 404
        return jsonify({'success': True, 'data': data}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500


@notificacion_bp.route('', methods=['POST'])
def crear():
    try:
        body = request.get_json() or {}
        if not body.get('nombre'):
            return jsonify({'success': False, 'message': 'El nombre es obligatorio'}), 400

        resultado = crear_notificacion(body)
        if not resultado.get('success'):
            return jsonify(resultado), 500
        return jsonify(resultado), 201
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500


@notificacion_bp.route('/<id_notificacion>/estado', methods=['PATCH'])
def actualizar_estado(id_notificacion):
    try:
        body = request.get_json() or {}
        estado_notificacion_id = body.get('estado_notificacion_id')
        if not estado_notificacion_id:
            return jsonify({'success': False, 'message': 'estado_notificacion_id es obligatorio'}), 400

        resultado = actualizar_estado_notificacion(id_notificacion, estado_notificacion_id)
        if not resultado.get('success'):
            return jsonify(resultado), 400
        return jsonify(resultado), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500
