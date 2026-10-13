"""
Tareas Programadas — el "cron interno" de Litch, estilo Jarvis/Hermes Agent.

Permite programar acciones por voz o chat para que ocurran solas:
  «Litch, programa el modo nocturno a las 22:00»
  «Litch, programa entrenar con historial a las 6:00»
  «Litch, programa un respaldo a las 23:30»
  «Litch, ¿qué tareas tienes programadas?»
  «Litch, borra las tareas programadas»

Las tareas se guardan en la memoria (config «tareas_programadas») y
sobreviven reinicios. Cada tarea diaria se ejecuta una vez al día a su hora.

Acciones disponibles (seguras, ninguna mueve dinero por sí sola):
  modo_nocturno   → inicia el entrenamiento nocturno continuo
  entrenar        → entrenamiento histórico con velas reales (una vez)
  practica_on     → activa el modo práctica DEMO
  practica_off    → desactiva el modo práctica
  trading_on      → activa el análisis de mercado
  trading_off     → desactiva el análisis
  respaldo        → respalda la memoria a las nubes registradas
  guardar         → guarda TODO el conocimiento ahora
  reporte         → dice el resumen de rendimiento por voz
  apagar          → guarda todo y cierra Litch ordenadamente

NOTA de seguridad: el auto-click (dinero) NO es programable a propósito —
activarlo requiere siempre al usuario presente pulsando AUTO.
"""

from __future__ import annotations

import re
import threading
import time

REVISAR_CADA = 20   # segundos entre chequeos de hora


# ── Acciones disponibles ────────────────────────────────────────────────────

def _acciones(app) -> dict:
    def _nocturno():
        from . import entrenador_historico as eh
        app.log("[Tareas] ⏰ Ejecutando: modo nocturno")
        eh.iniciar_modo_nocturno(app)

    def _entrenar():
        from . import entrenador_historico as eh
        app.log("[Tareas] ⏰ Ejecutando: entrenamiento histórico")
        eh.entrenar_en_fondo(app)

    def _practica_on():
        p = getattr(app, "modo_practica", None)
        if p and not p.activo:
            app.log("[Tareas] ⏰ Ejecutando: activar práctica")
            p.activar()

    def _practica_off():
        p = getattr(app, "modo_practica", None)
        if p and p.activo:
            app.log("[Tareas] ⏰ Ejecutando: desactivar práctica")
            p.desactivar()

    def _respaldo():
        from . import respaldo as r
        app.log("[Tareas] ⏰ Ejecutando: respaldo")
        try:
            app.log(r.respaldar(app))
        except Exception as e:
            app.log(f"[Tareas] Respaldo falló: {e}")

    def _guardar():
        aa = getattr(app, "autoaprendizaje", None)
        if aa:
            app.log("[Tareas] ⏰ Ejecutando: guardado total")
            aa.guardar_todo()

    def _reporte():
        try:
            app.decir(app.resumen_trading())
        except Exception:
            pass

    def _apagar():
        app.log("[Tareas] ⏰ Ejecutando: apagado programado")
        app.cerrar_app()

    return {
        "modo_nocturno": _nocturno,
        "entrenar":      _entrenar,
        "practica_on":   _practica_on,
        "practica_off":  _practica_off,
        "trading_on":    lambda: app.set_trading(True),
        "trading_off":   lambda: app.set_trading(False),
        "respaldo":      _respaldo,
        "guardar":       _guardar,
        "reporte":       _reporte,
        "apagar":        _apagar,
    }


_NOMBRES = {
    "modo_nocturno": "modo nocturno",
    "entrenar":      "entrenamiento histórico",
    "practica_on":   "activar práctica",
    "practica_off":  "desactivar práctica",
    "trading_on":    "activar análisis",
    "trading_off":   "desactivar análisis",
    "respaldo":      "respaldo a la nube",
    "guardar":       "guardado total",
    "reporte":       "reporte de rendimiento",
    "apagar":        "apagar Litch",
}


