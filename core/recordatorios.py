"""Recordatorios de Litch — «recuérdame X en N minutos» / «remind me…»."""
import threading

SEGUNDOS = {
    "segundo": 1, "minuto": 60, "hora": 3600,
    "second": 1, "minute": 60, "hour": 3600,
}


class Recordatorios:
    def __init__(self, app):
        self.app = app
        self.activos = []

    def crear(self, descripcion, cantidad, unidad, idioma="es"):
        unidad_base = unidad.lower().rstrip("s")
        segundos = int(cantidad) * SEGUNDOS.get(unidad_base, 60)

        def avisar():
            if idioma == "en":
                self.app.decir(f"Reminder, sir: {descripcion}.", "en")
            else:
                self.app.decir(f"Recordatorio, señor: {descripcion}.", "es")

        temporizador = threading.Timer(segundos, avisar)
        temporizador.daemon = True
        temporizador.start()
        self.activos.append({"texto": descripcion, "segundos": segundos})
        if idioma == "en":
            return (f"Understood, sir. I'll remind you in {cantidad} "
                    f"{unidad_base}{'s' if int(cantidad) != 1 else ''}: {descripcion}.")
        plural = "s" if int(cantidad) != 1 else ""
        return (f"Entendido, señor. Le recordaré en {cantidad} "
                f"{unidad_base}{plural}: {descripcion}.")
