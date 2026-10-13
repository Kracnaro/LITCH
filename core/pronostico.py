"""Módulo de pronóstico avanzado de Litch — series temporales + Benford.

Cuatro análisis complementarios que detectan si la serie de velas tiene
estructura estadística explotable más allá del puro azar:

  1. Entropía de Shannon (orden 2):
       Mide el desorden de la serie. Si la entropía es ≥ 0.95 bits, la
       secuencia es casi aleatoria y conviene no operar. Si es menor, hay
       patrones reales.

  2. Ley de Benford adaptada — distribución de rachas:
       En una secuencia binaria aleatoria justa las rachas siguen P(k) = 0.5^k.
       Si las rachas largas son MÁS frecuentes de lo esperado → momentum (la
       tendencia persiste). Si son MENOS frecuentes → reversión a la media.
       Esta es la adaptación de la Ley de Benford para datos binarios: busca
       desviaciones de la distribución "natural" esperada.

  3. Función de Autocorrelación (ACF) hasta lag 8:
       Detecta ciclos: si la vela de hace k pasos correlaciona con la actual,
       hay una periodicidad de longitud k que se puede explotar.

  4. EWMA cruzada (corta α=0.30 vs larga α=0.08):
       Tendencia ponderada exponencialmente. Cuando la media corta supera a
       la larga → sesgo alcista. Igual que el MACD pero en versión binaria.

El módulo expone un voto unificado (V/R/None) + confianza para integrarse
en la fusión bayesiana como cuarto método independiente.

Honestidad: estas herramientas detectan ESTRUCTURA PASADA, no el futuro.
"""
import math

import numpy as np


# ─── 1. Entropía de Shannon condicional ──────────────────────────────────────

def entropia_shannon(secuencia, orden=2):
    """Entropía condicional H(X_t | X_{t-1}, X_{t-2}) en bits.

    Rango: 0 = perfectamente predecible · 1 = máximo desorden (moneda justa).
    Con orden=2 mide cuánto predicen las últimas 2 velas a la siguiente.
    """
    n = len(secuencia)
    if n < orden + 4:
        return 1.0
    cuentas: dict = {}
    for i in range(n - orden):
        ctx = "".join(secuencia[i: i + orden])
        sig = secuencia[i + orden]
        bloque = cuentas.setdefault(ctx, {"V": 0, "R": 0, "tot": 0})
        bloque[sig] = bloque.get(sig, 0) + 1
        bloque["tot"] += 1

    total = n - orden
    h = 0.0
    for bloque in cuentas.values():
        p_ctx = bloque["tot"] / total
        for s in ("V", "R"):
            cnt = bloque.get(s, 0)
            if cnt > 0:
                p_s = cnt / bloque["tot"]
                h -= p_ctx * p_s * math.log2(p_s)
    return round(min(1.0, h), 4)


# ─── 2. Ley de Benford adaptada — distribución geométrica de rachas ──────────

def _rachas(secuencia):
    """Extrae las longitudes de todas las rachas de la secuencia."""
    if not secuencia:
        return []
    resultado = []
    racha = 1
    for i in range(1, len(secuencia)):
        if secuencia[i] == secuencia[i - 1]:
            racha += 1
        else:
            resultado.append(racha)
            racha = 1
    resultado.append(racha)
    return resultado


def benford_rachas(secuencia, ventana=80):
    """Compara la distribución real de rachas con P(k) = 0.5^k (Benford binario).

    Devuelve ('momentum'|'reversion'|'neutro', score 0..1, media_real, media_esp).
    momentum  → rachas largas más frecuentes de lo esperado → tendencia persiste.
    reversion → rachas cortas excesivas → la serie tiende a alternar.
    """
    reciente = list(secuencia[-ventana:]) if len(secuencia) > ventana else list(secuencia)
    rachas = _rachas(reciente)
    if len(rachas) < 6:
        return "neutro", 0.0, 0.0, 2.0

    media_real    = sum(rachas) / len(rachas)
    media_teorica = 2.0   # E[Geom(0.5)] = 1/0.5 = 2
    var_real      = float(np.var(rachas)) if len(rachas) > 1 else 0.0
    # var teórica Geom(0.5) = (1-0.5)/0.5² = 2.0
    var_teorica   = 2.0

    # z-score de la media muestral
    se = math.sqrt(var_teorica / len(rachas)) if len(rachas) > 0 else 1.0
    z  = (media_real - media_teorica) / (se + 1e-9)

    score = min(1.0, abs(z) / 2.5)   # z=2.5 → score≈1 (≈p<0.02)

    if score < 0.20:
        return "neutro", 0.0, round(media_real, 2), media_teorica
    if z > 0:
        return "momentum", round(score, 3), round(media_real, 2), media_teorica
    return "reversion", round(score, 3), round(media_real, 2), media_teorica


