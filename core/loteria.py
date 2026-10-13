"""Motor inteligente de análisis y predicción de loterías — Litch v2.

Análisis estadístico multicapa:
  1. Frecuencia ponderada: ¿qué números salen más? (hot numbers)
  2. Números fríos: ¿cuáles no salen hace tiempo? (due for comeback)
  3. Retraso: ¿cuántos sorteos lleva sin aparecer cada número?
  4. Pares de co-ocurrencia: ¿qué números salen juntos frecuentemente?
  5. Ley de Benford (primera cifra): desviación de la distribución natural
  6. Score bayesiano combinado: ponderación de todos los métodos

Predicción final: hasta 10 números con score de confianza individual.

ADVERTENCIA HONESTA: ningún análisis estadístico predice el futuro en
sorteos de azar. Esta herramienta es informativa, no profética.
"""
import math
from collections import Counter
from itertools import combinations

try:
    from .predictor_avanzado import PredictorCientifico
    _CIENTIFICO_OK = True
except Exception:
    _CIENTIFICO_OK = False


DESCARGO = (
    "⚠ Recordatorio honesto: cada sorteo es independiente. "
    "Ningún número tiene más probabilidad real por su historial. "
    "Esto es estadística descriptiva del pasado."
)


# ─── Parseo de texto ─────────────────────────────────────────────────────────

def parsear(texto: str) -> list:
    """Convierte texto (un sorteo por línea) en lista de listas de enteros."""
    historial = []
    for linea in texto.strip().splitlines():
        limpia  = linea.replace(",", " ").replace(";", " ").replace("-", " ")
        numeros = [int(t) for t in limpia.split() if t.isdigit()]
        if numeros:
            historial.append(numeros)
    return historial


# ─── Análisis de frecuencias (método clásico) ────────────────────────────────

def analizar(historial: list) -> tuple:
    """Análisis clásico de frecuencias. Devuelve (reporte, datos_dict)."""
    if not historial:
        return "No se ingresaron sorteos válidos.", {}

    todos     = [n for sorteo in historial for n in sorteo]
    frec      = Counter(todos)
    n_sorteos = len(historial)

    calientes = frec.most_common(6)
    frios     = sorted(frec.items(), key=lambda kv: (kv[1], kv[0]))[:6]

    # Atrasados
    ultima_ap = {}
    for i, sorteo in enumerate(historial):
        for n in sorteo:
            ultima_ap[n] = i
    atraso = sorted(
        ((n, n_sorteos - 1 - i) for n, i in ultima_ap.items()),
        key=lambda kv: kv[1], reverse=True)[:6]

    # Pares frecuentes
    pares = Counter()
    for sorteo in historial:
        for par in combinations(sorted(set(sorteo)), 2):
            pares[par] += 1
    pares_top = pares.most_common(5)

    # Sugerencia combinada
    sugerencia = []
    for n, _ in calientes:
        if n not in sugerencia:
            sugerencia.append(n)
        if len(sugerencia) >= 4:
            break
    for n, _ in atraso:
        if n not in sugerencia:
            sugerencia.append(n)
        if len(sugerencia) >= 6:
            break
    sugerencia.sort()

    lineas = [
        f"ANÁLISIS DE {n_sorteos} SORTEOS",
        "=" * 40, "",
        "Números CALIENTES (más frecuentes):",
        "   " + ", ".join(f"{n} ({c} veces)" for n, c in calientes), "",
        "Números FRÍOS (menos frecuentes):",
        "   " + ", ".join(f"{n} ({c} veces)" for n, c in frios), "",
        "Números ATRASADOS (sorteos sin salir):",
        "   " + ", ".join(f"{n} ({g} sorteos)" for n, g in atraso), "",
        "Pares que más salen juntos:",
        "   " + ", ".join(f"{a}-{b} ({c})" for (a, b), c in pares_top), "",
        f"Combinación sugerida: {' - '.join(map(str, sugerencia))}", "",
        DESCARGO,
    ]
    datos = {
        "calientes":  calientes,
        "frios":      frios,
        "atrasados":  atraso,
        "sugerencia": sugerencia,
    }
    return "\n".join(lineas), datos


