"""
Autocalibracion — Litch detecta y mantiene todos los elementos de pantalla
en tiempo real sin intervención humana.

Ciclo cada 20 s:
  1. Verifica que los botones calibrados siguen en el lugar correcto (color)
  2. Si alguno se movió → re-escanea pantalla completa
  3. Detecta automáticamente: SUBE, BAJA, gráfico, P&L, Rollover
  4. Primera detección exitosa → activa análisis; modo_autonomo → activa clicks
  5. Calibración completa forzada cada 15 minutos

Compatible con IQ Option y plataformas genéricas con botones verde/rojo.
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


_INTERVALO_VERIFICAR_TRADING  = 20   # s entre checks cuando trading activo
_INTERVALO_VERIFICAR_IDLE     = 20   # s entre checks cuando inactivo
_INTERVALO_FULL_CALIB         = 600  # s entre calibraciones completas (10 min)


class AutoCalibracion(threading.Thread):
    """
    Daemon que mantiene calibración de pantalla sincronizada.

    Se inicia automáticamente desde litch.py con:
        self.autocalib = AutoCalibracion(self)
        self.autocalib.start()
    """

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchAutoCalib")
        self.app               = app
        self._ultimo_full_calib = 0.0
        self._calibrado         = False
        self._iq_detectado      = False
        self._lock              = threading.Lock()
        self._fail_count        = 0   # fallos consecutivos de _verificar_rapido

    # ── API pública ──────────────────────────────────────────────────────────────

    def calibrar_ahora(self):
        """Fuerza calibración completa en hilo aparte (no bloquea al llamador)."""
        threading.Thread(target=self._full_calib, daemon=True,
                         name="CalibForce").start()

    @property
    def esta_calibrado(self) -> bool:
        return self._calibrado

    # ── Hilo principal ───────────────────────────────────────────────────────────

    def run(self):
        time.sleep(3.5)      # esperar a que la UI arranque
        self._full_calib()

        while True:
            # Intervalo dinámico: más frecuente cuando trading está activo
            # para mantener coordenadas siempre actualizadas sin calibración manual.
            trading_activo = getattr(self.app, "trading_on", False)
            intervalo = (_INTERVALO_VERIFICAR_TRADING if trading_activo
                         else _INTERVALO_VERIFICAR_IDLE)
            time.sleep(intervalo)
            if time.time() - self._ultimo_full_calib >= _INTERVALO_FULL_CALIB:
                self._full_calib()
            else:
                self._verificar_rapido()

    # ── Auto-detección de broker por título de ventana ──────────────────────────

    _MAPA_BROKERS = {
        "iq option":     "iq_option",
        "iqoption":      "iq_option",
        "quotex":        "quotex",
        "olymp trade":   "olymp_trade",
        "olymptrade":    "olymp_trade",
        "binomo":        "binomo",
        "deriv":         "deriv",
        "pocket option": "pocket_option",
        "pocketoption":  "pocket_option",
        "exness":        "exness",
        "xm global":     "xm",
        "metatrader":    "metatrader",
    }

    def _detectar_broker_ventana(self) -> str:
        """
        Escanea títulos de ventanas abiertas para identificar el broker.
        Devuelve clave de PERFILES o 'iq_option' como fallback seguro.
        """
        try:
            import ctypes
            titulos: list = []

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            )

            def _cb(hwnd, _):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
                        titulos.append(buf.value.lower())
                return True

            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)

            for titulo in titulos:
                for nombre, clave in self._MAPA_BROKERS.items():
                    if nombre in titulo:
                        return clave
        except Exception:
            pass
        return "iq_option"

    def _actualizar_broker_activo(self):
        """Detecta el broker y lo registra en config si cambió."""
        app    = self.app
        clave  = self._detectar_broker_ventana()
        cfg    = app.mem["config"]
        actual = cfg.get("broker_activo", "iq_option")

        if clave != actual:
            cfg["broker_activo"] = clave
            from . import broker_iq as biq, memoria as mem_mod
            nombre = biq.PERFILES.get(clave, {}).get("nombre", clave)
            app.log(f"[AutoCalib] Broker detectado automáticamente: {nombre}")
            if hasattr(app, "broker"):
                app.broker.cambiar_broker(clave)
            try:
                mem_mod.guardar(app.mem)
            except Exception:
                pass

    # ── Calibración completa ─────────────────────────────────────────────────────

    def _full_calib(self):
        if not _NP or not _MSS:
            return

        app = self.app
        from . import vision, memoria as mem_mod

        # Auto-detectar broker activo antes de calibrar
        self._actualizar_broker_activo()

        img = vision.capturar_pantalla_completa()
        if img is None:
            return

        # Detección principal (SUBE, BAJA, gráfico) — funciona con cualquier broker
        # que use botones verdes/rojos en el lado derecho de la pantalla
        resultado = vision.auto_calibrar_iq()
        if not resultado.get("boton_verde") and not resultado.get("boton_rojo"):
            return   # IQ Option no está visible

        cfg     = app.mem["config"]
        cambios = []

        for clave, valor in resultado.items():
            if cfg.get(clave) != valor:
                cfg[clave]  = valor
                cambios.append(clave)

        # Área P&L (si no está calibrada)
        if not cfg.get("region_pl"):
            pl = self._detectar_pl(img)
            if pl:
                cfg["region_pl"] = pl
                cambios.append("region_pl")

        # Botón Rollover/Sell (si no está calibrado)
        if not cfg.get("boton_rollover"):
            rv = self._detectar_rollover(img)
            if rv:
                cfg["boton_rollover"] = rv
                cambios.append("boton_rollover")

        primera_vez = not self._iq_detectado
        self._iq_detectado = True
        self._calibrado    = bool(cfg.get("boton_verde") and cfg.get("boton_rojo"))
        self._ultimo_full_calib = time.time()

        if cambios:
            mem_mod.guardar(app.mem)
            app.log(f"[AutoCalib] Actualizado: {', '.join(cambios)}")

        # Alimentar UILearner con posiciones verificadas visualmente
        try:
            ul = getattr(app, "ui_learner", None)
            if ul is not None:
                ul.alimentar_calibracion(
                    boton_verde    = cfg.get("boton_verde"),
                    boton_rojo     = cfg.get("boton_rojo"),
                    region_grafico = cfg.get("region_grafico"))
        except Exception:
            pass

        if primera_vez and self._calibrado:
            self._on_primer_calibrado()

    def _on_primer_calibrado(self):
        """Acciones automáticas en la primera calibración exitosa."""
        app = self.app
        cfg = app.mem["config"]

        partes = []
        if cfg.get("boton_verde"):    partes.append("SUBE")
        if cfg.get("boton_rojo"):     partes.append("BAJA")
        if cfg.get("region_grafico"): partes.append("grafico")
        if cfg.get("region_pl"):      partes.append("P&L")
        if cfg.get("boton_rollover"): partes.append("Rollover")

        periodo = cfg.get("periodo_vela", 120)
        consejo = ""
        if int(periodo) > 30:
            consejo = (
                " Para Blitz de 30 segundos, le recomiendo cambiar 'Periodo vela'"
                " a 30 en Configuracion para operar al maximo ritmo."
                if app.idioma == "es" else
                " For 30-second Blitz, I recommend setting 'Candle period' to 30"
                " in Settings for optimal trade frequency.")

        app.log("[AutoCalib] IQ Option detectado — calibracion inicial completa.")
        app.decir(app.txt(
            f"Calibracion automatica exitosa, senor. Detecte: {', '.join(partes)}.{consejo}",
            f"Auto-calibration complete, sir. Detected: {', '.join(partes)}.{consejo}"))

        # Auto-activar analisis (solo observacion, sin clicks — siempre seguro)
        if not app.trading_on:
            app.trading_on = True
            app._refrescar()
            app.log("[AutoCalib] Analisis de mercado activado automaticamente.")

        # Si modo_autonomo ya activo → activar tambien auto-click
        if app.modo_autonomo and not app.autoclick_on:
            app.autoclick_on = True
            app._refrescar()
            app.log("[AutoCalib] Auto-click activado (modo autonomo activo).")

    # ── Verificación rápida ──────────────────────────────────────────────────────

    def _verificar_rapido(self):
        if not _NP or not _MSS:
            return

        from . import vision
        cfg   = self.app.mem["config"]
        btn_v = cfg.get("boton_verde")
        btn_r = cfg.get("boton_rojo")
        if not btn_v or not btn_r:
            self._full_calib()
            return

        img = vision.capturar_pantalla_completa()
        if img is None:
            return

        h, w = img.shape[:2]

        def _color_ok(x, y, espera_verde: bool, radio: int = 25) -> bool:
            """Radio ampliado a 25 (antes 15) para tolerar animaciones post-trade."""
            y1 = max(0, y - radio); y2 = min(h, y + radio)
            x1 = max(0, x - radio); x2 = min(w, x + radio)
            if y2 <= y1 or x2 <= x1:
                return False
            zona = img[y1:y2, x1:x2]
            # img[:,:,0]=B, [:,:,1]=G, [:,:,2]=R
            b_ch = float(zona[:, :, 0].mean())
            g_ch = float(zona[:, :, 1].mean())
            r_ch = float(zona[:, :, 2].mean())
            # Umbral reducido a 1.05 (antes 1.10) — sobrevive hover/animación
            if espera_verde:
                return g_ch > r_ch * 1.05 and g_ch > 50
            else:
                return r_ch > g_ch * 1.05 and r_ch > 50

        # Omitir check si el cursor está muy cerca de algún botón — el hover
        # state de IQ Option cambia el color del botón y daría falso positivo.
        try:
            import pyautogui as _pag
            cx, cy = _pag.position()
            _cerca_btn = (
                abs(cx - btn_v[0]) < 50 and abs(cy - btn_v[1]) < 35 or
                abs(cx - btn_r[0]) < 50 and abs(cy - btn_r[1]) < 35)
        except Exception:
            _cerca_btn = False

        _v_ok = _cerca_btn or _color_ok(btn_v[0], btn_v[1], True)
        _r_ok = _cerca_btn or _color_ok(btn_r[0], btn_r[1], False)

        if _v_ok and _r_ok:
            self._fail_count = 0   # reset en detección exitosa
            # Actualizar template con imagen fresca (mejora future matching)
            try:
                _tv = img[max(0, btn_v[1]-28):btn_v[1]+28,
                           max(0, btn_v[0]-48):btn_v[0]+48]
                _tr = img[max(0, btn_r[1]-28):btn_r[1]+28,
                           max(0, btn_r[0]-48):btn_r[0]+48]
                vision._guardar_template("boton_verde", _tv)
                vision._guardar_template("boton_rojo",  _tr)
            except Exception:
                pass
        else:
            self._fail_count += 1
            # Solo re-calibrar tras 3 fallos consecutivos y cooldown de 60s
            if (self._fail_count >= 3
                    and time.time() - self._ultimo_full_calib >= 60):
                self.app.log("[AutoCalib] Botones desplazados — re-calibrando.")
                self._fail_count = 0
                self._full_calib()

    # ── Detectores auxiliares ────────────────────────────────────────────────────

    def _detectar_pl(self, img) -> list | None:
        """Busca texto verde/rojo brillante en el 40% derecho (P&L activo)."""
        if not _NP:
            return None
        h, w = img.shape[:2]
        xo  = int(w * 0.60)
        yo1 = int(h * 0.15)
        yo2 = int(h * 0.85)
        zona = img[yo1:yo2, xo:]

        # img de mss es BGR: índice 0=B, 1=G, 2=R
        r = zona[:, :, 2].astype(float)
        g = zona[:, :, 1].astype(float)

        mask = ((g > 130) & (g > r * 1.3)) | ((r > 130) & (r > g * 1.3))
        ys, xs = np.where(mask)
        if len(ys) < 30:
            return None

        y1 = max(0,  int(ys.min()) - 5) + yo1
        y2 = min(h,  int(ys.max()) + 5) + yo1
        x1 = max(xo, int(xs.min()) + xo - 5)
        x2 = min(w,  int(xs.max()) + xo + 5)

        if x2 - x1 < 15 or y2 - y1 < 8:
            return None
        return [x1, y1, x2, y2]

    def _detectar_rollover(self, img) -> list | None:
        """
        Busca botón naranja/amarillo de Rollover (Sell) en zona de controles.
        Solo aparece cuando hay un trade activo en IQ Option.
        """
        if not _NP:
            return None
        h, w = img.shape[:2]
        xo   = int(w * 0.55)
        zona = img[:, xo:]

        # img BGR: 0=B, 1=G, 2=R
        r = zona[:, :, 2].astype(float)
        g = zona[:, :, 1].astype(float)
        b = zona[:, :, 0].astype(float)

        # Naranja-amarillo: R alto, G medio, B bajo
        mask = (r > 160) & (g > 90) & (g < r * 0.85) & (b < 80)
        ys, xs = np.where(mask)
        if len(ys) < 80:
            return None

        cy = int(ys.mean())
        cx = int(xs.mean()) + xo
        return [cx, cy]
