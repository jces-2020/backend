import requests
from flask import Blueprint, request, jsonify
import os

bp_html = Blueprint('cotizacion_api', __name__)

# Token fijo - NUNCA usar variable de entorno (puede estar vencida o ser diferente)
# Este es el token actualizado que funciona
APISPERU_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImkyNDE1OTE0QGNvbnRpbmVudGFsLmVkdS5wZSJ9.e9EuekJUwsqKvAGuELbs-0P65QkqdeMranSkV-Tqb9Y'

# Asegurar que no se use variable de entorno
os.environ.pop('APISPERU_TOKEN', None)

@bp_html.route('/api/consulta_documento_html', methods=['POST'])
def consulta_documento_html():
    data = request.json
    tipo = (data.get('tipo') or '').upper()
    numero = (data.get('numero') or '').strip()

    if not tipo or not numero:
        return jsonify({'success': False, 'message': 'Faltan datos'}), 400

    if tipo == 'DNI':
        if len(numero) not in [7, 8] or not numero.isdigit():
            return jsonify({'success': False, 'message': 'El DNI debe tener 7 u 8 dígitos.'}), 400
        url = f'https://dniruc.apisperu.com/api/v1/dni/{numero}?token={APISPERU_TOKEN}'
    elif tipo == 'RUC':
        if len(numero) != 11 or not numero.isdigit():
            return jsonify({'success': False, 'message': 'El RUC debe tener 11 dígitos.'}), 400
        url = f'https://dniruc.apisperu.com/api/v1/ruc/{numero}?token={APISPERU_TOKEN}'
    else:
        return jsonify({'success': False, 'message': 'Tipo de documento inválido.'}), 400

    try:
        print(f"[DEBUG] Consultando URL: {url}")
        r = requests.get(url, timeout=8)
        print(f"[DEBUG] Status code: {r.status_code}")
        print(f"[DEBUG] Response text: {r.text[:200]}")
        
        # Si no encuentra el documento, responder 200 para no romper el flujo de venta
        if r.status_code != 200:
            print(f"[DEBUG] Documento no encontrado (status {r.status_code})")
            return jsonify({'success': False, 'message': 'No encontrado en RENIEC/SUNAT'}), 200
        
        j = r.json()
        
        if 'error' in j:
            print(f"[DEBUG] Error en respuesta: {j.get('error')}")
            return jsonify({'success': False, 'message': 'No encontrado en RENIEC/SUNAT', 'error': j['error']}), 200

        if tipo == 'DNI':
            nombre = f"{j.get('nombres', '')} {j.get('apellidoPaterno', '')} {j.get('apellidoMaterno', '')}".strip()
            print(f"[DEBUG] DNI encontrado: {nombre}")
            return jsonify({'success': True, 'html': nombre}), 200
        elif tipo == 'RUC':
            razon_social = j.get('razonSocial', '')
            print(f"[DEBUG] RUC encontrado: {razon_social}")
            return jsonify({'success': True, 'html': razon_social}), 200

    except requests.exceptions.Timeout:
        print("[DEBUG] Timeout al consultar APISPERU")
        return jsonify({'success': False, 'message': 'No se pudo conectar con ApisPeru (timeout).'}), 500
    except requests.exceptions.RequestException as e:
        print(f"[DEBUG] Error de requests: {str(e)}")
        return jsonify({'success': False, 'message': 'Error consultando APISPERU', 'error': str(e)}), 500
    except Exception as e:
        print(f"[DEBUG] Error inesperado: {str(e)}")
        return jsonify({'success': False, 'message': 'Error inesperado', 'error': str(e)}), 500
        return jsonify({'success': False, 'message': 'Error consultando APISPERU', 'error': str(e)}), 500
    except Exception as e:
        print(f"[DEBUG] Error inesperado: {str(e)}")
        return jsonify({'success': False, 'message': 'Error inesperado', 'error': str(e)}), 500