# ─── Predictor inteligente ────────────────────────────────────────────────────

def _benford_score(num: int) -> float:
    """Qué tan 'natural' es el primer dígito según la Ley de Benford.
    Números cuyo primer dígito sigue la distribución de Benford → mayor peso.
    Devuelve 0..1 (más alto = más 'natural' según Benford).
    """
    s = str(abs(num))
    if not s or s[0] == "0":
        return 0.5
    d = int(s[0])
    if d == 0:
        return 0.5
    return math.log10(1 + 1 / d)   # 0.301 para d=1 … 0.046 para d=9


def _rango_numeros(historial: list) -> tuple:
    """Detecta el rango de números de la lotería a partir del historial."""
    todos = [n for s in historial for n in s]
    if not todos:
        return 0, 99
    mn, mx = min(todos), max(todos)
    # Redondear al rango 'natural' más probable
    if mx <= 43:        # estilo Baloto (1-43)
        return 1, 43
    if mx <= 99:
        return max(0, mn - 5), min(99, mx + 5)
    return 0, 9999      # lotería tradicional 4 cifras


def predecir(historial: list, n: int = 9) -> list:
    """Predice los `n` números más prometedores con score de confianza 0..100.

    Combina 5 criterios ponderados:
      40%  frecuencia relativa (calientes)
      20%  retraso (números que tardan en salir)
      15%  paridad de temperatura (frío → bonus leve)
      15%  co-ocurrencia con los más calientes (pares)
      10%  Ley de Benford (distribución natural del primer dígito)

    Devuelve lista de (número, score 0-100) ordenada de mayor a menor.
    """
    if not historial:
        return []
    n = max(1, min(10, n))

    todos  = [num for s in historial for num in s]
    frec   = Counter(todos)
    total  = len(todos)
    num_s  = len(historial)
    rango  = _rango_numeros(historial)
    pool   = sorted(frec.keys())   # números que han aparecido al menos 1 vez

    # 1) Score de frecuencia (0..1)
    max_frec = max(frec.values()) if frec else 1
    s_frec   = {num: frec[num] / max_frec for num in pool}

    # 2) Score de retraso (0..1): más tiempo sin salir → mayor score
    ultima_ap: dict = {}
    for i, sorteo in enumerate(historial):
        for num in sorteo:
            ultima_ap[num] = i
    max_atraso = num_s - 1 if num_s > 1 else 1
    s_atraso   = {num: (num_s - 1 - ultima_ap.get(num, 0)) / max_atraso
                  for num in pool}

    # 3) Score de temperatura inversa (frío → moderado bonus)
    media_frec  = total / len(pool) if pool else 1
    s_frio      = {num: max(0.0, 1.0 - frec[num] / (media_frec * 2))
                   for num in pool}

    # 4) Score de co-ocurrencia con los 3 números más calientes
    top3 = [n for n, _ in frec.most_common(3)]
    pares_frec = Counter()
    for sorteo in historial:
        for par in combinations(sorted(set(sorteo)), 2):
            pares_frec[par] += 1
    max_par = max(pares_frec.values()) if pares_frec else 1
    s_par   = {}
    for num in pool:
        puntos_par = 0.0
        for hot in top3:
            key = tuple(sorted([num, hot]))
            puntos_par += pares_frec.get(key, 0) / max_par
        s_par[num] = min(1.0, puntos_par / max(1, len(top3)))

    # 5) Score Benford (distribución natural del primer dígito)
    s_benford = {num: _benford_score(num) / 0.301 for num in pool}  # norm a 1

    # Score combinado (pesos)
    W = dict(frec=0.40, atraso=0.20, frio=0.15, par=0.15, benford=0.10)
    scores_raw = {}
    for num in pool:
        scores_raw[num] = (
            W["frec"]    * s_frec.get(num, 0)
            + W["atraso"] * s_atraso.get(num, 0)
            + W["frio"]   * s_frio.get(num, 0)
            + W["par"]    * s_par.get(num, 0)
            + W["benford"]* s_benford.get(num, 0)
        )

    # Normalizar a 0-100
    if not scores_raw:
        return []
    max_sc  = max(scores_raw.values())
    min_sc  = min(scores_raw.values())
    rng_sc  = max_sc - min_sc if max_sc > min_sc else 1.0
    scores  = {num: int((scores_raw[num] - min_sc) / rng_sc * 100)
               for num in pool}

    ordenados = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ordenados[:n]


