"""
AutoAprendizaje — coordinador central de aprendizaje continuo de Litch.

Litch ya aprende en línea (RedMaestra.train_one, calibrador, conciencia,
MLP de lotería…), pero ese conocimiento solo se salvaba de forma dispersa.
Este módulo garantiza que TODO lo aprendido:

  · se guarda automáticamente cada AUTOGUARDADO_SEG segundos,
  · se guarda al cerrar la app (litch.cerrar_app lo invoca),
  · queda medido en MEMORIA_AP/autoaprendizaje.json (progreso por sesión),
  · nunca se pierde por un crash (máximo se pierden los últimos minutos).

También expone registrar(origen, acierto) para que cualquier módulo anote
sus aciertos/fallos y Litch pueda responder "cuánto has aprendido hoy".
"""

from __future__ import annotations

import json
import os
import threading
import time

AUTOGUARDADO_SEG = 300      # guardar todo cada 5 minutos
_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA_JSON = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "autoaprendizaje.json")


class AutoAprendizaje(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True, name="LitchAutoAprendizaje")
        self.app = app
        self._detener = threading.Event()
        self._lock = threading.Lock()
        self._inicio_sesion = time.time()
        self._stats = self._cargar()
        self._sesion = {"aciertos": 0, "fallos": 0, "eventos": 0,
                        "guardados": 0, "inicio": self._inicio_sesion}

    # ── API pública ─────────────────────────────────────────────────────────
    def registrar(self, origen: str, acierto: bool, detalle: str = "") -> None:
        """Cualquier módulo anota aquí un resultado de aprendizaje."""
        with self._lock:
            o = self._stats.setdefault("origenes", {}).setdefault(
                origen, {"aciertos": 0, "fallos": 0})
            if acierto:
                o["aciertos"] += 1
                self._sesion["aciertos"] += 1
            else:
                o["fallos"] += 1
                self._sesion["fallos"] += 1
            self._sesion["eventos"] += 1

    def resumen(self, idioma: str = "es") -> str:
        s = self._sesion
        tot = s["aciertos"] + s["fallos"]
        wr = (100.0 * s["aciertos"] / tot) if tot else 0.0
        mins = int((time.time() - s["inicio"]) / 60)
        try:
            n_updates = int(getattr(self.app.red, "n_updates", 0))
        except Exception:
            n_updates = 0
        if idioma == "en":
            return (f"This session: {tot} learning events, {wr:.0f}% accuracy, "
                    f"{s['guardados']} auto-saves in {mins} min. "
                    f"Master network updates: {n_updates}.")
        return (f"Esta sesión: {tot} eventos de aprendizaje, {wr:.0f}% de acierto, "
                f"{s['guardados']} autoguardados en {mins} min. "
                f"Updates de la red maestra: {n_updates}.")

    def guardar_todo(self) -> list:
        """Persiste TODO el conocimiento aprendido. Nunca lanza excepción."""
        a = self.app
        guardados = []

        def _try(nombre, fn):
            try:
                fn()
                guardados.append(nombre)
            except Exception:
                pass

        # Memoria principal (patrones, velas, config)
        _try("memoria", lambda: __import__(
            "core.memoria", fromlist=["guardar"]).guardar(a.mem))

        # Red maestra (CNN+LSTM+MLP)
        red = getattr(a, "red", None)
        if red is not None:
            if hasattr(red, "_guardar_todo"):
                _try("red_maestra", red._guardar_todo)
            if hasattr(red, "_guardar_stats"):
                _try("red_stats", red._guardar_stats)

        # MLP de lotería
        lot = getattr(a, "loteria_av", None)
        if lot is not None and hasattr(lot, "_guardar"):
            _try("loteria", lot._guardar)

        # Base de fallos + RL + performance del agente de trading
        ag = getattr(a, "agente", None)
        if ag is not None:
            fdb = getattr(ag, "fdb", None)
            if fdb is not None and hasattr(fdb, "_guardar"):
                _try("fallo_db", fdb._guardar)
            for atr in ("rl", "rl_agente", "perf", "performance", "tracker"):
                o = getattr(ag, atr, None)
                if o is not None and hasattr(o, "_guardar"):
                    _try(atr, o._guardar)

        # Snapshot de progreso
        self._sesion["guardados"] += 1
        self._persistir_stats()
        guardados.append("progreso")
        return guardados

    def parar(self) -> None:
        self._detener.set()

    # ── Loop ────────────────────────────────────────────────────────────────
    def run(self) -> None:
        # Espera inicial: dejar que todo arranque tranquilo
        self._detener.wait(60)

        # ── Pre-entrenamiento histórico automático (1 vez por sesión) ────
        # Litch se entrena solo con velas reales del mercado (yfinance).
        # Desactivable con config «entrenamiento_auto»: false.
        try:
            if self.app.mem["config"].get("entrenamiento_auto", True):
                from . import entrenador_historico as _eh
                if _eh.disponible() and not _eh.en_curso():
                    self.app.log("[AutoAprendizaje] Pre-entrenamiento "
                                 "histórico automático iniciado (fondo).")
                    _eh.entrenar_en_fondo(self.app)
        except Exception:
            pass
        while not self._detener.is_set():
            try:
                g = self.guardar_todo()
                # Log silencioso (sin voz): el usuario ve que aprende y guarda
                self.app.log(f"[AutoAprendizaje] ✓ Conocimiento guardado "
                             f"({len(g)} módulos).")
            except Exception:
                pass
            self._detener.wait(AUTOGUARDADO_SEG)

    # ── Persistencia propia ──────────────────────────────────────────────────
    def _cargar(self) -> dict:
        try:
            with open(_RUTA_JSON, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"origenes": {}, "sesiones": 0}

    def _persistir_stats(self) -> None:
        try:
            with self._lock:
                d = dict(self._stats)
                d["ultima_sesion"] = {
                    **self._sesion,
                    "ts": time.time(),
                }
            os.makedirs(os.path.dirname(_RUTA_JSON), exist_ok=True)
            tmp = _RUTA_JSON + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            os.replace(tmp, _RUTA_JSON)
        except Exception:
            pass


def iniciar(app) -> AutoAprendizaje:
    aa = AutoAprendizaje(app)
    aa._stats["sesiones"] = int(aa._stats.get("sesiones", 0)) + 1
    aa.start()
    return aa
