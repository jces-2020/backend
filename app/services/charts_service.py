"""
Servicio para generar gráficos con matplotlib basados en datos de Supabase.
Los gráficos se devuelven como base64 para mostrar en el frontend.
"""

import io
import base64
from matplotlib import pyplot as plt
from matplotlib import rcParams
import numpy as np
from services.supabase_client import supabase

# Configurar matplotlib para no mostrar interfaz gráfica
plt.switch_backend('Agg')

# Configurar estilos consistentes
rcParams['font.family'] = 'sans-serif'
rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans']
rcParams['axes.facecolor'] = '#f8f9fa'
rcParams['figure.facecolor'] = 'white'


def _fig_to_base64(fig):
    """Convierte una figura matplotlib a base64 para enviar al frontend."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return img_base64


def get_dashboard_counts():
    """Obtiene conteos básicos de la base de datos."""
    try:
        servicios_res = supabase.table("servicio").select("id_servicio").execute()
        productos_res = supabase.table("productos").select("id_producto").execute()
        clientes_res = supabase.table("cliente").select("id_cliente").execute()
        pedidos_res = supabase.table("carrito_compras").select("id_carrito").execute()
        
        return {
            'servicios': len(servicios_res.data or []),
            'productos': len(productos_res.data or []),
            'clientes': len(clientes_res.data or []),
            'pedidos': len(pedidos_res.data or [])
        }
    except Exception as e:
        print(f"Error en get_dashboard_counts: {e}")
        return {'servicios': 0, 'productos': 0, 'clientes': 0, 'pedidos': 0}


def generate_summary_bars_chart():
    """Gráfico de barras: Resumen general (Servicios, Productos, Clientes, Pedidos)."""
    try:
        counts = get_dashboard_counts()
        
        fig, ax = plt.subplots(figsize=(10, 5))
        categories = ['Servicios', 'Productos', 'Clientes', 'Pedidos']
        values = [counts['servicios'], counts['productos'], counts['clientes'], counts['pedidos']]
        colors = ['#3ab0e8', '#2ecc71', '#f39c12', '#e74c3c']
        
        bars = ax.bar(categories, values, color=colors, edgecolor='#1a1a1a', linewidth=1.5, alpha=0.8)
        
        # Agregar valores en las barras
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', fontweight='bold', fontsize=12)
        
        ax.set_ylabel('Cantidad', fontsize=11, fontweight='bold')
        ax.set_title('Resumen General del Sistema', fontsize=14, fontweight='bold', pad=20)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        return _fig_to_base64(fig)
    except Exception as e:
        print(f"Error en generate_summary_bars_chart: {e}")
        return None


def generate_categories_distribution_chart():
    """Gráfico de pastel: Distribución de productos por categoría."""
    try:
        cat_res = supabase.table("productos").select("categoria_id").execute()
        productos = cat_res.data or []
        
        if not productos:
            return None
        
        # Contar por categoría
        cat_counts = {}
        cat_names = {}
        for p in productos:
            cat_id = p.get('categoria_id')
            if cat_id:
                cat_counts[cat_id] = cat_counts.get(cat_id, 0) + 1
        
        # Obtener nombres de categorías
        if cat_counts:
            cat_ids = list(cat_counts.keys())
            cat_name_res = supabase.table("categoria").select("id_categoria, descripcion").in_("id_categoria", cat_ids).execute()
            for cat in (cat_name_res.data or []):
                cat_names[cat['id_categoria']] = cat['descripcion']
        
        labels = [cat_names.get(cid, f"Cat {cid[:8]}") for cid in cat_counts.keys()]
        sizes = list(cat_counts.values())
        colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))
        
        fig, ax = plt.subplots(figsize=(8, 6))
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                                           startangle=90, textprops={'fontsize': 10})
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        ax.set_title('Distribución de Productos por Categoría', fontsize=13, fontweight='bold', pad=20)
        
        return _fig_to_base64(fig)
    except Exception as e:
        print(f"Error en generate_categories_distribution_chart: {e}")
        return None


def generate_products_by_category_chart():
    """Gráfico de barras horizontales: Top categorías por cantidad de productos."""
    try:
        # Similar a distribute pero en barras horizontales para mejor visualización
        cat_res = supabase.table("productos").select("categoria_id").execute()
        productos = cat_res.data or []
        
        if not productos:
            return None
        
        cat_counts = {}
        cat_names = {}
        for p in productos:
            cat_id = p.get('categoria_id')
            if cat_id:
                cat_counts[cat_id] = cat_counts.get(cat_id, 0) + 1
        
        if cat_counts:
            cat_ids = list(cat_counts.keys())
            cat_name_res = supabase.table("categoria").select("id_categoria, descripcion").in_("id_categoria", cat_ids).execute()
            for cat in (cat_name_res.data or []):
                cat_names[cat['id_categoria']] = cat['descripcion']
        
        # Ordenar por cantidad descendente
        sorted_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:8]
        labels = [cat_names.get(cid, f"Cat {cid[:8]}") for cid, _ in sorted_cats]
        values = [count for _, count in sorted_cats]
        colors = ['#3ab0e8', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6', '#1abc9c', '#34495e', '#e67e22'][:len(labels)]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.barh(labels, values, color=colors, edgecolor='#1a1a1a', linewidth=1.2, alpha=0.8)
        
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                    f' {int(width)}',
                    ha='left', va='center', fontweight='bold', fontsize=10)
        
        ax.set_xlabel('Cantidad de Productos', fontsize=11, fontweight='bold')
        ax.set_title('Top Categorías por Cantidad de Productos', fontsize=13, fontweight='bold', pad=20)
        ax.grid(axis='x', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        return _fig_to_base64(fig)
    except Exception as e:
        print(f"Error en generate_products_by_category_chart: {e}")
        return None


def generate_clients_chart():
    """Gráfico de barras: Top 4 clientes por monto total gastado."""
    try:
        # Obtener todos los registros de pago
        pagos_res = supabase.table("registro_pago").select("cliente_id, monto").execute()
        pagos = pagos_res.data or []
        
        if not pagos:
            return None
        
        # Agrupar por cliente y sumar
        cliente_totales = {}
        for pago in pagos:
            cliente_id = pago.get('cliente_id')
            monto = float(pago.get('monto', 0)) if pago.get('monto') else 0
            if cliente_id:
                cliente_totales[cliente_id] = cliente_totales.get(cliente_id, 0) + monto
        
        if not cliente_totales:
            return None
        
        # Obtener top 4 clientes
        top_clientes = sorted(cliente_totales.items(), key=lambda x: x[1], reverse=True)[:4]
        
        if not top_clientes:
            return None
        
        # Obtener nombres de clientes
        cliente_ids = [str(cid) for cid, _ in top_clientes]
        cliente_names = {}
        
        try:
            clientes_res = supabase.table("cliente").select("id_cliente, nombre").execute()
            for c in (clientes_res.data or []):
                cid = c.get('id_cliente')
                nombre = c.get('nombre', '').strip()
                if nombre:
                    cliente_names[str(cid)] = nombre
        except Exception as e:
            print(f"Error obteniendo nombres de clientes: {e}")
        
        labels = [cliente_names.get(str(cid), f"Cliente {str(cid)[:8]}") for cid, _ in top_clientes]
        values = [total for _, total in top_clientes]
        colors = ['#3ab0e8', '#2ecc71', '#f39c12', '#e74c3c'][:len(labels)]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(labels, values, color=colors, edgecolor='#1a1a1a', linewidth=1.2, alpha=0.8)
        
        # Rotar etiquetas del eje X para mejor legibilidad
        ax.set_xticklabels(labels, rotation=45, ha='right')
        
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'S/ {height:.2f}',
                    ha='center', va='bottom', fontweight='bold', fontsize=10)
        
        ax.set_ylabel('Monto Total Gastado (S/)', fontsize=11, fontweight='bold')
        ax.set_title('Top 4 Clientes por Gasto Total', fontsize=13, fontweight='bold', pad=20)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        # Ajustar layout para que no se corte los nombres
        fig.tight_layout()
        
        return _fig_to_base64(fig)
    except Exception as e:
        print(f"Error en generate_clients_chart: {e}")
        return None


def generate_orders_status_chart():
    """Gráfico de pastel: Estado de carritos/pedidos."""
    try:
        carrito_res = supabase.table("carrito_compras").select("estado").execute()
        carritos = carrito_res.data or []
        
        if not carritos:
            return None
        
        # Contar por estado
        estado_counts = {}
        for c in carritos:
            estado = c.get('estado', 'Sin estado')
            estado_counts[estado] = estado_counts.get(estado, 0) + 1
        
        labels = list(estado_counts.keys())
        sizes = list(estado_counts.values())
        colors = {'pendiente': '#f39c12', 'completado': '#2ecc71', 'cancelado': '#e74c3c', 'en_proceso': '#3ab0e8'}
        pie_colors = [colors.get(label, '#95a5a6') for label in labels]
        
        fig, ax = plt.subplots(figsize=(8, 6))
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=pie_colors, autopct='%1.1f%%',
                                           startangle=45, textprops={'fontsize': 10, 'fontweight': 'bold'})
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        ax.set_title('Estado de Pedidos/Carritos', fontsize=13, fontweight='bold', pad=20)
        
        return _fig_to_base64(fig)
    except Exception as e:
        print(f"Error en generate_orders_status_chart: {e}")
        return None


def generate_price_range_chart():
    """Gráfico de histograma: Distribución de precios de productos."""
    try:
        prod_res = supabase.table("productos").select("precio_unitario").execute()
        productos = prod_res.data or []
        
        if not productos:
            return None
        
        prices = [float(p.get('precio_unitario', 0)) for p in productos if p.get('precio_unitario')]
        
        if not prices:
            return None
        
        fig, ax = plt.subplots(figsize=(10, 5))
        n, bins, patches = ax.hist(prices, bins=15, color='#3ab0e8', edgecolor='#1a1a1a', alpha=0.7)
        
        # Colorear gradiente
        cm = plt.cm.RdYlGn
        for i, patch in enumerate(patches):
            patch.set_facecolor(cm(i / len(patches)))
        
        ax.set_xlabel('Precio Unitario (S/)', fontsize=11, fontweight='bold')
        ax.set_ylabel('Cantidad de Productos', fontsize=11, fontweight='bold')
        ax.set_title('Distribución de Precios de Productos', fontsize=13, fontweight='bold', pad=20)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        return _fig_to_base64(fig)
    except Exception as e:
        print(f"Error en generate_price_range_chart: {e}")
        return None


def get_all_dashboard_charts():
    """Genera todos los gráficos del dashboard y los retorna como base64."""
    return {
        'summary_bars': generate_summary_bars_chart(),
        'products_by_cat': generate_products_by_category_chart(),
        'clients_chart': generate_clients_chart(),
    }