def _fusionar_scores(clasico: list, cientifico: dict,
                     w_clasico: float = 0.40) -> list:
    """
    Fusiona (num, score_0_100) clásico con dict {num: score_0_100} científico.
    Devuelve lista [(num, score_fusionado_0_100)] ordenada de mayor a menor.
    """
    w_c = w_clasico
    w_s = 1.0 - w_clasico

    # Normalizar clásico a 0-1
    if not clasico:
        return []
    max_c = clasico[0][1] if clasico else 1
    c_map = {n: (sc / max(max_c, 1)) for n, sc in clasico}

    # Normalizar científico a 0-1
    max_s = max(cientifico.values()) if cientifico else 1
    s_map = {n: (sc / max(max_s, 1)) for n, sc in cientifico.items()}

    todos = set(c_map) | set(s_map)
    fused = {}
    for n in todos:
        fused[n] = w_c * c_map.get(n, 0.0) + w_s * s_map.get(n, 0.0)

    max_f = max(fused.values()) if fused else 1.0
    norm  = {n: int(v / max(max_f, 1e-9) * 100) for n, v in fused.items()}
    return sorted(norm.items(), key=lambda x: x[1], reverse=True)


def predecir_baloto(historial_completo: list, n_princ: int = 5,
                    n_super: int = 3) -> dict:
    """
    Predicción especializada Baloto / Balota Revancha.

    Combina 2 capas:
      40% predictor clásico (frecuencia, retraso, Benford, pares)
      60% predictor científico (Bayes, Monte Carlo, AR, Chi2, Markov, Hurst,
                                K-Means, Bootstrap, RQA)

    historial_completo: lista de sorteos [b1..b5, super?]

    Devuelve dict con:
      "principales"         : [(num, score), ...]
      "super"               : [(num, score), ...]
      "combinacion_sugerida": [n1,n2,n3,n4,n5]
      "super_sugerido"      : num
      "reporte_cientifico"  : str   (solo si _CIENTIFICO_OK)
    """
    if not historial_completo:
        return {"principales": [], "super": [], "combinacion_sugerida": [],
                "super_sugerido": None, "reporte_cientifico": ""}

    # ── Separar principales / SuperBalota ────────────────────────────────────
    hist_princ = [s[:5] for s in historial_completo if len(s) >= 5]
    hist_super = [[s[5]] for s in historial_completo if len(s) >= 6]

    # ── Predictor clásico ────────────────────────────────────────────────────
    pred_c_p = predecir(hist_princ, max(n_princ + 6, 12)) if hist_princ else []
    pred_c_s = predecir(hist_super, max(n_super + 2, 5))  if hist_super else []

    # ── Predictor científico (ensemble 9 métodos) ────────────────────────────
    rep_cient = ""
    if _CIENTIFICO_OK and len(hist_princ) >= 10:
        try:
            pc_p     = PredictorCientifico(hist_princ, rango=(1, 43), n_sim=8_000)
            sc_p     = pc_p.ensemble_scores()
            rep_cient = pc_p.reporte(top_n=9)
            pred_p   = _fusionar_scores(pred_c_p, sc_p, w_clasico=0.40)
        except Exception:
            pred_p = pred_c_p

        if len(hist_super) >= 10:
            try:
                pc_s   = PredictorCientifico(hist_super, rango=(1, 16), n_sim=4_000)
                sc_s   = pc_s.ensemble_scores()
                pred_s = _fusionar_scores(pred_c_s, sc_s, w_clasico=0.40)
            except Exception:
                pred_s = pred_c_s
        else:
            pred_s = pred_c_s
    else:
        pred_p = pred_c_p
        pred_s = pred_c_s

    # ── Selección final ──────────────────────────────────────────────────────
    comb      = sorted([n for n, _ in pred_p[:n_princ]])
    top_super = pred_s[0][0] if pred_s else None

    return {
        "principales":          pred_p,
        "super":                pred_s,
        "combinacion_sugerida": comb,
        "super_sugerido":       top_super,
        "reporte_cientifico":   rep_cient,
    }


