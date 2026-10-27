import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = "flama-barber-proyecto-escolar"

RUTA_BASE_DE_DATOS = "peluqueria.db"

SERVICIOS_INICIALES = [
    {"nombre": "Corte", "precio": 12000, "descripcion": "Corte moderno con degradé o tijera", "duracion": 30},
    {"nombre": "Corte clásico", "precio": 10000, "descripcion": "Corte tradicional prolijo", "duracion": 30},
    {"nombre": "Corte + ceja", "precio": 13000, "descripcion": "Corte completo y perfilado de cejas", "duracion": 40},
    {"nombre": "Tintura", "precio": 15000, "descripcion": "Coloración profesional para cabello", "duracion": 60}
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

DIAS_SEMANA = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
MESES_ABREV = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]

# Las contraseñas se guardan como hashes, nunca se envían a las plantillas ni en texto plano.
# Contraseña para alexander y miriam: "peluqueria.26"
ADMINISTRADORES_INICIALES = [
    {
        "usuario": "alexander",
        "contrasena_hash": "scrypt:32768:8:1$VCbjJXzhWLUtGAgG$4bc1b9ebf11d79f0facc545e60a30a62c9f86ccd2dc0886455f8f8a9f32313a8a98a98c2975787a975b982e7b7689f74e1ca647735fc108ebf94bde350d3127d",
        "nombre": "Alex"
    },
    {
        "usuario": "miriam",
        "contrasena_hash": "scrypt:32768:8:1$VCbjJXzhWLUtGAgG$4bc1b9ebf11d79f0facc545e60a30a62c9f86ccd2dc0886455f8f8a9f32313a8a98a98c2975787a975b982e7b7689f74e1ca647735fc108ebf94bde350d3127d",
        "nombre": "Miriam"
    }
]


def fecha_es_pasada(fecha_str, fecha_referencia=None):
    """Devuelve 1 si la fecha (DD/MM) es estrictamente anterior a hoy, o 0 si es hoy o futura."""
    if not fecha_str:
        return 1
    try:
        dia, mes = map(int, str(fecha_str).split("/"))
        hoy = fecha_referencia or date.today()
        anio = hoy.year
        if hoy.month == 12 and mes == 1:
            anio += 1
        elif hoy.month == 1 and mes == 12:
            anio -= 1
        fecha_turno = date(anio, mes, dia)
        return 1 if fecha_turno < hoy else 0
    except Exception:
        return 1


def obtener_conexion():
    """Crea una conexión con la base de datos SQLite con funciones personalizadas."""
    conexion = sqlite3.connect(RUTA_BASE_DE_DATOS)
    conexion.row_factory = sqlite3.Row
    conexion.create_function("fecha_es_pasada", 1, fecha_es_pasada)
    return conexion


def crear_base_de_datos():
    """Crea las tablas y carga datos iniciales seguros."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('barberia_activa', '1')")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS servicios (
            id_servicio INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            precio INTEGER NOT NULL,
            descripcion TEXT DEFAULT '',
            duracion INTEGER DEFAULT 30,
            activo INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS peluqueros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            foto TEXT,
            activo INTEGER DEFAULT 1
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
            estado TEXT NOT NULL DEFAULT 'Confirmado',
            editado INTEGER DEFAULT 0,
            fecha_edicion TEXT DEFAULT '',
            cambio_detalle TEXT DEFAULT '',
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

    # Migración de columnas en servicios existentes
    columnas_servicios = [col["name"] for col in cursor.execute("PRAGMA table_info(servicios)").fetchall()]
    if "descripcion" not in columnas_servicios:
        cursor.execute("ALTER TABLE servicios ADD COLUMN descripcion TEXT DEFAULT ''")
    if "duracion" not in columnas_servicios:
        cursor.execute("ALTER TABLE servicios ADD COLUMN duracion INTEGER DEFAULT 30")
    if "activo" not in columnas_servicios:
        cursor.execute("ALTER TABLE servicios ADD COLUMN activo INTEGER DEFAULT 1")

    # Migración retrocompatible para columnas en tabla turnos existente
    columnas_turnos = [col["name"] for col in cursor.execute("PRAGMA table_info(turnos)").fetchall()]
    if "cliente_nombre" not in columnas_turnos:
        cursor.execute("ALTER TABLE turnos ADD COLUMN cliente_nombre TEXT DEFAULT 'Cliente'")
    if "cliente_telefono" not in columnas_turnos:
        cursor.execute("ALTER TABLE turnos ADD COLUMN cliente_telefono TEXT DEFAULT ''")
    if "editado" not in columnas_turnos:
        cursor.execute("ALTER TABLE turnos ADD COLUMN editado INTEGER DEFAULT 0")
    if "fecha_edicion" not in columnas_turnos:
        cursor.execute("ALTER TABLE turnos ADD COLUMN fecha_edicion TEXT DEFAULT ''")
    if "cambio_detalle" not in columnas_turnos:
        cursor.execute("ALTER TABLE turnos ADD COLUMN cambio_detalle TEXT DEFAULT ''")

    # Migración de columna activo en peluqueros
    columnas_peluqueros = [col["name"] for col in cursor.execute("PRAGMA table_info(peluqueros)").fetchall()]
    if "activo" not in columnas_peluqueros:
        cursor.execute("ALTER TABLE peluqueros ADD COLUMN activo INTEGER DEFAULT 1")

    # Las reglas se recrean luego de las migraciones para no bloquear datos históricos.
    cursor.execute("DROP TRIGGER IF EXISTS impedir_turno_superpuesto_insert")
    cursor.execute("DROP TRIGGER IF EXISTS impedir_turno_superpuesto_update")

    # Normalizar estados existentes al nuevo sistema estándar
    cursor.execute("UPDATE turnos SET estado = 'Confirmado' WHERE LOWER(estado) IN ('pendiente', 'confirmado') AND editado = 0")
    cursor.execute("UPDATE turnos SET estado = 'Editado' WHERE editado = 1 AND LOWER(estado) NOT IN ('cancelado', 'completado')")
    cursor.execute("UPDATE turnos SET estado = 'Cancelado' WHERE LOWER(estado) = 'cancelado'")
    cursor.execute("UPDATE turnos SET estado = 'Completado' WHERE LOWER(estado) = 'completado'")

    # Configura los dos administradores del sistema con contraseñas hasheadas.
    for administrador in ADMINISTRADORES_INICIALES:
        cursor.execute("""
            INSERT INTO administradores (usuario, contrasena_hash, nombre)
            VALUES (?, ?, ?)
            ON CONFLICT(usuario) DO UPDATE SET
                contrasena_hash = excluded.contrasena_hash,
                nombre = excluded.nombre
        """, (
            administrador["usuario"],
            administrador["contrasena_hash"],
            administrador["nombre"]
        ))

    cursor.execute("DELETE FROM administradores WHERE usuario IN ('admin', 'Alex', 'Miriam')")

    for servicio in SERVICIOS_INICIALES:
        cursor.execute("""
            INSERT OR IGNORE INTO servicios (nombre, precio, descripcion, duracion, activo)
            VALUES (?, ?, ?, ?, 1)
        """, (servicio["nombre"], servicio["precio"], servicio.get("descripcion", ""), servicio.get("duracion", 30)))

    for nombre, especialidades in ESPECIALIDADES_INICIALES.items():
        cursor.execute("INSERT OR IGNORE INTO peluqueros (nombre, foto, activo) VALUES (?, ?, 1)", (nombre, ""))
        peluquero_id = cursor.execute(
            "SELECT id FROM peluqueros WHERE nombre = ?", (nombre,)
        ).fetchone()["id"]

        for especialidad in especialidades:
            servicio_row = cursor.execute(
                "SELECT id_servicio FROM servicios WHERE nombre = ?", (especialidad,)
            ).fetchone()
            if servicio_row:
                cursor.execute("""
                    INSERT OR IGNORE INTO peluquero_servicios (peluquero_id, servicio_id)
                    VALUES (?, ?)
                """, (peluquero_id, servicio_row["id_servicio"]))

    # Protección final en SQLite para evitar solapamientos, incluso ante escrituras simultáneas.
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS impedir_turno_superpuesto_insert
        BEFORE INSERT ON turnos
        WHEN LOWER(NEW.estado) != 'cancelado'
        AND EXISTS (
            SELECT 1 FROM turnos
            WHERE peluquero_id = NEW.peluquero_id
              AND fecha = NEW.fecha
              AND hora = NEW.hora
              AND LOWER(estado) != 'cancelado'
        )
        BEGIN
            SELECT RAISE(ABORT, 'horario reservado');
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS impedir_turno_superpuesto_update
        BEFORE UPDATE OF peluquero_id, fecha, hora, estado ON turnos
        WHEN LOWER(NEW.estado) != 'cancelado'
        AND EXISTS (
            SELECT 1 FROM turnos
            WHERE peluquero_id = NEW.peluquero_id
              AND fecha = NEW.fecha
              AND hora = NEW.hora
              AND id != NEW.id
              AND LOWER(estado) != 'cancelado'
        )
        BEGIN
            SELECT RAISE(ABORT, 'horario reservado');
        END
    """)

    conexion.commit()
    conexion.close()


