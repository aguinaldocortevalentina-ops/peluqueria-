import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


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

HORARIOS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "13:00", "13:30", "14:00", "14:30",
    "15:00", "15:30", "16:00", "16:30", "17:00", "17:30",
    "18:00", "18:30", "19:00", "19:30", "20:00"
]


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
            cliente_nombre TEXT DEFAULT 'Cliente',
            cliente_telefono TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'pendiente',
            FOREIGN KEY (peluquero_id) REFERENCES peluqueros (id),
            FOREIGN KEY (servicio_id) REFERENCES servicios (id_servicio)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS administradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL UNIQUE,
            contrasena_hash TEXT NOT NULL,
            nombre TEXT NOT NULL
        )
    """)

    # Migración retrocompatible para columnas en tabla turnos existente
    columnas_turnos = [col["name"] for col in cursor.execute("PRAGMA table_info(turnos)").fetchall()]
    if "cliente_nombre" not in columnas_turnos:
        cursor.execute("ALTER TABLE turnos ADD COLUMN cliente_nombre TEXT DEFAULT 'Cliente'")
    if "cliente_telefono" not in columnas_turnos:
        cursor.execute("ALTER TABLE turnos ADD COLUMN cliente_telefono TEXT DEFAULT ''")

    # Administrador por defecto (admin / admin123)
    admin_existente = cursor.execute("SELECT id FROM administradores WHERE usuario = ?", ("admin",)).fetchone()
    if not admin_existente:
        cursor.execute("""
            INSERT INTO administradores (usuario, contrasena_hash, nombre)
            VALUES (?, ?, ?)
        """, ("admin", generate_password_hash("admin123"), "Admin Flama Barber"))

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


def admin_requerido(f):
    """Decorador para proteger rutas exclusivas de administración."""
    @wraps(f)
    def decorada(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorada


# =====================================================================
# RUTAS DE CLIENTES
# =====================================================================

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
    """Permite elegir fecha, hora y datos del cliente; guarda el turno al confirmar."""
    reserva = session.get("reserva")
    if not reserva or not reserva.get("servicio_id"):
        return redirect(url_for("elegir_servicio"))

    if request.method == "POST":
        fecha = f"{request.form['dia']}/{request.form['mes']}"
        hora = request.form["hora"]
        cliente_nombre = request.form.get("cliente_nombre", "Cliente").strip() or "Cliente"
        cliente_telefono = request.form.get("cliente_telefono", "").strip()

        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO turnos (peluquero_id, servicio_id, fecha, hora, cliente_nombre, cliente_telefono)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (reserva["peluquero_id"], reserva["servicio_id"], fecha, hora, cliente_nombre, cliente_telefono))
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
               turnos.cliente_nombre, turnos.cliente_telefono,
               peluqueros.nombre AS peluquero_nombre,
               servicios.nombre AS servicio_nombre, servicios.precio AS servicio_precio
        FROM turnos
        INNER JOIN peluqueros ON peluqueros.id = turnos.peluquero_id
        INNER JOIN servicios ON servicios.id_servicio = turnos.servicio_id
        WHERE turnos.id = ?
    """, (turno_id,)).fetchone()
    conexion.close()
    return render_template("confirmacion_turno.html", turno=turno)


# =====================================================================
# RUTAS DE ADMINISTRACIÓN
# =====================================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Inicio de sesión seguro para el administrador."""
    if session.get("admin_id"):
        return redirect(url_for("admin_agenda"))

    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        contrasena = request.form.get("contrasena", "")

        conexion = obtener_conexion()
        admin = conexion.execute(
            "SELECT * FROM administradores WHERE usuario = ?", (usuario,)
        ).fetchone()
        conexion.close()

        if admin and check_password_hash(admin["contrasena_hash"], contrasena):
            session["admin_id"] = admin["id"]
            session["admin_nombre"] = admin["nombre"]
            return redirect(url_for("admin_agenda"))
        else:
            error = "Usuario o contraseña incorrectos."

    return render_template("admin/login.html", error=error)


@app.get("/admin/logout")
def admin_logout():
    """Cierra la sesión del administrador."""
    session.pop("admin_id", None)
    session.pop("admin_nombre", None)
    return redirect(url_for("admin_login"))


