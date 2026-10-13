"""overlay.py — El borde que dice qué está mirando Litch.

━━━ QUÉ SE ARREGLÓ AQUÍ, Y POR QUÉ IMPORTA ━━━━━━━━━━━━━━━━━━━━━━━━━━━
La versión anterior tenía dos defectos que se veían en pantalla como un
recuadro verde «mocho»:

 1) EL BORDE MENTÍA SOBRE LO QUE LITCH VE.
    `set_region()` estaba vacío, con el comentario «siempre usamos
    pantalla completa». Así que el marco se dibujaba de borde a borde
    mientras Litch capturaba, de verdad, solo la región guardada en
    memoria. El señor veía un marco enorme y creía que Litch veía todo;
    Litch veía un rectángulo mucho más pequeño. Un indicador que miente
    es peor que no tener indicador.

 2) LA ALTURA DE LA BARRA ESTABA ESCRITA A MANO Y ESTABA MAL.
    Aquí decía `RIBBON_H = 56`. En `interfaz.py` la barra mide 104. Son
    dos números para la misma cosa y no coincidían: 48 píxeles de
    diferencia. Y cuando el señor pliega la barra con el botón, la barra
    pasa a medir mucho menos — pero el borde se quedaba clavado en 56,
    sin bajar ni subir. Por eso el marco nunca cuadraba.

La regla que se aplica ahora, la misma de siempre en este proyecto:
**no se estima lo que se puede medir.** La barra se pregunta cuánto
mide. La pantalla se le pregunta a Windows. Y el marco se dibuja donde
Litch mira de verdad.

Estados:
  VIENDO      → borde VERDE pulsante  (Litch ve y analiza)
  BUSCANDO    → borde AMARILLO        (intentando encontrar el gráfico)
  SIN_GRAFICO → borde ROJO pulsante   (no hay gráfico visible)
  INACTIVO    → sin borde             (Litch en espera)
"""
from __future__ import annotations

import threading
import tkinter as tk

# Colores (claro, oscuro) para el pulso de cada estado
_COLORES = {
    "viendo":      ("#00e676", "#00a152"),
    "buscando":    ("#ffee58", "#f9a825"),
    "sin_grafico": ("#ef5350", "#c62828"),
    "inactivo":    (None, None),
}

# Color "llave" de transparencia en Windows: este píxel se vuelve invisible
_TRANSP = "#010203"

# Grosor del borde
_BORDE = 6

# Solo se usa si no hay forma de medir la barra de verdad.
RIBBON_H_POR_DEFECTO = 104

# Compatibilidad con código viejo que importaba RIBBON_H
RIBBON_H = RIBBON_H_POR_DEFECTO


def _pantalla_real(root) -> tuple[int, int]:
    """
    Tamaño real de la pantalla en píxeles físicos.

    Se le pregunta a Windows antes que a Tk. Motivo: si el proceso se
    hace consciente del DPI *después* de crear la ventana de Tk (que es
    lo que pasa aquí, porque conciencia_pantalla lo activa más tarde),
    Tk se queda con las medidas escaladas antiguas y devuelve una
    pantalla más pequeña de la que hay. Ese es el otro motivo por el que
    el marco no llegaba abajo del todo.
    """
    try:
        import ctypes
        u = ctypes.windll.user32
        w = u.GetSystemMetrics(0)   # SM_CXSCREEN
        h = u.GetSystemMetrics(1)   # SM_CYSCREEN
        if w > 0 and h > 0:
            return int(w), int(h)
    except Exception:
        pass
    try:
        return int(root.winfo_screenwidth()), int(root.winfo_screenheight())
    except Exception:
        return 1920, 1080