def obtener_estado_barberia():
    """Devuelve True si la barbería está abierta a clientes, o False si está desactivada."""
    conexion = obtener_conexion()
    fila = conexion.execute("SELECT valor FROM configuracion WHERE clave = 'barberia_activa'").fetchone()
    conexion.close()
    return fila["valor"] == "1" if fila else True


def cambiar_estado_barberia(activo: bool):
    """Guarda en SQLite el estado general de la barbería (1 = activa, 0 = cerrada)."""
    conexion = obtener_conexion()
    conexion.execute("""
        INSERT INTO configuracion (clave, valor) VALUES ('barberia_activa', ?)
        ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
    """, ("1" if activo else "0",))
    conexion.commit()
    conexion.close()


def puede_modificar_turno(fecha_str, hora_str, momento_actual=None, accion="modificar"):
    """Verifica si faltan al menos 2 horas para el inicio del turno original (aplica a edición y cancelación)."""
    try:
        dia, mes = map(int, str(fecha_str).split("/"))
        hora, minuto = map(int, str(hora_str).split(":"))
        ahora = momento_actual or datetime.now()
        anio = ahora.year
        if ahora.month == 12 and mes == 1:
            anio += 1
        elif ahora.month == 1 and mes == 12:
            anio -= 1
        inicio_turno = datetime(anio, mes, dia, hora, minuto)
        limite = inicio_turno - timedelta(hours=2)
        if ahora > limite:
            verbo = "cancelar" if accion == "cancelar" else "modificar"
            return False, f"Este turno ya no se puede {verbo} porque faltan menos de 2 horas."
        return True, ""
    except Exception:
        verbo = "cancelar" if accion == "cancelar" else "modificar"
        return False, f"No se pudo determinar el horario para {verbo} el turno."


def turno_ya_ocurrio(fecha_str, hora_str, momento_actual=None):
    """Devuelve True si la fecha y hora del turno ya transcurrieron en el tiempo."""
    try:
        dia, mes = map(int, str(fecha_str).split("/"))
        hora, minuto = map(int, str(hora_str).split(":"))
        ahora = momento_actual or datetime.now()
        anio = ahora.year
        if ahora.month == 12 and mes == 1:
            anio += 1
        elif ahora.month == 1 and mes == 12:
            anio -= 1
        inicio_turno = datetime(anio, mes, dia, hora, minuto)
        return ahora >= inicio_turno
    except Exception:
        return True


def obtener_horarios_ocupados(peluquero_id, fecha_str, turno_id_excluir=None, conexion=None):
    """Devuelve los horarios ocupados, sin contar turnos cancelados."""
    conexion_propia = conexion is None
    if conexion_propia:
        conexion = obtener_conexion()

    query = """
        SELECT hora FROM turnos
        WHERE peluquero_id = ? AND fecha = ? AND LOWER(estado) != 'cancelado'
    """
    params = [peluquero_id, fecha_str]
    if turno_id_excluir:
        query += " AND id != ?"
        params.append(turno_id_excluir)
    filas = conexion.execute(query, params).fetchall()

    if conexion_propia:
        conexion.close()

    return {fila["hora"] for fila in filas}


