const botonAlternar = document.getElementById("alternarContrasena");
const campoContrasena = document.getElementById("contrasena");

if (botonAlternar && campoContrasena) {
    botonAlternar.addEventListener("click", function () {
        const mostrar = campoContrasena.type === "password";
        campoContrasena.type = mostrar ? "text" : "password";
        botonAlternar.textContent = mostrar ? "Ocultar" : "Ver";
        botonAlternar.setAttribute(
            "aria-label",
            mostrar ? "Ocultar contraseña" : "Mostrar contraseña"
        );
    });
}
