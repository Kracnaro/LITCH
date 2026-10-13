"""Laboratorio del Teorema de Litch — comprobación científica de sesgo.

La hipótesis del usuario: si en un sorteo las bolas tuvieran un sesgo
físico (peso desigual, desgaste, etc.), ciertos números aparecerían con
más frecuencia de la esperada por puro azar, y eso sería medible y
explotable. Este módulo NO afirma que exista ese sesgo: lo PONE A PRUEBA
con estadística honesta, que es justo lo que hace un científico.

Incluye:
  • Prueba de uniformidad chi-cuadrado: ¿las frecuencias observadas se
    desvían significativamente de lo esperado si todo fuese azar?
  • "Peso imaginario": índice relativo de cada número (frecuencia
    observada / frecuencia esperada). >1 = sale más de lo normal.
  • Análisis de consecutivos: ¿hay números que se repiten de un sorteo al
    siguiente más de lo que el azar predeciría?
  • Markov entre sorteos: probabilidad de transición de un número a otro.
  • Backtest honesto: simula predecir con el método y compara su acierto
    contra el acierto esperado del azar. Esta es la prueba de fuego.

Interpretación: si tras MUCHOS sorteos el chi-cuadrado da p < 0.05 de forma
estable Y el backtest supera al azar de forma consistente, habría evidencia
real de sesgo. Si no, el teorema no se sostiene para ese sorteo — que es un
resultado científico igual de valioso.
"""
import math
from collections import Counter


def _chi2_sf(chi2, df):
    """Aproximación de la cola superior de chi-cuadrado (sin scipy).
    Usa Wilson-Hilferty para estimar el p-valor."""
    if df <= 0:
        return 1.0
    if chi2 <= 0:
        return 1.0
    x = (chi2 / df)
    z = (x ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))
    # cola superior de la normal estándar
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def prueba_uniformidad(historial, rango=None):
    """¿Las frecuencias se desvían del azar? Devuelve dict con chi2, p, veredicto."""
    nums = [n for sorteo in historial for n in sorteo]
    if len(nums) < 20:
        return {"ok": False, "msg": "Necesito al menos 20 números para la prueba."}
    if rango is None:
        rango = (min(nums), max(nums))
    lo, hi = rango
    k = hi - lo + 1
    frec = Counter(nums)
    n = len(nums)
    esperado = n / k
    chi2 = sum((frec.get(v, 0) - esperado) ** 2 / esperado for v in range(lo, hi + 1))
    df = k - 1
    p = _chi2_sf(chi2, df)
    sesgo = p < 0.05
    return {
        "ok": True, "chi2": round(chi2, 2), "df": df, "p": round(p, 4),
        "n": n, "rango": (lo, hi), "sesgo_significativo": sesgo,
    }


def peso_imaginario(historial, rango=None, top=10):
    """Índice de 'peso' por número: frecuencia observada / esperada."""
    nums = [n for sorteo in historial for n in sorteo]
    if not nums:
        return []
    if rango is None:
        rango = (min(nums), max(nums))
    lo, hi = rango
    k = hi - lo + 1
    frec = Counter(nums)
    esperado = len(nums) / k
    pesos = []
    for v in range(lo, hi + 1):
        idx = frec.get(v, 0) / esperado if esperado else 0
        pesos.append((v, round(idx, 3), frec.get(v, 0)))
    pesos.sort(key=lambda x: x[1], reverse=True)
    return pesos[:top]


def consecutivos(historial):
    """Cuenta números que se repiten de un sorteo al inmediato siguiente."""
    if len(historial) < 2:
        return {"repeticiones": 0, "transiciones": 0, "tasa": 0.0}
    rep = 0
    trans = 0
    for i in range(1, len(historial)):
        previo = set(historial[i - 1])
        actual = set(historial[i])
        rep += len(previo & actual)
        trans += len(actual)
    tasa = rep / trans if trans else 0.0
    return {"repeticiones": rep, "transiciones": trans, "tasa": round(tasa, 4)}