def verificar_disponibilidad_turno(peluquero_id, fecha_str, hora_str, turno_id_excluir=None, conexion=None):
    """Verifica si un horario está disponible para un peluquero en una fecha determinada."""
    horarios_ocupados = obtener_horarios_ocupados(
        peluquero_id, fecha_str, turno_id_excluir, conexion
    )
    return hora_str not in horarios_ocupados


def fecha_iso_a_corta(fecha_iso):
    """Convierte una fecha AAAA-MM-DD al formato DD/MM guardado en SQLite."""
    try:
        return datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d/%m")
    except ValueError:
        return ""


def generar_proximos_dias(cantidad=14):
    """Genera la lista de próximos días a partir de hoy, identificando los lunes cerrados."""
    hoy = date.today()
    dias = []
    for i in range(cantidad):
        dia_fecha = hoy + timedelta(days=i)
        es_lunes = dia_fecha.weekday() == 0
        dias.append({
            "fecha_str": dia_fecha.strftime("%Y-%m-%d"),
            "dia_nombre": DIAS_SEMANA[dia_fecha.weekday()],
            "dia_numero": dia_fecha.day,
            "mes_nombre": MESES_ABREV[dia_fecha.month - 1],
            "cerrado": es_lunes
        })
    return dias


def obtener_peluqueros(solo_activos=True):
    """Devuelve peluqueros y un resumen de sus especialidades (por defecto solo activos para clientes)."""
    conexion = obtener_conexion()
    query = """
        SELECT peluqueros.id, peluqueros.nombre, peluqueros.foto, peluqueros.activo,
               GROUP_CONCAT(servicios.nombre, ', ') AS especialidades
        FROM peluqueros
        LEFT JOIN peluquero_servicios ON peluqueros.id = peluquero_servicios.peluquero_id
        LEFT JOIN servicios ON servicios.id_servicio = peluquero_servicios.servicio_id
    """
    if solo_activos:
        query += " WHERE peluqueros.activo = 1 "
    query += """
        GROUP BY peluqueros.id
        ORDER BY peluqueros.nombre
    """
    peluqueros = conexion.execute(query).fetchall()
    conexion.close()
    return peluqueros


