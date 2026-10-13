"""
chart_controls.py — Control inteligente del gráfico de IQ Option.

Gestiona los 3 botones de control visual del gráfico:
  [-]  zoom out — muestra más velas (vista panorámica)
  [⊙]  center / fit — centra y ajusta el gráfico automáticamente
  [+]  zoom in  — muestra menos velas (vista detallada)

Funciones principales:
  • centrar()          → clic en [⊙] para re-centrar el gráfico
  • zoom_in()          → clic en [+]
  • zoom_out()         → clic en [-]
  • zoom_optimo()      → ajusta el zoom según período de vela configurado
  • GestorGrafico      → hilo daemon que centra periódicamente y ajusta zoom

El gestor actúa en tres situaciones:
  1. Periódicamente cada CENTRAR_CADA segundos (mantiene vista limpia)
  2. Tras flash crash detectado (recentra inmediatamente)
  3. Antes de captura para Fable 5 (garantiza análisis sobre vista centrada)
"""

from __future__ import annotations

import threading
import time
from typing import Optional

try:
    import pyautogui as _pg
    _PG_OK = True
except ImportError:
    _PG_OK = False

# ── Parámetros ────────────────────────────────────────────────────────────────

CENTRAR_CADA   = 180    # segundos entre centrados automáticos (3 min)
ZOOM_OPTIMO_N  = 2      # clics de zoom-out desde default para vista de contexto
_CLICK_PAUSE   = 0.08   # pausa pyautogui entre acciones
_BOTON_W       = 45     # ancho estimado de cada botón
_BOTON_GAP     = 8      # separación entre botones
_OFFSET_TOTAL  = _BOTON_W + _BOTON_GAP   # 53 px entre centros de botones

# Fracción vertical dentro de la región del gráfico donde aparecen los botones
# En IQ Option los botones flotan a ~72% del alto del área del gráfico
_FRAC_Y_BOTONES = 0.72


# ── Estimación de posiciones ──────────────────────────────────────────────────

# Antirruido: cuándo se avisó por última vez de cada zona bloqueada,
# y cuántas veces se ha intentado. Sin esto el registro se vuelve
# ilegible y el señor no ve los mensajes que sí importan.
_AVISOS_BLOQUEO: dict = {}
_CUENTA_BLOQUEO: dict = {}


def estimar_posiciones(region: list) -> dict:
    """
    Estima las coordenadas de los 3 botones de chart control a partir de
    la región del gráfico [gx1, gy1, gx2, gy2].

    Devuelve dict con claves: 'minus', 'center', 'plus' → (x, y).
    """
    gx1, gy1, gx2, gy2 = int(region[0]), int(region[1]), int(region[2]), int(region[3])
    cx   = (gx1 + gx2) // 2
    cy   = int(gy1 + (gy2 - gy1) * _FRAC_Y_BOTONES)
    return {
        "minus":  (cx - _OFFSET_TOTAL, cy),
        "center": (cx,                 cy),
        "plus":   (cx + _OFFSET_TOTAL, cy),
    }


# ── Acciones individuales ─────────────────────────────────────────────────────

