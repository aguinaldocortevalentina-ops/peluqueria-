import sqlite3

from flask import Flask, render_template


app = Flask(__name__)


RUTA_BASE_DE_DATOS = "peluqueria.db"

SERVICIOS_INICIALES = [
    {"nombre": "Corte", "precio": 12000},
    {"nombre": "Corte clásico", "precio": 10000},
    {"nombre": "Corte + ceja", "precio": 13000},
    {"nombre": "Tintura", "precio": 15000}
]


def obtener_conexion():
    """Crea una conexión con la base de datos SQLite."""
    return sqlite3.connect(RUTA_BASE_DE_DATOS)


def crear_base_de_datos():
    """Crea la tabla de servicios y carga los datos iniciales."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS servicios (
            id_servicio INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            precio INTEGER NOT NULL
        )
    """)

    for servicio in SERVICIOS_INICIALES:
        cursor.execute("""
            INSERT OR IGNORE INTO servicios (nombre, precio)
            VALUES (?, ?)
        """, (servicio["nombre"], servicio["precio"]))

    conexion.commit()
    conexion.close()


@app.route("/")
def inicio():
    """Muestra la página principal de Flama Barber."""
    conexion = obtener_conexion()
    conexion.row_factory = sqlite3.Row
    servicios = conexion.execute("SELECT nombre, precio FROM servicios").fetchall()
    conexion.close()

    return render_template("index.html", servicios=servicios)


crear_base_de_datos()


if __name__ == "__main__":
    app.run(debug=True)