def admin_requerido(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorada


@app.route("/")
def inicio():
    barberia_activa = obtener_estado_barberia()
    return render_template("index.html", barberia_activa=barberia_activa)


@app.get("/reservar")
def iniciar_reserva():
    """Inicia una nueva reserva vacía."""
    session.pop("reserva", None)
    return redirect(url_for("elegir_peluquero"))


@app.get("/reservar/disponibilidad")
def disponibilidad_reserva():
    """Devuelve los horarios ya reservados para la fecha y peluquero elegidos."""
    reserva = session.get("reserva", {})
    fecha_corta = fecha_iso_a_corta(request.args.get("fecha", ""))

    if not reserva.get("peluquero_id") or not fecha_corta:
        return jsonify({"ocupados": []})

    ocupados = obtener_horarios_ocupados(reserva["peluquero_id"], fecha_corta)
    return jsonify({"ocupados": sorted(ocupados)})


@app.route("/reservar/peluquero", methods=["GET", "POST"])
def elegir_peluquero():
    """Permite seleccionar un peluquero activo."""
    if not obtener_estado_barberia():
        return redirect(url_for("inicio"))

    if request.method == "POST":
        peluquero_id = request.form.get("peluquero_id")
        conexion = obtener_conexion()
        peluquero = conexion.execute("SELECT id, activo FROM peluqueros WHERE id = ?", (peluquero_id,)).fetchone()
        conexion.close()
        if not peluquero or peluquero["activo"] == 0:
            return redirect(url_for("elegir_peluquero"))

        session["reserva"] = {"peluquero_id": peluquero_id}
        return redirect(url_for("elegir_servicio"))

    return render_template("reserva_peluquero.html", peluqueros=obtener_peluqueros(solo_activos=True), reserva=session.get("reserva", {}))


@app.route("/reservar/servicio", methods=["GET", "POST"])
def elegir_servicio():
    """Muestra solo los servicios activos asociados al peluquero seleccionado."""
    if not obtener_estado_barberia():
        return redirect(url_for("inicio"))

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
        SELECT servicios.id_servicio, servicios.nombre, servicios.precio, servicios.descripcion, servicios.duracion
        FROM servicios
        INNER JOIN peluquero_servicios ON servicios.id_servicio = peluquero_servicios.servicio_id
        WHERE peluquero_servicios.peluquero_id = ? AND servicios.activo = 1
        ORDER BY servicios.nombre
    """, (reserva["peluquero_id"],)).fetchall()
    conexion.close()
    return render_template("reserva_servicio.html", peluquero=peluquero, servicios=servicios, reserva=reserva)


@app.route("/reservar/fecha-hora", methods=["GET", "POST"])
def elegir_fecha_hora():
    """Permite elegir fecha, hora y datos del cliente; valida los datos y guarda el turno."""
    if not obtener_estado_barberia():
        return redirect(url_for("inicio"))

    reserva = session.get("reserva")
    if not reserva or not reserva.get("servicio_id"):
        return redirect(url_for("elegir_peluquero"))

    conexion = obtener_conexion()
    peluquero = conexion.execute(
        "SELECT id, nombre FROM peluqueros WHERE id = ?", (reserva["peluquero_id"],)
    ).fetchone()
    servicio = conexion.execute(
        "SELECT id_servicio, nombre, precio FROM servicios WHERE id_servicio = ?", (reserva["servicio_id"],)
    ).fetchone()

    fecha_minima = date.today().strftime("%Y-%m-%d")
    proximos_dias = generar_proximos_dias(14)
    primer_dia_disponible = next((d["fecha_str"] for d in proximos_dias if not d["cerrado"]), fecha_minima)

    if request.method == "POST":
        fecha_str = request.form.get("fecha", "").strip()
        hora = request.form.get("hora", "").strip()
        cliente_nombre = request.form.get("cliente_nombre", "").strip()
        cliente_telefono = request.form.get("cliente_telefono", "").strip()

        fecha_obj = None
        if fecha_str:
            try:
                fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        if not fecha_obj:
            error = "Por favor, seleccioná una fecha válida."
            conexion.close()
            return render_template(
                "reserva_fecha_hora.html",
                peluquero=peluquero,
                servicio=servicio,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_minima=fecha_minima,
                error=error,
                fecha_seleccionada=fecha_str or primer_dia_disponible,
                hora_seleccionada=hora,
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono
            )

        if fecha_obj < date.today():
            error = "No podés reservar en una fecha anterior al día de hoy."
            conexion.close()
            return render_template(
                "reserva_fecha_hora.html",
                peluquero=peluquero,
                servicio=servicio,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_minima=fecha_minima,
                error=error,
                fecha_seleccionada=fecha_str or primer_dia_disponible,
                hora_seleccionada=hora,
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono
            )

        if fecha_obj.weekday() == 0:
            error = "Los lunes la barbería permanece cerrada. Por favor, seleccioná otro día."
            conexion.close()
            return render_template(
                "reserva_fecha_hora.html",
                peluquero=peluquero,
                servicio=servicio,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_minima=fecha_minima,
                error=error,
                fecha_seleccionada=fecha_str or primer_dia_disponible,
                hora_seleccionada=hora,
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono
            )

        if not cliente_nombre:
            error = "Por favor, ingresá tu nombre completo."
            conexion.close()
            return render_template(
                "reserva_fecha_hora.html",
                peluquero=peluquero,
                servicio=servicio,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_minima=fecha_minima,
                error=error,
                fecha_seleccionada=fecha_str or primer_dia_disponible,
                hora_seleccionada=hora,
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono
            )

        telefono_digitos = "".join(ch for ch in cliente_telefono if ch.isdigit())
        if len(telefono_digitos) != 10:
            error = "El número de teléfono debe tener exactamente 10 dígitos (ej: 3512345678)."
            conexion.close()
            return render_template(
                "reserva_fecha_hora.html",
                peluquero=peluquero,
                servicio=servicio,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_minima=fecha_minima,
                error=error,
                fecha_seleccionada=fecha_str or primer_dia_disponible,
                hora_seleccionada=hora,
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono
            )

        if not hora or hora not in HORARIOS:
            error = "Por favor, seleccioná un horario disponible de la lista."
            conexion.close()
            return render_template(
                "reserva_fecha_hora.html",
                peluquero=peluquero,
                servicio=servicio,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_minima=fecha_minima,
                error=error,
                fecha_seleccionada=fecha_str or primer_dia_disponible,
                hora_seleccionada=hora,
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono
            )

        fecha_formateada = fecha_obj.strftime("%d/%m")

        # Esta transacción bloquea escrituras simultáneas mientras vuelve a comprobar la disponibilidad.
        conexion.execute("BEGIN IMMEDIATE")
        if not verificar_disponibilidad_turno(
            reserva["peluquero_id"], fecha_formateada, hora, conexion=conexion
        ):
            conexion.rollback()
            error = "El horario seleccionado ya no se encuentra disponible. Por favor, elegí otro."
            conexion.close()
            return render_template(
                "reserva_fecha_hora.html",
                peluquero=peluquero,
                servicio=servicio,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_minima=fecha_minima,
                error=error,
                fecha_seleccionada=fecha_str or primer_dia_disponible,
                hora_seleccionada=hora,
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono
            )

        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO turnos (peluquero_id, servicio_id, fecha, hora, cliente_nombre, cliente_telefono, estado)
            VALUES (?, ?, ?, ?, ?, ?, 'Confirmado')
        """, (reserva["peluquero_id"], reserva["servicio_id"], fecha_formateada, hora, cliente_nombre, cliente_telefono))
        turno_id = cursor.lastrowid
        conexion.commit()
        conexion.close()

        session.pop("reserva", None)
        return redirect(url_for("confirmacion_turno", turno_id=turno_id))

    conexion.close()
    return render_template(
        "reserva_fecha_hora.html",
        peluquero=peluquero,
        servicio=servicio,
        horarios=HORARIOS,
        proximos_dias=proximos_dias,
        fecha_minima=fecha_minima,
        fecha_seleccionada=primer_dia_disponible
    )


@app.route("/confirmacion/<int:turno_id>")
@app.route("/turnos/<int:turno_id>/confirmacion")
def confirmacion_turno(turno_id):
    conexion = obtener_conexion()
    turno = conexion.execute("""
        SELECT turnos.id, turnos.fecha, turnos.hora, turnos.cliente_nombre, turnos.cliente_telefono,
               peluqueros.nombre AS peluquero_nombre,
               servicios.nombre AS servicio_nombre, servicios.precio AS servicio_precio
        FROM turnos
        INNER JOIN peluqueros ON peluqueros.id = turnos.peluquero_id
        INNER JOIN servicios ON servicios.id_servicio = turnos.servicio_id
        WHERE turnos.id = ?
    """, (turno_id,)).fetchone()
    conexion.close()

    if not turno:
        return redirect(url_for("inicio"))

    modificado = request.args.get("modificado") == "1"
    return render_template("confirmacion_turno.html", turno=turno, modificado=modificado)