def _voto_benford(secuencia):
    """Convierte el análisis Benford en voto (dir, confianza)."""
    sesgo, score, *_ = benford_rachas(secuencia)
    if sesgo == "neutro" or score < 0.20:
        return None, 0.0
    ultimo = secuencia[-1] if secuencia else "V"
    if sesgo == "momentum":
        return ultimo, score * 0.65           # continúa la tendencia
    return ("R" if ultimo == "V" else "V"), score * 0.65   # reversión


# ─── 3. Función de Autocorrelación (ACF) ─────────────────────────────────────

def acf(secuencia, max_lag=8):
    """Autocorrelación ρ(k) para lags 1..max_lag sobre serie binaria V=1/R=0.

    Devuelve lista de (lag, rho). Valores |rho| > 0.12 son relevantes.
    """
    s = np.array([1.0 if c == "V" else 0.0 for c in secuencia], dtype=float)
    if len(s) < max_lag + 6:
        return []
    s -= s.mean()
    var = float(s @ s)
    if var < 1e-9:
        return []
    return [(k, round(float((s[:-k] @ s[k:]) / var), 4)) for k in range(1, max_lag + 1)]


def _voto_acf(secuencia, max_lag=8, umbral=0.11):
    """Usa la autocorrelación más intensa para emitir un voto.

    Umbral reducido a 0.11 (antes 0.12) para detectar ciclos más sutiles.
    Mínimo de datos reducido a max_lag+8 (antes +12) para activarse antes.
    Usa ventana de 100 velas recientes (antes 120) para ser más reactivo.
    """
    n = len(secuencia)
    if n < max_lag + 8:   # antes +12, ahora +8: se activa más rápido
        return None, 0.0
    # Ventana de 100 datos recientes (antes 120) — más reactivo a cambios
    muestra = list(secuencia[-100:]) if n > 100 else list(secuencia)
    correlaciones = acf(muestra, max_lag)
    if not correlaciones:
        return None, 0.0
    lag_max, rho_max = max(correlaciones, key=lambda x: abs(x[1]))
    if abs(rho_max) < umbral:
        return None, 0.0
    if lag_max + 1 > n:
        return None, 0.0
    estado_lag = secuencia[-(lag_max + 1)]
    if rho_max > 0:
        return estado_lag, abs(rho_max) * 0.78   # leve aumento de confianza
    return ("R" if estado_lag == "V" else "V"), abs(rho_max) * 0.78


# ─── 4. EWMA cruzada (MACD binario) ──────────────────────────────────────────

def _ewma(secuencia, alpha):
    """Exponential Weighted Moving Average de la serie binaria (V=1, R=0).

    Inicializa desde la tasa histórica real (no siempre 0.5) para que el
    primer valor refleje el sesgo previo de la serie.
    """
    if not secuencia:
        return 0.5
    # Inicializar desde la tasa base histórica (evita el sesgo de arranque con 0.5)
    base_rate = secuencia.count("V") / len(secuencia)
    val = base_rate
    for c in secuencia:
        val = alpha * (1.0 if c == "V" else 0.0) + (1.0 - alpha) * val
    return val


def _voto_ewma(secuencia, alpha_corta=0.30, alpha_larga=0.08, zona_neutra=0.040):
    """Cruce EWMA: media corta > larga → alcista; < larga → bajista.

    zona_neutra reducida a 0.040 (antes 0.045) para detectar cruces
    más pequeños — útil en mercados con sesgo leve pero consistente.
    """
    if len(secuencia) < 10:
        return None, 0.0
    ema_c = _ewma(secuencia, alpha_corta)
    ema_l = _ewma(secuencia, alpha_larga)
    dif = ema_c - ema_l
    if abs(dif) < zona_neutra:
        return None, 0.0
    conf = min(1.0, abs(dif) * 5.5) * 0.72   # ligeramente más sensible
    return ("V" if dif > 0 else "R"), round(conf, 3)


