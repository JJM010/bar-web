from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import requests
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = "bar_villarejosS"

DB_PATH = "reservas.db"
CAPACIDAD_MAXIMA = 80

# 🔔 TELEGRAM
TELEGRAM_TOKEN = "8692038176:AAHSftSOrz99c0ztBXhySG15LwO0sj1fu_k"
CHAT_ID = "7358799251"

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": mensaje
    })

# 📧 EMAIL
EMAIL_USER = "barrestaurantevillarejos@gmail.com"
EMAIL_PASS = "oljn ijpj umie ljke"

def enviar_email(destino, asunto, mensaje):

    url = "https://api.emailjs.com/api/v1.0/email/send"

    data = {
        "service_id": "gmail_bar_villarejos",
        "template_id": "template_8hpgg3v",
        "user_id": "Hom3i2y1a7x0RFq81",
        "template_params": {
            "to_email": destino,
            "subject": asunto,
            "message": mensaje
        }
    }

    try:
        response = requests.post(url, json=data)
        print("EMAILJS:", response.status_code, response.text)

    except Exception as e:
        print("Error enviando email:", e)


# =========================
# 🗄️ BASE DE DATOS
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            telefono TEXT,
            email TEXT,
            fecha TEXT,
            personas INTEGER,
            estado TEXT DEFAULT 'pendiente'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dias_cerrados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT
        )
    """)

    conn.commit()
    conn.close()

@app.route("/") 
def inicio(): 
    return render_template("index.html")


# =========================
# 🍽️ CARTA
# =========================
@app.route("/carta")
def carta():
    return render_template("carta.html")


# =========================
# 📅 RESERVAS
# =========================
@app.route("/reservas", methods=["GET", "POST"])
def reservas():

    if request.method == "POST":

        nombre = request.form.get("nombre")
        telefono = request.form.get("telefono")
        email = request.form.get("email")
        fecha = request.form.get("fecha")
        personas = int(request.form.get("personas"))

        fecha_solo = fecha.split("T")[0]

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM dias_cerrados WHERE fecha=?", (fecha_solo,))
        if cursor.fetchone():
            conn.close()
            flash("❌ Ese día el bar está cerrado")
            return redirect(url_for("reservas"))

        cursor.execute("""
            SELECT * FROM reservas
            WHERE telefono=? AND fecha=?
        """, (telefono, fecha))

        duplicado = cursor.fetchone()

        if duplicado and not request.form.get("confirmar"):
            conn.close()
            return render_template(
                "confirmar_reserva.html",
                nombre=nombre,
                telefono=telefono,
                fecha=fecha,
                personas=personas,
                email=email
            )

        cursor.execute(
            "SELECT SUM(personas) FROM reservas WHERE fecha LIKE ?",
            (fecha_solo + "%",)
        )
        total = cursor.fetchone()[0] or 0

        if total + personas > CAPACIDAD_MAXIMA:
            conn.close()
            flash("❌ Aforo completo para ese día")
            return redirect(url_for("reservas"))

        cursor.execute("""
            INSERT INTO reservas (nombre, telefono, email, fecha, personas, estado)
            VALUES (?, ?, ?, ?, ?, 'pendiente')
        """, (nombre, telefono, email, fecha, personas))

        conn.commit()
        conn.close()

        enviar_telegram(f"""
