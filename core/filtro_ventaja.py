"""
filtro_ventaja.py — El filtro que separa ganar de perder.

━━━ LA IDEA, EN UNA FRASE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Litch no gana acertando más. Gana operando menos.

Con un pago del 85 %, el punto de equilibrio está en el 54,05 %. Litch
acierta de media el 78 %. Parece que basta con operar siempre.

No basta, y el motivo es que ese 78 % es un promedio. Debajo hay
contextos donde acierta el 90 % y otros donde acierta el 45 %. Operar en
los segundos regala exactamente lo que ganan los primeros. El promedio
sale bien y la cuenta sale mal.

━━━ QUÉ HACE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antes de cada operación mira el historial de ESE contexto concreto —
esta hora, este número de votos, este patrón— y calcula si ahí ha
demostrado ventaja por encima del equilibrio.

  · Ventaja demostrada  → adelante
  · Ventaja negativa    → se salta la operación y anota por qué
  · Muestra insuficiente → deja pasar, pero lo dice

Ese último caso importa: sin datos hay que dejar operar, porque si no
nunca habría datos. Es la exploración necesaria para aprender. Pero se
hace sabiendo que se está explorando, no creyendo que se está apostando
sobre seguro.

━━━ POR QUÉ LA COTA INFERIOR Y NO LA MEDIA ━━━━━━━━━━━━━━━━━━━━━━━━━━━
Apostar sobre la media es apostar sobre el escenario optimista. Si con
el pesimista todavía hay ventaja, la ventaja es real. Un 70 % sobre 10
operaciones tiene una cota inferior del 40 %: no basta. El mismo 70 %
sobre 200 la tiene del 63 %: eso sí.
"""

from __future__ import annotations

import math
import time

# Mínimo de operaciones antes de creerse un contexto
MIN_N = 25
# Margen sobre el equilibrio: estar justo empatado no compensa el riesgo
MARGEN = 0.02
# Cada cuánto se recalcula (segundos). Los contextos no cambian a cada tick.
TTL = 45.0

_CACHE: dict = {}


def _wilson(aciertos: int, n: int, z: float = 1.96) -> float:
    """Cota inferior de Wilson. El acierto en el peor caso razonable."""
    if n <= 0:
        return 0.0
    p = max(0, min(aciertos, n)) / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def _limpios(app) -> list:
    """Solo operaciones que ocurrieron de verdad."""
    try:
        tr = list(getattr(getattr(app, "fdb", None), "trades", []) or [])
    except Exception:
        return []
    try:
        from . import cuarentena_stats as _cq
        return _cq.solo_limpios(tr)
    except Exception:
        return [t for t in tr if not t.get("sospechosa")]


def _gano(t) -> bool:
    return str(t.get("res", "")).upper() in ("WIN", "GANO", "ACIERTO")


def contexto(app, votos: int, hora: int = -1, patron: str = "") -> dict:
    """
    Historial en el contexto de AHORA.

    Se buscan las operaciones parecidas, de más específico a más general,
    y se para en el primer nivel con muestra suficiente. Así se usa la
    información más pertinente que exista, sin quedarse sin datos.
    """
    tr = _limpios(app)
    if hora < 0:
        hora = int(time.strftime("%H"))

    niveles = []
    # 1. Mismo patrón, misma franja de votos — lo más parecido
    if patron and patron != "?":
        niveles.append(("patrón «%s» con %d votos" % (patron, votos),
                        [t for t in tr if t.get("pat") == patron
                         and abs(int(t.get("vt", 0)) - votos) <= 1]))
    # 2. Misma franja de votos
    niveles.append(("%d votos" % votos,
                    [t for t in tr if abs(int(t.get("vt", 0)) - votos) <= 1]))
    # 3. Misma hora del día
    niveles.append(("hora %02d:00" % hora,
                    [t for t in tr if int(t.get("hora_h", -1)) == hora]))
    # 4. Todo
    niveles.append(("todo el historial", tr))

    for nombre, sel in niveles:
        if len(sel) >= MIN_N:
            ac = sum(1 for t in sel if _gano(t))
            return {"nombre": nombre, "n": len(sel), "aciertos": ac,
                    "media": ac / len(sel), "peor": _wilson(ac, len(sel))}

    # Nada con muestra suficiente
    sel = niveles[-1][1]
    ac = sum(1 for t in sel if _gano(t))
    return {"nombre": "sin muestra suficiente", "n": len(sel), "aciertos": ac,
            "media": (ac / len(sel)) if sel else 0.0,
            "peor": _wilson(ac, len(sel))}