class OverlayRegion:
    """
    Marco transparente que rodea exactamente lo que Litch está mirando.

    Si hay región de captura conocida, el marco la rodea a ella.
    Si no la hay, rodea toda el área de trabajo por debajo de la barra.
    En los dos casos, el interior queda 100 % transparente.
    """

    def __init__(self, root: tk.Tk, ui=None):
        self._root    = root
        self._ui      = ui        # la interfaz, para preguntarle cuánto mide
        self._win     = None
        self._canvas  = None
        self._estado  = "inactivo"
        self._region  = None      # [x1, y1, x2, y2] de la captura real
        self._fase    = 0
        self._lock    = threading.Lock()
        self._activo  = True

    # ── API pública (segura entre hilos) ─────────────────────────────────────

    def set_region(self, region) -> None:
        """
        Fija la región que Litch está capturando de verdad.

        Antes esto se ignoraba. Ahora es justamente lo que se dibuja: el
        marco pasa a significar «esto es lo que veo», que es lo que el
        señor necesita saber de un vistazo.
        """
        try:
            if not region:
                with self._lock:
                    self._region = None
                return
            x1, y1, x2, y2 = (int(v) for v in region[:4])
            if x2 < x1:
                x1, x2 = x2, x1
            if y2 < y1:
                y1, y2 = y2, y1
            # Una región degenerada (de menos de 20 px de lado) no es una
            # región: es una calibración a medias. Mejor no dibujar nada
            # que dibujar una mentira diminuta.
            if (x2 - x1) < 20 or (y2 - y1) < 20:
                with self._lock:
                    self._region = None
                return
            with self._lock:
                self._region = [x1, y1, x2, y2]
        except Exception:
            with self._lock:
                self._region = None

    def set_estado(self, estado: str) -> None:
        with self._lock:
            self._estado = estado

    def iniciar(self) -> None:
        self._root.after(200, self._tick)

    def destruir(self) -> None:
        self._activo = False
        try:
            if self._win:
                self._win.destroy()
        except Exception:
            pass
        self._win = None

    # ── Medir, no adivinar ───────────────────────────────────────────────────

    def _alto_barra(self) -> int:
        """
        Cuánto mide la barra de Litch AHORA MISMO.

        Se le pregunta a la ventana de la barra. Si el señor la plegó con
        el botón, esto devuelve el alto plegado y el marco sube a ocupar
        el sitio que quedó libre — que es exactamente para lo que sirve
        ese botón. Si no se puede medir, se usa el valor por defecto, y
        eso es un último recurso, no la vía normal.
        """
        v = getattr(self._ui, "_barra_win", None) if self._ui else None
        try:
            if v is not None and v.winfo_exists():
                v.update_idletasks()
                h = int(v.winfo_height())
                # winfo_height() devuelve 1 mientras la ventana no se ha
                # dibujado. Ese 1 no es una medida, es un «todavía no».
                if 10 <= h <= 400:
                    return h
                geo = v.winfo_geometry()          # "1920x104+0+0"
                h = int(geo.split("+")[0].split("x")[1])
                if 10 <= h <= 400:
                    return h
        except Exception:
            pass
        # Si la barra está plegada y no se pudo medir, al menos se sabe
        # por la preferencia guardada que ocupa poco.
        try:
            if self._ui and self._ui.app.mem["config"].get("ribbon_plegado"):
                return 28
        except Exception:
            pass
        return RIBBON_H_POR_DEFECTO

    # ── Bucle de dibujo ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        if not self._activo:
            return
        try:
            self._dibujar()
        except Exception:
            pass
        self._root.after(1200, self._tick)

    def _dibujar(self) -> None:
        with self._lock:
            estado = self._estado
            region = list(self._region) if self._region else None

        colores = _COLORES.get(estado, (None, None))
        if colores[0] is None:
            self._ocultar()
            return

        self._fase = (self._fase + 1) % 2
        color = colores[self._fase]

        sw, sh = _pantalla_real(self._root)
        barra = self._alto_barra()

        if self._win is None:
            self._crear_ventana(sw, sh)
        if self._win is None:
            return

        try:
            self._win.geometry(f"{sw}x{sh}+0+0")
            self._win.deiconify()
            self._win.attributes("-topmost", False)

            c = self._canvas
            try:
                c.config(width=sw, height=sh)
            except Exception:
                pass
            b = _BORDE
            c.delete("borde")

            if region:
                # ── Marco ceñido a lo que Litch captura de verdad ────────
                x1, y1, x2, y2 = region
                # Se recorta a la pantalla: una región mal calibrada no
                # debe pintar fuera del mundo.
                x1 = max(0, min(x1, sw)); x2 = max(0, min(x2, sw))
                y1 = max(0, min(y1, sh)); y2 = max(0, min(y2, sh))
                # Tk centra el trazo sobre la línea del rectángulo. Si la
                # región llega al borde de la pantalla, la mitad del trazo
                # cae fuera del lienzo y el borde se ve la mitad de grueso
                # — o no se ve. Se mete media anchura hacia dentro para que
                # el marco de pantalla completa se vea entero.
                m = b // 2
                x1 = max(x1, m); y1 = max(y1, m)
                x2 = min(x2, sw - m); y2 = min(y2, sh - m)
                c.create_rectangle(x1, y1, x2, y2,
                                   outline=color, width=b, tags="borde")
                c.create_rectangle(x1 + b, y1 + b, x2 - b, y2 - b,
                                   outline=color, width=1, tags="borde")
                # Esquinas marcadas: se ven aunque el fondo sea del mismo
                # color que el borde, que pasa con gráficos en verde.
                g = 22
                for (ex, ey, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1),
                                          (x1, y2, 1, -1), (x2, y2, -1, -1)):
                    c.create_line(ex, ey, ex + g * dx, ey,
                                  fill=color, width=b + 2, tags="borde")
                    c.create_line(ex, ey, ex, ey + g * dy,
                                  fill=color, width=b + 2, tags="borde")
            else:
                # ── Sin región: se rodea el área bajo la barra ───────────
                oy = barra
                c.create_rectangle(0, oy, b * 2, sh,
                                   fill=color, outline="", tags="borde")
                c.create_rectangle(sw - b * 2, oy, sw, sh,
                                   fill=color, outline="", tags="borde")
                c.create_rectangle(0, sh - b * 2, sw, sh,
                                   fill=color, outline="", tags="borde")
                c.create_rectangle(0, oy, sw, oy + b,
                                   fill=color, outline="", tags="borde")
                c.create_rectangle(b * 3, oy + b * 2, sw - b * 3, sh - b * 3,
                                   outline=color, width=1, fill="", tags="borde")

        except tk.TclError:
            self._win = None

    def _crear_ventana(self, w: int, h: int) -> None:
        try:
            v = tk.Toplevel(self._root)
            v.overrideredirect(True)
            v.attributes("-topmost", False)   # la barra va por encima
            v.geometry(f"{w}x{h}+0+0")
            v.configure(bg=_TRANSP)
            v.wm_attributes("-transparentcolor", _TRANSP)
            v.wm_attributes("-alpha", 0.85)
            c = tk.Canvas(v, bg=_TRANSP, width=w, height=h,
                          highlightthickness=0)
            c.pack(fill="both", expand=True)
            self._win    = v
            self._canvas = c
        except Exception:
            self._win = None

    def _ocultar(self) -> None:
        if self._win:
            try:
                self._win.withdraw()
            except Exception:
                pass
