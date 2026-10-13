"""
Indicadores técnicos clásicos de trading adaptados a series binarias V/R.
Implementación 100% NumPy — compatible con Python 3.14.

Cada vela V=+1, R=-1. La "cotización sintética" es el cumsum de esos retornos.

Indicadores:
  RSI            — Relative Strength Index         (sobrecompra / sobreventa)
  MACD           — Moving Average Convergence/Div  (momentum y cruce de señal)
  BB             — Bollinger Bands                 (extremos estadísticos)
  STOCH          — Stochastic Oscillator %K/%D     (velocidad de cambio)
  WR             — Williams %R                     (nivel respecto a rango reciente)
  ATR            — Average True Range sintético    (volatilidad)
  MOM            — Momentum puro                   (fuerza de la tendencia)
  ROC            — Rate of Change                  (aceleración porcentual)
  ADX            — Average Directional Index       (fuerza de tendencia, 0-100)
  OBV            — On-Balance "Volume" equivalente (flujo de mercado)
  HURST          — Exponente de Hurst R/S          (fractalidad de la serie)
  ENTROPY        — Entropía de permutación         (complejidad / predecibilidad)
  RACHA          — Longitud y dirección de racha   (momentum crudo)
  EMA_TRIPLE     — Triple Cruce EMA 4-18-40        (Equiti / tendencia fuerte)
  VWAP           — Volume-Weighted Avg Price sint. (DINAMITA GRIZZLY / zona de valor)
  RSI_DIV        — Divergencia RSI-precio          (señal de agotamiento)
  REGIMEN        — Clasificación de mercado        (trending / ranging / chaotic)
  RVI            — Relative Vigor Index            (v2) dirección del momentum
  CCI            — Commodity Channel Index         (v2) divergencias de ciclo
  FISHER         — Fisher Transform del RSI        (v2) señales de cruce extremo
  SUPERTREND     — Supertrend sintético ATR-based  (v3) seguimiento de tendencia
  KELTNER        — Keltner Channels (EMA±ATR)      (v3) bandas resistentes al ruido
  ELDER_RAY      — Bull/Bear Power (A. Elder)      (v3) fuerza compradora/vendedora
  CMO            — Chande Momentum Oscillator      (v3) momentum más sensible que RSI
  VOLUME_PROFILE — Value Area sintético            (v3) zonas institucionales

La función evaluar_senal() combina todo en un único voto con dirección
y confianza, listo para el motor de consenso de 7 métodos de Litch.

Basado en técnicas de:
  - Appel 1979 (MACD)
  - Wilder 1978 (RSI, ATR, ADX)
  - Bollinger 1993 (Bandas de Bollinger)
  - Lane 1950s (Stochastic)
  - Williams 1973 (%R)
  - Hurst 1951 (exponente R/S)
  - Ehlers 2004 (Fisher Transform, MESA)
  - Lambert 1980 (CCI)
  - Equiti Scalping Guide (EMA Triple Cruce 4-18-40, SMA 200)
  - DINAMITA GRIZZLY (Volume Profile, VWAP, market structure)
  - Kakushadze & Serur 2018 (151 Estrategias — momentum, mean-reversion)
  - Francisca Serrano (gestión de riesgo, disciplina operativa)
"""

import numpy as np

# ─── Primitivas de conversión ────────────────────────────────────────────────

def _ret(sec) -> np.ndarray:
    """['V','R',...] → [+1.0, -1.0, ...]"""
    return np.array([1.0 if c == 'V' else -1.0 for c in sec])


def _precio(sec) -> np.ndarray:
    """Precio sintético = cumsum de retornos."""
    return np.cumsum(_ret(sec))


# ─── EMA y SMA ───────────────────────────────────────────────────────────────

def ema(arr: np.ndarray, p: int) -> np.ndarray:
    """Exponential Moving Average estándar."""
    arr = np.asarray(arr, dtype=float)
    k   = 2.0 / (p + 1)
    out = np.empty(len(arr))
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = arr[i] * k + out[i - 1] * (1.0 - k)
    return out


def sma(arr: np.ndarray, p: int) -> np.ndarray:
    """Simple Moving Average."""
    arr = np.asarray(arr, dtype=float)
    return np.convolve(arr, np.ones(p) / p, mode='valid')


def _wilder(arr: np.ndarray, p: int) -> np.ndarray:
    """Suavizado de Wilder (EMA con α=1/p)."""
    arr = np.asarray(arr, dtype=float)
    out = np.empty(len(arr))
    if len(arr) < p:
        out[:] = arr.mean()
        return out
    out[:p] = arr[:p].mean()
    for i in range(p, len(arr)):
        out[i] = out[i - 1] + (arr[i] - out[i - 1]) / p
    return out


# ─── RSI de Wilder ───────────────────────────────────────────────────────────

def rsi(sec, p: int = 14) -> float | None:
    """RSI (0-100). >70 sobrecomprado → posible BAJA. <30 sobrevendido → posible SUBE."""
    if len(sec) < p + 2:
        return None
    r = _ret(sec)
    g = np.where(r > 0, r, 0.0)
    l = np.where(r < 0, -r, 0.0)
    ag = float(g[:p].mean())
    al = float(l[:p].mean())
    for i in range(p, len(r)):
        ag = (ag * (p - 1) + g[i]) / p
        al = (al * (p - 1) + l[i]) / p
    if al < 1e-9:
        return 100.0
    return float(100.0 - 100.0 / (1.0 + ag / al))