def evaluar(app, votos: int, patron: str = "", pago_pct: float = 0.0) -> dict:
    """
    ¿Conviene esta operación concreta?

    Devuelve {operar, motivo, contexto, equilibrio, esperanza}.
    """
    cfg = app.mem.get("config", {}) if hasattr(app, "mem") else {}
    if not pago_pct:
        pago_pct = float(cfg.get("pago_pct") or 85)
    monto = float(cfg.get("monto_broker") or cfg.get("monto_base") or 0)

    try:
        from . import ventaja_real as _vr
        eq = _vr.punto_equilibrio(pago_pct)
    except Exception:
        eq = 1.0 / (1.0 + (pago_pct / 100.0 if pago_pct > 3 else pago_pct))

    exigido = eq + MARGEN
    c = contexto(app, votos, patron=patron)

    p = float(pago_pct) / 100.0 if pago_pct > 3 else float(pago_pct)
    esp = (c["peor"] * monto * p - (1 - c["peor"]) * monto) if monto else 0.0

    r = {"operar": True, "motivo": "", "contexto": c, "equilibrio": eq,
         "exigido": exigido, "esperanza": round(esp, 2), "explorando": False}

    if c["n"] < MIN_N:
        # Sin datos hay que dejar operar: si no, nunca habría datos.
        # Pero se hace sabiendo que se está explorando.
        r["explorando"] = True
        r["motivo"] = (f"solo {c['n']} operaciones parecidas; opero para "
                       f"aprender, no porque tenga ventaja demostrada")
        return r

    if c["peor"] < exigido:
        r["operar"] = False
        falta = (exigido - c["peor"]) * 100
        r["motivo"] = (
            f"en {c['nombre']} acierto el {c['peor']*100:.1f} % en el peor "
            f"caso, y con pago {pago_pct:.0f} % hace falta "
            f"{exigido*100:.1f} %. Me faltan {falta:.1f} puntos"
            + (f"; cada operación esperaría {esp:+.0f}" if monto else ""))
        return r

    r["motivo"] = (f"en {c['nombre']} acierto {c['peor']*100:.1f} % en el "
                   f"peor caso sobre {c['n']} operaciones, por encima del "
                   f"{exigido*100:.1f} % necesario"
                   + (f"; esperanza {esp:+.0f}" if monto else ""))
    return r


def permitir(app, votos: int, patron: str = "") -> tuple[bool, str]:
    """
    Versión corta para el motor. (sí/no, motivo).

    Con caché: el contexto no cambia entre dos velas seguidas y recorrer
    2000 operaciones en cada señal sería tirar CPU.
    """
    clave = (int(votos), str(patron))
    ahora = time.time()
    ent = _CACHE.get(clave)
    if ent and (ahora - ent[0]) < TTL:
        return ent[1], ent[2]
    try:
        r = evaluar(app, votos, patron)
        res = (bool(r["operar"]), r["motivo"])
    except Exception as e:
        res = (True, f"no pude evaluar la ventaja ({e}); dejo pasar")
    _CACHE[clave] = (ahora, res[0], res[1])
    return res


def informe(app) -> str:
    """Dónde tiene ventaja Litch y dónde no. Para mirarlo de vez en cuando."""
    tr = _limpios(app)
    cfg = app.mem.get("config", {})
    pago = float(cfg.get("pago_pct") or 85)
    try:
        from . import ventaja_real as _vr
        eq = _vr.punto_equilibrio(pago)
    except Exception:
        eq = 0.5405
    exigido = eq + MARGEN

    l = [f"DÓNDE TENGO VENTAJA — pago {pago:.0f} %, hace falta "
         f"{exigido*100:.1f} %", "",
         f"Sobre {len(tr)} operaciones reales.", ""]

    # Por número de votos
    l.append("POR ACUERDO ENTRE MÉTODOS:")
    for v in range(2, 12):
        sel = [t for t in tr if int(t.get("vt", 0)) == v]
        if len(sel) < MIN_N:
            continue
        ac = sum(1 for t in sel if _gano(t))
        peor = _wilson(ac, len(sel))
        marca = "✓" if peor >= exigido else "✗"
        l.append(f"  {marca} {v:2d}/11 votos: {peor*100:5.1f} % peor caso "
                 f"({ac}/{len(sel)})")

    # Por hora
    l.append("")
    l.append("POR HORA DEL DÍA (solo las que tienen muestra):")
    buenas, malas = [], []
    for h in range(24):
        sel = [t for t in tr if int(t.get("hora_h", -1)) == h]
        if len(sel) < MIN_N:
            continue
        ac = sum(1 for t in sel if _gano(t))
        peor = _wilson(ac, len(sel))
        (buenas if peor >= exigido else malas).append((h, peor, len(sel)))
    for h, p, n in sorted(buenas, key=lambda x: -x[1])[:6]:
        l.append(f"  ✓ {h:02d}:00 — {p*100:5.1f} % ({n} ops)")
    for h, p, n in sorted(malas, key=lambda x: x[1])[:6]:
        l.append(f"  ✗ {h:02d}:00 — {p*100:5.1f} % ({n} ops)")

    l.append("")
    l.append("Las marcadas ✗ las salto. No gano acertando más: gano "
             "operando menos, solo donde la ventaja está demostrada.")
    return "\n".join(l)


__all__ = ["permitir", "evaluar", "contexto", "informe", "MIN_N", "MARGEN"]
