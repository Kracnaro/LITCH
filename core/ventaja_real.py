"""
ventaja_real.py — ¿Esta operación tiene sentido matemático, o solo esperanza?

━━━ EL NÚMERO QUE LO CAMBIA TODO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En la pantalla del señor, IQ Option paga **+85 %**. Eso significa:

    Si acierta:  gana  42,50 sobre 50
    Si falla:    pierde 50,00

No son simétricos, y ahí está todo. Para no perder ni ganar hace falta:

    p × 42,50 = (1 − p) × 50
    p × 92,50 = 50
    p = 54,05 %

**Acertar la mitad de las veces NO empata: pierde.** Con un 50 % de
aciertos, cada 100 operaciones de 50 dejan un saldo de −375. El sistema
está diseñado así; no es un fallo de Litch ni de la plataforma.

━━━ POR QUÉ ESTO IMPORTA MÁS QUE CUALQUIER ALGORITMO ━━━━━━━━━━━━━━━━━
El señor pidió «un algoritmo que memorice estrategias que lleven siempre
a la victoria». Ese algoritmo no existe, y quien diga tenerlo miente. Lo
que sí existe es esto:

    No operar cuando la ventaja no está de tu lado.

Un jugador que solo entra cuando tiene ventaja real gana a largo plazo
aunque falle mucho. Uno que entra siempre, pierde aunque acierte más de
la mitad. La diferencia no está en predecir mejor: está en **saber
cuándo callarse**.

━━━ QUÉ HACE ESTE MÓDULO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Calcula, para cada operación concreta:

  · el punto de equilibrio según el pago real de esa pantalla
  · la esperanza matemática en dinero
  · si Litch ha demostrado ventaja EN ESE CONTEXTO (activo, hora,
    patrón), con muestra suficiente

Y bloquea lo que tiene esperanza negativa. No es pesimismo: es la única
forma conocida de no regalar dinero.
"""

from __future__ import annotations

import math

# Mínimo de operaciones antes de creerse una tasa de acierto.
# Con menos de esto, un 70 % puede ser pura suerte.
MIN_MUESTRA = 40

# Margen de seguridad sobre el punto de equilibrio. Estar justo en el
# equilibrio no sirve: cualquier variación normal te pone en pérdida.
MARGEN = 0.03


def punto_equilibrio(pago_pct: float) -> float:
    """
    Tasa de acierto necesaria para no perder, dado el pago.

    pago_pct: 85 para +85 %, 0.85 también vale.
    """
    try:
        p = float(pago_pct)
        if p > 3:
            p = p / 100.0
        if p <= 0:
            return 1.0
        return round(1.0 / (1.0 + p), 4)
    except Exception:
        return 0.55


def esperanza(tasa: float, pago_pct: float, monto: float) -> float:
    """Cuánto se gana o se pierde de media por operación, en dinero."""
    try:
        p = float(pago_pct)
        if p > 3:
            p = p / 100.0
        t = max(0.0, min(1.0, float(tasa)))
        m = float(monto)
        return round(t * m * p - (1.0 - t) * m, 2)
    except Exception:
        return 0.0


def cota_inferior(aciertos: int, total: int, z: float = 1.96) -> float:
    """
    Tasa de acierto en el peor caso razonable (Wilson).

    Se usa la COTA INFERIOR, no la media. Motivo: apostar dinero sobre la
    media es apostar sobre el escenario optimista. Si con el pesimista
    todavía hay ventaja, la ventaja es real.
    """
    n = max(0, int(total))
    if n == 0:
        return 0.0
    p = max(0, min(int(aciertos), n)) / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, centro - margen), 4)


def evaluar(aciertos: int, total: int, pago_pct: float = 85.0,
            monto: float = 50.0) -> dict:
    """
    ¿Conviene operar con este historial y este pago?

    Devuelve todo lo necesario para decidir, y el porqué.
    """
    eq = punto_equilibrio(pago_pct)
    exigido = round(eq + MARGEN, 4)
    lo = cota_inferior(aciertos, total)
    media = round(aciertos / total, 4) if total else 0.0

    r = {
        "equilibrio": eq,
        "exigido": exigido,
        "tasa_media": media,
        "tasa_peor_caso": lo,
        "n": total,
        "muestra_suficiente": total >= MIN_MUESTRA,
        "esperanza_media": esperanza(media, pago_pct, monto),
        "esperanza_peor": esperanza(lo, pago_pct, monto),
        "operar": False,
        "motivo": "",
    }

    if total < MIN_MUESTRA:
        r["motivo"] = (f"solo {total} operaciones en este contexto; con menos "
                       f"de {MIN_MUESTRA} no distingo una ventaja real de una "
                       f"racha de suerte")
        return r

    if lo < exigido:
        falta = round((exigido - lo) * 100, 1)
        r["motivo"] = (f"en el peor caso acierto el {lo*100:.1f} %, y con un "
                       f"pago del {pago_pct:.0f} % hace falta {exigido*100:.1f} % "
                       f"para no perder. Me faltan {falta} puntos: cada "
                       f"operación esperaría {r['esperanza_peor']:+.2f}")
        return r

    r["operar"] = True
    r["motivo"] = (f"acierto {lo*100:.1f} % en el peor caso, por encima del "
                   f"{exigido*100:.1f} % necesario. Esperanza "
                   f"{r['esperanza_peor']:+.2f} por operación")
    return r