def analizar_completo(historial: list, n: int = 9,
                      predicciones: list = None) -> tuple:
    """Predicción inteligente + análisis completo en texto.

    Si `predicciones` se pasa (lista de [(num, score),...]) se usa como tal;
    de lo contrario se calcula internamente con el predictor clásico.

    Devuelve (predicciones, reporte_texto):
      predicciones : [(numero, score), ...]
      reporte_texto: cadena con el análisis detallado
    """
    if not historial:
        return [], "Sin datos. Cargue sorteos primero."

    if predicciones is None:
        predicciones = predecir(historial, n)
    todos        = [num for s in historial for num in s]
    frec         = Counter(todos)
    n_sorteos    = len(historial)
    n_numeros    = len(frec)

    # --- Resumen estadístico ---
    calientes = frec.most_common(8)
    frios     = sorted(frec.items(), key=lambda kv: kv[1])[:6]

    # Atrasados
    ultima_ap: dict = {}
    for i, sorteo in enumerate(historial):
        for num in sorteo:
            ultima_ap[num] = i
    atraso = sorted(
        ((num, n_sorteos - 1 - i) for num, i in ultima_ap.items()),
        key=lambda kv: kv[1], reverse=True)[:6]

    # Pares
    pares  = Counter()
    for sorteo in historial:
        for par in combinations(sorted(set(sorteo)), 2):
            pares[par] += 1
    pares_top = pares.most_common(6)

    # Análisis Benford del primer dígito
    primeros = [int(str(abs(n))[0]) for n in todos if n > 0]
    dist_real = Counter(primeros)
    benford_esp = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
    total_prim  = len(primeros) or 1

    # Chi-cuadrado Benford
    chi2 = 0.0
    for d in range(1, 10):
        obs = dist_real.get(d, 0)
        exp = benford_esp[d] * total_prim
        chi2 += (obs - exp) ** 2 / max(exp, 0.1)

    # Sesgo de paridad
    pares_cnt   = sum(1 for n in todos if n % 2 == 0)
    pct_pares   = pares_cnt / len(todos) * 100 if todos else 50

    # Predicción → texto
    pred_nums = [str(num) for num, _ in predicciones]
    pred_sc   = [f"{num}({sc}%)" for num, sc in predicciones]

    lineas = [
        f"═══ LITCH · PREDICCIÓN INTELIGENTE · {n_sorteos} SORTEOS ═══",
        "",
        f"🎯 TOP {len(predicciones)} NÚMEROS PREDICHOS (con score de confianza):",
        "   " + "  ·  ".join(pred_sc),
        "",
        f"► Números seleccionados: {' — '.join(pred_nums)}",
        "",
        "─" * 48,
        f"📊 ANÁLISIS ESTADÍSTICO COMPLETO",
        "─" * 48,
        "",
        f"Sorteos analizados: {n_sorteos}   ·   Números únicos: {n_numeros}",
        "",
        "🔥 Números CALIENTES (más frecuentes):",
        "   " + "  ".join(f"{n}×{c}" for n, c in calientes),
        "",
        "❄ Números FRÍOS (menos frecuentes):",
        "   " + "  ".join(f"{n}×{c}" for n, c in frios),
        "",
        "⏳ Números más ATRASADOS (sin salir hace X sorteos):",
        "   " + "  ".join(f"{n}:{g}s" for n, g in atraso),
        "",
        "🔗 Pares más frecuentes juntos:",
        "   " + "  ·  ".join(f"{a}-{b}({c})" for (a, b), c in pares_top),
        "",
        "─" * 48,
        f"📐 LEY DE BENFORD (primer dígito):",
        f"   Chi² = {chi2:.2f} — " + (
            "Sesgo detectado (p<0.05): distribución no natural."
            if chi2 > 15.5 else
            "Sin sesgo significativo: distribución normal."
        ),
        "",
        f"⚖ Paridad: {pct_pares:.1f}% pares / {100-pct_pares:.1f}% impares",
        "",
        "─" * 48,
        DESCARGO,
    ]
    return predicciones, "\n".join(lineas)


