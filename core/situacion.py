"""
Consciencia situacional de Litch — sabe DÓNDE está y QUÉ está haciendo.

Combina, sin dependencias externas (solo API nativa de Windows):
  · Ventana activa del sistema (qué aplicación tiene el foco)
  · Contexto visual de pantalla completa (vision.analizar_contexto_iq)
  · Estado interno (modos activos, cuenta, sesión, señal actual)

Comandos: «Litch, ¿dónde estás?» · «¿qué estás haciendo?» · «situación»
"""

from __future__ import annotations

import ctypes
import time


def ventana_activa() -> str:
    """Título de la ventana en primer plano (API nativa de Windows)."""
    try:
        u32 = ctypes.windll.user32
        hwnd = u32.GetForegroundWindow()
        n = u32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value or "(sin título)"
    except Exception:
        return "(no disponible)"


def app_detectada(titulo: str) -> str:
    """Clasifica la aplicación al frente a partir del título de ventana."""
    t = titulo.lower()
    if "iq option" in t or "iqoption" in t:
        return "IQ Option"
    if "trader workstation" in t or "tws" in t or "ib gateway" in t:
        return "TWS (Interactive Brokers)"
    if "tradingview" in t:
        return "TradingView"
    if "litch" in t:
        return "Litch (mi propia ventana)"
    for nav in ("chrome", "edge", "firefox", "opera", "brave"):
        if nav in t:
            return f"Navegador ({nav.capitalize()})"
    return "Otra aplicación"


def resumen_situacion(app, idioma: str = "es") -> str:
    """Informe completo de situación: dónde está, qué ve y qué hace."""
    lineas = []

    # 1) Ventana / aplicación al frente
    tit = ventana_activa()
    lineas.append(f"Ventana al frente: {app_detectada(tit)} — «{tit[:70]}».")

    # 2) Contexto visual de pantalla completa
    try:
        ctx = getattr(app.agente, "_ctx_pantalla", {}) or {}
        if ctx:
            piezas = []
            piezas.append("botones SUBE/BAJA visibles"
                          if ctx.get("botones_ok") else
                          "botones SUBE/BAJA NO visibles")
            pos = ctx.get("posiciones_abiertas", 0)
            if pos:
                piezas.append(f"~{pos} posición(es) abierta(s)")
            pl = ctx.get("pl_color", "desconocido")
            if pl in ("verde", "rojo"):
                piezas.append("P&L en " + ("verde (ganando)" if pl == "verde"
                                           else "rojo (perdiendo)"))
            lineas.append("Veo en pantalla: " + ", ".join(piezas) + ".")
    except Exception:
        pass

    # 3) Estado interno: qué estoy haciendo
    modos = []
    if getattr(app, "activo", False):
        modos.append("Sistema ON")
    if getattr(app, "trading_on", False):
        modos.append("Análisis ON")
    if getattr(app, "autoclick_on", False):
        modos.append("Auto-click ON")
    prc = getattr(app, "modo_practica", None)
    if prc and getattr(prc, "activo", False):
        modos.append("Práctica ON")
    lineas.append("Mis modos: " + (", ".join(modos) if modos
                                   else "todo en espera — usted decide") + ".")

    cuenta = app.mem["config"].get("tipo_cuenta", "demo")
    lineas.append(f"Cuenta registrada: {cuenta.upper()}"
                  + (" — dinero verdadero en juego." if cuenta == "real"
                     else " — práctica sin riesgo."))

    # 4) Qué estoy haciendo ahora mismo
    try:
        ag = app.agente
        sp = getattr(ag, "_senal_prep", None)
        if sp:
            lineas.append(f"Ahora mismo: señal preparada "
                          f"{'SUBE' if sp[0] == 'V' else 'BAJA'} "
                          f"con {sp[1]} votos, esperando el momento de entrada.")
        elif getattr(app, "trading_on", False):
            n_v = len(app.mem.get("secuencia", []))
            lineas.append(f"Ahora mismo: analizando el gráfico "
                          f"({n_v} velas en memoria).")
        else:
            lineas.append("Ahora mismo: en espera, sin analizar.")
    except Exception:
        pass

    # 5) Sesión
    try:
        est = app.mem.get("estadisticas", {})
        w, l = est.get("aciertos", 0), est.get("fallos", 0)
        if w + l:
            lineas.append(f"Histórico: {w} aciertos, {l} fallos "
                          f"({100.0 * w / (w + l):.0f}%).")
    except Exception:
        pass

    return "\n".join(lineas)
