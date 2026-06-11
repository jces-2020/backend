from flask import Blueprint, jsonify, render_template, request
# Asegúrate de que app.services.supabase_client.supabase esté correctamente configurado
from app.services.supabase_client import supabase 
import requests

tipo_documento_bp = Blueprint('tipo_documento', __name__)

# Token de ApisPeru desde entorno; fallback al valor configurado en credenciales/.env
APISPERU_TOKEN = os.environ.get(
    "APISPERU_TOKEN",
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImkyNDE1OTE0QGNvbnRpbnVudGFsLmVkdS5wZSJ9.e9EuekJUwsqKvAGuELbs-0P65QkqdeMranSkV-Tqb9Y"
)

@tipo_documento_bp.route('/api/tipo_documento', methods=['GET'])
def get_tipo_documento():
    """Consulta los tipos de documento desde Supabase."""
    try:
        response = supabase.table('tipo_documento').select('id_tipo, descripcion').execute()
        tipos = response.data or []
        # Aseguramos que los tipos devueltos sean 'DNI' y 'RUC' para que el frontend funcione
        tipos_filtrados = [t for t in tipos if t.get('descripcion') in ('DNI', 'RUC')]
        return jsonify({ 'success': True, 'tipos': tipos_filtrados })
    except Exception as e:
        # En caso de error de Supabase, devolvemos DNI y RUC por defecto
        default_tipos = [{'id_tipo': 1, 'descripcion': 'DNI'}, {'id_tipo': 2, 'descripcion': 'RUC'}]
        return jsonify({ 'success': False, 'error': str(e), 'tipos': default_tipos }), 500

@tipo_documento_bp.route('/test_apisperu')
def test_apisperu():
    """Renderiza el HTML de prueba."""
    # Asegúrate de que 'test_apisperu.html' esté en la carpeta 'templates'
    return render_template('test_apisperu.html')

@tipo_documento_bp.route('/api/consulta_documento', methods=['POST'])
def consulta_documento():
    """Consulta la API de ApisPeru desde el backend (Función Centralizada)."""
    data = request.json
    # Convertimos a mayúsculas para la validación
    tipo = (data.get('tipo') or '').upper() 
    numero = (data.get('numero') or '').strip()
    
    print(f"Tipo: {tipo}, Numero: {numero}")
    url = None
    
    if tipo == "DNI":
        if len(numero) != 8 or not numero.isdigit():
            return jsonify({"success": False, "error": "El DNI debe tener 8 dígitos numéricos."}), 400
        url = f"https://dniruc.apisperu.com/api/v1/dni/{numero}?token={APISPERU_TOKEN}"
    elif tipo == "RUC":
        if len(numero) != 11 or not numero.isdigit():
            return jsonify({"success": False, "error": "El RUC debe tener 11 dígitos numéricos."}), 400
        url = f"https://dniruc.apisperu.com/api/v1/ruc/{numero}?token={APISPERU_TOKEN}"
    else:
        return jsonify({"success": False, "error": "Tipo de documento inválido. Solo se acepta DNI o RUC."}), 400
        
    print(f"URL consultada: {url}")
    try:
        res = requests.get(url, timeout=10)
        print(f"Status code ApisPeru: {res.status_code}")
        print(f"Respuesta ApisPeru (raw): {res.text}")

        raw_text = (res.text or "").strip()
        if not raw_text:
            print("[DEBUG] Respuesta vacía desde ApisPeru")
            return jsonify({"success": False, "error": "No se encontró información para este documento.", "nombre": ""}), 200

        try:
            data_json = res.json()
        except ValueError:
            print(f"[DEBUG] Respuesta no JSON desde ApisPeru: {raw_text[:200]}")
            return jsonify({"success": False, "error": "No se encontró información para este documento.", "nombre": ""}), 200

        print(f"Respuesta ApisPeru (json): {data_json}")

        api_success = bool(data_json.get("success", False))
        if res.status_code == 200 and api_success:
            nombre = ""
            if tipo == "DNI":
                nombre = f"{data_json.get('nombres','')} {data_json.get('apellidoPaterno','')} {data_json.get('apellidoMaterno','')}".strip()
                if not nombre:
                    return jsonify({"success": False, "error": "No se encontró nombre para este DNI.", "nombre": ""}), 200
                return jsonify({"success": True, "nombre": nombre, "html": nombre, "data": data_json}), 200

            if tipo == "RUC":
                nombre = data_json.get('razonSocial', '').strip()
                if not nombre:
                    return jsonify({"success": False, "error": "No se encontró razón social para este RUC.", "nombre": ""}), 200
                return jsonify({"success": True, "nombre": nombre, "html": nombre, "data": data_json}), 200

            return jsonify({"success": True, "data": data_json}), 200

        # Manejo de respuestas exitosas sin el flag success o con error explícito
        error_msg = data_json.get("message") or data_json.get("error") or "No se encontró información para este documento."
        print(f"Error devuelto: {error_msg}")
        return jsonify({"success": False, "error": error_msg, "nombre": ""}), 200

    except requests.exceptions.Timeout:
        print("Timeout al conectar con ApisPeru")
        return jsonify({"success": False, "error": "No se pudo conectar con ApisPeru (timeout).", "nombre": ""}), 200
    except Exception as e:
        print(f"Error en la consulta: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Error interno en el servidor: {e}", "nombre": ""}), 200