# ─── Reporte completo Baloto ──────────────────────────────────────────────────

def analizar_baloto(historial_completo: list) -> tuple:
    """
    Análisis y predicción completa para Baloto / Balota Revancha.

    Devuelve (prediccion_dict, reporte_texto):
      prediccion_dict : resultado de predecir_baloto()
      reporte_texto   : cadena legible con análisis y combinación sugerida
    """
    if not historial_completo:
        return {}, "Sin datos. Cargue sorteos de Baloto primero."

    pred   = predecir_baloto(historial_completo)
    n_sort = len(historial_completo)
    comb   = pred["combinacion_sugerida"]
    super_s = pred["super_sugerido"]

    # Estadísticas de números principales
    hist_princ = [s[:5] for s in historial_completo if len(s) >= 5]
    hist_super = [[s[5]] for s in historial_completo if len(s) >= 6]

    todos_p   = [n for s in hist_princ for n in s]
    frec_p    = Counter(todos_p)
    calientes = frec_p.most_common(8)
    frios_p   = sorted(frec_p.items(), key=lambda kv: kv[1])[:6]

    # Estadísticas SuperBalota
    todos_sb  = [s[0] for s in hist_super]
    frec_sb   = Counter(todos_sb)
    hot_sb    = frec_sb.most_common(5)

    # Top scores principales y super
    top_princ = pred["principales"][:9]
    top_super = pred["super"][:5]

    pred_sc_p  = "  ·  ".join(f"{n}({sc}%)" for n, sc in top_princ)
    pred_sc_sb = "  ·  ".join(f"{n}({sc}%)" for n, sc in top_super)

    # Reporte científico (si está disponible)
    rep_cient = pred.get("reporte_cientifico", "")

    lineas = [
        f"═══ LITCH · ANÁLISIS BALOTO · {n_sort} SORTEOS ═══",
        "",
        f"► COMBINACION SUGERIDA:  {' - '.join(map(str, comb))}",
        f"► SUPERBALOTA SUGERIDA:  {super_s if super_s else '?'}",
        "",
        "─" * 50,
        "NUMEROS PRINCIPALES (1-43)",
        "─" * 50,
        "",
        f"Top candidatos (score):  {pred_sc_p}",
        "",
        "Calientes: " + "  ".join(f"{n}x{c}" for n, c in calientes),
        "Frios:     " + "  ".join(f"{n}x{c}" for n, c in frios_p),
        "",
        "─" * 50,
        "SUPERBALOTA (1-16)",
        "─" * 50,
        "",
        f"Top candidatos (score):  {pred_sc_sb if pred_sc_sb else 'necesita mas sorteos'}",
        "Mas frecuentes: " + "  ".join(f"{n}x{c}" for n, c in hot_sb),
        "",
        "─" * 50,
        DESCARGO,
    ]

    if rep_cient:
        lineas += ["", "─" * 50, rep_cient]

    return pred, "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
