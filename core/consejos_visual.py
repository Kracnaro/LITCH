"""
consejos_visual.py — Panel flotante de capital para LITCH v3.

Muestra en tiempo real:
  ┌──────────────────────────┐
  │ 💰  CAPITAL · LITCH      │
  │ Saldo   $7,555  ▲        │
  │ Monto   $50  0.66%  ✓   │
  │ Venc    45s / vela 45s ✓ │
  │ Aguanta 151 pérdidas      │
  ├──────────────────────────┤   ← solo si hay recomendación
  │ ⚠ Baja monto a $45       │
  └──────────────────────────┘

Draggable, minimizable con doble clic.
Thread-safe via root.after().
"""

from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
from typing import Optional

# ── Paleta ────────────────────────────────────────────────────────────────────
_BG     = "#0d1117"
_BG2    = "#161b22"
_BORDE  = "#30363d"
_CYAN   = "#00e5ff"
_VERDE  = "#00c853"
_AMARI  = "#ffd600"
_ROJO   = "#d50000"
_BLANCO = "#e6edf3"
_GRIS   = "#8b949e"
_TRANSP = "#010203"

# ── Geometría (valores fijos, sin cambios dinámicos de altura) ────────────────
_W    = 230   # ancho
_H    = 175   # alto con recomendación
_H_N  = 120   # alto sin recomendación
_H_M  = 26    # alto minimizado

_POS_FILE = os.path.join(os.path.dirname(__file__), "..", "hud_capital_pos.json")


