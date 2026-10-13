"""
Ventana de Loterías Inteligentes — Litch v3 (módulo independiente)

Mejoras respecto a la versión anterior:
  · ThreadPoolExecutor(max_workers=1) propio — nunca compite con trading
  · Caché de scraper en disco (MEMORIA_AP/loteria_cache_*.json) — cero peticiones
    redundantes si el sorteo ya fue descargado hoy
  · MLP limitado a 25 épocas con sleep entre épocas para ceder CPU
  · Barra de progreso real durante búsqueda/predicción
  · Panel de estadísticas rápidas (hot, cold, gap) siempre visible
  · Botón Copiar predicción al portapapeles
  · Próximo sorteo con cuenta regresiva
  · Auto-predecir tras buscar (toggle)
  · Exportar historial a texto
  · Diseño más oscuro y profesional con colores por rango de score
"""

from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
import tkinter.scrolledtext as scrolledtext
import tkinter.ttk as ttk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

# ── Colores del tema oscuro ────────────────────────────────────────────────────
_F   = "#060e1a"      # fondo principal
_P   = "#0d1b2a"      # panel
_A   = "#00e5ff"      # acento cyan
_VE  = "#00e676"      # verde éxito
_RO  = "#ff1744"      # rojo error
_GR  = "#546e7a"      # gris texto secundario
_TX  = "#cfd8dc"      # texto principal
_BG2 = "#071018"      # fondo oscuro alternativo
_AM  = "#ffd740"      # amarillo/score alto

# ── Rutas ─────────────────────────────────────────────────────────────────────
_RUTA_PROJ  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA_CACHE = os.path.join(_RUTA_PROJ, "MEMORIA_AP")

# ── Caché de scraper ──────────────────────────────────────────────────────────
_TTL_CACHE_H = 6   # horas de validez del caché de resultados


def _ruta_cache(nombre: str) -> str:
    slug = nombre.lower().replace(" ", "_").replace("/", "")
    return os.path.join(_RUTA_CACHE, f"loteria_cache_{slug}.json")


def _cache_valido(nombre: str) -> bool:
    ruta = _ruta_cache(nombre)
    if not os.path.exists(ruta):
        return False
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        ts = d.get("ts", 0)
        return (time.time() - ts) < _TTL_CACHE_H * 3600
    except Exception:
        return False


def _cargar_cache(nombre: str):
    try:
        with open(_ruta_cache(nombre), encoding="utf-8") as f:
            d = json.load(f)
        return d.get("sorteos", []), d.get("msg", "Cache cargado.")
    except Exception:
        return [], "Error al cargar caché."


def _guardar_cache(nombre: str, sorteos: list, msg: str):
    try:
        os.makedirs(_RUTA_CACHE, exist_ok=True)
        with open(_ruta_cache(nombre), "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "sorteos": sorteos, "msg": msg},
                      f, ensure_ascii=False)
    except Exception:
        pass


def _ts_cache(nombre: str) -> str:
    ruta = _ruta_cache(nombre)
    if not os.path.exists(ruta):
        return "Sin caché"
    try:
        with open(ruta, encoding="utf-8") as f:
            ts = json.load(f).get("ts", 0)
        dt = datetime.fromtimestamp(ts)
        return f"Actualizado {dt.strftime('%d/%m %H:%M')}"
    except Exception:
        return "Sin caché"


# ── Próximo sorteo ────────────────────────────────────────────────────────────
_DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miércoles": 2, "jueves": 3,
    "viernes": 4, "sábado": 5, "domingo": 6
}