📢 NUEVA RESERVA
👤 {nombre}
📞 {telefono}
📅 {fecha_solo}
👥 {personas}
✉️ {email}
""")

        flash("✅ Reserva enviada correctamente")
        return redirect(url_for("reservas"))

    return render_template("reservas.html")


# =========================
# 🔐 LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        password = request.form.get("password")

        if password == "bar_villarejos":
            session["admin"] = True
            return redirect(url_for("admin"))
        else:
            flash("❌ Contraseña incorrecta")

    return render_template("login.html")


# =========================
# 📊 ADMIN
# =========================
@app.route("/admin")
def admin():

    if not session.get("admin"):
        return redirect(url_for("login"))

    fecha = request.args.get("fecha")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM reservas ORDER BY fecha DESC")
    reservas = cursor.fetchall()

    cursor.execute("SELECT * FROM dias_cerrados")
    dias_cerrados = cursor.fetchall()

    total_personas = 0

    if fecha:
        cursor.execute(
            "SELECT SUM(personas) FROM reservas WHERE fecha LIKE ?",
            (fecha + "%",)
        )
        total_personas = cursor.fetchone()[0] or 0

    conn.close()

    return render_template(
        "admin.html",
        reservas=reservas,
        dias_cerrados=dias_cerrados,
        total_personas=total_personas,
        capacidad=CAPACIDAD_MAXIMA,
        fecha=fecha
    )


# =========================
# ✔ CONFIRMAR (ADMIN)
# =========================
@app.route("/confirmar/<int:id>")
def confirmar(id):

    if not session.get("admin"):
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("UPDATE reservas SET estado='confirmada' WHERE id=?", (id,))
    conn.commit()

    cursor.execute("SELECT email, nombre, fecha FROM reservas WHERE id=?", (id,))
    reserva = cursor.fetchone()

    conn.close()

    if reserva:
        enviar_email(
            reserva[0],
            "Reserva confirmada",
            f"Hola {reserva[1]}, tu reserva del día {reserva[2]} ha sido confirmada."
        )

    enviar_telegram(f"🟢 Reserva confirmada (ID {id})")

    return redirect(url_for("admin"))


# =========================
# ❌ CANCELAR (ADMIN)
# =========================
@app.route("/cancelar/<int:id>")
def cancelar(id):

    if not session.get("admin"):
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("UPDATE reservas SET estado='cancelada' WHERE id=?", (id,))
    conn.commit()

    cursor.execute("SELECT email, nombre, fecha FROM reservas WHERE id=?", (id,))
    reserva = cursor.fetchone()

    conn.close()

    if reserva:
        enviar_email(
            reserva[0],
            "Reserva cancelada",
            f"Hola {reserva[1]}, tu reserva del día {reserva[2]} ha sido cancelada."
        )

    enviar_telegram(f"🔴 Reserva cancelada (ID {id})")

    return redirect(url_for("admin"))


# =========================
# 🗑 BORRAR
# =========================
@app.route("/borrar/<int:id>")
def borrar(id):

    if not session.get("admin"):
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM reservas WHERE id=?", (id,))
    conn.commit()
    conn.close()

    enviar_telegram(f"🗑 Reserva borrada (ID {id})")

    return redirect(url_for("admin"))


# =========================
# 📍 ESTADO CLIENTE
# =========================
@app.route("/estado", methods=["GET", "POST"])
def estado():

    reservas_cliente = []
    mensaje = None

    if request.method == "POST":
        telefono = request.form.get("telefono")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, nombre, fecha, personas, estado
            FROM reservas
            WHERE telefono=?
            ORDER BY fecha DESC
        """, (telefono,))

        reservas_cliente = cursor.fetchall()
        conn.close()

        if len(reservas_cliente) == 0:
            mensaje = "❌ Este número no tiene ninguna reserva registrada"
        else:
            mensaje = "📋 Aquí están tus reservas"

    return render_template("estado.html", reservas=reservas_cliente, mensaje=mensaje)

@app.route("/cancelar_cliente/<int:id>")
def cancelar_cliente(id):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE reservas SET estado='cancelada' WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    flash("✅ Reserva cancelada correctamente")

    return redirect(url_for("estado"))

@app.route("/cerrar_dia", methods=["POST"])
def cerrar_dia():

    if not session.get("admin"):
        return redirect(url_for("login"))

    fechas = request.form.get("fechas")

    if not fechas:
        return redirect(url_for("admin"))

    lista_fechas = fechas.split(", ")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for fecha in lista_fechas:

        cursor.execute(
            "SELECT * FROM dias_cerrados WHERE fecha=?",
            (fecha,)
        )

        if cursor.fetchone() is None:

            cursor.execute(
                "INSERT INTO dias_cerrados (fecha) VALUES (?)",
                (fecha,)
            )

    conn.commit()
    conn.close()

    enviar_telegram(
        f"🚫 Días cerrados: {', '.join(lista_fechas)}"
    )

    return redirect(url_for("admin"))

@app.route("/borrar_dia/<int:id>")
def borrar_dia(id):

    if not session.get("admin"):
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 🔥 primero obtener la fecha antes de borrar
    cursor.execute("SELECT fecha FROM dias_cerrados WHERE id=?", (id,))
    fila = cursor.fetchone()

    fecha = fila[0] if fila else "desconocida"

    cursor.execute("DELETE FROM dias_cerrados WHERE id=?", (id,))
    conn.commit()
    conn.close()

    enviar_telegram(f"🔓 Día reabierto: {fecha}")

    return redirect(url_for("admin"))

@app.route("/logout")
def logout():

    session.clear()
    return redirect(url_for("login"))

@app.route("/ubicacion")
def ubicacion():
    return render_template("ubicacion.html")

# =========================
# 🚀 ARRANQUE
# =========================
init_db()  # <- esto es CLAVE

if __name__ == "__main__":
    app.run(host="0.0.0.0")