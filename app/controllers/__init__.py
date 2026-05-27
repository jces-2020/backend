from flask import Flask

# Creamos la instancia de la aplicación Flask
app = Flask(__name__)

# Definimos una ruta de prueba
@app.route('/')
def index():
    return "<h1>¡El backend de VIDRIOBRAS está funcionando!</h1>"