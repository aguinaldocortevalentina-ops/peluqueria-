document.addEventListener("DOMContentLoaded", function () {
    const selectorHorarios = document.querySelector("[data-disponibilidad-url]");
    const fechas = document.querySelectorAll('input[name="fecha"]');

    if (!selectorHorarios || fechas.length === 0) {
        return;
    }

    function fechaSeleccionada() {
        const seleccionada = document.querySelector('input[name="fecha"]:checked');
        return seleccionada ? seleccionada.value : "";
    }

    function mostrarDisponibilidad(ocupados) {
        selectorHorarios.querySelectorAll(".hora-opcion").forEach(function (opcion) {
            const input = opcion.querySelector('input[name="hora"]');
            const estado = opcion.querySelector(".estado-hora");
            const estaOcupado = ocupados.includes(input.value);

            input.disabled = estaOcupado;
            opcion.classList.toggle("hora-ocupada", estaOcupado);
            estado.textContent = estaOcupado ? "Reservado" : "";

            if (estaOcupado && input.checked) {
                input.checked = false;
            }
        });
    }

    async function actualizarDisponibilidad() {
        const fecha = fechaSeleccionada();
        if (!fecha) {
            return;
        }

        const url = new URL(selectorHorarios.dataset.disponibilidadUrl, window.location.origin);
        url.searchParams.set("fecha", fecha);

        try {
            const respuesta = await fetch(url);
            const datos = await respuesta.json();
            mostrarDisponibilidad(datos.ocupados || []);
        } catch (error) {
            // Si no hay conexión, Flask mantiene la validación final al confirmar.
        }
    }

    fechas.forEach(function (fecha) {
        fecha.addEventListener("change", actualizarDisponibilidad);
    });

    actualizarDisponibilidad();
});
