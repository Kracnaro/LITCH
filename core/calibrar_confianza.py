"""
calibrar_confianza.py — Que cuando Litch diga 70 %, acierte el 70 %.

━━━ EL ÚLTIMO NÚMERO QUE MENTÍA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Litch lo dice ella misma en el registro:

    «Señor, mi calibración probabilística está baja: ECE=0.33.
     Mis estimaciones de confianza no coinciden con los resultados reales.»

ECE es el error de calibración: la distancia media entre lo que dice y
lo que pasa. Un 0,33 significa que cuando anuncia 70 % de confianza, la
realidad está a treinta y tres puntos de eso — puede ser 40 % o 95 %, y
no hay forma de saber cuál.

━━━ POR QUÉ IMPORTA MÁS DE LO QUE PARECE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Todo el sistema de decisión se apoya en ese número:

  · el filtro de ventaja compara la confianza con el punto de equilibrio
  · el tamaño de la posición debería crecer con la confianza
  · el señor decide si confirmar mirando ese porcentaje

Si el número está descalibrado, las tres decisiones son ruido. Un modelo
que acierta el 80 % pero no sabe CUÁNDO va a acertar no vale mucho más
que uno que acierta el 60 % y lo sabe.

━━━ CÓMO SE ARREGLA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Con la técnica más simple que funciona: **binning isotónico**.

Se agrupan las operaciones pasadas por la confianza que Litch anunció, y
se mira qué pasó de verdad en cada grupo:

    dijo 60-65 %  →  acertó el 71 %   (se quedaba corta)
    dijo 85-90 %  →  acertó el 62 %   (se pasaba de optimista)

Esa tabla es la corrección. Cuando el modelo diga 87 %, se mira en qué
grupo cae y se anuncia lo que ese grupo acertó de verdad.

No cambia las predicciones — cambia lo que Litch cree saber sobre ellas.
Y eso, con dinero de por medio, vale más.

━━━ HONESTIDAD SOBRE EL MÉTODO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
La corrección solo es fiable donde hay muestra. En los grupos con pocas
observaciones no se corrige nada: se deja el valor original y se dice
que no hay datos. Corregir con cinco observaciones sería cambiar un
número inventado por otro.
"""

from __future__ import annotations

import json
import math
import os
import time

# Los grupos en que se parte el rango de confianza
BORDES = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01]
# Mínimo de observaciones para corregir un grupo
MIN_GRUPO = 20
# Cada cuánto se recalcula la tabla (segundos)
TTL = 600.0

_CACHE = {"t": 0.0, "tabla": None}


def _ruta() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "MEMORIA_AP")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "calibracion.json")


def _grupo(p: float) -> int:
    """En qué grupo cae esa confianza."""
    for i in range(len(BORDES) - 1):
        if BORDES[i] <= p < BORDES[i + 1]:
            return i
    return 0 if p < BORDES[0] else len(BORDES) - 2


def _limpios(app) -> list:
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


