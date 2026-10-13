"""Motor estadístico avanzado de Litch — segundo método de análisis.

Mientras analisis.py usa una sola cadena de Markov de orden 3, este módulo
combina OCHO métodos independientes y vota entre ellos. Cuando los métodos
coinciden, la decisión es asertiva; cuando discrepan, Litch se abstiene.

Métodos:
 1) Ensemble Markov multi-orden con decay temporal (1, 2 y 3 velas):
    Patrones recientes pesan más que antiguos (decay=0.97 por posición).
 2) Prueba chi-cuadrado de bondad de ajuste: mide si el sesgo observado es
    estadísticamente significativo o pura casualidad.
 3) Test de rachas (runs / Wald-Wolfowitz simplificado): detecta tendencias
    y reversiones de momentum en la serie reciente.
 4) Tendencia ponderada (EWMA ligera): mide el sesgo de las últimas 15 velas
    comparado con las últimas 40 — cruce = señal de cambio de régimen.
 5) Entropía condicional de orden 1: si la serie es altamente desordenada,
    reduce la confianza de todos los otros métodos automáticamente.
 6) Momentum puro de corto plazo: detecta 3+ velas consecutivas del mismo
    color — señal de tendencia clara en las últimas N velas (patrón técnico).

 NUEVOS EN v2:
 7) Z-score del win-rate reciente: compara la tasa de éxito de las últimas
    20 velas contra la media histórica con desviación estándar. Z > 1.5 indica
    régimen alcista anómalo; Z < -1.5 indica régimen bajista anómalo.
    Detecta cambios de régimen antes que los métodos de media móvil.
 8) Autocorrelación lag-1: mide si la serie tiende a seguir su dirección
    (autocorrelación positiva → tendencia) o a revertirla (negativa → mean-reversion).
    Correlación > 0.15 → seguir momentum  |  < -0.15 → anticipar reversión.

Umbral adaptativo (nuevo v2):
    Si la entropía global es alta (>0.80), el umbral de confianza se eleva
    automáticamente a 0.68 para ser más selectivo en mercados ruidosos.

Todo es estadística honesta: estima probabilidades del pasado, no garantiza
el futuro. Sirve para filtrar ruido y actuar solo con ventaja real.
"""
import math


def _markov_multiorden(secuencia, ordenes=(1, 2, 3, 4), decay=0.97):
    """Markov multi-orden (1..4) con decay exponencial temporal.

    v3: Añadido orden 4 para capturar patrones de 4-velas (p. ej. VVRR, VRVR).
    Los órdenes altos solo aportan cuando tienen suficiente evidencia (umbral>2.0
    para orden 4 vs 1.5 para órdenes menores), evitando ruido en series cortas.

    Pesos de orden: order 1 → 1.0×, order 2 → 1.8×, order 3 → 2.5×, order 4 → 3.0×
    (progresión no lineal: órdenes altos aportan más si tienen evidencia).
    """
    _PESOS_ORDEN = {1: 1.0, 2: 1.8, 3: 2.5, 4: 3.0}
    _UMBRAL_EV   = {1: 1.0, 2: 1.5, 3: 1.5, 4: 2.0}   # mínimo de peso acumulado

    if len(secuencia) < 2:
        return None, 0.0, 0
    votos = {"V": 0.0, "R": 0.0}
    evidencia_total = 0
    n = len(secuencia)
    for orden in ordenes:
        if n <= orden + 2:   # necesitar al menos 3 instancias posibles del patrón
            continue
        patron = "".join(secuencia[-orden:])
        cuenta = {"V": 0.0, "R": 0.0}
        for i in range(n - orden):
            if "".join(secuencia[i:i + orden]) == patron:
                w = decay ** (n - orden - i - 1)
                cuenta[secuencia[i + orden]] += w
        total = cuenta["V"] + cuenta["R"]
        umbral = _UMBRAL_EV.get(orden, 1.5)
        if total >= umbral:
            peso = _PESOS_ORDEN.get(orden, orden) * total
            votos["V"] += peso * cuenta["V"] / total
            votos["R"] += peso * cuenta["R"] / total
            evidencia_total += max(1, int(total))
    suma = votos["V"] + votos["R"]
    if suma == 0:
        return None, 0.0, 0
    direccion = "V" if votos["V"] >= votos["R"] else "R"
    confianza = max(votos["V"], votos["R"]) / suma
    return direccion, confianza, evidencia_total


