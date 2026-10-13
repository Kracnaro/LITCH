"""Motor matemático de Litch — sucesiones, regresión, series y clustering.

Reúne varios métodos clásicos para detectar la regla de una secuencia
numérica y pronosticar el siguiente valor, además de herramientas de
análisis de series temporales y agrupamiento. Todo en NumPy puro, sin
dependencias pesadas.

Métodos incluidos:
  • Sucesión aritmética:  a_n = a_1 + (n-1)·d
  • Sucesión geométrica:  a_n = a_1 · r^(n-1)
  • Regresión lineal (mínimos cuadrados):  y = m·x + b   (tendencia)
  • Autorregresión AR(p) tipo ARIMA:  pronóstico de series temporales
  • Cadena de Markov:  P(siguiente | estado actual)
  • Clustering k-means:  agrupa valores/estados en k grupos

Honestidad: estos modelos describen y extrapolan patrones del pasado. Son
exactos para secuencias deterministas (aritméticas/geométricas) y dan
estimaciones para datos ruidosos, pero ningún método predice con certeza
fenómenos aleatorios como loterías o mercados.
"""
import numpy as np


# --- Sucesiones deterministas ------------------------------------------------
def detectar_aritmetica(serie, tol=1e-6):
    """Si la serie es aritmética, devuelve (True, d, siguiente)."""
    s = np.asarray(serie, dtype=float)
    if len(s) < 3:
        return False, None, None
    difs = np.diff(s)
    if np.all(np.abs(difs - difs[0]) <= tol):
        d = float(difs[0])
        return True, d, float(s[-1] + d)
    return False, None, None


def detectar_geometrica(serie, tol=1e-6):
    """Si la serie es geométrica, devuelve (True, r, siguiente)."""
    s = np.asarray(serie, dtype=float)
    if len(s) < 3 or np.any(s == 0):
        return False, None, None
    razones = s[1:] / s[:-1]
    if np.all(np.abs(razones - razones[0]) <= tol):
        r = float(razones[0])
        return True, r, float(s[-1] * r)
    return False, None, None


# --- Regresión lineal (tendencia) -------------------------------------------
def regresion_lineal(serie):
    """Ajusta y = m·x + b por mínimos cuadrados. Devuelve (m, b, siguiente, r2)."""
    y = np.asarray(serie, dtype=float)
    if len(y) < 2:
        return None
    x = np.arange(len(y))
    m, b = np.polyfit(x, y, 1)
    pred = m * len(y) + b
    yhat = m * x + b
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-9
    r2 = 1 - ss_res / ss_tot
    return float(m), float(b), float(pred), float(r2)


# --- Autorregresión AR(p) (mini-ARIMA) --------------------------------------
def autorregresion(serie, p=3):
    """Modelo AR(p): predice el siguiente valor como combinación lineal de los
    p anteriores, estimando coeficientes por mínimos cuadrados. Devuelve
    (siguiente, coeficientes) o None si no hay datos suficientes."""
    y = np.asarray(serie, dtype=float)
    n = len(y)
    if n < p + 2:
        return None
    # Matriz de retardos
    X, objetivo = [], []
    for i in range(p, n):
        X.append(y[i - p:i][::-1])
        objetivo.append(y[i])
    X = np.array(X)
    objetivo = np.array(objetivo)
    X = np.hstack([X, np.ones((len(X), 1))])  # término independiente
    coef, *_ = np.linalg.lstsq(X, objetivo, rcond=None)
    ultimos = np.append(y[-p:][::-1], 1.0)
    pred = float(ultimos @ coef)
    return pred, coef.tolist()


# --- Cadena de Markov sobre estados discretos -------------------------------
def markov_estados(secuencia):
    """Matriz de transición y predicción del siguiente estado.
    secuencia: lista de símbolos (p.ej. 'V'/'R' o números). Devuelve
    (siguiente_probable, probabilidades_dict)."""
    if len(secuencia) < 2:
        return None, {}
    estados = sorted(set(secuencia))
    idx = {e: i for i, e in enumerate(estados)}
    M = np.zeros((len(estados), len(estados)))
    for a, b in zip(secuencia[:-1], secuencia[1:]):
        M[idx[a], idx[b]] += 1
    actual = secuencia[-1]
    fila = M[idx[actual]]
    total = fila.sum()
    if total == 0:
        return None, {}
    probs = {estados[j]: float(fila[j] / total) for j in range(len(estados))}
    siguiente = max(probs, key=probs.get)
    return siguiente, probs


# --- Clustering k-means -----------------------------------------------------
def kmeans(datos, k=3, iteraciones=50, semilla=0):
    """k-means simple en 1D o nD. Devuelve (centroides, asignaciones)."""
    X = np.asarray(datos, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    n = len(X)
    if n < k:
        return X.copy(), list(range(n))
    rng = np.random.default_rng(semilla)
    centroides = X[rng.choice(n, k, replace=False)].astype(float)
    asign = np.full(n, -1, dtype=int)  # -1 evita corte prematuro del bucle
    for _ in range(iteraciones):
        dist = np.linalg.norm(X[:, None, :] - centroides[None, :, :], axis=2)
        nuevas = dist.argmin(axis=1)
        if np.array_equal(nuevas, asign):
            break
        asign = nuevas
        for j in range(k):
            if np.any(asign == j):
                centroides[j] = X[asign == j].mean(axis=0)
    return centroides, asign.tolist()


# --- Predicción combinada de una secuencia numérica -------------------------
def predecir_secuencia(serie, idioma="es"):
    """Aplica el mejor método y explica la regla encontrada."""
    s = list(serie)
    es_ar, d, sig_ar = detectar_aritmetica(s)
    if es_ar:
        if idioma == "en":
            return (f"It's an arithmetic sequence with common difference {d:g}. "
                    f"Next value: {sig_ar:g}.")
        return (f"Es una sucesión aritmética con diferencia {d:g}. "
                f"Siguiente valor: {sig_ar:g}.")
    es_ge, r, sig_ge = detectar_geometrica(s)
    if es_ge:
        if idioma == "en":
            return (f"It's a geometric sequence with ratio {r:g}. "
                    f"Next value: {sig_ge:g}.")
        return (f"Es una sucesión geométrica con razón {r:g}. "
                f"Siguiente valor: {sig_ge:g}.")
    # No determinista: combina regresión y AR
    reg = regresion_lineal(s)
    ar = autorregresion(s, p=min(3, max(1, len(s) // 3)))
    if ar:
        pred = ar[0]
        metodo = "autorregresión AR" if idioma != "en" else "AR autoregression"
    elif reg:
        pred = reg[2]
        metodo = "regresión lineal" if idioma != "en" else "linear regression"
    else:
        return ("No hay datos suficientes para inferir la regla, señor."
                if idioma != "en" else "Not enough data to infer the rule, sir.")
    if idioma == "en":
        extra = f" (trend R²={reg[3]:.2f})" if reg else ""
        return (f"No exact rule; using {metodo}, the next value is about "
                f"{pred:.2f}{extra}. Treat it as an estimate, sir.")
    extra = f" (tendencia R²={reg[3]:.2f})" if reg else ""
    return (f"No hay regla exacta; con {metodo}, el siguiente valor sería "
            f"aproximadamente {pred:.2f}{extra}. Tómelo como estimación, señor.")
