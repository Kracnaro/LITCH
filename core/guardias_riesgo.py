"""
guardias_riesgo.py — Guardias de riesgo integradas en la INTELIGENCIA de Litch.

Del Manual 13 (skills riesgo-mercado + cerebro-trading) destilé las reglas que
Litch debe consultar ANTES de cada decisión, no como texto que se lee, sino como
código que se ejecuta. Cada guardia devuelve un veredicto claro.

Filosofía (catálogo de errores de IA, sección C4): un umbral de seguridad NO se
negocia por insistencia ni euforia. Si se rechazó por muestra insuficiente,
sigue rechazado el mensaje siguiente.
"""

from __future__ import annotations

import time


# ── Cortacircuitos por niveles (verde/amarillo/naranja/rojo) ────────────────

def cortacircuito(app) -> dict:
    """Evalúa el nivel de riesgo actual de la sesión.

    Devuelve {"nivel": str, "factor": float, "razon": str, "operar": bool}.
      · factor = multiplicador de tamaño recomendado (1.0 verde … 0.0 rojo).
      · operar = False solo en ROJO (parar del todo).
    """
    est = app.mem.get("estadisticas", {})
    fdb = getattr(getattr(app, "agente", None), "fdb", None)

    # Racha de pérdidas actual
    racha_loss = 0
    try:
        r = fdb.racha_actual() if fdb else {}
        if r.get("tipo") in ("LOSS", "loss", "L"):
            racha_loss = int(r.get("n", 0))
    except Exception:
        pass

    # Pérdidas del día (si hay meta diaria con P&L)
    pnl_dia = 0.0
    try:
        meta = getattr(app, "meta_diaria", None)
        if meta and getattr(meta, "activa", False):
            pnl_dia = float(meta.stats().get("pnl", 0.0))
    except Exception:
        pass

    # Límites configurables
    cfg = app.mem.get("config", {})
    max_racha_naranja = int(cfg.get("cc_racha_naranja", 4))
    max_racha_roja    = int(cfg.get("cc_racha_roja", 6))
    perdida_dia_roja  = float(cfg.get("cc_perdida_dia_roja", -0.0)) or None

    # ROJO — parar
    if racha_loss >= max_racha_roja:
        return {"nivel": "ROJO", "factor": 0.0, "operar": False,
                "razon": f"{racha_loss} pérdidas seguidas — el cortacircuitos "
                         "manda parar. Cuando el mercado no respeta patrones, "
                         "no operar es la jugada profesional."}
    if perdida_dia_roja is not None and pnl_dia <= perdida_dia_roja:
        return {"nivel": "ROJO", "factor": 0.0, "operar": False,
                "razon": f"Límite de pérdida diaria alcanzado ({pnl_dia:.2f}). "
                         "Se detiene la operativa por hoy."}

    # NARANJA — tamaño mínimo
    if racha_loss >= max_racha_naranja:
        return {"nivel": "NARANJA", "factor": 0.5, "operar": True,
                "razon": f"{racha_loss} pérdidas seguidas — reduzco el tamaño a "
                         "la mitad y solo señales de alta confianza."}

    # AMARILLO — reducir un poco
    if racha_loss >= 2 or (pnl_dia < 0 and perdida_dia_roja and
                           pnl_dia <= perdida_dia_roja * 0.5):
        return {"nivel": "AMARILLO", "factor": 0.75, "operar": True,
                "razon": "Racha o drawdown moderado — reduzco el tamaño con "
                         "prudencia."}

    return {"nivel": "VERDE", "factor": 1.0, "operar": True,
            "razon": "Riesgo normal."}


# ── Muestra insuficiente (error B3: Kelly con pocos datos) ──────────────────

def muestra_suficiente(n_trades: int, minimo: int = 30) -> bool:
    """Regla dura: por debajo del mínimo, no se concluye nada estadístico."""
    return int(n_trades or 0) >= minimo


def intervalo_wr(aciertos: int, total: int) -> dict:
    """Devuelve el WR observado y su intervalo de confianza ~95% (Wald).

    Error B1: reportar el intervalo, no la estimación puntual. Dimensionar
    sobre el límite INFERIOR, no sobre el observado.
    """
    if not total:
        return {"wr": 0.0, "bajo": 0.0, "alto": 0.0, "n": 0}
    p = aciertos / total
    import math
    se = math.sqrt(max(p * (1 - p), 1e-9) / total)
    return {"wr": round(p * 100, 1),
            "bajo": round(max(0.0, p - 1.96 * se) * 100, 1),
            "alto": round(min(1.0, p + 1.96 * se) * 100, 1),
            "n": total}


# ── Redondeo al tick (error A2 / guardia IBKR 2) ────────────────────────────

def redondear_tick(precio):
    """round(precio, 2) para ≥$1; 4 decimales por debajo. Sin esto IBKR rechaza."""
    if precio is None:
        return None
    try:
        p = float(precio)
        return round(p, 2) if p >= 1.0 else round(p, 4)
    except Exception:
        return precio


# ── Veredicto integral para el motor de decisión ────────────────────────────

def evaluar_antes_de_operar(app) -> dict:
    """Guardia única que el motor de trading consulta antes de ejecutar.

    Devuelve {"operar": bool, "factor_tamano": float, "razon": str, "nivel": str}.
    NO decide la dirección; solo autoriza/limita el riesgo. La disciplina de
    estas guardias no se negocia por insistencia ni euforia (error C4).
    """
    cc = cortacircuito(app)
    return {
        "operar":        cc["operar"],
        "factor_tamano": cc["factor"],
        "nivel":         cc["nivel"],
        "razon":         cc["razon"],
        "ts":            time.time(),
    }


def resumen_riesgo(app, idioma: str = "es") -> str:
    """Informe de riesgo para «Litch, ¿cómo está mi riesgo?»."""
    cc = cortacircuito(app)
    est = app.mem.get("estadisticas", {})
    w, l = est.get("aciertos", 0), est.get("fallos", 0)
    iv = intervalo_wr(w, w + l)
    partes = [
        f"Cortacircuitos: nivel {cc['nivel']} — {cc['razon']}",
        f"Tamaño recomendado: {int(cc['factor']*100)}% del normal.",
    ]
    if iv["n"]:
        partes.append(
            f"Win rate: {iv['wr']}% observado en {iv['n']} trades "
            f"(real entre {iv['bajo']}% y {iv['alto']}% — dimensiono sobre el "
            f"límite inferior, no sobre el observado).")
    if not muestra_suficiente(iv["n"]):
        partes.append("Muestra por debajo de 30 trades: cualquier conclusión "
                      "estadística es ruido. No aumento tamaño.")
    return " ".join(partes)