# ─── 5. Regresión local ponderada (LOWESS simplificado) ─────────────────────

def _voto_lowess(secuencia, ventana: int = 20) -> tuple:
    """Ajuste local de tendencia con pesos Gaussianos (distancia a punto actual).

    Asigna peso mayor a las velas más recientes vía kernel gaussiano:
        w_i = exp(-0.5 * (i / sigma)^2),  sigma = ventana/3

    Ajusta una recta (OLS ponderado) sobre las últimas `ventana` velas y
    usa su pendiente para detectar tendencia:
      pendiente > +0.015  → V, conf = min(1.0, slope * 20)
      pendiente < -0.015  → R
    """
    n = len(secuencia)
    if n < ventana:
        return None, 0.0
    vals = np.array([1.0 if c == "V" else 0.0 for c in secuencia[-ventana:]])
    xs   = np.arange(ventana, dtype=float)
    sigma = ventana / 3.0
    ws    = np.exp(-0.5 * ((xs - (ventana - 1)) / sigma) ** 2)
    ws   /= ws.sum()
    # OLS ponderado: beta = (X'WX)^-1 X'Wy
    xbar = (ws * xs).sum()
    ybar = (ws * vals).sum()
    cov  = (ws * (xs - xbar) * (vals - ybar)).sum()
    var  = (ws * (xs - xbar) ** 2).sum()
    if var < 1e-9:
        return None, 0.0
    slope = cov / var
    if abs(slope) < 0.015:
        return None, 0.0
    conf = float(min(1.0, abs(slope) * 18.0)) * 0.70   # cap confianza en 0.70
    return ("V" if slope > 0 else "R"), round(conf, 3)


# ─── 6. Momentum multifractal (3 escalas temporales) ────────────────────────

def _voto_fractal(secuencia) -> tuple:
    """Detecta momentum que se mantiene consistente en 3 escalas de tiempo.

    Escala corta  (5 velas):  WR > 0.70 → V,  < 0.30 → R
    Escala media  (12 velas): WR > 0.65 → V,  < 0.35 → R
    Escala larga  (25 velas): WR > 0.58 → V,  < 0.42 → R

    Alineamiento triple → conf base 0.72; doble → 0.52; simple → None
    Lógica: si el sesgo existe en las 3 escalas, es más probable que sea
    estructura real y no ruido de corto plazo.
    """
    n = len(secuencia)
    if n < 25:
        return None, 0.0

    def _wr(sec, k):
        tail = sec[-k:]
        v    = sum(1 for c in tail if c == "V")
        return v / k

    def _dir_escala(wr_, lo, hi):
        if wr_ > hi:   return "V"
        if wr_ < lo:   return "R"
        return None

    wr5  = _wr(secuencia, 5)
    wr12 = _wr(secuencia, 12)
    wr25 = _wr(secuencia, 25)

    d5  = _dir_escala(wr5,  0.30, 0.70)
    d12 = _dir_escala(wr12, 0.35, 0.65)
    d25 = _dir_escala(wr25, 0.42, 0.58)

    dirs = [d for d in (d5, d12, d25) if d is not None]
    if not dirs:
        return None, 0.0
    v_count = dirs.count("V")
    r_count = dirs.count("R")
    if v_count == r_count:
        return None, 0.0  # señales contradictorias → sin acción
    ganador = "V" if v_count > r_count else "R"
    acuerdo = max(v_count, r_count)
    conf_base = {3: 0.72, 2: 0.52, 1: 0.38}[acuerdo]
    # Bonus por extremo de la escala corta
    extremo_c = abs(wr5 - 0.5)
    conf = min(1.0, conf_base + extremo_c * 0.20)
    return ganador, round(conf, 3)


# ─── Motor integrado ──────────────────────────────────────────────────────────

