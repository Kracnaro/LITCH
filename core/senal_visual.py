"""
senal_visual.py — HUD profesional de señales para LITCH v3.

Panel flotante siempre-encima que muestra en tiempo real:

  MODO SEÑAL ACTIVA:
  ┌─────────────────────┐
  │ ⚡ LITCH · SEÑAL    │
  │  ▲▲  SUBE  ▲▲      │  ← flecha animada
  │  ████████████░  82% │  ← barra de confianza
  │  ●●●●●●○  6/7 votos │  ← qué métodos votaron
  │  [████████████  12s]│  ← cuenta regresiva
  │  TRENDING · EUR/AUD │
  └─────────────────────┘

  MODO URGENTE (< 5s):
  ┌─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐   ← borde parpadeante
  │  ⚡ ¡ACTÚA YA! ⚡   │
  │      ▲  SUBE  ▲     │
  │         3s          │
  └─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘

  MODO ESPERA (sin señal):
  ┌─────────────────────┐
  │  LITCH · Analizando │  ← mini, semitransparente
  │  ◌ ◌ ◌  (espera)   │
  └─────────────────────┘

Características:
  • Draggable: el usuario puede moverlo a donde quiera
  • Cuenta regresiva en tiempo real con barra de color
  • Modo URGENTE automático cuando quedan < 5 segundos
  • Historial de las últimas 4 señales (✓ / ✗)
  • Indicadores individuales de qué métodos votaron
  • Thread-safe vía root.after()
  • Doble clic para minimizar/restaurar
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import tkinter as tk
from typing import Optional

# Archivo donde se guarda la última posición del HUD
_POS_FILE = os.path.join(os.path.dirname(__file__), "..", "hud_pos.json")

# ── Paleta de colores ─────────────────────────────────────────────────────────
_C = {
    "transp":    "#010203",   # clave de transparencia Windows
    "fondo":     "#0d1117",   # negro azulado (fondo general)
    "fondo2":    "#161b22",   # gris muy oscuro (panel interior)
    "sube_bg":   "#00c853",   # verde vivo
    "sube_dark": "#00701e",   # verde oscuro
    "baja_bg":   "#d50000",   # rojo vivo
    "baja_dark": "#7f0000",   # rojo oscuro
    "acento":    "#00e5ff",   # cyan neón (título)
    "texto":     "#e6edf3",   # blanco suave
    "texto2":    "#8b949e",   # gris claro (secundario)
    "amarillo":  "#ffd600",   # urgencia / advertencia
    "borde":     "#30363d",   # borde gris oscuro
    "espera_bg": "#161b22",   # fondo modo espera
}

# ── Dimensiones ───────────────────────────────────────────────────────────────
_W   = 220   # ancho normal
_H   = 310   # alto normal
_W_U = 200   # ancho modo urgente
_H_U = 180   # alto modo urgente
_W_M = 160   # ancho minimizado
_H_M = 32    # alto minimizado

_PULSO_MS  = 350   # ms entre frames de animación
_URGENTE_S = 6     # segundos restantes para activar modo urgente


class SenalVisual:
    """
    HUD profesional de señales de trading para LITCH.

    API pública (thread-safe, llamar desde cualquier hilo):
        sv.mostrar(direccion, votos, confianza, secs_restantes,
                   patron, regimen, votos_detalle, asset)
        sv.ocultar()
        sv.actualizar_tiempo(secs)
        sv.registrar_resultado(gano: bool)   # para historial ✓/✗
    """

    def __init__(self, root: tk.Tk, app=None):
        self._root  = root
        self._app   = app
        self._lock  = threading.Lock()

        # Estado interno
        self._visible      = False
        self._minimizado   = False
        self._dir          = None
        self._votos        = 0
        self._confianza    = 0.0
        self._secs         = 0
        self._secs_total   = 60
        self._patron       = ""
        self._regimen      = ""
        self._asset        = ""
        self._votos_det    : list[int] = []   # 0/1 por cada uno de los 7 métodos
        self._historial    : list[bool] = []  # últimos 4 resultados
        self._pulso_fase   = 0
        self._urgente      = False
        self._ultimo_ts    = 0.0
        self._drag_x       = 0
        self._drag_y       = 0
        self._ultimo_redib = 0.0   # timestamp último redibujado (anti-freeze)

        # Posición: carga la última posición guardada o usa un valor por defecto
        # que NO tape los botones SUBE/BAJA de IQ Option.
        # El usuario puede arrastrar el HUD a donde quiera — se guarda automáticamente.
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        _pos = self._cargar_posicion()
        self._px = _pos[0] if _pos else sw - _W - 160
        self._py = _pos[1] if _pos else sh - _H - 110

        self._win:    Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas]  = None
        self._crear_ventana()

    # ── API pública ───────────────────────────────────────────────────────────

    def mostrar(self, direccion: str,
                votos:         int   = 0,
                confianza:     float = 0.5,
                secs_restantes: int  = 0,
                patron:        str   = "",
                regimen:       str   = "",
                votos_detalle: list  = None,
                asset:         str   = "") -> None:
        with self._lock:
            self._dir       = direccion
            self._votos     = votos
            self._confianza = confianza
            self._secs      = secs_restantes
            self._patron    = patron
            self._regimen   = regimen
            self._asset     = asset
            self._votos_det = list(votos_detalle) if votos_detalle else []
            self._visible   = True
            self._urgente   = (secs_restantes > 0 and secs_restantes <= _URGENTE_S)
            self._ultimo_ts = time.time()
        self._root.after(0, self._redibujar)

    def ocultar(self) -> None:
        with self._lock:
            self._visible = False
            self._dir     = None
        self._root.after(0, self._modo_espera)

    def actualizar_tiempo(self, secs: int) -> None:
        urgente_ant = self._urgente
        with self._lock:
            self._secs    = secs
            self._urgente = (secs > 0 and secs <= _URGENTE_S)
        # Si cambia a modo urgente → redibujar completo
        if self._urgente != urgente_ant and self._visible:
            self._root.after(0, self._redibujar)
        elif self._visible:
            self._root.after(0, self._solo_timer)

    def registrar_resultado(self, gano: bool) -> None:
        with self._lock:
            self._historial.append(gano)
            if len(self._historial) > 4:
                self._historial = self._historial[-4:]

    def set_posicion(self, x: int, y: int) -> None:
        self._px, self._py = x, y
        if self._win:
            self._root.after(0, lambda: self._win.geometry(
                f"+{x}+{y}"))

    def iniciar_pulso(self) -> None:
        self._root.after(_PULSO_MS, self._tick_animacion)

    # ── Creación de ventana ───────────────────────────────────────────────────

    def _crear_ventana(self) -> None:
        try:
            win = tk.Toplevel(self._root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.88)
            win.geometry(f"{_W_M}x{_H_M}+{self._px}+{self._py}")

            try:
                win.wm_attributes("-transparentcolor", _C["transp"])
            except Exception:
                pass

            canvas = tk.Canvas(win, width=_W, height=_H,
                               bg=_C["transp"], highlightthickness=0,
                               cursor="hand2")
            canvas.pack(fill="both", expand=True)

            # Drag
            canvas.bind("<ButtonPress-1>",   self._drag_inicio)
            canvas.bind("<B1-Motion>",       self._drag_mover)
            canvas.bind("<Double-Button-1>", self._toggle_minimizar)

            self._win    = win
            self._canvas = canvas
            self._modo_espera()
        except Exception as e:
            self._win = self._canvas = None
            if self._app:
                self._app.log(f"[HUD] Error init: {e}")

    # ── Redibujado principal ──────────────────────────────────────────────────

    def _redibujar(self) -> None:
        if self._win is None or self._canvas is None:
            return
        # Anti-freeze: no redibujar más de 1 vez cada 380ms
        ahora = time.time()
        if ahora - self._ultimo_redib < 0.38:
            self._root.after(400, self._redibujar_si_pendiente)
            return
        self._ultimo_redib = ahora
        if self._minimizado:
            self._dibujar_minimizado()
            return
        if not self._visible:
            self._modo_espera()
            return
        if self._urgente:
            self._dibujar_urgente()
        else:
            self._dibujar_normal()

    def _redibujar_si_pendiente(self) -> None:
        """Redibujado diferido — solo si la ventana sigue visible."""
        if self._visible or self._minimizado:
            self._redibujar()

    def _dibujar_normal(self) -> None:
        c  = self._canvas
        w, h = _W, _H
        try:
            self._win.geometry(f"{w}x{h}+{self._px}+{self._py}")
            c.configure(width=w, height=h)
            c.delete("all")

            es   = self._dir in ("V", "VERDE", "UP")
            col  = _C["sube_bg"]   if es else _C["baja_bg"]
            dark = _C["sube_dark"] if es else _C["baja_dark"]
            txt  = "SUBE" if es else "BAJA"
            flecha_txt = "▲" if es else "▼"
            conf_pct   = int(self._confianza * 100)

            # ── Fondo principal ──────────────────────────────────────────────
            self._rrect(c, 0, 0, w, h, r=14, fill=_C["fondo"], outline=col, width=2)

            # ── Cabecera ─────────────────────────────────────────────────────
            self._rrect(c, 0, 0, w, 36, r=14, fill=col, outline="")
            # Rectángulo inferior de la cabecera para que quede plano abajo
            c.create_rectangle(0, 22, w, 36, fill=col, outline="")
            c.create_text(w//2, 18, text=f"⚡  LITCH · SEÑAL",
                          font=("Segoe UI", 9, "bold"),
                          fill=_C["fondo"], anchor="center")

            # ── Flecha grande ────────────────────────────────────────────────
            # Sombra
            c.create_text(w//2 + 2, 88, text=flecha_txt,
                          font=("Segoe UI", 68, "bold"),
                          fill=dark, anchor="center")
            c.create_text(w//2, 86, text=flecha_txt,
                          font=("Segoe UI", 68, "bold"),
                          fill=col, anchor="center")

            # ── Texto dirección ──────────────────────────────────────────────
            c.create_text(w//2, 132, text=txt,
                          font=("Segoe UI", 20, "bold"),
                          fill=_C["texto"], anchor="center")

            # ── Barra de confianza ───────────────────────────────────────────
            bar_x1, bar_y1 = 14, 148
            bar_x2, bar_y2 = w - 14, 162
            # Fondo barra
            self._rrect(c, bar_x1, bar_y1, bar_x2, bar_y2, r=5,
                        fill=_C["borde"], outline="")
            # Relleno barra
            fill_w = int((bar_x2 - bar_x1) * min(self._confianza, 1.0))
            if fill_w > 6:
                self._rrect(c, bar_x1, bar_y1, bar_x1 + fill_w, bar_y2,
                            r=5, fill=col, outline="")
            # Texto confianza
            c.create_text(bar_x1, 172, text="Confianza",
                          font=("Segoe UI", 8), fill=_C["texto2"], anchor="w")
            c.create_text(bar_x2, 172, text=f"{conf_pct}%",
                          font=("Segoe UI", 9, "bold"),
                          fill=col, anchor="e")

            # ── Votos (7 círculos) ───────────────────────────────────────────
            self._dibujar_votos(c, w//2, 192, es)

            # ── Contador regresivo ────────────────────────────────────────────
            self._dibujar_timer(c, w, 210, h - 50)

            # ── Historial últimas 4 señales ──────────────────────────────────
            self._dibujar_historial(c, w, h - 28)

            # ── Pie: régimen + asset ─────────────────────────────────────────
            pie = []
            if self._regimen:
                pie.append(self._regimen.upper()[:10])
            if self._asset:
                pie.append(self._asset[:10])
            if pie:
                c.create_text(w//2, h - 10,
                              text=" · ".join(pie),
                              font=("Segoe UI", 7),
                              fill=_C["texto2"], anchor="center")

            self._win.attributes("-alpha", 0.93)
            self._win.lift()

        except Exception as e:
            if self._app:
                self._app.log(f"[HUD] draw_normal: {e}")

    def _dibujar_urgente(self) -> None:
        c  = self._canvas
        w, h = _W_U, _H_U
        try:
            self._win.geometry(f"{w}x{h}+{self._px}+{self._py}")
            c.configure(width=w, height=h)
            c.delete("all")

            es   = self._dir in ("V", "VERDE", "UP")
            col  = _C["sube_bg"] if es else _C["baja_bg"]
            dark = _C["sube_dark"] if es else _C["baja_dark"]
            txt  = "SUBE" if es else "BAJA"
            flecha = "▲" if es else "▼"

            # Parpadeo del borde (alterna entre col y amarillo según fase)
            borde_col = _C["amarillo"] if self._pulso_fase % 2 == 0 else col
            self._rrect(c, 0, 0, w, h, r=12,
                        fill=_C["fondo"], outline=borde_col, width=4)
            c.create_rectangle(0, 18, w, 28, fill=_C["fondo"], outline="")

            # "¡ACTÚA YA!"
            c.create_text(w//2, 20, text="⚡  ¡ACTÚA YA!  ⚡",
                          font=("Segoe UI", 11, "bold"),
                          fill=_C["amarillo"], anchor="center")

            # Flecha grande
            c.create_text(w//2 + 2, 78, text=flecha,
                          font=("Segoe UI", 56, "bold"),
                          fill=dark, anchor="center")
            c.create_text(w//2, 76, text=flecha,
                          font=("Segoe UI", 56, "bold"),
                          fill=col, anchor="center")

            # Dirección
            c.create_text(w//2, 114, text=txt,
                          font=("Segoe UI", 18, "bold"),
                          fill=_C["texto"], anchor="center")

            # Contador grande
            secs_txt = str(max(0, self._secs))
            c.create_text(w//2, 148, text=secs_txt + "s",
                          font=("Segoe UI", 22, "bold"),
                          fill=_C["amarillo"], anchor="center")

            # Barra de tiempo (agotándose, roja)
            if self._secs_total > 0:
                bw = int((w - 20) * max(0, self._secs) / self._secs_total)
                c.create_rectangle(10, 163, w - 10, 170,
                                   fill=_C["borde"], outline="")
                if bw > 0:
                    c.create_rectangle(10, 163, 10 + bw, 170,
                                       fill=_C["amarillo"], outline="")

            self._win.attributes("-alpha", 0.97)
            self._win.lift()

        except Exception as e:
            if self._app:
                self._app.log(f"[HUD] draw_urgente: {e}")

    def _modo_espera(self) -> None:
        if self._win is None or self._canvas is None or self._minimizado:
            return
        c = self._canvas
        w, h = _W_M, _H_M
        try:
            self._win.geometry(f"{w}x{h}+{self._px}+{self._py}")
            c.configure(width=w, height=h)
            c.delete("all")
            self._rrect(c, 0, 0, w, h, r=8,
                        fill=_C["fondo2"], outline=_C["borde"], width=1)
            # Puntos animados
            dots = "◌" * (1 + self._pulso_fase % 3) + "  "
            c.create_text(8, h//2,
                          text=f"LITCH {dots}",
                          font=("Consolas", 8),
                          fill=_C["texto2"], anchor="w")
            self._win.attributes("-alpha", 0.55)
        except Exception:
            pass

    def _dibujar_minimizado(self) -> None:
        if self._win is None:
            return
        c = self._canvas
        w, h = _W_M, _H_M
        try:
            self._win.geometry(f"{w}x{h}+{self._px}+{self._py}")
            c.configure(width=w, height=h)
            c.delete("all")
            col = (_C["sube_bg"] if self._dir in ("V","VERDE","UP")
                   else (_C["baja_bg"] if self._dir else _C["borde"]))
            self._rrect(c, 0, 0, w, h, r=8, fill=col, outline="")
            if self._dir:
                txt = ("▲ SUBE" if self._dir in ("V","VERDE","UP") else "▼ BAJA")
                c.create_text(w//2, h//2, text=txt,
                              font=("Segoe UI", 10, "bold"),
                              fill="white", anchor="center")
            else:
                c.create_text(w//2, h//2, text="LITCH",
                              font=("Segoe UI", 9),
                              fill=_C["texto2"], anchor="center")
            self._win.attributes("-alpha", 0.85)
        except Exception:
            pass

    # ── Sub-renders ───────────────────────────────────────────────────────────

    def _dibujar_votos(self, c, cx: int, y: int, es_sube: bool) -> None:
        col_on  = _C["sube_bg"]  if es_sube else _C["baja_bg"]
        col_off = _C["borde"]
        n   = 7
        r   = 7
        gap = 5
        total_w = n * (r * 2) + (n - 1) * gap
        x0  = cx - total_w // 2

        nombres = ["Mkv", "Est", "Red", "Pro", "Ind", "RL", "SMC"]
        for i in range(n):
            xi = x0 + i * (r * 2 + gap) + r
            activo = (i < self._votos) if not self._votos_det else bool(
                self._votos_det[i] if i < len(self._votos_det) else 0)
            col = col_on if activo else col_off
            c.create_oval(xi - r, y - r, xi + r, y + r, fill=col, outline="")
            c.create_text(xi, y + r + 6, text=nombres[i],
                          font=("Consolas", 6), fill=_C["texto2"], anchor="center")

        c.create_text(cx, y - r - 6,
                      text=f"{self._votos}/7 votos",
                      font=("Segoe UI", 8, "bold"),
                      fill=_C["texto2"], anchor="center")

    def _dibujar_timer(self, c, w: int, y1: int, y2: int) -> None:
        secs  = max(0, self._secs)
        total = max(1, self._secs_total)
        ratio = secs / total

        # Color del timer: verde→amarillo→rojo
        if ratio > 0.40:
            tcol = "#4caf50"
        elif ratio > 0.15:
            tcol = _C["amarillo"]
        else:
            tcol = _C["baja_bg"]

        # Fondo barra
        bx1, bx2 = 14, w - 14
        by  = (y1 + y2) // 2
        c.create_rectangle(bx1, by - 5, bx2, by + 5,
                           fill=_C["borde"], outline="", tags="timer")
        # Relleno
        fill_w = int((bx2 - bx1) * ratio)
        if fill_w > 0:
            c.create_rectangle(bx1, by - 5, bx1 + fill_w, by + 5,
                               fill=tcol, outline="", tags="timer")
        # Texto tiempo
        c.create_text(w//2, y1 - 6, text=f"⏱  {secs}s",
                      font=("Segoe UI", 9, "bold"),
                      fill=tcol, anchor="center", tags="timer")

    def _dibujar_historial(self, c, w: int, y: int) -> None:
        if not self._historial:
            return
        items = self._historial[-4:]
        gap   = 24
        total = len(items) * gap
        x0    = w//2 - total//2
        for i, gano in enumerate(items):
            xi  = x0 + i * gap + 8
            sym = "✓" if gano else "✗"
            col = _C["sube_bg"] if gano else _C["baja_bg"]
            c.create_text(xi, y, text=sym,
                          font=("Segoe UI", 9, "bold"),
                          fill=col, anchor="center")

    def _solo_timer(self) -> None:
        """Actualiza solo la parte del timer sin redibujar todo."""
        if not self._visible or self._urgente:
            return
        if self._canvas is None:
            return
        try:
            self._canvas.delete("timer")
            self._dibujar_timer(self._canvas, _W, 210, _H - 50)
        except Exception:
            pass

    # ── Animación ─────────────────────────────────────────────────────────────

    def _tick_animacion(self) -> None:
        try:
            self._pulso_fase = (self._pulso_fase + 1) % 8
            if self._visible and self._win:
                if self._urgente:
                    # Parpadeo intenso en modo urgente
                    alpha = 0.99 if self._pulso_fase % 2 == 0 else 0.80
                    self._win.attributes("-alpha", alpha)
                    self._redibujar()   # redibujar para parpadear borde
                else:
                    # Pulso suave normal
                    alpha = 0.93 if self._pulso_fase < 4 else 0.88
                    self._win.attributes("-alpha", alpha)
                # Auto-ocultar si nadie actualizó en 10s
                if time.time() - self._ultimo_ts > 10.0:
                    self.ocultar()
            elif not self._visible:
                # En espera: animar dots
                if self._pulso_fase % 2 == 0:
                    self._modo_espera()
        except Exception:
            pass
        finally:
            if self._win:
                self._root.after(_PULSO_MS, self._tick_animacion)

    # ── Drag ─────────────────────────────────────────────────────────────────

    # ── Anclaje ──────────────────────────────────────────────────────────────
    #
    # El cartel estaba suelto: cualquier roce con el ratón lo arrastraba,
    # y acababa en mitad del gráfico tapando las velas. Un cartel que hay
    # que recolocar cada rato estorba más de lo que informa.
    #
    # Ahora está ANCLADO por defecto. Se mueve solo si el señor lo pide a
    # propósito, arrastrando con Ctrl pulsado. La preferencia se guarda.

    def _drag_inicio(self, e) -> None:
        # Sin Ctrl no hay arrastre: 0x0004 es la máscara de Control en Tk
        self._puede_arrastrar = bool(getattr(e, "state", 0) & 0x0004)
        if not self._puede_arrastrar:
            return
        self._drag_x = e.x_root - self._px
        self._drag_y = e.y_root - self._py

    def _drag_mover(self, e) -> None:
        if not getattr(self, "_puede_arrastrar", False):
            return          # anclado: el ratón pasa por encima sin moverlo
        self._px = e.x_root - self._drag_x
        self._py = e.y_root - self._drag_y
        if self._win:
            self._win.geometry(f"+{self._px}+{self._py}")
        # Guardar posición en disco (con debounce ligero)
        self._root.after(800, self._guardar_posicion)

    @staticmethod
    def _cargar_posicion():
        try:
            with open(_POS_FILE, "r") as f:
                d = json.load(f)
            return d.get("x"), d.get("y")
        except Exception:
            return None

    def _guardar_posicion(self) -> None:
        try:
            with open(_POS_FILE, "w") as f:
                json.dump({"x": self._px, "y": self._py}, f)
        except Exception:
            pass

    def _toggle_minimizar(self, _=None) -> None:
        self._minimizado = not self._minimizado
        self._redibujar()

    # ── Utilidades ────────────────────────────────────────────────────────────

    @staticmethod
    def _rrect(canvas, x1, y1, x2, y2, r=10, **kw) -> None:
        pts = [
            x1+r, y1,  x2-r, y1,
            x2,   y1,  x2,   y1+r,
            x2,   y2-r, x2,  y2,
            x2-r, y2,  x1+r, y2,
            x1,   y2,  x1,   y2-r,
            x1,   y1+r, x1,  y1,
        ]
        canvas.create_polygon(pts, smooth=True, **kw)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instancia: Optional[SenalVisual] = None


def obtener(root: tk.Tk = None, app=None) -> Optional[SenalVisual]:
    global _instancia
    if _instancia is None and root is not None:
        _instancia = SenalVisual(root, app)
        _instancia.iniciar_pulso()
    return _instancia