@app.route("/turnos/consultar", methods=["GET", "POST"])
def consultar_turno():
    """Permite al cliente buscar sus turnos divididos en 'Próximos turnos' y 'Turnos anteriores'."""
    busqueda = request.form.get("busqueda", "").strip() if request.method == "POST" else request.args.get("busqueda", "").strip()
    turnos_proximos = []
    turnos_anteriores = []
    busqueda_realizada = False
    error = None
    mensaje_cancelado = "Turno cancelado correctamente. El horario ha quedado disponible nuevamente." if request.args.get("cancelado") else None

    if busqueda:
        busqueda_realizada = True
        conexion = obtener_conexion()
        query = """
            SELECT turnos.id, turnos.fecha, turnos.hora, turnos.estado,
                   turnos.cliente_nombre, turnos.cliente_telefono,
                   turnos.editado, turnos.fecha_edicion, turnos.cambio_detalle,
                   peluqueros.nombre AS peluquero_nombre,
                   servicios.nombre AS servicio_nombre, servicios.precio AS servicio_precio
            FROM turnos
            INNER JOIN peluqueros ON peluqueros.id = turnos.peluquero_id
            INNER JOIN servicios ON servicios.id_servicio = turnos.servicio_id
            WHERE (turnos.cliente_telefono = ? OR turnos.id = ?)
            ORDER BY turnos.id DESC
        """
        turnos_rows = conexion.execute(query, (busqueda, busqueda)).fetchall()
        conexion.close()

        for t in turnos_rows:
            t_dict = dict(t)
            es_pasado = bool(fecha_es_pasada(t["fecha"]))
            estado_lower = t["estado"].lower()

            if es_pasado or estado_lower in ("cancelado", "completado"):
                turnos_anteriores.append(t_dict)
            else:
                puede_e, motivo_e = puede_modificar_turno(t["fecha"], t["hora"], accion="modificar")
                puede_c, motivo_c = puede_modificar_turno(t["fecha"], t["hora"], accion="cancelar")
                t_dict["puede_editar"] = puede_e
                t_dict["puede_cancelar"] = puede_c
                t_dict["motivo_bloqueo"] = motivo_e or motivo_c
                turnos_proximos.append(t_dict)

    return render_template(
        "consultar_turno.html",
        turnos_proximos=turnos_proximos,
        turnos_anteriores=turnos_anteriores,
        busqueda=busqueda,
        busqueda_realizada=busqueda_realizada,
        error=error,
        mensaje_cancelado=mensaje_cancelado
    )


@app.post("/turnos/<int:turno_id>/cancelar")
def cancelar_turno(turno_id):
    """Permite al cliente cancelar un turno con la regla de las 2 horas de anticipación."""
    conexion = obtener_conexion()
    turno = conexion.execute("SELECT * FROM turnos WHERE id = ?", (turno_id,)).fetchone()
    if not turno:
        conexion.close()
        return redirect(url_for("consultar_turno"))

    puede_cancelar, motivo = puede_modificar_turno(turno["fecha"], turno["hora"], accion="cancelar")
    if not puede_cancelar:
        conexion.close()
        return render_template(
            "consultar_turno.html",
            error=motivo,
            busqueda=turno["cliente_telefono"],
            busqueda_realizada=True,
            turnos_proximos=[dict(turno, puede_editar=False, puede_cancelar=False, motivo_bloqueo=motivo)],
            turnos_anteriores=[]
        ), 400

    conexion.execute("UPDATE turnos SET estado = 'Cancelado' WHERE id = ?", (turno_id,))
    conexion.commit()
    conexion.close()

    telefono = turno["cliente_telefono"] or ""
    return redirect(url_for("consultar_turno", busqueda=telefono, cancelado=1))


@app.get("/turnos/<int:turno_id>/disponibilidad")
def disponibilidad_edicion(turno_id):
    """Devuelve horarios ocupados al modificar un turno, excluyendo el turno actual."""
    fecha_corta = fecha_iso_a_corta(request.args.get("fecha", ""))
    conexion = obtener_conexion()
    turno = conexion.execute(
        "SELECT peluquero_id FROM turnos WHERE id = ?", (turno_id,)
    ).fetchone()

    if not turno or not fecha_corta:
        conexion.close()
        return jsonify({"ocupados": []})

    ocupados = obtener_horarios_ocupados(
        turno["peluquero_id"], fecha_corta, turno_id, conexion
    )
    conexion.close()
    return jsonify({"ocupados": sorted(ocupados)})