def analizar(secuencia):
    """Combina los 6 métodos de pronóstico avanzado en un voto único (v3).

    Retorna dict:
      direccion  : 'V' / 'R' / None  (None si no hay ventaja clara)
      candidata  : dirección de mayor peso (aunque no supere el umbral)
      confianza  : 0..1
      consenso   : cuántos de los 5 votantes (ex-entropía) apuntan a la misma dirección
      entropia   : 0..1  (1 = máximo desorden)
      predecible : True si la entropía indica estructura estadística real
      detalle    : desglose por método
    """
    h = entropia_shannon(secuencia)
    predecible = h < 0.94

    d_b, c_b = _voto_benford(secuencia)
    d_a, c_a = _voto_acf(secuencia)
    d_e, c_e = _voto_ewma(secuencia)
    d_l, c_l = _voto_lowess(secuencia)     # ← nuevo v3
    d_f, c_f = _voto_fractal(secuencia)    # ← nuevo v3

    # Penalizar confianza si la serie es casi aleatoria
    penaliz = max(0.0, (h - 0.82) / 0.12) if h > 0.82 else 0.0
    c_b = max(0.0, c_b * (1.0 - penaliz * 0.6))
    c_a = max(0.0, c_a * (1.0 - penaliz * 0.6))
    c_e = max(0.0, c_e * (1.0 - penaliz * 0.4))
    c_l = max(0.0, c_l * (1.0 - penaliz * 0.5))
    c_f = max(0.0, c_f * (1.0 - penaliz * 0.3))   # fractal más robusto al ruido

    detalle = {
        "benford_rachas": {"dir": d_b, "conf": round(c_b, 3)},
        "acf":            {"dir": d_a, "conf": round(c_a, 3)},
        "ewma":           {"dir": d_e, "conf": round(c_e, 3)},
        "lowess":         {"dir": d_l, "conf": round(c_l, 3)},
        "fractal":        {"dir": d_f, "conf": round(c_f, 3)},
    }

    puntos = {"V": 0.0, "R": 0.0}
    for d, c in ((d_b, c_b), (d_a, c_a), (d_e, c_e), (d_l, c_l), (d_f, c_f)):
        if d in ("V", "R"):
            puntos[d] += c

    suma = puntos["V"] + puntos["R"]
    candidata = "V" if puntos.get("V", 0) >= puntos.get("R", 0) else "R"

    if suma < 0.01 or not predecible:
        return {
            "direccion": None, "candidata": candidata,
            "confianza": 0.0, "consenso": 0,
            "entropia": h, "predecible": predecible,
            "detalle": detalle,
        }

    direccion = candidata
    confianza = puntos[direccion] / suma
    consenso  = sum(1 for d in (d_b, d_a, d_e, d_l, d_f) if d == direccion)
    # Con 5 votantes: mayoría = >=3; señal absoluta mínima para no operar en empate
    actuar    = confianza >= 0.60 and consenso >= 3 and puntos[direccion] >= 0.28

    return {
        "direccion":  direccion if actuar else None,
        "candidata":  direccion,
        "confianza":  round(confianza, 3),
        "consenso":   consenso,
        "total_met":  5,
        "entropia":   h,
        "predecible": predecible,
        "detalle":    detalle,
    }


def resumen_texto(secuencia, idioma="es"):
    """Resumen hablado del análisis de pronóstico avanzado."""
    r    = analizar(secuencia)
    h_pct = int(r["entropia"] * 100)
    tot   = r.get("total_met", 5)

    if idioma == "en":
        pred_txt = "structured" if r["predecible"] else "near-random"
        if not r["direccion"]:
            return (f"Series entropy: {h_pct}% ({pred_txt}). "
                    f"Advanced forecast methods disagree — better to wait, sir.")
        lado = "rise (green)" if r["direccion"] == "V" else "fall (red)"
        return (f"Series entropy {h_pct}% ({pred_txt}). "
                f"Advanced forecast: {lado}, {int(r['confianza']*100)}% confidence, "
                f"{r['consenso']}/{tot} advanced methods agree, sir.")

    pred_txt = "con estructura" if r["predecible"] else "casi aleatoria"
    if not r["direccion"]:
        return (f"Entropía de la serie: {h_pct}% ({pred_txt}). "
                f"Los métodos avanzados no coinciden — mejor esperar, señor.")
    lado = "subida (verde)" if r["direccion"] == "V" else "bajada (roja)"
    return (f"Entropía {h_pct}% ({pred_txt}). "
            f"Pronóstico avanzado: {lado}, {int(r['confianza']*100)}% de confianza, "
            f"{r['consenso']}/{tot} métodos avanzados coinciden, señor.")
