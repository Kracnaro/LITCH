"""
Análisis avanzado de loterías para Litch — implementación 100% NumPy.

Complementa loteria.py con 9 técnicas adicionales + predictor neural MLP.

Módulos de análisis:
  1.  Frecuencia temporal con decaimiento exponencial
       Los sorteos recientes pesan más; gradualmente "olvida" los viejos.
  2.  Gap analysis (números atrasados)
       Score = gap_actual / gap_promedio. >1.5 → número "debería" salir.
  3.  Análisis de pares y tripletas
       Co-ocurrencia: ¿qué números salen juntos con más frecuencia?
  4.  Detección de ciclos (autocorrelación por número)
       Si el número 7 sale cada ~14 sorteos, hay un ciclo de período 14.
  5.  Análisis de suma del sorteo
       Las sumas no son uniformes; el rango óptimo histórico filtra combinaciones.
  6.  Análisis de paridad (pares vs. impares)
       La distribución par/impar más común históricamente.
  7.  Análisis de décadas
       ¿Qué rango numérico aparece con más frecuencia?
  8.  Análisis de delta
       Diferencias entre números consecutivos dentro del mismo sorteo.
  9.  Patrón de consecutivos
       Frecuencia de números consecutivos (e.g. 5-6, 12-13) en sorteos.
 10.  Red neuronal MLP (NumPy)
       Aprende de los últimos W sorteos como contexto y predice el siguiente.
 11.  Motor combinado bayesiano
       Fusión ponderada de todos los métodos con un score final por número.

El análisis completo devuelve sugerencia de N números ordenados por score,
más información complementaria sobre distribuciones y ciclos activos.

ADVERTENCIA HONESTA: ningún método estadístico o neural puede predecir
sorteos independientes de azar. Esta herramienta analiza patrones históricos
— útil para entender la distribución, no para garantizar resultados.
"""

import json
import math
import os
import time
import numpy as np
from collections import Counter, defaultdict
from itertools import combinations


# ─── 1. Frecuencia temporal con decay ────────────────────────────────────────

def frecuencia_temporal(historial: list, decay: float = 0.97) -> dict:
    """Score de frecuencia ponderada por recencia (sorteos recientes > peso)."""
    scores = defaultdict(float)
    n = len(historial)
    for i, sorteo in enumerate(historial):
        peso = decay ** (n - 1 - i)
        for num in sorteo:
            scores[int(num)] += peso
    total = sum(scores.values()) or 1.0
    return {k: v / total for k, v in scores.items()}


# ─── 2. Gap analysis ─────────────────────────────────────────────────────────

def analisis_gap(historial: list) -> dict:
    """
    Para cada número: gap_actual (sorteos sin aparecer) y gap_medio histórico.
    score = gap_actual / gap_medio  (>1.5 = número "atrasado").
    """
    ultima_vez = {}
    gaps_hist  = defaultdict(list)
    for i, sorteo in enumerate(historial):
        for num in sorteo:
            num = int(num)
            if num in ultima_vez:
                gaps_hist[num].append(i - ultima_vez[num])
            ultima_vez[num] = i
    n = len(historial)
    resultado = {}
    for num, ult in ultima_vez.items():
        ga  = n - 1 - ult
        gs  = gaps_hist.get(num, [])
        gm  = float(np.mean(gs)) if gs else float(n)
        sc  = ga / (gm + 1e-9)
        resultado[num] = {"gap_actual": ga, "gap_medio": round(gm, 1),
                          "score": round(sc, 3)}
    return resultado


# ─── 3. Pares y tripletas ─────────────────────────────────────────────────────

def analisis_pares(historial: list, top_n: int = 20) -> dict:
    """Co-ocurrencia de pares y tripletas en el historial."""
    pares = Counter()
    trips = Counter()
    for sorteo in historial:
        nums = sorted({int(n) for n in sorteo})
        for p in combinations(nums, 2):
            pares[p] += 1
        for t in combinations(nums, 3):
            trips[t] += 1
    return {"pares": pares.most_common(top_n),
            "triplets": trips.most_common(10)}


# ─── 4. Ciclos / autocorrelación ─────────────────────────────────────────────