class ConsejosVisual:
    """
    Panel flotante de gestión de capital para LITCH.

    API pública (thread-safe):
        cv.set_saldo(valor_float)               ← inicializa/actualiza el saldo
        cv.actualizar(saldo, monto, venc, per, recom, tendencia)
        cv.ocultar() / cv.mostrar()
    """

    def __init__(self, root: tk.Tk, app=None):
        self._root = root
        self._app  = app
        self._lock = threading.Lock()

        # Valores de estado
        self._saldo     = 0.0    # 0 = desconocido
        self._monto     = 0.0
        self._venc      = 60
        self._periodo   = 60
        self._recom     = None
        self._tendencia = "estable"   # 'sube' | 'baja' | 'estable'
        self._visible   = True
        self._mini      = False

        # Drag
        self._drag_x = self._drag_y = 0

        # Posición por defecto: esquina inferior izquierda
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        pos = self._cargar_pos()
        self._px = pos[0] if pos else 10
        self._py = pos[1] if pos else sh - _H - 80

        self._win:    Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas]   = None
        self._ultimo_redib = 0.0
        self._crear()

    # ── API pública ───────────────────────────────────────────────────────────

    def set_saldo(self, valor: float) -> None:
        """Establece el saldo base conocido."""
        with self._lock:
            self._saldo = max(0.0, float(valor))
        self._root.after(0, self._redibujar)

    def actualizar(self, saldo: float, monto: float,
                   vencimiento_seg: int = 60, periodo_seg: int = 60,
                   recomendacion: str = None,
                   saldo_tendencia: str = "estable") -> None:
        with self._lock:
            if saldo > 0:
                self._saldo = float(saldo)
            self._monto     = max(0.0, float(monto))
            self._venc      = max(1,   int(vencimiento_seg))
            self._periodo   = max(1,   int(periodo_seg))
            self._recom     = recomendacion
            self._tendencia = saldo_tendencia
        self._root.after(0, self._redibujar)

    def mostrar(self) -> None:
        with self._lock:
            self._visible = True
        self._root.after(0, self._redibujar)

    def ocultar(self) -> None:
        with self._lock:
            self._visible = False
        if self._win:
            self._root.after(0, lambda: (self._win and self._win.withdraw()))

    # ── Creación de ventana ───────────────────────────────────────────────────

    def _crear(self) -> None:
        try:
            win = tk.Toplevel(self._root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.92)
            win.geometry(f"{_W}x{_H_N}+{self._px}+{self._py}")
            try:
                win.wm_attributes("-transparentcolor", _TRANSP)
            except Exception:
                pass

            c = tk.Canvas(win, width=_W, height=_H,
                          bg=_TRANSP, highlightthickness=0,
                          cursor="hand2")
            c.pack(fill="both", expand=True)
            c.bind("<ButtonPress-1>",   self._drag_ini)
            c.bind("<B1-Motion>",       self._drag_mov)
            c.bind("<Double-Button-1>", self._toggle_mini)

            self._win    = win
            self._canvas = c
            self._redibujar()
        except Exception as e:
            self._win = self._canvas = None
            if self._app:
                self._app.log(f"[CapHUD] init error: {e}")

    # ── Dibujo ────────────────────────────────────────────────────────────────

    def _redibujar(self) -> None:
        if not self._win or not self._canvas:
            return
        ahora = time.time()
        if ahora - self._ultimo_redib < 0.35:
            self._root.after(380, self._redibujar)
            return
        self._ultimo_redib = ahora
        try:
            if self._mini:
                self._draw_mini()
            elif self._visible:
                self._draw_panel()
        except Exception:
            pass

    def _draw_panel(self) -> None:
        c  = self._canvas
        w  = _W
        h  = _H if self._recom else _H_N

        self._win.geometry(f"{w}x{h}+{self._px}+{self._py}")
        c.configure(width=w, height=h)
        c.delete("all")

        # ── Fondo ─────────────────────────────────────────────────────────────
        self._rr(c, 0, 0, w, h, r=10, fill=_BG, outline=_BORDE, width=1)

        # ── Cabecera cyan ──────────────────────────────────────────────────────
        self._rr(c, 0, 0, w, 24, r=10, fill=_CYAN, outline="")
        c.create_rectangle(0, 14, w, 24, fill=_CYAN, outline="")
        c.create_text(w // 2, 12,
                      text="💰  CAPITAL · LITCH",
                      font=("Segoe UI", 9, "bold"),
                      fill=_BG, anchor="center")

        # ── Filas ─────────────────────────────────────────────────────────────
        ROW_H = 22
        y = 34

        # Fila 1 — Saldo
        saldo_txt = f"${self._saldo:,.0f}" if self._saldo > 0 else "$ ?"
        tend_s    = ("▲" if self._tendencia == "sube" else
                     "▼" if self._tendencia == "baja" else "─")
        tend_c    = (_VERDE if self._tendencia == "sube" else
                     _ROJO  if self._tendencia == "baja" else _GRIS)
        self._fila(c, y, w, "Saldo",
                   f"{saldo_txt}  {tend_s}",
                   tend_c)
        y += ROW_H

        # Fila 2 — Monto + riesgo
        riesgo = self._monto / self._saldo if self._saldo > 0 else 0
        m_col  = (_VERDE  if riesgo <= 0.02 else
                  _AMARI  if riesgo <= 0.04 else _ROJO)
        m_icon = "✓" if riesgo <= 0.02 else ("⚠" if riesgo <= 0.04 else "✗")
        m_txt  = (f"${self._monto:.0f}  {riesgo:.1%}  {m_icon}"
                  if self._monto > 0 else "$ ?")
        self._fila(c, y, w, "Monto", m_txt, m_col)
        y += ROW_H

        # Fila 3 — Vencimiento vs período de vela
        ratio  = self._venc / max(1, self._periodo)
        v_col  = (_VERDE if 0.7 <= ratio <= 2.0 else
                  _AMARI if 0.4 <= ratio <= 3.5 else _ROJO)
        v_icon = "✓" if 0.7 <= ratio <= 2.0 else ("⚠" if 0.4 <= ratio <= 3.5 else "✗")
        v_txt  = f"{_t(self._venc)} / vela {_t(self._periodo)}  {v_icon}"
        self._fila(c, y, w, "Venc", v_txt, v_col)
        y += ROW_H

        # Fila 4 — Aguanta N pérdidas
        if self._saldo > 0 and self._monto > 0:
            aguanta = int(self._saldo / self._monto)
            ag_col  = (_VERDE  if aguanta >= 20 else
                       _AMARI  if aguanta >= 8  else _ROJO)
            self._fila(c, y, w, "Aguanta",
                       f"{aguanta} pérd. consec.", ag_col)
            y += ROW_H
        else:
            # Sin saldo conocido: pide inicialización
            c.create_text(w // 2, y + 8,
                          text='Di "mi saldo es X" para activar',
                          font=("Segoe UI", 7, "italic"),
                          fill=_GRIS, anchor="center")
            y += ROW_H

        # ── Recomendación ─────────────────────────────────────────────────────
        if self._recom:
            # Separador
            c.create_line(10, y + 4, w - 10, y + 4,
                          fill=_BORDE, width=1)
            y += 12
            for linea in _wrap(str(self._recom), 30)[:3]:
                c.create_text(12, y, text=linea,
                              font=("Segoe UI", 8),
                              fill=_AMARI, anchor="w")
                y += 14

        self._win.attributes("-alpha", 0.92)
        self._win.lift()

    def _draw_mini(self) -> None:
        c = self._canvas
        w, h = _W, _H_M
        self._win.geometry(f"{w}x{h}+{self._px}+{self._py}")
        c.configure(width=w, height=h)
        c.delete("all")
        self._rr(c, 0, 0, w, h, r=6, fill=_BG2, outline=_CYAN, width=1)
        riesgo = self._monto / self._saldo if self._saldo > 0 else 0
        col    = _VERDE if riesgo <= 0.02 else (_AMARI if riesgo <= 0.04 else _ROJO)
        saldo_txt = f"${self._saldo:,.0f}" if self._saldo > 0 else "$ ?"
        c.create_text(w // 2, h // 2,
                      text=f"💰 {saldo_txt}  |  ${self._monto:.0f}  {riesgo:.1%}",
                      font=("Segoe UI", 8, "bold"),
                      fill=col, anchor="center")
        self._win.attributes("-alpha", 0.80)

    # ── Helpers de dibujo ─────────────────────────────────────────────────────

    @staticmethod
    def _fila(canvas, y: int, w: int,
              etiqueta: str, valor: str, color_val: str) -> None:
        """Dibuja una fila etiqueta + valor alineado a la derecha."""
        canvas.create_text(12, y + 4, text=etiqueta,
                           font=("Segoe UI", 8), fill=_GRIS, anchor="w")
        canvas.create_text(w - 8, y + 4, text=valor,
                           font=("Segoe UI", 9, "bold"),
                           fill=color_val, anchor="e")

    @staticmethod
    def _rr(canvas, x1, y1, x2, y2, r=8, **kw) -> None:
        pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
               x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
               x1, y2, x1, y2-r, x1, y1+r, x1, y1]
        canvas.create_polygon(pts, smooth=True, **kw)

    # ── Drag ─────────────────────────────────────────────────────────────────

    def _drag_ini(self, e) -> None:
        self._drag_x = e.x_root - self._px
        self._drag_y = e.y_root - self._py

    def _drag_mov(self, e) -> None:
        self._px = e.x_root - self._drag_x
        self._py = e.y_root - self._drag_y
        if self._win:
            self._win.geometry(f"+{self._px}+{self._py}")
        self._root.after(800, self._guardar_pos)

    def _toggle_mini(self, _=None) -> None:
        self._mini = not self._mini
        self._redibujar()

    # ── Posición ─────────────────────────────────────────────────────────────

    def _cargar_pos(self):
        try:
            with open(_POS_FILE) as f:
                d = json.load(f)
            return d.get("x"), d.get("y")
        except Exception:
            return None

    def _guardar_pos(self) -> None:
        try:
            with open(_POS_FILE, "w") as f:
                json.dump({"x": self._px, "y": self._py}, f)
        except Exception:
            pass


# ── Helpers globales ──────────────────────────────────────────────────────────

def _t(segs: int) -> str:
    if segs < 60:   return f"{segs}s"
    if segs < 3600: return f"{segs // 60}m"
    return f"{segs // 3600}h"


def _wrap(texto: str, chars: int) -> list[str]:
    palabras = texto.split()
    lineas, linea = [], ""
    for p in palabras:
        if len(linea) + len(p) + 1 <= chars:
            linea += (" " if linea else "") + p
        else:
            if linea: lineas.append(linea)
            linea = p
    if linea: lineas.append(linea)
    return lineas


# ── Singleton ─────────────────────────────────────────────────────────────────

_instancia: Optional[ConsejosVisual] = None


def obtener(root: tk.Tk = None, app=None) -> Optional[ConsejosVisual]:
    global _instancia
    if _instancia is None and root is not None:
        _instancia = ConsejosVisual(root, app)
    return _instancia
