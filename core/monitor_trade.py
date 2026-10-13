"""
Monitor de trade activo — Litch cuida la posición abierta en tiempo real.

Cada ~0.8 s que hay un trade abierto este módulo:
  1. Lee el color del área P&L (verde = ganando, rojo = perdiendo)
  2. Rastrea ticks consecutivos en rojo
  3. Cuando se supera el umbral de tiempo Y de ticks en rojo decide:
       a. VENTA ANTICIPADA  (boton_vender)  → recupera capital parcial, sin diálogo
       b. ROLLOVER / PRÓRROGA (boton_rollover + boton_confirmar_rollover)
          → extiende el trade y dobla el monto (usar solo si se prevé recuperación)

Calibrar en Calibrar → Rollover/Venta:
  region_pl              → rectángulo [x1,y1,x2,y2] del área P&L en pantalla
  boton_vender           → "Vender todas" (venta anticipada, sin confirmación)
  boton_rollover         → botón Rollover/Prórroga (abre diálogo de confirmación)
  boton_confirmar_rollover → botón naranja "CONFIRMAR PRÓRROGA" dentro del diálogo
"""

import threading
import time

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

try:
    import mss as _mss_mod
    _MSS = True
except ImportError:
    _MSS = False

# Umbrales de decisión
_UMBRAL_VENTA    = 0.50   # fracción del tiempo a partir de la cual puede vender
_UMBRAL_ROLLOVER = 0.72   # fracción para rollover (necesita más certeza de pérdida)
_TICKS_VENTA     = 3      # ticks consecutivos en rojo para activar venta anticipada
_TICKS_ROLLOVER  = 5      # ticks para rollover (exige más evidencia)
_PAUSA_DIALOGO   = 0.45   # segundos de espera para que aparezca el diálogo de Rollover


