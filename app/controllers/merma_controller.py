"""
Controlador para consultas de merma.
"""
from flask import Blueprint, jsonify, request
from app.services.merma_service import (
    obtener_merma_por_categoria,
    eliminar_mermas,
    buscar_merma_por_medidas,
    obtener_categorias_merma,
    reducir_cantidad_merma,
)
from app.services.supabase_client import supabase

merma_bp = Blueprint("merma", __name__)


@merma_bp.route("/api/merma", methods=["GET"])
def obtener_todas_mermas():
    """
    GET /api/merma
    Obtiene todas las mermas disponibles.
    """
    try:
        # Obtener mermas con su categoría relacionada
        result = supabase.table('merma').select(
            'id_merma, nombre, ancho_cm, alto_cm, cantidad, lugar, descripción, id_categoria, fecha_registro'
        ).execute()
        
        mermas = result.data or []
        
        # Si hay mermas, enriquecemos con categoría
        if mermas and len(mermas) > 0:
            try:
                categorias_result = supabase.table('categoria').select('id_categoria, descripcion').execute()
                categorias_map = {c['id_categoria']: c['descripcion'] for c in (categorias_result.data or [])}
                
                for merma in mermas:
                    if merma.get('id_categoria'):
                        merma['categoria'] = {
                            'id_categoria': merma['id_categoria'],
                            'descripcion': categorias_map.get(merma['id_categoria'], 'Sin categoría')
                        }
                    else:
                        merma['categoria'] = {'id_categoria': None, 'descripcion': 'Sin categoría'}
            except Exception as e:
                print(f"[MERMA_CONTROLLER] Aviso: No se pudo enriquecer con categorías: {str(e)}")
                # Continuamos sin categorías si hay error
                for merma in mermas:
                    merma['categoria'] = {'id_categoria': merma.get('id_categoria'), 'descripcion': 'Sin categoría'}
        
        return jsonify({"data": mermas}), 200
    except Exception as e:
        print(f"[MERMA_CONTROLLER] Error al obtener mermas: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"data": [], "error": str(e)}), 500


@merma_bp.route("/api/merma/categoria/<categoria_id>", methods=["GET"])
def get_merma_por_categoria(categoria_id):
    """
    GET /api/merma/categoria/<categoria_id>
    Obtiene mermas filtradas por categoria.
    """
    try:
        resultado = obtener_merma_por_categoria(categoria_id)
        if resultado.get("success"):
            return jsonify({"success": True, "data": resultado.get("data", [])}), 200

        # Log detailed error for debugging
        import traceback
        print(f"[ERROR] get_merma_por_categoria({categoria_id}): {resultado.get('message')}")
        
        return jsonify({
            "success": False,
            "message": resultado.get("message", "Error al obtener mermas")
        }), 400
    except Exception as exc:
        import traceback
        print(f"[ERROR] get_merma_por_categoria endpoint - {str(exc)}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@merma_bp.route("/api/merma/eliminar", methods=["POST"])
def eliminar_mermas_endpoint():
    """
    POST /api/merma/eliminar
    Body: {"ids": ["uuid", ...]}
    """
    try:
        data = request.get_json() or {}
        ids = data.get("ids") or []

        resultado = eliminar_mermas(ids)
        if resultado.get("success"):
            return jsonify({"success": True, "eliminados": resultado.get("eliminados", 0)}), 200

        return jsonify({
            "success": False,
            "message": resultado.get("message", "Error al eliminar mermas")
        }), 400
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@merma_bp.route("/api/merma/buscar", methods=["GET"])
def buscar_merma_endpoint():
    """
    GET /api/merma/buscar?ancho=100&alto=200&tolerancia=10&categoria=uuid
    Busca merma disponible por medidas con tolerancia.
    
    Query params:
        ancho: Ancho requerido en cm (requerido)
        alto: Alto requerido en cm (requerido)
        tolerancia: Tolerancia en cm (default: 10)
        categoria: UUID de categoría (opcional)
    """
    try:
        ancho_str = request.args.get('ancho', '').strip()
        alto_str = request.args.get('alto', '').strip()
        tolerancia_str = request.args.get('tolerancia', '10').strip()
        id_categoria = request.args.get('categoria', '').strip() or None
        
        if not ancho_str or not alto_str:
            return jsonify({
                "success": False,
                "message": "Parámetros 'ancho' y 'alto' son requeridos",
                "mermas": []
            }), 400
        
        try:
            ancho_cm = float(ancho_str)
            alto_cm = float(alto_str)
            tolerancia = float(tolerancia_str)
        except ValueError:
            return jsonify({
                "success": False,
                "message": "Valores numéricos inválidos",
                "mermas": []
            }), 400
        
        print(f"[MERMA_CONTROLLER] Buscando merma: ancho={ancho_cm}, alto={alto_cm}, tolerancia={tolerancia}")
        
        resultado = buscar_merma_por_medidas(ancho_cm, alto_cm, tolerancia, id_categoria)
        
        if resultado.get("success"):
            return jsonify(resultado), 200
        
        return jsonify(resultado), 400
        
    except Exception as e:
        print(f"[MERMA_CONTROLLER] ✗ Error: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e),
            "mermas": []
        }), 500


@merma_bp.route("/api/merma/categorias", methods=["GET"])
def get_categorias_endpoint():
    """
    GET /api/merma/categorias
    Obtiene todas las categorías disponibles para filtrar merma.
    """
    try:
        resultado = obtener_categorias_merma()
        
        if resultado.get("success"):
            return jsonify(resultado), 200
        
        return jsonify(resultado), 400
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "categorias": []
        }), 500


@merma_bp.route("/api/merma/<merma_id>/descontar", methods=["POST"])
def descontar_merma_endpoint(merma_id):
    """
    POST /api/merma/<merma_id>/descontar
    Body: {"cantidad": 1}  — descuenta esa cantidad del stock de la merma.
    Si llega a 0 o menos, elimina el registro para que otros trabajadores
    vean en tiempo real que ya no está disponible.
    """
    try:
        data = request.get_json() or {}
        cantidad = int(data.get("cantidad", 1))
        if cantidad <= 0:
            return jsonify({"success": False, "message": "La cantidad debe ser mayor a 0"}), 400

        resultado = reducir_cantidad_merma(merma_id, cantidad)
        if resultado.get("success"):
            return jsonify(resultado), 200

        return jsonify(resultado), 404
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500