# ─── MACD ────────────────────────────────────────────────────────────────────

def macd(sec, fast: int = 5, slow: int = 10, signal: int = 3):
    """MACD con períodos cortos, óptimos para series binarias.
    Devuelve (linea, señal, histograma). Histograma > 0 → momentum alcista."""
    pr = _precio(sec)
    if len(pr) < slow + signal:
        return None, None, None
    ef  = ema(pr, fast)
    es  = ema(pr, slow)
    ml  = ef - es
    sl  = ema(ml, signal)
    return float(ml[-1]), float(sl[-1]), float(ml[-1] - sl[-1])


# ─── Bollinger Bands ─────────────────────────────────────────────────────────

def bollinger(sec, p: int = 20, dev: float = 2.0):
    """Bollinger Bands. pos∈[0,1]: 0=banda inferior, 1=banda superior.
    Retorna (sup, mid, inf, posicion_normalizada)."""
    pr = _precio(sec)
    if len(pr) < p:
        return None, None, None, None
    w   = pr[-p:]
    mid = float(w.mean())
    std = float(w.std())
    sup = mid + dev * std
    inf = mid - dev * std
    pos = float(np.clip((pr[-1] - inf) / (sup - inf + 1e-9), 0.0, 1.0))
    return sup, mid, inf, pos


# ─── Stochastic %K/%D ────────────────────────────────────────────────────────

def stochastic(sec, pk: int = 14, pd: int = 3):
    """Stochastic %K y %D. >80 sobrecomprado, <20 sobrevendido."""
    pr = _precio(sec)
    if len(pr) < pk + pd:
        return None, None
    k_vals = []
    for i in range(pd, len(pr) + 1):
        v = pr[max(0, i - pk):i]
        lo, hi = v.min(), v.max()
        k_vals.append(100.0 * (pr[i - 1] - lo) / (hi - lo + 1e-9))
    k = float(k_vals[-1])
    d = float(np.mean(k_vals[-pd:]))
    return k, d


# ─── Williams %R ─────────────────────────────────────────────────────────────

def williams_r(sec, p: int = 14) -> float | None:
    """Williams %R. > -20 sobrecomprado → BAJA. < -80 sobrevendido → SUBE."""
    pr = _precio(sec)
    if len(pr) < p:
        return None
    v  = pr[-p:]
    hi, lo = v.max(), v.min()
    return float(-100.0 * (hi - pr[-1]) / (hi - lo + 1e-9))


# ─── ATR sintético ────────────────────────────────────────────────────────────

def atr(sec, p: int = 14) -> float | None:
    """Volatilidad media de la secuencia (std de retornos en ventana p)."""
    if len(sec) < p:
        return None
    return float(_ret(sec[-p:]).std())


# ─── Momentum ────────────────────────────────────────────────────────────────

def momentum(sec, p: int = 5) -> float | None:
    """Precio[t] − Precio[t−p]. >0 → tendencia alcista."""
    pr = _precio(sec)
    if len(pr) < p + 1:
        return None
    return float(pr[-1] - pr[-p - 1])


# ─── Rate of Change ───────────────────────────────────────────────────────────

def roc(sec, p: int = 10) -> float | None:
    """ROC (%): variación porcentual respecto a N períodos atrás."""
    pr = _precio(sec)
    if len(pr) < p + 1:
        return None
    base = pr[-p - 1]
    return float(100.0 * (pr[-1] - base) / (abs(base) + 1e-9))


# ─── ADX simplificado ────────────────────────────────────────────────────────

def adx(sec, p: int = 14) -> float | None:
    """ADX (0-100). >25 = tendencia real. <20 = sin tendencia (rango)."""
    if len(sec) < p * 2:
        return None
    r    = _ret(sec)
    dm_p = np.where(r > 0, r, 0.0)
    dm_m = np.where(r < 0, -r, 0.0)
    atr_ = np.abs(r)
    sa   = _wilder(atr_, p)
    sp   = _wilder(dm_p, p)
    sm   = _wilder(dm_m, p)
    dip  = 100.0 * sp / (sa + 1e-9)
    dim  = 100.0 * sm / (sa + 1e-9)
    dx   = 100.0 * np.abs(dip - dim) / (dip + dim + 1e-9)
    return float(_wilder(dx, p)[-1])


# ─── OBV equivalente ─────────────────────────────────────────────────────────

def obv(sec, p: int = 10) -> float | None:
    """Tendencia del flujo: pendiente del OBV en las últimas p velas."""
    if len(sec) < p:
        return None
    v_obv = np.cumsum(_ret(sec[-p:]))
    x     = np.arange(len(v_obv), dtype=float)
    slope = float(np.polyfit(x, v_obv, 1)[0])
    return slope


# ─── Exponente de Hurst ───────────────────────────────────────────────────────