@app.get("/admin/agenda")
@admin_requerido
def admin_agenda():
    """Panel de control con agenda semanal interactiva y métricas clave."""
    fecha_param = request.args.get("fecha")
    try:
        if fecha_param:
            fecha_ref = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        else:
            fecha_ref = date.today()
    except ValueError:
        fecha_ref = date.today()

    inicio_semana = fecha_ref - timedelta(days=fecha_ref.weekday())
    semana_anterior = (inicio_semana - timedelta(days=7)).strftime("%Y-%m-%d")
    semana_siguiente = (inicio_semana + timedelta(days=7)).strftime("%Y-%m-%d")
    hoy_iso = date.today().strftime("%Y-%m-%d")

    nombres_dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    dias_semana = []
    fechas_cortas = []
    for i in range(6):
        dia_d = inicio_semana + timedelta(days=i)
        fc = dia_d.strftime("%d/%m")
        fechas_cortas.append(fc)
        dias_semana.append({
            "nombre": nombres_dias[i],
            "fecha_corta": fc,
            "es_hoy": dia_d == date.today(),
            "dia_numero": dia_d.day,
            "mes_numero": dia_d.strftime("%m")
        })

    peluquero_id_str = request.args.get("peluquero_id", "")
    peluquero_id = int(peluquero_id_str) if peluquero_id_str.isdigit() else None

    conexion = obtener_conexion()
    peluqueros = conexion.execute("SELECT id, nombre FROM peluqueros ORDER BY nombre").fetchall()

    placeholders = ",".join("?" for _ in fechas_cortas)
    query = f"""
        SELECT turnos.id, turnos.peluquero_id, turnos.servicio_id, turnos.fecha, turnos.hora,
               turnos.estado, turnos.cliente_nombre, turnos.cliente_telefono,
               peluqueros.nombre AS peluquero_nombre,
               servicios.nombre AS servicio_nombre, servicios.precio AS servicio_precio
        FROM turnos
        INNER JOIN peluqueros ON peluqueros.id = turnos.peluquero_id
        INNER JOIN servicios ON servicios.id_servicio = turnos.servicio_id
        WHERE turnos.fecha IN ({placeholders})
    """
    params = list(fechas_cortas)
    if peluquero_id:
        query += " AND turnos.peluquero_id = ?"
        params.append(peluquero_id)
    query += " ORDER BY turnos.hora ASC"

    turnos_semana = conexion.execute(query, params).fetchall()

    agenda_matriz = {fc: {h: [] for h in HORARIOS} for fc in fechas_cortas}

    fecha_hoy_corta = date.today().strftime("%d/%m")
    turnos_hoy_cont = 0
    turnos_semana_cont = 0
    facturacion_estimada = 0

    for t in turnos_semana:
        fc = t["fecha"]
        h = t["hora"]
        if fc in agenda_matriz and h in agenda_matriz[fc]:
            agenda_matriz[fc][h].append(t)
        if t["estado"] != "cancelado":
            turnos_semana_cont += 1
            facturacion_estimada += t["servicio_precio"]
            if fc == fecha_hoy_corta:
                turnos_hoy_cont += 1

    conexion.close()

    return render_template(
        "admin/agenda.html",
        dias_semana=dias_semana,
        horarios=HORARIOS,
        agenda_matriz=agenda_matriz,
        peluqueros=peluqueros,
        peluquero_id_seleccionado=peluquero_id,
        inicio_semana=inicio_semana,
        semana_anterior=semana_anterior,
        semana_siguiente=semana_siguiente,
        hoy_iso=hoy_iso,
        fecha_ref=fecha_ref,
        turnos_hoy_cont=turnos_hoy_cont,
        turnos_semana_cont=turnos_semana_cont,
        facturacion_estimada=facturacion_estimada,
        admin_nombre=session.get("admin_nombre", "Administrador")
    )


@app.post("/admin/turnos/<int:turno_id>/cambiar-estado")
@admin_requerido
def cambiar_estado_turno(turno_id):
    """Permite al administrador cambiar el estado de un turno (confirmado, completado, cancelado)."""
    nuevo_estado = request.form.get("estado")
    estados_validos = ["pendiente", "confirmado", "completado", "cancelado"]
    if nuevo_estado in estados_validos:
        conexion = obtener_conexion()
        conexion.execute(
            "UPDATE turnos SET estado = ? WHERE id = ?", (nuevo_estado, turno_id)
        )
        conexion.commit()
        conexion.close()

    retorno = request.referrer or url_for("admin_agenda")
    return redirect(retorno)


crear_base_de_datos()


if __name__ == "__main__":
    app.run(debug=True)
