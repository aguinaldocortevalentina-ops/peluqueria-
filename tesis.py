import sqlite3

from flask import Flask, redirect, render_template, request, url_for


app = Flask(__name__)


RUTA_BASE_DE_DATOS = "peluqueria.db"

SERVICIOS_INICIALES = [
    {"nombre": "Corte", "precio": 12000},
    {"nombre": "Corte clásico", "precio": 10000},
    {"nombre": "Corte + ceja", "precio": 13000},
    {"nombre": "Tintura", "precio": 15000}
]

ESPECIALIDADES_INICIALES = {
    "Miriam": ["Tintura", "Corte", "Corte clásico"],
    "Alexander": ["Corte", "Corte + ceja", "Corte clásico"]
}


def obtener_conexion():
    """Crea una conexión con la base de datos SQLite."""
    conexion = sqlite3.connect(RUTA_BASE_DE_DATOS)
    conexion.row_factory = sqlite3.Row
    return conexion


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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS peluqueros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            foto TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS peluquero_servicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peluquero_id INTEGER NOT NULL,
            servicio_id INTEGER NOT NULL,
            FOREIGN KEY (peluquero_id) REFERENCES peluqueros (id),
            FOREIGN KEY (servicio_id) REFERENCES servicios (id_servicio),
            UNIQUE (peluquero_id, servicio_id)
        )
    """)

    for servicio in SERVICIOS_INICIALES:
        cursor.execute("""
            INSERT OR IGNORE INTO servicios (nombre, precio)
            VALUES (?, ?)
        """, (servicio["nombre"], servicio["precio"]))

    for nombre, especialidades in ESPECIALIDADES_INICIALES.items():
        cursor.execute("""
            INSERT OR IGNORE INTO peluqueros (nombre, foto)
            VALUES (?, ?)
        """, (nombre, ""))

        peluquero = cursor.execute(
            "SELECT id FROM peluqueros WHERE nombre = ?", (nombre,)
        ).fetchone()

        for especialidad in especialidades:
            servicio = cursor.execute(
                "SELECT id_servicio FROM servicios WHERE nombre = ?", (especialidad,)
            ).fetchone()
            cursor.execute("""
                INSERT OR IGNORE INTO peluquero_servicios (peluquero_id, servicio_id)
                VALUES (?, ?)
            """, (peluquero["id"], servicio["id_servicio"]))

    conexion.commit()
    conexion.close()


@app.route("/")
def inicio():
    """Muestra la página principal de Flama Barber."""
    conexion = obtener_conexion()
    servicios = conexion.execute(
        "SELECT id_servicio, nombre, precio FROM servicios ORDER BY nombre"
    ).fetchall()
    peluqueros = conexion.execute("""
        SELECT peluqueros.id, peluqueros.nombre, peluqueros.foto,
               GROUP_CONCAT(servicios.nombre, ', ') AS especialidades
        FROM peluqueros
        LEFT JOIN peluquero_servicios
            ON peluqueros.id = peluquero_servicios.peluquero_id
        LEFT JOIN servicios
            ON servicios.id_servicio = peluquero_servicios.servicio_id
        GROUP BY peluqueros.id
        ORDER BY peluqueros.nombre
    """).fetchall()
    conexion.close()

    return render_template(
        "index.html", servicios=servicios, peluqueros=peluqueros
    )


@app.post("/peluqueros/nuevo")
def crear_peluquero():
    """Guarda un peluquero y las especialidades elegidas."""
    nombre = request.form["nombre"].strip()
    foto = request.form["foto"].strip()
    servicios_elegidos = request.form.getlist("servicios")

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("INSERT INTO peluqueros (nombre, foto) VALUES (?, ?)", (nombre, foto))
    peluquero_id = cursor.lastrowid

    for servicio_id in servicios_elegidos:
        cursor.execute("""
            INSERT INTO peluquero_servicios (peluquero_id, servicio_id)
            VALUES (?, ?)
        """, (peluquero_id, servicio_id))

    conexion.commit()
    conexion.close()
    return redirect(url_for("inicio"))


@app.post("/servicios/nuevo")
def crear_servicio():
    """Agrega un servicio al catálogo general."""
    nombre = request.form["nombre"].strip()
    precio = request.form["precio"].strip()

    conexion = obtener_conexion()
    conexion.execute(
        "INSERT INTO servicios (nombre, precio) VALUES (?, ?)", (nombre, precio)
    )
    conexion.commit()
    conexion.close()
    return redirect(url_for("inicio"))


@app.route("/peluqueros/<int:peluquero_id>/editar", methods=["GET", "POST"])
def editar_peluquero(peluquero_id):
    """Muestra y guarda los cambios de un peluquero."""
    conexion = obtener_conexion()

    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        foto = request.form["foto"].strip()
        servicios_elegidos = request.form.getlist("servicios")

        conexion.execute(
            "UPDATE peluqueros SET nombre = ?, foto = ? WHERE id = ?",
            (nombre, foto, peluquero_id)
        )
        conexion.execute(
            "DELETE FROM peluquero_servicios WHERE peluquero_id = ?", (peluquero_id,)
        )
        for servicio_id in servicios_elegidos:
            conexion.execute("""
                INSERT INTO peluquero_servicios (peluquero_id, servicio_id)
                VALUES (?, ?)
            """, (peluquero_id, servicio_id))

        conexion.commit()
        conexion.close()
        return redirect(url_for("inicio"))

    peluquero = conexion.execute(
        "SELECT id, nombre, foto FROM peluqueros WHERE id = ?", (peluquero_id,)
    ).fetchone()
    servicios = conexion.execute(
        "SELECT id_servicio, nombre FROM servicios ORDER BY nombre"
    ).fetchall()
    servicios_asignados = conexion.execute("""
        SELECT servicio_id FROM peluquero_servicios WHERE peluquero_id = ?
    """, (peluquero_id,)).fetchall()
    conexion.close()

    ids_asignados = [servicio["servicio_id"] for servicio in servicios_asignados]
    return render_template(
        "editar_peluquero.html",
        peluquero=peluquero,
        servicios=servicios,
        ids_asignados=ids_asignados
    )


@app.post("/peluqueros/<int:peluquero_id>/eliminar")
def eliminar_peluquero(peluquero_id):
    """Elimina un peluquero y sus asignaciones de servicios."""
    conexion = obtener_conexion()
    conexion.execute(
        "DELETE FROM peluquero_servicios WHERE peluquero_id = ?", (peluquero_id,)
    )
    conexion.execute("DELETE FROM peluqueros WHERE id = ?", (peluquero_id,))
    conexion.commit()
    conexion.close()
    return redirect(url_for("inicio"))


crear_base_de_datos()


if __name__ == "__main__":
    app.run(debug=True)