def backtest(historial, rango=None, ventana=15):
    """Prueba de fuego: usa los primeros sorteos para 'aprender' los números
    más frecuentes y mide si aciertan en los siguientes, comparado con el azar.

    Devuelve aciertos del método vs aciertos esperados por azar."""
    if len(historial) < ventana + 5:
        return {"ok": False, "msg": f"Necesito al menos {ventana + 5} sorteos."}
    nums = [n for s in historial for n in s]
    rango = rango or (min(nums), max(nums))
    lo, hi = rango
    k = hi - lo + 1
    tam_apuesta = max(1, int(round(sum(len(s) for s in historial) / len(historial))))

    aciertos_metodo = 0
    aciertos_azar_esp = 0.0
    pruebas = 0
    for i in range(ventana, len(historial)):
        pasado = historial[:i]
        frec = Counter(n for s in pasado for n in s)
        # método: apuesta a los 'tam_apuesta' más frecuentes hasta ahora
        apuesta = [v for v, _ in frec.most_common(tam_apuesta)]
        real = set(historial[i])
        aciertos_metodo += len(set(apuesta) & real)
        # azar: probabilidad de acertar = tam_apuesta/k por cada bola real
        aciertos_azar_esp += len(real) * (tam_apuesta / k)
        pruebas += 1

    ventaja = aciertos_metodo - aciertos_azar_esp
    return {
        "ok": True, "pruebas": pruebas, "aciertos_metodo": aciertos_metodo,
        "aciertos_azar_esperados": round(aciertos_azar_esp, 2),
        "ventaja": round(ventaja, 2),
        "supera_azar": ventaja > 0,
    }


def informe(historial, idioma="es"):
    """Informe completo del laboratorio, en texto legible."""
    if not historial:
        return ("No hay sorteos cargados. Ingrese varios sorteos primero, señor."
                if idioma != "en" else "No draws loaded yet, sir.")
    u = prueba_uniformidad(historial)
    c = consecutivos(historial)
    b = backtest(historial)
    pesos = peso_imaginario(historial, top=6)

    L = []
    if idioma == "en":
        L.append("LITCH — THEOREM LABORATORY")
        L.append("=" * 42)
        if u.get("ok"):
            L.append(f"Uniformity test (chi-squared): chi2={u['chi2']}, "
                     f"df={u['df']}, p={u['p']} over {u['n']} numbers.")
            L.append("  -> Significant bias detected (p<0.05)." if u["sesgo_significativo"]
                     else "  -> No significant bias: consistent with pure chance.")
        L.append("")
        L.append("'Imaginary weight' (observed/expected, >1 = appears more):")
        for v, idx, cnt in pesos:
            L.append(f"   number {v}: weight {idx}  ({cnt} times)")
        L.append("")
        L.append(f"Consecutive repeats across draws: {c['repeticiones']} "
                 f"({c['tasa']*100:.1f}% of numbers).")
        if b.get("ok"):
            L.append("")
            L.append(f"BACKTEST ({b['pruebas']} draws): method hit "
                     f"{b['aciertos_metodo']} vs {b['aciertos_azar_esperados']} "
                     f"expected by chance. Edge: {b['ventaja']:+}.")
            L.append("  -> The method BEATS chance here." if b["supera_azar"]
                     else "  -> The method does NOT beat chance. Theorem unsupported so far.")
        L.append("")
        L.append("Honest note: a single sample can deviate by luck. Real evidence "
                 "needs the result to hold across many draws.")
        return "\n".join(L)

    L.append("LITCH — LABORATORIO DEL TEOREMA")
    L.append("=" * 42)
    if u.get("ok"):
        L.append(f"Prueba de uniformidad (chi-cuadrado): chi2={u['chi2']}, "
                 f"gl={u['df']}, p={u['p']} sobre {u['n']} números.")
        L.append("  -> Sesgo significativo detectado (p<0.05)." if u["sesgo_significativo"]
                 else "  -> Sin sesgo significativo: compatible con puro azar.")
    else:
        L.append(u.get("msg", ""))
    L.append("")
    L.append("'Peso imaginario' (observado/esperado, >1 = sale más):")
    for v, idx, cnt in pesos:
        L.append(f"   número {v}: peso {idx}  ({cnt} veces)")
    L.append("")
    L.append(f"Repeticiones consecutivas entre sorteos: {c['repeticiones']} "
             f"({c['tasa']*100:.1f}% de los números).")
    if b.get("ok"):
        L.append("")
        L.append(f"BACKTEST ({b['pruebas']} sorteos): el método acertó "
                 f"{b['aciertos_metodo']} vs {b['aciertos_azar_esperados']} "
                 f"esperados por azar. Ventaja: {b['ventaja']:+}.")
        L.append("  -> El método SUPERA al azar aquí." if b["supera_azar"]
                 else "  -> El método NO supera al azar. El teorema no se sostiene aún.")
    else:
        L.append(b.get("msg", ""))
    L.append("")
    L.append("Nota honesta: una sola muestra puede desviarse por suerte. La "
             "evidencia real exige que el resultado se mantenga en muchos sorteos.")
    return "\n".join(L)
