
from flask import Blueprint, render_template_string, request
from app.services.producto_service import ProductoService

carrito_bp = Blueprint('carrito', __name__)

@carrito_bp.route('/carrito/prueba', methods=['GET', 'POST'])
def carrito_prueba():
    # Simular un carrito con estado y productos agregados
    estado = "pendiente"
    # Usa dos productos reales de la base de datos (puedes cambiar los IDs por los que quieras probar)
    productos_carrito = [
        {"id_producto": "1640d537-e48b-4efe-84af-1ba2aab4461b", "cantidad": 2},
        {"id_producto": "3c36959a-33c5-4997-a34f-cf2ed1905814", "cantidad": 1}
    ]
    mensaje = ''
    ubicacion = ''
    fecha_entrega = ''
    descripcion = ''
    if request.method == 'POST':
        ubicacion = request.form.get('ubicacion', '')
        fecha_entrega = request.form.get('fecha_entrega', '')
        descripcion = request.form.get('descripcion', '')
        mensaje = f"Pedido recibido para entregar en '{ubicacion}' el día {fecha_entrega}. Nota: {descripcion}"
    ids = [p["id_producto"] for p in productos_carrito]
    productos = ProductoService.obtener_productos_por_ids(ids)
    tabla = []
    total = 0
    for pcar in productos_carrito:
        prod = next((x for x in productos if x.id == pcar['id_producto']), None)
        if prod:
            # Suponiendo que el modelo Producto tiene precio_unitario como atributo extraído del dict
            precio_unitario = getattr(prod, 'precio_unitario', None)
            if precio_unitario is None:
                # fallback: buscar en el dict original si existe
                precio_unitario = next((d.get('precio_unitario') for d in productos if hasattr(d, '__dict__') and d.id == pcar['id_producto']), 0)
            subtotal = pcar['cantidad'] * float(precio_unitario)
            total += subtotal
            tabla.append({
                'nombre': prod.nombre,
                'grosor': getattr(prod, 'grosor', ''),
                'codigo': getattr(prod, 'codigo', ''),
                'descripcion': prod.descripcion,
                'cantidad': pcar['cantidad'],
                'precio_unitario': precio_unitario,
                'subtotal': subtotal
            })

    html = '''
    <h2>Carrito de Compras (Estado: {{estado}})</h2>
    <table border="1" cellpadding="6" style="border-collapse:collapse;">
        <tr>
            <th>NOMBRE</th><th>GROSOR</th><th>CODIGO</th><th>DESCRIPCIÓN</th><th>CANTIDAD</th><th>PRECIO UNITARIO</th><th>SUBTOTAL</th>
        </tr>
        {% for row in tabla %}
        <tr>
            <td>{{row.nombre}}</td><td>{{row.grosor}}</td><td>{{row.codigo}}</td><td>{{row.descripcion}}</td><td>{{row.cantidad}}</td><td style="text-align:right;">S/ {{row.precio_unitario}}</td><td style="text-align:right;">S/ {{row.subtotal}}</td>
        </tr>
        {% endfor %}
        <tr><td colspan="6" style="text-align:right;"><b>TOTAL</b></td><td style="text-align:right;"><b>S/ {{total}}</b></td></tr>
    </table>
    <br>
    <form method="post">
        <label><b>Lugar de entrega:</b></label>
        <input type="text" name="ubicacion" placeholder="Agregar ubicación" style="width: 250px;" required><br><br>
        <label><b>Fecha de entrega:</b></label>
        <input type="date" name="fecha_entrega" required><br>
        <small>Fecha de entrega</small><br><br>
        <label><b>Descripción:</b></label><br>
        <textarea name="descripcion" rows="3" cols="40" placeholder="Agrega una nota o comentario adicional..."></textarea><br><br>
        <button type="submit" style="background-color: orange; color: black; padding: 8px 20px; border: none; border-radius: 4px; font-weight: bold;">REALIZAR PEDIDO</button>
    </form>
    {% if mensaje %}<div style="color:green; font-weight:bold;">{{mensaje}}</div>{% endif %}
    '''
    return render_template_string(html, estado=estado, tabla=tabla, total=total, mensaje=mensaje)
