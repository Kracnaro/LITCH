"""
tamano_kelly.py — Cuánto poner en CADA operación, no siempre lo mismo.

━━━ LA PIEZA QUE FALTABA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ya está todo lo demás: Litch sabe lo que acierta de verdad
([[cuarentena_stats]]), dice confianzas que se corresponden con la
realidad ([[calibrar_confianza]]), y solo entra donde tiene ventaja
demostrada ([[filtro_ventaja]]).

Pero apostaba siempre la misma cantidad. Lo mismo en una señal de 8/11
votos con 89 % de acierto histórico que en una de 5/11 al 67 %. Eso
desperdicia la mejor información que tiene.

━━━ EL CRITERIO DE KELLY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Hay una fórmula que dice cuánto apostar para hacer crecer el capital lo
más rápido posible a largo plazo:

    f = (p·b − q) / b

    p = probabilidad de acertar    q = 1 − p
    b = cuánto se gana por unidad apostada (0,85 con pago del 85 %)

Con p = 0,80 y b = 0,85 sale f = 0,565 — el 56 % del capital.

**Y eso sería una barbaridad.** Kelly maximiza el crecimiento esperado,
pero el camino hasta ahí pasa por caídas brutales: con Kelly completo es
normal perder la mitad del capital antes de recuperarlo. Y la fórmula
supone que p es exacto. El p de Litch es una estimación con su error.

━━━ POR ESO SE USA KELLY FRACCIONADO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Se toma una fracción pequeña de lo que dice Kelly —aquí un cuarto— y
además se limita al 2 % del capital, que es la regla profesional.

    tamaño = min( Kelly/4 , 2 % del capital )

El resultado es que las señales buenas reciben más que las mediocres,
pero **ninguna recibe lo suficiente como para hacer daño**. La diferencia
entre 1 % y 2 % del capital compone mucho a lo largo de mil operaciones;
la diferencia entre 2 % y 50 % es la diferencia entre operar y arruinarse.

━━━ Y SI KELLY SALE NEGATIVO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Significa que esa apuesta tiene esperanza negativa: la respuesta correcta
es no apostar. No se reduce el tamaño — se salta la operación.
"""

from __future__ import annotations

# Fracción de Kelly que se usa. Un cuarto es lo habitual entre quienes
# lo aplican de verdad; Kelly completo es teórico.
FRACCION = 0.25
# Tope absoluto sobre el capital, pase lo que pase
TOPE_PCT = 0.02
# Suelo: por debajo de esto no merece la pena operar
SUELO_PCT = 0.002


def kelly(p: float, pago_pct: float = 85.0) -> float:
    """
    Fracción del capital que dice Kelly. Puede ser negativa.

    p: probabilidad de acertar (ya calibrada)
    pago: 85 para +85 %
    """
    try:
        b = float(pago_pct)
        if b > 3:
            b = b / 100.0
        p = max(0.0, min(1.0, float(p)))
        if b <= 0:
            return 0.0
        return (p * b - (1.0 - p)) / b
    except Exception:
        return 0.0


def calcular(capital: float, p: float, pago_pct: float = 85.0,
             fraccion: float = FRACCION,
             minimo_broker: float = 0.0) -> dict:
    """
    Cuánto poner en esta operación concreta.

    Devuelve todo el razonamiento, no solo la cifra: quien decide con
    dinero merece ver por qué.
    """
    r = {"monto": 0.0, "pct": 0.0, "kelly_puro": 0.0, "kelly_frac": 0.0,
         "operar": False, "motivo": "", "limitado_por": ""}
    try:
        cap = float(capital)
        if cap <= 0:
            r["motivo"] = "no sé cuál es su capital"
            return r
    except Exception:
        r["motivo"] = "capital no numérico"
        return r

    k = kelly(p, pago_pct)
    r["kelly_puro"] = round(k, 4)

    if k <= 0:
        r["motivo"] = (f"con {p*100:.0f} % de acierto y pago "
                       f"{pago_pct:.0f} %, Kelly sale {k*100:.1f} %: "
                       f"esperanza negativa. Lo correcto no es apostar "
                       f"menos, es no apostar")
        return r

    kf = k * fraccion
    r["kelly_frac"] = round(kf, 4)

    pct = kf
    r["limitado_por"] = f"Kelly/{int(1/fraccion)}"
    if pct > TOPE_PCT:
        pct = TOPE_PCT
        r["limitado_por"] = f"tope del {TOPE_PCT*100:.0f} %"
    if pct < SUELO_PCT:
        r["motivo"] = (f"Kelly fraccionado da {pct*100:.2f} % del capital: "
                       f"tan poco que no compensa el riesgo de ejecución")
        return r

    monto = cap * pct
    if minimo_broker and monto < minimo_broker:
        # El bróker tiene un mínimo. Si ese mínimo supera lo que Litch
        # considera prudente, se avisa en vez de forzar la operación.
        if minimo_broker > cap * TOPE_PCT * 1.5:
            r["motivo"] = (f"el mínimo del bróker ({minimo_broker:.0f}) es "
                           f"más del {TOPE_PCT*100:.0f} % de su capital. "
                           f"Con este saldo, ese activo no se puede operar "
                           f"con prudencia")
            return r
        monto = minimo_broker
        r["limitado_por"] = "mínimo del bróker"
        pct = monto / cap

    r.update({"monto": round(monto, 2), "pct": round(pct * 100, 3),
              "operar": True})
    r["motivo"] = (f"con {p*100:.0f} % de acierto calibrado, Kelly diría "
                   f"{k*100:.0f} % del capital; uso un "
                   f"{int(fraccion*100)} % de eso y lo limito al "
                   f"{TOPE_PCT*100:.0f} % → {pct*100:.2f} % "
                   f"(limitado por {r['limitado_por']})")
    return r