def hurst(sec, min_p: int = 4) -> float | None:
    """Exponente de Hurst R/S.
    H > 0.55 → persistencia (tendencia continúa).
    H < 0.45 → anti-persistencia (reversión a la media).
    H ≈ 0.50 → aleatoriedad pura."""
    if len(sec) < 20:
        return None
    ts = _precio(sec).astype(float)
    N  = len(ts)
    lags, rs = [], []
    lag = min_p
    while lag <= N // 2:
        chunks = [ts[i:i + lag] for i in range(0, N - lag + 1, lag)]
        rs_vals = []
        for c in chunks:
            c = c - c.mean()
            cumdev = np.cumsum(c)
            R = cumdev.max() - cumdev.min()
            S = c.std()
            if S > 1e-9:
                rs_vals.append(R / S)
        if rs_vals:
            lags.append(np.log(lag))
            rs.append(np.log(np.mean(rs_vals)))
        lag = int(lag * 1.5) + 1
    if len(lags) < 3:
        return None
    h = float(np.polyfit(lags, rs, 1)[0])
    return float(np.clip(h, 0.0, 1.0))


# ─── VWAP sintético (DINAMITA GRIZZLY) ───────────────────────────────────────

def vwap_sintetico(sec, p: int = 20):
    """
    VWAP sintético sobre la serie binaria V/R.
    Asigna "volumen" proporcional a la volatilidad local (proxy institucional).

    Devuelve (posicion_relativa, bias):
      posicion_relativa : float en [-1, 1]. >0 precio arriba del VWAP (alcista).
      bias              : 'V' si precio arriba del VWAP, 'R' si abajo, None si neutral.

    Basado en DINAMITA GRIZZLY (J.M. Martín Núñez, Traders Magazine 2020):
    "El VWAP te dice el precio más justo. Precios por encima del VWAP son caros
    (zona de distribución), precios por debajo son baratos (zona de acumulación)."
    """
    if len(sec) < p + 2:
        return 0.0, None
    pr  = _precio(sec)
    ret = _ret(sec)
    # Proxy de volumen: volatilidad local (cuanto más volátil, más participación)
    vol = np.abs(ret)
    pr_w = pr[-p:]
    vl_w = vol[-p:]
    tot_vol = vl_w.sum()
    if tot_vol < 1e-9:
        return 0.0, None
    vwap_val = float((pr_w * vl_w).sum() / tot_vol)
    precio_actual = float(pr[-1])
    rango = float(pr_w.max() - pr_w.min()) or 1.0
    posicion = float(np.clip((precio_actual - vwap_val) / rango, -1.0, 1.0))
    bias = "V" if posicion > 0.08 else ("R" if posicion < -0.08 else None)
    return posicion, bias


# ─── Triple Cruce EMA (Equiti Scalping Guide) ────────────────────────────────

def ema_triple_cross(sec, p1: int = 4, p2: int = 18, p3: int = 40):
    """
    Triple Cruce de la Muerte / Vida — EMAs 4-18-40.
    Basado en Guía Equiti Scalping (Equiti Distrito Financiero).

    Señal alcista: EMA4 > EMA18 > EMA40 con separación creciente.
    Señal bajista: EMA4 < EMA18 < EMA40 con separación creciente.

    Devuelve (direccion, fuerza_0_1) o (None, 0.0) si no hay alineación clara.
    La 'fuerza' refleja la separación relativa entre las EMAs.
    """
    if len(sec) < p3 + 2:
        return None, 0.0
    pr = _precio(sec)
    e1 = float(ema(pr, p1)[-1])
    e2 = float(ema(pr, p2)[-1])
    e3 = float(ema(pr, p3)[-1])
    rango = abs(e1 - e3) or 1e-9
    sep_norm = float(rango / (abs(e3) + 1e-9))

    if e1 > e2 > e3:
        return "V", float(np.clip(sep_norm * 10, 0.0, 1.0))
    if e1 < e2 < e3:
        return "R", float(np.clip(sep_norm * 10, 0.0, 1.0))
    return None, 0.0


# ─── Divergencia RSI ─────────────────────────────────────────────────────────

def rsi_divergencia(sec, ventana: int = 10) -> str | None:
    """
    Detecta divergencia entre el precio sintético y el RSI.

    Divergencia alcista: precio hace mínimo más bajo pero RSI hace mínimo más alto
    → señal de agotamiento bajista, probable rebote SUBE.

    Divergencia bajista: precio hace máximo más alto pero RSI hace máximo más bajo
    → señal de agotamiento alcista, probable caída BAJA.

    Devuelve 'V' (alcista), 'R' (bajista) o None.
    """
    if len(sec) < ventana * 2 + 14:
        return None
    # Calcular RSI en dos ventanas recientes
    r1 = rsi(sec[:-ventana])
    r2 = rsi(sec)
    if r1 is None or r2 is None:
        return None
    pr  = _precio(sec)
    pr1 = float(pr[-ventana - 1])
    pr2 = float(pr[-1])
    # Divergencia alcista: precio baja pero RSI sube
    if pr2 < pr1 and r2 > r1 + 3:
        return "V"
    # Divergencia bajista: precio sube pero RSI baja
    if pr2 > pr1 and r2 < r1 - 3:
        return "R"
    return None


# ─── Clasificación de régimen de mercado ────────────────────────────────────

