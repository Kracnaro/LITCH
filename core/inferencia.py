"""Motor de Inferencia Bayesiana de Litch — la capa que conecta todo.

Como las conexiones de un cerebro, este motor toma las opiniones de TODAS
las fuentes de Litch (cadena de Markov, ensemble estadístico, red neuronal)
y las fusiona en una sola probabilidad final usando teoremas clásicos:

  • TEOREMA DE BAYES: cada método actualiza la probabilidad a posteriori
    según su precisión histórica real (un método que acierta más, pesa más).
  • LEY DE LOS GRANDES NÚMEROS: la confianza solo crece con la evidencia;
    con pocas muestras, Litch reduce su certeza automáticamente.
  • TEOREMA DEL LÍMITE CENTRAL: intervalos de confianza (Wilson/normal)
    sobre las proporciones observadas — Litch sabe cuánto puede equivocarse.
  • LEY DE LITTLEWOOD (eventos improbables): con suficientes observaciones,
    las rachas "milagrosas" son esperables; Litch no se deja impresionar por
    una racha si su longitud está dentro de lo que el azar produce.

Resultado: una decisión única, rápida (NumPy puro) y con su incertidumbre
medida. Honestidad: esto optimiza el uso de la evidencia disponible; no
elimina el azar del mercado ni garantiza aciertos.
"""
import math


Z95 = 1.959964  # z del 95% (límite central)


# --- Teorema del Límite Central: intervalo de Wilson -------------------------
def intervalo_wilson(exitos, n, z=Z95):
    """Intervalo de confianza 95% para una proporción. Devuelve (lo, hi)."""
    if n <= 0:
        return 0.0, 1.0
    p = exitos / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    margen = (z / den) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centro - margen), min(1.0, centro + margen)


# --- Ley de los Grandes Números ----------------------------------------------
def factor_evidencia(n, n_objetivo=75):
    """0..1: cuánta confianza permite el tamaño de muestra. Con n>=n_objetivo
    la evidencia se considera madura; con poca muestra, la confianza se
    encoge hacia 0.5 (no sabemos). Reducido de 100 → 75 para madurar antes."""
    if n <= 0:
        return 0.0
    return min(1.0, math.sqrt(n / n_objetivo))


# --- Ley de Littlewood / rachas ------------------------------------------------
def racha_es_normal(secuencia):
    """¿La racha actual está dentro de lo esperable por azar?
    La racha más larga esperada en n ensayos justos es ~log2(n).
    Devuelve (racha_actual, racha_esperada_max, es_normal)."""
    n = len(secuencia)
    if n < 4:
        return 0, 0.0, True
    ultimo = secuencia[-1]
    racha = 0
    for c in reversed(secuencia):
        if c == ultimo:
            racha += 1
        else:
            break
    esperada = math.log2(n) + 1  # cota práctica de racha máxima esperable
    return racha, round(esperada, 1), racha <= esperada


# --- Teorema de Bayes: fusión de métodos ---------------------------------------
def fusion_bayesiana(opiniones, prior=0.5):
    """Combina opiniones de varios métodos en una probabilidad de 'V'.

    opiniones: lista de dicts {"direccion": 'V'/'R'/None,
                               "confianza": 0..1,
                               "precision": 0..1 (histórica del método),
                               "n": tamaño de muestra que respalda su precisión}
    Aplica Bayes en forma de odds: cada método multiplica las odds según
    su verosimilitud, atenuada por la Ley de los Grandes Números (n).
    Devuelve (prob_V, detalle_lista).
    """
    odds = prior / (1 - prior)
    detalle = []
    for op in opiniones:
        d = op.get("direccion")
        if d not in ("V", "R"):
            continue
        conf = min(1.0, max(0.0, op.get("confianza", 0.5)))
        prec = min(0.99, max(0.01, op.get("precision", 0.5)))
        n = op.get("n", 0)
        # LGN: con poca muestra, la precisión declarada se encoge hacia 0.5
        fe = factor_evidencia(n)
        prec_efectiva = 0.5 + (prec - 0.5) * fe
        # prob de que ESTE método esté en lo cierto ahora
        p_metodo = 0.5 + (prec_efectiva - 0.5) * conf
        p_metodo = min(0.95, max(0.05, p_metodo))
        lr = p_metodo / (1 - p_metodo)          # razón de verosimilitud
        odds *= lr if d == "V" else (1.0 / lr)
        detalle.append({"direccion": d, "p_metodo": round(p_metodo, 3),
                        "evidencia": round(fe, 2)})
    prob_v = odds / (1 + odds)
    return prob_v, detalle