def explicar(pago_pct: float = 85.0, monto: float = 50.0) -> str:
    """La matemática, en cristiano."""
    eq = punto_equilibrio(pago_pct)
    p = float(pago_pct) / 100.0 if pago_pct > 3 else float(pago_pct)
    gana = round(monto * p, 2)
    return (
        f"LA MATEMÁTICA DE ESTA PANTALLA — pago {pago_pct:.0f} %\n"
        f"\n"
        f"Si acierto gano {gana:.2f}. Si fallo pierdo {monto:.2f}.\n"
        f"No son simétricos, y ahí está todo.\n"
        f"\n"
        f"Para no perder ni ganar necesito acertar el {eq*100:.2f} % de las "
        f"veces. Acertar la mitad NO empata: con un 50 % de aciertos, cada "
        f"100 operaciones de {monto:.0f} dejan {esperanza(0.5, pago_pct, monto)*100:+.0f} "
        f"de saldo.\n"
        f"\n"
        f"Yo trabajo con margen: exijo {(eq+MARGEN)*100:.1f} % antes de "
        f"entrar. Estar justo en el equilibrio no sirve — cualquier "
        f"variación normal te pone en pérdida.\n"
        f"\n"
        f"Y uso la cota inferior, no la media. Apostar sobre la media es "
        f"apostar sobre el escenario optimista. Si con el pesimista todavía "
        f"hay ventaja, la ventaja es real.\n"
        f"\n"
        f"Señor, no existe un algoritmo que gane siempre. Lo que sí existe "
        f"es no operar cuando la ventaja no está de nuestro lado. Quien "
        f"solo entra con ventaja gana a la larga aunque falle mucho; quien "
        f"entra siempre pierde aunque acierte más de la mitad. La "
        f"diferencia no está en predecir mejor, está en saber callarse."
    )


def contexto_actual(app, asset: str = "", hora: int = -1) -> dict:
    """
    Ventaja demostrada en el contexto de AHORA: este activo, esta hora.

    Una tasa global no sirve para decidir una operación concreta. Litch
    puede ir bien en Nvidia a las 15 h y fatal en EUR/USD a las 3 h.
    """
    try:
        fdb = getattr(app, "fdb", None)
        trades = list(getattr(fdb, "trades", []) or [])
    except Exception:
        trades = []

    try:
        from . import cuarentena_stats as _cq
        trades = _cq.solo_limpios(trades)
    except Exception:
        pass

    def _gano(t):
        return str(t.get("res", "")).upper() in ("WIN", "GANO", "ACIERTO")

    sel = trades
    if asset:
        a = asset.upper()
        sel = [t for t in sel if a in str(t.get("asset", "")).upper()] or sel
    if hora >= 0:
        porh = [t for t in sel if int(t.get("hora_h", -1)) == hora]
        if len(porh) >= MIN_MUESTRA:
            sel = porh

    n = len(sel)
    ac = sum(1 for t in sel if _gano(t))
    return {"n": n, "aciertos": ac, "asset": asset or "todos",
            "hora": hora if hora >= 0 else "todas"}


def veredicto(app, pago_pct: float = 85.0, monto: float = 50.0,
              asset: str = "", hora: int = -1) -> str:
    """¿Conviene operar ahora? Con los números delante."""
    c = contexto_actual(app, asset, hora)
    e = evaluar(c["aciertos"], c["n"], pago_pct, monto)
    l = [f"¿CONVIENE OPERAR? — {c['asset']}, hora {c['hora']}", ""]
    l.append(f"· Historial limpio      : {c['aciertos']} de {c['n']}")
    l.append(f"· Acierto medio         : {e['tasa_media']*100:.1f} %")
    l.append(f"· Acierto en peor caso  : {e['tasa_peor_caso']*100:.1f} %")
    l.append(f"· Necesario (pago {pago_pct:.0f} %) : {e['equilibrio']*100:.2f} %")
    l.append(f"· Exijo con margen      : {e['exigido']*100:.1f} %")
    l.append(f"· Esperanza por operación: {e['esperanza_peor']:+.2f}")
    l.append("")
    l.append(("SÍ — " if e["operar"] else "NO — ") + e["motivo"])
    return "\n".join(l)


__all__ = ["punto_equilibrio", "esperanza", "cota_inferior", "evaluar",
           "explicar", "contexto_actual", "veredicto", "MIN_MUESTRA", "MARGEN"]