class TareasProgramadas(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True, name="LitchTareas")
        self.app = app
        self._detener = threading.Event()

    # ── API ────────────────────────────────────────────────────────────────
    def _lista(self) -> list:
        return self.app.mem["config"].setdefault("tareas_programadas", [])

    def _guardar_mem(self):
        try:
            from . import memoria
            memoria.guardar(self.app.mem)
        except Exception:
            pass

    def agregar(self, hora: str, accion: str, diaria: bool = True) -> str:
        if accion not in _NOMBRES:
            return (f"No conozco la acción «{accion}». Puedo programar: "
                    + ", ".join(_NOMBRES.values()) + ".")
        if not re.fullmatch(r"[0-2]?\d:[0-5]\d", hora):
            return "La hora debe ser en formato HH:MM, señor."
        self._lista().append({
            "hora": hora, "accion": accion,
            "diaria": bool(diaria), "ultima": ""})
        self._guardar_mem()
        return (f"Programado, señor: {_NOMBRES[accion]} "
                f"{'todos los días' if diaria else 'una vez'} a las {hora}.")

    def listar(self) -> str:
        ts = self._lista()
        if not ts:
            return ("No tengo tareas programadas, señor. Dígame por ejemplo: "
                    "'programa el modo nocturno a las 22:00'.")
        lineas = [f"· {_NOMBRES.get(t['accion'], t['accion'])} a las "
                  f"{t['hora']}" + (" (diaria)" if t.get("diaria") else " (una vez)")
                  for t in ts]
        return "Tareas programadas:\n" + "\n".join(lineas)

    def limpiar(self) -> str:
        n = len(self._lista())
        self.app.mem["config"]["tareas_programadas"] = []
        self._guardar_mem()
        return f"Listo, señor. Eliminé {n} tarea(s) programada(s)."

    def parar(self):
        self._detener.set()

    # ── Loop ───────────────────────────────────────────────────────────────
    def run(self):
        self._detener.wait(30)   # dejar arrancar todo
        acciones = _acciones(self.app)
        while not self._detener.is_set():
            try:
                ahora_hm  = time.strftime("%H:%M")
                hoy       = time.strftime("%Y-%m-%d")
                restantes = []
                cambio = False
                for t in self._lista():
                    if t["hora"] == ahora_hm and t.get("ultima") != hoy:
                        fn = acciones.get(t["accion"])
                        if fn:
                            try:
                                fn()
                            except Exception as e:
                                self.app.log(f"[Tareas] Error en "
                                             f"{t['accion']}: {e}")
                        t["ultima"] = hoy
                        cambio = True
                        if not t.get("diaria"):
                            continue   # tarea de una vez: no se re-agrega
                    restantes.append(t)
                if cambio:
                    self.app.mem["config"]["tareas_programadas"] = restantes
                    self._guardar_mem()
            except Exception:
                pass
            self._detener.wait(REVISAR_CADA)


# ── Parseo de órdenes de voz/chat ───────────────────────────────────────────

_MAPA_FRASES = [
    (("nocturno",), "modo_nocturno"),
    (("entrena", "historial"), "entrenar"),
    (("entrenamiento",), "entrenar"),
    (("practica", "activa"), "practica_on"),
    (("práctica", "activa"), "practica_on"),
    (("practica", "desactiva"), "practica_off"),
    (("práctica", "desactiva"), "practica_off"),
    (("respaldo",), "respaldo"),
    (("guarda",), "guardar"),
    (("reporte",), "reporte"),
    (("apaga",), "apagar"),
    (("apagar",), "apagar"),
    (("analisis", "activa"), "trading_on"),
    (("análisis", "activa"), "trading_on"),
    (("analisis", "desactiva"), "trading_off"),
    (("análisis", "desactiva"), "trading_off"),
]


def interpretar_orden(texto: str) -> tuple:
    """Extrae (accion, hora, diaria) de una frase, o (None, None, None)."""
    t = texto.lower()
    m = re.search(r"(\d{1,2})[:h.](\d{2})", t)
    if not m:
        # "a las 10 de la noche" → sin minutos
        m2 = re.search(r"a las (\d{1,2})\b", t)
        if not m2:
            return None, None, None
        h = int(m2.group(1))
        if "noche" in t or "pm" in t:
            h = h + 12 if h < 12 else h
        hora = f"{h:02d}:00"
    else:
        hora = f"{int(m.group(1)):02d}:{m.group(2)}"

    accion = None
    for claves, acc in _MAPA_FRASES:
        if all(c in t for c in claves):
            accion = acc
            break
    if accion is None:
        return None, hora, None

    diaria = not ("una vez" in t or "solo hoy" in t or "sólo hoy" in t)
    return accion, hora, diaria


def iniciar(app) -> TareasProgramadas:
    tp = TareasProgramadas(app)
    tp.start()
    n = len(app.mem["config"].get("tareas_programadas", []))
    if n:
        app.log(f"[Tareas] Programador activo — {n} tarea(s) pendiente(s).")
    else:
        app.log("[Tareas] Programador activo. Di: 'programa el modo "
                "nocturno a las 22:00'.")
    return tp