# --- Decisión integral ------------------------------------------------------------
def decidir(secuencia, opiniones, umbral=0.70, entropia: float = None,
            en_practica: bool = False, wr_sesion: float = None):
    """Decisión final de Litch fusionando todos sus métodos.

    Mejoras v2+:
    • umbral adaptativo — entropía baja → umbral menor; alta → umbral mayor.
    • en_practica — relaja exigencia de evidencia para aprendizaje rápido.
    • wr_sesion — si se pasa el win rate reciente de la sesión, se usa como
      prior bayesiano en vez de 0.5 (mejora la calibración cuando el activo
      tiene sesgo sistemático real, e.g. 55% alcista histórico).

    Devuelve dict con: direccion final (o None si no hay ventaja clara),
    probabilidad, intervalo de confianza, estado de la racha (Littlewood)
    y si la evidencia es suficiente (LGN)."""
    # Prior adaptativo: si se conoce el WR reciente, usarlo; si no, 0.5
    prior = 0.5
    if wr_sesion is not None and 0.35 <= wr_sesion <= 0.70:
        # Suavizar hacia 0.5 para no sesgar demasiado con pocas observaciones
        prior = 0.5 + (wr_sesion - 0.5) * 0.4
    prob_v, detalle = fusion_bayesiana(opiniones, prior=prior)
    direccion = "V" if prob_v >= 0.5 else "R"
    prob_dir = prob_v if direccion == "V" else 1 - prob_v

    # TLC: intervalo sobre la proporción de verdes reciente
    n = len(secuencia)
    verdes = sum(1 for c in secuencia[-200:] if c == "V")
    lo, hi = intervalo_wilson(verdes, min(n, 200))

    racha, racha_esp, racha_normal = racha_es_normal(secuencia)
    evidencia = factor_evidencia(n)

    # ── Umbral adaptativo según entropía del mercado ──────────────────────
    # Entropía baja (< 0.65) → mercado con estructura → podemos bajar el umbral
    # Entropía alta (> 0.88) → mercado caótico → subimos el umbral
    umbral_efectivo = umbral
    if entropia is not None:
        if entropia < 0.65:
            umbral_efectivo = max(0.58, umbral - 0.08)   # mercado predecible
        elif entropia > 0.88:
            umbral_efectivo = min(0.85, umbral + 0.08)   # mercado caótico

    # ── Umbral de evidencia adaptativo ───────────────────────────────────
    # En modo Practica, se relaja para que más señales lleguen al entrenamiento.
    ev_min = 0.25 if en_practica else 0.50

    actuar = (prob_dir >= umbral_efectivo
              and evidencia >= ev_min
              and racha_normal)
    return {
        "direccion": direccion if actuar else None,
        "candidata": direccion,
        "probabilidad": round(prob_dir, 3),
        "umbral_efectivo": round(umbral_efectivo, 3),
        "intervalo_verdes": (round(lo, 3), round(hi, 3)),
        "racha": racha, "racha_esperada": racha_esp,
        "racha_normal": racha_normal,
        "evidencia": round(evidencia, 2),
        "detalle": detalle,
        "actuar": actuar,
    }


def resumen(decision, idioma="es"):
    d = decision
    if idioma == "en":
        lado = "rise (green)" if d["candidata"] == "V" else "fall (red)"
        L = [f"Bayesian fusion: {lado} with {d['probabilidad']*100:.0f}% posterior "
             f"probability."]
        L.append(f"Evidence maturity (law of large numbers): {d['evidencia']*100:.0f}%.")
        L.append(f"95% interval for green ratio (CLT): "
                 f"{d['intervalo_verdes'][0]*100:.0f}%–{d['intervalo_verdes'][1]*100:.0f}%.")
        L.append(f"Current streak {d['racha']} vs expected max ~{d['racha_esperada']} "
                 + ("(normal — Littlewood says no miracle here)." if d["racha_normal"]
                    else "(unusual — caution)."))
        L.append("Decision: ACT." if d["actuar"] else
                 "Decision: WAIT — edge or evidence insufficient, sir.")
        return " ".join(L)
    lado = "subida (verde)" if d["candidata"] == "V" else "bajada (roja)"
    L = [f"Fusión bayesiana: {lado} con probabilidad a posteriori del "
         f"{d['probabilidad']*100:.0f}%."]
    L.append(f"Madurez de la evidencia (ley de grandes números): {d['evidencia']*100:.0f}%.")
    L.append(f"Intervalo 95% de proporción verde (límite central): "
             f"{d['intervalo_verdes'][0]*100:.0f}%–{d['intervalo_verdes'][1]*100:.0f}%.")
    L.append(f"Racha actual {d['racha']} frente a máxima esperable ~{d['racha_esperada']} "
             + ("(normal: Littlewood dice que no es milagro)." if d["racha_normal"]
                else "(inusual: cautela)."))
    L.append("Decisión: ACTUAR." if d["actuar"] else
             "Decisión: ESPERAR — la ventaja o la evidencia no bastan, señor.")
    return " ".join(L)