def detectar_ciclos(historial: list, max_lag: int = 20) -> dict:
    """
    Para cada número, calcula su autocorrelación hasta max_lag sorteos atrás.
    Ciclo confirmado si correlación > 0.25 en algún lag.
    """
    todos  = sorted({int(n) for s in historial for n in s})
    ciclos = {}
    for num in todos:
        pres = np.array([1 if num in s else 0 for s in historial], dtype=float)
        if pres.sum() < 4:
            continue
        pres -= pres.mean()
        mejor_lag, mejor_r = 0, 0.0
        for lag in range(1, min(max_lag + 1, len(pres) // 2)):
            r = float(np.corrcoef(pres[:-lag], pres[lag:])[0, 1])
            if abs(r) > abs(mejor_r):
                mejor_r   = r
                mejor_lag = lag
        if abs(mejor_r) > 0.25:
            ciclos[num] = {"periodo": mejor_lag, "corr": round(mejor_r, 3)}
    return ciclos


# ─── 5. Análisis de suma ─────────────────────────────────────────────────────

def analisis_suma(historial: list) -> dict:
    """Distribución estadística de la suma de cada sorteo."""
    sumas = [sum(s) for s in historial]
    if not sumas:
        return {}
    arr = np.array(sumas, dtype=float)
    return {
        "media":   round(float(arr.mean()), 1),
        "std":     round(float(arr.std()),  1),
        "mediana": round(float(np.median(arr)), 1),
        "min_hist": int(arr.min()),
        "max_hist": int(arr.max()),
        "rango_optimo": (round(float(arr.mean() - arr.std()), 1),
                         round(float(arr.mean() + arr.std()), 1)),
    }


# ─── 6. Paridad ───────────────────────────────────────────────────────────────

def analisis_paridad(historial: list) -> dict:
    """Distribución de cuántos pares/impares hay en cada sorteo."""
    dist = Counter()
    for sorteo in historial:
        pares = sum(1 for n in sorteo if int(n) % 2 == 0)
        dist[pares] += 1
    total = len(historial) or 1
    modo  = dist.most_common(1)[0][0] if dist else 0
    return {
        "modo_pares": modo,
        "prob": {k: round(v / total, 3) for k, v in dist.most_common()},
    }


# ─── 7. Décadas ───────────────────────────────────────────────────────────────

def analisis_decadas(historial: list) -> dict:
    """Frecuencia relativa por décadas numéricas."""
    dec = defaultdict(int)
    tot = 0
    for sorteo in historial:
        for n in sorteo:
            n = int(n)
            d = ((n - 1) // 10) * 10 + 1
            dec[d] += 1
            tot    += 1
    return {f"{d}-{d+9}": round(c / (tot or 1), 3)
            for d, c in sorted(dec.items())}


# ─── 8. Delta (diferencias internas) ────────────────────────────────────────

def analisis_delta(historial: list) -> dict:
    """Separaciones típicas entre números del mismo sorteo."""
    todos = []
    for sorteo in historial:
        nums = sorted({int(n) for n in sorteo})
        if len(nums) >= 2:
            todos.extend(nums[i+1] - nums[i] for i in range(len(nums)-1))
    if not todos:
        return {}
    arr  = np.array(todos, dtype=float)
    frec = Counter(todos)
    return {
        "media":      round(float(arr.mean()), 2),
        "std":        round(float(arr.std()),  2),
        "mas_comunes": frec.most_common(5),
    }


# ─── 9. Consecutivos ─────────────────────────────────────────────────────────

def analisis_consecutivos(historial: list) -> dict:
    """Frecuencia de pares consecutivos y sorteos que los contienen."""
    con_cons = 0
    pares_cons = Counter()
    for sorteo in historial:
        nums = sorted({int(n) for n in sorteo})
        hay  = False
        for i in range(len(nums) - 1):
            if nums[i+1] - nums[i] == 1:
                hay = True
                pares_cons[(nums[i], nums[i+1])] += 1
        if hay:
            con_cons += 1
    total = len(historial) or 1
    return {
        "pct_con_consecutivos": round(con_cons / total, 3),
        "pares_top": pares_cons.most_common(5),
    }


# ─── 10. Red Neuronal MLP (predictor) ────────────────────────────────────────

class _MLPLoteria:
    """MLP: INPUT(N*ventana) → 128 ReLU → N_nums Softmax.
    Predice la probabilidad de cada número dado el contexto reciente."""

    def __init__(self, n_nums: int = 50, ventana: int = 5):
        self.N = n_nums
        self.V = ventana
        inp = n_nums * ventana
        h   = 128
        self.W1 = np.random.randn(inp, h) * np.sqrt(2.0 / inp)
        self.b1 = np.zeros(h)
        self.W2 = np.random.randn(h, n_nums) * np.sqrt(2.0 / h)
        self.b2 = np.zeros(n_nums)
        self.entrenada = False
        self._ep = 0

    def _oh(self, sorteo: list) -> np.ndarray:
        v = np.zeros(self.N)
        for n in sorteo:
            n = int(n)
            if 1 <= n <= self.N:
                v[n - 1] = 1.0
        return v

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        e = np.exp(x - x.max())
        return e / (e.sum() + 1e-9)

    def predecir(self, historial_reciente: list) -> np.ndarray:
        """Distribución de probabilidad sobre los N números."""
        if len(historial_reciente) < self.V:
            return np.ones(self.N) / self.N
        inp = np.concatenate([self._oh(s)
                               for s in historial_reciente[-self.V:]])
        h   = np.maximum(0.0, inp @ self.W1 + self.b1)
        return self._softmax(h @ self.W2 + self.b2)

    def entrenar(self, historial: list, epochs: int = 40, lr: float = 0.003):
        """Entrenamiento online con cross-entropy + SGD."""
        if len(historial) < self.V + 2:
            return
        muestras = [(
            np.concatenate([self._oh(s) for s in historial[i:i + self.V]]),
            self._oh(historial[i + self.V])
        ) for i in range(len(historial) - self.V - 1)]
        for ep in range(epochs):
            time.sleep(0)    # cede el GIL — no bloquea hilos de trading
            np.random.shuffle(muestras)
            for x, y in muestras:
                h    = np.maximum(0.0, x @ self.W1 + self.b1)
                prob = self._softmax(h @ self.W2 + self.b2)
                dL   = prob - y
                dW2  = np.outer(h, dL)
                db2  = dL
                dh   = (dL @ self.W2.T) * (h > 0)
                dW1  = np.outer(x, dh)
                db1  = dh
                for p, g in ((self.W2, dW2), (self.b2, db2),
                              (self.W1, dW1), (self.b1, db1)):
                    p -= lr * np.clip(g, -1.0, 1.0)
        self.entrenada = True
        self._ep      += epochs

    def to_dict(self) -> dict:
        return {"W1": self.W1.tolist(), "b1": self.b1.tolist(),
                "W2": self.W2.tolist(), "b2": self.b2.tolist(),
                "entrenada": self.entrenada, "ep": self._ep, "N": self.N}

    def from_dict(self, d: dict):
        self.W1 = np.array(d["W1"]); self.b1 = np.array(d["b1"])
        self.W2 = np.array(d["W2"]); self.b2 = np.array(d["b2"])
        self.entrenada = d.get("entrenada", False)
        self._ep       = d.get("ep", 0)


# ─── 11. Motor combinado ─────────────────────────────────────────────────────

class AnalizadorLoteria:
    """
    Combina los 9 métodos estadísticos + MLP neural en una sola sugerencia.
    Se instancia una vez por tipo de lotería y se actualiza con cada sorteo.

    Uso:
        analizador = AnalizadorLoteria(n_numeros=49, ruta=ruta_pesos)
        resultado  = analizador.analizar(historial, cuantos=6)
        texto      = analizador.resumen_texto(historial)
    """

    # Pesos de cada método en la combinación final
    PESOS = {
        "freq_temporal": 3.5,
        "gap":           2.5,
        "mlp":           5.0,   # el más potente cuando está entrenada
        "pares":         1.5,
        "ciclos":        2.0,
        "consecutivos":  0.5,
    }

    def __init__(self, n_numeros: int = 50, ruta: str = None):
        self.N     = n_numeros
        self.ruta  = ruta
        self.mlp   = _MLPLoteria(n_numeros)
        self._ent_en = 0   # sorteos cuando se entrenó por última vez

        if ruta and os.path.exists(ruta):
            self._cargar()

    # ── Análisis principal ────────────────────────────────────────────────────

    def analizar(self, historial: list, cuantos: int = 6) -> dict:
        """Devuelve sugerencia de `cuantos` números con score y detalles."""
        if len(historial) < 3:
            return {"sugerencia": [], "detalle": "Historial insuficiente (mínimo 3 sorteos)."}

        # Reentrenar MLP si hay ≥5 sorteos nuevos desde el último entrenamiento
        nuevos = len(historial) - self._ent_en
        if nuevos >= 5 and len(historial) >= self.mlp.V + 2:
            self.mlp.entrenar(historial)
            self._ent_en = len(historial)
            if self.ruta:
                self._guardar()

        scores: dict[int, float] = defaultdict(float)

        # ── Frecuencia temporal ───────────────────────────────────────────
        for n, s in frecuencia_temporal(historial).items():
            scores[n] += s * self.PESOS["freq_temporal"]

        # ── Gap (atrasados) ───────────────────────────────────────────────
        for n, info in analisis_gap(historial).items():
            sc = min(info["score"], 3.0) / 3.0
            scores[n] += sc * self.PESOS["gap"]

        # ── MLP neural ────────────────────────────────────────────────────
        if self.mlp.entrenada:
            prob_mlp = self.mlp.predecir(historial)
            for i, p in enumerate(prob_mlp):
                scores[i + 1] += float(p) * self.PESOS["mlp"]

        # ── Pares frecuentes (bonus a los socios) ─────────────────────────
        for (a, b), _ in analisis_pares(historial, top_n=15)["pares"]:
            scores[a] += 0.3 * self.PESOS["pares"]
            scores[b] += 0.3 * self.PESOS["pares"]

        # ── Ciclos activos ────────────────────────────────────────────────
        gaps     = analisis_gap(historial)
        ciclos   = detectar_ciclos(historial)
        n_sort   = len(historial)
        for num, info in ciclos.items():
            gap_info = gaps.get(num)
            if gap_info and info["periodo"] > 0:
                ga   = gap_info["gap_actual"]
                resto = ga % info["periodo"]
                prox  = info["periodo"] - ga % info["periodo"]
                if prox <= 1:   # dentro del próximo período
                    scores[num] += self.PESOS["ciclos"]
                elif prox <= 2:
                    scores[num] += self.PESOS["ciclos"] * 0.5

        # ── Normalizar ───────────────────────────────────────────────────
        total = sum(scores.values()) or 1.0
        norm  = {k: v / total for k, v in scores.items()}
        top   = sorted(norm.items(), key=lambda x: x[1], reverse=True)

        sugerencia  = [n for n, _ in top[:cuantos]]
        top_15      = top[:15]

        # ── Análisis complementario ───────────────────────────────────────
        suma_i  = analisis_suma(historial)
        parid_i = analisis_paridad(historial)
        deca_i  = analisis_decadas(historial)
        delta_i = analisis_delta(historial)
        consec_i = analisis_consecutivos(historial)

        return {
            "sugerencia":      sorted(sugerencia),
            "top_scores":      [(n, round(s, 5)) for n, s in top_15],
            "suma":            suma_i,
            "paridad":         parid_i,
            "decadas":         deca_i,
            "delta":           delta_i,
            "consecutivos":    consec_i,
            "ciclos_activos":  {k: v for k, v in ciclos.items()
                                if k in sugerencia},
            "mlp_activa":      self.mlp.entrenada,
            "mlp_epochs":      self.mlp._ep,
            "n_sorteos":       n_sort,
        }

    def resumen_texto(self, historial: list, idioma: str = "es") -> str:
        """Resumen legible de la sugerencia."""
        res = self.analizar(historial)
        sug = res.get("sugerencia", [])
        if not sug:
            return ("Not enough lottery history to analyze, sir."
                    if idioma == "en" else
                    "No hay suficiente historial para analizar, señor.")

        suma  = res.get("suma", {})
        rango = suma.get("rango_optimo", ("?", "?"))
        parid = res.get("paridad", {}).get("modo_pares", "?")
        mlp   = res.get("mlp_activa", False)
        n     = res.get("n_sorteos", 0)

        if idioma == "en":
            return (
                f"Lottery analysis — {n} draws, "
                f"{'neural MLP active' if mlp else 'neural MLP training'}. "
                f"Top candidates: {', '.join(map(str, sug))}. "
                f"Optimal sum range: {rango[0]}–{rango[1]}. "
                f"Most common parity: {parid} even numbers per draw.")
        return (
            f"Análisis de lotería — {n} sorteos, "
            f"{'red neural MLP activa' if mlp else 'MLP entrenando'}. "
            f"Candidatos principales: {', '.join(map(str, sug))}. "
            f"Rango de suma óptimo: {rango[0]}–{rango[1]}. "
            f"Paridad más común: {parid} pares por sorteo.")

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _guardar(self):
        try:
            with open(self.ruta, "w", encoding="utf-8") as f:
                json.dump(self.mlp.to_dict(), f)
        except Exception as e:
            print(f"[LotML] Error al guardar: {e}")

    def _cargar(self):
        try:
            with open(self.ruta, encoding="utf-8") as f:
                d = json.load(f)
            self.mlp.from_dict(d)
            self._ent_en = d.get("sorteos_en", 0)
            print(f"[LotML] MLP cargada: {self.N} números — "
                  f"{'activa' if self.mlp.entrenada else 'pendiente'} "
                  f"({self.mlp._ep} epochs)")
        except Exception as e:
            print(f"[LotML] No se pudo cargar: {e}")