def _seguro(pos) -> bool:
    """¿Es seguro pulsar ahí?

    Estos botones son los del gráfico de IQ Option, con coordenadas
    absolutas de pantalla. Si Trader Workstation ocupa ahora esa zona,
    el clic caería dentro del broker de acciones — sobre lo que hubiera.
    Se reutiliza el mismo guardián que protege los clics de operación:
    una sola puerta vigilada vale más que tres a medias.
    """
    try:
        if pos is None:
            return False
        from . import manos as _manos
        if _manos._dentro_de_tws(pos[0], pos[1]):
            # El aviso se da UNA vez cada cinco minutos por coordenada.
            #
            # Antes se imprimía en cada intento, y en una sesión de once
            # horas eso llenó el registro con cientos de líneas idénticas
            # — «⛔ Botón bloqueado en (948,715)» una y otra vez. Un aviso
            # repetido mil veces deja de ser un aviso: se vuelve ruido que
            # esconde lo que sí importa.
            import time as _t
            k = (pos[0] // 10, pos[1] // 10)
            ahora = _t.time()
            if (ahora - _AVISOS_BLOQUEO.get(k, 0.0)) > 300:
                _AVISOS_BLOQUEO[k] = ahora
                n = _CUENTA_BLOQUEO.get(k, 0)
                extra = f" (van {n} intentos)" if n > 3 else ""
                print(f"[Gráfico] ⛔ Botón bloqueado en ({pos[0]},{pos[1]}): "
                      f"cae dentro de Interactive Brokers{extra}. "
                      f"Estos controles son del gráfico de IQ Option y aquí "
                      f"no sirven.")
            _CUENTA_BLOQUEO[k] = _CUENTA_BLOQUEO.get(k, 0) + 1
            return False
    except Exception:
        pass      # si el guardián falla, no bloqueo el uso normal
    return True


def centrar(region: list | None = None, cfg: dict | None = None) -> bool:
    """Hace clic en el botón [⊙] para centrar y ajustar el gráfico."""
    if not _PG_OK:
        return False
    try:
        pos = _posicion_boton("center", region, cfg)
        if pos is None or not _seguro(pos):
            return False
        _pg.click(pos[0], pos[1], _pause=_CLICK_PAUSE)
        return True
    except Exception:
        return False


def zoom_in(region: list | None = None, cfg: dict | None = None) -> bool:
    """Hace clic en el botón [+]."""
    if not _PG_OK:
        return False
    try:
        pos = _posicion_boton("plus", region, cfg)
        if pos is None or not _seguro(pos):
            return False
        _pg.click(pos[0], pos[1], _pause=_CLICK_PAUSE)
        return True
    except Exception:
        return False


def zoom_out(region: list | None = None, cfg: dict | None = None) -> bool:
    """Hace clic en el botón [-]."""
    if not _PG_OK:
        return False
    try:
        pos = _posicion_boton("minus", region, cfg)
        if pos is None or not _seguro(pos):
            return False
        _pg.click(pos[0], pos[1], _pause=_CLICK_PAUSE)
        return True
    except Exception:
        return False


def zoom_optimo(region: list | None = None, cfg: dict | None = None,
                periodo_seg: int = 60) -> bool:
    """
    Ajusta el zoom al nivel óptimo para el período configurado:
      - 1 min (60s)  → 2 clics zoom-out desde default (ve ~40 velas)
      - 5 min (300s) → 1 clic zoom-out (menos velas, más contexto visual)
      - ≤30s blitz   → 3 clics zoom-out (muestra más velas de contexto)
    Primero centra, luego ajusta zoom.
    """
    if not _PG_OK:
        return False
    ok = centrar(region, cfg)
    time.sleep(0.20)
    n = 2
    if periodo_seg <= 30:
        n = 3
    elif periodo_seg >= 300:
        n = 1
    for _ in range(n):
        zoom_out(region, cfg)
        time.sleep(0.12)
    return ok


# ── Internos ──────────────────────────────────────────────────────────────────

def _posicion_boton(boton: str, region: list | None,
                    cfg: dict | None) -> Optional[tuple]:
    """Devuelve (x, y) del botón solicitado, priorizando config guardada."""
    # 1. Posición explícita en config
    clave_cfg = f"boton_chart_{boton}"
    if cfg and clave_cfg in cfg:
        pos = cfg[clave_cfg]
        if pos and len(pos) >= 2:
            return (int(pos[0]), int(pos[1]))
    # 2. Estimación desde región del gráfico
    rg = region or (cfg.get("region_grafico") if cfg else None)
    if rg and len(rg) >= 4:
        return estimar_posiciones(rg)[boton]
    return None


# ── Gestor de gráfico (hilo daemon) ──────────────────────────────────────────

class GestorGrafico(threading.Thread):
    """
    Hilo daemon que mantiene el gráfico de IQ Option bien posicionado:

    • Centra el gráfico cada CENTRAR_CADA segundos.
    • Hace zoom óptimo al arrancar (configura la vista ideal).
    • Recentra inmediatamente cuando se le notifica un flash crash.
    • Recentra antes de captura para Fable 5 cuando se le solicita.
    """

    def __init__(self, app):
        super().__init__(daemon=True, name="GestorGrafico")
        self.app         = app
        self._detener    = threading.Event()
        self._forzar_ahora = threading.Event()  # señal para centrado urgente
        self._ultimo_centrado  = 0.0
        self._ultimo_zoom      = 0.0
        self._zoom_inicial_ok  = False

    def parar(self) -> None:
        self._detener.set()

    def forzar_centrado(self) -> None:
        """Notifica al gestor que debe centrar el gráfico en la próxima oportunidad."""
        self._forzar_ahora.set()

    def centrar_para_fable(self) -> None:
        """Bloquea hasta que el gráfico está centrado (para screenshot de Fable 5)."""
        cfg    = self.app.mem.get("config", {})
        region = cfg.get("region_grafico")
        centrar(region, cfg)
        time.sleep(0.35)   # pequeña pausa para que el gráfico redibuje

    # ── Loop principal ───────────────────────────────────────────────────────

    def run(self) -> None:
        time.sleep(8)   # deja arrancar todo lo demás primero

        while not self._detener.is_set():
            try:
                self._ciclo()
            except Exception as _e:
                pass
            self._detener.wait(timeout=5)

    def _ciclo(self) -> None:
        cfg    = self.app.mem.get("config", {})
        region = cfg.get("region_grafico")

        if not region or not _PG_OK:
            return

        # ══ CONTROL DE MOUSE SOLO CON PERMISO ═══════════════════════════
        # El gestor hace CLICKS reales (zoom/centrado). Solo puede tocar el
        # mouse si el usuario activó el modo autónomo (botón AUTO) o el
        # modo práctica. Nunca al arrancar la app.
        _practica = getattr(self.app, "modo_practica", None)
        _practica_on = bool(_practica and getattr(_practica, "activo", False))
        if not (getattr(self.app, "autoclick_on", False)
                or getattr(self.app, "modo_autonomo", False)
                or _practica_on):
            return

        ahora  = time.time()
        periodo = int(cfg.get("periodo_vela", 60))

        # Zoom inicial al arrancar con gráfico calibrado
        if not self._zoom_inicial_ok and ahora - self._ultimo_zoom > 2:
            self._ultimo_zoom   = ahora
            self._zoom_inicial_ok = True
            zoom_optimo(region, cfg, periodo)
            self.app.log("[Chart] Zoom óptimo inicial aplicado.")
            return

        # Centrado urgente solicitado (flash crash, señal externa)
        if self._forzar_ahora.is_set():
            self._forzar_ahora.clear()
            centrar(region, cfg)
            self._ultimo_centrado = ahora
            self.app.log("[Chart] Gráfico re-centrado (solicitud urgente).")
            return

        # Centrado periódico cada CENTRAR_CADA segundos
        if ahora - self._ultimo_centrado >= CENTRAR_CADA:
            self._ultimo_centrado = ahora
            centrar(region, cfg)
            # Solo loguear si el trading está activo (evitar spam cuando ocioso)
            if getattr(self.app, "trading_on", False):
                self.app.log("[Chart] Gráfico centrado automáticamente.")


# ── Singleton ─────────────────────────────────────────────────────────────────

_instancia: GestorGrafico | None = None


def iniciar(app) -> GestorGrafico:
    """Crea e inicia el GestorGrafico singleton."""
    global _instancia
    if _instancia is None or not _instancia.is_alive():
        _instancia = GestorGrafico(app)
        _instancia.start()
        app.log("[Chart] Gestor de gráfico iniciado.")
    return _instancia


def obtener() -> GestorGrafico | None:
    return _instancia
