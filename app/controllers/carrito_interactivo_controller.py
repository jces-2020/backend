from flask import Blueprint, render_template_string, request, redirect, url_for
from app.services.producto_service import ProductoService

carrito_interactivo_bp = Blueprint('carrito_interactivo', __name__)

# Estado simulado en memoria (solo para pruebas, no persistente)
CARRITO = []

@carrito_interactivo_bp.route('/carrito/interactive', methods=['GET', 'POST'])
def carrito_interactive():
    global CARRITO
    mensaje = ''
    # Obtener todos los productos disponibles
    productos_disp = ProductoService.obtener_todos_los_productos()
    if request.method == 'POST':
        if 'agregar' in request.form:
            id_prod = request.form['id_producto']
            cantidad = int(request.form['cantidad'])
            # Si ya está en el carrito, suma cantidad
            for item in CARRITO:
                if item['id_producto'] == id_prod:
                    item['cantidad'] += cantidad
                    break
            else:
                CARRITO.append({'id_producto': id_prod, 'cantidad': cantidad})
            mensaje = 'Producto agregado.'
        elif 'eliminar' in request.form:
            id_prod = request.form['eliminar']
            CARRITO = [item for item in CARRITO if item['id_producto'] != id_prod]
            mensaje = 'Producto eliminado.'
        return redirect(url_for('carrito_interactivo.carrito_interactive'))
    # Obtener info de productos en el carrito
    ids = [p['id_producto'] for p in CARRITO]
    productos = ProductoService.obtener_productos_por_ids(ids) if ids else []
    tabla = []
    total = 0
    for pcar in CARRITO:
        prod = next((x for x in productos if x.id == pcar['id_producto']), None)
        if prod:
            precio_unitario = getattr(prod, 'precio_unitario', None)
            if precio_unitario is None:
                precio_unitario = next((d.get('precio_unitario') for d in productos_disp if d.get('id_producto') == pcar['id_producto']), 0)
            subtotal = pcar['cantidad'] * float(precio_unitario)
            total += subtotal
            tabla.append({
                'id_producto': prod.id,
                'nombre': prod.nombre,
                'grosor': getattr(prod, 'grosor', ''),
                'codigo': getattr(prod, 'codigo', ''),
                'descripcion': prod.descripcion,
                'cantidad': pcar['cantidad'],
                'precio_unitario': precio_unitario,
                'subtotal': subtotal
            })
    html = '''
    <h2>Carrito de Compras Interactivo (Estado: pendiente)</h2>
    <form method="post">
        <label>Producto:
            <select name="id_producto">
                {% for p in productos_disp %}
                <option value="{{p.id_producto}}">{{p.nombre}} ({{p.codigo}})</option>
                {% endfor %}
            </select>
        </label>
        <label>Cantidad: <input type="number" name="cantidad" value="1" min="1" required></label>
        <button type="submit" name="agregar">Agregar +</button>
    </form>
    <br>
    <table border="1" cellpadding="6" style="border-collapse:collapse;">
        <tr>
            <th>NOMBRE</th><th>GROSOR</th><th>CODIGO</th><th>DESCRIPCIÓN</th><th>CANTIDAD</th><th>PRECIO UNITARIO</th><th>SUBTOTAL</th><th>Acción</th>
        </tr>
        {% for row in tabla %}
        <tr>
            <td>{{row.nombre}}</td><td>{{row.grosor}}</td><td>{{row.codigo}}</td><td>{{row.descripcion}}</td><td>{{row.cantidad}}</td><td style="text-align:right;">S/ {{row.precio_unitario}}</td><td style="text-align:right;">S/ {{row.subtotal}}</td>
            <td>
                <form method="post" style="display:inline;">
                    <input type="hidden" name="eliminar" value="{{row.id_producto}}">
                    <button type="submit">Eliminar</button>
                </form>
            </td>
        </tr>
        {% endfor %}
        <tr><td colspan="7" style="text-align:right;"><b>TOTAL</b></td><td style="text-align:right;"><b>S/ {{total}}</b></td></tr>
    </table>
    <div style="color:green;">{{mensaje}}</div>
    '''
    return render_template_string(html, productos_disp=productos_disp, tabla=tabla, total=total, mensaje=mensaje)
