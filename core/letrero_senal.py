"""
Letrero flotante de señal con razonamiento — Litch

Muestra una ventana flotante siempre visible que explica:
  · Qué dirección predice el sistema (SUBE ▲ / BAJA ▼)
  · Cuántos métodos votaron y cuáles
  · Cuánta confianza tiene la señal
  · Si auto-click está OFF: aviso informativo (NO ejecuta)
  · Si auto-click está ON:  confirmación de que ESTÁ apostando + razón

La ventana se actualiza automáticamente en cada ciclo de señal.
Se puede ocultar/mostrar desde el panel de control.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk


# ── Paleta ────────────────────────────────────────────────────────────────────
_FONDO   = "#05101e"
_SUBE    = "#00e676"
_BAJA    = "#ff5252"
_NEUTRO  = "#00d4ff"
_GRIS    = "#4a6b7a"
_TEXTO   = "#d6e6f2"
_PANEL   = "#0d1e2e"

# Nombre legible de cada método de votación
_NOMBRES_METODO = {
    "markov":      "Cadenas de Markov",
    "estadistica": "Estadística bayesiana",
    "red":         "Red Maestra Neuronal",
    "pronostico":  "Pronóstico avanzado",
    "indicadores": "Indicadores técnicos",
    "rl":          "RL-DQN (aprendizaje)",
    "smc":         "SMC / Liquidity",
    "patrones":    "Patrones de velas",
    "sr":          "Soporte y Resistencia",
    "scalping":    "Scalping EMA200+RSI",
    "triple":      "Triple Barrera",
}


class LetreroSenal:
    """
    Ventana flotante que muestra la señal activa y su razonamiento.

    Uso desde litch.py:
        self.letrero = LetreroSenal(self)
        self.letrero.mostrar(
            direccion="SUBE",
            confianza=0.82,
            votos={"markov": 1, "indicadores": 1, "scalping": 1, ...},
            monto=50, vencimiento=60,
            autonomo=False,
        )
    """

    def __init__(self, app):
        self.app      = app
        self._root    = None
        self._visible = False
        self._lock    = threading.Lock()
        self._ultima  = {}          # última señal mostrada
        self._auto_hide_id = None   # after-id para ocultar automáticamente

    # ── API pública ───────────────────────────────────────────────────────────

    def mostrar(self, direccion: str, confianza: float,
                votos: dict | None = None,
                monto: float = 0,
                vencimiento: int = 0,
                autonomo: bool = False,
                ejecutando: bool = False,
                razon_extra: str = "") -> None:
        """
        Muestra / actualiza el letrero con la señal más reciente.

        direccion  : "SUBE" | "BAJA" | "ESPERA"
        confianza  : 0.0–1.0
        votos      : dict {nombre_metodo: 1/-1/0} — quién votó qué
        monto      : monto de la apuesta (para modo autónomo)
        vencimiento: segundos de vencimiento
        autonomo   : True si auto-click está activo
        ejecutando : True si acabamos de ejecutar el trade
        razon_extra: texto libre adicional (ej. mensaje de Fable5)
        """
        with self._lock:
            self._ultima = dict(
                direccion=direccion, confianza=confianza, votos=votos or {},
                monto=monto, vencimiento=vencimiento, autonomo=autonomo,
                ejecutando=ejecutando, razon_extra=razon_extra,
                ts=time.time())

        # Siempre actualizar en el hilo de UI
        try:
            if self._root and self._root.winfo_exists():
                self._root.after(0, self._actualizar_contenido)
            else:
                self._root = None
                # Crear en hilo UI
                try:
                    self.app.interfaz.root.after(0, self._crear_ventana)
                except Exception:
                    pass
        except Exception:
            pass

    def ocultar(self) -> None:
        """Oculta el letrero sin destruirlo."""
        try:
            if self._root and self._root.winfo_exists():
                self._root.withdraw()
                self._visible = False
        except Exception:
            pass

    def toggle(self) -> None:
        """Alterna visibilidad."""
        try:
            if self._root and self._root.winfo_exists():
                if self._visible:
                    self.ocultar()
                else:
                    self._root.deiconify()
                    self._visible = True
            else:
                with self._lock:
                    d = self._ultima
                if d:
                    self.mostrar(**d)
        except Exception:
            pass

    # ── Construcción de ventana ───────────────────────────────────────────────

    def _calcular_posicion(self, w: int, h: int) -> tuple:
        """Elige una esquina de pantalla que NO tape el gráfico del broker.

        Si Litch tiene calibrada la región del gráfico, escoge la esquina
        más lejana a ella. Respeta una posición guardada por el usuario.
        Por defecto: esquina inferior izquierda (lejos de las velas y de
        los botones SUBE/BAJA de la derecha).
        """
        root_ui = self.app.interfaz.root
        sw = root_ui.winfo_screenwidth()
        sh = root_ui.winfo_screenheight()
        margen = 16
        barra_inf = 60   # deja espacio sobre la barra de tareas

        # 1) Posición guardada por el usuario (arrastró el letrero)
        xy = self.app.mem.get("config", {}).get("letrero_xy")
        if xy and isinstance(xy, (list, tuple)) and len(xy) == 2:
            return int(xy[0]), int(xy[1])

        # 2) Cuatro esquinas candidatas
        esquinas = {
            "inf_izq": (margen, sh - h - barra_inf),
            "sup_izq": (margen, 90),
            "inf_der": (sw - w - margen, sh - h - barra_inf),
            "sup_der": (sw - w - margen, 90),
        }

        # 3) Si conocemos el gráfico, descartar esquinas que lo tapen
        reg = self.app.mem.get("config", {}).get("region_grafico")
        if reg and len(reg) == 4:
            gx1, gy1, gx2, gy2 = reg
            def _tapa(x, y):
                return not (x + w < gx1 or x > gx2 or y + h < gy1 or y > gy2)
            libres = {k: v for k, v in esquinas.items() if not _tapa(*v)}
            if libres:
                # Preferir inferior izquierda entre las libres
                for pref in ("inf_izq", "sup_izq", "inf_der", "sup_der"):
                    if pref in libres:
                        return libres[pref]
        # 4) Por defecto: inferior izquierda
        return esquinas["inf_izq"]

    def _crear_ventana(self) -> None:
        try:
            if self._root and self._root.winfo_exists():
                self._actualizar_contenido()
                return

            root_ui = self.app.interfaz.root
            win = tk.Toplevel(root_ui)
            win.title("Señal Litch")
            win.configure(bg=_FONDO)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.95)
            # Sin barra de título → aparece AL INSTANTE (sin decoración del OS
            # ni animación de ventana). Crítico: si sale tarde, la oportunidad
            # de trade ya pasó.
            win.overrideredirect(True)
            win.resizable(False, False)

            # Tamaño compacto y posición en una ESQUINA que NO tape el gráfico
            # (para no estorbar la visión de Litch ni la tuya).
            _W, _H = 300, 380
            x, y = self._calcular_posicion(_W, _H)
            win.geometry(f"{_W}x{_H}+{x}+{y}")

            self._root   = win
            self._visible = True
            self._frames  = {}

            # ── Arrastrable: puedes moverlo a donde menos estorbe ──────────
            def _drag_start(ev):
                win._dx, win._dy = ev.x, ev.y
            def _drag_move(ev):
                try:
                    nx = win.winfo_x() + ev.x - win._dx
                    ny = win.winfo_y() + ev.y - win._dy
                    win.geometry(f"+{nx}+{ny}")
                    # Recordar la posición elegida por el usuario
                    self.app.mem["config"]["letrero_xy"] = [nx, ny]
                except Exception:
                    pass
            win.bind("<Button-1>", _drag_start)
            win.bind("<B1-Motion>", _drag_move)

            # Construir estructura fija
            self._lbl_dir = tk.Label(
                win, text="", bg=_FONDO,
                font=("Segoe UI", 28, "bold"))
            self._lbl_dir.pack(pady=(16, 2))

            # Tendencia en lenguaje claro (coincide con la dirección)
            self._lbl_tendencia = tk.Label(
                win, text="", bg=_FONDO, fg=_NEUTRO,
                font=("Segoe UI", 9), wraplength=280, justify="center")
            self._lbl_tendencia.pack(pady=(0, 4))

            self._lbl_conf = tk.Label(
                win, text="", bg=_FONDO, fg=_NEUTRO,
                font=("Segoe UI", 10, "bold"))
            self._lbl_conf.pack()

            # Barra de confianza VISUAL (Canvas) — no se desborda como el texto
            self._conf_canvas = tk.Canvas(
                win, width=264, height=10, bg=_PANEL,
                highlightthickness=0, bd=0)
            self._conf_canvas.pack(pady=(4, 2))
            self._conf_barra = self._conf_canvas.create_rectangle(
                0, 0, 0, 10, fill=_NEUTRO, width=0)

            tk.Frame(win, bg="#1a2a3a", height=1).pack(
                fill="x", padx=16, pady=8)

            # Modo: info o autónomo
            self._lbl_modo = tk.Label(
                win, text="", bg=_FONDO, fg=_GRIS,
                font=("Segoe UI", 9, "bold"),
                wraplength=280, justify="center")
            self._lbl_modo.pack(padx=16)

            tk.Frame(win, bg="#1a2a3a", height=1).pack(
                fill="x", padx=16, pady=8)

            # Título métodos
            tk.Label(win, text="MÉTODOS QUE VOTARON",
                     bg=_FONDO, fg=_GRIS,
                     font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=18)

            # Frame de votos (se regenera en actualizar)
            self._frame_votos = tk.Frame(win, bg=_FONDO)
            self._frame_votos.pack(fill="x", padx=14, pady=(4, 0))

            # Razón extra (Fable5 / texto libre)
            self._lbl_razon = tk.Label(
                win, text="", bg=_PANEL, fg=_TEXTO,
                font=("Segoe UI", 8), wraplength=280,
                justify="left", pady=6, padx=10)
            self._lbl_razon.pack(fill="x", padx=14, pady=8)

            # Pie: monto + vencimiento
            pie = tk.Frame(win, bg="#070f1c", pady=6)
            pie.pack(fill="x", side="bottom")
            self._lbl_pie = tk.Label(
                pie, text="", bg="#070f1c", fg=_GRIS,
                font=("Consolas", 8))
            self._lbl_pie.pack()

            # Botón cerrar (✕) — arriba a la derecha del letrero compacto
            tk.Button(win, text="✕", command=self.ocultar,
                      bg=_FONDO, fg=_GRIS, relief="flat",
                      font=("Segoe UI", 10, "bold"),
                      cursor="hand2", bd=0).place(x=274, y=4)

            win.protocol("WM_DELETE_WINDOW", self.ocultar)
            self._actualizar_contenido()

        except Exception as exc:
            print(f"[LetreroSenal] Error al crear ventana: {exc}")

    def _actualizar_contenido(self) -> None:
        try:
            if not self._root or not self._root.winfo_exists():
                return
            # Blindaje: si la ventana aún no terminó de construirse (por un
            # error previo), no intentar actualizar componentes inexistentes.
            if not hasattr(self, "_frame_votos") or self._frame_votos is None:
                return
            with self._lock:
                d = dict(self._ultima)
            if not d:
                return

            dir_  = d.get("direccion", "ESPERA")
            conf  = d.get("confianza", 0.0)
            votos = d.get("votos", {})
            auto  = d.get("autonomo", False)
            ejec  = d.get("ejecutando", False)
            monto = d.get("monto", 0)
            venc  = d.get("vencimiento", 0)
            extra = d.get("razon_extra", "")

            # Dirección principal
            if dir_ == "SUBE":
                emoji, color = "▲  SUBE", _SUBE
            elif dir_ == "BAJA":
                emoji, color = "▼  BAJA", _BAJA
            else:
                emoji, color = "◆  ESPERA", _NEUTRO

            self._lbl_dir.config(text=emoji, fg=color)

            # Tendencia en lenguaje claro — SIEMPRE coincide con la dirección
            # analizada (SUBE→arriba, BAJA→abajo). Coherencia total.
            if dir_ == "SUBE":
                tendencia = ("Es posible una tendencia HACIA ARRIBA: "
                             "el gráfico podría subir.")
            elif dir_ == "BAJA":
                tendencia = ("Es posible una tendencia HACIA ABAJO: "
                             "el gráfico podría bajar.")
            else:
                tendencia = ("Sin dirección clara — el análisis aconseja "
                             "esperar la próxima vela.")
            try:
                self._lbl_tendencia.config(text=tendencia, fg=color)
            except Exception:
                pass

            # Confianza — texto + barra visual (Canvas) que nunca se desborda
            _col_conf = (_SUBE if conf >= 0.70 else
                         _NEUTRO if conf >= 0.55 else _BAJA)
            self._lbl_conf.config(
                text=f"Confianza  {conf*100:.0f}%", fg=_col_conf)
            try:
                _ancho = int(max(0.0, min(1.0, conf)) * 264)
                self._conf_canvas.coords(self._conf_barra, 0, 0, _ancho, 10)
                self._conf_canvas.itemconfig(self._conf_barra, fill=_col_conf)
            except Exception:
                pass

            # Modo
            if ejec:
                txt_modo  = f"⚡ APOSTANDO AHORA  ${monto:.0f}  {venc}s"
                col_modo  = color
            elif auto:
                txt_modo  = "🤖 Modo autónomo activo — próxima señal válida ejecuta"
                col_modo  = _NEUTRO
            else:
                txt_modo  = "👁 Solo observando — auto-click OFF"
                col_modo  = _GRIS
            self._lbl_modo.config(text=txt_modo, fg=col_modo)

            # Votos
            for w in self._frame_votos.winfo_children():
                w.destroy()

            votos_a_favor  = []
            votos_en_contra= []
            for metodo, voto in votos.items():
                nombre = _NOMBRES_METODO.get(metodo, metodo)
                if voto == 1:
                    votos_a_favor.append(nombre)
                elif voto == -1:
                    votos_en_contra.append(nombre)

            if votos_a_favor:
                tk.Label(self._frame_votos,
                         text=f"✔  {' · '.join(votos_a_favor)}",
                         bg=_FONDO, fg=_SUBE,
                         font=("Segoe UI", 7),
                         wraplength=280, justify="left").pack(anchor="w")
            if votos_en_contra:
                tk.Label(self._frame_votos,
                         text=f"✘  {' · '.join(votos_en_contra)}",
                         bg=_FONDO, fg=_BAJA,
                         font=("Segoe UI", 7),
                         wraplength=280, justify="left").pack(anchor="w")
            if not votos_a_favor and not votos_en_contra:
                tk.Label(self._frame_votos,
                         text="Sin votos registrados",
                         bg=_FONDO, fg=_GRIS,
                         font=("Segoe UI", 7)).pack(anchor="w")

            # Razón extra
            if extra:
                self._lbl_razon.config(text=f"💬 {extra[:200]}")
                self._lbl_razon.pack(fill="x", padx=14, pady=(0, 4))
            else:
                self._lbl_razon.pack_forget()

            # Pie
            venc_str = f"{venc//60}m" if venc >= 60 else f"{venc}s"
            self._lbl_pie.config(
                text=f"${monto:.0f}  ·  Cierre {venc_str}  ·  "
                     + time.strftime("%H:%M:%S"))

            # Asegurar visibilidad
            if not self._visible:
                self._root.deiconify()
                self._visible = True
            self._root.lift()

        except Exception as exc:
            print(f"[LetreroSenal] Error actualizar: {exc}")