def regimen_mercado(sec, p: int = 14,
                    _adx=None, _hurst=None, _ep=None) -> str:
    """
    Clasifica el mercado en uno de tres regímenes para filtrar señales.

    - "trending"  : ADX > 25 y Hurst > 0.52 → operar en la dirección del momentum
    - "ranging"   : ADX < 20 y Hurst < 0.52 → operar reversión (BB extremos)
    - "chaotic"   : entropía > 0.88 → NO OPERAR (mercado impredecible)

    Acepta valores pre-computados (_adx, _hurst, _ep) para evitar cálculos
    duplicados cuando evaluar_senal() ya los calculó.
    """
    if len(sec) < max(p * 2, 20):
        return "neutral"
    adx_v = _adx if _adx is not None else adx(sec, p)
    h_v   = _hurst if _hurst is not None else hurst(sec)
    ep_v  = _ep  if _ep  is not None else entropia_perm(sec)

    if ep_v is not None and ep_v > 0.90:
        return "chaotic"
    if adx_v is not None and adx_v > 25 and (h_v is None or h_v > 0.50):
        return "trending"
    if adx_v is not None and adx_v < 20:
        return "ranging"
    return "neutral"


# ─── Entropía de permutación ─────────────────────────────────────────────────

def entropia_perm(sec, orden: int = 3) -> float | None:
    """Entropía de permutación (0=predecible, 1=caótico).
    Si < 0.7 → hay patrones explotables."""
    pr = _precio(sec)
    if len(pr) < orden + 4:
        return None
    n_patrones = {}
    fact_orden = 1
    for i in range(1, orden + 1):
        fact_orden *= i
    for i in range(len(pr) - orden):
        w = pr[i:i + orden]
        pat = tuple(np.argsort(w))
        n_patrones[pat] = n_patrones.get(pat, 0) + 1
    total = sum(n_patrones.values()) or 1
    h = 0.0
    for c in n_patrones.values():
        p = c / total
        if p > 0:
            h -= p * np.log2(p)
    return float(h / np.log2(fact_orden))


# ─── Racha actual ─────────────────────────────────────────────────────────────

def racha_actual(sec):
    """(longitud, dirección) de la racha al final de la secuencia."""
    if not sec:
        return 0, None
    d = sec[-1]
    n = 1
    for c in reversed(sec[:-1]):
        if c == d:
            n += 1
        else:
            break
    return n, d


# ─── RVI — Relative Vigor Index ─────────────────────────────────────────────

def rvi(sec, p: int = 10) -> float | None:
    """
    Relative Vigor Index — mide si el precio tiende a cerrar más alto (bullish)
    o más bajo (bearish) que su apertura.

    Adaptado a binarias: 'V' = cierre arriba, 'R' = cierre abajo.
    RVI > 0 → momentum alcista    |    RVI < 0 → momentum bajista.
    """
    if len(sec) < p * 2:
        return None
    rets = _ret(sec[-p * 2:])
    # Separar rachas alcistas y bajistas, medir vigor relativo
    v_sum = float(np.sum(rets[rets > 0]))
    r_sum = float(np.sum(rets[rets < 0]))
    total = abs(v_sum) + abs(r_sum)
    if total < 1e-9:
        return 0.0
    return round((v_sum + r_sum) / total, 4)


# ─── CCI — Commodity Channel Index ──────────────────────────────────────────

def cci(sec, p: int = 14) -> float | None:
    """
    Commodity Channel Index.
    CCI > +100 → sobrecompra (posible bajada)
    CCI < -100 → sobreventa  (posible subida)
    Cruce de 0 → señal de inicio de tendencia.
    """
    if len(sec) < p + 2:
        return None
    pr = _precio(sec[-p * 2:])
    if len(pr) < p:
        return None
    # "Precio típico" sintético: usamos el precio actual como proxy
    tp  = pr[-p:]
    sma = float(np.mean(tp))
    md  = float(np.mean(np.abs(tp - sma)))   # mean deviation
    if md < 1e-9:
        return 0.0
    return round((float(tp[-1]) - sma) / (0.015 * md), 2)


# ─── Fisher Transform del RSI ────────────────────────────────────────────────

def fisher_rsi(sec, p: int = 14) -> float | None:
    """
    Fisher Transform aplicado al RSI.
    Amplifica señales de sobrecompra/sobreventa del RSI para detectar
    cruces de señal más nítidos. Rango efectivo: -3 a +3.

    Fisher > +2.0 → sobrecompra extrema (esperar corrección)
    Fisher < -2.0 → sobreventa extrema  (esperar rebote)
    Cruce de 0    → cambio de momentum
    """
    r = rsi(sec, p)
    if r is None:
        return None
    # Mapear RSI [0-100] a [-0.999, +0.999] para la transform
    x = (r / 50.0) - 1.0
    x = max(-0.999, min(0.999, x))
    try:
        fisher = 0.5 * float(np.log((1 + x) / (1 - x)))
    except Exception:
        return None
    return round(fisher, 4)


# ─── Supertrend sintético ────────────────────────────────────────────────────

def supertrend(sec, p: int = 10, mult: float = 3.0) -> str | None:
    """
    Supertrend adaptado a series binarias.

    Calcula banda superior e inferior basadas en SMA ± mult×ATR_sintético.
    El precio está "sobre Supertrend" cuando el precio sintético > banda inferior
    → señal alcista. Bajo banda superior → bajista.

    Retorna: 'V' (alcista), 'R' (bajista) o None si indeterminado.
    """
    n = len(sec)
    if n < p + 5:
        return None
    pr   = _precio(sec)
    rets = _ret(sec)
    # ATR sintético: media de |cambios diarios| × p períodos
    if len(rets) < p:
        return None
    atr_v = float(np.mean(np.abs(np.diff(pr[-p - 1:]))))
    if atr_v < 1e-9:
        return None
    mid    = float(np.mean(pr[-p:]))
    b_up   = mid + mult * atr_v     # banda superior
    b_dn   = mid - mult * atr_v     # banda inferior
    precio_actual = float(pr[-1])
    if precio_actual > b_dn and precio_actual > mid:
        return "V"
    if precio_actual < b_up and precio_actual < mid:
        return "R"
    return None