def _proximo_sorteo(nombre: str) -> str:
    try:
        from . import scraper_loterias as _sc
        cfg = _sc.LOTERIAS.get(nombre, {})
        dia_str = cfg.get("dia", "")
        if "diario" in dia_str.lower():
            return "Sorteo: diario"
        dias = [_DIAS_SEMANA[d.strip()] for d in dia_str.split(" y ")
                if d.strip() in _DIAS_SEMANA]
        if not dias:
            return f"Sorteo: {dia_str}"
        hoy     = datetime.now().weekday()
        ahora   = datetime.now()
        prox    = None
        for d in sorted(dias):
            diff = (d - hoy) % 7
            if diff == 0:
                diff = 7
            cand = ahora + timedelta(days=diff)
            if prox is None or cand < prox:
                prox = cand
        if prox:
            diff_h = int((prox - ahora).total_seconds() // 3600)
            diff_d = diff_h // 24
            if diff_d == 0:
                return f"Próximo sorteo: hoy ({diff_h}h)"
            return f"Próximo sorteo: {diff_d}d {diff_h % 24}h"
        return ""
    except Exception:
        return ""


# ── Clase principal ────────────────────────────────────────────────────────────
class VentanaLoterias:
    """
    Ventana de loterías completamente independiente.
    Instanciar con VentanaLoterias(root, app) y luego llamar .abrir().
    """

    def __init__(self, root: tk.Tk, app):
        self.root = root
        self.app  = app
        self._v   = None                     # Toplevel activo
        # Pool propio — max_workers=1 serializa trabajo pesado sin competir con trading
        self._pool = ThreadPoolExecutor(max_workers=1,
                                        thread_name_prefix="LitchLoteria")
        self._historial: list = []
        self._pred_actual: list | dict = []
        self._modo_pred   = "clasico"
        self._canceling   = threading.Event()

    # ════════════════════════════════════════════════════════════════════════
    # API pública
    # ════════════════════════════════════════════════════════════════════════

    def abrir(self):
        """Abre (o enfoca) la ventana de loterías."""
        if self._v and self._v.winfo_exists():
            self._v.lift()
            self._v.focus_force()
            return
        self._canceling.clear()   # reset para reapertura tras cierre
        self._construir_ventana()

    # ════════════════════════════════════════════════════════════════════════
    # Construcción de la UI
    # ════════════════════════════════════════════════════════════════════════

    def _construir_ventana(self):  # noqa: C901
        from . import scraper_loterias as _sc
        from . import loteria          as _lot
        from . import loteria_avanzada as _lot_av

        # ── Importar módulos opcionales ────────────────────────────────────
        try:
            from . import red_loteria as _rl
            _RL_OK = True
        except Exception:
            _RL_OK = False
            _rl = None
        try:
            from . import laboratorio as _lab
            _LAB_OK = True
        except Exception:
            _LAB_OK = False
            _lab = None
        try:
            from . import mente_claude as _mc
            _MC_OK = True
        except Exception:
            _MC_OK = False
            _mc = None

        v = tk.Toplevel(self.root)
        v.title("Litch · Loterías Inteligentes")
        v.configure(bg=_F)
        v.geometry("760x860+60+30")
        v.resizable(True, True)
        v.attributes("-topmost", False)   # NO topmost — no bloquea otras ventanas
        self._v = v

        # Liberar pool al cerrar
        def _on_close():
            self._canceling.set()
            v.destroy()
        v.protocol("WM_DELETE_WINDOW", _on_close)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(v, bg=_BG2, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎰  LITCH · LOTERÍAS INTELIGENTES",
                 bg=_BG2, fg=_A, font=("Segoe UI", 13, "bold")).pack()
        tk.Label(hdr,
                 text="Búsqueda en internet  ·  Predicción neuronal  ·  9 métodos estadísticos",
                 bg=_BG2, fg=_GR, font=("Segoe UI", 8)).pack()

        # ── Fila de controles ────────────────────────────────────────────────
        ctrl = tk.Frame(v, bg=_F, pady=6)
        ctrl.pack(fill="x", padx=12)

        tk.Label(ctrl, text="Lotería:", bg=_F, fg=_TX,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        nombres  = _sc.nombres_disponibles()
        lotevar  = tk.StringVar(value=nombres[0])
        combo    = tk.OptionMenu(ctrl, lotevar, *nombres)
        combo.config(bg=_P, fg=_A, activebackground=_A, activeforeground=_F,
                     relief="flat", font=("Segoe UI", 9),
                     highlightthickness=0, bd=0, width=15)
        combo["menu"].config(bg=_P, fg=_TX, activebackground=_A,
                             activeforeground=_F, font=("Segoe UI", 9))
        combo.grid(row=0, column=1, padx=(4, 14), sticky="w")

        tk.Label(ctrl, text="Sorteos:", bg=_F, fg=_TX,
                 font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w")
        nvar = tk.IntVar(value=30)
        tk.Spinbox(ctrl, from_=5, to=200, textvariable=nvar, width=5,
                   bg=_P, fg=_TX, relief="flat", font=("Segoe UI", 9),
                   insertbackground=_TX, bd=1,
                   buttonbackground=_P).grid(row=0, column=3, padx=(4, 14))

        tk.Label(ctrl, text="Pred:", bg=_F, fg=_TX,
                 font=("Segoe UI", 9)).grid(row=0, column=4, sticky="w")
        npred = tk.IntVar(value=9)
        tk.Spinbox(ctrl, from_=1, to=10, textvariable=npred, width=3,
                   bg=_P, fg=_TX, relief="flat", font=("Segoe UI", 9),
                   insertbackground=_TX, bd=1,
                   buttonbackground=_P).grid(row=0, column=5, padx=(4, 14))

        auto_pred = tk.BooleanVar(value=True)
        tk.Checkbutton(ctrl, text="Auto-pred", variable=auto_pred,
                       bg=_F, fg=_GR, selectcolor=_P,
                       activebackground=_F, font=("Segoe UI", 8)
                       ).grid(row=0, column=6, padx=4)

        # ── Botones de acción ────────────────────────────────────────────────
        bots = tk.Frame(v, bg=_F)
        bots.pack(fill="x", padx=12, pady=(0, 2))

        def _mk_btn(parent, text, bg, fg, cmd, side="left", padx=(0, 6)):
            b = tk.Button(parent, text=text, bg=bg, fg=fg, relief="flat",
                          font=("Segoe UI", 9, "bold"), cursor="hand2",
                          padx=12, pady=6, command=cmd)
            b.pack(side=side, padx=padx)
            return b

        btn_buscar = _mk_btn(bots, "🌐  Buscar", _A,  _F,  lambda: _buscar())
        btn_pred   = _mk_btn(bots, "🔮  Predecir", _P, _A, lambda: _predecir())
        btn_audit  = _mk_btn(bots, "🔬  Auditar",  _P, _TX, lambda: _auditar())
        btn_copy   = _mk_btn(bots, "📋  Copiar",   _P, _GR, lambda: _copiar())
        btn_manual = _mk_btn(bots, "✏  Manual  ▾", _P, _GR, lambda: _toggle_manual())
        btn_info   = _mk_btn(bots, "ℹ  Cómo funciona", _P, _AM,
                             lambda: _como_funciona())

        def _como_funciona():
            """Popup educativo: qué es este juego, cómo se juega y sus odds."""
            nombre = lotevar.get()
            try:
                texto = _lot.explicar_juego(nombre)
            except Exception:
                texto = "Información no disponible."
            w = tk.Toplevel(v)
            w.title(f"ℹ {nombre} — Cómo funciona")
            w.configure(bg=_F)
            w.geometry("560x520")
            w.attributes("-topmost", True)
            cja = scrolledtext.ScrolledText(
                w, bg="#040a12", fg=_TX, font=("Consolas", 9),
                relief="flat", wrap="word", padx=10, pady=10)
            cja.pack(fill="both", expand=True, padx=8, pady=8)
            cja.insert("1.0", texto)
            cja.config(state="disabled")
            tk.Button(w, text="Entendido", bg=_A, fg=_F, relief="flat",
                      font=("Segoe UI", 9, "bold"), cursor="hand2",
                      command=w.destroy).pack(pady=(0, 8))

        # ── Info strip (próximo sorteo + caché) ────────────────────────────
        info_frame = tk.Frame(v, bg=_BG2)
        info_frame.pack(fill="x")

        lbl_prox  = tk.Label(info_frame, text="", bg=_BG2, fg=_GR,
                             font=("Segoe UI", 7), anchor="w", padx=8)
        lbl_prox.pack(side="left")
        lbl_cache = tk.Label(info_frame, text="", bg=_BG2, fg=_GR,
                             font=("Segoe UI", 7), anchor="e", padx=8)
        lbl_cache.pack(side="right")
        lbl_memoria = tk.Label(info_frame, text="🧠  Memoria: cargando…",
                               bg=_BG2, fg=_GR, font=("Segoe UI", 7))
        lbl_memoria.pack()

        # ── Estado / barra de progreso ───────────────────────────────────────
        lbl_estado = tk.Label(v, text="Selecciona una lotería y pulsa «Buscar»",
                              bg=_F, fg=_GR, font=("Segoe UI", 8), anchor="w")
        lbl_estado.pack(fill="x", padx=12, pady=(4, 0))

        prog = ttk.Progressbar(v, mode="indeterminate", length=740)
        prog.pack(fill="x", padx=12, pady=(2, 0))

        # ── Barra de estadísticas rápidas (hot/cold) ─────────────────────────
        stats_frame = tk.Frame(v, bg=_P, pady=4)
        stats_frame.pack(fill="x", padx=12, pady=(4, 0))
        lbl_hot  = tk.Label(stats_frame, text="🔥 —", bg=_P, fg=_AM,
                            font=("Consolas", 8), padx=6)
        lbl_hot.pack(side="left")
        lbl_cold = tk.Label(stats_frame, text="❄ —", bg=_P, fg="#29b6f6",
                            font=("Consolas", 8), padx=6)
        lbl_cold.pack(side="left")
        lbl_gap  = tk.Label(stats_frame, text="⏱ —", bg=_P, fg=_A,
                            font=("Consolas", 8), padx=6)
        lbl_gap.pack(side="left")

        # ── Canvas bolas ─────────────────────────────────────────────────────
        BALL_R  = 29
        BALL_SP = 76
        COLS    = 5
        CW      = 740

        canvas_balls = tk.Canvas(v, bg=_F, highlightthickness=0,
                                 width=CW, height=10)
        canvas_balls.pack(pady=(4, 0))

        # ── Panel de resultados ───────────────────────────────────────────────
        txt_res = scrolledtext.ScrolledText(
            v, height=11, bg="#040a12", fg=_A,
            font=("Consolas", 8), relief="flat", state="disabled",
            insertbackground=_TX)
        txt_res.pack(fill="both", expand=True, padx=12, pady=(4, 2))

        # ── Entrada manual (colapsable) ───────────────────────────────────────
        frame_manual  = tk.Frame(v, bg=_F)
        txt_manual    = scrolledtext.ScrolledText(
            frame_manual, height=4, bg=_P, fg=_TX,
            font=("Consolas", 8), relief="flat", insertbackground=_TX)
        txt_manual.pack(fill="x")
        tk.Label(frame_manual, text="Un sorteo por línea · números separados por espacios o comas",
                 bg=_F, fg=_GR, font=("Segoe UI", 7)).pack(anchor="w")
        _vis = [False]

        def _toggle_manual():
            if _vis[0]:
                frame_manual.pack_forget()
                btn_manual.config(text="✏  Manual  ▾")
            else:
                frame_manual.pack(fill="x", padx=12, pady=(0, 4))
                btn_manual.config(text="✏  Manual  ▲")
            _vis[0] = not _vis[0]

        # ── Helpers de UI ────────────────────────────────────────────────────
        def _set_estado(msg, col=_GR):
            try:
                lbl_estado.config(text=msg[:120], fg=col)
            except Exception:
                pass

        def _set_resultado(texto):
            try:
                txt_res.config(state="normal")
                txt_res.delete("1.0", "end")
                txt_res.insert("1.0", texto)
                txt_res.config(state="disabled")
            except Exception:
                pass

        def _prog_start():
            try:
                prog.start(12)
            except Exception:
                pass

        def _prog_stop():
            try:
                prog.stop()
                prog["value"] = 0
            except Exception:
                pass

        def _update_info(nombre):
            try:
                lbl_prox.config(text=_proximo_sorteo(nombre))
                lbl_cache.config(text=_ts_cache(nombre))
            except Exception:
                pass

        def _update_memoria(nombre):
            if not _RL_OK or _rl is None:
                return
            try:
                e   = _rl.estado_memoria(nombre)
                if e["sorteos"] == 0:
                    txt = f"🧠 Sin memoria para {nombre}"
                    col = _GR
                elif e["entrenada"]:
                    txt = (f"🧠 {nombre}: {e['sorteos']} sorteos · "
                           f"Red neuronal activa y lista")
                    col = _VE
                else:
                    txt = (f"🧠 {nombre}: {e['sorteos']} sorteos · "
                           f"Red pendiente (+{max(0, 8 - e['sorteos'])} para entrenar)")
                    col = _A
                lbl_memoria.config(text=txt[:100], fg=col)
            except Exception:
                pass

        def _update_stats(historial):
            """Rellena la barra de hot/cold/gap con el historial actual."""
            try:
                from collections import Counter
                todos = [n for s in historial for n in s]
                if not todos:
                    return
                frec = Counter(todos)
                hot  = frec.most_common(5)
                cold = sorted(frec.items(), key=lambda x: x[1])[:5]
                # Gap: número sin aparecer hace más sorteos
                ultima_ap = {}
                for i, s in enumerate(historial):
                    for n in s:
                        ultima_ap[n] = i
                n_sort = len(historial)
                gap = sorted(ultima_ap.items(),
                             key=lambda kv: n_sort - 1 - kv[1],
                             reverse=True)[:4]
                hot_txt  = "🔥 " + "  ".join(f"{n}" for n, _ in hot)
                cold_txt = "❄ " + "  ".join(f"{n}" for n, _ in cold)
                gap_txt  = "⏱ " + "  ".join(f"{n}" for n, _ in gap)
                lbl_hot.config(text=hot_txt)
                lbl_cold.config(text=cold_txt)
                lbl_gap.config(text=gap_txt)
            except Exception:
                pass

        # ── Dibujo de bolas ──────────────────────────────────────────────────
        def _dibujar_bola(cx, cy, num, score, bg_c, txt_c, etiqueta=None):
            for off, op in ((5, "#0a1520"), (3, "#0e1f30")):
                canvas_balls.create_oval(
                    cx - BALL_R + off, cy - BALL_R + off,
                    cx + BALL_R + off, cy + BALL_R + off,
                    fill=op, outline="")
            canvas_balls.create_oval(
                cx - BALL_R, cy - BALL_R,
                cx + BALL_R, cy + BALL_R,
                fill=bg_c, outline="#ffffff", width=1)
            canvas_balls.create_oval(
                cx - BALL_R * 0.50, cy - BALL_R * 0.78,
                cx + BALL_R * 0.08, cy - BALL_R * 0.18,
                fill="#ffffff", outline="")
            canvas_balls.create_text(cx, cy - 1, text=str(num),
                                     fill=txt_c, font=("Segoe UI", 13, "bold"))
            canvas_balls.create_text(cx, cy + BALL_R + 13, text=f"{score}%",
                                     fill=bg_c, font=("Segoe UI", 8, "bold"))
            if etiqueta:
                canvas_balls.create_text(cx, cy - BALL_R - 11, text=etiqueta,
                                         fill="#ffffffaa",
                                         font=("Segoe UI", 6, "bold"))

        def _color_rango(rank, total):
            t = rank / max(total - 1, 1)
            if t < 0.25:
                return "#00e676", "#003010"
            if t < 0.50:
                return _AM, "#1a1000"
            if t < 0.75:
                return "#00b4d8", "#001a22"
            return "#f4a261", "#2a1200"

        def _dibujar_bolas(predicciones, modo="clasico"):
            try:
                canvas_balls.delete("all")
                if not predicciones:
                    canvas_balls.config(height=10)
                    return
                n     = len(predicciones)
                filas = (n + COLS - 1) // COLS
                canvas_balls.config(height=filas * 92 + 36)
                modo_txt = "🧠+📊 Neuronal" if modo == "combinado" else "📊 Estadístico"
                canvas_balls.create_text(
                    CW - 10, 12, text=modo_txt, fill=_VE if modo == "combinado" else _A,
                    anchor="e", font=("Segoe UI", 7, "bold"))
                mx = (CW - min(n, COLS) * BALL_SP) // 2 + BALL_SP // 2
                for i, (num, score) in enumerate(predicciones):
                    col = i % COLS
                    row = i // COLS
                    cx  = mx + col * BALL_SP
                    cy  = 56 + row * 92
                    bg_c, txt_c = _color_rango(i, n)
                    _dibujar_bola(cx, cy, num, score, bg_c, txt_c,
                                  etiqueta=f"#{i + 1}")
            except Exception:
                pass

        def _dibujar_bolas_baloto(pred_dict):
            try:
                canvas_balls.delete("all")
                princ  = pred_dict.get("principales", [])[:5]
                comb   = pred_dict.get("combinacion_sugerida", [])
                super_l = pred_dict.get("super", [])[:1]
                sup_num = pred_dict.get("super_sugerido", "?")
                canvas_balls.config(height=240)
                canvas_balls.create_text(
                    CW - 10, 12, text="🎱 Baloto · 9 Métodos + Red Neuronal",
                    fill=_VE, anchor="e", font=("Segoe UI", 7, "bold"))
                canvas_balls.create_text(CW // 2, 34,
                    text="NÚMEROS PRINCIPALES (1–43)",
                    fill="#00b4d8", font=("Segoe UI", 8, "bold"))
                n_p = len(comb)
                sp5 = min(BALL_SP, (CW - 40) // max(n_p, 1))
                mx5 = (CW - n_p * sp5) // 2 + sp5 // 2
                for i, num in enumerate(comb):
                    score = princ[i][1] if i < len(princ) else 0
                    cx = mx5 + i * sp5
                    bg_c, txt_c = _color_rango(i, n_p)
                    _dibujar_bola(cx, 82, num, score, bg_c, txt_c)
                canvas_balls.create_line(60, 132, CW - 60, 132,
                    fill="#1a2a3a", width=1, dash=(4, 4))
                canvas_balls.create_text(CW // 2, 150,
                    text="SUPERBALOTA (1–16)",
                    fill=_RO, font=("Segoe UI", 8, "bold"))
                sup_score = super_l[0][1] if super_l else 0
                _dibujar_bola(CW // 2, 198, sup_num, sup_score,
                              "#e53935", "#fff9f9")
                alt_sb = pred_dict.get("super", [])[1:4]
                if alt_sb:
                    canvas_balls.create_text(
                        CW // 2, 228,
                        text="Alt: " + "  ".join(f"{n}({s}%)" for n, s in alt_sb),
                        fill="#ff8888", font=("Segoe UI", 7))
            except Exception:
                pass

        # ── Copiar al portapapeles ─────────────────────────────────────────
        def _copiar():
            try:
                if isinstance(self._pred_actual, list) and self._pred_actual:
                    nums = " - ".join(str(n) for n, _ in self._pred_actual)
                elif isinstance(self._pred_actual, dict):
                    comb = self._pred_actual.get("combinacion_sugerida", [])
                    sup  = self._pred_actual.get("super_sugerido", "")
                    nums = " - ".join(map(str, comb))
                    if sup:
                        nums += f"  +SB:{sup}"
                else:
                    nums = txt_res.get("1.0", "end")
                v.clipboard_clear()
                v.clipboard_append(nums)
                _set_estado("✓ Predicción copiada al portapapeles.", _VE)
            except Exception:
                pass

        # ── Acción: Auditar ──────────────────────────────────────────────────
        def _auditar():
            hist = self._historial
            if not hist:
                _set_resultado("Sin datos. Busca o ingresa sorteos primero.")
                return
            if not _LAB_OK or _lab is None:
                _set_resultado("Módulo de auditoría no disponible.")
                return

            def _work():
                try:
                    informe = _lab.informe(hist, getattr(self.app, "idioma", "es"))
                    v.after(0, lambda: _set_resultado(informe))
                except Exception as ex:
                    v.after(0, lambda: _set_resultado(f"Error en auditoría: {ex}"))

            self._pool.submit(_work)
            _set_estado("Auditando distribuciones estadísticas…", _A)

        # ── Acción: Predecir ─────────────────────────────────────────────────
        def _predecir():  # noqa: C901
            hist = self._historial
            if not hist:
                _set_resultado("Sin datos. Busca o ingresa sorteos primero.")
                return
            nombre   = lotevar.get()
            n        = max(1, min(10, npred.get()))
            es_baloto = _sc.tiene_super(nombre)
            btn_pred.config(state="disabled", text="⏳  Calculando…")
            _prog_start()

            def _work():
                try:
                    if self._canceling.is_set():
                        return

                    if es_baloto:
                        pred_dict, reporte_base = _lot.analizar_baloto(hist)
                        fable_txt = ""
                        if _MC_OK and _mc:
                            try:
                                comb    = pred_dict.get("combinacion_sugerida", [])
                                sup_num = pred_dict.get("super_sugerido", "?")
                                top_p   = pred_dict.get("principales", [])[:6]
                                pregunta = (
                                    f"Análisis predictivo Baloto ({nombre}) — "
                                    f"{len(hist)} sorteos.\n"
                                    f"Sugerida: {' - '.join(map(str, comb))} + SB:{sup_num}\n"
                                    f"Top: {', '.join(f'{x}({s}%)' for x, s in top_p)}\n"
                                    "Analiza brevemente (3-4 líneas, técnico y directo)."
                                )
                                fable_txt = _mc.responder_analisis(pregunta) or ""
                            except Exception:
                                fable_txt = ""

                        reporte = reporte_base
                        if fable_txt:
                            reporte += "\n\n" + "─" * 50 + "\n🤖 ANÁLISIS FABLE 5:\n" + "─" * 50 + "\n" + fable_txt

                        self._pred_actual = pred_dict
                        self._modo_pred   = "baloto"

                        def _ui():
                            _prog_stop()
                            btn_pred.config(state="normal", text="🔮  Predecir")
                            _dibujar_bolas_baloto(pred_dict)
                            _set_resultado(reporte)
                            _set_estado(f"✓ Predicción Baloto lista — {len(hist)} sorteos analizados.", _VE)
                            from . import memoria as _mm
                            self.app.mem["loteria"]["historial"] = hist
                            _mm.guardar(self.app.mem)
                            comb = pred_dict.get("combinacion_sugerida", [])
                            sup  = pred_dict.get("super_sugerido", "?")
                            if comb:
                                self.app.decir(
                                    f"Predicción Baloto: {', '.join(map(str, comb))}. "
                                    f"SuperBalota: {sup}. Consulte la interfaz, señor.")

                        if not self._canceling.is_set():
                            try:
                                v.after(0, _ui)
                            except Exception:
                                pass

                    else:
                        usa_red = False
                        pred    = None
                        if _RL_OK and _rl:
                            e = _rl.estado_memoria(nombre)
                            usa_red = e["entrenada"] and e["sorteos"] >= 15
                            if usa_red:
                                try:
                                    pred = _rl.predecir_combinado(nombre, hist, n)
                                except Exception:
                                    pred = None
                                    usa_red = False

                        _, reporte = _lot.analizar_completo(hist, n, predicciones=pred)
                        if pred is None:
                            pred, _ = _lot.analizar_completo(hist, n)

                        self._pred_actual = pred or []
                        self._modo_pred   = "combinado" if usa_red else "clasico"

                        def _ui():
                            _prog_stop()
                            btn_pred.config(state="normal", text="🔮  Predecir")
                            _dibujar_bolas(pred or [], modo=self._modo_pred)
                            _set_resultado(reporte)
                            _set_estado(f"✓ Predicción lista — {'neuronal+estadístico' if usa_red else 'estadístico'}.", _VE)
                            from . import memoria as _mm
                            self.app.mem["loteria"]["historial"] = hist
                            _mm.guardar(self.app.mem)
                            if pred:
                                nums = ", ".join(str(x) for x, _ in pred[:5])
                                suf  = " (neuronal)" if usa_red else ""
                                self.app.decir(
                                    f"Predicción{suf} lista. Números más probables: {nums}. "
                                    f"Consulte la interfaz, señor.")

                        if not self._canceling.is_set():
                            try:
                                v.after(0, _ui)
                            except Exception:
                                pass

                except Exception as ex:
                    def _err():
                        _prog_stop()
                        btn_pred.config(state="normal", text="🔮  Predecir")
                        _set_resultado(f"Error en predicción: {ex}")
                        _set_estado(f"Error: {ex}", _RO)
                    try:
                        v.after(0, _err)
                    except Exception:
                        pass

            self._pool.submit(_work)

        # ── Acción: Buscar en Internet ────────────────────────────────────────
        def _buscar():  # noqa: C901
            nombre  = lotevar.get()
            n_sor   = max(5, min(200, nvar.get()))
            btn_buscar.config(state="disabled", text="⏳  Buscando…")
            _prog_start()
            _set_estado(f"Conectando con {nombre}…", _A)
            canvas_balls.delete("all")
            canvas_balls.config(height=10)

            def _work():
                # 1) Intentar caché primero
                if _cache_valido(nombre):
                    sorteos, msg_scr = _cargar_cache(nombre)
                    fuente = "caché"
                else:
                    sorteos, msg_scr = _sc.obtener_resultados(nombre, n_sor)
                    fuente = "internet"
                    if sorteos:
                        _guardar_cache(nombre, sorteos, msg_scr)

                msg_mem = ""
                n_nuevos = 0
                if sorteos and _RL_OK and _rl:
                    def _notif():
                        lbl_memoria.config(
                            text=f"🧠 Aprendiendo patrones de {nombre}…", fg=_A)
                        _set_estado(f"Memorizando {len(sorteos)} sorteos…", _A)
                    try:
                        v.after(0, _notif)
                    except Exception:
                        pass
                    try:
                        _, n_nuevos, msg_mem = _rl.aprender(nombre, sorteos)
                    except Exception as ex:
                        msg_mem = f"Error de memoria: {ex}"

                def _ui():
                    try:
                        _prog_stop()
                        btn_buscar.config(state="normal", text="🌐  Buscar")
                        if sorteos:
                            self._historial = sorteos
                            # Actualizar entrada manual
                            txt_manual.delete("1.0", "end")
                            txt_manual.insert("1.0", "\n".join(
                                " ".join(map(str, s)) for s in sorteos))
                            e = _rl.estado_memoria(nombre) if (_RL_OK and _rl) else {}
                            total_mem = e.get("sorteos", 0)
                            _set_resultado(
                                f"✓ {len(sorteos)} sorteos de {nombre} ({fuente}).\n\n"
                                f"🧠 Memoria: {total_mem} sorteos acumulados (+{n_nuevos} nuevos).\n"
                                f"{'✓ Red neuronal entrenada.' if e.get('entrenada') else '⚠ Se necesitan más sorteos.'}\n\n"
                                f"Pulsa «🔮 Predecir» o activa Auto-pred.")
                            _set_estado(f"✓ {msg_scr[:80]}", _VE)
                            _update_info(nombre)
                            _update_memoria(nombre)
                            _update_stats(sorteos)
                            # ── Análisis extra: signos (Astro) y cifras ──
                            try:
                                extra = []
                                _signos = getattr(_sc, "ULTIMOS_SIGNOS",
                                                  {}).get(nombre)
                                if _signos:
                                    extra.append(_lot.analizar_signos(_signos))
                                if _sc.formato_tipo(nombre) == "4digit":
                                    extra.append(
                                        _lot.analizar_cifras_posicion(sorteos))
                                if extra:
                                    txt_res.config(state="normal")
                                    txt_res.insert(
                                        "end", "\n\n" + "\n\n".join(extra))
                                    txt_res.config(state="disabled")
                            except Exception:
                                pass
                            from . import memoria as _mm
                            self.app.mem["loteria"]["historial"] = sorteos
                            _mm.guardar(self.app.mem)
                            self.app.decir(
                                f"Listo. {len(sorteos)} sorteos de {nombre} desde {fuente}. "
                                f"Memoria: {total_mem} sorteos. Pulse predecir, señor.")
                            if auto_pred.get():
                                v.after(200, _predecir)
                        else:
                            _set_estado(msg_scr[:110], _RO)
                            _set_resultado(
                                f"⚠ No se pudieron obtener resultados de {nombre}.\n\n"
                                f"Motivo: {msg_scr}\n\n"
                                f"Opciones:\n"
                                f"  · Ingresa los números manualmente con «✏ Manual»\n"
                                f"  · Verifica tu conexión a internet\n"
                                f"  · Intenta con un número menor de sorteos")
                    except Exception:
                        pass

                if not self._canceling.is_set():
                    try:
                        v.after(0, _ui)
                    except Exception:
                        pass

            self._pool.submit(_work)

        # ── Sincronizar entrada manual ────────────────────────────────────────
        def _sync_manual(*_):
            from . import loteria as _lt
            hist = _lt.parsear(txt_manual.get("1.0", "end"))
            if hist:
                self._historial = hist
                _update_stats(hist)

        txt_manual.bind("<KeyRelease>", _sync_manual)

        # ── Al cambiar de lotería actualizar info ────────────────────────────
        def _on_lote_change(*_):
            nombre = lotevar.get()
            _update_info(nombre)
            _update_memoria(nombre)

        lotevar.trace_add("write", _on_lote_change)

        # ── Cargar historial previo ──────────────────────────────────────────
        previos = self.app.mem.get("loteria", {}).get("historial") or []
        if previos:
            self._historial = previos
            txt_manual.delete("1.0", "end")
            txt_manual.insert("1.0", "\n".join(
                " ".join(map(str, s)) for s in previos))
            _set_estado(f"Historial previo cargado · {len(previos)} sorteos.", _VE)
            _update_stats(previos)

        # Inicializar info strip
        _on_lote_change()