class MonitorTrade(threading.Thread):
    """
    Hilo daemon que vigila el P&L durante cada trade activo.

    Prioridades de salida (de menor a mayor riesgo):
      1. boton_vender           — sell anticipado, sin confirmación, preferido
      2. boton_rollover + boton_confirmar_rollover — extensión con doble monto
    """

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchMonitor")
        self.app           = app
        self._lock         = threading.Lock()
        self._trade        = None
        self._ticks_rojos  = 0
        self._ticks_verdes = 0

    # ── API pública ───────────────────────────────────────────────────────────

    def abrir_trade(self, direccion: str, duracion: int):
        """Registrar apertura de trade. Llamar justo después del click."""
        with self._lock:
            self._trade = {
                "dir":              direccion,
                "inicio":           time.time(),
                "duracion":         max(duracion, 10),
                "salida_intentada": False,
                "ticks_verde":      0,
                "ticks_rojo":       0,
            }
            self._ticks_rojos  = 0
            self._ticks_verdes = 0

    def cerrar_trade(self):
        """Registrar cierre de trade (vela cerrada, resultado conocido)."""
        with self._lock:
            self._trade        = None
            self._ticks_rojos  = 0
            self._ticks_verdes = 0

    def trade_activo(self) -> bool:
        with self._lock:
            return self._trade is not None

    # ── Bucle interno ─────────────────────────────────────────────────────────

    def run(self):
        while True:
            time.sleep(0.8)
            with self._lock:
                t = dict(self._trade) if self._trade else None
            if t is None or t.get("salida_intentada"):
                continue
            try:
                self._verificar(t)
            except Exception:
                pass   # nunca crashear el monitor

    def _verificar(self, t: dict):
        transcurrido = time.time() - t["inicio"]
        fraccion     = transcurrido / t["duracion"]

        pl = self._leer_pl()

        with self._lock:
            if self._trade is None:
                return
            if pl == "GANANDO":
                self._ticks_verdes += 1
                self._ticks_rojos   = 0
                self._trade["ticks_verde"] = self._ticks_verdes
            elif pl == "PERDIENDO":
                self._ticks_rojos  += 1
                self._ticks_verdes  = 0
                self._trade["ticks_rojo"] = self._ticks_rojos
            rojos = self._ticks_rojos

        # Activar salida si se cumplen ambas condiciones
        if fraccion >= _UMBRAL_VENTA and rojos >= _TICKS_VENTA:
            self._decidir_salida(t, fraccion, rojos)

    # ── Decisión inteligente de salida ────────────────────────────────────────

    def _decidir_salida(self, t: dict, fraccion: float, rojos: int):
        """Elige la salida menos costosa disponible según calibración."""
        cfg = self.app.mem["config"]
        pct = int(fraccion * 100)

        tiene_vender   = bool(cfg.get("boton_vender"))
        tiene_rollover = (bool(cfg.get("boton_rollover"))
                          and fraccion >= _UMBRAL_ROLLOVER
                          and rojos >= _TICKS_ROLLOVER)

        if tiene_vender:
            # Opción 1 (mejor): venta anticipada sin confirmación
            self._ejecutar_venta(t, pct, rojos)
        elif tiene_rollover:
            # Opción 2: Rollover — extiende el trade y dobla el monto
            self._ejecutar_rollover(t, pct, rojos)
        else:
            # Sin calibración — solo advertir (una sola vez por trade)
            with self._lock:
                if self._trade and not self._trade.get("salida_intentada"):
                    self._trade["salida_intentada"] = True
            self.app.log(
                f"[Monitor] Trade en rojo ({pct}% tiempo). "
                "Calibra 'boton_vender' para habilitar salidas automáticas.")

    # ── Opción 1: Venta anticipada ────────────────────────────────────────────

    def _ejecutar_venta(self, t: dict, pct: int, rojos: int):
        cfg    = self.app.mem["config"]
        coords = cfg.get("boton_vender")
        if not coords:
            return

        with self._lock:
            if self._trade is None or self._trade.get("salida_intentada"):
                return
            self._trade["salida_intentada"] = True

        from . import manos
        self.app.log(
            f"[Monitor] VENTA ANTICIPADA — {rojos} ticks en rojo, {pct}% del tiempo.")
        self.app.decir(self.app.txt(
            "Venta anticipada, senor. El trade lleva varios segundos en rojo — "
            "prefiero recuperar parte del capital que esperar la perdida total.",
            "Early sell, sir. The trade has been in the red — "
            "better to recover partial capital than wait for a total loss."))
        try:
            manos.click_rapido(int(coords[0]), int(coords[1]))
            manos.aparcar_cursor(cfg.get("region_grafico"))
        except Exception as e:
            self.app.log(f"[Monitor] Error al vender: {e}")

    # ── Opción 2: Rollover (extensión + confirmación de diálogo) ─────────────

    def _ejecutar_rollover(self, t: dict, pct: int, rojos: int):
        """
        Hace click en el botón Rollover y luego confirma el diálogo emergente.
        ⚠ El Rollover dobla el monto invertido — usar con precaución.
        """
        cfg    = self.app.mem["config"]
        coords = cfg.get("boton_rollover")
        if not coords:
            return

        with self._lock:
            if self._trade is None or self._trade.get("salida_intentada"):
                return
            self._trade["salida_intentada"] = True

        from . import manos
        self.app.log(
            f"[Monitor] ROLLOVER (extensión) — {rojos} ticks en rojo, {pct}% tiempo.")
        self.app.decir(self.app.txt(
            "Activando Rollover, senor. Extiendo la posicion para darle "
            "mas tiempo de recuperarse — el monto se duplicara.",
            "Activating Rollover, sir. Extending the position to allow "
            "recovery — the investment amount will double."))
        try:
            manos.click_rapido(int(coords[0]), int(coords[1]))

            # Esperar el diálogo de confirmación (CONFIRMAR PRÓRROGA)
            time.sleep(_PAUSA_DIALOGO)
            confirmar = cfg.get("boton_confirmar_rollover")
            if confirmar:
                manos.click_rapido(int(confirmar[0]), int(confirmar[1]))
                self.app.log("[Monitor] Rollover confirmado en el diálogo.")
            else:
                self.app.log(
                    "[Monitor] ⚠ boton_confirmar_rollover sin calibrar — "
                    "confirma el diálogo 'CONFIRMAR PRÓRROGA' manualmente. "
                    "Calibra en: Calibrar → Botón CONFIRMAR PRÓRROGA.")

            manos.aparcar_cursor(cfg.get("region_grafico"))
        except Exception as e:
            self.app.log(f"[Monitor] Error en rollover: {e}")

    # ── Lectura del P&L por color de pantalla ─────────────────────────────────

    def _leer_pl(self) -> str:
        """
        Analiza region_pl: verde dominante → GANANDO, rojo → PERDIENDO.
        Requiere calibrar region_pl en el menú Calibrar.
        """
        region = self.app.mem["config"].get("region_pl")
        if not region or not _NP or not _MSS:
            return "DESCONOCIDO"
        try:
            x1, y1, x2, y2 = [int(v) for v in region]
            w = max(x2 - x1, 1)
            h = max(y2 - y1, 1)
            with _mss_mod.mss() as sct:
                img = np.array(sct.grab(
                    {"left": x1, "top": y1, "width": w, "height": h}
                ))[:, :, :3]
            r_mean = float(img[:, :, 0].mean())
            g_mean = float(img[:, :, 1].mean())
            if g_mean > r_mean * 1.20 and g_mean > 80:
                return "GANANDO"
            if r_mean > g_mean * 1.20 and r_mean > 80:
                return "PERDIENDO"
            return "NEUTRAL"
        except Exception:
            return "DESCONOCIDO"

    # ── Calibración automática del área P&L ───────────────────────────────────

    def calibrar_region_pl_auto(self) -> dict | None:
        """
        Detecta automáticamente el área de P&L buscando texto verde (+) o
        rojo (-) en la zona derecha de pantalla durante un trade activo.
        Devuelve {"region_pl": [x1,y1,x2,y2]} o None.
        """
        if not _NP or not _MSS:
            return None
        try:
            import numpy as np
            from . import vision as _vis
            img = _vis.capturar_pantalla_completa()
            if img is None:
                return None

            H, W = img.shape[:2]
            zona  = img[:, W // 2:, :]
            r     = zona[:, :, 0].astype(float)
            g     = zona[:, :, 1].astype(float)

            mask_v = (g > 120) & (g > r * 1.4)
            mask_r = (r > 120) & (r > g * 1.4)
            mask   = mask_v | mask_r

            ys, xs = np.where(mask)
            if len(ys) < 50:
                return None

            y1 = max(0,     int(ys.min()) - 10)
            y2 = min(H,     int(ys.max()) + 10)
            x1 = max(W//2,  int(xs.min()) + W//2 - 10)
            x2 = min(W,     int(xs.max()) + W//2 + 10)

            if x2 - x1 < 20 or y2 - y1 < 10:
                return None

            return {"region_pl": [x1, y1, x2, y2]}
        except Exception:
            return None
