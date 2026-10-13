"""
panel_simple.py — La ventana fácil de Litch para trabajar con IBKR.

La barra completa tiene decenas de botones porque hace decenas de cosas.
Este panel hace lo contrario: enseña SEIS cosas grandes y claras, escritas
como se le habla a una persona, no como se documenta un programa.

QUÉ RESUELVE
────────────
Cuando uno empieza, una interfaz llena de opciones no da poder: da
parálisis. Aquí arriba siempre se ve lo único que de verdad hay que saber
antes de tocar nada:

    ¿Está TWS abierto?  ¿Es la cuenta simulada?  ¿Está abierto el mercado?

Esas tres respuestas, en verde o en rojo, sin tener que buscarlas.

Debajo, seis botones grandes con lo que se hace de verdad en un día:
mirar, calibrar, aprender, analizar, y pedir la lección del día.

Todo el trabajo pesado ocurre fuera del hilo de la interfaz, para que la
ventana nunca se congele mientras Litch piensa.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import scrolledtext

FONDO = "#0a1420"
PANEL = "#10202f"
ACENTO = "#00d4ff"
TEXTO = "#d6e6f2"
VERDE = "#2ecc71"
AMBAR = "#f39c12"
ROJO = "#e74c3c"
GRIS = "#5a6b7a"

_ventana = None


class PanelSimple:
    """Ventana de control sencilla, pensada para quien está aprendiendo."""

    def __init__(self, app, padre=None):
        self.app = app
        self.v = tk.Toplevel(padre) if padre is not None else tk.Toplevel()
        self.v.title("Litch — Panel sencillo")
        self.v.configure(bg=FONDO)
        self.v.geometry("560x640")
        self.v.minsize(460, 520)
        try:
            self.v.attributes("-topmost", True)
        except Exception:
            pass
        try:
            import os
            ico = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "litch.ico")
            if os.path.exists(ico):
                self.v.iconbitmap(ico)
        except Exception:
            pass

        self._construir()
        self.v.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.refrescar_estado()

    # ── Construcción ────────────────────────────────────────────────────────

    def _construir(self):
        # Cabecera
        cab = tk.Frame(self.v, bg=PANEL)
        cab.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(cab, text="Antes de operar, esto tiene que estar en verde",
                 bg=PANEL, fg=ACENTO,
                 font=("Segoe UI", 11, "bold")).pack(pady=(8, 2))

        self.semaforos = {}
        for clave, etiqueta in (("tws", "Trader Workstation abierto"),
                                ("paper", "Cuenta simulada (sin dinero real)"),
                                ("mercado", "Wall Street abierto"),
                                ("calibrado", "Sé dónde está cada botón")):
            f = tk.Frame(cab, bg=PANEL)
            f.pack(fill="x", padx=14, pady=1)
            punto = tk.Label(f, text="●", bg=PANEL, fg=GRIS,
                             font=("Segoe UI", 13))
            punto.pack(side="left")
            txt = tk.Label(f, text=etiqueta, bg=PANEL, fg=TEXTO,
                           font=("Segoe UI", 10), anchor="w")
            txt.pack(side="left", padx=(6, 0))
            detalle = tk.Label(f, text="", bg=PANEL, fg=GRIS,
                               font=("Segoe UI", 9), anchor="e")
            detalle.pack(side="right")
            self.semaforos[clave] = (punto, detalle)

        tk.Button(cab, text="Volver a comprobar", bg=PANEL, fg=ACENTO,
                  font=("Segoe UI", 9), relief="flat", cursor="hand2",
                  activebackground=FONDO, activeforeground=ACENTO,
                  command=self.refrescar_estado).pack(pady=(4, 8))

        # Botones grandes
        botones = tk.Frame(self.v, bg=FONDO)
        botones.pack(fill="x", padx=10, pady=4)

        acciones = [
            ("✅  ¿Estamos listos para operar?", VERDE,
             "Las nueve comprobaciones de apertura, una por una",
             self._revision),
            ("👁  ¿Qué ves en mi pantalla?", ACENTO,
             "Litch mira todo el monitor y te cuenta qué hay",
             self._ver_pantalla),
            ("📐  Enséñale dónde está cada botón", AMBAR,
             "Un minuto. Sin esto Litch no toca TWS de verdad",
             self._calibrar),
            ("🎓  Enséñame TWS paso a paso", VERDE,
             "Recorre el ticket de órdenes explicándotelo en voz alta",
             self._leccion_tws),
            ("📈  Analiza SPY ahora", ACENTO,
             "Tendencia, RSI, MACD y un veredicto honesto",
             self._analizar),
            ("📖  Mi siguiente lección", VERDE,
             "La escuela de Interactive Brokers, una cosa cada vez",
             self._leccion),
            ("💡  Consejo del día", AMBAR,
             "Un principio que de verdad importa",
             self._consejo),
        ]
        for texto, color, ayuda, cmd in acciones:
            marco = tk.Frame(botones, bg=FONDO)
            marco.pack(fill="x", pady=3)
            b = tk.Button(marco, text=texto, bg=PANEL, fg=color,
                          font=("Segoe UI", 10, "bold"), relief="flat",
                          cursor="hand2", anchor="w", padx=12, pady=7,
                          activebackground="#16293b", activeforeground=color,
                          command=lambda c=cmd: self._lanzar(c))
            b.pack(fill="x")
            tk.Label(marco, text="      " + ayuda, bg=FONDO, fg=GRIS,
                     font=("Segoe UI", 8), anchor="w").pack(fill="x")

        # Respuesta
        tk.Label(self.v, text="Litch dice:", bg=FONDO, fg=ACENTO,
                 font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        self.caja = scrolledtext.ScrolledText(
            self.v, bg=PANEL, fg=TEXTO, wrap="word", relief="flat",
            font=("Segoe UI", 10), padx=10, pady=8, state="disabled", height=9)
        self.caja.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._escribir("Buenos días. Pulse cualquier botón de arriba.\n\n"
                       "Si es su primer día, empiece por «Enséñale dónde "
                       "está cada botón»: es lo que me permite trabajar con "
                       "precisión en su pantalla.")

    # ── Estado ──────────────────────────────────────────────────────────────

    def _pintar(self, clave, color, detalle=""):
        try:
            punto, lbl = self.semaforos[clave]
            if punto.winfo_exists():
                punto.config(fg=color)
                lbl.config(text=detalle, fg=color if color != VERDE else GRIS)
        except Exception:
            pass

    def refrescar_estado(self):
        """Comprueba las cuatro condiciones. Fuera del hilo de la interfaz."""
        def _tarea():
            datos = {}
            try:
                from . import vision_tws as _vt
                est = _vt.leer_estado_tws(self.app)
                datos["tws"] = bool(est.get("tws_abierta"))
                datos["paper"] = est.get("es_paper")
                datos["cuenta"] = est.get("cuenta", "")
            except Exception:
                datos["tws"] = False
                datos["paper"] = None
            try:
                from . import motor_acciones as _ma
                ab, msg = _ma.mercado_abierto()
                datos["mercado"] = ab
                datos["mercado_msg"] = msg
            except Exception:
                datos["mercado"] = None
                datos["mercado_msg"] = ""
            try:
                from . import piloto_tws as _pt
                datos["calibrado"] = _pt.esta_calibrado(self.app)
            except Exception:
                datos["calibrado"] = False
            try:
                self.v.after(0, lambda: self._aplicar_estado(datos))
            except Exception:
                pass

        threading.Thread(target=_tarea, daemon=True,
                         name="LitchPanelEstado").start()

    def _aplicar_estado(self, d):
        self._pintar("tws", VERDE if d.get("tws") else ROJO,
                     "sí" if d.get("tws") else "ábralo")

        p = d.get("paper")
        if p is True:
            self._pintar("paper", VERDE, d.get("cuenta") or "simulada")
        elif p is False:
            self._pintar("paper", ROJO, "⚠ CUENTA REAL")
        else:
            self._pintar("paper", AMBAR, "no confirmado")

        m = d.get("mercado")
        if m is True:
            self._pintar("mercado", VERDE, "abierto")
        elif m is False:
            self._pintar("mercado", AMBAR, "cerrado")
        else:
            self._pintar("mercado", GRIS, "?")

        self._pintar("calibrado", VERDE if d.get("calibrado") else AMBAR,
                     "listo" if d.get("calibrado") else "falta calibrar")

        if d.get("mercado_msg"):
            self._escribir(d["mercado_msg"], anexar=False)

    # ── Acciones ────────────────────────────────────────────────────────────

    def _lanzar(self, fn):
        """Ejecuta una acción sin congelar la ventana."""
        self._escribir("Un momento…", anexar=False)

        def _t():
            try:
                r = fn()
            except Exception as e:
                r = f"Algo falló: {e}"
            try:
                self.v.after(0, lambda: self._escribir(r or "Hecho."))
            except Exception:
                pass

        threading.Thread(target=_t, daemon=True,
                         name="LitchPanelAccion").start()

    def _revision(self):
        from . import rutinas_tws as _rt
        r = _rt.revision_apertura(self.app)
        # Si algo falla, además del detalle enseño lo que me falta en general
        if not r.ok:
            return r.texto() + "\n\n" + _rt.ensayo_general(self.app)
        return r.texto()

    def _ver_pantalla(self):
        from . import conciencia_pantalla as _cp
        return _cp.describir_pantalla(self.app)

    def _calibrar(self):
        from . import piloto_tws as _pt
        return _pt.calibrar_ticket(self.app)

    def _leccion_tws(self):
        from . import piloto_tws as _pt
        return _pt.leccion_guiada(self.app)

    def _analizar(self):
        from . import motor_acciones as _ma
        ab, msg = _ma.mercado_abierto()
        try:
            r = _ma.resumen_analisis(self.app, "SPY")
        except Exception as e:
            r = f"No pude analizar: {e}"
        if not ab:
            r = (msg + "\n\nCon el mercado cerrado los datos están "
                       "congelados: lo que le diga ahora no sirve para "
                       "decidir.\n\n" + r)
        return r

    def _leccion(self):
        from . import escuela_ibkr as _ei
        return _ei.siguiente_leccion(self.app)

    def _consejo(self):
        from . import escuela_ibkr as _ei
        return _ei.consejo_del_dia()

    # ── Texto ───────────────────────────────────────────────────────────────

    def _escribir(self, texto, anexar=False):
        try:
            if not self.caja.winfo_exists():
                return
            self.caja.config(state="normal")
            if not anexar:
                self.caja.delete("1.0", "end")
            self.caja.insert("end", str(texto) + "\n")
            self.caja.see("end")
            self.caja.config(state="disabled")
        except Exception:
            pass

    def cerrar(self):
        global _ventana
        _ventana = None
        try:
            self.v.destroy()
        except Exception:
            pass


# ── Punto de entrada ────────────────────────────────────────────────────────

def abrir(app, padre=None) -> str:
    """Abre el panel sencillo (o lo trae al frente si ya estaba)."""
    global _ventana
    try:
        if _ventana is not None and _ventana.v.winfo_exists():
            _ventana.v.lift()
            _ventana.v.focus_force()
            _ventana.refrescar_estado()
            return "El panel sencillo ya estaba abierto, señor. Se lo traigo."
    except Exception:
        _ventana = None
    try:
        if padre is None:
            padre = getattr(getattr(app, "interfaz", None), "root", None)
        _ventana = PanelSimple(app, padre)
        return ("Panel sencillo abierto, señor. Arriba tiene las cuatro "
                "cosas que deben estar en verde antes de operar.")
    except Exception as e:
        return f"No pude abrir el panel: {e}"
