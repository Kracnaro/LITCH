"""
aprendiz_tws.py — Litch aprende a usar IBKR MIRÁNDOTE operar.

La idea: un aprendiz de verdad no aprende leyendo un manual, aprende
mirando al maestro y anotando lo que ve. Este módulo pone a Litch a
observar TWS en tiempo real mientras TÚ operas, y a memorizar:

  · Qué activo estás mirando y cuándo lo cambias.
  · Cuándo aparece una orden y de qué tipo.
  · Qué hora del día operas y en qué condiciones de mercado.
  · Cómo se ve la pantalla antes de una operación tuya (el "setup" que
    tú reconoces y él todavía no).

CADA OBSERVACIÓN ES UNA LECCIÓN. Litch las guarda en
MEMORIA_AP/lecciones_tws.json y las usa para entender el flujo real de
trabajo en Wall Street — no la teoría, sino lo que de verdad haces.

SEGURIDAD: este módulo solo MIRA. Nunca toca el mouse ni el teclado sobre
TWS. Es un observador silencioso.
"""

from __future__ import annotations

import json
import os
import threading
import time

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA_JSON = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "lecciones_tws.json")

INTERVALO_OBS = 4      # segundos entre observaciones
MAX_LECCIONES = 1000


class AprendizTWS(threading.Thread):
    """Observa TWS y aprende de lo que ve."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchAprendizTWS")
        self.app = app
        self._detener = threading.Event()
        self._activo = False
        self._lecciones: list[dict] = []
        self._estado_previo: dict = {}
        self._cargar()

    # ── Control ─────────────────────────────────────────────────────────────

    def activar(self) -> str:
        if self._activo:
            return "Ya estoy observando TWS, señor."
        self._activo = True
        if not self.is_alive():
            self.start()
        self.app.log("[AprendizTWS] Observación activada — aprendo mirándole "
                     "operar.")
        return ("Modo aprendiz activado, señor. Voy a observar Trader "
                "Workstation mientras usted opera y anotaré todo lo que vea: "
                "qué activos mira, cuándo entra, a qué hora, en qué "
                "condiciones. Cada cosa que haga es una lección para mí. "
                "Solo miro — no tocaré nada.")

    def desactivar(self) -> str:
        self._activo = False
        self._guardar()
        return (f"Observación detenida, señor. Llevo {len(self._lecciones)} "
                f"lecciones anotadas de verle operar.")

    def parar(self):
        self._detener.set()

    # ── Bucle de observación ────────────────────────────────────────────────

    def run(self):
        self._detener.wait(10)
        while not self._detener.is_set():
            if self._activo:
                try:
                    self._observar()
                except Exception:
                    pass
            self._detener.wait(INTERVALO_OBS)

    def _observar(self):
        """Toma una foto del estado de TWS y anota los cambios."""
        from . import vision_tws as _vt

        est = _vt.leer_estado_tws(self.app)
        if not est.get("tws_abierta"):
            return

        actual = {
            "cuenta":     est.get("cuenta", ""),
            "es_paper":   est.get("es_paper"),
            "al_frente":  est.get("al_frente"),
            "titulo":     est.get("titulo", "")[:80],
        }

        # Leer también el color de la última vela si la visión está lista
        try:
            an = _vt.analizar_grafico_tws(self.app)
            if an.get("ok"):
                actual["vela"] = an.get("color_ultima")
        except Exception:
            pass

        prev = self._estado_previo
        cambios = []

        # ¿Cambió de activo? (el título de TWS suele traer el símbolo)
        if prev.get("titulo") and prev["titulo"] != actual["titulo"]:
            cambios.append(f"cambió la vista: «{actual['titulo'][:40]}»")

        # ¿Pasó de simulada a real o viceversa? (crítico)
        if (prev.get("es_paper") is not None
                and prev["es_paper"] != actual.get("es_paper")):
            tipo = "REAL" if actual.get("es_paper") is False else "PAPER"
            cambios.append(f"⚠ cambió a cuenta {tipo}")

        # ¿El usuario volvió a poner TWS al frente? (señal de que va a operar)
        if not prev.get("al_frente") and actual.get("al_frente"):
            cambios.append("puso TWS al frente (posible intención de operar)")

        if cambios:
            self._anotar(cambios, actual)

        self._estado_previo = actual

    def _anotar(self, cambios: list, contexto: dict):
        """Guarda una lección de lo observado."""
        t = time.localtime()
        leccion = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "hora": t.tm_hour,
            "dia_semana": t.tm_wday,
            "cambios": cambios,
            "contexto": contexto,
        }
        self._lecciones.append(leccion)
        if len(self._lecciones) > MAX_LECCIONES:
            del self._lecciones[:-MAX_LECCIONES]
        self.app.log("[AprendizTWS] Aprendido: " + "; ".join(cambios))
        self._guardar()

    # ── Lo que aprendió ─────────────────────────────────────────────────────

    def resumen(self) -> str:
        if not self._lecciones:
            return ("Aún no he observado nada en TWS, señor. Active el modo "
                    "aprendiz con 'observa TWS' y opere normalmente: "
                    "aprenderé mirándole.")
        n = len(self._lecciones)
        # ¿A qué horas suele operar el usuario?
        horas = {}
        for l in self._lecciones:
            h = l.get("hora")
            if h is not None:
                horas[h] = horas.get(h, 0) + 1
        top_horas = sorted(horas.items(), key=lambda kv: -kv[1])[:3]
        partes = [f"He anotado {n} observaciones de verle operar en TWS."]
        if top_horas:
            partes.append("Sus horas más activas: " + ", ".join(
                f"{h:02d}:00 ({c} veces)" for h, c in top_horas) + ".")
        ultimas = self._lecciones[-3:]
        if ultimas:
            partes.append("Últimas lecciones: " + " | ".join(
                "; ".join(l["cambios"]) for l in ultimas))
        partes.append("Cada vez que usted opera aprendo el flujo real de "
                      "trabajo, no la teoría.")
        return " ".join(partes)

    # ── Persistencia ────────────────────────────────────────────────────────

    def _cargar(self):
        try:
            with open(_RUTA_JSON, encoding="utf-8") as f:
                self._lecciones = json.load(f).get("lecciones", [])
        except Exception:
            self._lecciones = []

    def _guardar(self):
        try:
            os.makedirs(os.path.dirname(_RUTA_JSON), exist_ok=True)
            tmp = _RUTA_JSON + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"lecciones": self._lecciones,
                           "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False)
            os.replace(tmp, _RUTA_JSON)
        except Exception:
            pass


# ── Singleton ───────────────────────────────────────────────────────────────

_instancia: AprendizTWS | None = None


def obtener(app) -> AprendizTWS:
    global _instancia
    if _instancia is None:
        _instancia = AprendizTWS(app)
    return _instancia
