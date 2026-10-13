"""Panel flotante de Litch — la ventanita de control en la esquina.

Incluye: interruptores (sistema, micrófono, trading, auto-click), registro
de actividad, chat escrito, módulo de lotería y calibración de pantalla.
"""  # v2.0
import os
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

from . import (agente_web, correo, laboratorio, loteria, memoria, mente_claude,
               permisos as perms_mod, red_loteria, respaldo, scraper_loterias,
               seguridad, vision)
from .orbe import Orbe

RUTA_ICONO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "litch.ico")

try:
    import pyautogui
    _PG_OK = True
except Exception:
    _PG_OK = False

# Paleta estilo Litch
FONDO = "#0a1420"
PANEL = "#10202f"
ACENTO = "#00d4ff"
TEXTO = "#d6e6f2"
VERDE = "#2ecc71"
ROJO = "#e74c3c"
GRIS = "#5a6b7a"
FUENTE = ("Segoe UI", 9)
FUENTE_T = ("Segoe UI", 12, "bold")


# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE TOOLTIPS PROFESIONAL — estilo Microsoft Word
# ═══════════════════════════════════════════════════════════════════════════════

class ToolTip:
    """
    Tooltip flotante estilo Word: título en negrita + descripción + atajo de teclado.

    Aparece 450ms después de posar el mouse sobre el widget.
    Se posiciona inteligentemente (evita salir de la pantalla).

    Uso:
        ToolTip(boton, titulo="Chat de texto",
                descripcion="Abre el chat escrito para hablar con LITCH "
                            "sin necesidad de usar el micrófono.",
                atajo="Ctrl+C")
    """
    _DELAY_MS  = 450    # ms antes de aparecer
    _TIP_BG    = "#1a2535"
    _TIP_BOR   = "#00d4ff"
    _TIP_TITLE = "#00d4ff"
    _TIP_BODY  = "#c8d8e8"
    _TIP_ATAJO = "#5a6b7a"
    _MAX_W     = 280    # ancho máximo del tooltip

    def __init__(self, widget: tk.Widget, titulo: str,
                 descripcion: str = "", atajo: str = ""):
        self._widget  = widget
        self._titulo  = titulo
        self._desc    = descripcion
        self._atajo   = atajo
        self._tip_win = None
        self._after_id = None

        widget.bind("<Enter>",  self._on_enter,  add="+")
        widget.bind("<Leave>",  self._on_leave,  add="+")
        widget.bind("<Button>", self._on_leave,  add="+")

    def _on_enter(self, event=None):
        self._cancelar()
        self._after_id = self._widget.after(
            self._DELAY_MS, self._mostrar)

    def _on_leave(self, event=None):
        self._cancelar()
        self._ocultar()

    def _cancelar(self):
        if self._after_id:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _mostrar(self):
        if self._tip_win:
            return
        try:
            # Posición: debajo del widget, pegado a la izquierda del mismo
            wx  = self._widget.winfo_rootx()
            wy  = self._widget.winfo_rooty()
            wh  = self._widget.winfo_height()
            sw  = self._widget.winfo_screenwidth()
            sh  = self._widget.winfo_screenheight()

            win = tk.Toplevel(self._widget)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=self._TIP_BOR)
            self._tip_win = win

            # Marco interior
            inner = tk.Frame(win, bg=self._TIP_BG, padx=10, pady=8)
            inner.pack(padx=1, pady=1)

            # Título en negrita
            tk.Label(inner, text=self._titulo,
                     bg=self._TIP_BG, fg=self._TIP_TITLE,
                     font=("Segoe UI", 9, "bold"),
                     wraplength=self._MAX_W - 20,
                     justify="left").pack(anchor="w")

            # Separador
            if self._desc or self._atajo:
                tk.Frame(inner, bg="#2a3a4a",
                         height=1).pack(fill="x", pady=(4, 4))

            # Descripción
            if self._desc:
                tk.Label(inner, text=self._desc,
                         bg=self._TIP_BG, fg=self._TIP_BODY,
                         font=("Segoe UI", 8),
                         wraplength=self._MAX_W - 20,
                         justify="left").pack(anchor="w")

            # Atajo de teclado
            if self._atajo:
                tk.Label(inner, text=f"Atajo: {self._atajo}",
                         bg=self._TIP_BG, fg=self._TIP_ATAJO,
                         font=("Segoe UI", 7, "italic"),
                         justify="left").pack(anchor="w", pady=(4, 0))

            # Calcular posición final (evitar que salga de pantalla)
            win.update_idletasks()
            tw = win.winfo_reqwidth()
            th = win.winfo_reqheight()

            # Preferir debajo del widget, si no cabe arriba
            ty = wy + wh + 4
            if ty + th > sh - 40:
                ty = wy - th - 4

            tx = wx
            if tx + tw > sw - 10:
                tx = sw - tw - 10

            win.geometry(f"+{tx}+{ty}")

        except Exception:
            self._ocultar()

    def _ocultar(self):
        if self._tip_win:
            try:
                self._tip_win.destroy()
            except Exception:
                pass
            self._tip_win = None


def _tip(widget, titulo, descripcion="", atajo=""):
    """Shortcut para crear un ToolTip."""
    ToolTip(widget, titulo, descripcion, atajo)


def _scroll_seguro(sb):
    """
    Devuelve un `set` de barra de desplazamiento a prueba de desmontaje.

    Al cerrar Litch, Tk destruye los widgets en un orden que no
    controlamos. Si la barra muere antes que su lienzo, el lienzo la
    sigue llamando y Tk lanza:

        TclError: invalid command name ".!frame6...!scrollbar"

    No es un fallo de lógica — es la ventana desmontándose. Pero sale en
    rojo justo cuando el señor cierra el programa y parece que algo se
    rompió. Con esto, el desmontaje es silencioso.
    """
    def _set(*args, _sb=sb):
        try:
            if _sb.winfo_exists():
                _sb.set(*args)
        except Exception:
            pass
    return _set


class Interfaz:
    def __init__(self, app):
        self.app = app
        self.root = tk.Tk()
        self.root.title("Litch")
        self._aplicar_icono(self.root)
        self.root.configure(bg=FONDO)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)   # transparencia leve (vidrio esmerilado)
        self.root.resizable(True, True)         # ventana completamente redimensionable
        self._compacto   = False
        self._ancho_full = 368
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # Alto adaptado a la pantalla, no fijo.
        #
        # Estaba en 820 px. Con todo lo que hay ahora (orbe, ocho
        # interruptores en cuatro filas, conciencia, indicadores, medidor,
        # panel de control y trece botones de navegación) no sobraba ni un
        # píxel, y el REGISTRO DE ACTIVIDAD se quedaba con altura cero:
        # estaba ahí, pero no se veía. Es justo donde LITCH cuenta lo que
        # hace, así que perderlo no es un detalle estético.
        #
        # Se usa el 88% de la altura disponible, con un tope de 980 para
        # que en pantallas muy altas no quede desproporcionada.
        _disponible = max(560, sh - 90)          # 90 = barra de tareas + margen
        self._alto_full = max(760, min(980, int(_disponible * 0.88)))

        self.root.geometry(
            f"{self._ancho_full}x{self._alto_full}"
            f"+{sw - self._ancho_full - 14}+{sh - self._alto_full - 60}")
        self.root.minsize(260, 560)             # nunca más pequeña que esto
        self._chat = None
        self.orbe = None
        self._modo_rostro = False
        self._construir()
        # Cierre ordenado: al pulsar X se guarda TODO y se apaga sin colgarse
        self.root.protocol("WM_DELETE_WINDOW", self._cerrar_aplicacion)

    def _cerrar_aplicacion(self):
        """Guarda todo el aprendizaje y cierra Litch (nunca se cuelga)."""
        try:
            self.log("Guardando todo y cerrando…")
        except Exception:
            pass
        # El guardado corre en un hilo para no congelar la UI ni el cierre
        threading.Thread(target=self.app.cerrar_app, daemon=True,
                         name="LitchCierre").start()

    @staticmethod
    def _aplicar_icono(ventana):
        try:
            if os.path.exists(RUTA_ICONO):
                ventana.iconbitmap(RUTA_ICONO)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _construir(self):
        # ── Cabecera ──────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=FONDO)
        hdr.pack(fill="x", pady=(8, 0), padx=10)
        tk.Label(hdr, text="◉  Litch", bg=FONDO, fg=ACENTO,
                 font=FUENTE_T).pack(side="left", expand=True)

        # Botón de modo compacto
        self._btn_compacto = tk.Button(
            hdr, text="⊟", command=self._t_compacto,
            bg=FONDO, fg=GRIS, relief="flat",
            font=("Segoe UI", 13, "bold"), cursor="hand2",
            padx=4, pady=0, bd=0)
        self._btn_compacto.pack(side="right")

        # Botón modo barra de tareas (se oculta la ventana principal)
        self._btn_barra = tk.Button(
            hdr, text="▬", command=self._activar_barra,
            bg=FONDO, fg=GRIS, relief="flat",
            font=("Segoe UI", 11, "bold"), cursor="hand2",
            padx=4, pady=0, bd=0)
        self._btn_barra.pack(side="right")

        # Botón alternar Orbe ↔ Rostro
        self._btn_rostro = tk.Button(
            hdr, text="😶", command=self._t_modo_rostro,
            bg=FONDO, fg=GRIS, relief="flat",
            font=("Segoe UI", 11), cursor="hand2",
            padx=4, pady=0, bd=0)
        self._btn_rostro.pack(side="right", padx=(0, 2))

        # Línea separadora bajo la cabecera
        tk.Frame(self.root, bg=ACENTO, height=1).pack(fill="x", padx=10)

        # ── Orbe HD circular ───────────────────────────────────────────────
        # El canvas usa bg=FONDO para que sus esquinas sean invisibles
        # y el globo parezca perfectamente circular sobre la ventana
        self.orbe = Orbe(self.root, tam=162, bg=FONDO)
        self.orbe.widget().pack(pady=(6, 2))

        self.lbl_estado = tk.Label(self.root, text="Sistemas en línea",
                                   bg=FONDO, fg=GRIS, font=FUENTE)
        self.lbl_estado.pack(pady=(0, 2))

        # ── Grid de botones — 4 columnas, sin ancho fijo ──────────────────
        marco = tk.Frame(self.root, bg=FONDO)
        marco.pack(fill="x", padx=10, pady=(2, 2))
        self.botones = {}
        definiciones = [
            ("sistema",   "Sistema",     self._t_sistema),
            ("mic",       "Micrófono",   self._t_mic),
            ("trading",   "Trading",     self._t_trading),
            ("click",     "Auto-click",  self._t_click),
            ("consejos",  "Consejos",    self._t_consejos),
            ("claude",    "Claude ✦",    self._t_claude),
            ("ollama",    "Ollama",      self._t_ollama),
            ("practica",  "Practica",    self._t_practica),
        ]
        # DOS columnas, no cuatro.
        #
        # La ventana mide 368 px. Con cuatro columnas cada botón se queda en
        # ~82 px, y «Auto-click» necesita unos 74 más el relleno interno:
        # se cortaba. Se veía en pantalla y ninguna prueba lo detectaba,
        # porque el código era correcto — solo que no cabía.
        #
        # Con dos columnas cada botón tiene ~160 px: entran todas las
        # etiquetas enteras, con su indicador de estado y sin apreturas.
        # Son cuatro filas en vez de dos, y se lee mucho mejor.
        COLS = 2
        for i, (clave, nombre, cmd) in enumerate(definiciones):
            b = tk.Button(marco, text=nombre, command=cmd,
                          bg=PANEL, fg=TEXTO, font=FUENTE, relief="flat",
                          activebackground=ACENTO, activeforeground=FONDO,
                          cursor="hand2", pady=5, anchor="w", padx=8)
            b.grid(row=i // COLS, column=i % COLS, padx=2, pady=2, sticky="ew")
            self.botones[clave] = b
        for col in range(COLS):
            marco.columnconfigure(col, weight=1, uniform="tog")

        # ── Banner de Modo Práctica DEMO (oculto por defecto) ─────────────────
        self._banner_practica = tk.Label(
            self.root,
            text="",
            bg=FONDO, fg=FONDO,
            font=("Segoe UI", 8, "bold"))
        self._banner_practica.pack(fill="x", padx=10)

        # ── Banner de Modo Profesional (oculto por defecto) ────────────────────
        self._banner_pro = tk.Label(
            self.root,
            text="",
            bg=FONDO, fg=FONDO,
            font=("Segoe UI", 8, "bold"))
        self._banner_pro.pack(fill="x", padx=10)

        # ── Banner Meta Diaria (oculto por defecto) ──────────────────────────
        self._banner_meta = tk.Label(
            self.root,
            text="",
            bg=FONDO, fg=FONDO,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2")
        self._banner_meta.pack(fill="x", padx=10)
        self._banner_meta.bind("<Button-1>", lambda _: self.abrir_meta())

        # ── Banner de señal activa — dirección + votos + urgencia ────────────
        self._banner_senal = tk.Label(
            self.root,
            text="",
            bg=FONDO, fg=FONDO,
            font=("Segoe UI", 10, "bold"),
            pady=2)
        self._banner_senal.pack(fill="x", padx=6)

        # ── Banner tipo de cuenta (DEMO / REAL) — oculto hasta que el usuario lo indique ──
        self._banner_cuenta = tk.Label(
            self.root,
            text="",
            bg=FONDO, fg=FONDO,
            font=("Segoe UI", 8, "bold"))
        self._banner_cuenta.pack(fill="x", padx=10)

        # ── Barra de Override de Conciencia — siempre visible ─────────────────
        # Permite al usuario controlar si Litch opera o se abstiene sin
        # tener que abrir el panel de conciencia completo.
        # DOS FILAS, no una.
        #
        # Todo esto iba en una sola línea: etiqueta, estado, tres botones,
        # separador, «Visión» y su LED. Sumaban más ancho del que tiene la
        # ventana (368 px) y los últimos elementos quedaban fuera.
        # Ahora los controles van arriba y los indicadores debajo.
        _ovr_cont = tk.Frame(self.root, bg="#070d17", pady=3)
        _ovr_cont.pack(fill="x", padx=8, pady=(2, 0))

        _ovr_f = tk.Frame(_ovr_cont, bg="#070d17")
        _ovr_f.pack(fill="x")

        # Segunda fila, para los indicadores
        self._ovr_f2 = tk.Frame(_ovr_cont, bg="#070d17")
        self._ovr_f2.pack(fill="x", pady=(3, 0))

        tk.Label(_ovr_f, text="Conciencia:", bg="#070d17", fg=GRIS,
                 font=("Segoe UI", 7)).pack(side="left", padx=(4, 0))

        self._ovr_lbl = tk.Label(_ovr_f, text="Auto",
                                  bg="#070d17", fg=ACENTO,
                                  font=("Segoe UI", 7, "bold"))
        self._ovr_lbl.pack(side="left", padx=(4, 6))

        # Botón Auto
        tk.Button(_ovr_f, text="🔄 Auto",
                  bg=PANEL, fg=ACENTO, font=("Segoe UI", 7),
                  relief="flat", cursor="hand2", padx=4,
                  command=lambda: self._set_ovr("auto")
                  ).pack(side="left", padx=1)
        # Botón Forzar operar
        tk.Button(_ovr_f, text="▶ Operar",
                  bg=PANEL, fg="#00e676", font=("Segoe UI", 7),
                  relief="flat", cursor="hand2", padx=4,
                  command=lambda: self._set_ovr("forzar_actuar")
                  ).pack(side="left", padx=1)
        # Botón Forzar abstención
        tk.Button(_ovr_f, text="⏸ Pausar",
                  bg=PANEL, fg="#ff7043", font=("Segoe UI", 7),
                  relief="flat", cursor="hand2", padx=4,
                  command=lambda: self._set_ovr("forzar_abstener")
                  ).pack(side="left", padx=1)

        # ── Segunda fila: indicadores (visión y broker aprendido) ──────────
        _f2 = self._ovr_f2

        tk.Label(_f2, text="Visión:", bg="#070d17", fg=GRIS,
                 font=("Segoe UI", 7)).pack(side="left", padx=(4, 0))
        self._vision_led = tk.Label(_f2, text="●",
                                     bg="#070d17", fg=GRIS,
                                     font=("Segoe UI", 8, "bold"))
        self._vision_led.pack(side="left", padx=2)
        self._vision_txt = tk.Label(_f2, text="—",
                                     bg="#070d17", fg=GRIS,
                                     font=("Segoe UI", 7))
        self._vision_txt.pack(side="left")

        tk.Label(_f2, text="│", bg="#070d17", fg="#1a2a3a",
                 font=("Segoe UI", 7)).pack(side="left", padx=5)

        # Indicador del broker que LITCH está aprendiendo, con su color:
        # gris = sin empezar · naranja = aprendiendo · azul = lo domina.
        # Es el mismo estado que el botón 🧠 de la barra de herramientas.
        tk.Label(_f2, text="Broker:", bg="#070d17", fg=GRIS,
                 font=("Segoe UI", 7)).pack(side="left")
        self._brk_led = tk.Label(_f2, text="●", bg="#070d17", fg=GRIS,
                                 font=("Segoe UI", 8, "bold"))
        self._brk_led.pack(side="left", padx=2)
        self._brk_txt = tk.Label(_f2, text="—", bg="#070d17", fg=GRIS,
                                 font=("Segoe UI", 7))
        self._brk_txt.pack(side="left")

        # ── Sección pie (nav) — se ancla al FONDO antes del log ─────────────
        # Empaquetar primero con side="bottom" garantiza que nunca se corte
        self._seccion_pie = tk.Frame(self.root, bg=FONDO)
        pie = self._seccion_pie
        pie.pack(side="bottom", fill="x", pady=(0, 4), padx=6)

        # Línea divisora
        tk.Frame(pie, bg="#1a2a3a", height=1).pack(fill="x", pady=(3, 3))

        # ── Nav 4 columnas (4 filas para 13 items → todo visible) ────────────
        nav = tk.Frame(pie, bg=FONDO)
        nav.pack(fill="x")
        _NAV_COLS = 4
        nav_items = [
            ("💬 Chat",       self.abrir_chat,          ACENTO),
            ("🎰 Lotería",    self.abrir_loteria,        ACENTO),
            ("🎯 Avanzado",   self.abrir_calibracion,   ACENTO),
            ("📊 Broker",     self.abrir_broker,         ACENTO),
            ("📚 Libros",     self.abrir_libros,         ACENTO),
            ("🧠 Conciencia", self.abrir_conciencia,    "#a8f"),
            ("🔐 Llave",      self.abrir_seguridad,     ACENTO),
            ("☁  Nube",       self.abrir_nube,           ACENTO),
            ("📧 Correo",     self.abrir_correo_ia,     ACENTO),
            ("📷 Cámara",     self.abrir_camara,         ACENTO),
            ("🏆 Pro",        self.abrir_profesional,   "#ffd700"),
            ("🎯 Meta",       self.abrir_meta,          "#00e5ff"),
            ("◆ Fable 5",    self._dialogo_api_key,    "#00d4ff"),
            ("📈 Velas",     self.abrir_grafico_velas, "#2ecc71"),
            ("🏦 IBKR",      self.abrir_ibkr_panel,    "#1a73e8"),
            # Todo lo construido últimamente vivía solo como comandos de
            # voz. Funcionaba, pero era invisible: el señor no tenía forma
            # de saber que existía. Una función que hay que adivinar es
            # una función que no está.
            ("⚙ Ajustes",   self.abrir_panel_ajustes, "#ff9500"),
        ]
        for i, (txt, cmd, fg) in enumerate(nav_items):
            tk.Button(nav, text=txt, command=cmd,
                      bg=PANEL, fg=fg,
                      font=("Segoe UI", 8), relief="flat",
                      cursor="hand2", pady=4,
                      activebackground="#1a2f40",
                      activeforeground=fg).grid(
                row=i // _NAV_COLS, column=i % _NAV_COLS,
                padx=2, pady=2, sticky="ew")
        # Botón idioma ocupa la última celda disponible
        self._btn_idioma = tk.Button(
            nav, text="🌐 ES", command=self._t_idioma,
            bg=PANEL, fg=GRIS, font=("Segoe UI", 8),
            relief="flat", cursor="hand2", pady=4,
            activebackground="#1a2f40", activeforeground=GRIS)
        _last_row = len(nav_items) // _NAV_COLS
        _last_col = len(nav_items) % _NAV_COLS
        self._btn_idioma.grid(row=_last_row, column=_last_col,
                              padx=2, pady=2, sticky="ew")
        for col in range(_NAV_COLS):
            nav.columnconfigure(col, weight=1, uniform="nav")

        # ── Sección expandible (gauge + log) — ocupa espacio sobrante ────────
        self._frame_expandible = tk.Frame(self.root, bg=FONDO)
        self._frame_expandible.pack(fill="both", expand=True)

        # ── Gauge circular ─────────────────────────────────────────────────
        gauge_frame = tk.Frame(self._frame_expandible, bg=FONDO)
        gauge_frame.pack(pady=(4, 0), anchor="w", padx=10)

        self._gauge_canvas = tk.Canvas(
            gauge_frame, width=80, height=80,
            bg=FONDO, highlightthickness=0)
        self._gauge_canvas.pack(side="left", padx=(0, 6))

        gauge_info = tk.Frame(gauge_frame, bg=FONDO)
        gauge_info.pack(side="left", anchor="w")
        self._lbl_gauge_pct  = tk.Label(
            gauge_info, text="— %", bg=FONDO, fg=ACENTO,
            font=("Segoe UI", 14, "bold"))
        self._lbl_gauge_pct.pack(anchor="w")
        self._lbl_gauge_sub  = tk.Label(
            gauge_info, text="Red Maestra", bg=FONDO, fg=GRIS,
            font=("Segoe UI", 7))
        self._lbl_gauge_sub.pack(anchor="w")
        self._lbl_gauge_tend = tk.Label(
            gauge_info, text="sin datos", bg=FONDO, fg=GRIS,
            font=("Segoe UI", 7))
        self._lbl_gauge_tend.pack(anchor="w")

        self._dibujar_gauge(50.0)
        self.root.after(5000,  self._actualizar_gauge_loop)
        self.root.after(500,   self._loop_mic_status)
        self.root.after(15000, self._loop_banners_autonomia)
        # Compactar ya, sin esperar 15 s: si no, el hueco de los banners
        # vacíos se ve durante los primeros quince segundos de cada sesión.
        self.root.after(400,   self._compactar_banners)
        # Y otra vez al segundo, por si algún banner se rellenó al arrancar
        self.root.after(1200,  self._compactar_banners)

        # ── Arrancar en modo RIBBON por defecto (ventana grande oculta) ──────
        # El usuario puede expandir con el botón ⊡ del ribbon
        self.root.after(200, self._activar_barra)

        # ══════════════════════════════════════════════════════════════════
        # PANEL DE CONTROL MANUAL — Monto · Vencimiento · Gráfico · Toggles
        # ══════════════════════════════════════════════════════════════════
        _CP_BG   = "#060f1a"
        _CP_BG2  = "#091523"
        _CP_SEP  = "#0e1e30"
        _CP_FONT = ("Segoe UI", 8, "bold")
        _CP_FONS = ("Segoe UI", 7)

        _ctrl_outer = tk.Frame(self._frame_expandible, bg=_CP_BG,
                               bd=1, relief="flat")
        _ctrl_outer.pack(fill="x", padx=8, pady=(4, 0))

        # ── Fila A: Monto de inversión ────────────────────────────────────
        _fa = tk.Frame(_ctrl_outer, bg=_CP_BG)
        _fa.pack(fill="x", padx=6, pady=(5, 2))

        tk.Label(_fa, text="INVERSIÓN", bg=_CP_BG, fg="#4a7a9b",
                 font=("Segoe UI", 6, "bold")).pack(side="left", padx=(0, 5))

        # Botones de monto rápido
        _monto_presets = (5, 10, 25, 50, 100)
        _cfg_monto_init = int(self.app.mem["config"].get("monto_base", 10))
        self._qmonto_var = tk.StringVar(value=str(_cfg_monto_init))
        for _m in _monto_presets:
            _is_active = (_m == _cfg_monto_init)
            _mb = tk.Button(_fa, text=f"${_m}",
                            bg="#0f2236" if _is_active else PANEL,
                            fg=VERDE if _is_active else GRIS,
                            font=("Consolas", 7, "bold") if _is_active
                                 else ("Consolas", 7),
                            relief="flat", padx=4, pady=1, cursor="hand2",
                            command=lambda x=_m: (
                                self._qmonto_var.set(str(x)),
                                self._qmonto_e.config(fg=VERDE),
                                self._cp_aplicar_config()))
            _mb.pack(side="left", padx=1)

        tk.Label(_fa, text="$", bg=_CP_BG, fg=VERDE,
                 font=_CP_FONT).pack(side="left", padx=(8, 1))
        self._qmonto_e = tk.Entry(_fa, textvariable=self._qmonto_var,
                                  width=6, bg="#0a1e30", fg=VERDE,
                                  font=("Consolas", 9, "bold"),
                                  relief="flat", insertbackground=VERDE,
                                  justify="center", highlightthickness=1,
                                  highlightcolor=VERDE,
                                  highlightbackground="#1a3a5a")
        self._qmonto_e.pack(side="left", padx=(0, 4), ipady=3)
        self._qmonto_e.bind("<Return>", lambda e: self._cp_aplicar_config())

        # +/- botones de monto
        def _monto_step(delta):
            try:
                v = float(self._qmonto_var.get()) + delta
                if v < 1: v = 1.0
                self._qmonto_var.set(str(int(v)) if v == int(v) else f"{v:.1f}")
                self._cp_aplicar_config()
            except Exception:
                pass
        tk.Button(_fa, text="−", bg=PANEL, fg=ROJO,
                  font=_CP_FONT, relief="flat", padx=4, pady=0,
                  cursor="hand2",
                  command=lambda: _monto_step(-5)).pack(side="left")
        tk.Button(_fa, text="+", bg=PANEL, fg=VERDE,
                  font=_CP_FONT, relief="flat", padx=4, pady=0,
                  cursor="hand2",
                  command=lambda: _monto_step(+5)).pack(side="left")

        # ── Separador vertical ─────────────────────────────────────────────
        tk.Label(_fa, text="│", bg=_CP_BG, fg=_CP_SEP,
                 font=("Segoe UI", 11)).pack(side="left", padx=6)

        # ── Vencimiento (tiempo de cierre del trade) ───────────────────────
        tk.Label(_fa, text="CIERRE", bg=_CP_BG, fg="#4a7a9b",
                 font=("Segoe UI", 6, "bold")).pack(side="left", padx=(0, 5))

        _venc_presets = (
            (30, "30s"), (60, "1m"), (120, "2m"),
            (300, "5m"), (600, "10m"), (900, "15m"),
        )
        _cfg_venc_init = int(self.app.mem["config"].get("vencimiento",
                              self.app.mem["config"].get("periodo_vela", 60)))
        self._qvenc_var = tk.StringVar(value=str(_cfg_venc_init))
        for _v_seg, _v_lbl in _venc_presets:
            _is_act_v = (_v_seg == _cfg_venc_init)
            _vb = tk.Button(_fa, text=_v_lbl,
                            bg="#0f2236" if _is_act_v else PANEL,
                            fg=ACENTO if _is_act_v else GRIS,
                            font=("Consolas", 7, "bold") if _is_act_v
                                 else ("Consolas", 7),
                            relief="flat", padx=4, pady=1, cursor="hand2",
                            command=lambda x=_v_seg: (
                                self._qvenc_var.set(str(x)),
                                self._cp_aplicar_config()))
            _vb.pack(side="left", padx=1)

        tk.Label(_fa, text="⏳", bg=_CP_BG, fg=ACENTO,
                 font=("Segoe UI", 9)).pack(side="left", padx=(6, 1))
        self._qvenc_e = tk.Entry(_fa, textvariable=self._qvenc_var,
                                 width=5, bg="#0a1e30", fg=ACENTO,
                                 font=("Consolas", 9, "bold"),
                                 relief="flat", insertbackground=ACENTO,
                                 justify="center", highlightthickness=1,
                                 highlightcolor=ACENTO,
                                 highlightbackground="#1a3a5a")
        self._qvenc_e.pack(side="left", padx=(0, 2), ipady=3)
        tk.Label(_fa, text="s", bg=_CP_BG, fg="#4a7a9b",
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 4))
        self._qvenc_e.bind("<Return>", lambda e: self._cp_aplicar_config())

        # ── Fila B: Botones del gráfico + Período de análisis ─────────────
        _fb = tk.Frame(_ctrl_outer, bg=_CP_BG2)
        _fb.pack(fill="x", padx=6, pady=(1, 2))

        tk.Label(_fb, text="GRÁFICO", bg=_CP_BG2, fg="#4a7a9b",
                 font=("Segoe UI", 6, "bold")).pack(side="left", padx=(0, 4))

        def _chart_btn(symbol, tooltip, cmd):
            b = tk.Button(_fb, text=symbol, bg="#0d2035", fg=ACENTO,
                          font=("Consolas", 9, "bold"), relief="flat",
                          padx=6, pady=0, cursor="hand2", command=cmd,
                          activebackground="#1a3a5a", activeforeground="#ffffff")
            b.pack(side="left", padx=1)
            _tip(b, tooltip,
                 f"Controla el zoom del gráfico en IQ Option.\n{tooltip}")
            return b

        def _do_centrar():
            try:
                _gc = getattr(self.app, "gestor_grafico", None)
                if _gc:
                    _gc.centrar_para_fable()
                else:
                    from . import chart_controls as _cc
                    cfg = self.app.mem.get("config", {})
                    _cc.centrar(cfg.get("region_grafico"), cfg)
            except Exception:
                pass
        def _do_zoom_out():
            try:
                from . import chart_controls as _cc
                cfg = self.app.mem.get("config", {})
                _cc.zoom_out(cfg.get("region_grafico"), cfg)
            except Exception:
                pass
        def _do_zoom_in():
            try:
                from . import chart_controls as _cc
                cfg = self.app.mem.get("config", {})
                _cc.zoom_in(cfg.get("region_grafico"), cfg)
            except Exception:
                pass
        def _do_zoom_opt():
            try:
                from . import chart_controls as _cc
                cfg = self.app.mem.get("config", {})
                per = int(cfg.get("periodo_vela", 60))
                _cc.zoom_optimo(cfg.get("region_grafico"), cfg, per)
            except Exception:
                pass

        _chart_btn("−", "Zoom out — ver más velas (panorámica)", _do_zoom_out)
        _chart_btn("⊙", "Centrar gráfico — ajuste automático",    _do_centrar)
        _chart_btn("+", "Zoom in — ver más detalle",              _do_zoom_in)
        _chart_btn("⊞", "Zoom óptimo automático según período",   _do_zoom_opt)

        tk.Label(_fb, text="│", bg=_CP_BG2, fg=_CP_SEP,
                 font=("Segoe UI", 11)).pack(side="left", padx=5)

        tk.Label(_fb, text="ANÁLISIS", bg=_CP_BG2, fg="#4a7a9b",
                 font=("Segoe UI", 6, "bold")).pack(side="left", padx=(0, 4))
        _dur_presets = ((10, "10s"), (30, "30s"), (60, "1m"), (120, "2m"), (300, "5m"))
        _cfg_dur_init = int(self.app.mem["config"].get("periodo_vela", 60))
        self._qdur_var = tk.StringVar(value=str(_cfg_dur_init))
        for _dp, _dl in _dur_presets:
            _is_act_d = (_dp == _cfg_dur_init)
            tk.Button(_fb, text=_dl,
                      bg="#0f2236" if _is_act_d else PANEL,
                      fg="#f39c12" if _is_act_d else GRIS,
                      font=("Consolas", 7, "bold") if _is_act_d
                           else ("Consolas", 7),
                      relief="flat", padx=3, pady=1, cursor="hand2",
                      command=lambda x=_dp: (
                          self._qdur_var.set(str(x)),
                          self._cp_aplicar_config())).pack(side="left", padx=1)

        self._qdur_e = tk.Entry(_fb, textvariable=self._qdur_var,
                                width=5, bg="#0a1e30", fg="#f39c12",
                                font=("Consolas", 8, "bold"),
                                relief="flat", insertbackground="#f39c12",
                                justify="center", highlightthickness=1,
                                highlightcolor="#f39c12",
                                highlightbackground="#1a3a5a")
        self._qdur_e.pack(side="left", padx=(4, 1), ipady=2)
        tk.Label(_fb, text="s", bg=_CP_BG2, fg="#4a7a9b",
                 font=("Segoe UI", 7)).pack(side="left", padx=(0, 4))
        self._qdur_e.bind("<Return>", lambda e: self._cp_aplicar_config())

        # Checkbutton monto auto
        self._qauto_var = tk.BooleanVar(
            value=not bool(self.app.mem["config"].get("monto_modo_manual", False)))
        def _toggle_auto():
            auto = self._qauto_var.get()
            self.app.mem["config"]["monto_modo_manual"] = not auto
            memoria.guardar(self.app.mem)
            self.app.log(f"[Config] Monto {'automático (IA decide)' if auto else 'manual (fijo)'}")
        tk.Checkbutton(_fb, text="Monto auto", variable=self._qauto_var,
                       bg=_CP_BG2, fg=GRIS, selectcolor=PANEL,
                       activebackground=_CP_BG2, activeforeground=ACENTO,
                       font=("Segoe UI", 6), command=_toggle_auto
                       ).pack(side="right", padx=4)

        # ── Fila C: Grandes toggles de sistema ────────────────────────────
        _fc = tk.Frame(_ctrl_outer, bg="#050c16")
        _fc.pack(fill="x", padx=6, pady=(2, 5))

        tk.Label(_fc, text="ACTIVAR →", bg="#050c16", fg="#4a7a9b",
                 font=("Segoe UI", 6, "bold")).pack(side="left", padx=(0, 6))

        def _big_toggle(parent, text_off, text_on, get_state, toggle_cmd,
                        color_on=VERDE, color_off=GRIS, width=9):
            state = get_state()
            _var_state = [state]
            _btn_ref = [None]
            def _update():
                s = get_state()
                _var_state[0] = s
                if _btn_ref[0]:
                    _btn_ref[0].config(
                        text=text_on if s else text_off,
                        bg="#0a2a12" if s else "#1a1a1a",
                        fg=color_on if s else color_off,
                        relief="groove" if s else "flat")
            def _click():
                toggle_cmd()
                parent.after(200, _update)
            btn = tk.Button(parent,
                            text=text_on if state else text_off,
                            bg="#0a2a12" if state else "#1a1a1a",
                            fg=color_on if state else color_off,
                            font=("Consolas", 7, "bold"),
                            relief="groove" if state else "flat",
                            padx=4, pady=2, cursor="hand2", width=width,
                            activebackground="#1a3a20",
                            command=_click)
            btn.pack(side="left", padx=2)
            _btn_ref[0] = btn
            # Guardar referencia para refrescos externos
            return btn, _update

        self._cp_btn_sis, self._cp_upd_sis = _big_toggle(
            _fc,
            "○ SISTEMA", "● SISTEMA",
            lambda: self.app.activo,
            lambda: self._en_hilo(self.app.set_activo, not self.app.activo, True),
            color_on=VERDE)

        self._cp_btn_trd, self._cp_upd_trd = _big_toggle(
            _fc,
            "○ TRADING", "● TRADING",
            lambda: self.app.trading_on,
            lambda: self._en_hilo(self.app.set_trading, not self.app.trading_on, True),
            color_on="#00e676")

        self._cp_btn_auto, self._cp_upd_auto = _big_toggle(
            _fc,
            "○ AUTO-CLICK", "● AUTO-CLICK",
            lambda: self.app.autoclick_on,
            lambda: self._en_hilo(self.app.set_autoclick, not self.app.autoclick_on, True),
            color_on=ACENTO, width=11)

        self._cp_btn_prac, self._cp_upd_prac = _big_toggle(
            _fc,
            "○ PRÁCTICA", "● PRÁCTICA",
            lambda: getattr(self.app, "modo_practica", False),
            self._t_practica,
            color_on="#f39c12", width=10)

        # Label de estado compacto (monto + vencimiento actuales)
        self._cp_lbl_estado = tk.Label(
            _fc, text="", bg="#050c16", fg="#4a7a9b",
            font=("Consolas", 6), anchor="e")
        self._cp_lbl_estado.pack(side="right", padx=6)
        self.root.after(1000, self._cp_loop_estado)

        # ── Barra de estado en tiempo real (qué está haciendo Litch ahora) ──
        self._lbl_status_rt = tk.Label(
            self._frame_expandible,
            text="⏸ Sistema OFF — activa SISTEMA para comenzar",
            bg="#050f18", fg=GRIS,
            font=("Consolas", 7), anchor="w", pady=2)
        self._lbl_status_rt.pack(fill="x", padx=10, pady=(3, 0))
        self.root.after(800, self._loop_status_rt)

        # ── Log de actividad — se expande con la ventana ──────────────────
        self._lbl_actividad = tk.Label(self._frame_expandible, text="Actividad",
                                       bg=FONDO, fg=ACENTO, font=FUENTE)
        self._lbl_actividad.pack(anchor="w", padx=12, pady=(2, 0))
        # Contenedor con alto MÍNIMO garantizado.
        #
        # Con `expand=True` a secas, si no sobra espacio pack encoge el
        # registro hasta cero y desaparece sin avisar. Metiéndolo en un
        # marco con altura mínima y `pack_propagate(False)`, el registro
        # nunca puede quedarse en nada: si falta sitio, lo cede otro.
        _caja_cont = tk.Frame(self._frame_expandible, bg=FONDO, height=96)
        _caja_cont.pack(fill="both", expand=True, padx=10, pady=(2, 6))
        _caja_cont.pack_propagate(False)

        self.caja_log = scrolledtext.ScrolledText(
            _caja_cont, height=5, bg=PANEL, fg=TEXTO,
            font=("Consolas", 8), relief="flat", state="disabled", wrap="word")
        self.caja_log.pack(fill="both", expand=True)

        self.actualizar()

    # --- override de conciencia (barra siempre visible) ----------------------
    def _set_ovr(self, modo: str):
        """Aplica override de conciencia desde la barra del panel principal."""
        def _apply():
            try:
                con = getattr(self.app, "conciencia", None)
                if con is None:
                    from core import conciencia as _cm
                    con = _cm.obtener(self.app)
                con.set_override(modo)
                self.app.log(f"[Conciencia] Override → {modo}")
                voz = {
                    "auto":            self.app.txt(
                        "Conciencia en modo automático.", "Conscience back to auto."),
                    "forzar_actuar":   self.app.txt(
                        "Operaciones forzadas. Litch ejecutará todas las señales.",
                        "Forced trading. Litch will execute every signal."),
                    "forzar_abstener": self.app.txt(
                        "Abstención forzada. Litch no abrirá operaciones.",
                        "Forced abstention. Litch will not open any trades."),
                }.get(modo, "")
                if voz:
                    self.app.voz.decir(voz, self.app.idioma)
            except Exception as e:
                self.app.log(f"[Conciencia] Error aplicando override: {e}")
            try:
                self.root.after(0, self._sincronizar_ovr_lbl)
            except Exception:
                pass
        self._en_hilo(_apply)

    def _sincronizar_ovr_lbl(self):
        """Actualiza la etiqueta de modo en la barra de override (hilo tkinter)."""
        try:
            con = getattr(self.app, "conciencia", None)
            modo = con.estado_override() if con else "auto"
            textos = {
                "auto":            ("🔄 Auto",       ACENTO),
                "forzar_actuar":   ("▶ Operando",    "#00e676"),
                "forzar_abstener": ("⏸ Pausada",     "#ff7043"),
            }
            txt, col = textos.get(modo, ("🔄 Auto", ACENTO))
            self._ovr_lbl.config(text=txt, fg=col)
        except Exception:
            pass

    def _actualizar_vision_led(self, estado_vision: str):
        """Actualiza el LED de visión activa (hilo tkinter)."""
        _MAP = {
            "viendo":      ("#00e676", "Viendo"),
            "buscando":    ("#ffee58", "Buscando..."),
            "sin_grafico": ("#ef5350", "Sin gráfico"),
            "inactivo":    (GRIS,      "—"),
        }
        col, lbl = _MAP.get(estado_vision, (GRIS, "—"))
        try:
            self._vision_led.config(fg=col)
            self._vision_txt.config(text=lbl, fg=col)
        except Exception:
            pass
        # También actualizar el LED en la barra de tareas si está activa
        try:
            if getattr(self, "_barra_win", None) and self._barra_win.winfo_exists():
                self._barra_vision_led.config(fg=col)
        except Exception:
            pass

        # De paso, el indicador de broker aprendido (mismo ciclo, sin
        # crear otro temporizador). Se recalcula cada pocos segundos.
        self._actualizar_led_broker()

    _COL_BRK = {"gris": GRIS, "naranja": "#f39c12", "azul": "#2196f3"}

    def _actualizar_led_broker(self):
        """LED del broker que LITCH está aprendiendo, con su progreso."""
        led = getattr(self, "_brk_led", None)
        if led is None:
            return
        try:
            if not led.winfo_exists():
                return
        except Exception:
            return

        # Solo cada 15 refrescos: detectar la ventana cuesta, y este dato
        # cambia despacio. Sin esto, se enumeraría la lista de ventanas
        # varias veces por segundo para nada.
        n = getattr(self, "_brk_tick", 0)
        self._brk_tick = n + 1
        if n % 15 != 0:
            return

        try:
            from . import aprendizaje_broker as ab
            col = self._COL_BRK.get(ab.color(self.app), GRIS)
            p = ab.progreso(self.app)
            nom = getattr(ab.obtener(self.app), "nombre_broker", "") or "—"
            txt = (f"{nom[:14]} {p['pct']:.0f}%" if p["total"] else nom[:14])
            led.config(fg=col)
            self._brk_txt.config(text=txt, fg=col)
            # Y de paso repintar el botón 🧠 de la barra si existe
            self._pintar_aprendizaje()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # ─── MODO BARRA DE TAREAS ──────────────────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════════════

    def _activar_barra(self):
        """Contrae Litch a una barra de tareas en el borde inferior de pantalla."""
        if getattr(self, "_barra_win", None) and self._barra_win.winfo_exists():
            return
        self._construir_barra()
        self.root.withdraw()

    def _construir_barra(self):
        """
        Ribbon profesional de 2 filas estilo Microsoft Word.

        Fila 1 (28px): Señal activa con colores prominentes
        Fila 2 (28px): Controles + herramientas agrupadas

        Total: 56px — máxima visibilidad del gráfico.
        """
        # ── Posición acoplable: arriba / abajo / izquierda / derecha ──────
        dock = self.app.mem["config"].get("barra_dock", "arriba")
        if dock in ("izquierda", "derecha"):
            self._construir_barra_vertical(dock)
            return

        # ── EN QUÉ MONITOR NACE LA BARRA ────────────────────────────────
        #
        # Antes se usaba `winfo_screenwidth()`, que devuelve el monitor
        # PRINCIPAL y solo ese. Con dos pantallas, la barra nacía siempre
        # en la primera aunque el señor estuviera trabajando en la
        # segunda, y no había forma de moverla.
        #
        # Ahora se pregunta cuál toca. Y es un ajuste aparte del de la
        # visión: el señor puede querer la barra en el monitor 1 mientras
        # Litch mira el 2 — de hecho es lo más cómodo, así la barra no
        # tapa el gráfico.
        _ox, _oy = 0, 0
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        try:
            from . import monitores as _mon
            _n = self.app.mem.get("config", {}).get("monitor_barra")
            _ms = _mon.listar()
            _m = next((m for m in _ms if m["n"] == int(_n)), None) if _n else None
            if _m is None:
                _m = next((m for m in _ms if m["principal"]), _ms[0])
            _ox, _oy, sw, sh = _m["x"], _m["y"], _m["w"], _m["h"]
        except Exception:
            pass

        _BG   = "#050d18"    # fondo casi negro
        _BG2  = "#091523"    # fondo filas pares
        _SEP  = "#1a2a3a"    # separadores verticales
        _FONT = ("Segoe UI", 8)
        _FONB = ("Segoe UI", 8, "bold")
        _FONS = ("Segoe UI", 7)

        v = tk.Toplevel(self.root)
        v.overrideredirect(True)
        v.attributes("-topmost", True)
        v.attributes("-alpha", 0.93)
        # Altura total de la ventana de la barra.
        #
        # AQUÍ ESTABA EL FALLO: valía 76 px, pero el contenido necesita
        #     28 (fila de título) + 1 (separador) + 68 (cinta) = 97 px
        # así que la segunda fila de la cinta quedaba fuera de la ventana
        # y parecía que el apilado en dos filas no funcionaba. Funcionaba:
        # simplemente no había sitio para verlo.
        #
        # 104 deja margen para la barra de desplazamiento cuando aparece.
        # Es aproximadamente lo que mide la cinta de Word.
        _BARRA_H = 104
        if dock == "abajo":
            # Justo encima de la barra de tareas de Windows (~48px)
            v.geometry(f"{sw}x{_BARRA_H}+{_ox}+{_oy + sh - _BARRA_H - 48}")
        else:
            v.geometry(f"{sw}x{_BARRA_H}+{_ox}+{_oy}")
        v.configure(bg=_BG)
        self._barra_win = v

        # ══════════════════════════════════════════════════════════════════
        # FILA 1 — Señal activa (toda la fila cambia de color con la señal)
        # ══════════════════════════════════════════════════════════════════
        fila1 = tk.Frame(v, bg=_BG, height=28)
        fila1.pack(fill="x")
        fila1.pack_propagate(False)

        # ◉ Logo / botón expandir
        _btn_logo = tk.Button(fila1, text="◉ LITCH", bg=_BG, fg=ACENTO,
                              font=_FONB, relief="flat", cursor="hand2", padx=8,
                              command=self._expandir_barra)
        _btn_logo.pack(side="left")
        _tip(_btn_logo, "LITCH — Expandir ventana",
             "Abre la ventana principal completa con el orbe de estado, "
             "el panel de estadísticas, el historial de trades y todos "
             "los controles avanzados. El ribbon seguirá visible arriba.")

        tk.Label(fila1, text="│", bg=_BG, fg=_SEP,
                 font=("Segoe UI", 13)).pack(side="left")

        # Señal grande (cambia color y texto con cada señal)
        self._barra_senal = tk.Label(
            fila1, text="  LITCH  ◌◌◌  Analizando...",
            bg=_BG, fg=ACENTO,
            font=("Consolas", 9, "bold"),
            anchor="w")
        self._barra_senal.pack(side="left", fill="x", expand=True, padx=4)
        _tip(self._barra_senal, "Señal activa en tiempo real",
             "Muestra la dirección de la señal más reciente del motor de 9 algoritmos. "
             "Verde = señal de SUBE (CALL). Rojo = señal de BAJA (PUT). "
             "Amarillo parpadeante = señal urgente, actúa en los próximos segundos. "
             "El contador regresivo indica cuánto tiempo falta para que cierre la vela.")

        # Indicador de votos gráfico (●●●●●●●●●)
        self._barra_votos = tk.Label(
            fila1, text="",
            bg=_BG, fg=GRIS,
            font=("Segoe UI", 8))
        self._barra_votos.pack(side="left", padx=4)
        _tip(self._barra_votos, "Votos del consenso (9 algoritmos)",
             "Cada ● representa un algoritmo que confirmó la señal. "
             "Más puntos llenos = más consenso = mayor confianza. "
             "Los 9 métodos son: Markov, Estadística, Red Maestra (CNN+LSTM+MLP), "
             "Pronóstico, Indicadores Técnicos, RL-DQN, SMC/LWS, "
             "Patrones de Velas Japonesas y Soporte/Resistencia automático.")

        # WR en tiempo real
        self._barra_wr = tk.Label(
            fila1, text="WR —%", bg=_BG, fg=GRIS,
            font=_FONB)
        self._barra_wr.pack(side="left", padx=(0, 4))
        _tip(self._barra_wr, "Win Rate — Precisión de los últimos 50 trades",
             "Porcentaje de trades ganados en las últimas 50 operaciones. "
             "Verde ≥ 60% (rentable). Naranja 50-60% (zona de breakeven). "
             "Rojo < 50% (revisar estrategia). "
             "LITCH necesita al menos 60% para ser consistentemente rentable.")

        tk.Label(fila1, text="│", bg=_BG, fg=_SEP,
                 font=("Segoe UI", 13)).pack(side="left")

        # Visión LED
        self._barra_vision_led = tk.Label(
            fila1, text="●", bg=_BG, fg=GRIS,
            font=("Segoe UI", 9, "bold"))
        self._barra_vision_led.pack(side="left", padx=(4, 2))
        self._barra_vision_txt = tk.Label(
            fila1, text="—", bg=_BG, fg=GRIS, font=_FONS)
        self._barra_vision_txt.pack(side="left", padx=(0, 4))
        _tip(self._barra_vision_led, "Estado de la visión de pantalla",
             "● Verde = LITCH está viendo correctamente el gráfico del broker. "
             "● Amarillo = Región no calibrada — ve a Calibrar (📐) para enseñarle dónde está el gráfico. "
             "● Rojo = LITCH no detecta colores — el gráfico puede estar oculto o la región es incorrecta.")
        _tip(self._barra_vision_txt, "Estado de la visión de pantalla",
             "Indica si LITCH está capturando el gráfico correctamente. "
             "Usa la herramienta 📐 Calibrar para ajustar la región si hay problemas.")

        # ══════════════════════════════════════════════════════════════════
        # CADENA DE OPERACIÓN — los cinco eslabones, de un vistazo
        # ══════════════════════════════════════════════════════════════════
        #
        # Para que LITCH opere en IQ Option tienen que cumplirse cinco
        # cosas a la vez. Si falta una sola, no pasa nada — y desde fuera
        # eso se ve igual que «está roto».
        #
        # Esa confusión ha costado sesiones enteras: el señor preguntando
        # «¿por qué no opera?» y LITCH callada porque le faltaba un
        # interruptor. Un indicador que hay que pedir no sirve; tiene que
        # estar delante.
        #
        #   S = Sistema activo      T = Trading activo
        #   A = Auto-clic           C = Botones calibrados
        #   M = Motor de binarias / botones alcanzables
        #
        # Verde = ese eslabón está bien. Rojo = ahí se rompe la cadena.
        tk.Label(fila1, text="│", bg=_BG, fg=_SEP,
                 font=_FONS).pack(side="left", padx=2)
        self._cadena_lbls = {}
        for _cl, _ayuda in (
            ("S", "SISTEMA — el interruptor maestro.\n\n"
                  "Rojo: LITCH está en espera y no analiza nada.\n"
                  "Se enciende con el botón «Sis» de la barra."),
            ("T", "TRADING — permiso para analizar y decidir.\n\n"
                  "Rojo: LITCH ve el gráfico pero no saca señales.\n"
                  "Se enciende con el botón «Trd»."),
            ("A", "AUTO-CLIC — permiso para mover el ratón.\n\n"
                  "Rojo: LITCH decide pero no ejecuta; solo avisa.\n"
                  "Se enciende con el botón «Auto».\n\n"
                  "Sin esto tampoco puede explorar Interactive Brokers."),
            ("C", "CALIBRACIÓN — sabe dónde están SUBE, BAJA y el gráfico.\n\n"
                  "Rojo: no tiene los botones localizados.\n"
                  "Diga «Litch calibra» con IQ Option en pantalla."),
            ("M", "MOTOR — puede llegar a los botones de IQ Option.\n\n"
                  "Rojo: los botones están tapados por otra ventana "
                  "(normalmente Trader Workstation), así que el clic no "
                  "llegaría a su destino.\n\n"
                  "Traiga IQ Option al frente, o diga «enciende el motor» "
                  "para forzarlo."),
        ):
            _l = tk.Label(fila1, text=_cl, bg=_BG, fg="#3a3a3a",
                          font=("Consolas", 8, "bold"))
            _l.pack(side="left", padx=1)
            _tip(_l, f"Cadena de operación — {_cl}", _ayuda,
                 "Los cinco tienen que estar verdes para operar")
            self._cadena_lbls[_cl] = _l

        # ✕ Cerrar Litch (guarda TODO antes de salir)
        _btn_cerrar_app = tk.Button(
            fila1, text="✕", bg=_BG, fg="#ef5350",
            font=_FONB, relief="flat", cursor="hand2", padx=6,
            command=self._cerrar_aplicacion)
        _btn_cerrar_app.pack(side="right")

        # ══════════════════════════════════════════════════════════════════
        # OCULTAR / MOSTRAR la barra — VA EN LA FILA 1, Y ES A PROPÓSITO
        # ══════════════════════════════════════════════════════════════════
        #
        # Antes este botón vivía en la fila 2, y era un «⌃» diminuto perdido
        # entre otros ocho iconos. Tenía un defecto que lo volvía inútil:
        # al plegar se oculta la fila 2 ENTERA, así que el botón se
        # escondía a sí mismo. Una vez plegada la barra no había forma
        # visible de devolverla — solo un doble clic que nadie podía
        # adivinar.
        #
        # La fila 1 es la única que sobrevive al plegado. Por eso el botón
        # tiene que estar aquí: para poder deshacer lo que hace.
        # ══════════════════════════════════════════════════════════════════
        # CAMBIAR DE MONITOR — un botón, un clic
        # ══════════════════════════════════════════════════════════════════
        #
        # Había comandos para mover la barra y para cambiar dónde mira,
        # por separado. Útil para afinar, engorroso para el día a día: el
        # señor solo quiere que Litch se vaya a la otra pantalla.
        #
        # Este botón hace las dos cosas de golpe y va rotando entre los
        # monitores conectados. Muestra en cuál está: «🖥 1/2».
        self._btn_monitor = tk.Button(
            fila1, text="🖥", command=self._cambiar_monitor,
            bg="#1a3a5a", fg="#00d4ff", font=("Segoe UI", 9, "bold"),
            relief="flat", cursor="hand2", padx=8, pady=1,
            bd=0, highlightthickness=0,
            activebackground="#245078", activeforeground="#00d4ff")
        self._btn_monitor.pack(side="right", padx=(4, 2))
        _tip(self._btn_monitor, "Cambiar de monitor",
             "Un clic y LITCH se pasa entera a la siguiente pantalla: la "
             "barra y la visión a la vez.\n\n"
             "El número dice en cuál está y cuántas hay. Va rotando: 1 → 2 "
             "→ 1…\n\n"
             "Se adapta al tamaño del monitor de destino, aunque sea "
             "distinto.",
             "Los monitores se detectan solos")

        self._btn_plegar = tk.Button(
            fila1, text="⌃ OCULTAR BARRA",
            command=self._plegar_ribbon,
            bg="#1a3a5a", fg="#00e676",
            font=("Segoe UI", 9, "bold"),
            relief="flat", cursor="hand2", padx=10, pady=1,
            bd=0, highlightthickness=0,
            activebackground="#245078", activeforeground="#00e676")
        self._btn_plegar.pack(side="right", padx=(6, 6))
        _tip(self._btn_plegar,
             "Ocultar / mostrar la barra de herramientas",
             "Esconde la fila de herramientas y deja solo esta línea de "
             "estado. Libera 76 píxeles de pantalla para el broker.\n\n"
             "El botón se queda siempre visible aquí, incluso con la barra "
             "oculta, para que siempre pueda devolverla.\n\n"
             "⌃ OCULTAR BARRA  →  la esconde\n"
             "⌄ MOSTRAR BARRA  →  la devuelve",
             "También: doble clic en esta línea de estado")
        _tip(_btn_cerrar_app, "Cerrar Litch — Guardado automático",
             "Guarda TODA la memoria y el aprendizaje (patrones, redes "
             "neuronales, estadísticas, lotería) y cierra Litch de forma "
             "ordenada. Nunca se queda colgado: si algo tarda más de 5 "
             "segundos, fuerza la salida igual con lo ya guardado.")

        # Hora y velas
        self._barra_hora = tk.Label(
            fila1, text="", bg=_BG, fg=GRIS, font=_FONS)
        self._barra_hora.pack(side="right", padx=8)
        _tip(self._barra_hora, "Hora UTC y sesión de mercado",
             "Hora en tiempo real (UTC). Las sesiones de mayor liquidez son:\n"
             "• Tokio:   00:00 – 09:00 UTC (menor volatilidad)\n"
             "• Londres: 07:00 – 16:00 UTC (alta volatilidad)\n"
             "• NY:      13:00 – 22:00 UTC (máxima volatilidad)\n"
             "Solapamiento Londres+NY (13:00-16:00 UTC) = mejores señales.")

        # ══════════════════════════════════════════════════════════════════
        # SEPARADOR entre filas (1px)
        # ══════════════════════════════════════════════════════════════════
        _sep_ribbon = tk.Frame(v, bg=_SEP, height=1)
        _sep_ribbon.pack(fill="x")

        # ══════════════════════════════════════════════════════════════════
        # FILA 2 — Controles + herramientas agrupadas
        # ══════════════════════════════════════════════════════════════════
        # La fila de herramientas va DENTRO de un lienzo desplazable.
        #
        # Antes era un Frame normal: todo lo que no cabía en el ancho de la
        # ventana simplemente se cortaba y no había forma de llegar a ello.
        # Con el grupo de Interactive Brokers añadido, los últimos botones
        # quedaban fuera de la pantalla.
        #
        # Ahora, si no cabe, se desplaza: con la rueda del ratón, con la
        # barra de abajo, o arrastrando. Nada se pierde nunca.
        _cont2 = tk.Frame(v, bg=_BG2)
        _cont2.pack(fill="x")

        # Altura al estilo Word: dos filas de iconos + el nombre del grupo
        # debajo. Con 47 px cabía una sola fila y el nombre quedaba cortado.
        _ALTO_RIBBON = 68
        _lienzo2 = tk.Canvas(_cont2, bg=_BG2, height=_ALTO_RIBBON,
                             highlightthickness=0, bd=0)
        _lienzo2.pack(side="top", fill="x")

        _scroll2 = tk.Scrollbar(_cont2, orient="horizontal",
                                command=_lienzo2.xview)
        # Al cerrar Litch, Tk destruye los widgets en un orden que no
        # controlamos. Si la barra de desplazamiento muere antes que el
        # lienzo, el lienzo sigue llamándola y Tk lanza:
        #     TclError: invalid command name ".!frame6...!scrollbar"
        #
        # No es un fallo de lógica — es la ventana desmontándose. Pero
        # aparece en pantalla como un error rojo justo cuando el señor
        # cierra el programa, y da la impresión de que algo se rompió.
        # Se envuelve para que el desmontaje sea silencioso.
        def _set_scroll_seguro(*args, _sb=_scroll2):
            try:
                if _sb.winfo_exists():
                    _sb.set(*args)
            except Exception:
                pass
        _lienzo2.configure(xscrollcommand=_scroll_seguro(_scroll2))

        fila2 = tk.Frame(_lienzo2, bg=_BG2, height=_ALTO_RIBBON)
        _ventana2 = _lienzo2.create_window((0, 0), window=fila2,
                                           anchor="nw")

        def _ajustar_scroll(_e=None):
            """Ajusta alto y ancho a lo que de verdad ocupa el contenido.

            La altura se MIDE, no se estima. Antes estaba fijada a mano y
            me quedé corto dos veces seguidas: un botón con emoji ocupa
            distinto según la fuente, el DPI y la escala de Windows, así
            que ningún número puesto a ojo vale para todos los equipos.

            Aquí se pregunta a tkinter cuánto necesita la fila y se le da
            exactamente eso, tanto al lienzo como a la ventana de la barra.
            """
            try:
                if not _lienzo2.winfo_exists():
                    return

                # ── ALTO: medido ────────────────────────────────────────
                alto_necesario = max(fila2.winfo_reqheight(), 40)
                if abs(alto_necesario - self._alto_ribbon_actual) > 1:
                    self._alto_ribbon_actual = alto_necesario
                    _lienzo2.configure(height=alto_necesario)
                    _lienzo2.itemconfig(_ventana2, height=alto_necesario)
                    # Y la ventana de la barra, para que no lo recorte
                    try:
                        alto_ventana = 28 + 1 + alto_necesario + 14
                        anchura = v.winfo_screenwidth()
                        if dock == "abajo":
                            v.geometry(f"{anchura}x{alto_ventana}+0+"
                                       f"{v.winfo_screenheight() - alto_ventana - 48}")
                        else:
                            v.geometry(f"{anchura}x{alto_ventana}+0+0")
                    except Exception:
                        pass
                else:
                    _lienzo2.itemconfig(_ventana2, height=alto_necesario)

                # ── ANCHO: barra de desplazamiento solo si hace falta ───
                _lienzo2.configure(scrollregion=_lienzo2.bbox("all"))
                ancho_hijo = fila2.winfo_reqwidth()
                ancho_visible = _lienzo2.winfo_width()
                if ancho_hijo > ancho_visible + 4:
                    if not _scroll2.winfo_ismapped():
                        _scroll2.pack(side="bottom", fill="x")
                else:
                    if _scroll2.winfo_ismapped():
                        _scroll2.pack_forget()
                    _lienzo2.xview_moveto(0)
            except Exception:
                pass

        self._alto_ribbon_actual = 0

        fila2.bind("<Configure>", _ajustar_scroll)
        _lienzo2.bind("<Configure>", _ajustar_scroll)

        def _rueda2(evento):
            """Rueda del ratón = desplazamiento horizontal."""
            try:
                if fila2.winfo_reqwidth() <= _lienzo2.winfo_width():
                    return
                paso = -1 if getattr(evento, "delta", 0) > 0 else 1
                _lienzo2.xview_scroll(paso * 2, "units")
            except Exception:
                pass

        for _w in (_lienzo2, fila2):
            _w.bind("<MouseWheel>", _rueda2)
            _w.bind("<Shift-MouseWheel>", _rueda2)

        self._lienzo_ribbon = _lienzo2
        self._ajustar_ribbon = _ajustar_scroll

        # ── Helper estilo Word: grupo con nombre debajo ────────────────────
        _LBL_GRUPO = "#5a7a95"   # color tenue del nombre del grupo (como Word)

        def _grupo(nombre):
            """Crea un grupo de ribbon: fila de contenido arriba + etiqueta
            centrada abajo + separador vertical a la derecha. Devuelve el
            frame de contenido donde se empacan los botones."""
            cont = tk.Frame(fila2, bg=_BG2)
            cont.pack(side="left", fill="y", padx=(3, 0))
            fila_widgets = tk.Frame(cont, bg=_BG2)
            fila_widgets.pack(side="top", pady=(2, 0))
            tk.Label(cont, text=nombre, bg=_BG2, fg=_LBL_GRUPO,
                     font=("Segoe UI", 6)).pack(side="bottom", pady=(0, 1))
            # Separador vertical a la derecha del grupo
            tk.Frame(fila2, bg=_SEP, width=1).pack(side="left", fill="y",
                                                   padx=2, pady=3)
            return fila_widgets

        def _sep2():
            tk.Label(fila2, text="│", bg=_BG2, fg=_SEP,
                     font=("Segoe UI", 11)).pack(side="left", padx=1)

        def _btn(txt, cmd, fg_on=TEXTO, bg=_BG2, font=_FONS, padx=5):
            return tk.Button(fila2, text=txt, command=cmd,
                             bg=bg, fg=fg_on, font=font,
                             relief="flat", cursor="hand2",
                             padx=padx, pady=0,
                             activebackground="#1a2f40",
                             activeforeground=fg_on)

        # ── GRUPO: Los 8 interruptores originales — formato compacto ───────
        # Cada toggle: [etiqueta corta] [LED ●] — click en el LED lo activa.
        # Tooltip completo al posar el mouse sobre cualquiera de los dos.

        # Los interruptores también en DOS FILAS, como los grupos.
        #
        # Iban los ocho en una sola línea, ocupando casi un tercio de la
        # barra. Apilados de dos en dos ocupan la mitad, y el nombre del
        # grupo cabe debajo como en Word.
        _cont_tog = tk.Frame(fila2, bg=_BG2)
        _cont_tog.pack(side="left", fill="y", padx=(3, 0))
        _tog_grid = tk.Frame(_cont_tog, bg=_BG2)
        _tog_grid.pack(side="top", pady=(2, 0))
        tk.Label(_cont_tog, text="Interruptores", bg=_BG2, fg=_LBL_GRUPO,
                 font=("Segoe UI", 6)).pack(side="bottom", pady=(0, 1))
        self._n_toggles = 0

        def _toggle_par(label_txt, led_attr, cmd,
                        tip_titulo, tip_desc, tip_atajo="",
                        led_fg=GRIS, pad_r=2):
            """Crea label + LED para un toggle. Registra el LED en self."""
            i = self._n_toggles
            self._n_toggles += 1
            fila_i, col_i = i % 2, i // 2

            par = tk.Frame(_tog_grid, bg=_BG2)
            par.grid(row=fila_i, column=col_i, padx=(2, 3), pady=0,
                     sticky="w")

            lbl = tk.Label(par, text=label_txt, bg=_BG2, fg=GRIS,
                           font=_FONS, cursor="hand2")
            lbl.pack(side="left")
            _tip(lbl, tip_titulo, tip_desc, tip_atajo)
            led = tk.Button(par, text="●", command=cmd,
                            bg=_BG2, fg=led_fg,
                            font=_FONS, relief="flat", cursor="hand2",
                            padx=1, pady=0, activebackground="#1a2f40")
            led.pack(side="left", padx=(1, 0))
            _tip(led, tip_titulo, tip_desc, tip_atajo)
            setattr(self, led_attr, led)

        _toggle_par(
            "Sis", "_barra_btn_sistema",
            lambda: self._en_hilo(self.app.set_activo, not self.app.activo, True),
            "Sistema — Encender / Apagar LITCH",
            "Activa o desactiva completamente el motor de análisis y captura de pantalla. "
            "Cuando está apagado, LITCH no procesa el mercado ni genera señales de ningún tipo.")

        _toggle_par(
            "Mic", "_barra_btn_mic",
            self._t_mic,
            "Micrófono — Comandos de voz",
            "Activa o desactiva el micrófono para escuchar órdenes en voz. "
            "Puedes decir: 'operar', 'pausar', 'cuánto gané hoy', "
            "'cambiar monto a 50', 'analiza EUR/USD', 'conectar IQ Option', etc. "
            "El micrófono escucha continuamente en español e inglés.",
            "Ctrl+M")

        _toggle_par(
            "Trd", "_barra_btn_trading",
            lambda: self._en_hilo(self.app.set_trading, not self.app.trading_on, True),
            "Trading — Habilitar ejecución de operaciones",
            "Con Trading ON, LITCH puede abrir posiciones reales en el broker. "
            "Con Trading OFF, LITCH analiza y genera señales pero NO ejecuta ningún trade. "
            "Siempre combinar con Auto-click para el modo 100% autónomo.")

        _toggle_par(
            "Auto", "_barra_btn_auto",
            lambda: self._en_hilo(self.app.set_autoclick, not self.app.autoclick_on, True),
            "Auto-click — Modo completamente autónomo",
            "LITCH opera solo, sin intervención manual. "
            "REQUISITO: Trading también debe estar ON. "
            "Sin Auto-click: LITCH avisa cuándo operar pero espera que tú hagas clic. "
            "Con Auto-click + Trading + Sistema: LITCH opera 24/7 de forma autónoma.",
            "Ctrl+A")

        _toggle_par(
            "Con", "_barra_btn_consejos",
            self._t_consejos,
            "Consejos — Análisis verbal en tiempo real",
            "LITCH habla en voz alta explicando su análisis: "
            "qué ve en el gráfico, por qué sube o baja el activo, "
            "qué patrones detecta y cuál es su nivel de confianza. "
            "Muy útil para aprender mientras LITCH opera.",
            "Ctrl+C")

        _toggle_par(
            "Prc", "_barra_btn_practica",
            self._t_practica,
            "Práctica — Modo entrenamiento sin riesgo",
            "Activa el modo DEMO donde LITCH entrena sus algoritmos en tiempo real "
            "usando la cuenta de práctica del broker (dinero virtual). "
            "LITCH aprende qué patrones funcionan mejor en cada activo "
            "sin arriesgar dinero real. Recomendado para el primer mes.",
            "Ctrl+P",
            led_fg="#f39c12")

        _toggle_par(
            "Pro", "_barra_btn_profesional",
            self._t_profesional,
            "Modo Profesional — el más precavido (dinero real)",
            "El modo de máxima disciplina, pensado para operar con dinero real "
            "en IQ Option o Interactive Brokers. Solo ejecuta señales de "
            "MÁXIMA precisión (más votos), exige expectativa positiva "
            "(Kelly > 0), aplica filtros de sesión, control de drawdown y "
            "cooldown adaptativo tras pérdidas. Opera MENOS pero MEJOR. "
            "Al activarlo pide confirmación. Úsalo cuando pases a real.",
            "Ctrl+R",
            led_fg="#00e676")

        _toggle_par(
            "Cla", "_barra_btn_claude",
            self._t_claude,
            "Claude ✦ — Razonamiento con IA avanzada",
            "Conecta el motor de análisis de LITCH con Claude (Anthropic) "
            "para razonamiento profundo: interpretación de noticias, "
            "análisis de contexto macro, respuestas de chat más inteligentes "
            "y explicaciones detalladas de cada señal. Requiere API key.",
            "Ctrl+K")

        _toggle_par(
            "Oll", "_barra_btn_ollama",
            self._t_ollama,
            "Ollama — IA local sin internet",
            "Usa un modelo de lenguaje local (llama3.2) en lugar de Claude. "
            "No requiere internet ni API key. Es más lento que Claude "
            "pero funciona 100% offline y con privacidad total. "
            "Instalar con: ollama pull llama3.2",
            "Ctrl+O")

        _toggle_par(
            "Voz", "_barra_btn_voz",
            self._t_idioma,
            "Voz — Idioma y síntesis de voz",
            "Alterna el idioma de LITCH entre Español e Inglés. "
            "Afecta: mensajes hablados, alertas de voz, respuestas del chat "
            "y etiquetas de la interfaz. LITCH habla con síntesis de voz "
            "integrada en Windows (Edge TTS) — sin instalaciones extras.",
            led_fg=ACENTO, pad_r=4)

        _sep2()

        # ── GRUPO: Conciencia y parámetros de operación ───────────────────
        #
        # Todo esto iba suelto en la línea de la barra. Ahora va dentro de
        # un contenedor con su nombre debajo, como los demás grupos: se
        # alinea con el resto y deja de estirar la barra a lo ancho.
        _cont_ope = tk.Frame(fila2, bg=_BG2)
        _cont_ope.pack(side="left", fill="y", padx=(3, 0))
        _ope = tk.Frame(_cont_ope, bg=_BG2)
        _ope.pack(side="top", pady=(2, 0))
        tk.Label(_cont_ope, text="Operación", bg=_BG2, fg=_LBL_GRUPO,
                 font=("Segoe UI", 6)).pack(side="bottom", pady=(0, 1))

        # Dos filas dentro del grupo: conciencia arriba, importes abajo
        _ope_f1 = tk.Frame(_ope, bg=_BG2)
        _ope_f1.pack(side="top", anchor="w")
        _ope_f2 = tk.Frame(_ope, bg=_BG2)
        _ope_f2.pack(side="top", anchor="w", pady=(1, 0))

        # A partir de aquí, lo que iba a `fila2` va a estas dos filas.
        # Se redefinen los ayudantes para no tocar las decenas de llamadas
        # que vienen después.
        def _btn(txt, cmd, fg_on=TEXTO, bg=_BG2, font=_FONS, padx=5,
                 _p=_ope_f1):
            return tk.Button(_p, text=txt, command=cmd,
                             bg=bg, fg=fg_on, font=font,
                             relief="flat", cursor="hand2",
                             padx=padx, pady=0,
                             activebackground="#1a2f40",
                             activeforeground=fg_on)

        _lbl_con = tk.Label(_ope_f1, text="Con:", bg=_BG2, fg=GRIS,
                            font=_FONS, cursor="hand2")
        _lbl_con.pack(side="left")
        _tip(_lbl_con, "Conciencia — Modo de decisión",
             "Controla cómo LITCH toma sus decisiones de trading. "
             "Auto: LITCH decide solo según sus análisis. "
             "▶ Operar: fuerza que opere en la próxima señal sin importar la confianza. "
             "⏸ Pausar: bloquea cualquier trade aunque haya señal clara.")

        self._barra_ovr_lbl = tk.Label(_ope_f1, text="🔄", bg=_BG2, fg=ACENTO,
                                        font=("Segoe UI", 8, "bold"))
        self._barra_ovr_lbl.pack(side="left", padx=(2, 1))

        _b_auto_ovr = _btn("🔄", lambda: self._set_ovr("auto"), fg_on=ACENTO)
        _b_auto_ovr.pack(side="left", padx=1)
        _tip(_b_auto_ovr, "Conciencia: Auto",
             "Restaura el modo automático. LITCH decide solo cuándo operar "
             "basándose en el consenso de los 7 algoritmos y el umbral de confianza configurado.")

        _b_actuar = _btn("▶", lambda: self._set_ovr("forzar_actuar"), fg_on="#00e676")
        _b_actuar.pack(side="left", padx=1)
        _tip(_b_actuar, "Conciencia: Forzar operación",
             "Fuerza a LITCH a operar en la próxima oportunidad, ignorando el umbral mínimo "
             "de confianza. Útil cuando ves una señal clara pero LITCH es demasiado conservador.",
             "Solo tiene efecto mientras esté activo")

        _b_pausar = _btn("⏸", lambda: self._set_ovr("forzar_abstener"), fg_on="#ff7043")
        _b_pausar.pack(side="left", padx=1)
        _tip(_b_pausar, "Conciencia: Pausar trades",
             "Bloquea TODOS los trades temporalmente aunque haya señales con alta confianza. "
             "Úsalo antes de noticias importantes (NFP, FOMC) o cuando quieras que LITCH "
             "analice pero no opere.")

        _sep2()

        # ── GRUPO: Monto · Vencimiento · Período ─────────────────────────
        _lbl_monto = tk.Label(_ope_f2, text=" $", bg=_BG2, fg=VERDE,
                              font=_FONB, cursor="hand2")
        _lbl_monto.pack(side="left")
        _tip(_lbl_monto, "Monto de inversión por trade ($)",
             "Cuánto dinero invierte LITCH en cada operación. "
             "Escribe el valor y presiona Enter para guardar. "
             "Recomendado: entre el 1% y 5% de tu capital total.")

        self._barra_monto_var = tk.StringVar(
            value=str(int(self.app.mem["config"].get("monto_base", 10))))
        _e_monto = tk.Entry(_ope_f2, textvariable=self._barra_monto_var,
                            width=5, bg=PANEL, fg=VERDE,
                            font=("Consolas", 8, "bold"),
                            relief="flat", justify="center",
                            insertbackground=VERDE)
        _e_monto.pack(side="left", ipady=1, padx=(1, 1))
        _e_monto.bind("<Return>", self._barra_set_monto)
        _tip(_e_monto, "Monto de inversión",
             "Monto en dólares por trade. Escribe y presiona Enter para aplicar.",
             "Enter para guardar")

        # Vencimiento (tiempo de cierre de la opción) — separado del período de análisis
        _lbl_venc = tk.Label(_ope_f2, text="⏳", bg=_BG2, fg="#e67e22",
                             font=_FONS, cursor="hand2")
        _lbl_venc.pack(side="left", padx=(3, 0))
        _tip(_lbl_venc, "Vencimiento — tiempo de cierre del trade",
             "Cuántos segundos hasta que la opción binaria cierra.\n"
             "Si no ganas en ese tiempo, pierdes la inversión.\n"
             "30s=30seg · 60s=1min · 300s=5min")

        self._barra_venc_var = tk.StringVar(
            value=str(int(self.app.mem["config"].get("vencimiento",
                          self.app.mem["config"].get("periodo_vela", 60)))))
        _e_venc = tk.Entry(_ope_f2, textvariable=self._barra_venc_var,
                           width=4, bg=PANEL, fg="#e67e22",
                           font=("Consolas", 8, "bold"),
                           relief="flat", justify="center",
                           insertbackground="#e67e22")
        _e_venc.pack(side="left", ipady=1, padx=(1, 1))
        _e_venc.bind("<Return>", self._barra_set_venc)
        _tip(_e_venc, "Vencimiento (seg)",
             "Tiempo en segundos hasta el cierre. Enter para aplicar.",
             "Enter para guardar")

        _lbl_dur = tk.Label(_ope_f2, text="⏱", bg=_BG2, fg=ACENTO,
                            font=_FONS, cursor="hand2")
        _lbl_dur.pack(side="left", padx=(3, 0))
        _tip(_lbl_dur, "Período de análisis de velas (segundos)",
             "Cada cuántos segundos LITCH lee una nueva vela del gráfico. "
             "60s = 1 minuto. 300s = 5 minutos.")

        self._barra_dur_var = tk.StringVar(
            value=str(int(self.app.mem["config"].get("periodo_vela", 60))))
        _e_dur = tk.Entry(_ope_f2, textvariable=self._barra_dur_var,
                          width=4, bg=PANEL, fg=ACENTO,
                          font=("Consolas", 8, "bold"),
                          relief="flat", justify="center",
                          insertbackground=ACENTO)
        _e_dur.pack(side="left", ipady=1, padx=(1, 2))
        _e_dur.bind("<Return>", self._barra_set_dur)
        _tip(_e_dur, "Período de análisis (seg)",
             "Escribe el período en segundos y presiona Enter para aplicar.",
             "Enter para guardar")

        # Botones rápidos de vencimiento en el ribbon
        for _vq, _vl in ((30, "30s"), (60, "1m"), (120, "2m"), (300, "5m")):
            _bq = tk.Button(_ope_f2, text=_vl, bg=_BG2, fg="#e67e22",
                            font=_FONS, relief="flat", padx=2, pady=0,
                            cursor="hand2",
                            command=lambda x=_vq: (
                                self._barra_venc_var.set(str(x)),
                                self._barra_set_venc()))
            _bq.pack(side="left", padx=1)
            _tip(_bq, f"Vencimiento rápido: {_vl}",
                 f"Fija el tiempo de cierre de cada trade en {_vq} segundos "
                 "con un solo clic. Equivale a escribir el valor en la "
                 "casilla ⏳ y presionar Enter.")

        _sep2()

        # ── GRUPO: Herramientas — Panel 1: Comunicación y análisis ──────────
        _tools_g1 = [
            ("💬", self.abrir_chat,
             "Chat escrito con LITCH",
             "Habla con LITCH por texto. Dale instrucciones, pide análisis de mercado, "
             "cambia configuraciones o simplemente conversa. "
             "Alternativa al micrófono cuando no puedes hablar en voz alta.",
             "Ctrl+T"),

            ("🎙", self._toggle_mic,
             "Micrófono — Comandos de voz",
             "Activa o desactiva el micrófono para dar órdenes a LITCH con la voz. "
             "Puedes decir: 'operar', 'pausar', 'cuánto gané hoy', 'analiza EUR/USD', "
             "'cambiar monto a 50', 'conectar IQ Option', etc."),

            ("🧠", self.abrir_conciencia,
             "Conciencia de LITCH — Motor de IA",
             "Ventana avanzada que muestra el pensamiento interno de LITCH: "
             "los 9 votos del motor de consenso en tiempo real, "
             "el Grafo de Conocimiento (mapa mental de patrones aprendidos), "
             "la memoria episódica de trades y el razonamiento de cada señal.",
             "F2"),
        ]

        # ── GRUPO: Herramientas — Panel 2: Broker y mercado ──────────────────
        _tools_g2 = [
            ("📊", self.abrir_broker,
             "Panel de Broker y cuenta",
             "Conecta y gestiona tu broker: IQ Option (cuenta práctica/real), "
             "Interactive Brokers (TWS) y Charles Schwab (OAuth). "
             "Revisa saldo, payout actual, sentimiento del mercado y "
             "cambia de activo o modo de cuenta sin salir de LITCH.",
             "F3"),

            ("📈", self.abrir_profesional,
             "Modo Profesional — Backtesting y configuración avanzada",
             "Herramientas de nivel institucional: backtesting completo sobre historial real, "
             "análisis de drawdown, curva de equity, factor de Sharpe, "
             "configuración fina del motor de 9 algoritmos, parámetros del DQN, "
             "Kelly criterion y gestión de riesgo avanzada.",
             "F4"),

            ("🎯", self.abrir_meta,
             "Metas diarias y objetivos financieros",
             "Define cuánto quieres ganar hoy, esta semana y este mes. "
             "LITCH ajusta automáticamente su agresividad: más conservador cuando "
             "la meta está cerca (para no perder lo ganado) y más activo cuando "
             "estás lejos de la meta. También muestra el progreso en tiempo real.",
             "F5"),

            ("📉", self._abrir_historial,
             "Historial de trades y estadísticas",
             "Tabla completa de todas las operaciones: fecha, activo, dirección, "
             "monto invertido, resultado (ganancia/pérdida), confianza, "
             "cuántos votos tuvo y qué patrón se detectó. "
             "Filtra por fecha, activo o resultado. Exporta a CSV.",
             "F6"),
        ]

        # ── GRUPO: Herramientas — Panel 3: Herramientas especiales ───────────
        _tools_g3 = [
            ("🔍", self._abrir_escaner,
             "Escáner de activos — Mejor oportunidad",
             "Escanea TODOS los activos disponibles en el broker y clasifica "
             "cuál tiene la mejor combinación de: payout alto, "
             "win rate histórico de LITCH en ese activo, "
             "y claridad de la tendencia actual. "
             "LITCH cambia automáticamente al mejor activo.",
             "F7"),

            ("📐", self.abrir_calibracion,
             "Calibrar visión de pantalla",
             "Enseña a LITCH exactamente dónde está el gráfico del broker en tu pantalla. "
             "Dibuja un rectángulo sobre el área del gráfico y LITCH calibra "
             "la captura de colores. El borde de visión (verde/rojo) muestra "
             "el área que LITCH está monitoreando — siempre debajo de esta barra.",
             "F8"),

            ("📷", self.abrir_camara,
             "Vista en vivo de la visión de LITCH",
             "Muestra exactamente lo que LITCH está capturando de la pantalla: "
             "la región del gráfico, los colores detectados píxel a píxel "
             "y cómo interpreta verde = SUBE / rojo = BAJA. "
             "Útil para diagnosticar problemas de visión.",
             "F9"),

            ("🎰", self.abrir_loteria,
             "Predictor de Lotería Tica",
             "Motor de predicción especializado en lotería costarricense. "
             "Analiza patrones estadísticos en el historial de resultados, "
             "detecta números fríos/calientes y genera combinaciones "
             "con la mayor probabilidad estadística para cada sorteo.",
             "F10"),
        ]

        # ── GRUPO: Herramientas — Panel 4: Datos y sistema ───────────────────
        _tools_g4 = [
            ("📚", self.abrir_libros,
             "Biblioteca de conocimiento de trading",
             "Base de datos de estrategias descargadas de internet: "
             "análisis técnico (RSI, MACD, Fibonacci, SMC/ICT, Wyckoff), "
             "noticias económicas recientes (Yahoo Finance RSS), "
             "tasas de cambio actualizadas y conceptos de trading de Wikipedia. "
             "LITCH consulta esta biblioteca automáticamente al analizar.",
             "F11"),

            ("☁", self.abrir_nube,
             "Respaldo y restauración en la nube",
             "Hace una copia de seguridad del modelo entrenado de LITCH, "
             "el historial de trades y la memoria de patrones en la nube. "
             "Restaura automáticamente si cambias de PC o si hay pérdida de datos. "
             "También permite sincronizar LITCH entre dispositivos.",
             "F12"),

            ("🔐", self.abrir_seguridad,
             "Seguridad y control de acceso",
             "Configura el PIN de acceso para que nadie más pueda usar LITCH, "
             "el tiempo de bloqueo por inactividad y los permisos de operación "
             "(qué puede hacer LITCH en modo autónomo y qué requiere confirmación). "
             "Protege tu capital de usos no autorizados."),

            ("📧", self.abrir_correo_ia,
             "Reportes automáticos por email",
             "LITCH te envía un resumen diario de trading por correo: "
             "trades realizados, ganancias/pérdidas, activos más rentables, "
             "alertas de señales importantes y estado del modelo. "
             "Configura el email de destino y la frecuencia de reportes."),
        ]

        # ── GRUPO: Interactive Brokers — lo sencillo, para aprender ─────────
        _tools_g5 = [
            ("🟢", self.abrir_panel_simple,
             "Panel sencillo — empiece por aquí",
             "Abre una ventana simple con lo único que hay que saber antes "
             "de operar: si TWS está abierto, si la cuenta es simulada, si "
             "Wall Street está abierto y si LITCH sabe dónde está cada botón. "
             "Las cuatro en verde = puede trabajar tranquilo. Debajo, seis "
             "botones grandes con lo que se hace de verdad en un día."),

            ("📐", self.calibrar_ticket_tws,
             "Enseñarle a LITCH dónde está cada botón de TWS",
             "LITCH le pedirá que ponga el mouse encima de cada campo del "
             "ticket de órdenes (símbolo, comprar, vender, cantidad, tipo, "
             "precio, enviar), uno por uno, con cuenta regresiva en voz alta. "
             "Tarda un minuto.\n\n"
             "IMPORTANTE: sin esta calibración LITCH se NIEGA a hacer clic "
             "en TWS, porque sus posiciones serían estimaciones. Solo "
             "ensayará moviendo el mouse sin pulsar nada."),

            ("👁", self.ver_pantalla_completa,
             "¿Qué ves en mi pantalla?",
             "LITCH mira TODO el monitor (no solo el gráfico) y le cuenta "
             "qué ventanas hay, si TWS está tapado por algo, qué paneles "
             "tienen contenido y si detecta la franja de cuenta simulada.\n\n"
             "Detecta también los cuadros de diálogo encima de TWS: son la "
             "causa número uno de que una automatización pulse donde no "
             "debe. Si hay uno, LITCH se detiene y avisa."),

            ("🤖", self.alternar_piloto_autonomo,
             "PILOTO AUTÓNOMO — LITCH trabaja y aprende solo",
             "Enciende las cuatro piezas a la vez y las coordina: aprende "
             "la pantalla, analiza el mercado, opera y registra cómo salió "
             "cada operación para aprender de ella.\n\n"
             "LA AUTONOMÍA SE GANA, NO SE REGALA. Empieza en nivel 0 "
             "(solo mira) y sube demostrando resultados:\n\n"
             "  0 Observación — solo mira la pantalla\n"
             "  1 Ensayo — prepara operaciones, NO las envía\n"
             "  2 Primeras armas — 1 operación al día, solo SPY\n"
             "  3 Practicante — 2 al día, tres ETF\n"
             "  4 Operador — 3 al día, lista completa\n\n"
             "Y BAJA SOLO si el resultado se hunde: por debajo de −5R "
             "vuelve a Ensayo y deja de ejecutar.\n\n"
             "Colores: gris apagado · naranja aprendiendo · azul "
             "ejecutando · verde nivel máximo.\n\n"
             "Exige cuenta simulada verificada y modo autónomo activo."),

            ("🧠", self.alternar_aprendizaje_ibkr,
             "APRENDIZAJE ACTIVO de Interactive Brokers",
             "LITCH TOMA EL RATÓN y recorre Trader Workstation posándose "
             "sobre cada elemento para verificar dónde está de verdad en SU "
             "pantalla, no donde el manual supone.\n\n"
             "NO HACE CLIC. Posarse encima no puede enviar una orden; "
             "pulsar sí. Aprende igual mirando, y mirando no puede romper "
             "nada.\n\n"
             "Colores del botón:\n"
             "  GRIS — sin empezar\n"
             "  NARANJA — aprendiendo\n"
             "  AZUL — domina la pantalla (75% verificado)\n\n"
             "Exige cuenta simulada, modo autónomo y que nada tape TWS. "
             "Verá el ratón moverse solo: es LITCH."),

            ("🎓", self.leccion_ibkr,
             "Escuela de Interactive Brokers — siguiente lección",
             "Un plan de 17 lecciones que va de lo imprescindible a lo "
             "avanzado: cuenta simulada, watchlist, gráfico, ticket, orden "
             "límite, stop, bracket, alertas, y por qué la orden a mercado "
             "es peligrosa.\n\n"
             "LITCH lleva la cuenta de lo que ya vio. Una cosa cada vez, "
             "no un manual de 300 páginas."),
        ]

        # Renderizar los grupos estilo Word — cada uno con su nombre debajo
        _nombres_grupo = ["Comunicación", "Broker y mercado",
                          "Herramientas", "Datos y sistema",
                          "Interactive Brokers"]
        for grupo, nombre_g in zip(
                (_tools_g1, _tools_g2, _tools_g3, _tools_g4, _tools_g5),
                _nombres_grupo):
            cont_g = _grupo(nombre_g)
            # DOS FILAS por grupo, como la cinta de Word.
            #
            # Antes iban todos en una sola línea horizontal: el grupo
            # ocupaba el doble de ancho y la barra se salía de la pantalla.
            # Apilando de dos en dos (baja primero, luego a la derecha) el
            # ancho se reduce a la mitad y se lee igual de bien.
            for i, entry in enumerate(grupo):
                ico, cmd = entry[0], entry[1]
                titulo, desc = entry[2], entry[3]
                atajo = entry[4] if len(entry) > 4 else ""
                b = tk.Button(cont_g, text=ico, command=cmd,
                              bg=_BG2, fg=TEXTO,
                              font=("Segoe UI", 11),
                              relief="flat", cursor="hand2",
                              padx=3, pady=0,
                              # Sin borde ni marco de foco: son 4 px por
                              # fila que no aportan nada visualmente y con
                              # dos filas se notan.
                              bd=0, highlightthickness=0,
                              activebackground="#1a2f40",
                              activeforeground=ACENTO)
                b.grid(row=i % 2, column=i // 2, padx=1, pady=0, sticky="nsew")
                _tip(b, titulo, desc, atajo)
                # Guardar la referencia del botón de aprendizaje: su color
                # cambia según lo que LITCH haya verificado de verdad.
                if ico == "🧠":
                    self._btn_aprendizaje = b
                    try:
                        self._pintar_aprendizaje()
                    except Exception:
                        pass
                elif ico == "🤖":
                    self._btn_autonomo = b
                    try:
                        self._pintar_autonomo()
                    except Exception:
                        pass

        # ══════════════════════════════════════════════════════════════════
        # GRUPO: Preparación — TODO A MANO, la voz como respaldo
        # ══════════════════════════════════════════════════════════════════
        #
        # El reconocimiento de voz no es fiable: entiende «cloral broker»
        # cuando el señor dice «explora el bróker», y se pierden órdenes
        # sin que nadie sepa por qué. Depender de él para funciones que
        # mueven dinero es una mala decisión de diseño.
        #
        # A partir de aquí, TODO tiene botón. La voz sigue funcionando —
        # es cómoda cuando se acierta— pero deja de ser el único camino.
        cont_prep = _grupo("Preparación")

        def _panel(fn_nombre, fn_mod):
            """Ejecuta una función de módulo y enseña el resultado."""
            def _h():
                try:
                    from importlib import import_module
                    m = import_module(f".{fn_mod}", package="core")
                    self._mostrar_resultado(getattr(m, fn_nombre)(self.app))
                except Exception as e:
                    self._mostrar_resultado(f"No pude hacerlo:\n\n{e}")
            return _h

        # Este va con TEXTO y no con icono, a propósito. Es el que hay que
        # pulsar antes de nada, y un ✅ perdido entre otros siete iconos
        # parecidos no se distingue de los demás. Un botón importante
        # tiene que parecerlo.
        _b_prep = tk.Button(cont_prep, text="⚙ PREPARAR",
                            command=self.abrir_panel_preparacion,
                            bg="#1a3a5a", fg="#00e676",
                            font=("Segoe UI", 9, "bold"), relief="flat",
                            cursor="hand2", padx=8, pady=2, bd=0,
                            highlightthickness=0,
                            activebackground="#245078",
                            activeforeground="#00e676")
        _b_prep.pack(side="left", padx=(2, 3))

        # ── CONFIGURARSE SOLA ─────────────────────────────────────────────
        #
        # Se fueron acumulando cosas que configurar: monitor, visión,
        # botones, ticket, saldo, monto, cuenta, interruptores. Cada una
        # razonable; juntas, una trampa — si falta UNA, Litch no opera, y
        # desde fuera eso se ve igual que «está rota».
        #
        # Un programa que exige ocho aciertos seguidos para arrancar está
        # mal diseñado. Encontrar la ventana y los botones es trabajo suyo.
        _b_auto = tk.Button(cont_prep, text="🔎 DETECTAR",
                            command=self._autoconfigurar,
                            bg="#3a2a10", fg="#ffb020",
                            font=("Segoe UI", 9, "bold"), relief="flat",
                            cursor="hand2", padx=8, pady=2, bd=0,
                            highlightthickness=0,
                            activebackground="#4a3618",
                            activeforeground="#ffb020")
        _b_auto.pack(side="left", padx=(0, 3))

        # ── EL CEREBRO AUTÓNOMO ───────────────────────────────────────────
        #
        # Se construyeron dieciséis módulos nuevos y el sistema autónomo no
        # usaba ninguno: cuando el señor se iba, la Litch que operaba era
        # la vieja. Un fallo de integración, no de diseño.
        #
        # Este botón enciende el ciclo que sí los atraviesa todos, y que
        # además se repara solo cuando el problema es suyo de arreglar.
        _b_cer = tk.Button(cont_prep, text="🧠 AUTÓNOMO",
                           command=self._cerebro_autonomo,
                           bg="#2a1a3a", fg="#c9a0ff",
                           font=("Segoe UI", 9, "bold"), relief="flat",
                           cursor="hand2", padx=8, pady=2, bd=0,
                           highlightthickness=0,
                           activebackground="#3a2450",
                           activeforeground="#c9a0ff")
        _b_cer.pack(side="left", padx=(0, 6))
        _tip(_b_cer, "AUTÓNOMO — el ciclo completo, que se repara solo",
             "Cada 20 segundos recorre los catorce eslabones. Si algo se "
             "rompe y puede arreglarlo —la ventana se movió, cambió el "
             "monitor, los botones ya no están donde creía— vuelve a "
             "detectarlo él mismo en vez de pararse a esperarle.\n\n"
             "Usa TODO lo nuevo: detección automática, filtro de ventaja, "
             "freno diario, confianza calibrada y tamaño por Kelly.\n\n"
             "No toca lo que depende de usted: cuenta, saldo y límite.",
             "Lo automático repite; lo autónomo se arregla")
        _tip(_b_auto, "DETECTAR — que se configure sola",
             "Busca la ventana de IQ Option esté donde esté, se muda a ese "
             "monitor, localiza SUBE y BAJA por su color y lee el ticket.\n\n"
             "Los botones los busca por COLOR, no por una coordenada "
             "guardada: así funciona aunque cambie la resolución, el "
             "monitor o el tamaño de la ventana.\n\n"
             "Es lo primero que hay que pulsar. Después «⚙ PREPARAR» para "
             "lo que solo usted puede decidir: cuenta, saldo y límite.",
             "Con IQ Option visible y sin nada encima")
        _tip(_b_prep, "PREPARAR — el panel donde se arregla todo",
             "Las once comprobaciones, cada una con su control al lado: "
             "botones DEMO/REAL, los interruptores, y campos para escribir "
             "su saldo, su monto y su límite de pérdida.\n\n"
             "La lista se actualiza sola según va tocando cosas. Es lo "
             "primero que hay que abrir antes de dejarla operando.",
             "Aquí SÍ se puede activar todo a mano")

        for _ic, _cmd, _tit, _ay in (
            ("🎯", _panel("calibrar", "leer_ticket_iq"),
             "Calibrar el ticket",
             "Le señala con el ratón dónde están el monto, el vencimiento "
             "y el pago. Después los lee sola."),
            ("💰", _panel("descripcion", "leer_ticket_iq"),
             "¿Con qué números opera?",
             "Monto, vencimiento y pago actuales, y si los leyó de la "
             "pantalla o los tenía de memoria."),
            ("📏", _panel("sugerir", "mercado_y_tamano"),
             "¿Cuánto invertir?",
             "El 1 %, 2 % y 5 % del capital, y cuántas pérdidas seguidas "
             "aguanta con el monto actual."),
            ("📐", _panel("ajustar", "escala_temporal"),
             "Ajustar el gráfico",
             "Centra el gráfico y ajusta el zoom para ver entre 40 y 60 "
             "velas."),
            ("🖥", _panel("descripcion", "monitores"),
             "Monitores",
             "Cuáles hay y en cuál está mirando."),
            ("🎓", lambda: self._mostrar_resultado(self._entrenar()),
             "Entrenar automáticamente",
             "Enciende o apaga el entrenamiento con medición. Cada 25 "
             "operaciones compara con el bloque anterior: acierto, "
             "calibración y si está por encima del punto de equilibrio.\n\n"
             "Se para sola si empeora dos bloques seguidos, si salta el "
             "freno diario o si su calibración se degrada."),
            ("📈", _panel("informe", "entrenador"),
             "¿Cómo va el entrenamiento?",
             "Bloque a bloque: si mejora, empeora o va igual. Y si está "
             "ganando dinero o solo acertando."),
            ("🛑", _panel("informe", "freno_diario"),
             "El día de hoy",
             "Cuánto llevo ganado o perdido hoy, y cuánto margen queda "
             "antes de que el freno diario me pare."),
            ("🗺", _panel("estado", "calibracion_por_monitor"),
             "Calibración por monitor",
             "Qué pantallas están calibradas y cuáles no. Cada monitor "
             "guarda sus propias coordenadas de SUBE, BAJA y el gráfico."),
            ("⚖", _panel("informe", "tamano_kelly"),
             "¿Cuánto en cada operación?",
             "El tamaño no debería ser fijo: una señal de 8/11 votos "
             "merece más que una de 5/11. Kelly fraccionado, limitado al "
             "2 % del capital."),
            ("🎚", _panel("informe", "calibrar_confianza"),
             "¿Acierto lo que digo?",
             "Cuando digo «70 % de confianza», ¿acierto el 70 %? Compara "
             "lo anunciado con lo ocurrido, tramo por tramo. Si no "
             "coinciden, corrijo."),
            ("🎲", _panel("informe", "filtro_ventaja"),
             "¿Dónde tengo ventaja?",
             "Por acuerdo de métodos y por hora del día: dónde acierta "
             "por encima del punto de equilibrio y dónde no. Las malas "
             "las salta."),
            ("🩺", _panel("informe", "porque_no_opera"),
             "¿Por qué no opero?",
             "Recorre los catorce eslabones que hay que atravesar para "
             "que Litch haga clic, y señala el PRIMERO que falla — que es "
             "el que importa: los de después ni se prueban."),
            ("🖱", _panel("probar_clic", "porque_no_opera"),
             "Probar el ratón",
             "Mueve el cursor y comprueba si obedece. No pulsa nada: si el "
             "movimiento no llega, el clic tampoco llegaría.\n\n"
             "Úselo cuando Litch no haga clic y no sepa por qué."),
            ("🔊", lambda: self._probar_voz(),
             "Probar la voz",
             "Comprueba las dos vías de voz —en línea y sin internet— y "
             "dice cuál funciona. Úselo cuando no se oiga nada."),
        ):
            _b = tk.Button(cont_prep, text=_ic, command=_cmd,
                           bg=_BG2, fg="#ff9500", font=("Segoe UI", 11),
                           relief="flat", cursor="hand2", padx=4, bd=0,
                           highlightthickness=0,
                           activebackground="#1a2f40")
            _b.pack(side="left", padx=1)
            _tip(_b, _tit, _ay, "También funciona hablando, pero el botón "
                                "no se equivoca")

        # ── GRUPO: Instituciones (agregar broker/cuenta a mano) ─────────────
        cont_inst = _grupo("Instituciones")
        self._barra_inst_var = tk.StringVar()
        # Ancho 9 en vez de 12: este campo está vacío el 99% del tiempo
        # (solo se usa al añadir un broker nuevo) y ocupaba un hueco
        # llamativo en medio de la barra. Sigue cabiendo «Interactive».
        _e_inst = tk.Entry(cont_inst, textvariable=self._barra_inst_var,
                           width=9, bg=PANEL, fg=ACENTO,
                           font=("Segoe UI", 8), relief="flat",
                           insertbackground=ACENTO)
        _e_inst.pack(side="left", ipady=1, padx=(2, 1))
        _e_inst.bind("<Return>", self._barra_agregar_institucion)
        _tip(_e_inst, "Agregar institución / broker manualmente",
             "Escribe aquí el nombre de un broker o institución que quieras "
             "registrar (ej. «IQ Option», «Interactive Brokers», «Binance») "
             "y presiona Enter o el botón ＋. LITCH lo guarda en su lista de "
             "instituciones para poder trabajar con él. No pide contraseñas: "
             "solo registra el nombre.")
        _b_inst = tk.Button(cont_inst, text="＋", command=self._barra_agregar_institucion,
                            bg=_BG2, fg="#00e676", font=_FONB,
                            relief="flat", cursor="hand2", padx=4)
        _b_inst.pack(side="left")
        _tip(_b_inst, "Agregar la institución escrita",
             "Guarda el nombre escrito en la casilla de la izquierda como una "
             "institución con la que LITCH puede trabajar.")

        # ── GRUPO: Sesión de mercado + P&L (derecha, informativo) ────────────
        self._barra_sesion = tk.Label(
            fila2, text="", bg=_BG2, fg=GRIS, font=_FONS, cursor="hand2")
        self._barra_sesion.pack(side="right", padx=(0, 2))
        _tip(self._barra_sesion, "Sesión de mercado activa",
             "Indica qué sesión de trading está activa ahora mismo:\n"
             "TYO = Tokio (00-09 UTC) — menor volatilidad\n"
             "LON = Londres (07-16 UTC) — alta volatilidad\n"
             "NY  = Nueva York (13-22 UTC) — máxima volatilidad\n"
             "LON+NY = Solapamiento (13-16 UTC) = mejores señales del día")

        self._barra_pnl = tk.Label(
            fila2, text="", bg=_BG2, fg=GRIS, font=_FONS, cursor="hand2")
        self._barra_pnl.pack(side="right", padx=(0, 2))
        _tip(self._barra_pnl, "P&L del día (ganancia/pérdida neta hoy)",
             "Resultado acumulado de todos los trades de hoy. "
             "Verde = en positivo. Rojo = en negativo. "
             "LITCH reduce el tamaño de inversión automáticamente "
             "cuando el drawdown del día supera el 10% del capital.")

        self._barra_trades_hoy = tk.Label(
            fila2, text="", bg=_BG2, fg=GRIS, font=_FONS, cursor="hand2")
        self._barra_trades_hoy.pack(side="right", padx=(0, 4))
        _tip(self._barra_trades_hoy, "Trades realizados hoy",
             "Número total de operaciones realizadas en la sesión de hoy. "
             "Formato: W=ganados / L=perdidos. "
             "LITCH puede pausar automáticamente si acumula "
             "demasiadas pérdidas consecutivas.")

        _sep2()

        # ── Idioma + expandir (extremo derecho) ──────────────────────────────
        # ── PLEGAR / DESPLEGAR la cinta (como el ⌃ de Word) ────────────────
        #
        # La barra tapa parte de TWS, y lo que es peor: le tapa la vista a
        # la propia LITCH. Su cuadro verde de visión no puede leer lo que
        # queda debajo de la barra.
        #
        # Plegada deja solo la línea de título (28 px) y libera 76 px de
        # pantalla. La preferencia se recuerda entre sesiones.
        # El botón de ocultar/mostrar YA NO va aquí. Vive en la fila 1,
        # porque la fila 2 desaparece al plegar y el botón se escondía a
        # sí mismo. Ver el comentario largo junto a su creación.

        # Guardar lo necesario para plegar sin reconstruir la barra
        self._ribbon_cont = _cont2
        self._ribbon_lienzo = _lienzo2
        self._ribbon_scroll = _scroll2
        self._ribbon_sep = _sep_ribbon
        self._ribbon_fila1 = fila1

        # Doble clic en la línea de título también pliega, como en Word
        try:
            fila1.bind("<Double-Button-1>",
                       lambda _e: self._plegar_ribbon())
        except Exception:
            pass

        _b_expand = tk.Button(fila2, text="⊡", command=self._expandir_barra,
                              bg=_BG2, fg=GRIS, font=_FONS, relief="flat",
                              cursor="hand2", padx=6)
        _b_expand.pack(side="right", padx=(0, 4))
        _tip(_b_expand, "Expandir — Ver ventana completa de LITCH",
             "Muestra la ventana principal con el orbe de estado, "
             "el panel de estadísticas detalladas, el historial completo "
             "y todos los controles avanzados de configuración. "
             "El ribbon permanece visible encima.",
             "Doble clic en el orbe para volver al ribbon")

        self._btn_idioma_barra = tk.Button(
            fila2, text="🌐 ES", command=self._t_idioma,
            bg=_BG2, fg=GRIS, font=_FONS, relief="flat",
            cursor="hand2", padx=4)
        self._btn_idioma_barra.pack(side="right")
        _tip(self._btn_idioma_barra, "Idioma / Language",
             "Alterna el idioma de LITCH entre Español e Inglés. "
             "Afecta mensajes de voz, alertas, etiquetas de la interfaz "
             "y respuestas del chat. El modelo de IA piensa en ambos idiomas.")

        # 💰 Cuenta DEMO/REAL — toggle manual con confirmación
        _tipo_ini = self.app.mem["config"].get("tipo_cuenta", "demo")
        self._btn_cuenta = tk.Button(
            fila2,
            text="REAL" if _tipo_ini == "real" else "DEMO",
            command=self._t_cuenta,
            bg=_BG2, fg="#ff5252" if _tipo_ini == "real" else "#f39c12",
            font=_FONB, relief="flat", cursor="hand2", padx=5)
        self._btn_cuenta.pack(side="right")
        _tip(self._btn_cuenta, "Cuenta DEMO / REAL — registro manual",
             "Le dice a Litch en qué cuenta de IQ Option estás operando "
             "para que sus mensajes y registros sean honestos. "
             "DEMO (naranja) = dinero virtual de práctica. "
             "REAL (rojo) = dinero verdadero — pasar a REAL pide "
             "confirmación. IMPORTANTE: este botón NO cambia la cuenta "
             "en el broker; eso se hace en IQ Option. Solo registra "
             "cuál estás usando.")

        # ⚓ Acoplar barra: arriba → abajo → izquierda → derecha
        _btn_dock = tk.Button(
            fila2, text="⚓", command=self._dock_barra,
            bg=_BG2, fg=ACENTO, font=_FONS, relief="flat",
            cursor="hand2", padx=4)
        _btn_dock.pack(side="right")
        _tip(_btn_dock, "Acoplar barra — cambiar posición",
             "Mueve la barra de herramientas al borde que prefieras de la "
             "pantalla: arriba → abajo → izquierda → derecha. "
             "En los lados se vuelve una columna compacta que no estorba "
             "ni al gráfico ni a los movimientos automáticos del mouse. "
             "La posición se recuerda entre sesiones.")

        # Estado compacto (zona central sobrante)
        self._barra_status = tk.Label(
            fila2, text="", bg=_BG2, fg=GRIS,
            font=_FONS, anchor="e")
        self._barra_status.pack(side="right", padx=4)

        # ── La rueda del ratón funciona sobre CUALQUIER botón ──────────────
        #
        # Sin esto, la rueda solo desplazaba si el puntero estaba sobre un
        # hueco vacío de la fila — justo lo que no pasa nunca, porque la
        # fila está llena de botones. Se ata a todos los hijos.
        def _atar_rueda(w, hondo=0):
            if hondo > 4:
                return
            try:
                w.bind("<MouseWheel>", _rueda2, add="+")
                for hijo in w.winfo_children():
                    _atar_rueda(hijo, hondo + 1)
            except Exception:
                pass

        try:
            _atar_rueda(fila2)
        except Exception:
            pass

        # Primer ajuste, ya con todos los botones dentro
        try:
            self.root.after(150, _ajustar_scroll)
            self.root.after(600, _ajustar_scroll)
            # Y después, aplicar si el usuario la dejó plegada. Va al
            # final para que el alto ya esté medido cuando se despliegue.
            self.root.after(750, self._restaurar_plegado)
        except Exception:
            pass

        # ── Arrastrar haciendo drag en cualquier área ─────────────────────
        for widget in [v, fila1, fila2]:
            widget.bind("<ButtonPress-1>",   self._barra_drag_start)
            widget.bind("<B1-Motion>",       self._barra_drag_move)

        # Iniciar loop de refresco
        self._barra_tick_activo = True
        self._ribbon_cache = {}   # dirty-check: evita .config() innecesarios
        self.root.after(0, self._barra_tick)

    # ── Plegar / desplegar la cinta ─────────────────────────────────────────

    def _plegar_ribbon(self, forzar=None):
        """Esconde o muestra la fila de herramientas.

        Plegada, la barra se queda en la línea de estado (28 px) y libera
        76 px de pantalla. Importa más de lo que parece: la barra tapa el
        gráfico, y la visión de LITCH no puede leer lo que queda debajo —
        así que plegarla no es solo cosmético, le devuelve campo de visión.

        `forzar`: True para plegar, False para desplegar, None para
        alternar.
        """
        cont = getattr(self, "_ribbon_cont", None)
        if cont is None:
            return
        try:
            if not cont.winfo_exists():
                return
        except Exception:
            return

        plegada = getattr(self, "_ribbon_plegado", False)
        nuevo = (not plegada) if forzar is None else bool(forzar)
        self._ribbon_plegado = nuevo

        try:
            sep = getattr(self, "_ribbon_sep", None)
            if nuevo:
                cont.pack_forget()
                if sep is not None and sep.winfo_exists():
                    sep.pack_forget()
                alto = 28
            else:
                if sep is not None and sep.winfo_exists():
                    sep.pack(fill="x")
                cont.pack(fill="x")
                alto = 28 + 1 + max(
                    getattr(self, "_alto_ribbon_actual", 68), 40) + 14

            # Redimensionar la ventana de la barra al alto que toque
            v = getattr(self, "_barra_win", None)
            if v is not None and v.winfo_exists():
                # Mismo criterio que al crearla: el monitor elegido manda,
                # no el principal. Si no, al plegar saltaba de pantalla.
                ox, oy = 0, 0
                sw = v.winfo_screenwidth(); sh = v.winfo_screenheight()
                try:
                    from . import monitores as _mon
                    n = self.app.mem.get("config", {}).get("monitor_barra")
                    ms = _mon.listar()
                    m = next((x for x in ms if x["n"] == int(n)), None) if n else None
                    if m is None:
                        m = next((x for x in ms if x["principal"]), ms[0])
                    ox, oy, sw, sh = m["x"], m["y"], m["w"], m["h"]
                except Exception:
                    pass
                dock = self.app.mem["config"].get("barra_dock", "arriba")
                if dock == "abajo":
                    v.geometry(f"{sw}x{alto}+{ox}+{oy + sh - alto - 48}")
                else:
                    v.geometry(f"{sw}x{alto}+{ox}+{oy}")

            # El botón dice lo que VA A HACER, no en qué estado está. Es
            # la diferencia entre un botón que se entiende y uno que hay
            # que descifrar.
            b = getattr(self, "_btn_plegar", None)
            if b is not None and b.winfo_exists():
                if nuevo:
                    b.config(text="⌄ MOSTRAR BARRA", fg="#f39c12",
                             bg="#3a2a10", activebackground="#4a3618",
                             activeforeground="#f39c12")
                else:
                    b.config(text="⌃ OCULTAR BARRA", fg="#00e676",
                             bg="#1a3a5a", activebackground="#245078",
                             activeforeground="#00e676")
        except Exception:
            pass

        # Recordar la preferencia
        try:
            self.app.mem["config"]["ribbon_plegado"] = nuevo
            from . import memoria as _mem
            _mem.guardar(self.app.mem)
        except Exception:
            pass

        # Al plegar o desplegar cambia cuánta pantalla queda libre. Si la
        # visión está en pantalla completa, tiene que seguir a la barra —
        # si no, plegar liberaría espacio que Litch no aprovecharía, que
        # es justo lo que este botón viene a evitar.
        try:
            from . import vision_total as _vt
            _vt.refrescar(self.app)
        except Exception:
            pass

        try:
            if nuevo:
                _msg = "Barra plegada — LITCH ve más pantalla."
                try:
                    from . import vision_total as _vt2
                    if self.app.mem["config"].get("vision_total"):
                        _r = self.app.mem["config"].get("region_grafico")
                        _msg = ("Barra plegada — LITCH ve ahora el "
                                f"{_vt2.porcentaje_visible(_r)} % de la pantalla.")
                except Exception:
                    pass
                self.log(_msg)
            else:
                self.log("Barra desplegada.")
        except Exception:
            pass

    def _restaurar_plegado(self):
        """Aplica la preferencia guardada al arrancar la barra."""
        try:
            if self.app.mem.get("config", {}).get("ribbon_plegado"):
                self._plegar_ribbon(forzar=True)
        except Exception:
            pass

    # ── Agregar institución/broker manualmente desde la barra ───────────────
    def _barra_agregar_institucion(self, _=None):
        """Registra el nombre escrito como institución con la que trabajar."""
        try:
            nombre = self._barra_inst_var.get().strip()
        except Exception:
            nombre = ""
        if not nombre:
            return
        cfg = self.app.mem["config"]
        lista = cfg.setdefault("instituciones", [])
        if nombre.lower() not in [x.lower() for x in lista]:
            lista.append(nombre)
            try:
                from . import memoria as _mem
                _mem.guardar(self.app.mem)
            except Exception:
                pass
            self.app.decir(self.app.txt(
                f"Institución {nombre} registrada, señor. Ya son "
                f"{len(lista)} en mi lista.",
                f"Institution {nombre} registered, sir. {len(lista)} total."))
        else:
            self.app.log(f"[Instituciones] «{nombre}» ya estaba registrada.")
        try:
            self._barra_inst_var.set("")
        except Exception:
            pass

    # ── Toggle cuenta DEMO/REAL ─────────────────────────────────────────────
    def _t_cuenta(self):
        """Alterna el registro de cuenta. Pasar a REAL exige confirmación."""
        actual = self.app.mem["config"].get("tipo_cuenta", "demo")
        if actual == "demo":
            from tkinter import messagebox
            if not messagebox.askyesno(
                    "Cuenta REAL",
                    "¿Confirmas que en IQ Option tienes seleccionada la "
                    "cuenta REAL?\n\nCon Auto-click activo, cada operación "
                    "usará dinero VERDADERO.\n\n(Este botón solo registra "
                    "la cuenta — el cambio real se hace en el broker.)"):
                return
            nuevo = "real"
        else:
            nuevo = "demo"
        try:
            self._btn_cuenta.config(
                text="REAL" if nuevo == "real" else "DEMO",
                fg="#ff5252" if nuevo == "real" else "#f39c12")
        except Exception:
            pass
        self._en_hilo(self.app.set_tipo_cuenta, nuevo, True)

    # ── Acoplado de la barra (arriba/abajo/izquierda/derecha) ──────────────
    def _dock_barra(self):
        """Cicla la posición de la barra y la reconstruye ahí."""
        orden  = ["arriba", "abajo", "izquierda", "derecha"]
        cfg    = self.app.mem["config"]
        actual = cfg.get("barra_dock", "arriba")
        nuevo  = orden[(orden.index(actual) + 1) % len(orden)] \
            if actual in orden else "abajo"
        cfg["barra_dock"] = nuevo
        try:
            from . import memoria as _mem
            _mem.guardar(self.app.mem)
        except Exception:
            pass
        try:
            self._barra_tick_activo = False
            if self._barra_win and self._barra_win.winfo_exists():
                self._barra_win.destroy()
        except Exception:
            pass
        self._barra_win = None
        self._construir_barra()
        try:
            self.app.log(f"[Barra] Acoplada: {nuevo}.")
        except Exception:
            pass

    def _construir_barra_vertical(self, lado: str):
        """Columna compacta acoplada al borde izquierdo o derecho.

        Contiene los mismos interruptores y herramientas del ribbon,
        cada uno con su tooltip explicativo. Los LEDs se sincronizan con
        el mismo _barra_tick del ribbon horizontal.
        """
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        _BG   = "#050d18"
        _FONS = ("Segoe UI", 7)
        _FONB = ("Segoe UI", 8, "bold")
        ANCHO = 52
        ALTO  = sh - 120

        v = tk.Toplevel(self.root)
        v.overrideredirect(True)
        v.attributes("-topmost", True)
        v.attributes("-alpha", 0.93)
        x = 0 if lado == "izquierda" else sw - ANCHO
        v.geometry(f"{ANCHO}x{ALTO}+{x}+60")
        v.configure(bg=_BG)
        self._barra_win = v

        col = tk.Frame(v, bg=_BG)
        col.pack(fill="both", expand=True)

        # ◉ Logo / expandir
        _b_logo = tk.Button(col, text="◉", bg=_BG, fg=ACENTO, font=_FONB,
                            relief="flat", cursor="hand2",
                            command=self._expandir_barra)
        _b_logo.pack(fill="x", pady=(4, 0))
        _tip(_b_logo, "LITCH — Expandir ventana",
             "Abre la ventana principal completa de Litch.")

        # Señal compacta + WR + LED de visión (mismos attrs que el ribbon)
        self._barra_senal = tk.Label(col, text="◌", bg=_BG, fg=ACENTO,
                                     font=_FONB, width=5, wraplength=48)
        self._barra_senal.pack(fill="x")
        _tip(self._barra_senal, "Señal activa",
             "▲ verde = SUBE (CALL) · ▼ rojo = BAJA (PUT). "
             "Versión compacta de la señal del ribbon.")
        self._barra_votos = tk.Label(col, text="", bg=_BG, fg=GRIS,
                                     font=_FONS, width=5, wraplength=48)
        self._barra_votos.pack(fill="x")
        self._barra_wr = tk.Label(col, text="WR", bg=_BG, fg=GRIS,
                                  font=_FONS, width=5)
        self._barra_wr.pack(fill="x")
        _tip(self._barra_wr, "Win Rate (últimos 50 trades)",
             "Verde ≥60% · Naranja 50-60% · Rojo <50%.")
        self._barra_vision_led = tk.Label(col, text="●", bg=_BG, fg=GRIS,
                                          font=_FONB)
        self._barra_vision_led.pack()
        _tip(self._barra_vision_led, "Visión de pantalla",
             "Verde = viendo el gráfico. Rojo = sin gráfico. "
             "Amarillo = calibrar con 📐.")
        self._barra_vision_txt = tk.Label(col, text="", bg=_BG, fg=GRIS,
                                          font=("Segoe UI", 1))
        self._barra_hora = tk.Label(col, text="", bg=_BG, fg=GRIS,
                                    font=("Segoe UI", 6), width=7,
                                    wraplength=48)
        self._barra_hora.pack(fill="x")

        tk.Frame(col, bg="#1a2a3a", height=1).pack(fill="x", pady=3)

        # ── Interruptores (mismos comandos que el ribbon) ────────────────
        _toggles = [
            ("Sis", "_barra_btn_sistema",
             lambda: self._en_hilo(self.app.set_activo,
                                   not self.app.activo, True),
             "Sistema — Encender/Apagar LITCH",
             "Activa o desactiva el motor de análisis completo."),
            ("Mic", "_barra_btn_mic", self._t_mic,
             "Micrófono — Comandos de voz",
             "Escucha órdenes habladas en español e inglés."),
            ("Trd", "_barra_btn_trading",
             lambda: self._en_hilo(self.app.set_trading,
                                   not self.app.trading_on, True),
             "Trading — Análisis de mercado",
             "ON: Litch analiza el gráfico y genera señales."),
            ("Auto", "_barra_btn_auto",
             lambda: self._en_hilo(self.app.set_autoclick,
                                   not self.app.autoclick_on, True),
             "Auto-click — Modo autónomo",
             "Litch opera solo. Es el ÚNICO botón que le permite "
             "mover el mouse y hacer clicks."),
            ("Prc", "_barra_btn_practica", self._t_practica,
             "Práctica — Entrenamiento DEMO",
             "Entrena en la cuenta demo sin dinero real."),
            ("Pro", "_barra_btn_profesional", self._t_profesional,
             "Modo Profesional — el más precavido (dinero real)",
             "Solo señales de máxima precisión, Kelly>0, filtros de sesión "
             "y control de drawdown. Para operar con dinero real. Pide "
             "confirmación al activar."),
            ("Con", "_barra_btn_consejos", self._t_consejos,
             "Consejos — Voz proactiva",
             "Litch comenta su análisis y da recomendaciones."),
            ("Cla", "_barra_btn_claude", self._t_claude,
             "Claude ✦ — IA en la nube",
             "Razonamiento avanzado con Claude (requiere API key)."),
            ("Oll", "_barra_btn_ollama", self._t_ollama,
             "Ollama — IA local offline",
             "Modelo de lenguaje local, 100% privado."),
        ]
        for _txt, _attr, _cmd, _tt, _td in _toggles:
            fr = tk.Frame(col, bg=_BG)
            fr.pack(fill="x")
            lb = tk.Label(fr, text=_txt, bg=_BG, fg=GRIS, font=_FONS,
                          cursor="hand2")
            lb.pack(side="left", padx=(4, 0))
            _tip(lb, _tt, _td)
            led = tk.Button(fr, text="●", command=_cmd, bg=_BG, fg=GRIS,
                            font=_FONS, relief="flat", cursor="hand2",
                            padx=1, pady=0, activebackground="#1a2f40")
            led.pack(side="right", padx=(0, 4))
            _tip(led, _tt, _td)
            setattr(self, _attr, led)
        # Attr requerido por el tick aunque no se muestre
        self._barra_btn_voz = tk.Label(col, text="", bg=_BG)
        self._barra_ovr_lbl = tk.Label(col, text="🔄", bg=_BG, fg=ACENTO,
                                       font=_FONS)
        self._barra_ovr_lbl.pack()
        _tip(self._barra_ovr_lbl, "Conciencia — modo de decisión",
             "🔄 Auto · ▶ Forzar operación · ⏸ Pausado. "
             "Se cambia desde el ribbon horizontal o el panel principal.")
        self._barra_status = tk.Label(col, text="", bg=_BG,
                                      font=("Segoe UI", 1))

        tk.Frame(col, bg="#1a2a3a", height=1).pack(fill="x", pady=3)

        # ── Herramientas ─────────────────────────────────────────────────
        _tools = [
            ("💬", self.abrir_chat, "Chat con LITCH",
             "Conversa por texto: órdenes, análisis, configuración."),
            ("🧠", self.abrir_conciencia, "Conciencia — motor de IA",
             "Votos del consenso, grafo de conocimiento y razonamiento."),
            ("📊", self.abrir_broker, "Broker y cuenta",
             "IQ Option, IBKR y Schwab: saldo, payout y activos."),
            ("🎯", self.abrir_meta, "Metas diarias",
             "Objetivo de ganancia del día y progreso en tiempo real."),
            ("🔍", self._abrir_escaner, "Escáner de activos",
             "Busca el mejor activo para operar ahora."),
            ("📐", self.abrir_calibracion, "Calibrar visión",
             "Enseña a Litch dónde está el gráfico del broker."),
            ("📷", self.abrir_camara, "Vista de la visión",
             "Muestra lo que Litch está viendo de la pantalla."),
            ("🎰", self.abrir_loteria, "Loterías inteligentes",
             "Baloto, Revancha, Astro Luna y Sol: análisis y educación."),
            ("📚", self.abrir_libros, "Biblioteca de trading",
             "Estrategias, noticias y conceptos aprendidos."),
            ("☁", self.abrir_nube, "Respaldo en la nube",
             "Copia de seguridad de toda la memoria de Litch."),
        ]
        for _ic, _cmd, _tt, _td in _tools:
            b = tk.Button(col, text=_ic, command=_cmd, bg=_BG, fg=TEXTO,
                          font=("Segoe UI", 10), relief="flat",
                          cursor="hand2", pady=1,
                          activebackground="#1a2f40")
            b.pack(fill="x")
            _tip(b, _tt, _td)

        # ── Dock + cerrar ────────────────────────────────────────────────
        _b_dock = tk.Button(col, text="⚓", command=self._dock_barra,
                            bg=_BG, fg=ACENTO, font=_FONB, relief="flat",
                            cursor="hand2")
        _b_dock.pack(side="bottom", fill="x", pady=(0, 4))
        _tip(_b_dock, "Acoplar barra — cambiar posición",
             "Arriba → abajo → izquierda → derecha. Se recuerda "
             "entre sesiones.")
        _b_close = tk.Button(col, text="✕", command=self._cerrar_aplicacion,
                             bg=_BG, fg="#ef5350", font=_FONB, relief="flat",
                             cursor="hand2")
        _b_close.pack(side="bottom", fill="x")
        _tip(_b_close, "Cerrar Litch — guardado automático",
             "Guarda toda la memoria y el aprendizaje y cierra ordenado.")

        # Drag vertical
        for widget in (v, col):
            widget.bind("<ButtonPress-1>", self._barra_drag_start)
            widget.bind("<B1-Motion>",     self._barra_drag_move)

        self._barra_tick_activo = True
        self._ribbon_cache = {}
        self.root.after(0, self._barra_tick)

    def _barra_set_monto(self, _=None):
        """Aplica el monto desde el ribbon."""
        try:
            val = float(self._barra_monto_var.get())
            self.app.mem["config"]["monto_base"] = val
            from . import memoria
            memoria.guardar(self.app.mem)
        except Exception:
            pass

    def _barra_set_dur(self, _=None):
        """Aplica la duración desde el ribbon."""
        try:
            val = int(self._barra_dur_var.get())
            self.app.mem["config"]["periodo_vela"] = val
            from . import memoria
            memoria.guardar(self.app.mem)
        except Exception:
            pass

    def _barra_set_venc(self, _=None):
        """Aplica el vencimiento (tiempo de cierre del trade) desde el ribbon."""
        try:
            val = int(self._barra_venc_var.get())
            if val <= 0:
                return
            self.app.mem["config"]["vencimiento"] = val
            from . import memoria
            memoria.guardar(self.app.mem)
            self.app.log(f"[Config] Vencimiento={val}s ({val//60}min {val%60}s)")
            # Sincronizar con el panel de control si existe
            try:
                self._qvenc_var.set(str(val))
            except Exception:
                pass
        except Exception:
            pass

    def _cp_aplicar_config(self):
        """Aplica monto, vencimiento y período de análisis desde el panel de control."""
        try:
            from . import memoria
            cfg = self.app.mem["config"]
            nm  = float(self._qmonto_var.get())
            nv  = int(self._qvenc_var.get())
            nd  = int(self._qdur_var.get())
            if nm <= 0 or nv <= 0 or nd <= 0:
                return
            cfg["monto_base"]        = nm
            cfg["vencimiento"]       = nv
            cfg["periodo_vela"]      = nd
            cfg["monto_modo_manual"] = True
            memoria.guardar(self.app.mem)
            self.app.log(
                f"[Config] ${nm:.0f} | venc={nv}s | período={nd}s")
        except Exception:
            pass

    def _cp_loop_estado(self):
        """Actualiza el label de estado del panel de control cada segundo."""
        try:
            a   = self.app
            cfg = a.mem.get("config", {})
            m   = float(cfg.get("monto_base", 10))
            v   = int(cfg.get("vencimiento", cfg.get("periodo_vela", 60)))
            vm  = v // 60
            vs  = v % 60
            vs_str = f"{vm}m{vs:02d}s" if vs else f"{vm}m"
            self._cp_lbl_estado.config(
                text=f"${m:.0f} · cierre={vs_str}")
            # Refrescar colores de los toggles grandes
            try:
                self._cp_upd_sis()
                self._cp_upd_trd()
                self._cp_upd_auto()
                self._cp_upd_prac()
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.root.after(1000, self._cp_loop_estado)
        except Exception:
            pass

    def _toggle_mic(self):
        """Activa/desactiva el micrófono desde el ribbon."""
        try:
            a = self.app
            nuevo = not getattr(a, "mic_on", False)
            if hasattr(a, "set_mic"):
                self._en_hilo(a.set_mic, nuevo, True)
            elif hasattr(a, "oido") and a.oido:
                if nuevo:
                    a.oido.iniciar()
                else:
                    a.oido.detener()
        except Exception:
            pass

    def _abrir_historial(self):
        """Abre el panel de historial de trades."""
        try:
            # Intentar usar el método existente si está disponible
            if hasattr(self, "abrir_profesional"):
                self.abrir_profesional()
        except Exception:
            pass

    def _abrir_escaner(self):
        """Abre el escáner de activos."""
        try:
            a = self.app
            scanner = getattr(a, "asset_scanner", None)
            if scanner is None:
                try:
                    from . import asset_scanner as _asc
                    scanner = _asc.obtener(app=a)
                    a.asset_scanner = scanner
                except Exception:
                    pass

            def _escanear():
                try:
                    if scanner:
                        res = scanner.escanear()
                        mejor = scanner.mejor_activo()
                        a.log(f"[Escaner] Mejor activo: {mejor}")
                        if mejor:
                            simbolo = getattr(mejor, "simbolo", str(mejor))
                            a.mem["config"]["asset_actual"] = simbolo
                            from . import memoria
                            memoria.guardar(a.mem)
                            a.log(f"[Escaner] Activo cambiado a: {simbolo}")
                except Exception as e:
                    a.log(f"[Escaner] Error: {e}")

            self._en_hilo(_escanear)
        except Exception:
            pass

    def _barra_drag_start(self, event):
        self._barra_drag_x = event.x_root
        self._barra_drag_y = event.y_root
        w = self._barra_win
        self._barra_win_ox = w.winfo_x()
        self._barra_win_oy = w.winfo_y()

    def _barra_drag_move(self, event):
        dx = event.x_root - self._barra_drag_x
        dy = event.y_root - self._barra_drag_y
        x  = self._barra_win_ox + dx
        y  = self._barra_win_oy + dy
        try:
            self._barra_win.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _expandir_barra(self):
        """Cierra la barra y restaura la ventana principal de Litch."""
        self._barra_tick_activo = False
        try:
            if self._barra_win and self._barra_win.winfo_exists():
                self._barra_win.destroy()
        except Exception:
            pass
        self._barra_win = None
        try:
            self.root.deiconify()
        except Exception:
            pass

    def _barra_tick(self):
        """Refresca el estado de la barra cada 1s."""
        if not getattr(self, "_barra_tick_activo", False):
            return
        try:
            win = getattr(self, "_barra_win", None)
            if win is None or not win.winfo_exists():
                return
        except Exception:
            return
        try:
            self._barra_actualizar_estado()
        except Exception:
            pass
        try:
            self.root.after(1500, self._barra_tick)
        except Exception:
            pass

    def _barra_actualizar_estado(self):
        """
        Sincroniza el ribbon con el estado actual de la app.
        Actualiza: señal (fila 1), interruptores, override, visión, estado, WR.
        """
        a = self.app
        _BG   = "#050d18"
        _BG2  = "#091523"

        def _col(on):  return VERDE if on else "#3a3a3a"

        # ── FILA 1: Señal activa ─────────────────────────────────────────
        try:
            agente  = getattr(a, "agente", None)
            _sp     = getattr(agente, "_senal_prep", None)
            monitor = getattr(agente, "monitor", None)
            _trade  = getattr(monitor, "_trade", None) if monitor else None
            n_v     = len(a.mem.get("secuencia", []))
            periodo = int(a.mem["config"].get("periodo_vela", 60))

            import time as _t
            if _trade:
                dr  = "SUBE" if _trade.get("dir") == "V" else "BAJA"
                dur = _trade.get("duracion", 60)
                el  = _t.time() - _trade.get("inicio", _t.time())
                rem = max(0, int(dur - el))
                es_sube = _trade.get("dir") == "V"
                txt_s   = f"  {'▲' if es_sube else '▼'} {dr}  —  Trade en curso  {rem}s restantes"
                bg_s    = "#0a2a10" if es_sube else "#2a0a0a"
                fg_s    = "#00e676" if es_sube else "#ef5350"
                self._barra_senal.config(text=txt_s, bg=bg_s, fg=fg_s)
                self._barra_votos.config(bg=bg_s, text="")
                self._barra_wr.config(bg=bg_s)

            elif _sp:
                es_sube = _sp[0] == "V"
                votos   = _sp[1]
                conf    = int(getattr(agente, "_ultima_conf", 0.7) * 100)
                secs    = getattr(agente, "_secs_pre", 0)
                puntos  = "●" * min(votos, 11) + "○" * max(0, 11 - votos)
                urgente = secs <= 6 and secs > 0

                if urgente:
                    bg_s  = "#3a2a00"
                    fg_s  = "#ffd600"
                    txt_s = f"  ⚡ {'▲ SUBE' if es_sube else '▼ BAJA'}  {conf}%  ¡ACTÚA YA!  {secs}s"
                else:
                    bg_s  = "#0a2215" if es_sube else "#200a0a"
                    fg_s  = "#00e676" if es_sube else "#ef5350"
                    txt_s = (f"  {'▲ SUBE' if es_sube else '▼ BAJA'}  {conf}%  "
                             f"{'🎯' if votos >= 5 else ''}  {secs}s")

                self._barra_senal.config(text=txt_s, bg=bg_s, fg=fg_s)
                self._barra_votos.config(text=puntos, bg=bg_s,
                    fg=fg_s if votos >= 5 else "#888")
                self._barra_wr.config(bg=bg_s)

            elif not a.activo:
                self._barra_senal.config(text="  ⏸  SISTEMA PAUSADO",
                    bg=_BG, fg=GRIS)
                self._barra_votos.config(text="", bg=_BG)
            elif not a.trading_on:
                self._barra_senal.config(text="  📴  Trading desactivado",
                    bg=_BG, fg=GRIS)
                self._barra_votos.config(text="", bg=_BG)
            elif not (a.autoclick_on and a.modo_autonomo):
                self._barra_senal.config(
                    text="  👁  Observando (sin auto-click)",
                    bg=_BG, fg="#f39c12")
                self._barra_votos.config(text="", bg=_BG)
            elif n_v < 10:
                self._barra_senal.config(
                    text=f"  📊  Acumulando velas: {n_v}/10",
                    bg=_BG, fg=GRIS)
                self._barra_votos.config(text="", bg=_BG)
            else:
                tr  = int(periodo - (_t.time() % periodo))
                self._barra_senal.config(
                    text=f"  🔍  Analizando  {n_v} velas  |  siguiente cierre: {tr}s",
                    bg=_BG, fg=ACENTO)
                self._barra_votos.config(text="", bg=_BG)

            # Activo actual + modo práctica en fila 1
            try:
                activo_actual = a.mem["config"].get("asset_actual", "EUR/USD-OTC")
                practica_activa = bool(
                    getattr(a, "modo_practica", None) and a.modo_practica.activo)
                modo_txt = "  🎮 DEMO" if practica_activa else ""
                _cta_real = (a.mem["config"].get("tipo_cuenta", "demo") == "real")
                cta_txt = "  💰REAL" if _cta_real else ""
                self._barra_hora.config(
                    text=f"  {activo_actual}{modo_txt}{cta_txt}  |  "
                         f"{_t.strftime('%H:%M:%S')}  ",
                    bg="#2a0505" if _cta_real else
                       ("#1a0a00" if practica_activa else _BG),
                    fg="#ff5252" if _cta_real else
                       ("#f39c12" if practica_activa else GRIS))
                # Sincronizar botón DEMO/REAL si cambió por voz o código
                _rc_c = getattr(self, "_ribbon_cache", {})
                _cta_v = "real" if _cta_real else "demo"
                if (_rc_c.get("cta") != _cta_v
                        and getattr(self, "_btn_cuenta", None)):
                    self._btn_cuenta.config(
                        text="REAL" if _cta_real else "DEMO",
                        fg="#ff5252" if _cta_real else "#f39c12")
                    _rc_c["cta"] = _cta_v
            except Exception:
                self._barra_hora.config(
                    text=_t.strftime("  %H:%M:%S  "),
                    bg=_BG, fg=GRIS)
        except Exception:
            pass

        # ── El botón de monitor, al día ─────────────────────────────────
        # También detecta si el señor conecta o desconecta una pantalla:
        # el «1/2» pasa a «1/1» solo.
        try:
            self._sinc_boton_monitor()
        except Exception:
            pass

        # ── CADENA DE OPERACIÓN — los cinco eslabones ───────────────────
        #
        # Cada uno se comprueba de verdad, no se supone. Verde = ese
        # eslabón aguanta; rojo = ahí se rompe la cadena y por eso LITCH
        # no está operando.
        try:
            _cad = getattr(self, "_cadena_lbls", None)
            if _cad:
                _cfg = a.mem.get("config", {})

                _ok_c = bool(_cfg.get("boton_verde")
                             and _cfg.get("boton_rojo")
                             and _cfg.get("region_grafico"))

                # El motor: ¿puede llegar a los botones de IQ Option?
                _ok_m = True
                try:
                    from . import trading as _trd
                    _ok_m = not _trd._motor_iq_debe_callar(a)
                except Exception:
                    pass

                _estado = {
                    "S": bool(getattr(a, "activo", False)),
                    "T": bool(getattr(a, "trading_on", False)),
                    "A": bool(getattr(a, "autoclick_on", False)),
                    "C": _ok_c,
                    "M": _ok_m,
                }
                for _k, _bien in _estado.items():
                    _lbl = _cad.get(_k)
                    if _lbl is not None and _lbl.winfo_exists():
                        _lbl.config(fg=(VERDE if _bien else "#ef5350"))

                # Cuando los cinco están verdes se dice una vez, no en cada
                # refresco: un aviso repetido deja de ser un aviso.
                _todos = all(_estado.values())
                if _todos and not getattr(self, "_cadena_ok_dicho", False):
                    self._cadena_ok_dicho = True
                    self.log("Cadena completa: Sistema, Trading, Auto, "
                             "Calibración y Motor — LITCH puede operar.")
                elif not _todos:
                    self._cadena_ok_dicho = False
        except Exception:
            pass

        # ── FILA 2: Los 8 interruptores — sincronizar LEDs ──────────────
        try:
            practica_on = bool(
                getattr(a, "modo_practica", None) and
                a.modo_practica.activo)
            mic_on   = getattr(a, "mic_on", False)
            oido     = getattr(a, "oido", None)
            if oido:
                mic_on = getattr(oido, "escuchando", mic_on)

            _leds = [
                ("_barra_btn_sistema",  a.activo),
                ("_barra_btn_mic",      mic_on),
                ("_barra_btn_trading",  a.trading_on),
                ("_barra_btn_auto",     a.autoclick_on),
                ("_barra_btn_consejos", getattr(a, "consejos_on", True)),
                ("_barra_btn_practica", practica_on),
                ("_barra_btn_profesional",
                 bool(getattr(a, "modo_profesional", None)
                      and a.modo_profesional.activo)),
                ("_barra_btn_claude",   getattr(a, "usar_claude", False)),
                ("_barra_btn_ollama",   getattr(a, "usar_ollama", True)),
                ("_barra_btn_voz",      True),  # siempre activa (toggle idioma)
            ]
            _COL_PRAC = "#f39c12"   # naranja para práctica
            _rc = getattr(self, "_ribbon_cache", {})
            for attr, estado in _leds:
                btn = getattr(self, attr, None)
                if btn:
                    if attr == "_barra_btn_practica":
                        fg = _COL_PRAC if estado else "#3a3a3a"
                    elif attr == "_barra_btn_profesional":
                        fg = "#00e676" if estado else "#3a3a3a"
                    elif attr == "_barra_btn_claude":
                        if not mente_claude.disponible():
                            fg = "#f39c12"
                            btn.config(fg=fg, text="⚙")
                            _rc[f"led_{attr}"] = fg
                            continue
                        fg = ACENTO if estado else "#3a3a3a"
                    elif attr == "_barra_btn_ollama":
                        fg = ACENTO if estado else "#3a3a3a"
                    elif attr == "_barra_btn_voz":
                        fg = ACENTO
                    else:
                        fg = _col(estado)
                    _key = f"led_{attr}"
                    if _rc.get(_key) != fg:
                        btn.config(fg=fg, text="●")
                        _rc[_key] = fg
        except Exception:
            pass

        # Override de conciencia
        try:
            con  = getattr(a, "conciencia", None)
            modo = con.estado_override() if con else "auto"
            _tex   = {"auto": "🔄 Auto", "forzar_actuar": "▶ Activo",
                      "forzar_abstener": "⏸ Pausado"}
            _col_o = {"auto": ACENTO, "forzar_actuar": "#00e676",
                      "forzar_abstener": "#ff7043"}
            _rc = getattr(self, "_ribbon_cache", {})
            if _rc.get("ovr_modo") != modo:
                self._barra_ovr_lbl.config(
                    text=_tex.get(modo, "🔄"),
                    fg=_col_o.get(modo, ACENTO))
                _rc["ovr_modo"] = modo
        except Exception:
            pass

        # LED de visión + texto
        try:
            agente = getattr(a, "agente", None)
            streak = getattr(agente, "_color_null_streak", 0) if agente else 0
            cfg_r  = a.mem["config"].get("region_grafico")
            if not cfg_r:
                led_c, led_t = "#ffee58", "Sin calibrar"
            elif streak >= 3:
                led_c, led_t = "#ef5350", "Sin señal"
            else:
                led_c, led_t = "#00e676", "Viendo"
            _rc = getattr(self, "_ribbon_cache", {})
            if _rc.get("vis_c") != led_c:
                self._barra_vision_led.config(fg=led_c)
                self._barra_vision_txt.config(text=led_t, fg=led_c)
                _rc["vis_c"] = led_c
        except Exception:
            pass

        # WR (fila 1, derecha de señal) — recalcula cada 10 ticks (~15s)
        try:
            _rc = getattr(self, "_ribbon_cache", {})
            _wr_tick = _rc.get("wr_tick", 0)
            if _wr_tick <= 0:
                # Esto llamaba a `estadistica.winrate_reciente()`, que NO
                # EXISTE en ningún módulo. Como todo el bloque está dentro
                # de un try/except, la excepción se tragaba en silencio: el
                # indicador WR de la barra no ha funcionado nunca y nadie
                # podía saberlo. Se calcula aquí, que son cuatro líneas.
                _hist = a.mem.get("historial", []) or []
                _ult = _hist[-50:]
                _res = []
                for _op in _ult:
                    if isinstance(_op, dict):
                        _r = _op.get("resultado") or _op.get("res")
                    else:
                        _r = _op
                    if _r in ("W", "WIN", "win", True, 1):
                        _res.append(1)
                    elif _r in ("L", "LOSS", "loss", False, 0):
                        _res.append(0)
                # Con menos de 10 operaciones el porcentaje no dice nada
                wr = (sum(_res) / len(_res)) if len(_res) >= 10 else None
                _rc["wr_tick"] = 10
                if wr is not None:
                    pct_col = VERDE if wr >= 0.6 else ("#f39c12" if wr >= 0.5 else ROJO)
                    _wr_txt = f"WR {wr*100:.0f}%"
                    if _rc.get("wr_txt") != _wr_txt:
                        self._barra_wr.config(text=_wr_txt, fg=pct_col)
                        _rc["wr_txt"] = _wr_txt
            else:
                _rc["wr_tick"] = _wr_tick - 1
        except Exception:
            pass

        # ── P&L del día + trades hoy + sesión de mercado (cada 5 ticks ~7.5s) ──
        try:
            import time as _ti; import datetime as _dt
            _rc = getattr(self, "_ribbon_cache", {})
            _pnl_tick = _rc.get("pnl_tick", 0)
            if _pnl_tick <= 0:
                _rc["pnl_tick"] = 5
                hist = a.mem.get("historial", [])

                # Solo las últimas 200 entradas para evitar iterar miles
                hoy_str = _dt.date.today().isoformat()
                trades_hoy = [h for h in hist[-200:]
                              if str(h.get("fecha", ""))[:10] == hoy_str
                              or str(h.get("ts", ""))[:10] == hoy_str]

                wins_h  = sum(1 for h in trades_hoy if h.get("resultado") == "win")
                loss_h  = len(trades_hoy) - wins_h
                monto   = float(a.mem["config"].get("monto_base", 10))

                pnl = wins_h * monto * 0.85 - loss_h * monto

                if trades_hoy:
                    pnl_col  = VERDE if pnl > 0 else (ROJO if pnl < 0 else GRIS)
                    pnl_txt  = f"{'+'if pnl>=0 else ''}{pnl:.1f}$"
                    trade_txt = f"W{wins_h}/L{loss_h}"
                    _pnl_key = f"{pnl_txt}|{trade_txt}"
                    if _rc.get("pnl_key") != _pnl_key:
                        self._barra_pnl.config(text=f" {pnl_txt} ", fg=pnl_col)
                        self._barra_trades_hoy.config(text=f" {trade_txt} ", fg=GRIS)
                        _rc["pnl_key"] = _pnl_key

                # Sesión de mercado activa (UTC)
                hora_utc = _ti.gmtime().tm_hour
                if 0 <= hora_utc < 7:
                    sesion, col_s = "TYO", "#64b5f6"
                elif 7 <= hora_utc < 13:
                    sesion, col_s = "LON", "#ffca28"
                elif 13 <= hora_utc < 16:
                    sesion, col_s = "LON+NY", "#00e676"
                elif 16 <= hora_utc < 22:
                    sesion, col_s = "NY", "#ff7043"
                else:
                    sesion, col_s = "CIERRE", GRIS
                if _rc.get("sesion") != sesion:
                    self._barra_sesion.config(text=f" {sesion} ", fg=col_s)
                    _rc["sesion"] = sesion

                # Estado compacto en fila 2 (aquí dentro para compartir hist)
                n_h  = len(hist)
                wins = sum(1 for h in hist[-20:] if h.get("resultado") == "win")
                _st_txt = f"  {n_h} totales  {wins}/20 rec  "
                if _rc.get("status_txt") != _st_txt:
                    self._barra_status.config(text=_st_txt, fg=GRIS)
                    _rc["status_txt"] = _st_txt
            else:
                _rc["pnl_tick"] = _pnl_tick - 1

        except Exception:
            pass

    # ─── FIN MODO RIBBON ───────────────────────────────────────────────────────

    # --- interruptores — todos corren en daemon threads para no bloquear UI ---
    def _en_hilo(self, fn, *args, **kwargs):
        """Ejecuta fn en un daemon thread para no congelar tkinter."""
        threading.Thread(target=fn, args=args, kwargs=kwargs,
                         daemon=True, name="UICallback").start()

    def _t_sistema(self):
        self._en_hilo(self.app.set_activo, not self.app.activo, True)

    def _t_mic(self):
        self._en_hilo(self.app.set_microfono, not self.app.oido.escuchando)

    def _t_trading(self):
        self._en_hilo(self.app.set_trading, not self.app.trading_on, True)

    def _t_click(self):
        self._en_hilo(self.app.set_autoclick, not self.app.autoclick_on, True)

    def _t_consejos(self):
        self._en_hilo(self.app.set_consejos, not self.app.consejos_on)

    def _t_claude(self):
        if not mente_claude.disponible():
            self.root.after(0, self._dialogo_api_key)
            return
        self._en_hilo(self.app.set_usar_claude,
                      not getattr(self.app, "usar_claude", False), True)

    def _dialogo_api_key(self):
        """Ventana para configurar la API key de Anthropic (Fable 5)."""
        # Si ya existe abierta, la trae al frente
        if hasattr(self, "_win_apikey") and self._win_apikey.winfo_exists():
            self._win_apikey.lift()
            self._win_apikey.focus_force()
            return

        win = tk.Toplevel(self.root)
        win.title("Activar Claude Fable 5")
        self._aplicar_icono(win)
        win.configure(bg=FONDO)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        self._win_apikey = win

        # Centrar sobre la ventana principal
        self.root.update_idletasks()
        rx = self.root.winfo_rootx()
        ry = self.root.winfo_rooty()
        rw = self.root.winfo_width()
        win.geometry(f"380x310+{rx + rw + 10}+{ry}")

        _BG2 = "#0e1e30"

        # Título
        tk.Label(win, text="◆  Claude Fable 5", bg=FONDO, fg=ACENTO,
                 font=("Segoe UI", 13, "bold")).pack(pady=(16, 4))
        tk.Label(win, text="El modelo más capaz de Anthropic",
                 bg=FONDO, fg=GRIS, font=("Segoe UI", 8)).pack()
        tk.Frame(win, bg=ACENTO, height=1).pack(fill="x", padx=16, pady=10)

        # Estado actual
        _hay_key = bool(mente_claude._api_key())
        _est_txt = "✔ API key configurada" if _hay_key else "✘ Sin API key — Fable 5 inactivo"
        _est_fg  = VERDE if _hay_key else ROJO
        self._lbl_estado_key = tk.Label(win, text=_est_txt,
                                        bg=FONDO, fg=_est_fg,
                                        font=("Segoe UI", 8, "bold"))
        self._lbl_estado_key.pack(pady=(0, 10))

        # Frame del campo
        frm = tk.Frame(win, bg=_BG2, padx=14, pady=12)
        frm.pack(fill="x", padx=16)

        tk.Label(frm, text="API Key de Anthropic (sk-ant-...):",
                 bg=_BG2, fg=TEXTO, font=("Segoe UI", 8)).pack(anchor="w")

        _key_var = tk.StringVar()
        _entry = tk.Entry(frm, textvariable=_key_var,
                          show="•", width=42,
                          bg="#071422", fg=ACENTO,
                          font=("Consolas", 9),
                          relief="flat", insertbackground=ACENTO,
                          highlightthickness=1,
                          highlightcolor=ACENTO,
                          highlightbackground="#1a3a5a")
        _entry.pack(fill="x", pady=(5, 4), ipady=5)
        _entry.focus_set()

        # Checkbox mostrar/ocultar
        _mostrar_var = tk.BooleanVar(value=False)
        def _toggle_vis():
            _entry.config(show="" if _mostrar_var.get() else "•")
        tk.Checkbutton(frm, text="Mostrar key", variable=_mostrar_var,
                       command=_toggle_vis,
                       bg=_BG2, fg=GRIS, selectcolor=_BG2,
                       activebackground=_BG2, activeforeground=ACENTO,
                       font=("Segoe UI", 7), bd=0).pack(anchor="w")

        _lbl_msg = tk.Label(win, text="", bg=FONDO, fg=VERDE,
                            font=("Segoe UI", 8))
        _lbl_msg.pack(pady=(8, 4))

        def _guardar():
            key = _key_var.get().strip()
            if not key:
                _lbl_msg.config(text="Escribe la API key primero.", fg=ROJO)
                return
            if not key.startswith("sk-ant-"):
                _lbl_msg.config(
                    text="La key debe empezar con  sk-ant-...", fg=ROJO)
                return
            try:
                import json as _json
                cfg_path = mente_claude._cfg_path()
                try:
                    with open(cfg_path, encoding="utf-8") as f:
                        cfg = _json.load(f)
                except Exception:
                    cfg = {}
                cfg["api_key"] = key
                cfg["modelo"]  = "claude-fable-5"
                if "_instrucciones" not in cfg:
                    cfg["_instrucciones"] = (
                        "Pon tu API key de Anthropic aqui. "
                        "Nunca compartas este archivo.")
                with open(cfg_path, "w", encoding="utf-8") as f:
                    _json.dump(cfg, f, indent=2, ensure_ascii=False)
                _lbl_msg.config(text="✔ API key guardada — Fable 5 activo!", fg=VERDE)
                self._lbl_estado_key.config(
                    text="✔ API key configurada", fg=VERDE)
                _key_var.set("")
                # Activar Claude automáticamente
                win.after(1200, lambda: (
                    self._en_hilo(self.app.set_usar_claude, True, True),
                    win.destroy()
                ))
            except Exception as exc:
                _lbl_msg.config(text=f"Error al guardar: {exc}", fg=ROJO)

        # Botones
        btn_frame = tk.Frame(win, bg=FONDO)
        btn_frame.pack(pady=6)
        tk.Button(btn_frame, text="💾  Guardar y Activar",
                  command=_guardar,
                  bg=ACENTO, fg=FONDO, font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=14, pady=6,
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(btn_frame, text="Cerrar",
                  command=win.destroy,
                  bg=PANEL, fg=GRIS, font=("Segoe UI", 9),
                  relief="flat", padx=10, pady=6,
                  cursor="hand2").pack(side="left", padx=6)

        tk.Label(win,
                 text="Obtén tu key en: console.anthropic.com",
                 bg=FONDO, fg=GRIS, font=("Segoe UI", 7)).pack(pady=(2, 10))

        _entry.bind("<Return>", lambda _: _guardar())

    def _t_ollama(self):
        self._en_hilo(self.app.set_usar_ollama,
                      not getattr(self.app, "usar_ollama", True), True)

    def _t_profesional(self):
        """Activa/desactiva el Modo Profesional — el más precavido, para
        operar con dinero real: solo señales de máxima precisión, Kelly
        positivo, filtros de sesión y control de drawdown."""
        pro = getattr(self.app, "modo_profesional", None)
        if pro is None:
            self.app.log("[PRO] Módulo no disponible — inicia Trading primero.")
            return
        if not pro.activo:
            from tkinter import messagebox
            cuenta = self.app.mem["config"].get("tipo_cuenta", "demo")
            _extra = ("\n\n⚠ Estás en cuenta REAL: cada trade usará dinero "
                      "verdadero.") if cuenta == "real" else ""
            if not messagebox.askyesno(
                    "Modo Profesional",
                    "El Modo Profesional es el más precavido:\n\n"
                    "• Solo opera señales de máxima precisión (más votos).\n"
                    "• Exige expectativa positiva (Kelly > 0).\n"
                    "• Aplica filtros de sesión y control de drawdown.\n"
                    "• Menos operaciones, pero de mayor calidad.\n\n"
                    "Recomendado para operar con dinero real."
                    + _extra + "\n\n¿Activar Modo Profesional?"):
                return
        def _toggle():
            pro.toggle()
            try:
                self.root.after(0, self.actualizar)
            except Exception:
                pass
        self._en_hilo(_toggle)

    def _t_practica(self):
        practica = getattr(self.app, "modo_practica", None)
        if practica is None:
            self.app.log("[Practica] Modulo no disponible aun — inicia Trading primero.")
            return
        def _toggle():
            practica.toggle()
            try:
                self.root.after(0, self.actualizar)
            except Exception:
                pass
        self._en_hilo(_toggle)

    def _actualizar_banner_practica(self, activo: bool) -> None:
        try:
            practica = getattr(self.app, "modo_practica", None)
            if activo and practica:
                s = practica.stats()
                if s["trades"] > 0:
                    wr = s["wr"]
                    fg = ("#2ecc71" if wr >= 58 else
                          "#f39c12" if wr >= 47 else "#e74c3c")
                    texto = (f"  🎓 PRACTICA DEMO  "
                             f"{s['wins']}W {s['losses']}L  WR {wr:.0f}%  "
                             f"umbral≥{practica._votos_min}v  ")
                else:
                    fg    = "#f39c12"
                    texto = "  🎓 PRACTICA DEMO — esperando señal...  "
                self._banner_practica.config(text=texto, bg="#2a1500", fg=fg)
            else:
                self._banner_practica.config(text="", bg=FONDO, fg=FONDO)
        except Exception:
            pass

    def _actualizar_banner_pro(self, activo: bool) -> None:
        if activo:
            self._banner_pro.config(
                text="  MODO PROFESIONAL — FILTROS MAXIMOS  ",
                bg="#8b6914", fg="#ffd700")
        else:
            self._banner_pro.config(
                text="", bg=FONDO, fg=FONDO)

    def _actualizar_banner_cuenta(self, tipo: str = None) -> None:
        """Banner de tipo de cuenta: REAL (rojo) o DEMO (azul) o nada si no seteado."""
        try:
            if tipo is None:
                tipo = self.app.mem.get("config", {}).get("tipo_cuenta")
            if tipo == "real":
                self._banner_cuenta.config(
                    text="  ⚠  CUENTA REAL — cada trade usa dinero verdadero  ⚠  ",
                    bg="#4a0000", fg="#ff8888")
            elif tipo == "demo":
                self._banner_cuenta.config(
                    text="  🎮  CUENTA DEMO — practicando sin riesgo real  ",
                    bg="#001a33", fg="#66aaff")
            else:
                self._banner_cuenta.config(text="", bg=FONDO, fg=FONDO)
        except Exception:
            pass

    def actualizar_banner_senal(self, direccion: str, votos: int,
                               confianza: float, secs: int,
                               urgente: bool = False) -> None:
        """Muestra la señal activa directamente en la ventana de LITCH."""
        try:
            if not direccion:
                self._banner_senal.config(text="", bg=FONDO, fg=FONDO)
                return
            es    = direccion in ("V", "VERDE", "UP")
            flech = "▲ SUBE" if es else "▼ BAJA"
            pct   = int(confianza * 100)
            dots  = "●" * votos + "○" * (7 - votos)
            if urgente and secs <= 6:
                texto  = f"  ⚡ {flech}  {pct}%  ¡ACTÚA YA! {secs}s  "
                bg_col = "#7f0000" if not es else "#004d1a"
                fg_col = "#ffff00"
            else:
                texto  = f"  {flech}  {pct}%  {dots}  {secs}s  "
                bg_col = "#003300" if es else "#330000"
                fg_col = "#00ff88" if es else "#ff4444"
            self._banner_senal.config(text=texto, bg=bg_col, fg=fg_col)
        except Exception:
            pass

    def _actualizar_banner_meta(self) -> None:
        """Muestra el progreso de la Meta Diaria en el banner."""
        try:
            meta = getattr(self.app, "meta_diaria", None)
            if not meta or not meta.activa:
                self._banner_meta.config(text="", bg=FONDO, fg=FONDO)
                return
            s    = meta.stats()
            pnl  = s["pnl"]
            sgn  = "+" if pnl >= 0 else ""
            if pnl >= 0:
                limite = s["meta_gan"]
                color_bg = "#003300"
                color_fg = "#00ff88"
                icono    = "🎯"
            else:
                limite = s["stop_perd"]
                color_bg = "#330000"
                color_fg = "#ff4444"
                icono    = "⛔"
            pct   = min(100, int(abs(pnl) / max(limite, 0.01) * 100))
            barra = "█" * (pct // 10) + "░" * (10 - pct // 10)
            texto = (f"  {icono} META  {sgn}${pnl:.2f} / ${limite:.0f}  "
                     f"[{barra}] {pct}%  "
                     f"{s['wins']}W {s['losses']}L  ")
            if s["completada"]:
                texto = f"  ✅ TAREA COMPLETADA  {sgn}${pnl:.2f}  "
                color_bg, color_fg = "#004400", "#88ff88"
            self._banner_meta.config(text=texto, bg=color_bg, fg=color_fg)
        except Exception:
            pass

    # ── Modo compacto / expandido ──────────────────────────────────────────
    def _t_compacto(self):
        if self._compacto:
            self._modo_expandido()
        else:
            self._modo_compacto()

    def _modo_compacto(self):
        """Ventana pequeña (~220×390) siempre visible al lado de IQ Option."""
        self._compacto = True
        self._btn_compacto.config(text="⊡")
        # Ocultar gauge+log; pie queda anclado abajo (side="bottom") sin repack
        self._frame_expandible.pack_forget()
        ancho, alto = 220, 390
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"{ancho}x{alto}+{sw - ancho - 14}+10")
        self.root.attributes("-topmost", True)

    def _modo_expandido(self):
        """Restaurar ventana normal con log y gauge completos."""
        self._compacto = False
        self._btn_compacto.config(text="⊟")
        # Reponer frame expandible; pie ya está side="bottom" — no repack
        self._frame_expandible.pack(fill="both", expand=True)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        a, b_ = self._ancho_full, self._alto_full
        self.root.geometry(f"{a}x{b_}+{sw - a - 14}+{sh - b_ - 60}")
        self.root.attributes("-topmost", True)

    def _t_idioma(self):
        nuevo = "en" if self.app.idioma == "es" else "es"
        self.app.set_idioma(nuevo)

    def _t_modo_rostro(self):
        self._modo_rostro = not self._modo_rostro
        if self.orbe:
            self.orbe.set_modo_rostro(self._modo_rostro)
        icono = "🧠" if self._modo_rostro else "😶"
        try:
            self._btn_rostro.config(text=icono,
                                    fg=ACENTO if self._modo_rostro else GRIS)
        except Exception:
            pass

    def actualizar(self):
        def pintar(clave, encendido, nombre):
            color = VERDE if encendido else ROJO
            self.botones[clave].config(
                text=f"{nombre}  {'●' if encendido else '○'}", fg=color)
        pintar("sistema", self.app.activo, "Sistema")
        # Micrófono: verde=escuchando, ámbar=grabando activo
        grabando = getattr(self.app.oido, "grabando", False)
        if grabando:
            self.botones["mic"].config(text="Micrófono  ◉ REC", fg="#f39c12")
        else:
            pintar("mic", self.app.oido.escuchando, "Micrófono")
        pintar("trading", self.app.trading_on, "Trading")
        pintar("click", self.app.autoclick_on, "Auto-click")
        pintar("consejos", getattr(self.app, "consejos_on",   True),  "Consejos")
        if not mente_claude.disponible():
            self.botones["claude"].config(
                text="Claude ✦  ⚙", fg="#f39c12")
        else:
            pintar("claude", getattr(self.app, "usar_claude", False), "Claude ✦")
        pintar("ollama",   getattr(self.app, "usar_ollama",  True),  "Ollama")
        # Práctica DEMO — naranja cuando activo
        practica = getattr(self.app, "modo_practica", None)
        practica_on = bool(practica and practica.activo)
        col_p = "#f39c12" if practica_on else ROJO
        self.botones["practica"].config(
            text=f"Practica  {'●' if practica_on else '○'}", fg=col_p)
        if grabando:
            estado, color = "● Capturando voz...", "#f39c12"
        elif not self.app.activo:
            estado, color = "En espera (pausado)", GRIS
        elif self.app.autoclick_on and self.app.modo_autonomo:
            estado, color = "⚡ Autonomo ACTIVO · " + ("EN" if self.app.idioma == "en" else "ES"), VERDE
        elif self.app.modo_autonomo:
            estado, color = "Autonomo · " + ("EN" if self.app.idioma == "en" else "ES"), ACENTO
        else:
            estado, color = "Sistemas en linea · " + ("EN" if self.app.idioma == "en" else "ES"), VERDE
        self.lbl_estado.config(text=estado, fg=color)
        # Actualizar botón de idioma
        try:
            idioma_txt = "🌐 EN" if self.app.idioma == "en" else "🌐 ES"
            self._btn_idioma.config(text=idioma_txt, fg=ACENTO)
        except Exception:
            pass
        # Sincronizar etiqueta de override de conciencia
        try:
            self._sincronizar_ovr_lbl()
        except Exception:
            pass

    # --- barra de estado tiempo real ------------------------------------
    def _loop_status_rt(self):
        """Refresca cada 800ms la barra que muestra qué hace Litch en este momento."""
        try:
            a   = self.app
            agente = getattr(a, "agente", None)
            txt = "⏸ En espera"
            col = GRIS

            if not a.activo:
                txt, col = "⏸ Pausado", GRIS
            elif not a.trading_on:
                txt, col = "📴 Trading desactivado — pulsa Trading para activar", GRIS
            elif not (a.autoclick_on and a.modo_autonomo):
                txt, col = "👁 Observando (sin auto-click)", "#f39c12"
            elif agente is not None:
                # Leer el estado interno del agente de trading
                n_velas = len(a.mem.get("secuencia", []))
                periodo = int(a.mem["config"].get("periodo_vela", 60))

                # ¿Hay un trade activo abierto?
                import time as _t2
                monitor = getattr(agente, "monitor", None)
                _trade  = getattr(monitor, "_trade", None) if monitor else None
                if _trade:
                    dir_t    = _trade.get("dir", "?")
                    dur      = _trade.get("duracion", 60)
                    elapsed  = _t2.time() - _trade.get("inicio", _t2.time())
                    restando = max(0, int(dur - elapsed))
                    icon_t   = "📈" if dir_t == "V" else "📉"
                    txt  = (f"{icon_t} Trade {'SUBE' if dir_t=='V' else 'BAJA'} "
                            f"| {restando}s restantes")
                    col  = "#2ecc71" if dir_t == "V" else "#e74c3c"

                # ¿Pre-calculando señal?
                elif getattr(agente, "_en_precalculo", False):
                    txt = f"⚡ Pre-calculando señal ({n_velas} velas)..."
                    col = "#f39c12"

                # ¿Señal pre-calculada lista?
                elif getattr(agente, "_senal_prep", None):
                    _sp = agente._senal_prep
                    _dir_p = "SUBE" if _sp[0] == "V" else "BAJA"
                    txt = f"🎯 Señal lista: {_dir_p} | {_sp[1]}/11 votos — esperando cierre vela"
                    col = VERDE

                # ¿Acumulando velas?
                elif n_velas < 10:
                    txt = f"📊 Acumulando velas: {n_velas}/10 mín..."
                    col = GRIS
                else:
                    # Calcular tiempo para el próximo cierre de vela
                    import time as _t
                    t_en = _t.time() % periodo
                    t_restante = int(periodo - t_en)
                    txt = f"🔍 Analizando patrón ({n_velas} velas) | próximo cierre en {t_restante}s"
                    col = ACENTO
            else:
                txt, col = "⏸ Iniciando...", GRIS

            self._lbl_status_rt.config(text=f"  {txt}", fg=col)
        except Exception:
            pass
        try:
            self.root.after(800, self._loop_status_rt)
        except Exception:
            pass

    # --- gauge circular de precisión ------------------------------------
    def _dibujar_gauge(self, pct: float):
        """Dibuja un arco circular 0-100% con color según precisión."""
        c = self._gauge_canvas
        c.delete("all")
        cx, cy, r = 40, 40, 32
        # Fondo del arco (gris oscuro)
        c.create_arc(cx-r, cy-r, cx+r, cy+r,
                     start=0, extent=360,
                     outline=PANEL, width=8, style="arc")
        # Color por rango: rojo <50%, amarillo 50-65%, verde >65%
        if pct < 50:
            color = "#e74c3c"
        elif pct < 65:
            color = "#f4a261"
        else:
            color = "#2ecc71"
        # Arco de progreso (desde las 12 en punto = 90°, sentido horario)
        extent = (pct / 100.0) * 360.0
        c.create_arc(cx-r, cy-r, cx+r, cy+r,
                     start=90, extent=-extent,
                     outline=color, width=8, style="arc")
        # Texto del porcentaje en el centro
        c.create_text(cx, cy, text=f"{pct:.0f}%",
                      fill=color, font=("Segoe UI", 10, "bold"))

    def _actualizar_gauge_loop(self):
        """Actualiza el gauge cada 10 segundos con los datos de la Red Maestra."""
        try:
            s = self.app.red.progreso()
            pct = s.get("rolling_50", 50.0)
            self._dibujar_gauge(pct)
            self._lbl_gauge_pct.config(
                text=f"{pct:.1f}%",
                fg=("#2ecc71" if pct >= 65 else "#f4a261" if pct >= 50 else "#e74c3c"))
            total = s.get("total", 0)
            sub   = f"R50 | {total} velas"
            self._lbl_gauge_sub.config(text=sub)
            tend  = s.get("tendencia", "—")
            tend_col = {"mejorando": "#2ecc71", "empeorando": "#e74c3c"}.get(tend, GRIS)
            self._lbl_gauge_tend.config(text=tend, fg=tend_col)
        except Exception:
            pass
        try:
            self.root.after(10000, self._actualizar_gauge_loop)
        except Exception:
            pass

    def _loop_banners_autonomia(self):
        """Refresca banners de práctica y meta cada 15 s con datos en vivo."""
        try:
            practica = getattr(self.app, "modo_practica", None)
            if practica and practica.activo:
                self._actualizar_banner_practica(True)
            self._actualizar_banner_meta()
            self._actualizar_banner_cuenta()
        except Exception:
            pass
        self._compactar_banners()
        try:
            self.root.after(15000, self._loop_banners_autonomia)
        except Exception:
            pass

    def _compactar_banners(self):
        """Oculta los banners vacíos para que no dejen huecos.

        Son cinco etiquetas (práctica, pro, meta, señal, cuenta) que casi
        siempre están vacías. Aun sin texto, cada una ocupa la altura de
        una línea: entre los interruptores y la fila de Conciencia se veía
        un hueco de casi cien píxeles sin nada.

        Esto se limita a empaquetarlas o desempaquetarlas según tengan
        contenido, así que no hay que tocar ninguno de los sitios donde se
        les asigna el texto.
        """
        nombres = ("_banner_practica", "_banner_pro", "_banner_meta",
                   "_banner_senal", "_banner_cuenta")

        # El orden original hay que guardarlo ANTES de desempaquetar nada.
        # Si luego se vuelve a empaquetar con un pack() a secas, el widget
        # se va al FINAL del panel en vez de a su sitio. Con `before` se
        # devuelve exactamente donde estaba.
        if not getattr(self, "_orden_banners", None):
            try:
                self._orden_banners = list(self.root.pack_slaves())
            except Exception:
                self._orden_banners = []

        orden = self._orden_banners

        def _vecino(w):
            """El primer hermano visible que va después de w."""
            try:
                i = orden.index(w)
            except (ValueError, AttributeError):
                return None
            for otro in orden[i + 1:]:
                try:
                    if otro.winfo_exists() and otro.winfo_ismapped():
                        return otro
                except Exception:
                    continue
            return None

        for nombre in nombres:
            w = getattr(self, nombre, None)
            if w is None:
                continue
            try:
                if not w.winfo_exists():
                    continue
                tiene = bool((w.cget("text") or "").strip())
                visible = bool(w.winfo_ismapped())
                if tiene and not visible:
                    ref = _vecino(w)
                    if ref is not None:
                        w.pack(fill="x", padx=8, before=ref)
                    else:
                        w.pack(fill="x", padx=8)
                elif not tiene and visible:
                    w.pack_forget()
            except Exception:
                pass

    def _loop_mic_status(self):
        """Refresca el botón de micrófono cada 500ms para mostrar ◉ REC."""
        try:
            grabando = getattr(self.app.oido, "grabando", False)
            if grabando:
                self.botones["mic"].config(text="Microfono  ◉ REC", fg="#f39c12")
                self.lbl_estado.config(text="● Capturando voz...", fg="#f39c12")
            elif self.app.oido.escuchando:
                self.botones["mic"].config(text="Microfono  ●", fg=VERDE)
            self.root.after(500, self._loop_mic_status)
        except Exception:
            pass

    # --- Interactive Brokers: los cuatro botones del grupo IBKR ----------

    def abrir_panel_simple(self):
        """Abre la ventana sencilla: lo esencial, en grande y en claro."""
        try:
            from . import panel_simple
            self.log(panel_simple.abrir(self.app, self.root))
        except Exception as e:
            self.log(f"No pude abrir el panel sencillo: {e}")

    def calibrar_ticket_tws(self):
        """Litch aprende dónde está cada campo del ticket en ESTA pantalla."""
        try:
            from . import piloto_tws
            self.log(piloto_tws.calibrar_ticket(self.app))
        except Exception as e:
            self.log(f"No pude iniciar la calibración: {e}")

    def ver_pantalla_completa(self):
        """Litch describe todo el monitor. Puede tardar: va en su hilo."""
        def _t():
            try:
                from . import conciencia_pantalla
                texto = conciencia_pantalla.describir_pantalla(self.app)
            except Exception as e:
                texto = f"No pude leer la pantalla: {e}"
            self.log(texto)
            try:
                self.app.decir(texto)
            except Exception:
                pass

        self.log("Mirando toda la pantalla…")
        threading.Thread(target=_t, daemon=True,
                         name="LitchVerPantalla").start()

    # ── Aprendizaje activo de IBKR ────────────────────────────────────────

    _COLOR_APR = {
        "gris":    "#5a6b7a",   # sin empezar
        "naranja": "#f39c12",   # aprendiendo
        "azul":    "#2196f3",   # domina la pantalla
    }

    def _pintar_aprendizaje(self):
        """El color del botón sale del progreso REAL, no de un contador.

        Azul solo cuando LITCH ha verificado con el ratón dónde está cada
        cosa. No se regala por haber leído el manual.
        """
        b = getattr(self, "_btn_aprendizaje", None)
        if b is None:
            return
        try:
            if not b.winfo_exists():
                return
        except Exception:
            return
        try:
            from . import aprendizaje_ibkr as _ai
            col = _ai.color(self.app)
            p = _ai.progreso(self.app)
            b.config(fg=self._COLOR_APR.get(col, "#5a6b7a"))
            # El propio botón cuenta el progreso al posar el ratón
            b.config(text="🧠" if col != "azul" else "🧠")
            self._apr_pct = p["pct"]
        except Exception:
            pass

    # ── Piloto autónomo ───────────────────────────────────────────────────

    _COLOR_AUT = {
        "gris":    "#5a6b7a",   # apagado
        "naranja": "#f39c12",   # aprendiendo, sin ejecutar
        "azul":    "#2196f3",   # ejecutando en simulada
        "verde":   "#2ecc71",   # nivel máximo
    }

    def _pintar_autonomo(self):
        """El color del botón sale del NIVEL alcanzado, no de un contador."""
        b = getattr(self, "_btn_autonomo", None)
        if b is None:
            return
        try:
            if not b.winfo_exists():
                return
            from . import piloto_autonomo as _pa
            b.config(fg=self._COLOR_AUT.get(_pa.color(self.app), "#5a6b7a"))
        except Exception:
            pass

    def alternar_piloto_autonomo(self):
        """Enciende o apaga el piloto autónomo.

        Antes de ejecutar por primera vez pide confirmación explícita:
        que LITCH mande órdenes solo, aunque sean simuladas, es un salto
        que merece un «sí» consciente y no un clic distraído.
        """
        def _t():
            try:
                from . import piloto_autonomo as _pa
                p = _pa.obtener(self.app)

                # Si va a ejecutar y aún no lo ha hecho nunca, preguntar
                if (not p.activo and p.nivel >= 2
                        and not self.app.mem.get("config", {})
                                     .get("autonomo_confirmado")):
                    from tkinter import messagebox
                    niv = _pa.NIVELES[p.nivel]
                    ok = messagebox.askyesno(
                        "Piloto autónomo — ejecutará operaciones",
                        f"LITCH está en nivel {p.nivel} ({niv['nombre']}) y "
                        f"a partir de aquí ENVÍA ÓRDENES por su cuenta.\n\n"
                        f"· Hasta {niv['ops_dia']} operación(es) al día\n"
                        f"· Solo en: {', '.join(niv['activos'])}\n"
                        f"· Solo en la cuenta SIMULADA (verificada por API)\n"
                        f"· Siempre con stop y objetivo puestos\n\n"
                        f"Si el resultado acumulado baja de −5R, bajará "
                        f"solo de nivel y dejará de ejecutar.\n\n"
                        f"¿Le autoriza a operar solo?",
                        parent=self.root)
                    if not ok:
                        self.log("Piloto autónomo: no autorizado. "
                                 "Sigue sin ejecutar.")
                        return
                    self.app.mem["config"]["autonomo_confirmado"] = True
                    try:
                        from . import memoria as _mem
                        _mem.guardar(self.app.mem)
                    except Exception:
                        pass

                texto = _pa.alternar(self.app)
            except Exception as e:
                texto = f"No pude con el piloto autónomo: {e}"

            self.log(texto)
            try:
                self.app.decir(texto.split("\n")[0])
            except Exception:
                pass
            try:
                self.root.after(0, self._pintar_autonomo)
                self.root.after(0, self._seguir_autonomo)
            except Exception:
                pass

        self.log("Preparando el piloto autónomo…")
        threading.Thread(target=_t, daemon=True,
                         name="LitchPilotoAutonomo").start()

    def _seguir_autonomo(self):
        """Repinta el botón cada 10 s mientras el piloto esté activo."""
        try:
            from . import piloto_autonomo as _pa
            self._pintar_autonomo()
            if _pa.obtener(self.app).activo:
                self.root.after(10000, self._seguir_autonomo)
        except Exception:
            pass

    def alternar_aprendizaje_ibkr(self):
        """Enciende o apaga el aprendizaje activo. Va en su hilo."""
        def _t():
            try:
                from . import aprendizaje_ibkr as _ai
                texto = _ai.alternar(self.app)
            except Exception as e:
                texto = f"No pude con el aprendizaje: {e}"
            self.log(texto)
            try:
                self.app.decir(texto.split("\n")[0])
            except Exception:
                pass
            # Refrescar el color y seguir refrescándolo mientras aprende
            try:
                self.root.after(0, self._pintar_aprendizaje)
                self.root.after(0, self._seguir_aprendizaje)
            except Exception:
                pass

        self.log("Preparando el aprendizaje de Interactive Brokers…")
        threading.Thread(target=_t, daemon=True,
                         name="LitchAprendizajeIBKR").start()

    def _seguir_aprendizaje(self):
        """Repinta el botón cada 5 s mientras el aprendizaje esté activo."""
        try:
            from . import aprendizaje_ibkr as _ai
            self._pintar_aprendizaje()
            if _ai.obtener(self.app).activo:
                self.root.after(5000, self._seguir_aprendizaje)
        except Exception:
            pass

    def leccion_ibkr(self):
        """La siguiente lección de la escuela de Interactive Brokers."""
        try:
            from . import escuela_ibkr
            texto = escuela_ibkr.siguiente_leccion(self.app)
            self.log(texto)
            try:
                self.app.decir(texto.split("\n\n")[0])
            except Exception:
                pass
        except Exception as e:
            self.log(f"No pude dar la lección: {e}")

    # --- registro -------------------------------------------------------
    _LOG_MAX_LINEAS = 400   # el log nunca crece sin límite (evita lag en sesiones largas)

    def log(self, texto):
        def _añadir():
            import time as _t
            # Blindaje: al cerrar Litch los widgets se destruyen pero pueden
            # quedar logs en cola → TclError "invalid command name". Si la
            # caja ya no existe, escribimos en consola y salimos limpio.
            try:
                if not self.caja_log.winfo_exists():
                    print(texto)
                    return
            except Exception:
                print(texto)
                return
            self.caja_log.config(state="normal")
            self.caja_log.insert("end", f"[{_t.strftime('%H:%M:%S')}] {texto}\n")
            # Recortar líneas viejas: mantiene la UI fluida en sesiones de horas
            try:
                n_lineas = int(self.caja_log.index("end-1c").split(".")[0])
                if n_lineas > self._LOG_MAX_LINEAS:
                    self.caja_log.delete("1.0", f"{n_lineas - self._LOG_MAX_LINEAS}.0")
            except Exception:
                pass
            self.caja_log.see("end")
            self.caja_log.config(state="disabled")
        try:
            self.root.after(0, _añadir)
        except Exception:
            print(texto)

    # --- chat -------------------------------------------------------------
    def abrir_chat(self):
        if self._chat is not None and tk.Toplevel.winfo_exists(self._chat):
            self._chat.lift()
            self._chat.focus_force()
            return
        v = tk.Toplevel(self.root)
        self._chat = v
        v.title("Chat con Litch")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("480x520")
        v.attributes("-topmost", True)
        v.resizable(True, True)

        # Área de mensajes
        caja = scrolledtext.ScrolledText(v, bg=PANEL, fg=TEXTO, wrap="word",
                                         font=("Segoe UI", 10), relief="flat",
                                         state="disabled", padx=8, pady=8)
        caja.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        caja.tag_config("yo",    foreground=VERDE,  font=("Segoe UI", 10, "bold"))
        caja.tag_config("litch", foreground=ACENTO, font=("Segoe UI", 10))
        caja.tag_config("sys",   foreground=GRIS,   font=("Segoe UI", 9, "italic"))

        # Pista de voz
        lbl_mic = tk.Label(v,
            text="Mic activo: dile «Litch, [tu pregunta]» — o escribe aquí directamente.",
            bg=FONDO, fg=GRIS, font=("Segoe UI", 8))
        lbl_mic.pack(anchor="w", padx=10)

        # Fila de entrada
        marco = tk.Frame(v, bg=FONDO)
        marco.pack(fill="x", padx=8, pady=(4, 8))
        entrada = tk.Entry(marco, bg=PANEL, fg=TEXTO, font=("Segoe UI", 11),
                           relief="flat", insertbackground=TEXTO)
        entrada.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 6))

        def escribir(quien, texto, tag):
            caja.config(state="normal")
            caja.insert("end", f"{quien}: ", tag)
            caja.insert("end", texto + "\n\n", "")
            caja.see("end")
            caja.config(state="disabled")

        btn_enviar = tk.Button(marco, text="Enviar ↵", bg=ACENTO, fg=FONDO,
                               relief="flat", font=("Segoe UI", 10, "bold"),
                               cursor="hand2", padx=10)
        btn_enviar.pack(side="right")

        def _desbloquear():
            """Siempre re-habilita la entrada — aunque haya ocurrido un error."""
            try:
                entrada.config(state="normal")
                btn_enviar.config(state="normal", text="Enviar ↵")
                entrada.focus_force()
            except Exception:
                pass

        def enviar(_=None):
            texto = entrada.get().strip()
            if not texto:
                return
            if btn_enviar.cget("state") == "disabled":
                return  # ya hay un mensaje procesándose
            entrada.delete(0, "end")
            entrada.config(state="disabled")
            btn_enviar.config(state="disabled", text="💭 …")
            escribir("Tú", texto, "yo")

            def en_hilo():
                try:
                    respuesta = self.app.entrada_chat(texto)
                    resp_txt = respuesta or "(sin respuesta)"
                except Exception as exc:
                    resp_txt = f"(error interno: {exc})"
                def finalizar():
                    escribir("Litch", resp_txt, "litch")
                    _desbloquear()
                try:
                    v.after(0, finalizar)
                except Exception:
                    pass  # ventana cerrada

            threading.Thread(target=en_hilo, daemon=True,
                             name="LitchChat").start()

        btn_enviar.config(command=enviar)
        entrada.bind("<Return>", enviar)
        # Clic en el marco vuelve a dar foco a la entrada
        marco.bind("<Button-1>", lambda e: entrada.focus_force())

        escribir("Litch",
                 "Hola señor, canal de texto abierto. ¿En qué le ayudo?\n"
                 "Puede preguntarme sobre el mercado, buscar noticias, "
                 "precio de activos, recordatorios, o cualquier cosa.", "litch")
        escribir("Sistema",
                 "Comandos útiles: «ayuda» · «estado» · «noticias» · «precio AAPL» · "
                 "«investiga sobre X» · «busca X» · «hora»", "sys")
        entrada.focus_force()

    # --- lotería ------------------------------------------------------------
    def abrir_loteria(self):
        if not hasattr(self, "_ventana_loterias") or self._ventana_loterias is None:
            from . import ventana_loterias as _vl
            self._ventana_loterias = _vl.VentanaLoterias(self.root, self.app)
        self._ventana_loterias.abrir()

    # --- calibración -----------------------------------------------------------
    def abrir_calibracion(self):
        v = tk.Toplevel(self.root)
        v.title("Visión avanzada — Litch ve el broker")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("480x580")
        v.attributes("-topmost", True)

        # ── Estado en tiempo real de lo que Litch ve ahora ────────────────────
        cfg = self.app.mem["config"]

        estado_frame = tk.Frame(v, bg="#051a10", bd=1, relief="solid")
        estado_frame.pack(fill="x", padx=12, pady=(10, 4))

        def _color_coord(val):
            return VERDE if val else "#555"

        bv  = cfg.get("boton_verde")
        br  = cfg.get("boton_rojo")
        rg  = cfg.get("region_grafico")
        bv2 = cfg.get("boton_verde_2")

        lbl_titulo_est = tk.Label(estado_frame,
            text="◉ Lo que Litch ve AHORA en pantalla (se actualiza solo)",
            bg="#051a10", fg=VERDE, font=("Consolas", 8, "bold"))
        lbl_titulo_est.pack(anchor="w", padx=8, pady=(4, 2))

        lbl_bv = tk.Label(estado_frame,
            text=f"  SUBE :  {bv[0]},{bv[1]}" if bv else "  SUBE :  buscando...",
            bg="#051a10", fg=_color_coord(bv), font=("Consolas", 8))
        lbl_bv.pack(anchor="w", padx=8)

        lbl_br = tk.Label(estado_frame,
            text=f"  BAJA :  {br[0]},{br[1]}" if br else "  BAJA :  buscando...",
            bg="#051a10", fg=_color_coord(br), font=("Consolas", 8))
        lbl_br.pack(anchor="w", padx=8)

        lbl_rg = tk.Label(estado_frame,
            text=(f"  Gráfico: [{rg[0]},{rg[1]} → {rg[2]},{rg[3]}]"
                  if rg else "  Gráfico: buscando..."),
            bg="#051a10", fg=_color_coord(rg), font=("Consolas", 8))
        lbl_rg.pack(anchor="w", padx=8)

        if bv2:
            lbl_bv2 = tk.Label(estado_frame,
                text=f"  SUBE2: {bv2[0]},{bv2[1]} (2ª gráfica)",
                bg="#051a10", fg=VERDE, font=("Consolas", 8))
            lbl_bv2.pack(anchor="w", padx=8)

        def _refrescar_estado():
            """Actualiza las etiquetas con lo que hay en config ahora."""
            try:
                _bv = cfg.get("boton_verde")
                _br = cfg.get("boton_rojo")
                _rg = cfg.get("region_grafico")
                lbl_bv.config(
                    text=f"  SUBE :  {_bv[0]},{_bv[1]}" if _bv else "  SUBE :  buscando...",
                    fg=_color_coord(_bv))
                lbl_br.config(
                    text=f"  BAJA :  {_br[0]},{_br[1]}" if _br else "  BAJA :  buscando...",
                    fg=_color_coord(_br))
                lbl_rg.config(
                    text=(f"  Gráfico: [{_rg[0]},{_rg[1]} → {_rg[2]},{_rg[3]}]"
                          if _rg else "  Gráfico: buscando..."),
                    fg=_color_coord(_rg))
                v.after(2000, _refrescar_estado)
            except Exception:
                pass

        v.after(2000, _refrescar_estado)

        tk.Label(v, text=(
            "✓ SUBE y BAJA se detectan solos — no necesitas calibrar manualmente.\n"
            "  Solo calibra las secciones ⬇ de salida anticipada si las vas a usar."),
            bg=FONDO, fg="#7cfc00", font=("Consolas", 8), wraplength=440,
            justify="left").pack(padx=12, pady=(6, 2))

        temp = {"g1": None, "g2": None}
        filas = tk.Frame(v, bg=FONDO)
        filas.pack(padx=12, fill="x")

        def fila(texto, clave_etiqueta):
            f = tk.Frame(filas, bg=FONDO)
            f.pack(fill="x", pady=3)
            etiqueta = tk.Label(f, text="—", bg=FONDO, fg=GRIS, font=FUENTE,
                                width=14, anchor="e")
            etiqueta.pack(side="right")
            boton = tk.Button(f, text=texto, bg=PANEL, fg=TEXTO, font=FUENTE,
                              relief="flat", cursor="hand2", anchor="w",
                              padx=8, pady=4)
            boton.pack(side="left", fill="x", expand=True)
            return boton, etiqueta

        def capturar(etiqueta, destino):
            if not _PG_OK:
                etiqueta.config(text="sin pyautogui", fg=ROJO)
                return

            def cuenta(n):
                if n > 0:
                    etiqueta.config(text=f"capturando en {n}…", fg=ACENTO)
                    v.after(1000, cuenta, n - 1)
                else:
                    p = pyautogui.position()
                    destino(p.x, p.y)
                    etiqueta.config(text=f"({p.x}, {p.y})", fg=VERDE)
                    self._guardar_region(temp)
            cuenta(5)

        b1, e1 = fila("1) Esquina SUPERIOR-IZQUIERDA del gráfico", "g1")
        b1.config(command=lambda: capturar(e1, lambda x, y: temp.update(g1=(x, y))))
        b2, e2 = fila("2) Esquina INFERIOR-DERECHA del gráfico", "g2")
        b2.config(command=lambda: capturar(e2, lambda x, y: temp.update(g2=(x, y))))
        b3, e3 = fila("3) Botón VERDE (Compra)", "bv")
        b3.config(command=lambda: capturar(
            e3, lambda x, y: self._guardar_boton("boton_verde", x, y)))
        b4, e4 = fila("4) Botón ROJO (Venta)", "br")
        b4.config(command=lambda: capturar(
            e4, lambda x, y: self._guardar_boton("boton_rojo", x, y)))

        # ── 5a) Botón Vender anticipado (preferido — sin confirmación) ────────
        tk.Label(v, text="⬇ Salidas automáticas de emergencia (calibrar al menos una)",
                 bg=FONDO, fg="#888", font=("Consolas", 9)).pack(anchor="w", padx=18)
        f_vd = tk.Frame(v, bg=FONDO)
        f_vd.pack(fill="x", padx=18, pady=(0, 2))
        tk.Label(f_vd, text="5a) Botón Vender anticipado  ★ PREFERIDO",
                 bg=FONDO, fg="#00d4aa", font=FUENTE).pack(side="left")
        e_vd_val = cfg.get("boton_vender")
        lbl_vd   = tk.Label(f_vd,
                             text=f"({e_vd_val[0]},{e_vd_val[1]})" if e_vd_val else "Sin calibrar",
                             bg=FONDO, fg=VERDE if e_vd_val else "#888", font=FUENTE)
        lbl_vd.pack(side="left", padx=8)
        tk.Button(f_vd, text="Capturar", bg=PANEL, fg=TEXTO, relief="flat",
                  font=FUENTE, cursor="hand2",
                  command=lambda: capturar(
                      lbl_vd, lambda x, y: self._guardar_extra("boton_vender", x, y, lbl_vd))
                  ).pack(side="right")

        # ── 5b) Botón Rollover (extiende el trade, dobla el monto) ─────────
        f_rl = tk.Frame(v, bg=FONDO)
        f_rl.pack(fill="x", padx=18, pady=(0, 2))
        tk.Label(f_rl, text="5b) Botón Rollover  (⚠ extiende y dobla monto)",
                 bg=FONDO, fg="#e0a000", font=FUENTE).pack(side="left")
        e_rl_val = cfg.get("boton_rollover")
        lbl_rl   = tk.Label(f_rl,
                             text=f"({e_rl_val[0]},{e_rl_val[1]})" if e_rl_val else "Sin calibrar",
                             bg=FONDO, fg=VERDE if e_rl_val else "#888", font=FUENTE)
        lbl_rl.pack(side="left", padx=8)
        tk.Button(f_rl, text="Capturar", bg=PANEL, fg=TEXTO, relief="flat",
                  font=FUENTE, cursor="hand2",
                  command=lambda: capturar(
                      lbl_rl, lambda x, y: self._guardar_extra("boton_rollover", x, y, lbl_rl))
                  ).pack(side="right")

        # ── 5c) Botón CONFIRMAR PRÓRROGA (diálogo emergente del Rollover) ──
        f_cr = tk.Frame(v, bg=FONDO)
        f_cr.pack(fill="x", padx=18, pady=(0, 4))
        tk.Label(f_cr, text="5c) CONFIRMAR PRÓRROGA  (diálogo de Rollover)",
                 bg=FONDO, fg="#e0a000", font=FUENTE).pack(side="left")
        e_cr_val = cfg.get("boton_confirmar_rollover")
        lbl_cr   = tk.Label(f_cr,
                             text=f"({e_cr_val[0]},{e_cr_val[1]})" if e_cr_val else "Sin calibrar",
                             bg=FONDO, fg=VERDE if e_cr_val else "#888", font=FUENTE)
        lbl_cr.pack(side="left", padx=8)
        tk.Label(f_cr, text="(abre un trade en rojo, ve al diálogo y captura)",
                 bg=FONDO, fg="#555", font=("Consolas", 8)).pack(side="left", padx=4)
        tk.Button(f_cr, text="Capturar", bg=PANEL, fg=TEXTO, relief="flat",
                  font=FUENTE, cursor="hand2",
                  command=lambda: capturar(
                      lbl_cr,
                      lambda x, y: self._guardar_extra("boton_confirmar_rollover", x, y, lbl_cr))
                  ).pack(side="right")

        # ── Calibración región P&L (área verde/rojo del resultado) ────────
        f_pl = tk.Frame(v, bg=FONDO)
        f_pl.pack(fill="x", padx=18, pady=(0, 6))
        tk.Label(f_pl, text="6) Área P&L (resultado del trade)",
                 bg=FONDO, fg="#e0a000", font=FUENTE).pack(side="left")
        e_pl_val = cfg.get("region_pl")
        lbl_pl   = tk.Label(f_pl,
                             text=(f"[{e_pl_val[0]},{e_pl_val[1]}-{e_pl_val[2]},{e_pl_val[3]}]"
                                   if e_pl_val else "Sin calibrar"),
                             bg=FONDO, fg=VERDE if e_pl_val else "#888", font=FUENTE)
        lbl_pl.pack(side="left", padx=8)

        def _auto_pl():
            res = self.app.agente.monitor.calibrar_region_pl_auto()
            if res:
                cfg.update(res)
                memoria.guardar(self.app.mem)
                r = res["region_pl"]
                lbl_pl.config(text=f"[{r[0]},{r[1]}-{r[2]},{r[3]}]", fg=VERDE)
                self.app.decir(self.app.txt(
                    "Área P&L detectada. Monitoreo de trades activo.",
                    "P&L area detected. Trade monitoring is now active."))
            else:
                self.app.decir(self.app.txt(
                    "No pude detectar el área P&L. Ábrela durante un trade activo.",
                    "Couldn't detect P&L area. Try during an active trade."))

        tk.Button(f_pl, text="Auto-detectar", bg=PANEL, fg=TEXTO, relief="flat",
                  font=FUENTE, cursor="hand2", command=_auto_pl).pack(side="right")

        f5 = tk.Frame(v, bg=FONDO)
        f5.pack(pady=10)
        tk.Label(f5, text="Duración de cada vela (segundos):", bg=FONDO,
                 fg=TEXTO, font=FUENTE).pack(side="left")
        var_p = tk.StringVar(value=str(cfg.get("periodo_vela", 60)))
        tk.Spinbox(f5, values=(30, 60, 120, 300), textvariable=var_p, width=6,
                   bg=PANEL, fg=TEXTO, relief="flat",
                   font=FUENTE).pack(side="left", padx=6)

        def auto_calibrar():
            lbl_estado = tk.Label(v, text="🔍 Escaneando pantalla...", bg=FONDO,
                                  fg=ACENTO, font=FUENTE)
            lbl_estado.pack()
            v.update()
            resultado = vision.auto_calibrar_iq()
            lbl_estado.destroy()
            if not resultado:
                self.app.decir(self.app.txt(
                    "No detecté IQ Option. Asegúrese de que esté abierto y visible.",
                    "Could not find IQ Option. Make sure it's open and visible."))
                return
            encontrados = []
            if resultado.get("boton_verde"):
                bx, by = resultado["boton_verde"]
                cfg["boton_verde"] = [bx, by]
                e3.config(text=f"({bx}, {by})", fg=VERDE)
                encontrados.append(f"SUBE ({bx},{by})")
            if resultado.get("boton_rojo"):
                bx, by = resultado["boton_rojo"]
                cfg["boton_rojo"] = [bx, by]
                e4.config(text=f"({bx}, {by})", fg=VERDE)
                encontrados.append(f"BAJA ({bx},{by})")
            if resultado.get("region_grafico"):
                r = resultado["region_grafico"]
                cfg["region_grafico"] = r
                temp["g1"] = (r[0], r[1])
                temp["g2"] = (r[2], r[3])
                e1.config(text=f"({r[0]},{r[1]})", fg=VERDE)
                e2.config(text=f"({r[2]},{r[3]})", fg=VERDE)
                encontrados.append(f"Gráfico [{r[0]},{r[1]}→{r[2]},{r[3]}]")
            if encontrados:
                memoria.guardar(self.app.mem)
                self.app.decir(self.app.txt(
                    f"Auto-calibración completa. Detecté: {', '.join(encontrados)}.",
                    f"Auto-calibration done. Detected: {', '.join(encontrados)}."))
            else:
                self.app.decir(self.app.txt(
                    "Detecté la pantalla pero no encontré los elementos de IQ Option. "
                    "Asegúrese de que el panel de trading sea visible.",
                    "Screen captured but IQ Option elements not found. "
                    "Make sure the trading panel is visible."))

        fila_auto = tk.Frame(v, bg=FONDO)
        fila_auto.pack(pady=6)
        tk.Button(fila_auto, text="🤖 Auto-calibrar (detectar automáticamente)",
                  command=auto_calibrar,
                  bg="#1a3a1a", fg=VERDE, relief="flat", font=FUENTE,
                  cursor="hand2", padx=14, pady=7).pack(side="left", padx=4)
        tk.Button(fila_auto, text="🔄 Re-calibrar ahora",
                  command=lambda: self.app.calibrar_ahora(),
                  bg="#1a2a3a", fg="#4af", relief="flat", font=FUENTE,
                  cursor="hand2", padx=10, pady=7).pack(side="left", padx=4)

        def probar_vision():
            region = self.app.mem["config"].get("region_grafico")
            if not region:
                self.app.decir("Primero calibre las dos esquinas del gráfico, señor.")
                return
            color = vision.color_vela(region)
            if color == "V":
                self.app.decir("Prueba de visión correcta: veo una vela verde, alcista.")
            elif color == "R":
                self.app.decir("Prueba de visión correcta: veo una vela roja, bajista.")
            else:
                self.app.decir("No distingo ninguna vela en esa región. Ajuste las "
                               "esquinas para cubrir solo el área de las velas.")

        def guardar_periodo():
            try:
                cfg["periodo_vela"] = int(var_p.get())
                memoria.guardar(self.app.mem)
                self.app.decir("Calibración guardada, señor. Listo para observar el gráfico.")
                v.destroy()
            except ValueError:
                pass

        botones_cal = tk.Frame(v, bg=FONDO)
        botones_cal.pack(pady=4)
        tk.Button(botones_cal, text="👁 Probar visión", command=probar_vision,
                  bg=PANEL, fg=ACENTO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=14, pady=6).pack(side="left", padx=4)
        tk.Button(botones_cal, text="Guardar y cerrar", command=guardar_periodo,
                  bg=ACENTO, fg=FONDO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=14, pady=6).pack(side="left", padx=4)

    def _guardar_boton(self, clave, x, y):
        self.app.mem["config"][clave] = [x, y]
        memoria.guardar(self.app.mem)
        self.log(f"{clave} calibrado en ({x}, {y})")

    def _guardar_extra(self, clave, x, y, lbl=None):
        self.app.mem["config"][clave] = [x, y]
        memoria.guardar(self.app.mem)
        self.log(f"{clave} calibrado en ({x}, {y})")
        if lbl:
            try:
                lbl.config(text=f"({x},{y})", fg=VERDE)
            except Exception:
                pass

    def _guardar_region(self, temp):
        if temp.get("g1") and temp.get("g2"):
            x1, y1 = temp["g1"]
            x2, y2 = temp["g2"]
            self.app.mem["config"]["region_grafico"] = [
                min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
            memoria.guardar(self.app.mem)
            self.log("Región del gráfico calibrada")

    # --- modo profesional ─────────────────────────────────────────────────────
    def abrir_profesional(self):  # noqa: C901
        """Panel del Modo Profesional — stats en vivo y control de activación."""
        v = tk.Toplevel(self.root)
        v.title("Litch · Modo Profesional")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("400x500")
        v.attributes("-topmost", True)
        v.resizable(False, False)

        # ── Header dorado ───────────────────────────────────────────────────
        hdr = tk.Frame(v, bg="#1a1200", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🏆  MODO PROFESIONAL",
                 bg="#1a1200", fg="#ffd700",
                 font=("Segoe UI", 13, "bold")).pack()
        tk.Label(hdr,
                 text="7/11 votos  ·  prob>57%  ·  Kelly>1%  ·  Anti-martingala",
                 bg="#1a1200", fg="#8b8060", font=("Segoe UI", 8)).pack()

        # ── Botón activar/desactivar ────────────────────────────────────────
        pro = getattr(self.app, "modo_profesional", None)

        estado_var = tk.StringVar()
        color_var  = ["#ffd700"]

        def _refrescar_boton():
            if pro and pro.activo:
                estado_var.set("DESACTIVAR MODO PROFESIONAL")
                btn_toggle.config(bg="#5a4000", fg="#ffd700")
            else:
                estado_var.set("ACTIVAR MODO PROFESIONAL")
                btn_toggle.config(bg="#ffd700", fg="#1a1200")

        def _toggle():
            if pro is None:
                self.app.log("[PRO] Modulo no disponible — inicia Trading primero.")
                return
            pro.toggle()
            self.actualizar()
            _refrescar_boton()
            _actualizar_stats()

        btn_toggle = tk.Button(
            v, textvariable=estado_var,
            command=_toggle,
            relief="flat", font=("Segoe UI", 11, "bold"),
            cursor="hand2", padx=12, pady=10)
        btn_toggle.pack(fill="x", padx=16, pady=(10, 4))
        _refrescar_boton()

        # ── Descripción de umbrales ─────────────────────────────────────────
        desc_frame = tk.Frame(v, bg=PANEL)
        desc_frame.pack(fill="x", padx=16, pady=(4, 8))
        umbrales = [
            ("Votos mínimos",     "5 / 7 motores en acuerdo"),
            ("Probabilidad",      "≥ 57.2% bayesiana"),
            ("Kelly mínimo",      "> 1.0% (expectativa positiva)"),
            ("Anti-martingala",   "Pausa 15 min tras 3 pérdidas seguidas"),
            ("Cooldown",          "18 s entre trades"),
            ("Position sizing",   "Kelly conservador (25% del pleno)"),
            ("FalloDB activo",    "Bloquea patrones con historial adverso"),
            ("Sesión óptima",     "London 07-10 UTC · NY 13-16 UTC (info)"),
        ]
        for i, (lbl, val) in enumerate(umbrales):
            bg = "#0d1a28" if i % 2 == 0 else PANEL
            fila = tk.Frame(desc_frame, bg=bg)
            fila.pack(fill="x")
            tk.Label(fila, text=lbl, bg=bg, fg=GRIS,
                     font=("Segoe UI", 8), anchor="w", width=18).pack(
                side="left", padx=(8, 2), pady=2)
            tk.Label(fila, text=val, bg=bg, fg=TEXTO,
                     font=("Segoe UI", 8), anchor="w").pack(
                side="left", padx=(2, 8), pady=2)

        # ── Stats en vivo ───────────────────────────────────────────────────
        tk.Frame(v, bg="#1a2a3a", height=1).pack(fill="x", padx=16, pady=(4, 0))
        tk.Label(v, text="ESTADÍSTICAS DE SESIÓN",
                 bg=FONDO, fg="#ffd700",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(4, 0))

        stats_frame = tk.Frame(v, bg=PANEL)
        stats_frame.pack(fill="x", padx=16, pady=(4, 8))

        stat_labels = {}
        stat_campos = [
            ("trades",     "Trades ejecutados"),
            ("wins",       "Ganados"),
            ("losses",     "Perdidos"),
            ("wr",         "Win rate"),
            ("racha_loss", "Racha de pérdidas"),
            ("pnl_kelly",  "P&L (Kelly units)"),
        ]
        for i, (clave, nombre) in enumerate(stat_campos):
            bg = "#0d1a28" if i % 2 == 0 else PANEL
            fila = tk.Frame(stats_frame, bg=bg)
            fila.pack(fill="x")
            tk.Label(fila, text=nombre, bg=bg, fg=GRIS,
                     font=("Segoe UI", 8), anchor="w", width=22).pack(
                side="left", padx=(8, 2), pady=2)
            lv = tk.Label(fila, text="—", bg=bg, fg=ACENTO,
                          font=("Segoe UI", 8, "bold"), anchor="w")
            lv.pack(side="left", padx=(2, 8), pady=2)
            stat_labels[clave] = lv

        def _actualizar_stats():
            if pro is None:
                return
            s = pro.stats()
            stat_labels["trades"].config(text=str(s["trades"]))
            stat_labels["wins"].config(  text=str(s["wins"]),
                                         fg=VERDE if s["wins"] else GRIS)
            stat_labels["losses"].config(text=str(s["losses"]),
                                         fg=ROJO  if s["losses"] else GRIS)
            wr_txt = f"{s['wr']:.1f}%"
            wr_col = VERDE if s["wr"] >= 57 else (ACENTO if s["wr"] >= 50 else ROJO)
            stat_labels["wr"].config(        text=wr_txt, fg=wr_col)
            rl_col = ROJO if s["racha_loss"] >= 2 else GRIS
            stat_labels["racha_loss"].config(text=str(s["racha_loss"]), fg=rl_col)
            pnl_col = VERDE if s["pnl_kelly"] >= 0 else ROJO
            stat_labels["pnl_kelly"].config( text=f"{s['pnl_kelly']:+.3f}", fg=pnl_col)

        _actualizar_stats()

        # Refrescar stats cada 5 s mientras la ventana esté abierta
        def _loop():
            try:
                _actualizar_stats()
                v.after(5000, _loop)
            except Exception:
                pass
        v.after(5000, _loop)

    # --- cámara: reconocimiento facial -----------------------------------
    def abrir_camara(self):  # noqa: C901
        """Panel de cámara y reconocimiento facial."""
        from . import vision_cam as _vc
        app = self.app
        cam = _vc.obtener(app)

        v = tk.Toplevel(self.root)
        v.title("Litch · Cámara & Reconocimiento Facial")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("560x520+80+60")
        v.attributes("-topmost", True)
        v.resizable(False, False)

        # Header
        tk.Label(v, text="📷  CÁMARA — Reconocimiento Facial",
                 bg="#071018", fg=ACENTO,
                 font=("Segoe UI", 12, "bold"),
                 pady=8).pack(fill="x")
        tk.Label(v,
                 text="Litch aprende tu cara y te saluda cuando te ve",
                 bg="#071018", fg=GRIS, font=("Segoe UI", 8)).pack(fill="x")

        # Estado disponibilidad
        if not _vc.disponible():
            tk.Label(v,
                     text="⚠  OpenCV no instalado.\n\n"
                          "Abre una terminal y ejecuta:\n"
                          "pip install opencv-python",
                     bg=FONDO, fg="#f84",
                     font=("Consolas", 10), justify="center").pack(
                         expand=True, pady=30)
            return

        # Vista en vivo
        lbl_cam = tk.Label(v, bg="#050d15", relief="flat")
        lbl_cam.pack(padx=14, pady=(8, 4))

        # Estado del perfil
        lbl_perfil = tk.Label(v, bg=FONDO, fg=GRIS, font=FUENTE, anchor="w")
        lbl_perfil.pack(fill="x", padx=14)

        def _actualizar_perfil():
            if cam and cam.tiene_perfil():
                lbl_perfil.config(
                    text=f"✓ Perfil registrado: {cam.nombre_usuario()}",
                    fg=VERDE)
            else:
                lbl_perfil.config(text="Sin perfil registrado aún.", fg="#f84")

        # Área de enrolamiento
        enr_frame = tk.LabelFrame(v, text=" Registrar cara ",
                                  bg=FONDO, fg=ACENTO, font=FUENTE)
        enr_frame.pack(fill="x", padx=14, pady=(4, 4))

        row_enr = tk.Frame(enr_frame, bg=FONDO)
        row_enr.pack(padx=8, pady=4)
        tk.Label(row_enr, text="Tu nombre:", bg=FONDO, fg=TEXTO,
                 font=FUENTE).pack(side="left")
        nombre_var = tk.StringVar(value=cam.nombre_usuario() if cam else "")
        entry_nombre = tk.Entry(row_enr, textvariable=nombre_var, bg=PANEL,
                                fg=TEXTO, font=FUENTE, relief="flat", width=18,
                                insertbackground=TEXTO)
        entry_nombre.pack(side="left", padx=(6, 8), ipady=3)

        lbl_prog = tk.Label(enr_frame, text="", bg=FONDO, fg=ACENTO,
                            font=("Consolas", 8))
        lbl_prog.pack()

        btn_enrollar = tk.Button(enr_frame, text="📸 Tomar fotos y registrarme",
                                 bg="#1a3a1a", fg=VERDE, relief="flat",
                                 font=("Segoe UI", 9, "bold"), cursor="hand2",
                                 padx=10, pady=5)

        def _enrollar():
            nombre = nombre_var.get().strip()
            if not nombre:
                lbl_prog.config(text="Escribe tu nombre primero.", fg=ROJO)
                return
            btn_enrollar.config(state="disabled", text="⏳ Capturando…")

            def cb(msg):
                try:
                    v.after(0, lambda m=msg: lbl_prog.config(text=m, fg=ACENTO))
                except Exception:
                    pass

            def en_hilo():
                ok, msg = cam.enrollar(nombre, n_fotos=5, callback=cb)
                def en_ui():
                    btn_enrollar.config(state="normal",
                                        text="📸 Tomar fotos y registrarme")
                    lbl_prog.config(text=msg,
                                    fg=VERDE if ok else ROJO)
                    _actualizar_perfil()
                    if ok:
                        app.decir(app.txt(
                            f"Perfecto, {nombre}. Ya te reconozco, senor.",
                            f"Perfect, {nombre}. I recognize you now, sir."))
                try:
                    v.after(0, en_ui)
                except Exception:
                    pass

            threading.Thread(target=en_hilo, daemon=True,
                             name="CamEnroll").start()

        btn_enrollar.config(command=_enrollar)
        btn_enrollar.pack(pady=(4, 8))

        # Botones de control de cámara
        ctrl_frame = tk.Frame(v, bg=FONDO)
        ctrl_frame.pack(fill="x", padx=14, pady=(0, 8))

        lbl_cam_est = tk.Label(ctrl_frame, text="", bg=FONDO, fg=GRIS,
                               font=("Segoe UI", 8))
        lbl_cam_est.pack(side="right")

        def _toggle_cam():
            if cam.esta_activa():
                cam.detener()
                btn_cam.config(text="▶ Iniciar cámara", fg=ACENTO)
                lbl_cam_est.config(text="Cámara detenida", fg=GRIS)
            else:
                ok = cam.iniciar()
                if ok:
                    btn_cam.config(text="⏹ Detener cámara", fg=ROJO)
                    lbl_cam_est.config(text="Cámara activa", fg=VERDE)
                    _loop_video()

        btn_cam = tk.Button(ctrl_frame,
                            text="▶ Iniciar cámara" if not cam.esta_activa()
                            else "⏹ Detener cámara",
                            command=_toggle_cam,
                            bg=PANEL, fg=ACENTO, relief="flat",
                            font=FUENTE, cursor="hand2", padx=10, pady=5)
        btn_cam.pack(side="left")

        # Loop de video (actualiza la preview en tkinter)
        def _loop_video():
            if not cam.esta_activa():
                return
            try:
                import io
                frame_bytes = cam.get_frame()
                if frame_bytes:
                    from PIL import Image, ImageTk
                    img = Image.open(io.BytesIO(frame_bytes))
                    img.thumbnail((532, 240))
                    photo = ImageTk.PhotoImage(img)
                    lbl_cam.config(image=photo, width=532, height=240)
                    lbl_cam.image = photo
                    # Indicador de reconocimiento
                    if cam.usuario_presente():
                        lbl_cam_est.config(
                            text=f"✓ {cam.nombre_usuario()} detectado", fg=VERDE)
            except ImportError:
                lbl_cam.config(text="(Instala Pillow para preview: pip install Pillow)",
                               fg=GRIS, width=40, height=10)
            except Exception:
                pass
            try:
                v.after(100, _loop_video)
            except Exception:
                pass

        # Si la cámara ya estaba activa, arranca el loop de video
        if cam and cam.esta_activa():
            btn_cam.config(text="⏹ Detener cámara", fg=ROJO)
            lbl_cam_est.config(text="Cámara activa", fg=VERDE)
            _loop_video()

        _actualizar_perfil()
        v.protocol("WM_DELETE_WINDOW", v.destroy)

    # --- activación directa de modo autónomo (sin TOTP) ------------------
    def abrir_seguridad(self):
        """Activa o desactiva el modo autónomo + auto-click directamente,
        sin requerir ningún código ni autenticador externo.
        El botón Auto-click es la única llave."""
        # Toggle directo — el usuario controla con un clic
        nuevo_estado = not self.app.autoclick_on
        self.app.set_autoclick(nuevo_estado, hablar=True)
        return  # sin ventana de diálogo — acción inmediata

    def _abrir_seguridad_ventana_legacy(self):
        """Ventana informativa (sin TOTP) — explica cómo activar Auto-click."""
        v = tk.Toplevel(self.root)
        v.title("Modo autónomo — Auto-click")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("380x280")
        v.attributes("-topmost", True)

        estado_txt = ("AUTO-CLICK: ACTIVO  ●" if self.app.autoclick_on
                      else "AUTO-CLICK: INACTIVO  ○")
        tk.Label(v, text=estado_txt, bg=FONDO,
                 fg=ACENTO if self.app.autoclick_on else GRIS,
                 font=FUENTE_T).pack(pady=(16, 4))
        tk.Label(v, text=("Presiona el botón AUTO en la barra superior para activar "
                          "el modo autónomo completo.\n\n"
                          "No se requiere ningún código ni autenticador.\n"
                          "Funciona tanto en cuenta DEMO (práctica) como en REAL."),
                 bg=FONDO, fg=TEXTO, font=FUENTE, wraplength=340,
                 justify="left").pack(padx=18, pady=8)

        def _toggle():
            self.app.set_autoclick(not self.app.autoclick_on, hablar=True)
            v.destroy()

        btn_txt = ("● Desactivar Auto-click" if self.app.autoclick_on
                   else "● Activar Auto-click")
        btn_clr = ROJO if self.app.autoclick_on else ACENTO
        tk.Button(v, text=btn_txt, command=_toggle,
                  bg=btn_clr, fg=FONDO, relief="flat", font=FUENTE_T,
                  cursor="hand2", padx=16, pady=10).pack(pady=20)

        tk.Label(v, text=("No se requiere ningún código. El botón AUTO en la "
                          "barra superior hace exactamente lo mismo."),
                 bg=FONDO, fg=GRIS, font=("Segoe UI", 8), wraplength=340,
                 justify="left").pack(side="bottom", padx=14, pady=10)

    # --- nube: respaldo en varias cuentas tuyas --------------------------
    def abrir_libros(self):  # noqa: C901
        """Ventana de gestión de libros y documentos para Litch."""
        from . import lector_libros as _lb
        import threading as _thr

        v = tk.Toplevel(self.root)
        v.title("📚 Libros y documentos — base de conocimiento")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("620x560")
        v.attributes("-topmost", True)

        tk.Label(v, text="📚  BASE DE CONOCIMIENTO — LIBROS Y DOCUMENTOS",
                 bg=FONDO, fg=ACENTO, font=FUENTE_T).pack(pady=(12, 2))
        tk.Label(v,
                 text=("Copia tus PDF, TXT o DOCX en la carpeta  LIBROS/  "
                       "(que está junto a litch.py).\n"
                       "Luego pulsa «Cargar libros» y Litch los leerá y los indexará."),
                 bg=FONDO, fg=TEXTO, font=FUENTE, wraplength=580).pack(pady=(0, 8))

        # Ruta de la carpeta
        tk.Label(v, text=f"📁 Carpeta: {_lb.RUTA_LIBROS}",
                 bg=FONDO, fg=GRIS, font=FUENTE).pack()

        def _abrir_carpeta():
            import subprocess
            try:
                import os as _os
                _os.makedirs(_lb.RUTA_LIBROS, exist_ok=True)
                subprocess.Popen(["explorer", _lb.RUTA_LIBROS])
            except Exception as e:
                log_txt.insert("end", f"\n⚠ {e}")

        tk.Button(v, text="📂 Abrir carpeta LIBROS/", command=_abrir_carpeta,
                  bg=PANEL, fg=ACENTO, font=FUENTE, relief="flat",
                  cursor="hand2", padx=10, pady=4).pack(pady=(4, 10))

        # Lista de libros cargados
        tk.Label(v, text="Libros en el índice:", bg=FONDO, fg=TEXTO, font=FUENTE).pack(anchor="w", padx=14)

        frame_lista = tk.Frame(v, bg=PANEL, bd=0)
        frame_lista.pack(fill="x", padx=14, pady=(2, 6))

        lbl_libros = tk.Label(frame_lista, text="(sin libros cargados)",
                              bg=PANEL, fg=GRIS, font=FUENTE,
                              wraplength=560, justify="left")
        lbl_libros.pack(anchor="w", padx=6, pady=4)

        def _actualizar_lista():
            lista = _lb.listar_libros()
            if lista:
                txt = "\n".join(
                    f"  • {lb['nombre']}  ({lb['chunks']} fragmentos)"
                    for lb in lista)
                lbl_libros.config(
                    text=f"Total: {_lb.total_chunks()} fragmentos buscables\n{txt}",
                    fg=TEXTO)
            else:
                lbl_libros.config(text="(sin libros cargados)", fg=GRIS)

        _actualizar_lista()

        # Log de progreso
        tk.Label(v, text="Progreso:", bg=FONDO, fg=TEXTO, font=FUENTE).pack(anchor="w", padx=14)
        log_txt = tk.Text(v, height=8, bg=PANEL, fg=TEXTO, font=("Consolas", 8),
                          relief="flat", state="disabled", wrap="word")
        log_txt.pack(fill="both", expand=True, padx=14, pady=(2, 6))

        def _log(msg):
            log_txt.config(state="normal")
            log_txt.insert("end", msg + "\n")
            log_txt.see("end")
            log_txt.config(state="disabled")

        # Botón de carga
        btn_cargar = tk.Button(v, text="⬇  Cargar / actualizar libros",
                               bg=ACENTO, fg=FONDO, font=FUENTE,
                               relief="flat", cursor="hand2", padx=14, pady=6)
        btn_cargar.pack(pady=(0, 10))

        def _cargar():
            btn_cargar.config(state="disabled", text="⏳  Leyendo…")
            _log("Iniciando carga de libros…")

            def _job():
                res = _lb.cargar_libros(callback=_log)
                if res["nuevos"] > 0:
                    _log(f"\n✅  {res['nuevos']} libro(s) nuevo(s) procesados.")
                    _log(f"   Total en índice: {res['total']} libros | {res['chunks']} fragmentos.")
                elif not res["errores"]:
                    _log("\nℹ  Todos los libros ya estaban al día (sin cambios).")
                for err in res["errores"]:
                    _log(f"⚠  {err}")
                _actualizar_lista()
                btn_cargar.config(state="normal", text="⬇  Cargar / actualizar libros")
                # Informar por voz
                if res["nuevos"] > 0:
                    self.app.decir(
                        f"{res['nuevos']} libros aprendidos, señor. "
                        f"Ahora puedo responder preguntas sobre ellos.")

            _thr.Thread(target=_job, daemon=True, name="LitchLibrosCarga").start()

        btn_cargar.config(command=_cargar)

        # Búsqueda rápida
        frame_busq = tk.Frame(v, bg=FONDO)
        frame_busq.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(frame_busq, text="Buscar en los libros:", bg=FONDO, fg=TEXTO,
                 font=FUENTE).pack(anchor="w")
        entrada = tk.Entry(frame_busq, bg=PANEL, fg=TEXTO, font=FUENTE,
                           relief="flat", insertbackground=ACENTO)
        entrada.pack(side="left", fill="x", expand=True, ipady=4)

        def _buscar(_evt=None):
            q = entrada.get().strip()
            if not q:
                return
            resultados = _lb.buscar(q, top_n=2)
            _log(f"\n🔍 Búsqueda: «{q}»")
            if not resultados:
                _log("   Sin resultados.")
                return
            for r in resultados:
                _log(f"   📖 [{r['libro']}] score={r['score']}:")
                _log(f"   «{r['texto'][:280].strip()}…»")

        tk.Button(frame_busq, text="🔍", command=_buscar, bg=PANEL, fg=ACENTO,
                  font=FUENTE, relief="flat", cursor="hand2", padx=8,
                  pady=4).pack(side="left", padx=(4, 0))
        entrada.bind("<Return>", _buscar)

    def abrir_nube(self):
        v = tk.Toplevel(self.root)
        v.title("Respaldo en la nube — tus cuentas")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("560x600")
        v.attributes("-topmost", True)

        tk.Label(v, text="Tus cuentas de nube (TeraBox / Drive / Dropbox)",
                 bg=FONDO, fg=ACENTO, font=FUENTE_T).pack(pady=(10, 2))
        tk.Label(v, text=("Instala la app oficial de tu nube, inicia sesión con uno de "
                          "tus correos y ubica la carpeta que sincroniza en tu PC. "
                          "Registra aquí ese correo y esa carpeta. Litch copiará su "
                          "memoria a TODAS tus cuentas y rotará cuando una se llene."),
                 bg=FONDO, fg=TEXTO, font=FUENTE, wraplength=520,
                 justify="left").pack(padx=14, pady=4)

        lista = scrolledtext.ScrolledText(v, height=8, bg=PANEL, fg=TEXTO,
                                          font=("Consolas", 8), relief="flat",
                                          state="disabled", wrap="word")
        lista.pack(fill="x", padx=12, pady=6)

        def refrescar_lista():
            lista.config(state="normal")
            lista.delete("1.0", "end")
            lista.insert("1.0", respaldo.estado_texto())
            lista.config(state="disabled")

        form = tk.Frame(v, bg=FONDO)
        form.pack(padx=12, pady=4, fill="x")

        def campo(etiqueta, valor=""):
            f = tk.Frame(form, bg=FONDO)
            f.pack(fill="x", pady=2)
            tk.Label(f, text=etiqueta, bg=FONDO, fg=TEXTO, font=FUENTE,
                     width=12, anchor="w").pack(side="left")
            e = tk.Entry(f, bg=PANEL, fg=TEXTO, font=FUENTE, relief="flat",
                         insertbackground=TEXTO)
            e.pack(side="left", fill="x", expand=True, ipady=3)
            if valor:
                e.insert(0, valor)
            return e

        e_correo = campo("Correo:")
        e_carpeta = campo("Carpeta:", "")
        e_prov = campo("Proveedor:", "TeraBox")
        e_limite = campo("Límite GB:", "1024")

        aviso = tk.Label(v, text="", bg=FONDO, fg=VERDE, font=FUENTE,
                         wraplength=520)
        aviso.pack(padx=14, pady=2)

        def registrar():
            correo = e_correo.get().strip()
            carpeta = e_carpeta.get().strip()
            if not correo or not carpeta:
                aviso.config(text="Indica correo y carpeta, señor.", fg=ROJO)
                return
            try:
                limite = int(e_limite.get().strip() or "1024")
            except ValueError:
                limite = 1024
            ok, msg = respaldo.registrar_cuenta(
                correo, carpeta, e_prov.get().strip() or "TeraBox", limite)
            aviso.config(text=msg, fg=VERDE if ok else ROJO)
            if ok:
                e_correo.delete(0, "end")
                e_carpeta.delete(0, "end")
                self.app.decir(f"Cuenta {correo} registrada, señor.")
            refrescar_lista()

        botones = tk.Frame(v, bg=FONDO)
        botones.pack(pady=8)
        tk.Button(botones, text="➕ Registrar cuenta", command=registrar,
                  bg=ACENTO, fg=FONDO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=12, pady=6).pack(side="left", padx=4)

        def respaldar_ahora():
            aviso.config(text=respaldo.respaldar(self.app), fg=ACENTO)
            refrescar_lista()

        tk.Button(botones, text="☁ Respaldar ahora", command=respaldar_ahora,
                  bg=PANEL, fg=ACENTO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=12, pady=6).pack(side="left", padx=4)

        def quitar():
            datos = respaldo.cargar_cuentas()
            if datos["cuentas"]:
                correo = respaldo.eliminar_cuenta(len(datos["cuentas"]) - 1)
                aviso.config(text=f"Eliminada la última cuenta: {correo}", fg=GRIS)
                refrescar_lista()

        tk.Button(botones, text="🗑 Quitar última", command=quitar,
                  bg=PANEL, fg=ROJO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=12, pady=6).pack(side="left", padx=4)

        tk.Checkbutton(
            v, text="Respaldar automáticamente cada 30 minutos",
            bg=FONDO, fg=TEXTO, selectcolor=PANEL, font=FUENTE,
            activebackground=FONDO, activeforeground=ACENTO,
            variable=self.app.var_respaldo_auto,
            command=self.app.toggle_respaldo_auto).pack(pady=6)

        refrescar_lista()

    # --- correo e IA -------------------------------------------------------
    def abrir_correo_ia(self):  # noqa: C901
        v = tk.Toplevel(self.root)
        v.title("Litch · Correo e IA")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("620x700+60+40")
        v.attributes("-topmost", True)
        v.resizable(False, True)

        # ── Header ─────────────────────────────────────────────────────────
        tk.Label(v, text="📧  CORREO ELECTRÓNICO E IA",
                 bg=FONDO, fg=ACENTO, font=FUENTE_T).pack(pady=(10, 0))
        tk.Label(v, text="Cuentas de correo  ·  Permisos de capacidades autónomas",
                 bg=FONDO, fg=GRIS, font=("Segoe UI", 8)).pack(pady=(0, 8))

        nb = tk.Frame(v, bg=FONDO)
        nb.pack(fill="both", expand=True, padx=12)

        # ── Pestaña: Cuentas de correo ─────────────────────────────────────
        sec_cuentas = tk.LabelFrame(
            nb, text=" Cuentas de correo ", bg=FONDO, fg=ACENTO,
            font=FUENTE, pady=6)
        sec_cuentas.pack(fill="x", pady=(0, 8))

        # Lista de cuentas
        lista_c = scrolledtext.ScrolledText(
            sec_cuentas, height=5, bg=PANEL, fg=VERDE,
            font=("Consolas", 8), relief="flat", state="disabled")
        lista_c.pack(fill="x", padx=6, pady=(0, 6))

        def refrescar_cuentas():
            lista_c.config(state="normal")
            lista_c.delete("1.0", "end")
            cuentas = correo.cargar_cuentas()
            if cuentas:
                for c in cuentas:
                    activa = "✓" if c.get("activa") else "✗"
                    lista_c.insert("end",
                        f"[{activa}] {c['email']}  ({c.get('proveedor','?')})"
                        f"  IMAP:{c.get('imap_host','')}:{c.get('imap_port',993)}\n")
            else:
                lista_c.insert("end", "Sin cuentas configuradas. Añade una abajo.\n")
            lista_c.config(state="disabled")

        refrescar_cuentas()

        # Formulario de nueva cuenta
        form = tk.Frame(sec_cuentas, bg=FONDO)
        form.pack(fill="x", padx=6)

        def campo_f(etiq, ancho=22, pwd=False):
            f = tk.Frame(form, bg=FONDO)
            f.pack(fill="x", pady=1)
            tk.Label(f, text=etiq, bg=FONDO, fg=TEXTO, font=FUENTE,
                     width=14, anchor="w").pack(side="left")
            kw = {"show": "●"} if pwd else {}
            e = tk.Entry(f, bg=PANEL, fg=TEXTO, font=FUENTE, relief="flat",
                         insertbackground=TEXTO, width=ancho, **kw)
            e.pack(side="left", fill="x", expand=True, ipady=3)
            return e

        e_email  = campo_f("Email:")
        e_pass   = campo_f("Contraseña / App pwd:", pwd=True)

        # Proveedor
        fp = tk.Frame(form, bg=FONDO)
        fp.pack(fill="x", pady=2)
        tk.Label(fp, text="Proveedor:", bg=FONDO, fg=TEXTO, font=FUENTE,
                 width=14, anchor="w").pack(side="left")
        prov_var = tk.StringVar(value="Gmail")
        prov_menu = tk.OptionMenu(fp, prov_var, *correo.PROVEEDORES.keys())
        prov_menu.config(bg=PANEL, fg=ACENTO, relief="flat", font=FUENTE,
                         highlightthickness=0, bd=0, activebackground=ACENTO,
                         activeforeground=FONDO)
        prov_menu["menu"].config(bg=PANEL, fg=TEXTO, activebackground=ACENTO,
                                 activeforeground=FONDO)
        prov_menu.pack(side="left")

        # Ayuda dinámica según proveedor
        lbl_ayuda = tk.Label(
            sec_cuentas, text=correo.PROVEEDORES["Gmail"]["ayuda"],
            bg="#071018", fg=GRIS, font=("Segoe UI", 7), wraplength=560,
            justify="left", anchor="w")
        lbl_ayuda.pack(fill="x", padx=6, pady=(2, 4))

        def _actualizar_ayuda(*_):
            prov = prov_var.get()
            lbl_ayuda.config(text=correo.PROVEEDORES.get(prov, {}).get("ayuda", ""))
        prov_var.trace_add("write", _actualizar_ayuda)

        aviso_c = tk.Label(sec_cuentas, text="", bg=FONDO, fg=VERDE, font=FUENTE)
        aviso_c.pack(padx=6)

        bots_c = tk.Frame(sec_cuentas, bg=FONDO)
        bots_c.pack(pady=4)

        def agregar_cuenta():
            em  = e_email.get().strip()
            pw  = e_pass.get().strip()
            prov = prov_var.get()
            if not em or not pw:
                aviso_c.config(text="Indica email y contraseña.", fg=ROJO)
                return
            correo.agregar_cuenta(em, pw, prov)
            aviso_c.config(text=f"✓ Cuenta {em} guardada.", fg=VERDE)
            e_email.delete(0, "end")
            e_pass.delete(0, "end")
            refrescar_cuentas()

        tk.Button(bots_c, text="➕ Agregar cuenta", command=agregar_cuenta,
                  bg=ACENTO, fg=FONDO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=12, pady=5).pack(side="left", padx=4)

        def probar_cuenta():
            aviso_c.config(text="Probando conexión…", fg=ACENTO)
            v.update_idletasks()
            cuenta = correo.cuenta_principal()
            if not cuenta:
                aviso_c.config(text="No hay cuenta principal. Agrega una primero.", fg=ROJO)
                return

            def en_hilo():
                imap_ok, smtp_ok, msg = correo.probar_conexion(cuenta)
                color = VERDE if (imap_ok and smtp_ok) else ROJO
                def en_ui():
                    aviso_c.config(text=msg.replace("\n", "  "), fg=color)
                try:
                    v.after(0, en_ui)
                except Exception:
                    pass

            threading.Thread(target=en_hilo, daemon=True).start()

        tk.Button(bots_c, text="🔌 Probar conexión", command=probar_cuenta,
                  bg=PANEL, fg=ACENTO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=12, pady=5).pack(side="left", padx=4)

        def quitar_ultima():
            cuentas = correo.cargar_cuentas()
            if cuentas:
                correo.eliminar_cuenta(cuentas[-1]["email"])
                aviso_c.config(text=f"Eliminada: {cuentas[-1]['email']}", fg=GRIS)
                refrescar_cuentas()

        tk.Button(bots_c, text="🗑 Quitar última", command=quitar_ultima,
                  bg=PANEL, fg=ROJO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=10, pady=5).pack(side="left", padx=4)

        # ── Estado de MEMORIA_AP ───────────────────────────────────────────
        sec_peso = tk.LabelFrame(
            nb, text=" MEMORIA_AP — conocimiento guardado ", bg=FONDO, fg=ACENTO,
            font=FUENTE, pady=4)
        sec_peso.pack(fill="x", pady=(0, 8))

        lbl_peso = tk.Label(sec_peso,
                            text="Calculando…",
                            bg=FONDO, fg=VERDE, font=("Consolas", 8),
                            anchor="w", justify="left", wraplength=560)
        lbl_peso.pack(fill="x", padx=8, pady=(0, 2))

        def _refrescar_peso():
            txt  = memoria.peso_memoria()
            ruta = memoria.ruta_memoria_ap()
            lbl_peso.config(text=f"{txt}\nRuta: {ruta}")

        def _abrir_carpeta():
            ruta = memoria.ruta_memoria_ap()
            os.makedirs(ruta, exist_ok=True)
            try:
                import subprocess
                subprocess.Popen(["explorer", ruta])
            except Exception:
                pass

        bots_peso = tk.Frame(sec_peso, bg=FONDO)
        bots_peso.pack(pady=2)
        tk.Button(bots_peso, text="🔄 Actualizar", command=_refrescar_peso,
                  bg=PANEL, fg=ACENTO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=10, pady=4).pack(side="left", padx=4)
        tk.Button(bots_peso, text="📂 Abrir carpeta", command=_abrir_carpeta,
                  bg=PANEL, fg=VERDE, relief="flat", font=FUENTE,
                  cursor="hand2", padx=10, pady=4).pack(side="left", padx=4)

        _refrescar_peso()

        # ── Pestaña: Permisos ──────────────────────────────────────────────
        sec_perm = tk.LabelFrame(
            nb, text=" Permisos de capacidades ", bg=FONDO, fg=ACENTO,
            font=FUENTE, pady=6)
        sec_perm.pack(fill="x", pady=(0, 8))

        tk.Label(sec_perm,
                 text=("siempre = actúa sin preguntar   "
                       "pedir = pregunta antes   "
                       "nunca = bloqueado"),
                 bg=FONDO, fg=GRIS, font=("Segoe UI", 7)).pack(anchor="w", padx=8)

        grid_p = tk.Frame(sec_perm, bg=FONDO)
        grid_p.pack(fill="x", padx=8, pady=4)

        _vars_perm = {}
        ESTADOS = ["siempre", "pedir", "nunca"]
        COL_E   = {  # colores por estado
            "siempre": VERDE,
            "pedir":   ACENTO,
            "nunca":   ROJO,
        }

        for fila_i, (clave, info) in enumerate(perms_mod.CATALOGO.items()):
            estado_actual = perms_mod.estado(clave)
            var = tk.StringVar(value=estado_actual)
            _vars_perm[clave] = var

            tk.Label(grid_p,
                     text=f"{info['icono']} {info['nombre']}",
                     bg=FONDO, fg=TEXTO, font=FUENTE,
                     width=26, anchor="w").grid(row=fila_i, column=0,
                                                sticky="w", pady=1)

            lbl_e = tk.Label(grid_p, text=estado_actual,
                             bg=FONDO, fg=COL_E.get(estado_actual, GRIS),
                             font=("Segoe UI", 8, "bold"), width=8, anchor="w")
            lbl_e.grid(row=fila_i, column=1, padx=(4, 8))

            def _hacer_cambio(k=clave, lbl=lbl_e):
                estados_ciclo = ESTADOS
                actual = perms_mod.estado(k)
                nuevo = estados_ciclo[(estados_ciclo.index(actual) + 1) % 3]
                perms_mod.set_estado(k, nuevo)
                lbl.config(text=nuevo, fg=COL_E.get(nuevo, GRIS))

            tk.Button(grid_p, text="↻ cambiar",
                      command=_hacer_cambio,
                      bg=PANEL, fg=GRIS, relief="flat",
                      font=("Segoe UI", 7), cursor="hand2",
                      padx=6, pady=2).grid(row=fila_i, column=2, padx=2)

            tk.Label(grid_p, text=info["desc"],
                     bg=FONDO, fg=GRIS,
                     font=("Segoe UI", 7), anchor="w").grid(
                         row=fila_i, column=3, sticky="w", padx=(4, 0))

        # ── Pestaña: Bandeja de entrada ────────────────────────────────────
        sec_inbox = tk.LabelFrame(
            nb, text=" Vista rápida de correo ", bg=FONDO, fg=ACENTO,
            font=FUENTE, pady=6)
        sec_inbox.pack(fill="both", expand=True, pady=(0, 8))

        inbox_txt = scrolledtext.ScrolledText(
            sec_inbox, height=8, bg="#060f1a", fg=ACENTO,
            font=("Consolas", 8), relief="flat", state="disabled")
        inbox_txt.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        aviso_inbox = tk.Label(sec_inbox, text="", bg=FONDO, fg=GRIS, font=FUENTE)
        aviso_inbox.pack()

        def _mostrar_emails(emails, estado_msg):
            inbox_txt.config(state="normal")
            inbox_txt.delete("1.0", "end")
            if emails:
                for em in emails:
                    inbox_txt.insert("end",
                        f"De: {em['de'][:50]}\n"
                        f"Asunto: {em['asunto'][:70]}\n"
                        f"Fecha: {em['fecha'][:30]}\n"
                        f"  {em['cuerpo'][:120]}…\n"
                        f"{'─'*60}\n")
            else:
                inbox_txt.insert("end", estado_msg)
            inbox_txt.config(state="disabled")
            aviso_inbox.config(text=estado_msg[:80])

        bots_inbox = tk.Frame(sec_inbox, bg=FONDO)
        bots_inbox.pack(pady=(0, 4))

        def leer_correos():
            aviso_inbox.config(text="Leyendo…", fg=ACENTO)
            v.update_idletasks()

            def en_hilo():
                emails, msg = correo.leer_inbox(n=8)
                try:
                    v.after(0, lambda: _mostrar_emails(emails, msg))
                except Exception:
                    pass

            threading.Thread(target=en_hilo, daemon=True).start()

        tk.Button(bots_inbox, text="📬 Leer bandeja", command=leer_correos,
                  bg=ACENTO, fg=FONDO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=12, pady=5).pack(side="left", padx=4)

        # Formulario de envío rápido
        frm_send = tk.Frame(sec_inbox, bg=FONDO)
        frm_send.pack(fill="x", padx=6, pady=2)

        def campo_s(etiq):
            f = tk.Frame(frm_send, bg=FONDO)
            f.pack(fill="x", pady=1)
            tk.Label(f, text=etiq, bg=FONDO, fg=TEXTO, font=FUENTE,
                     width=10, anchor="w").pack(side="left")
            e = tk.Entry(f, bg=PANEL, fg=TEXTO, font=FUENTE,
                         relief="flat", insertbackground=TEXTO)
            e.pack(side="left", fill="x", expand=True, ipady=3)
            return e

        e_para   = campo_s("Para:")
        e_asunto = campo_s("Asunto:")
        e_cuerpo = campo_s("Mensaje:")

        def enviar_rapido():
            dest    = e_para.get().strip()
            asunto_ = e_asunto.get().strip()
            cuerpo_ = e_cuerpo.get().strip()
            if not dest or not asunto_:
                aviso_inbox.config(text="Indica destinatario y asunto.", fg=ROJO)
                return

            def en_hilo():
                ok, msg_env = correo.enviar(dest, asunto_, cuerpo_)
                color = VERDE if ok else ROJO
                try:
                    v.after(0, lambda: aviso_inbox.config(text=msg_env[:80], fg=color))
                    if ok:
                        v.after(0, lambda: (
                            e_para.delete(0, "end"),
                            e_asunto.delete(0, "end"),
                            e_cuerpo.delete(0, "end")))
                except Exception:
                    pass

            threading.Thread(target=en_hilo, daemon=True).start()
            aviso_inbox.config(text="Enviando…", fg=ACENTO)

        tk.Button(bots_inbox, text="📤 Enviar", command=enviar_rapido,
                  bg=PANEL, fg=ACENTO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=12, pady=5).pack(side="left", padx=4)

    # --- conciencia e inteligencia autónoma --------------------------------
    def abrir_conciencia(self):  # noqa: C901
        """Panel que muestra el estado interno del sistema de conciencia."""
        app = self.app
        con = getattr(app, "conciencia", None)

        v = tk.Toplevel(self.root)
        v.title("Litch · Conciencia e Inteligencia Autónoma")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("720x640+50+30")
        v.attributes("-topmost", True)
        v.resizable(True, True)

        # Header
        hdr = tk.Frame(v, bg="#071018", pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🧠  CONCIENCIA LITCH — Inteligencia Autónoma",
                 bg="#071018", fg=ACENTO,
                 font=("Segoe UI", 12, "bold")).pack()
        tk.Label(hdr,
                 text="Memoria Episódica · Creencias Bayesianas · Red Neuronal · Metacognición",
                 bg="#071018", fg=GRIS, font=("Segoe UI", 8)).pack()

        # Estado rápido en chips
        chips_f = tk.Frame(v, bg=FONDO)
        chips_f.pack(fill="x", padx=14, pady=(6, 2))

        lbl_ep  = tk.Label(chips_f, text="Episodios: —", bg="#0a1a0a", fg=VERDE,
                           font=("Consolas", 9), relief="flat", padx=8, pady=3)
        lbl_ep.pack(side="left", padx=(0, 4))
        lbl_rd  = tk.Label(chips_f, text="Red updates: —", bg="#0a0a1a", fg="#a8f",
                           font=("Consolas", 9), relief="flat", padx=8, pady=3)
        lbl_rd.pack(side="left", padx=(0, 4))
        lbl_ece = tk.Label(chips_f, text="ECE: —", bg="#1a0a0a", fg="#f84",
                           font=("Consolas", 9), relief="flat", padx=8, pady=3)
        lbl_ece.pack(side="left", padx=(0, 4))
        lbl_bri = tk.Label(chips_f, text="Brier: —", bg="#1a1a0a", fg="#ff4",
                           font=("Consolas", 9), relief="flat", padx=8, pady=3)
        lbl_bri.pack(side="left")

        # Cuerpo principal: introspección
        txt_f = tk.Frame(v, bg=FONDO)
        txt_f.pack(fill="both", expand=True, padx=14, pady=(4, 2))

        txt = tk.Text(txt_f, bg="#060f1a", fg=TEXTO, font=("Consolas", 9),
                      relief="flat", wrap="word", padx=10, pady=8, state="disabled")
        sb  = tk.Scrollbar(txt_f, command=txt.yview)
        txt.config(yscrollcommand=_scroll_seguro(sb))
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)

        txt.tag_config("sep",    foreground=ACENTO, font=("Consolas", 9, "bold"))
        txt.tag_config("ok",     foreground=VERDE)
        txt.tag_config("warn",   foreground="#f84")
        txt.tag_config("rojo",   foreground=ROJO)
        txt.tag_config("lila",   foreground="#c8a0ff")
        txt.tag_config("gris",   foreground=GRIS)

        def _refrescar():
            if con is None:
                contenido = "Sistema de Conciencia no inicializado aún.\nIncia el Agente Trading primero."
                txt.config(state="normal")
                txt.delete("1.0", "end")
                txt.insert("end", contenido)
                txt.config(state="disabled")
                return

            intro = con.introspeccionar()
            ece   = con.meta.ece()
            brier = con.meta.brier()

            lbl_ep.config( text=f"Episodios: {len(con.memoria)}")
            lbl_rd.config( text=f"Red: {con.red.n_updates} updates")
            lbl_ece.config(text=f"ECE: {ece:.4f}",
                           fg=VERDE if ece < 0.06 else ("#f84" if ece < 0.16 else ROJO))
            lbl_bri.config(text=f"Brier: {brier:.4f}",
                           fg=VERDE if brier < 0.20 else ("#f84" if brier < 0.25 else ROJO))

            # Sincronizar label de override con estado real
            try:
                _modo_var.set(con.estado_override())
                _color_modo = {"🔄 AUTO": ACENTO, "▶ FORZAR OPERAR": VERDE,
                               "⏸ FORZAR ABSTENCIÓN": "#f84"}.get(con.estado_override(), ACENTO)
                lbl_modo.config(fg=_color_modo)
            except Exception:
                pass

            txt.config(state="normal")
            txt.delete("1.0", "end")
            for linea in intro.splitlines():
                if linea.startswith("═") or linea.startswith("  ──"):
                    txt.insert("end", linea + "\n", "sep")
                elif "EXCELEN" in linea or "BUENA ✓" in linea or "✓✓" in linea:
                    txt.insert("end", linea + "\n", "ok")
                elif "MEJORABLE" in linea or "⚠" in linea:
                    txt.insert("end", linea + "\n", "warn")
                elif "EVITAR" in linea or "PELIGRO" in linea:
                    txt.insert("end", linea + "\n", "rojo")
                elif "Reflexión" in linea or "REFLEXIÓN" in linea:
                    txt.insert("end", linea + "\n", "lila")
                elif linea.startswith("  ["):
                    txt.insert("end", linea + "\n", "lila")
                else:
                    txt.insert("end", linea + "\n")
            txt.config(state="disabled")

        # Área de estado
        lbl_est = tk.Label(v, text="", bg=FONDO, fg=GRIS,
                           font=("Segoe UI", 8), anchor="w", wraplength=680)
        lbl_est.pack(fill="x", padx=14, pady=(2, 2))

        def _actualizar():
            _refrescar()
            lbl_est.config(text="Actualizado.", fg=VERDE)

        def _reflexionar():
            if con is None:
                lbl_est.config(text="Sistema no disponible.", fg=ROJO)
                return
            btn_ref.config(state="disabled", text="⏳ Consultando Fable 5…")
            lbl_est.config(text="Generando reflexión profunda…", fg=ACENTO)
            v.update_idletasks()

            def en_hilo():
                resp = con.reflexion_manual()
                def en_ui():
                    btn_ref.config(state="normal", text="🔮 Reflexión profunda")
                    lbl_est.config(text="Reflexión completada.", fg=VERDE)
                    _refrescar()
                    app.decir(app.txt(
                        "Reflexion de conciencia completada, senor.",
                        "Consciousness reflection complete, sir."))
                try:
                    v.after(0, en_ui)
                except Exception:
                    pass

            threading.Thread(target=en_hilo, daemon=True, name="ConRef").start()

        def _resetear():
            if con is None:
                return
            resp = app.txt(
                "¿Resetear la memoria episódica y creencias? Esto no borra la red neuronal.",
                "Reset episodic memory and beliefs? This does not erase the neural network.")
            import tkinter.messagebox as mb
            if mb.askyesno("Confirmar reset", resp, parent=v):
                with con.memoria._lock:
                    con.memoria._episodios.clear()
                    con.memoria._vecs.clear()
                with con.creencias._lock:
                    con.creencias._betas.clear()
                lbl_est.config(text="Memoria episódica y creencias reseteadas.", fg="#f84")
                _refrescar()

        # ── Barra de override manual ─────────────────────────────────────────
        ovr_f = tk.Frame(v, bg="#0a0f1a", pady=6)
        ovr_f.pack(fill="x", padx=14, pady=(2, 0))

        tk.Label(ovr_f, text="Control manual de abstención:",
                 bg="#0a0f1a", fg=GRIS, font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))

        _modo_var = tk.StringVar(value=con.estado_override() if con else "—")
        lbl_modo  = tk.Label(ovr_f, textvariable=_modo_var,
                             bg="#0a0f1a", fg=ACENTO,
                             font=("Consolas", 9, "bold"), padx=8, pady=2)
        lbl_modo.pack(side="left", padx=(0, 12))

        def _set_auto():
            if con:
                msg = con.set_override("auto")
                _modo_var.set(con.estado_override())
                lbl_est.config(text=msg, fg=ACENTO)
                lbl_modo.config(fg=ACENTO)
                app.log(f"[Conciencia] {msg}")
                try:
                    self._sincronizar_ovr_lbl()
                except Exception:
                    pass

        def _set_forzar_actuar():
            if con:
                msg = con.set_override("forzar_actuar")
                _modo_var.set(con.estado_override())
                lbl_est.config(text=msg, fg=VERDE)
                lbl_modo.config(fg=VERDE)
                app.log(f"[Conciencia] {msg}")
                try:
                    self._sincronizar_ovr_lbl()
                except Exception:
                    pass

        def _set_forzar_abstener():
            if con:
                msg = con.set_override("forzar_abstener")
                _modo_var.set(con.estado_override())
                lbl_est.config(text=msg, fg="#f84")
                lbl_modo.config(fg="#f84")
                app.log(f"[Conciencia] {msg}")
                try:
                    self._sincronizar_ovr_lbl()
                except Exception:
                    pass

        tk.Button(ovr_f, text="🔄 Auto",
                  command=_set_auto,
                  bg="#0a1a2a", fg=ACENTO,
                  relief="flat", font=("Segoe UI", 8), cursor="hand2",
                  padx=8, pady=3).pack(side="left", padx=2)

        tk.Button(ovr_f, text="▶ Forzar operar",
                  command=_set_forzar_actuar,
                  bg="#0a2a0a", fg=VERDE,
                  relief="flat", font=("Segoe UI", 8), cursor="hand2",
                  padx=8, pady=3).pack(side="left", padx=2)

        tk.Button(ovr_f, text="⏸ Forzar abstención",
                  command=_set_forzar_abstener,
                  bg="#2a0a0a", fg="#f84",
                  relief="flat", font=("Segoe UI", 8), cursor="hand2",
                  padx=8, pady=3).pack(side="left", padx=2)

        # ── Botones de acción principales ─────────────────────────────────────
        btn_f = tk.Frame(v, bg=FONDO)
        btn_f.pack(fill="x", padx=14, pady=(4, 8))

        tk.Button(btn_f, text="🔄 Actualizar",
                  command=_actualizar, bg=PANEL, fg=ACENTO,
                  relief="flat", font=FUENTE, cursor="hand2",
                  padx=10, pady=5).pack(side="left", padx=(0, 4))

        btn_ref = tk.Button(btn_f, text="🔮 Reflexión profunda",
                            command=_reflexionar, bg="#1a1a3a", fg="#a8f",
                            relief="flat", font=FUENTE, cursor="hand2",
                            padx=10, pady=5)
        btn_ref.pack(side="left", padx=(0, 4))

        tk.Button(btn_f, text="🗑 Reset memoria",
                  command=_resetear, bg="#2a0a0a", fg=ROJO,
                  relief="flat", font=FUENTE, cursor="hand2",
                  padx=10, pady=5).pack(side="left")

        # Auto-refresco cada 8 segundos (muestra trades en tiempo real)
        def _auto_refresh():
            try:
                _refrescar()
                v.after(8000, _auto_refresh)
            except Exception:
                pass

        _refrescar()
        v.after(8000, _auto_refresh)

    # --- broker universal -----------------------------------------------
    def abrir_broker(self):  # noqa: C901
        from .broker_iq import PERFILES, ELEMENTOS_UI, TRADES_PARA_IA
        app = self.app
        broker = app.broker

        v = tk.Toplevel(self.root)
        v.title("Litch · Broker Universal")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("680x720+60+30")
        v.attributes("-topmost", True)
        v.resizable(True, True)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = tk.Frame(v, bg="#071018", pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📊  BROKER UNIVERSAL — Configuración Automática",
                 bg="#071018", fg=ACENTO,
                 font=("Segoe UI", 12, "bold")).pack()
        tk.Label(hdr,
                 text="Aprende · Optimiza · Configura cualquier broker con el ratón",
                 bg="#071018", fg=GRIS, font=("Segoe UI", 8)).pack()

        # ── Selector de broker ─────────────────────────────────────────────
        sel_frame = tk.Frame(v, bg=FONDO, pady=6)
        sel_frame.pack(fill="x", padx=14)
        tk.Label(sel_frame, text="Broker activo:", bg=FONDO, fg=TEXTO,
                 font=FUENTE).pack(side="left")
        broker_var = tk.StringVar(value=broker.broker_activo)
        nombres_brokers = list(PERFILES.keys())
        etiquetas_b = [PERFILES[k]["nombre"] for k in nombres_brokers]
        combo_var = tk.StringVar(value=PERFILES.get(broker.broker_activo, {}).get("nombre", "IQ Option"))

        def _cambiar_broker(seleccion):
            for clave, p in PERFILES.items():
                if p["nombre"] == seleccion:
                    broker.cambiar_broker(clave)
                    _refrescar_todo()
                    app.decir(app.txt(
                        f"Broker cambiado a {p['nombre']}, senor.",
                        f"Broker changed to {p['nombre']}, sir."))
                    break

        opt_broker = tk.OptionMenu(sel_frame, combo_var, *etiquetas_b,
                                   command=_cambiar_broker)
        opt_broker.config(bg=PANEL, fg=ACENTO, activebackground=ACENTO,
                          activeforeground=FONDO, relief="flat", font=FUENTE,
                          highlightthickness=0, bd=0)
        opt_broker["menu"].config(bg=PANEL, fg=TEXTO, activebackground=ACENTO,
                                  activeforeground=FONDO, font=FUENTE)
        opt_broker.pack(side="left", padx=(6, 14))

        lbl_payout = tk.Label(sel_frame, text="", bg=FONDO, fg=GRIS, font=FUENTE)
        lbl_payout.pack(side="left")

        # ── Panel de recomendación ─────────────────────────────────────────
        rec_frame = tk.LabelFrame(v, text=" Configuración Óptima Recomendada ",
                                  bg=FONDO, fg=ACENTO, font=FUENTE, pady=6)
        rec_frame.pack(fill="x", padx=14, pady=(4, 2))

        rec_grid = tk.Frame(rec_frame, bg=FONDO)
        rec_grid.pack(fill="x", padx=8)
        lbl_rec_asset  = tk.Label(rec_grid, text="Activo:    —", bg=FONDO, fg=VERDE,
                                  font=("Segoe UI", 10, "bold"), anchor="w")
        lbl_rec_asset.grid(row=0, column=0, sticky="w", padx=(0, 20))
        lbl_rec_dur    = tk.Label(rec_grid, text="Duración:  —", bg=FONDO, fg=VERDE,
                                  font=("Segoe UI", 10, "bold"), anchor="w")
        lbl_rec_dur.grid(row=0, column=1, sticky="w", padx=(0, 20))
        lbl_rec_monto  = tk.Label(rec_grid, text="Monto:     —", bg=FONDO, fg=VERDE,
                                  font=("Segoe UI", 10, "bold"), anchor="w")
        lbl_rec_monto.grid(row=0, column=2, sticky="w")
        lbl_rec_wr     = tk.Label(rec_grid, text="Win rate:  —", bg=FONDO, fg=GRIS,
                                  font=FUENTE, anchor="w")
        lbl_rec_wr.grid(row=1, column=0, sticky="w", pady=(2, 0))
        lbl_rec_trades = tk.Label(rec_grid, text="Trades:    —", bg=FONDO, fg=GRIS,
                                  font=FUENTE, anchor="w")
        lbl_rec_trades.grid(row=1, column=1, sticky="w", pady=(2, 0))

        btn_aplicar = tk.Button(
            rec_frame, text="⚙ Aplicar al broker ahora",
            bg="#1a3a1a", fg=VERDE, relief="flat",
            font=("Segoe UI", 9, "bold"), cursor="hand2", padx=12, pady=6)
        btn_aplicar.pack(pady=(6, 4))

        def _aplicar():
            cfg = broker.mejor_config()
            if cfg["trades"] < 5:
                app.decir(app.txt(
                    "Insuficientes datos todavia, senor.",
                    "Not enough data yet, sir."))
                return
            btn_aplicar.config(state="disabled", text="⏳ Aplicando…")
            v.update_idletasks()

            def en_hilo():
                res = broker.aplicar_config_completa()
                ok  = sum(res.values())
                def en_ui():
                    btn_aplicar.config(state="normal",
                                       text="⚙ Aplicar al broker ahora")
                    app.decir(app.txt(
                        f"Configuracion aplicada: {ok}/3 elementos OK, senor.",
                        f"Config applied: {ok}/3 elements OK, sir."))
                try:
                    v.after(0, en_ui)
                except Exception:
                    pass
            threading.Thread(target=en_hilo, daemon=True,
                             name="BrokerAplicar").start()

        btn_aplicar.config(command=_aplicar)

        # ── Tabla de rendimiento por activo ────────────────────────────────
        tbl_frame = tk.LabelFrame(v, text=" Rendimiento por activo ",
                                  bg=FONDO, fg=ACENTO, font=FUENTE, pady=4)
        tbl_frame.pack(fill="both", expand=True, padx=14, pady=(2, 2))

        cols = ("Activo", "Ganados", "Perdidos", "Total", "Win %")
        tree_frame = tk.Frame(tbl_frame, bg=FONDO)
        tree_frame.pack(fill="both", expand=True, padx=4)

        # Usar un ScrolledText para la tabla (evita la dependencia de ttk)
        tbl_txt = tk.Text(tree_frame, height=8, bg="#060f1a", fg=ACENTO,
                          font=("Consolas", 9), relief="flat", state="disabled")
        sb_tbl  = tk.Scrollbar(tree_frame, command=tbl_txt.yview)
        tbl_txt.config(yscrollcommand=_scroll_seguro(sb_tbl))
        sb_tbl.pack(side="right", fill="y")
        tbl_txt.pack(side="left", fill="both", expand=True)
        tbl_txt.tag_config("verde",  foreground=VERDE)
        tbl_txt.tag_config("rojo",   foreground=ROJO)
        tbl_txt.tag_config("header", foreground=ACENTO, font=("Consolas", 9, "bold"))

        def _dibujar_tabla():
            tbl_txt.config(state="normal")
            tbl_txt.delete("1.0", "end")
            filas = broker.tabla_assets()
            header_txt = f"{'Activo':<22} {'Wins':>5} {'Loss':>5} {'Tot':>5}  {'WR%':>6}\n"
            tbl_txt.insert("end", header_txt, "header")
            tbl_txt.insert("end", "─" * 52 + "\n", "header")
            if not filas:
                tbl_txt.insert("end", "  Sin estadísticas aún. Opera para que Litch aprenda.\n", "")
            for r in filas:
                tag  = "verde" if r["wr"] >= 60 else ("rojo" if r["wr"] < 50 else "")
                linea = (f"{r['asset']:<22} {r['wins']:>5} {r['losses']:>5}"
                         f" {r['total']:>5}  {r['wr']:>5.1f}%\n")
                tbl_txt.insert("end", linea, tag)
            tbl_txt.config(state="disabled")

        # ── Calibración de elementos de UI ─────────────────────────────────
        cal_frame = tk.LabelFrame(v, text=" Calibrar interfaz del broker ",
                                  bg=FONDO, fg="#e0a000", font=FUENTE, pady=4)
        cal_frame.pack(fill="x", padx=14, pady=(2, 2))

        tk.Label(cal_frame,
                 text=("Cada elemento: pulsa «Capturar», coloca el ratón sobre "
                       "ese punto en el broker y espera 5 segundos."),
                 bg=FONDO, fg=TEXTO, font=FUENTE, wraplength=600,
                 justify="left").pack(padx=8, pady=(4, 2))

        cal_grid = tk.Frame(cal_frame, bg=FONDO)
        cal_grid.pack(fill="x", padx=8, pady=2)
        _cal_labels = {}

        cal_descs = {
            "campo_monto":       "Campo de monto / apuesta",
            "selector_duracion": "Selector de duración / tiempo",
            "area_asset":        "Zona del nombre del activo",
            "boton_confirmar":   "Botón confirmar (opcional)",
        }

        for i, (elem, desc) in enumerate(cal_descs.items()):
            pos = broker._pos(elem)
            txt_pos = f"({pos[0]},{pos[1]})" if pos else "Sin calibrar"
            col_pos = VERDE if pos else "#888"

            tk.Label(cal_grid, text=desc, bg=FONDO, fg=TEXTO, font=FUENTE,
                     width=28, anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            lbl_p = tk.Label(cal_grid, text=txt_pos, bg=FONDO, fg=col_pos,
                             font=("Consolas", 8), width=14, anchor="e")
            lbl_p.grid(row=i, column=1, padx=(4, 6))
            _cal_labels[elem] = lbl_p

            def _capturar(elemento=elem, lbl=lbl_p):
                if not _PG_OK:
                    lbl.config(text="sin pyautogui", fg=ROJO)
                    return
                def cuenta(n, lbl=lbl, elemento=elemento):
                    if n > 0:
                        lbl.config(text=f"en {n}…", fg=ACENTO)
                        v.after(1000, cuenta, n - 1)
                    else:
                        p = pyautogui.position()
                        broker.guardar_posicion(elemento, p.x, p.y)
                        lbl.config(text=f"({p.x},{p.y})", fg=VERDE)
                        app.log(f"[Broker] {elemento} calibrado: ({p.x},{p.y})")
                cuenta(5)

            tk.Button(cal_grid, text="Capturar", bg=PANEL, fg=TEXTO,
                      font=FUENTE, relief="flat", cursor="hand2",
                      command=_capturar).grid(row=i, column=2, padx=2)

        # ── Botones de acción ──────────────────────────────────────────────
        act_frame = tk.Frame(v, bg=FONDO, pady=6)
        act_frame.pack(fill="x", padx=14)

        def _auto_calibrar():
            lbl_estado.config(text="🔍 Escaneando pantalla…", fg=ACENTO)
            v.update_idletasks()

            def en_hilo():
                resultado = broker.calibrar_ui_auto()
                def en_ui():
                    if resultado:
                        for elem, pos in resultado.items():
                            if elem in _cal_labels:
                                _cal_labels[elem].config(
                                    text=f"({pos[0]},{pos[1]})", fg=VERDE)
                        lbl_estado.config(
                            text=f"✓ Detectado: {', '.join(resultado.keys())}",
                            fg=VERDE)
                        app.decir(app.txt(
                            f"Calibracion automatica completada: {len(resultado)} elementos.",
                            f"Auto-calibration done: {len(resultado)} elements found."))
                    else:
                        lbl_estado.config(
                            text="⚠ No se encontraron elementos. Calibra manualmente.",
                            fg=ROJO)
                try:
                    v.after(0, en_ui)
                except Exception:
                    pass
            threading.Thread(target=en_hilo, daemon=True,
                             name="BrokerCalib").start()

        def _consultar_ia():
            lbl_estado.config(text="💭 Consultando IA…", fg=ACENTO)
            v.update_idletasks()

            def en_hilo():
                consejo = broker.consultar_ia()
                def en_ui():
                    lbl_estado.config(text=consejo[:90], fg=ACENTO)
                    app.decir(consejo[:200])
                try:
                    v.after(0, en_ui)
                except Exception:
                    pass
            threading.Thread(target=en_hilo, daemon=True,
                             name="BrokerIA").start()

        tk.Button(act_frame, text="🤖 Auto-calibrar pantalla",
                  command=_auto_calibrar,
                  bg="#1a2a3a", fg="#4af", relief="flat", font=FUENTE,
                  cursor="hand2", padx=10, pady=5).pack(side="left", padx=(0, 4))

        tk.Button(act_frame, text="🧠 Consultar IA",
                  command=_consultar_ia,
                  bg="#1a1a3a", fg="#a8f", relief="flat", font=FUENTE,
                  cursor="hand2", padx=10, pady=5).pack(side="left", padx=(0, 4))

        tk.Button(act_frame, text="🔄 Actualizar stats",
                  command=lambda: _refrescar_todo(),
                  bg=PANEL, fg=ACENTO, relief="flat", font=FUENTE,
                  cursor="hand2", padx=10, pady=5).pack(side="left", padx=(0, 4))

        def _forzar_aprendizaje():
            broker.consejero._trades_desde_ia = 99
            lbl_estado.config(
                text="Aprendizaje IA forzado — se ejecutará en el próximo ciclo (≤60s)",
                fg=ACENTO)
            app.decir(app.txt(
                "Forzando consulta de aprendizaje a la IA en el proximo ciclo, senor.",
                "Forcing AI learning query on the next cycle, sir."))

        tk.Button(act_frame, text="📚 Forzar aprendizaje IA",
                  command=_forzar_aprendizaje,
                  bg="#2a1a3a", fg="#c8a0ff", relief="flat", font=FUENTE,
                  cursor="hand2", padx=10, pady=5).pack(side="left", padx=(0, 4))

        def _resumen_sesion():
            btn_sesion.config(state="disabled", text="⏳ Analizando…")
            lbl_estado.config(text="Generando informe de sesión con Fable 5…", fg=ACENTO)
            v.update_idletasks()

            def en_hilo():
                reporte = broker.resumen_sesion_ia()

                def en_ui():
                    btn_sesion.config(state="normal", text="🔍 Sesión IA")
                    lbl_estado.config(text="Informe de sesión generado.", fg=VERDE)

                    # Popup con el reporte completo
                    pop = tk.Toplevel(v)
                    pop.title("Fable 5 · Informe de Sesión")
                    self._aplicar_icono(pop)
                    pop.configure(bg=FONDO)
                    pop.geometry("700x560+100+60")
                    pop.attributes("-topmost", True)

                    tk.Label(pop, text="INFORME DE SESIÓN — FABLE 5",
                             bg="#071018", fg=ACENTO,
                             font=("Segoe UI", 12, "bold"),
                             pady=8).pack(fill="x")

                    txt_pop = tk.Text(pop, bg="#060f1a", fg=TEXTO,
                                     font=("Consolas", 9), relief="flat",
                                     wrap="word", padx=10, pady=8)
                    sb_pop  = tk.Scrollbar(pop, command=txt_pop.yview)
                    txt_pop.config(yscrollcommand=_scroll_seguro(sb_pop))
                    sb_pop.pack(side="right", fill="y")
                    txt_pop.pack(fill="both", expand=True)

                    txt_pop.tag_config("sep",    foreground=ACENTO)
                    txt_pop.tag_config("titulo", foreground=ACENTO,
                                       font=("Consolas", 9, "bold"))
                    txt_pop.tag_config("verde",  foreground=VERDE)
                    txt_pop.tag_config("rojo",   foreground=ROJO)

                    for linea in reporte.splitlines():
                        if linea.startswith("═") or linea.startswith("─"):
                            txt_pop.insert("end", linea + "\n", "sep")
                        elif "INFORME" in linea or "RESUMEN" in linea or "ANÁLISIS" in linea:
                            txt_pop.insert("end", linea + "\n", "titulo")
                        elif "RENTABLE" in linea or "Win Rate:" in linea:
                            txt_pop.insert("end", linea + "\n", "verde")
                        elif "PÉRDIDA" in linea or "riesgo" in linea.lower():
                            txt_pop.insert("end", linea + "\n", "rojo")
                        else:
                            txt_pop.insert("end", linea + "\n")

                    txt_pop.config(state="disabled")

                    tk.Button(pop, text="Cerrar",
                              command=pop.destroy,
                              bg=PANEL, fg=TEXTO, relief="flat", font=FUENTE,
                              cursor="hand2", padx=12, pady=5).pack(pady=6)

                    app.decir(app.txt(
                        "Informe de sesion listo, senor. Revisa la ventana Fable 5.",
                        "Session report ready, sir. Check the Fable 5 window."))

                try:
                    v.after(0, en_ui)
                except Exception:
                    pass

            threading.Thread(target=en_hilo, daemon=True,
                             name="BrokerSesion").start()

        btn_sesion = tk.Button(act_frame, text="🔍 Sesión IA",
                               command=_resumen_sesion,
                               bg="#1a3a2a", fg="#4dffaa", relief="flat", font=FUENTE,
                               cursor="hand2", padx=10, pady=5)
        btn_sesion.pack(side="left")

        # Balance demo (ajustable para cálculo Kelly)
        bal_frame = tk.Frame(v, bg=FONDO)
        bal_frame.pack(fill="x", padx=14, pady=(2, 0))
        tk.Label(bal_frame, text="Balance demo ($) para Kelly:",
                 bg=FONDO, fg=TEXTO, font=FUENTE).pack(side="left")
        bal_var = tk.StringVar(
            value=str(int(app.mem["config"].get("balance_demo", 10000))))
        bal_entry = tk.Entry(bal_frame, textvariable=bal_var, bg=PANEL, fg=TEXTO,
                             font=("Consolas", 10), relief="flat", width=10,
                             insertbackground=TEXTO)
        bal_entry.pack(side="left", padx=(6, 4), ipady=3)

        def _guardar_balance():
            try:
                app.mem["config"]["balance_demo"] = float(bal_var.get())
                memoria.guardar(app.mem)
                _refrescar_todo()
            except ValueError:
                pass

        tk.Button(bal_frame, text="Guardar", bg=PANEL, fg=VERDE, relief="flat",
                  font=FUENTE, cursor="hand2", padx=8, pady=3,
                  command=_guardar_balance).pack(side="left")

        # ── Panel de Parámetros Manuales ──────────────────────────────────
        param_frame = tk.LabelFrame(v,
            text=" ⚙ Parámetros de Operación (aplica a todos los brokers) ",
            bg=FONDO, fg="#e0a000", font=FUENTE, pady=6)
        param_frame.pack(fill="x", padx=14, pady=(4, 2))

        pg = tk.Frame(param_frame, bg=FONDO)
        pg.pack(fill="x", padx=8, pady=(2, 4))

        # ── Fila 0: Monto por trade ──────────────────────────────────────
        tk.Label(pg, text="Monto ($):", bg=FONDO, fg=TEXTO,
                 font=FUENTE, width=14, anchor="w").grid(row=0, column=0, sticky="w", pady=3)
        monto_var = tk.StringVar(value=str(app.mem["config"].get("monto_base", 10.0)))
        monto_entry = tk.Entry(pg, textvariable=monto_var, bg=PANEL, fg=TEXTO,
                               font=("Consolas", 10), relief="flat", width=9,
                               insertbackground=TEXTO)
        monto_entry.grid(row=0, column=1, padx=(4, 8), ipady=3)

        manual_var = tk.BooleanVar(value=bool(app.mem["config"].get("monto_modo_manual", False)))
        tk.Checkbutton(pg, text="Fijo (sin Kelly)",
                       variable=manual_var,
                       bg=FONDO, fg=TEXTO, selectcolor=PANEL,
                       activebackground=FONDO, activeforeground=ACENTO,
                       font=FUENTE).grid(row=0, column=2, padx=(0, 14), sticky="w")

        # ── Fila 1: Montos a probar (rotación de aprendizaje) ────────────
        tk.Label(pg, text="Rotar montos:", bg=FONDO, fg=TEXTO,
                 font=FUENTE, width=14, anchor="w").grid(row=1, column=0, sticky="w", pady=3)
        montos_test_var = tk.StringVar(
            value=app.mem["config"].get("montos_test", "10,50,100,500"))
        montos_entry = tk.Entry(pg, textvariable=montos_test_var, bg=PANEL, fg=TEXTO,
                                font=("Consolas", 10), relief="flat", width=26,
                                insertbackground=TEXTO)
        montos_entry.grid(row=1, column=1, columnspan=3, padx=(4, 8), ipady=3, sticky="w")
        tk.Label(pg, text="← Litch aprende cuál rinde más", bg=FONDO,
                 fg=GRIS, font=("Segoe UI", 7)).grid(row=1, column=4, sticky="w")

        # ── Fila 2: Duración (período de vela) ───────────────────────────
        tk.Label(pg, text="Duración (seg):", bg=FONDO, fg=TEXTO,
                 font=FUENTE, width=14, anchor="w").grid(row=2, column=0, sticky="w", pady=3)
        dur_var = tk.StringVar(value=str(app.mem["config"].get("periodo_vela", 60)))
        dur_entry = tk.Entry(pg, textvariable=dur_var, bg=PANEL, fg=TEXTO,
                             font=("Consolas", 10), relief="flat", width=7,
                             insertbackground=TEXTO)
        dur_entry.grid(row=2, column=1, padx=(4, 4), ipady=3)

        dur_btn_f = tk.Frame(pg, bg=FONDO)
        dur_btn_f.grid(row=2, column=2, columnspan=3, sticky="w")
        for d in (10, 15, 30, 60, 120, 300):
            lbl_d = d
            tk.Button(dur_btn_f, text=f"{d}s", bg=PANEL, fg=ACENTO, relief="flat",
                      font=("Consolas", 8), cursor="hand2", padx=5,
                      command=lambda x=d: dur_var.set(str(x))
                      ).pack(side="left", padx=1)

        # ── Fila 3: Parámetros de patrones ───────────────────────────────
        tk.Label(pg, text="Longitud patrón:", bg=FONDO, fg=TEXTO,
                 font=FUENTE, width=14, anchor="w").grid(row=3, column=0, sticky="w", pady=3)
        longpat_var = tk.StringVar(value=str(app.mem["config"].get("longitud_patron", 3)))
        tk.Entry(pg, textvariable=longpat_var, bg=PANEL, fg=TEXTO,
                 font=("Consolas", 10), relief="flat", width=4,
                 insertbackground=TEXTO).grid(row=3, column=1, padx=(4, 8), ipady=3)

        tk.Label(pg, text="Min. obs:", bg=FONDO, fg=TEXTO,
                 font=FUENTE).grid(row=3, column=2, sticky="w")
        minobs_var = tk.StringVar(value=str(app.mem["config"].get("min_observaciones", 8)))
        tk.Entry(pg, textvariable=minobs_var, bg=PANEL, fg=TEXTO,
                 font=("Consolas", 10), relief="flat", width=4,
                 insertbackground=TEXTO).grid(row=3, column=3, padx=(4, 8), ipady=3)

        tk.Label(pg, text="Umbral:", bg=FONDO, fg=TEXTO,
                 font=FUENTE).grid(row=3, column=4, sticky="w")
        umbral_var = tk.StringVar(value=str(app.mem["config"].get("umbral_probabilidad", 0.65)))
        tk.Entry(pg, textvariable=umbral_var, bg=PANEL, fg=TEXTO,
                 font=("Consolas", 10), relief="flat", width=5,
                 insertbackground=TEXTO).grid(row=3, column=5, padx=(4, 8), ipady=3)

        # ── Stats de montos (mini-tabla dinámica) ────────────────────────
        lbl_montos_stats = tk.Label(param_frame, text="", bg=FONDO, fg=GRIS,
                                    font=("Consolas", 8), anchor="w", justify="left")
        lbl_montos_stats.pack(fill="x", padx=10, pady=(0, 2))

        def _actualizar_stats_montos():
            filas = broker.tabla_montos()
            if not filas:
                lbl_montos_stats.config(
                    text="  Sin montos configurados — escribe montos separados por coma arriba.")
                return
            partes = []
            for f in filas:
                wr_txt = f"{f['wr']:.0f}%" if f["wr"] is not None else "?"
                partes.append(f"${f['monto']:.0f}→{wr_txt}({f['total']}t)")
            lbl_montos_stats.config(text="  Rendimiento por monto: " + "  ".join(partes))

        def _guardar_params():
            try:
                nuevo_monto = float(monto_var.get())
                nueva_dur   = int(dur_var.get())
                nuevo_lp    = max(1, min(5, int(longpat_var.get())))
                nuevo_mo    = max(2, min(30, int(minobs_var.get())))
                nuevo_um    = max(0.51, min(0.90, float(umbral_var.get())))
                nuevo_mt    = montos_test_var.get().strip()

                app.mem["config"]["monto_base"]          = nuevo_monto
                app.mem["config"]["monto_modo_manual"]   = bool(manual_var.get())
                app.mem["config"]["montos_test"]         = nuevo_mt
                app.mem["config"]["periodo_vela"]        = nueva_dur
                app.mem["config"]["longitud_patron"]     = nuevo_lp
                app.mem["config"]["min_observaciones"]   = nuevo_mo
                app.mem["config"]["umbral_probabilidad"] = round(nuevo_um, 2)
                memoria.guardar(app.mem)
                _actualizar_stats_montos()
                _refrescar_todo()
                app.log(f"[Params] Guardado: monto=${nuevo_monto} dur={nueva_dur}s "
                        f"patrón={nuevo_lp} obs={nuevo_mo} umbral={nuevo_um:.2f} "
                        f"montos_test='{nuevo_mt}'")
                app.decir(app.txt(
                    f"Parametros actualizados: monto {nuevo_monto:.0f} dolares, "
                    f"duracion {nueva_dur} segundos, umbrales ajustados, senor.",
                    f"Parameters updated: amount {nuevo_monto:.0f} dollars, "
                    f"duration {nueva_dur}s, thresholds adjusted, sir."))
            except ValueError as _e:
                app.log(f"[Params] Valor inválido: {_e}")

        tk.Button(pg, text="Guardar todo", bg="#1a3a1a", fg=VERDE,
                  relief="flat", font=("Segoe UI", 9, "bold"),
                  cursor="hand2", padx=10, pady=5,
                  command=_guardar_params).grid(row=4, column=0, columnspan=6,
                                                pady=(6, 2), sticky="w")

        _actualizar_stats_montos()

        # ── Lecciones de la IA ────────────────────────────────────────────
        lec_frame = tk.LabelFrame(v, text=" Lecciones que la IA enseñó a Litch ",
                                  bg=FONDO, fg="#c8a0ff", font=FUENTE, pady=4)
        lec_frame.pack(fill="x", padx=14, pady=(2, 2))

        lec_txt = tk.Text(lec_frame, height=5, bg="#0d0a18", fg="#c8a0ff",
                          font=("Consolas", 8), relief="flat", state="disabled",
                          wrap="word")
        sb_lec  = tk.Scrollbar(lec_frame, command=lec_txt.yview)
        lec_txt.config(yscrollcommand=_scroll_seguro(sb_lec))
        sb_lec.pack(side="right", fill="y")
        lec_txt.pack(side="left", fill="x", expand=True, padx=(4, 0))

        def _dibujar_lecciones():
            lec_txt.config(state="normal")
            lec_txt.delete("1.0", "end")
            lecciones = broker.lecciones_recientes(5)
            if not lecciones:
                lec_txt.insert("end",
                    "  Sin lecciones aún. Opera y activa Claude/Ollama para que Litch aprenda.\n")
            else:
                for lec in reversed(lecciones):
                    fecha  = lec.get("fecha", "")[:16].replace("T", " ")
                    texto  = lec.get("leccion", "")
                    lec_txt.insert("end", f"[{fecha}]\n{texto}\n\n")
            lec_txt.config(state="disabled")

        # Estado del consejero (indicador live)
        estado_consejero_frame = tk.Frame(v, bg=FONDO)
        estado_consejero_frame.pack(fill="x", padx=14, pady=(2, 0))
        lbl_consejero = tk.Label(
            estado_consejero_frame,
            text="● Consejero: iniciando…",
            bg=FONDO, fg=GRIS, font=("Segoe UI", 8), anchor="w")
        lbl_consejero.pack(side="left")

        def _actualizar_consejero():
            """Muestra si el consejero está vivo y cuántos trades quedan para la IA."""
            try:
                vivo  = broker.consejero.is_alive()
                n_ia  = TRADES_PARA_IA - broker.consejero._trades_desde_ia
                n_ia  = max(0, n_ia)
                texto = (f"● Consejero: {'activo' if vivo else 'inactivo'}  |  "
                         f"Próxima consulta IA en {n_ia} trades")
                color = VERDE if vivo else ROJO
                lbl_consejero.config(text=texto, fg=color)
            except Exception:
                pass
            try:
                v.after(5000, _actualizar_consejero)
            except Exception:
                pass

        _actualizar_consejero()

        # ── Estado ────────────────────────────────────────────────────────
        lbl_estado = tk.Label(v, text="", bg=FONDO, fg=GRIS, font=("Segoe UI", 8),
                              anchor="w", wraplength=650)
        lbl_estado.pack(fill="x", padx=14, pady=(4, 8))

        # ── Función de refresco global ─────────────────────────────────────
        def _refrescar_todo():
            cfg = broker.mejor_config()
            lbl_rec_asset.config(text=f"Activo:    {cfg['asset']}")
            lbl_rec_dur.config(text=f"Duración:  {cfg['duracion']}s")
            lbl_rec_monto.config(text=f"Monto:     ${cfg['monto']:.0f}")
            wr_col = VERDE if cfg["win_rate"] >= 60 else (ROJO if cfg["win_rate"] < 50 else "#f4a261")
            lbl_rec_wr.config(text=f"Win rate:  {cfg['win_rate']:.1f}%  "
                              f"(hora: {cfg.get('score_hora', 0):.0f}%)", fg=wr_col)
            lbl_rec_trades.config(text=f"Trades:    {cfg['trades']}")
            payout = broker.perfil.get("payout", 0.85) * 100
            lbl_payout.config(text=f"Payout: {payout:.0f}%")
            _dibujar_tabla()
            _dibujar_lecciones()
            # Actualizar etiquetas de calibración
            for elem, lbl in _cal_labels.items():
                pos = broker._pos(elem)
                if pos:
                    lbl.config(text=f"({pos[0]},{pos[1]})", fg=VERDE)

        _refrescar_todo()

    # ── Meta Diaria ───────────────────────────────────────────────────────────
    def abrir_meta(self):  # noqa: C901
        """Panel de configuración y seguimiento de la Meta Diaria."""
        if hasattr(self, "_ventana_meta") and self._ventana_meta is not None:
            try:
                if self._ventana_meta.winfo_exists():
                    self._ventana_meta.lift()
                    self._ventana_meta.focus_force()
                    return
            except Exception:
                pass

        v = tk.Toplevel(self.root)
        self._ventana_meta = v
        v.title("Litch · Meta Diaria")
        self._aplicar_icono(v)
        v.configure(bg=FONDO)
        v.geometry("520x620")
        v.attributes("-topmost", True)
        v.resizable(False, True)

        def _on_close():
            self._ventana_meta = None
            v.destroy()
        v.protocol("WM_DELETE_WINDOW", _on_close)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = tk.Frame(v, bg="#071018", pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎯  META DIARIA",
                 bg="#071018", fg="#00e5ff",
                 font=("Segoe UI", 14, "bold")).pack()
        tk.Label(hdr, text="Litch opera hasta alcanzar tu objetivo y luego hiberna.",
                 bg="#071018", fg=GRIS, font=("Segoe UI", 8)).pack()

        # ── Configuración ──────────────────────────────────────────────────
        frm_cfg = tk.LabelFrame(v, text=" Configurar nueva sesión ",
                                bg=FONDO, fg=ACENTO,
                                font=("Segoe UI", 9, "bold"), padx=16, pady=12)
        frm_cfg.pack(fill="x", padx=16, pady=(14, 0))

        tk.Label(frm_cfg, text="Meta de ganancia ($):", bg=FONDO, fg=TEXTO,
                 font=FUENTE).grid(row=0, column=0, sticky="w", pady=5)
        ent_meta = tk.Entry(frm_cfg, bg=PANEL, fg="#00ff88", font=("Segoe UI", 12, "bold"),
                            relief="flat", insertbackground=TEXTO, width=10, justify="center")
        ent_meta.grid(row=0, column=1, padx=(12, 0), pady=5, ipady=6)
        ent_meta.insert(0, "50")

        tk.Label(frm_cfg, text="Stop de pérdidas ($):", bg=FONDO, fg=TEXTO,
                 font=FUENTE).grid(row=1, column=0, sticky="w", pady=5)
        ent_stop = tk.Entry(frm_cfg, bg=PANEL, fg="#ff4444", font=("Segoe UI", 12, "bold"),
                            relief="flat", insertbackground=TEXTO, width=10, justify="center")
        ent_stop.grid(row=1, column=1, padx=(12, 0), pady=5, ipady=6)
        ent_stop.insert(0, "25")

        # ── Estado en vivo ─────────────────────────────────────────────────
        frm_live = tk.LabelFrame(v, text=" Estado en vivo ",
                                 bg=FONDO, fg=ACENTO,
                                 font=("Segoe UI", 9, "bold"), padx=16, pady=10)
        frm_live.pack(fill="x", padx=16, pady=(10, 0))

        lbl_estado_meta = tk.Label(frm_live, text="No configurada",
                                   bg=FONDO, fg=GRIS, font=("Segoe UI", 11, "bold"))
        lbl_estado_meta.pack()

        cvs_barra = tk.Canvas(frm_live, bg=PANEL, height=22, relief="flat",
                               highlightthickness=0)
        cvs_barra.pack(fill="x", pady=(6, 2))

        lbl_stats = tk.Label(frm_live, text="",
                             bg=FONDO, fg=GRIS, font=("Segoe UI", 9))
        lbl_stats.pack()

        def _refrescar_live():
            meta = getattr(self.app, "meta_diaria", None)
            if not meta:
                return
            s    = meta.stats()
            pnl  = s["pnl"]
            sgn  = "+" if pnl >= 0 else ""

            if not s["activa"] and not s["completada"]:
                lbl_estado_meta.config(text="No configurada", fg=GRIS)
                cvs_barra.delete("all")
                lbl_stats.config(text="")
                return

            # Color y texto según estado
            if s["completada"]:
                if s["razon"] == "META_ALCANZADA":
                    lbl_estado_meta.config(
                        text=f"✅ TAREA COMPLETADA  {sgn}${pnl:.2f}",
                        fg="#88ff88")
                    color_barra = "#2ecc71"
                else:
                    lbl_estado_meta.config(
                        text=f"⛔ STOP ACTIVADO  ${pnl:.2f}",
                        fg="#ff4444")
                    color_barra = "#e74c3c"
            elif pnl >= 0:
                lbl_estado_meta.config(
                    text=f"🎯 P&L: {sgn}${pnl:.2f} / ${s['meta_gan']:.0f}",
                    fg="#00ff88")
                color_barra = "#2ecc71"
            else:
                lbl_estado_meta.config(
                    text=f"📉 P&L: ${pnl:.2f}  (Stop: -${s['stop_perd']:.0f})",
                    fg="#ff4444")
                color_barra = "#e74c3c"

            # Barra de progreso
            limite = s["meta_gan"] if pnl >= 0 else s["stop_perd"]
            pct    = min(1.0, abs(pnl) / max(limite, 0.01))
            w      = cvs_barra.winfo_width() or 460
            cvs_barra.delete("all")
            cvs_barra.create_rectangle(0, 0, w, 22, fill=PANEL, outline="")
            cvs_barra.create_rectangle(0, 0, int(w * pct), 22,
                                        fill=color_barra, outline="")
            cvs_barra.create_text(w // 2, 11,
                                   text=f"{int(pct * 100)}%",
                                   fill="white", font=("Segoe UI", 9, "bold"))

            lbl_stats.config(
                text=f"{s['wins']}W  {s['losses']}L  |  {s['trades']} trades  "
                     f"|  inicio {s['hora_inicio']}",
                fg=GRIS)

            if not s["completada"]:
                v.after(2000, _refrescar_live)

        # ── Botones ────────────────────────────────────────────────────────
        frm_btns = tk.Frame(v, bg=FONDO)
        frm_btns.pack(fill="x", padx=16, pady=12)

        def _activar():
            try:
                mg   = float(ent_meta.get().replace(",", "."))
                sp   = float(ent_stop.get().replace(",", "."))
            except ValueError:
                self.app.log("[Meta] Valores inválidos — usa números.")
                return
            meta = getattr(self.app, "meta_diaria", None)
            if not meta:
                from . import meta_diaria as _md
                meta = _md.obtener(self.app)
                self.app.meta_diaria = meta
            meta.configurar(mg, sp)
            btn_activar.config(state="disabled", text="✓ Activa")
            btn_desactivar.config(state="normal")
            _refrescar_live()

        def _desactivar():
            meta = getattr(self.app, "meta_diaria", None)
            if meta:
                meta.desactivar()
            btn_activar.config(state="normal", text="▶ ACTIVAR META")
            btn_desactivar.config(state="disabled")
            _refrescar_live()

        meta_actual = getattr(self.app, "meta_diaria", None)
        meta_on     = bool(meta_actual and meta_actual.activa)

        btn_activar = tk.Button(
            frm_btns, text="▶ ACTIVAR META",
            bg="#00aa44", fg="white", relief="flat",
            font=("Segoe UI", 11, "bold"), cursor="hand2",
            padx=20, pady=10, command=_activar,
            state="disabled" if meta_on else "normal")
        btn_activar.pack(side="left", expand=True, fill="x", padx=(0, 6))

        btn_desactivar = tk.Button(
            frm_btns, text="⏹ DESACTIVAR",
            bg="#882222", fg="white", relief="flat",
            font=("Segoe UI", 11, "bold"), cursor="hand2",
            padx=20, pady=10, command=_desactivar,
            state="normal" if meta_on else "disabled")
        btn_desactivar.pack(side="right", expand=True, fill="x")

        # ── Historial de sesiones ─────────────────────────────────────────
        frm_hist = tk.LabelFrame(v, text=" Historial de sesiones ",
                                 bg=FONDO, fg=ACENTO,
                                 font=("Segoe UI", 9, "bold"))
        frm_hist.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        cols_hist = ("Fecha", "Inicio", "Cierre", "P&L", "W/L", "Razón")
        tree = ttk.Treeview(frm_hist, columns=cols_hist,
                             show="headings", height=7)
        for col in cols_hist:
            tree.heading(col, text=col)
            tree.column(col, width=72, anchor="center")
        tree.column("Fecha", width=88)
        tree.column("Razón", width=120)
        tree.pack(fill="both", expand=True, padx=4, pady=4)

        # Estilo de filas
        tree.tag_configure("win",  background="#001a00", foreground="#88ff88")
        tree.tag_configure("loss", background="#1a0000", foreground="#ff8888")
        tree.tag_configure("par",  background=PANEL,     foreground=TEXTO)

        def _cargar_historial():
            for row in tree.get_children():
                tree.delete(row)
            meta = getattr(self.app, "meta_diaria", None)
            if meta:
                sesiones = meta.historial(20)
                for i, s in enumerate(reversed(sesiones)):
                    sgn   = "+" if s["pnl"] >= 0 else ""
                    tag   = "win" if s["pnl"] >= 0 else "loss"
                    if tag == "win" and i % 2 == 0:
                        tag = "par"
                    tree.insert("", "end", values=(
                        s.get("fecha", ""),
                        s.get("inicio", ""),
                        s.get("cierre", ""),
                        f"{sgn}${s['pnl']:.2f}",
                        f"{s['wins']}W/{s['losses']}L",
                        s.get("razon", "").replace("_", " "),
                    ), tags=(tag,))

        _cargar_historial()

        # Inicio de los refrescos en vivo
        v.after(500, _refrescar_live)
        ent_meta.focus_force()

    # ─────────────────────────────────────────────────────────────────────
    # GRÁFICO DE VELAS INTERACTIVO
    # ─────────────────────────────────────────────────────────────────────
    def abrir_grafico_velas(self):  # noqa: C901
        """Ventana flotante con gráfico de velas OHLC + EMA + RSI en tiempo real."""
        if hasattr(self, "_win_chart") and self._win_chart.winfo_exists():
            self._win_chart.lift()
            self._win_chart.focus_force()
            return

        app  = self.app
        feed = getattr(app, "tv_feed", None)

        win = tk.Toplevel(self.root)
        win.title("Gráfico de Velas — Litch")
        self._aplicar_icono(win)
        win.configure(bg=FONDO)
        win.attributes("-topmost", True)
        win.resizable(True, True)
        win.geometry("820x580")
        self._win_chart = win

        _CG   = "#0a1420"    # fondo canvas
        _GRID = "#0e1e30"    # grid
        _UP   = "#2ecc71"    # vela alcista
        _DN   = "#e74c3c"    # vela bajista
        _EMA9 = "#00d4ff"    # EMA9
        _EMA21= "#f39c12"    # EMA21
        _RSI  = "#a8f"       # RSI línea
        _TXT  = "#d6e6f2"

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg=FONDO, pady=4)
        hdr.pack(fill="x", padx=8)

        self._lbl_chart_titulo = tk.Label(
            hdr, text="Cargando…", bg=FONDO, fg=ACENTO,
            font=("Segoe UI", 11, "bold"))
        self._lbl_chart_titulo.pack(side="left")

        self._lbl_chart_precio = tk.Label(
            hdr, text="", bg=FONDO, fg=VERDE,
            font=("Consolas", 12, "bold"))
        self._lbl_chart_precio.pack(side="left", padx=16)

        self._lbl_chart_ind = tk.Label(
            hdr, text="", bg=FONDO, fg=GRIS,
            font=("Segoe UI", 8))
        self._lbl_chart_ind.pack(side="left")

        # Selector de número de velas
        tk.Label(hdr, text="Velas:", bg=FONDO, fg=GRIS,
                 font=("Segoe UI", 8)).pack(side="right", padx=(0, 4))
        self._chart_n_var = tk.IntVar(value=60)
        for n in (30, 60, 100, 200):
            tk.Radiobutton(hdr, text=str(n), variable=self._chart_n_var,
                           value=n, command=lambda: self._redibujar_chart(),
                           bg=FONDO, fg=GRIS, selectcolor=FONDO,
                           activebackground=FONDO, activeforeground=ACENTO,
                           font=("Segoe UI", 8)).pack(side="right")

        tk.Frame(win, bg=ACENTO, height=1).pack(fill="x", padx=8)

        # ── Canvas principal (velas) ───────────────────────────────────────
        frame_c = tk.Frame(win, bg=_CG)
        frame_c.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        self._chart_canvas = tk.Canvas(
            frame_c, bg=_CG, highlightthickness=0, cursor="crosshair")
        self._chart_canvas.pack(fill="both", expand=True)

        # ── Canvas RSI (subpanel) ─────────────────────────────────────────
        tk.Frame(win, bg="#050d18", height=1).pack(fill="x", padx=8)
        self._rsi_canvas = tk.Canvas(
            win, bg="#050d18", height=80,
            highlightthickness=0)
        self._rsi_canvas.pack(fill="x", padx=8, pady=(0, 4))

        # ── Footer status ─────────────────────────────────────────────────
        self._lbl_chart_status = tk.Label(
            win, text="", bg=FONDO, fg=GRIS, font=("Segoe UI", 7))
        self._lbl_chart_status.pack(pady=(0, 4))

        # ── Función de dibujo ─────────────────────────────────────────────
        def _dibujar(velas):
            if not velas:
                return
            cv  = self._chart_canvas
            rcv = self._rsi_canvas
            cv.delete("all")
            rcv.delete("all")

            W = cv.winfo_width()
            H = cv.winfo_height()
            if W < 10 or H < 10:
                return

            pad_l, pad_r, pad_t, pad_b = 52, 12, 10, 28
            area_w = W - pad_l - pad_r
            area_h = H - pad_t - pad_b

            n   = len(velas)
            vw  = max(2, area_w // n)        # ancho por vela
            cw  = max(1, int(vw * 0.6))      # cuerpo de vela

            highs  = [v["h"] for v in velas]
            lows   = [v["l"] for v in velas]
            closes = [v["c"] for v in velas]
            opens  = [v["o"] for v in velas]

            mn, mx = min(lows), max(highs)
            rng = mx - mn or 1e-8

            def py(precio):
                return pad_t + area_h - int((precio - mn) / rng * area_h)

            def px(i):
                return pad_l + i * vw + vw // 2

            # ── Grid horizontal ───────────────────────────────────────────
            for step in range(5):
                y = pad_t + int(area_h * step / 4)
                cv.create_line(pad_l, y, W - pad_r, y, fill=_GRID, dash=(2, 4))
                precio_lbl = mx - (mx - mn) * step / 4
                cv.create_text(pad_l - 4, y, text=f"{precio_lbl:.5g}",
                               fill="#4a6b7a", font=("Consolas", 7), anchor="e")

            # ── EMA9 y EMA21 ──────────────────────────────────────────────
            try:
                import numpy as _np
                arr = _np.array(closes, dtype=float)

                def _ema_line(periodo, color, tag):
                    if len(arr) < periodo:
                        return
                    k   = 2.0 / (periodo + 1)
                    ema = arr[:periodo].mean()
                    vals = [ema]
                    for c in arr[periodo:]:
                        ema = c * k + ema * (1 - k)
                        vals.append(ema)
                    offset = n - len(vals)
                    pts = []
                    for i, v in enumerate(vals):
                        pts += [px(i + offset), py(v)]
                    if len(pts) >= 4:
                        cv.create_line(*pts, fill=color, width=1, smooth=True, tags=tag)

                _ema_line(9,  _EMA9,  "ema9")
                _ema_line(21, _EMA21, "ema21")
            except Exception:
                pass

            # ── Velas OHLC ────────────────────────────────────────────────
            for i, v in enumerate(velas):
                x   = px(i)
                col = _UP if v["c"] >= v["o"] else _DN
                # Mecha
                cv.create_line(x, py(v["h"]), x, py(v["l"]), fill=col, width=1)
                # Cuerpo
                y1 = py(max(v["o"], v["c"]))
                y2 = py(min(v["o"], v["c"]))
                if y2 <= y1:
                    y2 = y1 + 1
                cv.create_rectangle(
                    x - cw // 2, y1, x + cw // 2, y2,
                    fill=col, outline=col)

            # ── Eje tiempo (últimas 5 velas visibles) ────────────────────
            import time as _time
            step_t = max(1, n // 5)
            for i in range(0, n, step_t):
                ts = velas[i].get("ts", 0)
                if ts:
                    lbl = _time.strftime("%H:%M", _time.localtime(ts))
                    cv.create_text(px(i), H - pad_b + 4, text=lbl,
                                   fill="#4a6b7a", font=("Consolas", 7))

            # ── Precio actual línea punteada ──────────────────────────────
            ultimo = closes[-1]
            y_ult  = py(ultimo)
            cv.create_line(pad_l, y_ult, W - pad_r, y_ult,
                           fill=ACENTO, dash=(3, 3), width=1)
            cv.create_text(W - pad_r + 2, y_ult, text=f"{ultimo:.5g}",
                           fill=ACENTO, font=("Consolas", 7, "bold"), anchor="w")

            # ── Leyenda EMA ───────────────────────────────────────────────
            cv.create_text(pad_l + 4, pad_t + 2,
                           text=f"EMA9  EMA21",
                           fill=_EMA9, font=("Segoe UI", 7), anchor="nw")

            # ── RSI subpanel ──────────────────────────────────────────────
            try:
                rw = rcv.winfo_width()
                rh = rcv.winfo_height()
                if rw < 10 or rh < 10 or not _np:
                    return
                arr_c = _np.array(closes, dtype=float)
                if len(arr_c) < 15:
                    return
                per = 14
                deltas = _np.diff(arr_c)
                g = _np.where(deltas > 0, deltas, 0.0)
                l = _np.where(deltas < 0, -deltas, 0.0)
                ag = g[:per].mean(); al = l[:per].mean()
                rsis = []
                for i in range(per, len(g)):
                    ag = (ag * (per - 1) + g[i]) / per
                    al = (al * (per - 1) + l[i]) / per
                    rs = (ag / al) if al > 0 else 100.0
                    rsis.append(100 - 100 / (1 + rs))

                if len(rsis) < 2:
                    return
                # Grid RSI
                for lvl, col in ((30, "#2a3a2a"), (50, _GRID), (70, "#3a2a2a")):
                    yv = int((1 - lvl / 100) * rh)
                    rcv.create_line(0, yv, rw, yv, fill=col, dash=(2, 4))
                    rcv.create_text(4, yv, text=str(lvl),
                                    fill="#4a6b7a", font=("Consolas", 6), anchor="w")
                # Línea RSI
                offset_r = n - len(rsis)
                pts_rsi  = []
                for i, rv in enumerate(rsis):
                    xr = pad_l + (i + offset_r) * vw + vw // 2
                    yr = int((1 - rv / 100) * rh)
                    pts_rsi += [xr, yr]
                if len(pts_rsi) >= 4:
                    rcv.create_line(*pts_rsi, fill=_RSI, width=1, smooth=True)
                # Valor RSI actual
                rv_ult = rsis[-1]
                col_r = (_UP if rv_ult < 30 else _DN if rv_ult > 70 else ACENTO)
                rcv.create_text(rw - 4, 4, text=f"RSI {rv_ult:.1f}",
                                fill=col_r, font=("Consolas", 7, "bold"), anchor="ne")
            except Exception:
                pass

        def _refrescar():
            if not win.winfo_exists():
                return
            n_velas = self._chart_n_var.get()
            velas   = []
            activo  = (app.mem.get("config", {}).get("asset_actual")
                       or app.mem.get("config", {}).get("activo", "—"))

            if feed:
                velas = feed.obtener_velas(n_velas)

            if not velas:
                # Fallback: construir velas sintéticas desde secuencia V/R
                sec = app.mem.get("secuencia", [])
                if sec:
                    precio = 1.0
                    for item in sec[-n_velas:]:
                        d = item.get("d") or item.get("dir") or item.get("c")
                        subida = d in (1, "V", "SUBE") if d is not None else True
                        precio *= 1.001 if subida else 0.999
                        velas.append({
                            "o": round(precio * 0.9998, 5),
                            "h": round(precio * 1.0002, 5),
                            "l": round(precio * 0.9997, 5),
                            "c": round(precio, 5),
                            "ts": item.get("ts", 0),
                        })

            if velas:
                ultimo = velas[-1].get("c", 0)
                self._lbl_chart_titulo.config(
                    text=f"◈  {activo}  —  {len(velas)} velas")
                self._lbl_chart_precio.config(text=f"{ultimo:.5g}")
                # Indicadores del feed
                if feed:
                    ind = feed.indicadores()
                    rsi = ind.get("rsi_14")
                    tend= ind.get("tendencia", "")
                    txt = []
                    if rsi  is not None: txt.append(f"RSI {rsi:.1f}")
                    if tend:             txt.append(tend.upper())
                    self._lbl_chart_ind.config(text="  |  ".join(txt))
                _dibujar(velas)
                src = "TVFeed" if feed and feed.obtener_velas(1) else "Sintético"
                self._lbl_chart_status.config(
                    text=f"Fuente: {src}   Última actualización: "
                         + __import__("time").strftime("%H:%M:%S"))
            else:
                self._lbl_chart_titulo.config(text="Sin datos — inicia TVFeed")
                self._lbl_chart_status.config(text="Sin velas disponibles")

            if win.winfo_exists():
                win.after(15000, _refrescar)   # refresca cada 15s

        def _redibujar_chart():
            n_velas = self._chart_n_var.get()
            velas   = feed.obtener_velas(n_velas) if feed else []
            if velas:
                _dibujar(velas)

        win.bind("<Configure>", lambda _: _redibujar_chart())
        win.after(300, _refrescar)

    # ─────────────────────────────────────────────────────────────────────
    # PANEL IBKR — Interactive Brokers completo
    # ─────────────────────────────────────────────────────────────────────
    def abrir_panel_ajustes(self):
        """
        Todo lo nuevo, con un botón para cada cosa.

        Se construyó mucho en poco tiempo y todo quedó como comandos de
        voz: «calibra el ticket», «mira el monitor 2», «prepárate para
        entrenar»… Funcionaba, pero había que saberse las frases. Una
        función que hay que adivinar es una función que no está.

        Aquí está todo, agrupado por lo que hace, y cada botón dice qué
        va a pasar antes de pulsarlo.
        """
        import tkinter as tk
        a = self.app

        v = tk.Toplevel(self.root)
        v.title("Ajustes de Litch")
        v.configure(bg=FONDO)
        v.geometry("760x640")

        tk.Label(v, text="⚙  AJUSTES Y HERRAMIENTAS", bg=FONDO, fg=ACENTO,
                 font=("Segoe UI", 12, "bold")).pack(pady=(12, 2))
        tk.Label(v, text="Todo esto también funciona hablando; aquí está "
                         "para no tener que acordarse de las frases.",
                 bg=FONDO, fg=GRIS, font=("Segoe UI", 8)).pack(pady=(0, 8))

        # Zona de resultados: lo que devuelva cada botón se lee aquí
        cont = tk.Frame(v, bg=FONDO)
        cont.pack(fill="both", expand=True, padx=10)

        izq = tk.Frame(cont, bg=FONDO)
        izq.pack(side="left", fill="y", padx=(0, 8))

        der = tk.Frame(cont, bg=PANEL)
        der.pack(side="right", fill="both", expand=True)
        sb = tk.Scrollbar(der)
        sb.pack(side="right", fill="y")
        txt = tk.Text(der, bg=PANEL, fg="#cfe8ff", font=("Consolas", 9),
                      wrap="word", relief="flat", padx=8, pady=8,
                      yscrollcommand=_scroll_seguro(sb))
        txt.pack(fill="both", expand=True)
        sb.config(command=txt.yview)
        txt.insert("1.0", "Pulse cualquier botón de la izquierda.\n\n"
                          "Los de arriba preparan a Litch. Los de abajo le "
                          "preguntan cómo está.")
        txt.config(state="disabled")

        def _mostrar(s):
            txt.config(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", str(s))
            txt.config(state="disabled")

        def _correr(fn, *args):
            def _h():
                try:
                    _mostrar(fn(*args))
                except Exception as e:
                    _mostrar(f"No pude hacerlo:\n\n{e}")
            return _h

        def _mod(nombre):
            from importlib import import_module
            return import_module(f".{nombre}", package="core")

        def _grupo(titulo):
            tk.Label(izq, text=titulo, bg=FONDO, fg="#ff9500",
                     font=("Segoe UI", 8, "bold"), anchor="w").pack(
                fill="x", pady=(10, 3))

        def _boton(txt_b, fn, ayuda, color=ACENTO):
            b = tk.Button(izq, text=txt_b, command=fn, bg=PANEL, fg=color,
                          font=("Segoe UI", 8), relief="flat", anchor="w",
                          cursor="hand2", padx=8, pady=3, width=30)
            b.pack(fill="x", pady=1)
            try:
                _tip(b, txt_b.strip(), ayuda)
            except Exception:
                pass

        # ── ANTES DE OPERAR ────────────────────────────────────────────
        _grupo("ANTES DE OPERAR")
        _boton("✅  Preparación (arreglar aquí)",
               lambda: (v.destroy(), self.abrir_panel_preparacion()),
               "Las once comprobaciones que haría usted si estuviera "
               "mirando. Dice qué falta y cómo arreglarlo.", "#00e676")
        _boton("🎯  Calibrar el ticket de IQ",
               _correr(lambda: _mod("leer_ticket_iq").calibrar(a)),
               "Le pide que señale con el ratón dónde están el monto, el "
               "vencimiento y el pago. Después los lee sola.")
        _boton("💰  ¿Con qué números opero?",
               _correr(lambda: _mod("leer_ticket_iq").descripcion(a)),
               "Monto, vencimiento y pago que está usando, y si los leyó "
               "de su pantalla o los tenía de memoria.")
        _boton("📏  ¿Cuánto debo invertir?",
               _correr(lambda: _mod("mercado_y_tamano").sugerir(a)),
               "El 1 %, 2 % y 5 % de su capital, y cuántas pérdidas "
               "seguidas aguanta con el monto actual.")
        _boton("🧮  ¿Conviene operar?",
               _correr(lambda: _mod("ventaja_real").explicar(
                   a.mem.get("config", {}).get("pago_pct") or 85,
                   a.mem.get("config", {}).get("monto_broker") or 50)),
               "La matemática del pago: cuánto hay que acertar para no "
               "perder. Con 85 % de pago hacen falta 54,05 %.")

        # ── PANTALLA Y GRÁFICO ─────────────────────────────────────────
        _grupo("PANTALLA Y GRÁFICO")
        _boton("🖥  ¿Qué monitores tengo?",
               _correr(lambda: _mod("monitores").descripcion(a)),
               "Los enumera y marca en cuál está mirando.")
        _boton("👁  Ver toda la pantalla",
               _correr(lambda: _mod("vision_total").activar(a)),
               "Amplía la visión al monitor entero.")
        _boton("📐  Ajustar el gráfico",
               _correr(lambda: _mod("escala_temporal").ajustar(a)),
               "Centra el gráfico y ajusta el zoom para ver entre 40 y "
               "60 velas.")
        _boton("⏱  ¿La vela y el vencimiento cuadran?",
               _correr(lambda: _mod("escala_temporal").explicar(a)),
               "La vela debe medir entre un tercio y una vez el "
               "vencimiento. Si no, las señales valen menos.")

        # ── MERCADO ────────────────────────────────────────────────────
        _grupo("MERCADO")
        _boton("🏷  ¿Qué activo es este?",
               _correr(lambda: _mod("mercado_y_tamano").informe(a)),
               "Divisa, cripto, acción o índice — y si es OTC, que "
               "significa que el precio lo genera el bróker.")
        _boton("📋  ¿Qué sabes del cuadro de confirmación?",
               _correr(lambda: _mod("confirmacion_iq").explicar()),
               "Una operación no existe hasta que se confirma.")

        # ── SALUD DE LITCH ─────────────────────────────────────────────
        _grupo("SALUD DE LITCH")
        _boton("🩺  ¿Por qué no predices?",
               _correr(lambda: self._diag_motor()),
               "Los cinco eslabones de la cadena, y cuál está roto.")
        _boton("⚠  ¿Por qué te cerraste?",
               _correr(lambda: (_mod("guardian_cierre").revisar_arranque(a)
                                or "La última vez me cerré bien.")
                       + "\n\n" + _mod("guardian_cierre").historial(10)),
               "Si Litch se cayó dejando dinero expuesto, aquí consta.")
        _boton("🧹  Limpiar estadísticas",
               _correr(lambda: _mod("cuarentena_stats").limpiar_todo(a)),
               "Marca las operaciones que nunca ocurrieron para que no "
               "inflen la tasa de acierto. No borra nada.")
        _boton("🔍  ¿Qué estás viendo?",
               _correr(lambda: _mod("vision_total").estado(a)),
               "Cuánta pantalla alcanza a ver, en porcentaje.")

        tk.Button(v, text="Cerrar", command=v.destroy, bg=PANEL, fg=GRIS,
                  font=("Segoe UI", 8), relief="flat", cursor="hand2",
                  padx=16).pack(pady=8)

    def abrir_panel_preparacion(self):  # noqa: C901
        """
        Preparación INTERACTIVA — se arregla aquí, no se lee y ya.

        ━━━ LO QUE ESTABA MAL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        La ventana anterior decía «✗ Cuenta: no consta si es demo o real»
        y ahí se acababa. El señor tenía que leer, entender qué botón de
        la barra tocar, cerrar la ventana, buscarlo y pulsarlo. Para cada
        una de las once comprobaciones.

        Un diagnóstico que no trae el remedio al lado obliga a hacer de
        intérprete entre la máquina y la máquina. Aquí cada cosa que
        falta tiene su control justo al lado, y la lista se actualiza
        sola al tocarlo.
        """
        import tkinter as tk
        a = self.app

        v = tk.Toplevel(self.root)
        v.title("Preparación de Litch")
        v.configure(bg=FONDO)

        # ── QUE SE VEA, QUE ES LA MITAD DEL TRABAJO ────────────────────
        #
        # El panel se construía bien y el señor no lo veía: nacía DETRÁS
        # de las demás ventanas. La barra de Litch es «siempre encima», y
        # una ventana nueva sin posición explícita aparece donde Windows
        # quiera — a menudo tapada, o en el monitor equivocado cuando hay
        # dos.
        #
        # Desde fuera eso es indistinguible de «el botón no hace nada», y
        # así se pierde media hora buscando el fallo donde no está.
        #
        # Se centra en el monitor donde está la barra y se sube al frente
        # de verdad: topmost un instante para saltar por encima de la
        # barra, y se quita enseguida para no molestar después.
        try:
            from . import monitores as _mon
            _m = _mon.monitor_de_barra(self.app)
            _w, _h = 920, 700
            _x = _m["x"] + max(0, (_m["w"] - _w) // 2)
            _y = _m["y"] + max(0, (_m["h"] - _h) // 2)
            v.geometry(f"{_w}x{_h}+{_x}+{_y}")
        except Exception:
            # Sin el módulo de monitores, al menos se centra con lo que
            # Tk sepa. Una ventana sin posición aparece donde Windows
            # quiera, y eso ya nos costó creer que el botón no servía.
            try:
                _w, _h = 920, 700
                _sw = self.root.winfo_screenwidth()
                _sh = self.root.winfo_screenheight()
                v.geometry(f"{_w}x{_h}+{max(0,(_sw-_w)//2)}+{max(0,(_sh-_h)//2)}")
            except Exception:
                v.geometry("920x700+200+120")

        try:
            v.bind("<Escape>", lambda _e: v.destroy())
        except Exception:
            pass
        try:
            v.attributes("-topmost", True)
            v.lift()
            v.focus_force()
            # Se quita el topmost medio segundo después: solo hacía falta
            # para nacer por encima de la barra, no para quedarse ahí
            # estorbando al señor mientras trabaja.
            v.after(500, lambda: v.attributes("-topmost", False))
        except Exception:
            pass

        tk.Label(v, text="✅  PREPARACIÓN — todo se arregla desde aquí",
                 bg=FONDO, fg="#00e676",
                 font=("Segoe UI", 12, "bold")).pack(pady=(12, 2))
        tk.Label(v, text="Cada cosa que falte tiene su control al lado. "
                         "La lista se actualiza sola.",
                 bg=FONDO, fg=GRIS, font=("Segoe UI", 8)).pack(pady=(0, 8))

        cont = tk.Frame(v, bg=FONDO)
        cont.pack(fill="both", expand=True, padx=12)

        # ── Izquierda: los controles que arreglan ──────────────────────
        izq = tk.Frame(cont, bg=FONDO, width=330)
        izq.pack(side="left", fill="y", padx=(0, 10))
        izq.pack_propagate(False)

        # ── Derecha: la lista, que se refresca ─────────────────────────
        der = tk.Frame(cont, bg=PANEL)
        der.pack(side="right", fill="both", expand=True)
        sb = tk.Scrollbar(der)
        sb.pack(side="right", fill="y")
        txt = tk.Text(der, bg=PANEL, fg="#cfe8ff", font=("Consolas", 9),
                      wrap="word", relief="flat", padx=10, pady=10,
                      yscrollcommand=_scroll_seguro(sb))
        txt.pack(fill="both", expand=True)
        sb.config(command=txt.yview)

        def _refrescar():
            try:
                from importlib import import_module
                pe = import_module(".preparar_entrenamiento", package="core")
                s = pe.informe(a)
            except Exception as e:
                s = f"No pude revisar:\n\n{e}"
            txt.config(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", s)
            txt.config(state="disabled")
            _sinc_botones()

        def _guardar():
            try:
                from importlib import import_module
                import_module(".memoria", package="core").guardar(a.mem)
            except Exception:
                pass

        def _titulo(t):
            tk.Label(izq, text=t, bg=FONDO, fg="#ff9500",
                     font=("Segoe UI", 8, "bold"), anchor="w").pack(
                fill="x", pady=(12, 4))

        # ── 1. CUENTA ──────────────────────────────────────────────────
        _titulo("1 · CUENTA — lo primero de todo")
        f_cta = tk.Frame(izq, bg=FONDO); f_cta.pack(fill="x")
        _b_demo = tk.Button(f_cta, text="DEMO", width=11,
                            font=("Segoe UI", 9, "bold"), relief="flat",
                            cursor="hand2")
        _b_real = tk.Button(f_cta, text="REAL", width=11,
                            font=("Segoe UI", 9, "bold"), relief="flat",
                            cursor="hand2")
        _b_demo.pack(side="left", padx=(0, 4)); _b_real.pack(side="left")

        def _set_cta(tipo):
            def _h():
                if tipo == "real":
                    from tkinter import messagebox
                    if not messagebox.askyesno(
                            "Cuenta REAL",
                            "¿Seguro? En cuenta REAL cada operación mueve "
                            "dinero de verdad.\n\nEntrenar es equivocarse a "
                            "propósito: eso no se hace con dinero real.",
                            parent=v):
                        return
                a.mem.setdefault("config", {})["tipo_cuenta"] = tipo
                _guardar(); _refrescar()
            return _h
        _b_demo.config(command=_set_cta("demo"))
        _b_real.config(command=_set_cta("real"))

        # ── 2. INTERRUPTORES ───────────────────────────────────────────
        _titulo("2 · INTERRUPTORES — la cadena de operación")
        f_sw = tk.Frame(izq, bg=FONDO); f_sw.pack(fill="x")
        _sw_btns = {}

        def _toggle(clave):
            def _h():
                try:
                    if clave == "activo":
                        a.set_activo(not getattr(a, "activo", False))
                    elif clave == "trading_on":
                        a.set_trading(not getattr(a, "trading_on", False))
                    elif clave == "autoclick_on":
                        a.set_autoclick(not getattr(a, "autoclick_on", False))
                except Exception:
                    setattr(a, clave, not getattr(a, clave, False))
                _refrescar()
            return _h

        for _k, _lbl in (("activo", "Sistema"), ("trading_on", "Trading"),
                         ("autoclick_on", "Auto-clic")):
            b = tk.Button(f_sw, text=_lbl, width=9, relief="flat",
                          font=("Segoe UI", 8, "bold"), cursor="hand2",
                          command=_toggle(_k))
            b.pack(side="left", padx=(0, 3))
            _sw_btns[_k] = b

        # ── 3. CIFRAS ──────────────────────────────────────────────────
        _titulo("3 · SUS CIFRAS — escríbalas y pulse Guardar")
        campos = {}
        for _cl, _et, _ay in (
            ("saldo", "Saldo / capital",
             "Lo que tiene en la cuenta. Sin esto no puedo juzgar si el "
             "monto es sensato."),
            ("monto_broker", "Monto por operación",
             "Lo que pone en «Invers» de IQ Option."),
            ("perdida_max_dia", "Límite de pérdida al día",
             "Si pierdo esto, me paro hasta mañana. Es el freno que corre "
             "toda la noche."),
        ):
            fr = tk.Frame(izq, bg=FONDO); fr.pack(fill="x", pady=1)
            tk.Label(fr, text=_et, bg=FONDO, fg=GRIS, width=19,
                     font=("Segoe UI", 8), anchor="w").pack(side="left")
            e = tk.Entry(fr, width=11, bg=PANEL, fg=ACENTO, relief="flat",
                         font=("Consolas", 9), insertbackground=ACENTO)
            e.pack(side="left", ipady=2)
            try:
                _tip(e, _et, _ay)
            except Exception:
                pass
            campos[_cl] = e

        f_div = tk.Frame(izq, bg=FONDO); f_div.pack(fill="x", pady=(4, 0))
        tk.Label(f_div, text="Divisa", bg=FONDO, fg=GRIS, width=19,
                 font=("Segoe UI", 8), anchor="w").pack(side="left")
        _div_var = tk.StringVar(value=a.mem.get("config", {}).get("divisa")
                                or "CO$")
        tk.OptionMenu(f_div, _div_var, "CO$", "US$", "€", "R$", "MX$"
                      ).pack(side="left")

        def _guardar_cifras():
            from importlib import import_module
            mr = import_module(".monto_real", package="core")
            cfg = a.mem.setdefault("config", {})
            cambios = []
            for cl, e in campos.items():
                v_txt = e.get().strip()
                if not v_txt:
                    continue
                d = mr.interpretar(v_txt)
                if d["monto"] is None:
                    continue
                cfg[cl] = d["monto"]
                if cl == "monto_broker":
                    cfg["monto_base"] = cfg["monto"] = d["monto"]
                cambios.append(cl)
            cfg["divisa"] = _div_var.get()
            _guardar()
            _refrescar()
            if cambios:
                self.log(f"[Preparación] Actualizado: {', '.join(cambios)}")

        tk.Button(izq, text="💾  Guardar cifras", command=_guardar_cifras,
                  bg="#1a3a5a", fg="#00e676", font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", pady=4).pack(fill="x",
                                                              pady=(8, 2))

        # ── 4. HERRAMIENTAS ────────────────────────────────────────────
        _titulo("4 · HERRAMIENTAS")

        def _accion(mod, fn):
            def _h():
                try:
                    from importlib import import_module
                    m = import_module(f".{mod}", package="core")
                    self._mostrar_resultado(getattr(m, fn)(a))
                    v.after(1200, _refrescar)
                except Exception as e:
                    self._mostrar_resultado(f"No pude:\n\n{e}")
            return _h

        for _t2, _cmd2, _ay2 in (
            ("🎯  Calibrar el ticket de IQ",
             _accion("leer_ticket_iq", "calibrar"),
             "Le pide señalar con el ratón dónde están el monto, el "
             "vencimiento y el pago."),
            ("📖  Leer el ticket ahora",
             _accion("leer_ticket_iq", "sincronizar"),
             "Lee las cifras de su pantalla sin recalibrar."),
            ("👁  Ver toda la pantalla",
             _accion("vision_total", "activar"),
             "Amplía la visión al monitor entero."),
            ("📐  Ajustar el gráfico",
             _accion("escala_temporal", "ajustar"),
             "Centra y ajusta el zoom."),
            ("🧹  Limpiar estadísticas",
             _accion("cuarentena_stats", "limpiar_todo"),
             "Marca las operaciones que no ocurrieron."),
        ):
            b = tk.Button(izq, text=_t2, command=_cmd2, bg=PANEL, fg=ACENTO,
                          font=("Segoe UI", 8), relief="flat", anchor="w",
                          cursor="hand2", padx=8, pady=3)
            b.pack(fill="x", pady=1)
            try:
                _tip(b, _t2.strip(), _ay2)
            except Exception:
                pass

        # ── Sincronizar el aspecto de los botones con el estado real ───
        def _sinc_botones():
            try:
                cfg = a.mem.get("config", {})
                tipo = str(cfg.get("tipo_cuenta") or "").lower()
                _b_demo.config(bg="#1e5c2e" if tipo == "demo" else PANEL,
                               fg="#00e676" if tipo == "demo" else GRIS)
                _b_real.config(bg="#5c1e1e" if tipo == "real" else PANEL,
                               fg="#ff5252" if tipo == "real" else GRIS)
                for k, b in _sw_btns.items():
                    on = bool(getattr(a, k, False))
                    b.config(bg="#1e5c2e" if on else PANEL,
                             fg="#00e676" if on else GRIS)
                for cl, e in campos.items():
                    if not e.get().strip() and cfg.get(cl):
                        e.insert(0, str(cfg[cl]))
            except Exception:
                pass

        tk.Button(v, text="🔄  Revisar de nuevo", command=_refrescar,
                  bg=PANEL, fg="#00e676", font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=20,
                  pady=4).pack(pady=(6, 2))
        tk.Button(v, text="Cerrar (Esc)", command=v.destroy, bg=FONDO,
                  fg=GRIS, font=("Segoe UI", 8), relief="flat",
                  cursor="hand2").pack(pady=(0, 8))

        _refrescar()
        try:
            v.lift(); v.focus_force()
        except Exception:
            pass

    def _cerebro_autonomo(self):
        """Enciende o apaga el ciclo autónomo completo."""
        try:
            from . import cerebro_autonomo as _ca
            self._mostrar_resultado(_ca.alternar(self.app))
        except Exception as e:
            self._mostrar_resultado(f"No pude arrancarlo:\n\n{e}")

    def _autoconfigurar(self):
        """Detecta IQ Option y lo configura todo. En hilo aparte: la
        búsqueda por color tarda un par de segundos y no debe congelar
        la interfaz."""
        def _t():
            try:
                from . import autoconfigurar as _ac
                r = _ac.ejecutar(self.app)
            except Exception as e:
                r = f"No pude detectar:\n\n{e}"
            try:
                self.root.after(0, lambda: self._mostrar_resultado(r))
            except Exception:
                pass
        import threading
        threading.Thread(target=_t, daemon=True, name="AutoConfig").start()
        self._mostrar_resultado(
            "Buscando IQ Option…\n\n"
            "Localizo la ventana, el monitor, y los botones SUBE y BAJA "
            "por su color.\n\n"
            "Tarda un par de segundos.")

    def _entrenar(self) -> str:
        """Enciende o apaga el entrenamiento automático."""
        try:
            from . import entrenador as _en
            return _en.alternar(self.app)
        except Exception as e:
            return f"No pude arrancar el entrenamiento:\n\n{e}"

    def _cambiar_monitor(self):
        """Pasa Litch al siguiente monitor conectado."""
        try:
            from . import monitores as _mon
            r = _mon.siguiente(self.app)
            if r.get("solo_uno"):
                self.log(r["texto"])
            else:
                self.log(f"[Monitor] Monitor {r['n']} — "
                         f"{r['w']}×{r['h']}.")
                # Si falta calibración en la pantalla nueva hay que
                # DECIRLO en grande: operar ahí sin calibrar significa
                # pulsar donde no es.
                av = r.get("calibracion", "")
                if av and "no tengo calibración" in av:
                    self._mostrar_resultado(av)
                elif av:
                    self.log(f"[Monitor] {av}")
            self._sinc_boton_monitor()
        except Exception as e:
            self.log(f"[Monitor] No pude cambiar: {e}")

    def _sinc_boton_monitor(self):
        """El botón muestra en qué monitor está: «🖥 1/2»."""
        try:
            from . import monitores as _mon
            b = getattr(self, "_btn_monitor", None)
            if b is not None and b.winfo_exists():
                b.config(text=_mon.etiqueta(self.app))
        except Exception:
            pass

    def _mostrar_resultado(self, texto: str):
        """
        Ventana con el resultado de cualquier acción de la barra.

        Los botones de la barra no pueden abrir un panel entero cada vez.
        Esto es una ventana pequeña, con scroll, que se cierra con Escape.
        """
        import tkinter as tk
        v = tk.Toplevel(self.root)
        v.title("Litch")
        v.configure(bg=FONDO)
        # Misma razón que en el panel de preparación: si nace detrás de la
        # barra, el señor cree que el botón no funcionó.
        try:
            from . import monitores as _mon
            _m = _mon.monitor_de_barra(self.app)
            _w, _h = 640, 480
            v.geometry(f"{_w}x{_h}"
                       f"+{_m['x'] + max(0, (_m['w'] - _w) // 2)}"
                       f"+{_m['y'] + max(0, (_m['h'] - _h) // 2)}")
        except Exception:
            try:
                _w, _h = 640, 480
                _sw = self.root.winfo_screenwidth()
                _sh = self.root.winfo_screenheight()
                v.geometry(f"{_w}x{_h}+{max(0,(_sw-_w)//2)}+{max(0,(_sh-_h)//2)}")
            except Exception:
                v.geometry("640x480+300+200")
        try:
            v.bind("<Escape>", lambda _e: v.destroy())
        except Exception:
            pass
        try:
            v.attributes("-topmost", True)
            v.lift(); v.focus_force()
            v.after(500, lambda: v.attributes("-topmost", False))
        except Exception:
            pass

        marco = tk.Frame(v, bg=PANEL)
        marco.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        sb = tk.Scrollbar(marco)
        sb.pack(side="right", fill="y")
        t = tk.Text(marco, bg=PANEL, fg="#cfe8ff", font=("Consolas", 9),
                    wrap="word", relief="flat", padx=10, pady=10,
                    yscrollcommand=_scroll_seguro(sb))
        t.pack(fill="both", expand=True)
        sb.config(command=t.yview)
        t.insert("1.0", str(texto))
        t.config(state="disabled")

        tk.Button(v, text="Cerrar (Esc)", command=v.destroy, bg=PANEL,
                  fg=GRIS, font=("Segoe UI", 8), relief="flat",
                  cursor="hand2", padx=16).pack(pady=(0, 8))
        try:
            v.lift(); v.focus_force()
        except Exception:
            pass

    def _probar_voz(self):
        """Prueba las dos vías de voz y enseña el resultado."""
        def _t():
            try:
                voz = getattr(self.app, "voz", None)
                if voz is None:
                    r = "No tengo módulo de voz cargado."
                elif hasattr(voz, "probar"):
                    r = voz.probar()
                else:
                    r = ("La versión de voz cargada no tiene diagnóstico. "
                         "Reinicie Litch para tomar la nueva.")
            except Exception as e:
                r = f"La prueba falló:\n\n{e}"
            try:
                self.root.after(0, lambda: self._mostrar_resultado(r))
            except Exception:
                pass
        import threading
        threading.Thread(target=_t, daemon=True, name="ProbarVoz").start()
        self._mostrar_resultado(
            "Probando la voz…\n\n"
            "Debería oír dos frases: una en línea y otra sin internet.\n"
            "El informe aparecerá en unos segundos.")

    def _diag_motor(self) -> str:
        """El diagnóstico de los cinco eslabones, para el panel."""
        a = self.app
        from . import trading as _tr
        cfg = a.mem.get("config", {})
        l = ["ESTADO DEL MOTOR DE BINARIAS", ""]
        est = {
            "Sistema":    bool(getattr(a, "activo", False)),
            "Trading":    bool(getattr(a, "trading_on", False)),
            "Auto-clic":  bool(getattr(a, "autoclick_on", False)),
            "Calibración": bool(cfg.get("boton_verde") and cfg.get("boton_rojo")),
        }
        for k, ok in est.items():
            l.append(f" {'✓' if ok else '✗'} {k}")
        try:
            callado = _tr._motor_iq_debe_callar(a)
            l.append(f" {'✗' if callado else '✓'} Motor "
                     f"{'callado' if callado else 'analizando'}")
        except Exception as e:
            l.append(f" · Motor: {e}")
        l.append("")
        falta = [k for k, ok in est.items() if not ok]
        if falta:
            l.append(f"Falta encender: {', '.join(falta)}.")
            l.append("Están en la fila de interruptores de la barra.")
        else:
            l.append("Todos los eslabones en su sitio.")
        return "\n".join(l)

    def abrir_ibkr_panel(self):  # noqa: C901
        """Ventana completa de Interactive Brokers: conectar, balance, posiciones, órdenes."""
        if hasattr(self, "_win_ibkr") and self._win_ibkr.winfo_exists():
            self._win_ibkr.lift()
            self._win_ibkr.focus_force()
            return

        app  = self.app
        ibkr = getattr(app, "broker_ibkr", None)

        win = tk.Toplevel(self.root)
        win.title("Interactive Brokers — Litch")
        self._aplicar_icono(win)
        win.configure(bg=FONDO)
        win.attributes("-topmost", True)
        win.resizable(True, True)
        win.geometry("760x620")
        self._win_ibkr = win

        _BG2  = "#0d1e2e"
        _BG3  = "#07101a"
        _AZUL = "#1a73e8"

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg="#0b1a2e", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🏦  Interactive Brokers",
                 bg="#0b1a2e", fg="#1a73e8",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16)

        self._ibkr_led  = tk.Label(hdr, text="●  Desconectado",
                                    bg="#0b1a2e", fg=ROJO,
                                    font=("Segoe UI", 9, "bold"))
        self._ibkr_led.pack(side="left", padx=8)

        tk.Frame(win, bg=_AZUL, height=1).pack(fill="x")

        # ── Panel de conexión ─────────────────────────────────────────────
        cnx_f = tk.Frame(win, bg=_BG2, pady=8)
        cnx_f.pack(fill="x", padx=12, pady=(8, 4))

        tk.Label(cnx_f, text="CONEXIÓN", bg=_BG2, fg="#4a6b7a",
                 font=("Segoe UI", 7, "bold")).grid(
            row=0, column=0, columnspan=6, sticky="w", padx=8, pady=(0, 6))

        tk.Label(cnx_f, text="Host:", bg=_BG2, fg=TEXTO,
                 font=FUENTE).grid(row=1, column=0, padx=(8, 4), sticky="w")
        _host_var = tk.StringVar(value="127.0.0.1")
        tk.Entry(cnx_f, textvariable=_host_var, width=13,
                 bg="#071422", fg=ACENTO, font=("Consolas", 9),
                 relief="flat", insertbackground=ACENTO).grid(
            row=1, column=1, padx=4)

        tk.Label(cnx_f, text="Modo:", bg=_BG2, fg=TEXTO,
                 font=FUENTE).grid(row=1, column=2, padx=(12, 4), sticky="w")
        _modo_var = tk.StringVar(value="paper")
        for i, (txt, val) in enumerate((("Paper", "paper"), ("Live ⚠", "live"))):
            tk.Radiobutton(cnx_f, text=txt, variable=_modo_var, value=val,
                           bg=_BG2, fg=TEXTO if val == "paper" else ROJO,
                           selectcolor=_BG2, activebackground=_BG2,
                           font=("Segoe UI", 8)).grid(row=1, column=3 + i, padx=4)

        _lbl_cnx_msg = tk.Label(cnx_f, text="", bg=_BG2, fg=VERDE,
                                 font=("Segoe UI", 8))
        _lbl_cnx_msg.grid(row=2, column=0, columnspan=6, sticky="w",
                           padx=8, pady=(4, 0))

        def _conectar():
            if ibkr is None:
                _lbl_cnx_msg.config(
                    text="BrokerIBKR no inicializado — reinicia Litch.", fg=ROJO)
                return
            _btn_con.config(state="disabled", text="Conectando…")
            win.update_idletasks()
            def _hilo():
                ok = ibkr.conectar(modo=_modo_var.get(), host=_host_var.get())
                def _ui():
                    _btn_con.config(state="normal", text="Conectar")
                    if ok:
                        _actualizar_todo()
                        self._ibkr_led.config(
                            text=f"●  Conectado ({_modo_var.get().upper()})",
                            fg=VERDE)
                        _lbl_cnx_msg.config(
                            text="✔ Conexión exitosa — datos en tiempo real.", fg=VERDE)
                    else:
                        _lbl_cnx_msg.config(
                            text="✘ Error — ¿TWS abierto? ¿API habilitada?", fg=ROJO)
                try:
                    win.after(0, _ui)
                except Exception:
                    pass
            threading.Thread(target=_hilo, daemon=True, name="IBKRConect").start()

        def _desconectar():
            if ibkr:
                ibkr.desconectar()
                self._ibkr_led.config(text="●  Desconectado", fg=ROJO)
                _lbl_cnx_msg.config(text="Desconectado.", fg=GRIS)

        _btn_con = tk.Button(cnx_f, text="Conectar",
                             command=_conectar,
                             bg=_AZUL, fg="#fff",
                             font=("Segoe UI", 9, "bold"),
                             relief="flat", padx=12, pady=4, cursor="hand2")
        _btn_con.grid(row=1, column=5, padx=(12, 8))
        tk.Button(cnx_f, text="Desconectar",
                  command=_desconectar,
                  bg=PANEL, fg=ROJO,
                  font=("Segoe UI", 9), relief="flat",
                  padx=8, pady=4, cursor="hand2").grid(
            row=1, column=6, padx=4)

        for col in range(7):
            cnx_f.columnconfigure(col, weight=(1 if col == 0 else 0))

        # ── Balance ───────────────────────────────────────────────────────
        bal_f = tk.Frame(win, bg=_BG3, pady=8)
        bal_f.pack(fill="x", padx=12, pady=4)

        self._ibkr_lbl_eq  = tk.Label(bal_f, text="Equity\n—",
                                       bg=_BG3, fg=ACENTO,
                                       font=("Segoe UI", 10, "bold"),
                                       justify="center")
        self._ibkr_lbl_eq.grid(row=0, column=0, padx=20, pady=4)

        self._ibkr_lbl_cash = tk.Label(bal_f, text="Cash\n—",
                                        bg=_BG3, fg=VERDE,
                                        font=("Segoe UI", 10, "bold"),
                                        justify="center")
        self._ibkr_lbl_cash.grid(row=0, column=1, padx=20, pady=4)

        self._ibkr_lbl_bp  = tk.Label(bal_f, text="Buying Power\n—",
                                       bg=_BG3, fg=GRIS,
                                       font=("Segoe UI", 10, "bold"),
                                       justify="center")
        self._ibkr_lbl_bp.grid(row=0, column=2, padx=20, pady=4)

        self._ibkr_lbl_modo = tk.Label(bal_f, text="Modo\n—",
                                        bg=_BG3, fg="#f39c12",
                                        font=("Segoe UI", 10, "bold"),
                                        justify="center")
        self._ibkr_lbl_modo.grid(row=0, column=3, padx=20, pady=4)

        for c in range(4):
            bal_f.columnconfigure(c, weight=1)

        # ── Notebook (Posiciones / Órdenes / Nueva Orden) ─────────────────
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=FONDO, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=TEXTO,
                        font=("Segoe UI", 9), padding=(12, 4))
        style.map("TNotebook.Tab",
                  background=[("selected", _AZUL)],
                  foreground=[("selected", "#fff")])

        # ── Tab 1: Posiciones ─────────────────────────────────────────────
        tab_pos = tk.Frame(nb, bg=_BG2)
        nb.add(tab_pos, text="📋 Posiciones")

        cols_pos = ("Símbolo", "Cantidad", "Costo", "Precio", "P&L $", "P&L %")
        tree_pos = ttk.Treeview(tab_pos, columns=cols_pos, show="headings",
                                 height=8, selectmode="browse")
        style.configure("Treeview",
                        background=_BG3, foreground=TEXTO,
                        rowheight=22, fieldbackground=_BG3,
                        font=("Consolas", 8))
        style.configure("Treeview.Heading",
                        background=_BG2, foreground=ACENTO,
                        font=("Segoe UI", 8, "bold"))
        style.map("Treeview", background=[("selected", "#1a3a5a")])

        for c in cols_pos:
            tree_pos.heading(c, text=c)
            tree_pos.column(c, width=90, anchor="center")
        tree_pos.tag_configure("up",   foreground=VERDE)
        tree_pos.tag_configure("down", foreground=ROJO)
        tree_pos.tag_configure("flat", foreground=GRIS)

        sb_pos = ttk.Scrollbar(tab_pos, orient="vertical",
                                command=tree_pos.yview)
        tree_pos.configure(yscrollcommand=_scroll_seguro(sb_pos))
        tree_pos.pack(side="left", fill="both", expand=True)
        sb_pos.pack(side="right", fill="y")

        # ── Tab 2: Órdenes abiertas ───────────────────────────────────────
        tab_ord = tk.Frame(nb, bg=_BG2)
        nb.add(tab_ord, text="📌 Órdenes Abiertas")

        cols_ord = ("ID", "Símbolo", "Acción", "Cantidad", "Tipo", "Estado")
        tree_ord = ttk.Treeview(tab_ord, columns=cols_ord, show="headings",
                                 height=8, selectmode="browse")
        for c in cols_ord:
            tree_ord.heading(c, text=c)
            tree_ord.column(c, width=90 if c != "ID" else 50, anchor="center")
        tree_ord.tag_configure("buy",  foreground=VERDE)
        tree_ord.tag_configure("sell", foreground=ROJO)
        sb_ord = ttk.Scrollbar(tab_ord, orient="vertical",
                                command=tree_ord.yview)
        tree_ord.configure(yscrollcommand=_scroll_seguro(sb_ord))
        tree_ord.pack(side="left", fill="both", expand=True)
        sb_ord.pack(side="right", fill="y")

        # Botón cancelar orden seleccionada
        def _cancelar_orden():
            sel = tree_ord.selection()
            if not sel or ibkr is None:
                return
            vals = tree_ord.item(sel[0])["values"]
            oid  = vals[0] if vals else None
            if oid:
                ibkr.cancelar_orden(int(oid))
                _cargar_ordenes()

        tk.Button(tab_ord, text="✘ Cancelar orden seleccionada",
                  command=_cancelar_orden,
                  bg=PANEL, fg=ROJO, font=("Segoe UI", 8),
                  relief="flat", cursor="hand2", pady=4).pack(pady=4)

        # ── Tab 3: Nueva Orden ────────────────────────────────────────────
        tab_nueva = tk.Frame(nb, bg=_BG2)
        nb.add(tab_nueva, text="➕ Nueva Orden")

        _nf = tk.Frame(tab_nueva, bg=_BG2, padx=20, pady=16)
        _nf.pack(fill="x")

        def _lbl(txt, row, col):
            tk.Label(_nf, text=txt, bg=_BG2, fg=GRIS,
                     font=("Segoe UI", 8)).grid(
                row=row, column=col, sticky="w", pady=4, padx=4)

        def _ent(row, col, width=14, **kw):
            v = tk.StringVar()
            e = tk.Entry(_nf, textvariable=v, width=width,
                         bg="#071422", fg=ACENTO, font=("Consolas", 9),
                         relief="flat", insertbackground=ACENTO, **kw)
            e.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
            return v

        _lbl("Símbolo:",    0, 0); _v_sim  = _ent(0, 1, 10)
        _lbl("Cantidad:",   1, 0); _v_cant = _ent(1, 1, 10)
        _lbl("Tipo orden:", 2, 0)
        _v_tipo = tk.StringVar(value="MARKET")
        ttk.Combobox(_nf, textvariable=_v_tipo, width=12,
                     values=["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
                     state="readonly",
                     font=("Segoe UI", 9)).grid(row=2, column=1, padx=4, pady=4)

        _lbl("Precio límite:", 3, 0); _v_prec = _ent(3, 1, 10)
        _lbl("Stop-loss:",     4, 0); _v_stop = _ent(4, 1, 10)

        _lbl_nueva_msg = tk.Label(_nf, text="", bg=_BG2, fg=VERDE,
                                   font=("Segoe UI", 8))
        _lbl_nueva_msg.grid(row=5, column=0, columnspan=3, pady=6, sticky="w")

        def _ejecutar(accion):
            if ibkr is None:
                _lbl_nueva_msg.config(text="No conectado.", fg=ROJO)
                return
            try:
                sim  = _v_sim.get().strip().upper()
                cant = float(_v_cant.get() or 0)
                tipo = _v_tipo.get()
                prec = float(_v_prec.get()) if _v_prec.get().strip() else None
                stop = float(_v_stop.get()) if _v_stop.get().strip() else None
                if not sim or cant <= 0:
                    _lbl_nueva_msg.config(text="Símbolo y cantidad son obligatorios.", fg=ROJO)
                    return
            except ValueError:
                _lbl_nueva_msg.config(text="Valores numéricos inválidos.", fg=ROJO)
                return

            _lbl_nueva_msg.config(text="Enviando orden…", fg=ACENTO)
            win.update_idletasks()
            def _hilo():
                fn = ibkr.comprar if accion == "BUY" else ibkr.vender
                r  = fn(sim, cant, precio=prec, stop=stop, tipo=tipo)
                def _ui():
                    if r:
                        _lbl_nueva_msg.config(
                            text=f"✔ Orden #{r['id']} {accion} {cant}x{sim} → {r['estado']}",
                            fg=VERDE)
                        _actualizar_todo()
                    else:
                        _lbl_nueva_msg.config(text="✘ Error al colocar orden.", fg=ROJO)
                try:
                    win.after(0, _ui)
                except Exception:
                    pass
            threading.Thread(target=_hilo, daemon=True, name="IBKROrden").start()

        btn_row = tk.Frame(_nf, bg=_BG2)
        btn_row.grid(row=6, column=0, columnspan=3, pady=8)
        tk.Button(btn_row, text="🟢 COMPRAR",
                  command=lambda: _ejecutar("BUY"),
                  bg="#1a4a1a", fg=VERDE, font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=20, pady=8,
                  cursor="hand2").pack(side="left", padx=8)
        tk.Button(btn_row, text="🔴 VENDER",
                  command=lambda: _ejecutar("SELL"),
                  bg="#4a1a1a", fg=ROJO, font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=20, pady=8,
                  cursor="hand2").pack(side="left", padx=8)

        # Cerrar posición rápida
        tk.Label(_nf, text="Cerrar posición (símbolo):",
                 bg=_BG2, fg=GRIS, font=("Segoe UI", 8)).grid(
            row=7, column=0, sticky="w", pady=(12, 4), padx=4)
        _v_cerrar = tk.StringVar()
        tk.Entry(_nf, textvariable=_v_cerrar, width=10,
                 bg="#071422", fg=ROJO, font=("Consolas", 9),
                 relief="flat", insertbackground=ROJO).grid(
            row=7, column=1, padx=4, pady=(12, 4))
        def _cerrar_pos():
            s = _v_cerrar.get().strip().upper()
            if s and ibkr:
                ok = ibkr.cerrar_posicion(s)
                _lbl_nueva_msg.config(
                    text=f"✔ Posición {s} cerrada." if ok else f"✘ No hay posición en {s}.",
                    fg=(VERDE if ok else ROJO))
                _actualizar_todo()
        tk.Button(_nf, text="Cerrar",
                  command=_cerrar_pos,
                  bg=PANEL, fg=ROJO, font=("Segoe UI", 8),
                  relief="flat", padx=8, pady=4,
                  cursor="hand2").grid(row=7, column=2, padx=4, pady=(12, 4))

        # ── Tab 4: Historial ──────────────────────────────────────────────
        tab_hist = tk.Frame(nb, bg=_BG2)
        nb.add(tab_hist, text="📜 Historial")

        cols_hist = ("Fecha", "Acción", "Símbolo", "Cant", "Tipo", "Estado", "Modo")
        tree_hist = ttk.Treeview(tab_hist, columns=cols_hist, show="headings",
                                  height=10, selectmode="browse")
        for c in cols_hist:
            tree_hist.heading(c, text=c)
            tree_hist.column(c, width=85, anchor="center")
        tree_hist.tag_configure("buy",  foreground=VERDE)
        tree_hist.tag_configure("sell", foreground=ROJO)
        sb_hist = ttk.Scrollbar(tab_hist, orient="vertical",
                                 command=tree_hist.yview)
        tree_hist.configure(yscrollcommand=_scroll_seguro(sb_hist))
        tree_hist.pack(side="left", fill="both", expand=True)
        sb_hist.pack(side="right", fill="y")

        # ── Funciones de carga ────────────────────────────────────────────
        def _cargar_posiciones():
            for row in tree_pos.get_children():
                tree_pos.delete(row)
            if ibkr is None or not ibkr.esta_conectado:
                return
            for p in ibkr.posiciones():
                pnl  = p.get("pnl") or 0.0
                tag  = "up" if pnl > 0 else ("down" if pnl < 0 else "flat")
                tree_pos.insert("", "end", values=(
                    p.get("simbolo", ""),
                    p.get("cantidad", 0),
                    f"${p.get('costo', 0):.2f}",
                    "—",
                    f"${pnl:.2f}",
                    "—",
                ), tags=(tag,))

        def _cargar_ordenes():
            for row in tree_ord.get_children():
                tree_ord.delete(row)
            if ibkr is None or not ibkr.esta_conectado:
                return
            for o in ibkr.ordenes_abiertas():
                tag = "buy" if o.get("accion") == "BUY" else "sell"
                tree_ord.insert("", "end", values=(
                    o.get("id", ""),
                    o.get("simbolo", ""),
                    o.get("accion", ""),
                    o.get("cantidad", 0),
                    o.get("tipo", ""),
                    o.get("estado", ""),
                ), tags=(tag,))

        def _cargar_historial_ibkr():
            for row in tree_hist.get_children():
                tree_hist.delete(row)
            if ibkr is None:
                return
            for h in reversed(ibkr._historial[-100:]):
                tag = "buy" if h.get("accion") == "BUY" else "sell"
                tree_hist.insert("", "end", values=(
                    h.get("ts", ""),
                    h.get("accion", ""),
                    h.get("simbolo", ""),
                    h.get("cantidad", ""),
                    h.get("tipo", ""),
                    h.get("estado", ""),
                    h.get("modo", ""),
                ), tags=(tag,))

        def _cargar_balance():
            if ibkr is None or not ibkr.esta_conectado:
                return
            bal = ibkr.balance_cuenta()
            if bal:
                self._ibkr_lbl_eq.config(
                    text=f"Equity\n${bal.get('equity', 0):,.2f}")
                self._ibkr_lbl_cash.config(
                    text=f"Cash\n${bal.get('cash', 0):,.2f}")
                self._ibkr_lbl_bp.config(
                    text=f"Buying Power\n${bal.get('buying_power', 0):,.2f}")
                modo = bal.get("modo", "—").upper()
                col  = "#f39c12" if modo == "PAPER" else ROJO
                self._ibkr_lbl_modo.config(text=f"Modo\n{modo}", fg=col)

        def _actualizar_todo():
            _cargar_balance()
            _cargar_posiciones()
            _cargar_ordenes()
            _cargar_historial_ibkr()
            # Actualizar LED
            if ibkr and ibkr.esta_conectado:
                modo = getattr(ibkr, "_modo", "paper").upper()
                self._ibkr_led.config(
                    text=f"●  Conectado ({modo})", fg=VERDE)

        # ── Botón actualizar ──────────────────────────────────────────────
        pie_f = tk.Frame(win, bg=FONDO)
        pie_f.pack(fill="x", padx=12, pady=(0, 8))
        tk.Button(pie_f, text="🔄 Actualizar todo",
                  command=lambda: threading.Thread(
                      target=_actualizar_todo, daemon=True,
                      name="IBKRRefresh").start(),
                  bg=_AZUL, fg="#fff",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=14, pady=6,
                  cursor="hand2").pack(side="left")
        tk.Label(pie_f,
                 text="Paper = práctica sin riesgo. Live = dinero real. "
                      "Requiere TWS o IB Gateway con API habilitada.",
                 bg=FONDO, fg=GRIS, font=("Segoe UI", 7)).pack(
            side="left", padx=12)

        # Estado inicial si ya está conectado
        if ibkr and ibkr.esta_conectado:
            self._ibkr_led.config(
                text=f"●  Conectado ({getattr(ibkr, '_modo', 'paper').upper()})",
                fg=VERDE)
            _actualizar_todo()

    # ------------------------------------------------------------------
    def iniciar(self):
        # Arranca con la VENTANA COMPLETA visible por defecto (menos confuso).
        # Si quieres que arranque como barra delgada arriba, pon en la config
        # «barra_auto»: true. El botón de la barra sigue disponible en la UI.
        try:
            if self.app.mem["config"].get("barra_auto", False):
                self.root.after(1200, self._activar_barra)
        except Exception:
            pass
        self.root.mainloop()