# ─── Keltner Channels ────────────────────────────────────────────────────────

def keltner(sec, p: int = 20, mult: float = 2.0) -> tuple:
    """
    Keltner Channels: EMA ± mult×ATR.
    Similar a Bollinger pero usa ATR en lugar de desv. estándar — menos sensible
    al ruido de corto plazo.

    Retorna (posición 0..1, señal 'V'/'R'/None).
    """
    n = len(sec)
    if n < p + 5:
        return 0.5, None
    pr    = _precio(sec)
    e     = ema(pr, p)
    rets  = _ret(sec)
    atr_v = float(np.mean(np.abs(np.diff(pr[-p - 1:]))))
    if atr_v < 1e-9:
        return 0.5, None
    mid_e  = float(e[-1])
    banda_s = mid_e + mult * atr_v
    banda_i = mid_e - mult * atr_v
    ancho   = banda_s - banda_i
    if ancho < 1e-9:
        return 0.5, None
    precio_actual = float(pr[-1])
    pos = float(np.clip((precio_actual - banda_i) / ancho, 0.0, 1.0))
    if pos > 0.90:   return pos, "R"   # toca banda superior → sobrecompra
    if pos < 0.10:   return pos, "V"   # toca banda inferior → sobreventa
    # Señal de dirección por posición relativa al centro
    if pos > 0.65:   return pos, "V"   # sobre la media → alcista
    if pos < 0.35:   return pos, "R"   # bajo la media → bajista
    return pos, None


# ─── Elder Ray (Bull Power / Bear Power) ────────────────────────────────────

def elder_ray(sec, p: int = 13) -> tuple:
    """
    Elder Ray — Alexander Elder.
    Bull Power  = High_sintetico - EMA(p)
    Bear Power  = Low_sintetico  - EMA(p)

    Adaptado a binarias:
      "High" sintético: acumulado máximo de las últimas 3 velas
      "Low"  sintético: acumulado mínimo

    Bull > 0 y aumentando → mercado fuerte
    Bear < 0 y subiendo   → fuerza compradora emergente
    """
    n = len(sec)
    if n < p + 3:
        return None, None
    pr   = _precio(sec)
    e    = ema(pr, p)
    ema_act  = float(e[-1])
    high_syn = float(np.max(pr[-3:]))
    low_syn  = float(np.min(pr[-3:]))
    bull = round(high_syn - ema_act, 4)
    bear = round(low_syn  - ema_act, 4)
    return bull, bear


# ─── Chande Momentum Oscillator (CMO) ───────────────────────────────────────

def cmo(sec, p: int = 14) -> float | None:
    """
    Chande Momentum Oscillator.
    CMO = 100 × (suma_sube - suma_baja) / (suma_sube + suma_baja)

    Rango [-100, +100].
    CMO > +50  → momentum alcista fuerte
    CMO < -50  → momentum bajista fuerte
    CMO cerca de 0 → consolidación / indecisión

    Más sensible que el RSI a cambios de momentum en series cortas.
    """
    if len(sec) < p + 1:
        return None
    rets = _ret(sec[-(p + 1):])
    cambios = np.diff(rets)
    sube = float(np.sum(cambios[cambios > 0]))
    baja = float(np.abs(np.sum(cambios[cambios < 0])))
    total = sube + baja
    if total < 1e-9:
        return 0.0
    return round(100.0 * (sube - baja) / total, 2)


# ─── Volume Profile sintético (distribución de precios) ─────────────────────

def volume_profile(sec, buckets: int = 5) -> tuple:
    """
    Volume Profile sintético: densidad de "volumen" por zona de precio.

    En series binarias "volumen" = tiempo en una zona de precio.
    Identifica la zona de valor (Value Area: 70% del volumen).

    Retorna (zona: 'high'/'mid'/'low', sesgo: 'V'/'R'/None).
    'high' → precio en zona de distribución (vender)
    'low'  → precio en zona de acumulación  (comprar)
    """
    n = len(sec)
    if n < 20:
        return "mid", None
    pr       = _precio(sec[-50:] if n >= 50 else sec)
    p_act    = float(pr[-1])
    p_min    = float(pr.min())
    p_max    = float(pr.max())
    rango    = p_max - p_min
    if rango < 1e-9:
        return "mid", None
    # Distribuir precios en buckets y contar "tiempo" en cada zona
    indices  = np.clip(((pr - p_min) / rango * (buckets - 1)).astype(int),
                       0, buckets - 1)
    counts   = np.bincount(indices, minlength=buckets).astype(float)
    total_c  = counts.sum()
    # Value Area: zona de mayor concentración
    va_idx   = int(np.argmax(counts))
    va_center = p_min + (va_idx + 0.5) / buckets * rango
    pos_rel  = (p_act - p_min) / rango   # 0 = mínimo, 1 = máximo
    if pos_rel > 0.80:
        return "high", "R"    # precio en zona alta → presión bajista
    if pos_rel < 0.20:
        return "low",  "V"    # precio en zona baja → presión alcista
    # Si el precio está sobre el value area → seguir tendencia
    if p_act > va_center:     return "mid", "V"
    if p_act < va_center:     return "mid", "R"
    return "mid", None