def _chi_cuadrado(secuencia, ventana=40):
    """¿El sesgo verde/rojo reciente es significativo? Devuelve
    (direccion, confianza 0..1) según el desbalance y su significancia."""
    reciente = secuencia[-ventana:]
    n = len(reciente)
    if n < 10:
        return None, 0.0
    verdes = reciente.count("V")
    rojos = n - verdes
    esperado = n / 2
    chi = ((verdes - esperado) ** 2 + (rojos - esperado) ** 2) / esperado
    # chi alto => sesgo significativo. Normalizamos a 0..1 (chi=6.6 ~ p<0.01)
    confianza = min(1.0, chi / 6.635)
    direccion = "V" if verdes > rojos else "R"
    return direccion, confianza


def _test_rachas(secuencia, ventana=30):
    """Detecta momentum: si hay una racha actual fuerte, predice continuación;
    si la serie es muy alternante, predice reversión."""
    reciente = secuencia[-ventana:]
    if len(reciente) < 6:
        return None, 0.0
    # longitud de la racha final
    ultimo = reciente[-1]
    racha = 0
    for c in reversed(reciente):
        if c == ultimo:
            racha += 1
        else:
            break
    # número de cambios (rachas) en la ventana
    cambios = sum(1 for i in range(1, len(reciente))
                  if reciente[i] != reciente[i - 1])
    alternancia = cambios / (len(reciente) - 1)
    if racha >= 3:
        # momentum fuerte: probable continuación
        return ultimo, min(1.0, racha / 5)
    if alternancia > 0.7:
        # muy alternante: probable reversión respecto al último
        return ("R" if ultimo == "V" else "V"), min(1.0, alternancia)
    return None, 0.0


def _ewma_ligera(secuencia, v_corta=15, v_larga=40):
    """Compara la proporción de verdes en las últimas v_corta vs v_larga velas.

    Si reciente > largo → sesgo alcista de corto plazo (cruce al alza).
    Devuelve (dirección, confianza 0..1).
    """
    n = len(secuencia)
    if n < v_larga:
        return None, 0.0
    pct_c = secuencia[-v_corta:].count("V") / v_corta
    pct_l = secuencia[-v_larga:].count("V") / v_larga
    dif = pct_c - pct_l
    if abs(dif) < 0.06:   # zona neutral
        return None, 0.0
    return ("V" if dif > 0 else "R"), min(1.0, abs(dif) * 5.0)


def _entropia_ord1(secuencia, ventana=30):
    """Entropía de Shannon de orden 1 sobre las últimas `ventana` velas.

    Devuelve un factor de penalización [0..1]: cuanto más desordenada la
    serie, más se encoge la confianza de los otros métodos.
    """
    reciente = secuencia[-ventana:] if len(secuencia) >= ventana else secuencia
    n = len(reciente)
    if n < 6:
        return 0.0  # sin penalización si no hay datos
    p = reciente.count("V") / n
    p = max(1e-9, min(1.0 - 1e-9, p))
    q = 1.0 - p
    h = -(p * math.log2(p) + q * math.log2(q))   # 0..1 (máx cuando p=0.5)
    # Si h > 0.95 bits → casi aleatoria → penalizar (0 = sin penalizar, 1 = max)
    return max(0.0, (h - 0.88) / 0.12)


def _momentum_puro(secuencia, ventana=5, minimo=3):
    """Método 6 — Momentum de corto plazo: detecta rachas claras recientes.

    Si las últimas `ventana` velas tienen >= `minimo` del mismo color,
    hay un momentum de corto plazo identificable y predecible.

    Casos:
    - 5 velas: 4-5 del mismo color → señal fuerte (continuación)
    - 4 velas: 4 del mismo color   → señal media
    - 3 velas seguidas al final    → señal ligera (puede revertir)

    Separado de _test_rachas porque este método considera TODA la ventana
    reciente, no solo la racha final.
    """
    n = len(secuencia)
    if n < ventana:
        return None, 0.0
    reciente = secuencia[-ventana:]
    cv = reciente.count("V")
    cr = reciente.count("R")
    # Dirección dominante
    dom = "V" if cv >= cr else "R"
    ratio = max(cv, cr) / ventana
    if ratio < minimo / ventana:
        return None, 0.0
    # Confianza basada en qué tan dominante es la dirección
    conf = (ratio - 0.5) * 2.0   # 0.0 → 0.5 → 1.0 (en ratio 0.5 → 0.75 → 1.0)
    conf = max(0.0, min(1.0, conf * 0.85))
    # Si las últimas 3 son la dirección opuesta → el momentum puede estar girando
    if ventana >= 4 and n >= 3:
        ultimas3 = secuencia[-3:]
        opuesta  = "R" if dom == "V" else "V"
        if ultimas3.count(opuesta) >= 2:
            conf *= 0.5   # penalizar: la ventana mayor sugiere una cosa pero las últimas 3 giran
    return dom, round(conf, 3)