# EDUCACIÓN: cómo funciona cada juego (Baloto, Revancha, Astro Luna/Sol)
# ═══════════════════════════════════════════════════════════════════════════

INFO_JUEGOS = {
    "Baloto": (
        "🎱 BALOTO — Cómo funciona\n"
        "─────────────────────────\n"
        "· Eliges 5 números del 1 al 43 + 1 SuperBalota del 1 al 16.\n"
        "· Sorteos: miércoles y sábado en la noche.\n"
        "· Premio mayor (acumulado): acertar los 5 números + la SuperBalota.\n"
        "· Probabilidad real del premio mayor: 1 entre 15.401.568.\n"
        "  (C(43,5) = 962.598 combinaciones × 16 superbalotas)\n"
        "· Hay premios secundarios por 5, 4+SB, 4, 3+SB, 3, 2+SB aciertos.\n"
        "\n"
        "Qué analiza Litch: frecuencias históricas, números atrasados,\n"
        "pares que co-ocurren, ley de Benford y una red neuronal MLP.\n"
        "Verdad matemática: cada sorteo es independiente — el análisis\n"
        "describe el pasado, no garantiza el futuro."
    ),
    "Balota Revancha": (
        "🎱 BALOTA REVANCHA — Cómo funciona\n"
        "──────────────────────────────────\n"
        "· Es una segunda oportunidad del mismo tiquete de Baloto:\n"
        "  con los MISMOS 5 números + SuperBalota participas en un\n"
        "  segundo sorteo independiente, pagando un adicional.\n"
        "· Sorteos: miércoles y sábado, después del Baloto principal.\n"
        "· Misma probabilidad: 1 entre 15.401.568 para el mayor.\n"
        "· El acumulado de Revancha suele ser menor que el del Baloto.\n"
        "\n"
        "Litch la analiza igual que el Baloto, con su propio historial,\n"
        "porque las bolas y la máquina del sorteo son independientes."
    ),
    "Astro Luna": (
        "🌙 ASTRO LUNA — Cómo funciona\n"
        "─────────────────────────────\n"
        "· Juego SuperAstro NOCTURNO de Colombia (sorteo diario ~10:45 pm,\n"
        "  lunes a sábado).\n"
        "· Eliges un número de 4 cifras (0000–9999) + un signo zodiacal\n"
        "  (12 signos: Aries … Piscis).\n"
        "· Premio mayor: acertar las 4 cifras EN ORDEN + el signo →\n"
        "  paga 42.000 veces lo apostado.\n"
        "· Probabilidad real: 4 cifras = 1/10.000; con el signo =\n"
        "  1 entre 120.000.\n"
        "· Premios menores: últimas 3 cifras + signo (1.000×, prob. 1/12.000)\n"
        "  y últimas 2 cifras + signo (100×, prob. 1/1.200).\n"
        "\n"
        "Qué analiza Litch: frecuencia de cada cifra por posición,\n"
        "números completos calientes/fríos/atrasados y frecuencia de\n"
        "los 12 signos. Cada sorteo es independiente: el análisis es\n"
        "descriptivo, no una promesa."
    ),
    "Astro Sol": (
        "☀ ASTRO SOL — Cómo funciona\n"
        "───────────────────────────\n"
        "· Juego SuperAstro DIURNO de Colombia (sorteo diario ~1:00 pm,\n"
        "  lunes a sábado).\n"
        "· Idéntico a Astro Luna: 4 cifras (0000–9999) + signo zodiacal.\n"
        "· Premio mayor 42.000× (prob. 1 entre 120.000);\n"
        "  3 cifras+signo 1.000×; 2 cifras+signo 100×.\n"
        "\n"
        "Astro Sol y Astro Luna son sorteos separados con historiales\n"
        "separados. Litch analiza cada uno por su cuenta."
    ),
    "SuperAstro": (
        "✨ SUPERASTRO — Cómo funciona\n"
        "────────────────────────────\n"
        "· Nombre general del juego con dos sorteos diarios:\n"
        "  Astro Sol (día) y Astro Luna (noche).\n"
        "· 4 cifras + signo zodiacal. Premio mayor 42.000×.\n"
        "· Selecciona «Astro Luna» o «Astro Sol» en la lista para\n"
        "  analizar cada sorteo por separado."
    ),
}


