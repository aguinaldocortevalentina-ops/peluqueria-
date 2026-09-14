import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for


app = Flask(__name__)
app.config["SECRET_KEY"] = "flama-barber-proyecto-escolar"

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
    """Crea las tablas y carga datos simples para comenzar."""
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS turnos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peluquero_id INTEGER NOT NULL,
            servicio_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            FOREIGN KEY (peluquero_id) REFERENCES peluqueros (id),
            FOREIGN KEY (servicio_id) REFERENCES servicios (id_servicio)
        )
    """)

    for servicio in SERVICIOS_INICIALES:
        cursor.execute("""
            INSERT OR IGNORE INTO servicios (nombre, precio)
            VALUES (?, ?)
        """, (servicio["nombre"], servicio["precio"]))

    for nombre, especialidades in ESPECIALIDADES_INICIALES.items():
        cursor.execute("INSERT OR IGNORE INTO peluqueros (nombre, foto) VALUES (?, ?)", (nombre, ""))
        peluquero_id = cursor.execute(
            "SELECT id FROM peluqueros WHERE nombre = ?", (nombre,)
        ).fetchone()["id"]

        for especialidad in especialidades:
            servicio_id = cursor.execute(
                "SELECT id_servicio FROM servicios WHERE nombre = ?", (especialidad,)
            ).fetchone()["id_servicio"]
            cursor.execute("""
                INSERT OR IGNORE INTO peluquero_servicios (peluquero_id, servicio_id)
                VALUES (?, ?)
            """, (peluquero_id, servicio_id))

    conexion.commit()
    conexion.close()


def obtener_peluqueros():
    """Devuelve peluqueros y un resumen de sus especialidades."""
    conexion = obtener_conexion()
    peluqueros = conexion.execute("""
        SELECT peluqueros.id, peluqueros.nombre, peluqueros.foto,
               GROUP_CONCAT(servicios.nombre, ', ') AS especialidades
        FROM peluqueros
        LEFT JOIN peluquero_servicios ON peluqueros.id = peluquero_servicios.peluquero_id
        LEFT JOIN servicios ON servicios.id_servicio = peluquero_servicios.servicio_id
        GROUP BY peluqueros.id
        ORDER BY peluqueros.nombre
    """).fetchall()
    conexion.close()
    return peluqueros


@app.get("/")
def inicio():
    """Muestra la página principal y los servicios generales."""
    conexion = obtener_conexion()
    servicios = conexion.execute("SELECT nombre, precio FROM servicios ORDER BY nombre").fetchall()
    conexion.close()
    return render_template("index.html", servicios=servicios)


@app.get("/reservar")
def iniciar_reserva():
    """Inicia una nueva reserva vacía."""
    session.pop("reserva", None)
    return redirect(url_for("elegir_peluquero"))


@app.route("/reservar/peluquero", methods=["GET", "POST"])
def elegir_peluquero():
    """Permite seleccionar un peluquero."""
    if request.method == "POST":
        session["reserva"] = {"peluquero_id": request.form["peluquero_id"]}
        return redirect(url_for("elegir_servicio"))

    return render_template("reserva_peluquero.html", peluqueros=obtener_peluqueros(), reserva=session.get("reserva", {}))


@app.route("/reservar/servicio", methods=["GET", "POST"])
def elegir_servicio():
    """Muestra solo los servicios del peluquero seleccionado."""
    reserva = session.get("reserva")
    if not reserva or not reserva.get("peluquero_id"):
        return redirect(url_for("elegir_peluquero"))

    if request.method == "POST":
        reserva["servicio_id"] = request.form["servicio_id"]
        session["reserva"] = reserva
        return redirect(url_for("elegir_fecha_hora"))

    conexion = obtener_conexion()
    peluquero = conexion.execute("SELECT id, nombre FROM peluqueros WHERE id = ?", (reserva["peluquero_id"],)).fetchone()
    servicios = conexion.execute("""
        SELECT servicios.id_servicio, servicios.nombre, servicios.precio
        FROM servicios
        INNER JOIN peluquero_servicios ON servicios.id_servicio = peluquero_servicios.servicio_id
        WHERE peluquero_servicios.peluquero_id = ?
        ORDER BY servicios.nombre
    """, (reserva["peluquero_id"],)).fetchall()
    conexion.close()
    return render_template("reserva_servicio.html", peluquero=peluquero, servicios=servicios, reserva=reserva)


@app.route("/reservar/fecha-hora", methods=["GET", "POST"])
def elegir_fecha_hora():
    """Permite elegir fecha y hora y guarda el turno al confirmar."""
    reserva = session.get("reserva")
    if not reserva or not reserva.get("servicio_id"):
        return redirect(url_for("elegir_servicio"))

    if request.method == "POST":
        fecha = f"{request.form['dia']}/{request.form['mes']}"
        hora = request.form["hora"]
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO turnos (peluquero_id, servicio_id, fecha, hora)
            VALUES (?, ?, ?, ?)
        """, (reserva["peluquero_id"], reserva["servicio_id"], fecha, hora))
        turno_id = cursor.lastrowid
        conexion.commit()
        conexion.close()
        session.pop("reserva", None)
        return redirect(url_for("confirmacion_turno", turno_id=turno_id))

    return render_template("reserva_fecha_hora.html")


@app.get("/turnos/<int:turno_id>/confirmacion")
def confirmacion_turno(turno_id):
    """Muestra la información de un turno confirmado."""
    conexion = obtener_conexion()
    turno = conexion.execute("""
        SELECT turnos.fecha, turnos.hora, turnos.estado,
               peluqueros.nombre AS peluquero_nombre,
               servicios.nombre AS servicio_nombre, servicios.precio AS servicio_precio
        FROM turnos
        INNER JOIN peluqueros ON peluqueros.id = turnos.peluquero_id
        INNER JOIN servicios ON servicios.id_servicio = turnos.servicio_id
        WHERE turnos.id = ?
    """, (turno_id,)).fetchone()
    conexion.close()
    return render_template("confirmacion_turno.html", turno=turno)


crear_base_de_datos()


if __name__ == "__main__":
    app.run(debug=True)