def construir(app) -> dict:
    """
    Construye la tabla de corrección a partir del historial.

    Devuelve {grupos: [...], ece_antes, ece_despues, n}
    """
    tr = _limpios(app)
    grupos = []
    for i in range(len(BORDES) - 1):
        lo, hi = BORDES[i], BORDES[i + 1]
        sel = [t for t in tr
               if lo <= float(t.get("prob", 0) or 0) < hi]
        n = len(sel)
        ac = sum(1 for t in sel if _gano(t))
        dicho = (lo + min(hi, 1.0)) / 2.0
        real = (ac / n) if n else None
        grupos.append({
            "desde": round(lo, 2), "hasta": round(min(hi, 1.0), 2),
            "dicho": round(dicho, 3), "n": n, "aciertos": ac,
            "real": round(real, 3) if real is not None else None,
            "fiable": n >= MIN_GRUPO,
        })

    # ECE: error medio ponderado por cuántas operaciones hay en cada grupo
    total = sum(g["n"] for g in grupos) or 1
    ece = sum(g["n"] * abs(g["dicho"] - g["real"])
              for g in grupos if g["real"] is not None) / total

    # Después de corregir, el error de los grupos fiables es cero por
    # construcción; el de los no fiables se queda como estaba.
    ece_desp = sum(g["n"] * abs(g["dicho"] - g["real"])
                   for g in grupos
                   if g["real"] is not None and not g["fiable"]) / total

    tabla = {"grupos": grupos, "n": total,
             "ece_antes": round(ece, 4), "ece_despues": round(ece_desp, 4),
             "hora": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with open(_ruta(), "w", encoding="utf-8") as f:
            json.dump(tabla, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return tabla


def tabla(app, forzar: bool = False) -> dict:
    """La tabla actual, con caché."""
    ahora = time.time()
    if not forzar and _CACHE["tabla"] and (ahora - _CACHE["t"]) < TTL:
        return _CACHE["tabla"]
    t = construir(app)
    _CACHE.update({"t": ahora, "tabla": t})
    return t


def corregir(app, prob: float) -> tuple[float, str]:
    """
    Convierte la confianza cruda en la corregida.

    Devuelve (probabilidad corregida, explicación). Si el grupo no tiene
    muestra suficiente, devuelve la original y lo dice — corregir con
    cinco observaciones sería cambiar un número inventado por otro.
    """
    try:
        p = float(prob)
    except Exception:
        return 0.5, "valor no numérico"
    if not (0.0 <= p <= 1.0):
        return 0.5, "fuera de rango"

    try:
        t = tabla(app)
        g = t["grupos"][_grupo(p)]
    except Exception as e:
        return p, f"no pude calibrar ({e})"

    if not g["fiable"] or g["real"] is None:
        return p, (f"sin datos suficientes en el tramo "
                   f"{g['desde']:.0%}-{g['hasta']:.0%} "
                   f"({g['n']} operaciones); dejo el valor original")

    dif = g["real"] - g["dicho"]
    sentido = ("me quedaba corta" if dif > 0.02 else
               "me pasaba de optimista" if dif < -0.02 else "iba bien")
    return g["real"], (f"en el tramo {g['desde']:.0%}-{g['hasta']:.0%} "
                       f"acierto el {g['real']:.0%} de verdad "
                       f"({g['aciertos']}/{g['n']}) — {sentido}")


def informe(app) -> str:
    """Cómo de bien se conoce Litch a sí misma."""
    t = tabla(app, forzar=True)
    l = ["CALIBRACIÓN — ¿acierto lo que digo que voy a acertar?", ""]
    l.append(f"Sobre {t['n']} operaciones reales.")
    l.append("")
    l.append("  Tramo      Dije    Acerté   Muestra")
    l.append("  " + "─" * 42)

    for g in t["grupos"]:
        if g["n"] == 0:
            continue
        if g["real"] is None:
            continue
        marca = "✓" if g["fiable"] else "·"
        dif = g["real"] - g["dicho"]
        flecha = "↑" if dif > 0.03 else ("↓" if dif < -0.03 else "=")
        l.append(f"  {marca} {g['desde']:.0%}-{g['hasta']:.0%}  "
                 f"{g['dicho']:5.0%}   {g['real']:5.0%} {flecha}   "
                 f"{g['n']:4d} ops")

    l.append("")
    l.append(f"Error de calibración (ECE): {t['ece_antes']:.3f} "
             f"→ {t['ece_despues']:.3f} tras corregir")
    l.append("")
    if t["ece_antes"] > 0.15:
        l.append("Un ECE alto significa que mis porcentajes no describen la "
                 "realidad. Todo lo que decido con ellos —si opero, cuánto "
                 "pongo— se apoya en ese número, así que corregirlo importa "
                 "más de lo que parece.")
    else:
        l.append("Un ECE bajo significa que cuando digo 70 %, acierto cerca "
                 "del 70 %. Es lo que hace que mis porcentajes sirvan para "
                 "decidir.")
    l.append("")
    l.append("↑ = me quedaba corta   ↓ = me pasaba de optimista")
    l.append("· = sin muestra suficiente, ahí no corrijo nada.")
    return "\n".join(l)


__all__ = ["construir", "tabla", "corregir", "informe", "BORDES", "MIN_GRUPO"]