@app.route("/turnos/<int:turno_id>/editar", methods=["GET", "POST"])
def editar_turno(turno_id):
    """Permite al cliente seleccionar una nueva fecha y horario para un turno existente."""
    if not obtener_estado_barberia():
        return redirect(url_for("inicio"))

    conexion = obtener_conexion()
    turno = conexion.execute("""
        SELECT turnos.id, turnos.peluquero_id, turnos.servicio_id, turnos.fecha, turnos.hora,
               turnos.cliente_nombre, turnos.cliente_telefono, turnos.estado,
               peluqueros.nombre AS peluquero_nombre,
               servicios.nombre AS servicio_nombre, servicios.precio AS servicio_precio
        FROM turnos
        INNER JOIN peluqueros ON peluqueros.id = turnos.peluquero_id
        INNER JOIN servicios ON servicios.id_servicio = turnos.servicio_id
        WHERE turnos.id = ?
    """, (turno_id,)).fetchone()
    conexion.close()

    if not turno:
        return redirect(url_for("consultar_turno"))

    if fecha_es_pasada(turno["fecha"]):
        return render_template(
            "consultar_turno.html",
            error="No se pueden consultar ni modificar turnos de fechas anteriores.",
            busqueda=turno["cliente_telefono"],
            busqueda_realizada=True,
            turnos_proximos=[],
            turnos_anteriores=[]
        ), 400

    puede_editar, motivo = puede_modificar_turno(turno["fecha"], turno["hora"], accion="modificar")
    if not puede_editar:
        return render_template(
            "consultar_turno.html",
            error=motivo,
            busqueda=turno["cliente_telefono"],
            busqueda_realizada=True,
            turnos_proximos=[dict(turno, puede_editar=False, puede_cancelar=False, motivo_bloqueo=motivo)],
            turnos_anteriores=[]
        ), 400

    fecha_minima = date.today().strftime("%Y-%m-%d")
    proximos_dias = generar_proximos_dias(14)
    primer_dia_disponible = next((d["fecha_str"] for d in proximos_dias if not d["cerrado"]), fecha_minima)

    if request.method == "POST":
        nueva_fecha_str = request.form.get("fecha", "").strip()
        nueva_hora = request.form.get("hora", "").strip()

        fecha_obj = None
        if nueva_fecha_str:
            try:
                fecha_obj = datetime.strptime(nueva_fecha_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        if not fecha_obj:
            error = "Por favor, seleccioná una fecha válida."
            return render_template(
                "editar_turno.html",
                turno=turno,
                error=error,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_seleccionada=nueva_fecha_str or primer_dia_disponible,
                hora_seleccionada=nueva_hora
            ), 400

        if fecha_obj < date.today():
            error = "No se puede reservar un turno para una fecha que ya pasó."
            return render_template(
                "editar_turno.html",
                turno=turno,
                error=error,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_seleccionada=nueva_fecha_str or primer_dia_disponible,
                hora_seleccionada=nueva_hora
            ), 400

        if fecha_obj.weekday() == 0:
            error = "Los lunes la barbería permanece cerrada. Por favor, seleccioná otro día."
            return render_template(
                "editar_turno.html",
                turno=turno,
                error=error,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_seleccionada=nueva_fecha_str or primer_dia_disponible,
                hora_seleccionada=nueva_hora
            ), 400

        if not nueva_hora:
            error = "Por favor, seleccioná un horario para tu nuevo turno."
            return render_template(
                "editar_turno.html",
                turno=turno,
                error=error,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_seleccionada=nueva_fecha_str or primer_dia_disponible,
                hora_seleccionada=nueva_hora
            ), 400

        nueva_fecha_formateada = fecha_obj.strftime("%d/%m")

        if not verificar_disponibilidad_turno(turno["peluquero_id"], nueva_fecha_formateada, nueva_hora, turno_id_excluir=turno["id"]):
            error = "Ese horario ya no está disponible. Elegí otro horario."
            return render_template(
                "editar_turno.html",
                turno=turno,
                error=error,
                horarios=HORARIOS,
                proximos_dias=proximos_dias,
                fecha_seleccionada=nueva_fecha_str or primer_dia_disponible,
                hora_seleccionada=nueva_hora
            ), 400

        return render_template(
            "confirmar_modificacion_turno.html",
            turno=turno,
            nueva_fecha_formateada=nueva_fecha_formateada,
            nueva_fecha_iso=nueva_fecha_str,
            nueva_hora=nueva_hora
        )

    return render_template(
        "editar_turno.html",
        turno=turno,
        horarios=HORARIOS,
        proximos_dias=proximos_dias,
        fecha_seleccionada=primer_dia_disponible,
        hora_seleccionada=turno["hora"]
    )


@app.post("/turnos/<int:turno_id>/guardar-edicion")
def guardar_edicion_turno(turno_id):
    """Aplica la modificación sobre el turno existente en SQLite sin duplicarlo."""
    if not obtener_estado_barberia():
        return redirect(url_for("inicio"))

    conexion = obtener_conexion()
    turno = conexion.execute("SELECT * FROM turnos WHERE id = ?", (turno_id,)).fetchone()
    if not turno:
        conexion.close()
        return redirect(url_for("consultar_turno"))

    puede_editar, motivo = puede_modificar_turno(turno["fecha"], turno["hora"], accion="modificar")
    if not puede_editar:
        conexion.close()
        return render_template("consultar_turno.html", error=motivo), 400

    nueva_fecha = request.form.get("nueva_fecha", "").strip()
    nueva_hora = request.form.get("nueva_hora", "").strip()

    if not nueva_fecha or not nueva_hora:
        conexion.close()
        return redirect(url_for("editar_turno", turno_id=turno_id))

    # Revisa dentro de una transacción para que otro cambio simultáneo no ocupe el mismo horario.
    conexion.execute("BEGIN IMMEDIATE")
    if not verificar_disponibilidad_turno(
        turno["peluquero_id"], nueva_fecha, nueva_hora,
        turno_id_excluir=turno["id"], conexion=conexion
    ):
        conexion.rollback()
        conexion.close()
        return redirect(url_for("editar_turno", turno_id=turno_id))

    turno_anterior_fecha = turno["fecha"]
    turno_anterior_hora = turno["hora"]
    cambio_detalle = f"Antes: {turno_anterior_fecha} - {turno_anterior_hora} hs → Ahora: {nueva_fecha} - {nueva_hora} hs"
    fecha_edicion = datetime.now().strftime("%d/%m/%Y %H:%M")

    conexion.execute("""
        UPDATE turnos
        SET fecha = ?, hora = ?, estado = 'Editado', editado = 1, fecha_edicion = ?, cambio_detalle = ?
        WHERE id = ?
    """, (nueva_fecha, nueva_hora, fecha_edicion, cambio_detalle, turno_id))
    conexion.commit()
    conexion.close()

    return redirect(url_for("confirmacion_turno", turno_id=turno_id, modificado=1))


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
    """Panel de control con dashboard de métricas, agenda semanal interactiva, historial y gestión."""
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
    peluqueros = conexion.execute("SELECT id, nombre, activo FROM peluqueros ORDER BY nombre").fetchall()

    placeholders = ",".join("?" for _ in fechas_cortas)
    query = f"""
        SELECT turnos.id, turnos.peluquero_id, turnos.servicio_id, turnos.fecha, turnos.hora,
               turnos.estado, turnos.cliente_nombre, turnos.cliente_telefono,
               turnos.editado, turnos.fecha_edicion, turnos.cambio_detalle,
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

    for t in turnos_semana:
        fc = t["fecha"]
        h = t["hora"]
        if fc in agenda_matriz and h in agenda_matriz[fc]:
            agenda_matriz[fc][h].append(t)

    # 1. MÉTRICAS DEL DASHBOARD DEL ADMINISTRADOR (calculadas directamente desde SQLite)
    turnos_hoy_kpi = conexion.execute(
        "SELECT COUNT(*) AS total FROM turnos WHERE fecha = ? AND LOWER(estado) != 'cancelado'",
        (fecha_hoy_corta,)
    ).fetchone()["total"]

    turnos_pendientes_kpi = conexion.execute("""
        SELECT COUNT(*) AS total FROM turnos
        WHERE fecha_es_pasada(fecha) = 0
          AND LOWER(estado) IN ('confirmado', 'editado', 'pendiente')
    """).fetchone()["total"]

    turnos_completados_kpi = conexion.execute(
        "SELECT COUNT(*) AS total FROM turnos WHERE LOWER(estado) = 'completado'"
    ).fetchone()["total"]

    turnos_cancelados_kpi = conexion.execute(
        "SELECT COUNT(*) AS total FROM turnos WHERE LOWER(estado) = 'cancelado'"
    ).fetchone()["total"]

    facturacion_estimada = sum(t["servicio_precio"] for t in turnos_semana if t["estado"].lower() != "cancelado")
    turnos_semana_cont = sum(1 for t in turnos_semana if t["estado"].lower() != "cancelado")

    # 2. HISTORIAL DE TURNOS CON FILTROS BÁSICOS
    hist_estado = request.args.get("hist_estado", "").strip()
    hist_peluquero = request.args.get("hist_peluquero", "").strip()
    hist_fecha = request.args.get("hist_fecha", "").strip()

    hist_query = """
        SELECT turnos.id, turnos.fecha, turnos.hora, turnos.estado,
               turnos.cliente_nombre, turnos.cliente_telefono,
               turnos.editado, turnos.fecha_edicion, turnos.cambio_detalle,
               peluqueros.nombre AS peluquero_nombre,
               servicios.nombre AS servicio_nombre, servicios.precio AS servicio_precio
        FROM turnos
        INNER JOIN peluqueros ON peluqueros.id = turnos.peluquero_id
        INNER JOIN servicios ON servicios.id_servicio = turnos.servicio_id
        WHERE 1=1
    """
    hist_params = []
    if hist_estado:
        hist_query += " AND LOWER(turnos.estado) = ?"
        hist_params.append(hist_estado.lower())
    if hist_peluquero and hist_peluquero.isdigit():
        hist_query += " AND turnos.peluquero_id = ?"
        hist_params.append(int(hist_peluquero))
    if hist_fecha:
        if "-" in hist_fecha:
            try:
                f_obj = datetime.strptime(hist_fecha, "%Y-%m-%d").date()
                hist_query += " AND turnos.fecha = ?"
                hist_params.append(f_obj.strftime("%d/%m"))
            except ValueError:
                pass
        else:
            hist_query += " AND turnos.fecha LIKE ?"
            hist_params.append(f"%{hist_fecha}%")

    hist_query += " ORDER BY turnos.id DESC LIMIT 150"
    turnos_historial = conexion.execute(hist_query, hist_params).fetchall()

    # 3. GESTIÓN DE SERVICIOS Y PELUQUEROS (con relación muchos a muchos)
    servicios_admin = conexion.execute("""
        SELECT servicios.id_servicio, servicios.nombre, servicios.precio, servicios.descripcion, servicios.duracion, servicios.activo,
               GROUP_CONCAT(peluqueros.nombre, ', ') AS peluqueros_nombres,
               GROUP_CONCAT(peluqueros.id, ',') AS peluqueros_ids
        FROM servicios
        LEFT JOIN peluquero_servicios ON servicios.id_servicio = peluquero_servicios.servicio_id
        LEFT JOIN peluqueros ON peluquero_servicios.peluquero_id = peluqueros.id
        GROUP BY servicios.id_servicio
        ORDER BY servicios.nombre
    """).fetchall()

    peluqueros_admin = conexion.execute("""
        SELECT peluqueros.id, peluqueros.nombre, peluqueros.activo,
               GROUP_CONCAT(servicios.nombre, ', ') AS especialidades
        FROM peluqueros
        LEFT JOIN peluquero_servicios ON peluqueros.id = peluquero_servicios.peluquero_id
        LEFT JOIN servicios ON servicios.id_servicio = peluquero_servicios.servicio_id
        GROUP BY peluqueros.id
        ORDER BY peluqueros.nombre
    """).fetchall()

    barberia_activa = obtener_estado_barberia()
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
        turnos_hoy_kpi=turnos_hoy_kpi,
        turnos_pendientes_kpi=turnos_pendientes_kpi,
        turnos_completados_kpi=turnos_completados_kpi,
        turnos_cancelados_kpi=turnos_cancelados_kpi,
        turnos_semana_cont=turnos_semana_cont,
        facturacion_estimada=facturacion_estimada,
        admin_nombre=session.get("admin_nombre", "Administrador"),
        servicios_admin=servicios_admin,
        peluqueros_admin=peluqueros_admin,
        turnos_historial=turnos_historial,
        filtro_hist_estado=hist_estado,
        filtro_hist_peluquero=hist_peluquero,
        filtro_hist_fecha=hist_fecha,
        barberia_activa=barberia_activa
    )


@app.post("/admin/turnos/<int:turno_id>/cambiar-estado")
@admin_requerido
def cambiar_estado_turno(turno_id):
    """Permite al administrador cambiar el estado de un turno (Confirmado, Completado, Cancelado, Editado)."""
    nuevo_estado = request.form.get("estado", "").capitalize()
    estados_validos = ["Confirmado", "Completado", "Cancelado", "Editado"]
    if nuevo_estado in estados_validos:
        conexion = obtener_conexion()
        conexion.execute(
            "UPDATE turnos SET estado = ? WHERE id = ?", (nuevo_estado, turno_id)
        )
        conexion.commit()
        conexion.close()

    retorno = request.referrer or url_for("admin_agenda")
    return redirect(retorno)


@app.post("/admin/turnos/<int:turno_id>/completar")
@admin_requerido
def admin_completar_turno(turno_id):
    """Marca un turno como completado en el panel de administración."""
    conexion = obtener_conexion()
    turno = conexion.execute("SELECT id, estado FROM turnos WHERE id = ?", (turno_id,)).fetchone()
    if turno:
        conexion.execute("UPDATE turnos SET estado = 'Completado' WHERE id = ?", (turno_id,))
        conexion.commit()
    conexion.close()
    return redirect(request.referrer or url_for("admin_agenda"))


@app.post("/admin/peluqueros/agregar")
@admin_requerido
def admin_agregar_peluquero():
    """Permite agregar un nuevo peluquero desde el panel de administración."""
    nombre = request.form.get("nombre", "").strip()
    if nombre:
        conexion = obtener_conexion()
        try:
            cursor = conexion.cursor()
            cursor.execute("INSERT INTO peluqueros (nombre, foto, activo) VALUES (?, '', 1)", (nombre,))
            nuevo_id = cursor.lastrowid
            servicios = cursor.execute("SELECT id_servicio FROM servicios WHERE activo = 1").fetchall()
            for s in servicios:
                cursor.execute(
                    "INSERT OR IGNORE INTO peluquero_servicios (peluquero_id, servicio_id) VALUES (?, ?)",
                    (nuevo_id, s["id_servicio"])
                )
            conexion.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conexion.close()
    return redirect(url_for("admin_agenda"))


@app.post("/admin/peluqueros/<int:peluquero_id>/editar")
@admin_requerido
def admin_editar_peluquero(peluquero_id):
    """Permite editar el nombre de un peluquero."""
    nombre = request.form.get("nombre", "").strip()
    if nombre:
        conexion = obtener_conexion()
        try:
            conexion.execute("UPDATE peluqueros SET nombre = ? WHERE id = ?", (nombre, peluquero_id))
            conexion.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conexion.close()
    return redirect(url_for("admin_agenda"))


@app.post("/admin/peluqueros/<int:peluquero_id>/toggle")
@admin_requerido
def admin_toggle_peluquero(peluquero_id):
    """Activa o desactiva un peluquero para nuevos turnos sin borrar información histórica."""
    conexion = obtener_conexion()
    peluquero = conexion.execute("SELECT activo FROM peluqueros WHERE id = ?", (peluquero_id,)).fetchone()
    if peluquero:
        nuevo_activo = 0 if peluquero["activo"] == 1 else 1
        conexion.execute("UPDATE peluqueros SET activo = ? WHERE id = ?", (nuevo_activo, peluquero_id))
        conexion.commit()
    conexion.close()
    return redirect(url_for("admin_agenda"))


@app.post("/admin/barberia/toggle")
@admin_requerido
def admin_toggle_barberia():
    """Permite pausar o reanudar la recepción de turnos en toda la barbería."""
    estado_actual = obtener_estado_barberia()
    cambiar_estado_barberia(not estado_actual)
    return redirect(url_for("admin_agenda"))


@app.post("/admin/servicios/agregar")
@admin_requerido
def admin_agregar_servicio():
    """Agrega un nuevo servicio y lo asocia a los peluqueros seleccionados."""
    nombre = request.form.get("nombre", "").strip()
    precio_str = request.form.get("precio", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    duracion_str = request.form.get("duracion", "30").strip()
    peluqueros_ids = request.form.getlist("peluqueros_ids")

    # Validación: debe haber al menos un peluquero seleccionado
    if not peluqueros_ids:
        return redirect(url_for("admin_agenda"))

    if nombre and precio_str.isdigit():
        precio = int(precio_str)
        duracion = int(duracion_str) if duracion_str.isdigit() else 30
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        try:
            cursor.execute(
                "INSERT INTO servicios (nombre, precio, descripcion, duracion, activo) VALUES (?, ?, ?, ?, 1)",
                (nombre, precio, descripcion, duracion)
            )
            nuevo_servicio_id = cursor.lastrowid
            for p_id in peluqueros_ids:
                if str(p_id).isdigit():
                    cursor.execute(
                        "INSERT OR IGNORE INTO peluquero_servicios (peluquero_id, servicio_id) VALUES (?, ?)",
                        (int(p_id), nuevo_servicio_id)
                    )
            conexion.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conexion.close()

    return redirect(url_for("admin_agenda"))


@app.post("/admin/servicios/<int:servicio_id>/editar")
@admin_requerido
def admin_editar_servicio(servicio_id):
    """Permite editar nombre, precio, descripción, duración y peluqueros asociados de un servicio."""
    nombre = request.form.get("nombre", "").strip()
    precio_str = request.form.get("precio", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    duracion_str = request.form.get("duracion", "30").strip()
    peluqueros_ids = request.form.getlist("peluqueros_ids")

    # Validación: debe haber al menos un peluquero seleccionado
    if not peluqueros_ids:
        return redirect(url_for("admin_agenda"))

    if nombre and precio_str.isdigit():
        precio = int(precio_str)
        duracion = int(duracion_str) if duracion_str.isdigit() else 30
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        try:
            cursor.execute("""
                UPDATE servicios
                SET nombre = ?, precio = ?, descripcion = ?, duracion = ?
                WHERE id_servicio = ?
            """, (nombre, precio, descripcion, duracion, servicio_id))

            # Sincronizar asociaciones en peluquero_servicios
            cursor.execute("DELETE FROM peluquero_servicios WHERE servicio_id = ?", (servicio_id,))
            for p_id in peluqueros_ids:
                if str(p_id).isdigit():
                    cursor.execute(
                        "INSERT OR IGNORE INTO peluquero_servicios (peluquero_id, servicio_id) VALUES (?, ?)",
                        (int(p_id), servicio_id)
                    )
            conexion.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conexion.close()

    return redirect(url_for("admin_agenda"))


@app.post("/admin/servicios/<int:servicio_id>/toggle")
@admin_requerido
def admin_toggle_servicio(servicio_id):
    """Activa o desactiva un servicio para los clientes (sin eliminarlo de la BD)."""
    conexion = obtener_conexion()
    servicio = conexion.execute("SELECT activo FROM servicios WHERE id_servicio = ?", (servicio_id,)).fetchone()
    if servicio:
        nuevo_estado = 0 if servicio["activo"] == 1 else 1
        conexion.execute("UPDATE servicios SET activo = ? WHERE id_servicio = ?", (nuevo_estado, servicio_id))
        conexion.commit()
    conexion.close()
    return redirect(url_for("admin_agenda"))


@app.post("/admin/servicios/<int:servicio_id>/eliminar")
@admin_requerido
def admin_eliminar_servicio(servicio_id):
    """Elimina definitivamente un servicio y su vinculación con los peluqueros."""
    conexion = obtener_conexion()
    conexion.execute("DELETE FROM peluquero_servicios WHERE servicio_id = ?", (servicio_id,))
    conexion.execute("DELETE FROM servicios WHERE id_servicio = ?", (servicio_id,))
    conexion.commit()
    conexion.close()
    return redirect(url_for("admin_agenda"))


crear_base_de_datos()


if __name__ == "__main__":
    app.run(debug=True)