# ─── Señal técnica unificada (v3 — +Supertrend, +Keltner, +Elder Ray, +CMO, +VP) ──

def evaluar_senal(sec) -> dict | None:
    """
    Combina 22 indicadores en un único voto de trading con dirección y confianza.

    MEJORAS v3 (sobre v2):
    ─────────────────────
      +Supertrend:    seguimiento de tendencia robusto al ATR
      +Keltner:       bandas basadas en ATR, más estables que BB en volatilidad
      +Elder Ray:     Bull/Bear Power de Alexander Elder
      +CMO:           Chande Momentum — más sensible que RSI a cambios rápidos
      +Volume Profile: zonas de acumulación/distribución institucional

    MEJORAS v2 (basadas en DINAMITA GRIZZLY, Equiti Guide, 151 Estrategias):
    ─────────────────────────────────────────────────────────────────────────
    FILTRO DE RÉGIMEN (pre-filtro antes de votar):
      chaotic  (entropía > 0.90)  → retorna None — mercado impredecible
      ranging  (ADX < 18)         → desactiva indicadores de tendencia (MACD, MOM, ROC, OBV)
                                    solo cuenta reversión (BB, RSI extremo, Stoch, WR)

    RSI (thresholds más estrictos que v1 — menos señales falsas):
      < 25  → SUBE +2   (sobrevendido fuerte)
      > 75  → BAJA +2   (sobrecomprado fuerte)
      25-38 → SUBE +1   (sobrevendido moderado)
      62-75 → BAJA +1   (sobrecomprado moderado)
      [zona 38-62 ya no genera voto — evita ruido en zona neutra]

    Divergencia RSI:
      alcista/bajista confirmada → +2 en la dirección indicada

    MACD histograma (solo en régimen "trending" o "neutral"):
      > 0  → SUBE +1    (momentum alcista)
      < 0  → BAJA +1    (momentum bajista)
      cruce de señal (cambio de signo) → +1 extra

    Bollinger Bands:
      pos > 0.88 → BAJA +2   (precio tocando banda superior)
      pos < 0.12 → SUBE +2   (precio tocando banda inferior)
      pos > 0.70 → BAJA +1
      pos < 0.30 → SUBE +1

    Stochastic:
      %K > 82, %D > 75 (doble confirmación) → BAJA +2
      %K < 18, %D < 25 (doble confirmación) → SUBE +2
      solo %K (sin confirmación %D)          → ±1

    Williams %R:
      > -15  → BAJA +1   (sobrecomprado extremo)
      < -85  → SUBE +1   (sobrevendido extremo)

    Momentum (solo en trending/neutral):
      > 0 → SUBE +1
      < 0 → BAJA +1

    ROC (solo en trending/neutral):
      > 15% → SUBE +1
      < -15% → BAJA +1

    OBV (solo en trending/neutral):
      pendiente > 0.08 → SUBE +1
      pendiente < -0.08 → BAJA +1

    Hurst (confirmación de tendencia):
      > 0.58 + ADX > 25 → +1 en dirección del momentum
      < 0.43            → +1 contra el momentum (reversión)

    Racha (REDUCIDA respecto a v1 para evitar over-reversión):
      ≥ 6  → reversión +2  (solo en ranging — DINAMITA GRIZZLY: no revertir en trending)
      ≥ 5  → reversión +2  (siempre)
      ≥ 4  → reversión +1
      ≥ 3  → reversión +1 solo en ranging (no en trending)

    EMA Triple Cross (Equiti EMA 4-18-40):
      alcista alineado → SUBE +2
      bajista alineado → BAJA +2
      fuerza de separación escala el voto

    VWAP sintético (DINAMITA GRIZZLY):
      precio > VWAP → SUBE +1 (zona cara, institucionales vendiendo, pero momentum)
      precio < VWAP → BAJA +1 (zona barata, acumulación)
      — se usa para CONFIRMAR, no para generar señal sola

    Entropía de permutación:
      < 0.55 → confianza ×1.25 (serie muy predecible)
      0.55-0.78 → sin ajuste
      0.78-0.90 → confianza ×0.85
      > 0.90 → filtrado antes de llegar aquí (chaotic)

    UMBRAL FINAL:
      confianza < 0.58 → retorna None (más estricto que v1: 0.55→0.58)

    Retorna None si el mercado está en régimen chaotic, señal ambigua,
    o confianza insuficiente.
    """
    n = len(sec)
    if n < 15:
        return None

    # ── Pre-computar indicadores costosos (usados en múltiples lugares) ──
    # Hurst limitado a 200 velas: suficiente precisión, mucho más rápido
    adx_v    = adx(sec)
    ep_v     = entropia_perm(sec)
    h_v      = hurst(sec[-200:] if n > 200 else sec)
    mom_v    = momentum(sec)
    adx_val  = float(adx_v) if adx_v is not None else 20.0
    adx_fuerte = adx_val > 25.0

    det = {
        "adx": round(adx_val, 1),
        "hurst": round(h_v, 3) if h_v is not None else None,
        "entropia_perm": round(ep_v, 3) if ep_v is not None else None,
    }

    # ── FILTRO 1: Mercado caótico → no operar ────────────────────────────
    if ep_v is not None and ep_v > 0.90:
        return None

    # ── FILTRO 2: Clasificar régimen (reutiliza valores ya calculados) ────
    regimen = regimen_mercado(sec, _adx=adx_v, _hurst=h_v, _ep=ep_v)
    en_tendencia = regimen == "trending"
    en_rango     = regimen == "ranging"

    vs, bs = 0.0, 0.0

    # ── RSI (thresholds más estrictos en v2) ─────────────────────────────
    rsi_v = rsi(sec)
    det["rsi"] = round(rsi_v, 1) if rsi_v is not None else None
    if rsi_v is not None:
        if rsi_v < 25:     vs += 2
        elif rsi_v > 75:   bs += 2
        elif rsi_v < 38:   vs += 1
        elif rsi_v > 62:   bs += 1

    # ── Divergencia RSI ───────────────────────────────────────────────────
    div = rsi_divergencia(sec)
    det["rsi_div"] = div
    if div == "V": vs += 2
    elif div == "R": bs += 2

    # ── MACD (solo en trending/neutral para evitar ruido en rango) ────────
    ml, sl, hist = macd(sec)
    det["macd_h"] = round(hist, 4) if hist is not None else None
    if hist is not None and not en_rango:
        if hist > 0: vs += 1
        else:        bs += 1
        _, _, hist_ant = macd(sec[:-1]) if n > 10 else (None, None, None)
        if hist_ant is not None:
            if hist > 0 and hist_ant <= 0:   vs += 1
            elif hist < 0 and hist_ant >= 0: bs += 1

    # ── Bollinger Bands ───────────────────────────────────────────────────
    _, _, _, pos_bb = bollinger(sec)
    det["bb"] = round(pos_bb, 2) if pos_bb is not None else None
    if pos_bb is not None:
        if pos_bb > 0.88:   bs += 2
        elif pos_bb < 0.12: vs += 2
        elif pos_bb > 0.70: bs += 1
        elif pos_bb < 0.30: vs += 1

    # ── Stochastic (doble confirmación en v2) ────────────────────────────
    k_v, d_v = stochastic(sec)
    det["stoch_k"] = round(k_v, 1) if k_v is not None else None
    if k_v is not None and d_v is not None:
        if k_v > 82 and d_v > 75:    bs += 2   # doble sobrecompra
        elif k_v < 18 and d_v < 25:  vs += 2   # doble sobreventa
        elif k_v > 80:                bs += 1
        elif k_v < 20:                vs += 1
        # Cruce K/D
        if k_v > d_v + 2:   vs += 1
        elif k_v < d_v - 2: bs += 1

    # ── Williams %R (thresholds más extremos en v2) ───────────────────────
    wr_v = williams_r(sec)
    det["wr"] = round(wr_v, 1) if wr_v is not None else None
    if wr_v is not None:
        if wr_v > -15:   bs += 1
        elif wr_v < -85: vs += 1

    # ── Momentum (solo en trending/neutral) ──────────────────────────────
    det["mom"] = round(mom_v, 2) if mom_v is not None else None
    if mom_v is not None and not en_rango:
        if mom_v > 0: vs += 1
        else:         bs += 1

    # ── ROC (umbral más alto que v1: 15% vs 10%) ─────────────────────────
    roc_v = roc(sec)
    det["roc"] = round(roc_v, 2) if roc_v is not None else None
    if roc_v is not None and not en_rango:
        if roc_v > 15:    vs += 1
        elif roc_v < -15: bs += 1

    # ── OBV (umbral más exigente: 0.08 vs 0.05) ──────────────────────────
    obv_v = obv(sec)
    det["obv"] = round(obv_v, 4) if obv_v is not None else None
    if obv_v is not None and not en_rango:
        if obv_v > 0.08:    vs += 1
        elif obv_v < -0.08: bs += 1

    # ── Hurst (solo cuando ADX confirma tendencia real) ──────────────────
    if h_v is not None and adx_fuerte and mom_v is not None:
        if h_v > 0.58:    # persistente → seguir momentum
            if mom_v > 0: vs += 1
            else:         bs += 1
        elif h_v < 0.43:  # anti-persistente → contra momentum
            if mom_v > 0: bs += 1
            else:         vs += 1

    # ── Racha (pesos REDUCIDOS en v2; desactivada en trending) ───────────
    n_r, dir_r = racha_actual(sec)
    det["racha"] = (n_r, dir_r)
    if dir_r:
        if n_r >= 5:
            peso_rev = 2
        elif n_r >= 4:
            peso_rev = 1
        elif n_r >= 3 and en_rango:
            peso_rev = 1   # solo en rango, como indica DINAMITA GRIZZLY
        else:
            peso_rev = 0
        if peso_rev > 0 and not (en_tendencia and n_r < 5):
            if dir_r == "V": bs += peso_rev
            else:            vs += peso_rev

    # ── EMA Triple Cross (Equiti 4-18-40) ────────────────────────────────
    dir_ema, fuerza_ema = ema_triple_cross(sec)
    det["ema_triple"] = dir_ema
    if dir_ema is not None:
        # +1 base, +1 extra si la separación es fuerte (fuerza > 0.5)
        voto_ema = 1 + (1 if fuerza_ema > 0.5 else 0)
        if dir_ema == "V": vs += voto_ema
        else:              bs += voto_ema

    # ── VWAP sintético (sesgo institucional — DINAMITA GRIZZLY) ──────────
    pos_vwap, bias_vwap = vwap_sintetico(sec)
    det["vwap_bias"] = bias_vwap
    if bias_vwap is not None:
        if bias_vwap == "V": vs += 1
        else:                bs += 1

    # ── RVI — Relative Vigor Index (v2) ──────────────────────────────────
    rvi_v = rvi(sec)
    det["rvi"] = round(rvi_v, 4) if rvi_v is not None else None
    if rvi_v is not None and not en_rango:
        if rvi_v > 0.25:    vs += 1
        elif rvi_v < -0.25: bs += 1

    # ── CCI — Commodity Channel Index (v2) ───────────────────────────────
    cci_v = cci(sec)
    det["cci"] = round(cci_v, 1) if cci_v is not None else None
    if cci_v is not None:
        if cci_v < -100:    vs += 1
        elif cci_v > 100:   bs += 1
        if 0 < cci_v < 80 and en_tendencia and mom_v is not None and mom_v > 0:
            vs += 1
        elif -80 < cci_v < 0 and en_tendencia and mom_v is not None and mom_v < 0:
            bs += 1

    # ── Fisher Transform del RSI (v2) ────────────────────────────────────
    fish_v = fisher_rsi(sec)
    det["fisher"] = round(fish_v, 4) if fish_v is not None else None
    if fish_v is not None:
        if fish_v < -1.8:   vs += 1
        elif fish_v > 1.8:  bs += 1
        if abs(fish_v) < 0.3 and abs(fish_v) > 0.05:
            if fish_v > 0 and en_tendencia: vs += 1
            elif fish_v < 0 and en_tendencia: bs += 1

    # ── Supertrend sintético (nuevo v3) ──────────────────────────────────
    st_dir = supertrend(sec)
    det["supertrend"] = st_dir
    if st_dir == "V": vs += 2   # Supertrend es un indicador de tendencia fuerte
    elif st_dir == "R": bs += 2

    # ── Keltner Channels (nuevo v3) ───────────────────────────────────────
    kc_pos, kc_dir = keltner(sec)
    det["keltner"] = round(kc_pos, 3)
    if kc_dir == "V": vs += 1
    elif kc_dir == "R": bs += 1

    # ── Elder Ray (nuevo v3) ──────────────────────────────────────────────
    bull_p, bear_p = elder_ray(sec)
    det["elder_bull"] = round(bull_p, 4) if bull_p is not None else None
    det["elder_bear"] = round(bear_p, 4) if bear_p is not None else None
    if bull_p is not None and bear_p is not None:
        if bull_p > 0 and bear_p > 0:   vs += 1   # fuerza compradora en ambos → alcista
        elif bull_p < 0 and bear_p < 0: bs += 1   # debilidad total → bajista
        elif bull_p > 0 and bear_p < 0 and not en_rango:
            vs += 1   # bull power positivo, bear power aún negativo pero en tendencia
        elif bull_p < 0 and bear_p > 0 and not en_rango:
            bs += 1

    # ── CMO — Chande Momentum Oscillator (nuevo v3) ───────────────────────
    cmo_v = cmo(sec)
    det["cmo"] = round(cmo_v, 2) if cmo_v is not None else None
    if cmo_v is not None:
        if cmo_v > 50:     vs += 1   # momentum alcista fuerte
        elif cmo_v < -50:  bs += 1   # momentum bajista fuerte
        if 20 < cmo_v < 50 and en_tendencia:  vs += 1   # momentum moderado en tendencia
        elif -50 < cmo_v < -20 and en_tendencia: bs += 1

    # ── Volume Profile sintético (nuevo v3) ───────────────────────────────
    vp_zona, vp_dir = volume_profile(sec)
    det["vp_zona"] = vp_zona
    det["vp_dir"]  = vp_dir
    if vp_dir == "V": vs += 1
    elif vp_dir == "R": bs += 1

    # ── Resultado ────────────────────────────────────────────────────────
    total = vs + bs
    if total < 2:
        return None

    if vs > bs:
        candidata = "V"
        confianza = float(vs / total)
    elif bs > vs:
        candidata = "R"
        confianza = float(bs / total)
    else:
        return None

    # Ajuste por entropía de permutación
    if ep_v is not None:
        if ep_v < 0.55:   confianza = min(1.0, confianza * 1.25)
        elif ep_v < 0.78: pass
        elif ep_v < 0.90: confianza *= 0.85

    # Umbral final: 0.58 (igual que v2 — no relajar)
    if confianza < 0.58:
        return None

    return {
        "candidata":    candidata,
        "confianza":    round(confianza, 3),
        "votos_sube":   float(vs),
        "votos_baja":   float(bs),
        "total_votos":  float(total),
        "adx_fuerza":   round(adx_val, 1),
        "hurst":        round(h_v, 3) if h_v is not None else None,
        "entropia":     round(ep_v, 3) if ep_v is not None else None,
        "regimen":      regimen,
        "ema_triple":   dir_ema,
        "vwap_bias":    bias_vwap,
        "rvi":          det.get("rvi"),
        "cci":          det.get("cci"),
        "fisher":       det.get("fisher"),
        "supertrend":   st_dir,
        "keltner":      round(kc_pos, 3),
        "elder_bull":   det.get("elder_bull"),
        "elder_bear":   det.get("elder_bear"),
        "cmo":          det.get("cmo"),
        "vp_zona":      vp_zona,
        "vp_dir":       vp_dir,
        "detalle":      det,
    }
