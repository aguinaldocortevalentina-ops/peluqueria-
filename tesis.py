from flask import Flask, render_template


app = Flask(__name__)


servicios = [
    {"nombre": "Corte", "precio": 12000},
    {"nombre": "Corte clásico", "precio": 10000},
    {"nombre": "Corte + ceja", "precio": 13000},
    {"nombre": "Tintura", "precio": 15000}
]


@app.route("/")
def inicio():
    """Muestra la página principal de Flama Barber."""
    return render_template("index.html", servicios=servicios)


if __name__ == "__main__":
    app.run(debug=True)