def _zscore_winrate(secuencia, ventana_reciente: int = 20,
                    ventana_hist: int = 100) -> tuple:
    """
    Método 7 — Z-score del win-rate reciente vs histórico.

    Pregunta: ¿está el mercado en un régimen alcista o bajista estadísticamente
    anómalo respecto a lo que hemos visto en las últimas 100 velas?

    Z > +1.5 → sesgo verde anómalo → señal V
    Z < -1.5 → sesgo rojo anómalo  → señal R
    """
    n = len(secuencia)
    if n < ventana_hist + ventana_reciente:
        return None, 0.0

    hist     = secuencia[-(ventana_hist + ventana_reciente):-ventana_reciente]
    reciente = secuencia[-ventana_reciente:]

    if len(hist) < 10:
        return None, 0.0

    # Media y std del win-rate histórico por ventanas de tamaño ventana_reciente
    wr_hist_muestras = []
    paso = max(1, ventana_reciente // 2)
    for i in range(0, len(hist) - ventana_reciente + 1, paso):
        bloque = hist[i:i + ventana_reciente]
        wr_hist_muestras.append(bloque.count("V") / ventana_reciente)

    if len(wr_hist_muestras) < 3:
        return None, 0.0

    mu   = sum(wr_hist_muestras) / len(wr_hist_muestras)
    var  = sum((x - mu) ** 2 for x in wr_hist_muestras) / len(wr_hist_muestras)
    std  = max(0.01, math.sqrt(var))

    wr_actual = reciente.count("V") / ventana_reciente
    z = (wr_actual - mu) / std

    if z > 1.5:
        conf = min(0.85, 0.55 + (z - 1.5) * 0.08)
        return "V", round(conf, 3)
    if z < -1.5:
        conf = min(0.85, 0.55 + (abs(z) - 1.5) * 0.08)
        return "R", round(conf, 3)
    return None, 0.0


def _autocorrelacion_lag1(secuencia, ventana: int = 30) -> tuple:
    """
    Método 8 — Autocorrelación de lag-1.

    Mide si la serie binaria V/R tiende a autocorrelarse positivamente
    (seguir la misma dirección: tendencia) o negativamente (alternar: reversión).

    Autocorr > +0.15 → serie persistente (tendencia) → seguir dirección actual
    Autocorr < -0.15 → serie antipersistente (reversión) → anticipar cambio
    """
    reciente = secuencia[-ventana:]
    n = len(reciente)
    if n < 8:
        return None, 0.0

    # Codificar V=+1 R=-1 y calcular autocorrelación lag-1
    encoded = [1.0 if c == "V" else -1.0 for c in reciente]
    mu = sum(encoded) / n
    cov_lag1 = sum((encoded[i] - mu) * (encoded[i - 1] - mu) for i in range(1, n))
    var_t    = sum((x - mu) ** 2 for x in encoded)

    if var_t < 1e-9:
        return None, 0.0

    autocorr = cov_lag1 / var_t
    ultimo    = reciente[-1]

    if autocorr > 0.15:
        # Persistente → continuar la dirección actual
        conf = min(0.82, 0.52 + abs(autocorr) * 1.5)
        return ultimo, round(conf, 3)
    if autocorr < -0.15:
        # Antipersistente → revertir
        conf = min(0.82, 0.52 + abs(autocorr) * 1.5)
        dir_rev = "R" if ultimo == "V" else "V"
        return dir_rev, round(conf, 3)
    return None, 0.0


def analizar(secuencia, umbral=0.60):
    """Combina los ocho métodos por voto ponderado (v2: +Z-score +Autocorr).

    Devuelve dict con: direccion ('V'/'R'/None), confianza (0..1),
    consenso (cuántos métodos coinciden 0..8) y detalle por método.

    Umbral adaptativo: si entropía > 0.80 → umbral sube a 0.68 automáticamente.
    """
    d_m, c_m, _ev = _markov_multiorden(secuencia)
    d_c, c_c      = _chi_cuadrado(secuencia)
    d_r, c_r      = _test_rachas(secuencia)
    d_e, c_e      = _ewma_ligera(secuencia)
    d_p, c_p      = _momentum_puro(secuencia)
    d_z, c_z      = _zscore_winrate(secuencia)
    d_a, c_a      = _autocorrelacion_lag1(secuencia)

    # Penalización por entropía alta (serie muy desordenada)
    penaliz = _entropia_ord1(secuencia)
    c_m = max(0.0, c_m * (1.0 - penaliz * 0.5))
    c_c = max(0.0, c_c * (1.0 - penaliz * 0.5))
    c_r = max(0.0, c_r * (1.0 - penaliz * 0.4))
    c_e = max(0.0, c_e * (1.0 - penaliz * 0.3))
    c_p = max(0.0, c_p * (1.0 - penaliz * 0.4))
    c_z = max(0.0, c_z * (1.0 - penaliz * 0.3))
    c_a = max(0.0, c_a * (1.0 - penaliz * 0.5))

    # Umbral adaptativo: mercado ruidoso → exigir más
    umbral_efectivo = max(umbral, 0.68 if penaliz > 0.70 else umbral)

    detalle = {
        "markov":        {"dir": d_m, "conf": round(c_m, 3)},
        "chi2":          {"dir": d_c, "conf": round(c_c, 3)},
        "rachas":        {"dir": d_r, "conf": round(c_r, 3)},
        "ewma":          {"dir": d_e, "conf": round(c_e, 3)},
        "momentum_puro": {"dir": d_p, "conf": round(c_p, 3)},
        "zscore_wr":     {"dir": d_z, "conf": round(c_z, 3)},
        "autocorr_lag1": {"dir": d_a, "conf": round(c_a, 3)},
        "entropia_penaliz": round(penaliz, 3),
        "umbral_efectivo":  round(umbral_efectivo, 3),
    }

    # Voto ponderado por confianza de cada método (8 métodos)
    puntos = {"V": 0.0, "R": 0.0}
    for direccion, conf in ((d_m, c_m), (d_c, c_c), (d_r, c_r), (d_e, c_e),
                            (d_p, c_p), (d_z, c_z), (d_a, c_a)):
        if direccion in ("V", "R"):
            puntos[direccion] += conf
    suma = puntos["V"] + puntos["R"]
    if suma == 0:
        return {"direccion": None, "confianza": 0.0, "consenso": 0,
                "candidata": "V", "detalle": detalle}

    direccion = "V" if puntos["V"] >= puntos["R"] else "R"
    confianza = puntos[direccion] / suma
    consenso  = sum(1 for d in (d_m, d_c, d_r, d_e, d_p, d_z, d_a) if d == direccion)

    # Actuar si mayoría de 8 métodos coincide (>=4) y confianza supera umbral adaptativo
    actuar = consenso >= 4 and confianza >= umbral_efectivo
    return {
        "direccion": direccion if actuar else None,
        "candidata": direccion,
        "confianza": round(confianza, 3),
        "consenso":  consenso,
        "total_met": 8,
        "detalle":   detalle,
    }


def resumen(secuencia, idioma="es"):
    r = analizar(secuencia)
    tot = r.get("total_met", 8)
    if idioma == "en":
        if not r["direccion"]:
            return (f"No strong consensus yet ({r['consenso']}/{tot} methods agree, "
                    f"confidence {int(r['confianza'] * 100)}%). I'd rather wait, sir.")
        d = "rise (green)" if r["direccion"] == "V" else "fall (red)"
        return (f"Eight-method consensus: {r['consenso']}/{tot} point to {d} "
                f"with {int(r['confianza'] * 100)}% confidence, sir.")
    if not r["direccion"]:
        return (f"Aún no hay consenso fuerte ({r['consenso']}/{tot} métodos, "
                f"confianza {int(r['confianza'] * 100)}%). Prefiero esperar, señor.")
    d = "subida (verde)" if r["direccion"] == "V" else "bajada (roja)"
    return (f"Consenso de {tot} métodos ({r['consenso']}/{tot} votantes) indica {d} "
            f"con {int(r['confianza'] * 100)}% de confianza, señor.")