def sugerir(app, p_calibrada: float = 0.0, votos: int = 0) -> dict:
    """
    El tamaño para la operación de ahora, con los datos del señor.

    Si no se pasa `p_calibrada`, se deduce del historial en ese contexto.
    """
    cfg = app.mem.get("config", {}) if hasattr(app, "mem") else {}
    cap = float(cfg.get("saldo") or cfg.get("capital") or 0)
    pago = float(cfg.get("pago_pct") or 85)

    if not p_calibrada and votos:
        try:
            from . import filtro_ventaja as _fv
            c = _fv.contexto(app, votos)
            p_calibrada = c["peor"]     # el peor caso, no la media
        except Exception:
            p_calibrada = 0.0
    if not p_calibrada:
        p_calibrada = 0.55

    return calcular(cap, p_calibrada, pago)


def informe(app) -> str:
    """La tabla de tamaños según la confianza. Para verla de un vistazo."""
    cfg = app.mem.get("config", {})
    cap = float(cfg.get("saldo") or cfg.get("capital") or 0)
    pago = float(cfg.get("pago_pct") or 85)
    div = cfg.get("divisa", "")
    actual = float(cfg.get("monto_broker") or cfg.get("monto_base") or 0)

    try:
        from . import monto_real as _mr
        f = lambda v: _mr.formatear(v, div)
    except Exception:
        f = lambda v: f"{v:,.0f}"

    if not cap:
        return ("No sé su capital, señor. Sin eso no puedo calcular "
                "tamaños: cualquier cifra sería inventada. Escríbalo en "
                "«⚙ PREPARAR» o dígame «mi saldo es X».")

    l = [f"CUÁNTO PONER EN CADA OPERACIÓN", "",
         f"Capital {f(cap)} · pago {pago:.0f} %", ""]
    l.append("  Si acierto…   Kelly dice   Yo pongo    Del capital")
    l.append("  " + "─" * 48)
    for p in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        r = calcular(cap, p, pago)
        if not r["operar"]:
            l.append(f"  {p*100:5.0f} %        —          NO OPERO")
            continue
        l.append(f"  {p*100:5.0f} %      {r['kelly_puro']*100:5.0f} %     "
                 f"{f(r['monto']):>10}   {r['pct']:5.2f} %")

    l.append("")
    if actual:
        pct_act = actual / cap * 100
        l.append(f"Ahora tiene puesto {f(actual)} — el {pct_act:.2f} % fijo, "
                 f"igual para todas las señales.")
        if pct_act > TOPE_PCT * 100 * 1.5:
            l.append(f"Eso es más del doble de lo que pondría yo ni en la "
                     f"mejor señal.")
    l.append("")
    l.append(f"Kelly completo diría hasta el 56 % del capital con un 80 % de "
             f"acierto. **Sería una barbaridad**: maximiza el crecimiento "
             f"esperado, pero el camino pasa por perder la mitad antes de "
             f"recuperarla — y supone que mi probabilidad es exacta, cuando "
             f"es una estimación.")
    l.append("")
    l.append(f"Por eso uso un cuarto de Kelly y lo limito al "
             f"{TOPE_PCT*100:.0f} %. Las señales buenas reciben más que las "
             f"mediocres, pero ninguna lo suficiente para hacer daño.")
    return "\n".join(l)


__all__ = ["kelly", "calcular", "sugerir", "informe",
           "FRACCION", "TOPE_PCT", "SUELO_PCT"]