def explicar_juego(nombre: str) -> str:
    """Explicación educativa de cómo funciona una lotería."""
    if nombre in INFO_JUEGOS:
        return INFO_JUEGOS[nombre] + "\n\n" + DESCARGO
    return (
        f"📋 {nombre}\n"
        "Lotería tradicional colombiana de 4 cifras (0000–9999).\n"
        "Premio mayor: acertar el número completo en orden (prob. 1/10.000\n"
        "por serie). Litch analiza frecuencia de cifras por posición,\n"
        "números calientes, fríos y atrasados.\n\n" + DESCARGO
    )


# ─── Análisis de signos zodiacales (Astro Luna / Astro Sol) ─────────────────

def analizar_signos(signos: list) -> str:
    """Frecuencia de signos zodiacales en el historial de SuperAstro.

    `signos` es una lista tipo ['leo', 'piscis', ...] (reciente primero).
    """
    if not signos:
        return ("Sin datos de signos. Busca resultados de Astro Luna o "
                "Astro Sol primero.")
    c = Counter(signos)
    total = len(signos)
    calientes = c.most_common(3)
    todos = ["aries", "tauro", "geminis", "cancer", "leo", "virgo", "libra",
             "escorpion", "sagitario", "capricornio", "acuario", "piscis"]
    frios = [s for s in todos if s not in c]
    # Retraso: hace cuántos sorteos no sale cada signo
    retraso = {}
    for s in todos:
        try:
            retraso[s] = signos.index(s)
        except ValueError:
            retraso[s] = total
    atrasados = sorted(retraso.items(), key=lambda kv: -kv[1])[:3]

    lineas = [
        f"♈ SIGNOS ZODIACALES ({total} sorteos analizados)",
        "─" * 46,
        "Calientes:  " + "  ".join(f"{s.capitalize()}×{n}" for s, n in calientes),
        "Atrasados:  " + "  ".join(f"{s.capitalize()} ({n} sorteos)"
                                   for s, n in atrasados),
    ]
    if frios:
        lineas.append("Sin salir:  " + ", ".join(s.capitalize() for s in frios))
    lineas += [
        "",
        "Cada signo tiene probabilidad real de 1/12 en cada sorteo,",
        "sin importar su historial. " + DESCARGO,
    ]
    return "\n".join(lineas)


def analizar_cifras_posicion(historial: list) -> str:
    """Frecuencia de cada cifra (0-9) por posición para juegos de 4 cifras."""
    nums = [s[0] for s in historial if s and isinstance(s[0], int)]
    if not nums:
        return "Sin historial de números."
    pos_nombres = ["Miles", "Centenas", "Decenas", "Unidades"]
    lineas = [f"🔢 CIFRAS POR POSICIÓN ({len(nums)} sorteos)", "─" * 46]
    for i in range(4):
        digitos = [int(f"{n:04d}"[i]) for n in nums]
        c = Counter(digitos)
        top = "  ".join(f"{d}×{k}" for d, k in c.most_common(3))
        faltan = [str(d) for d in range(10) if d not in c]
        linea = f"{pos_nombres[i]:<9}→ top: {top}"
        if faltan:
            linea += f"   sin salir: {','.join(faltan)}"
        lineas.append(linea)
    return "\n".join(lineas)
