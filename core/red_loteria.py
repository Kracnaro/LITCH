"""Memoria algorítmica neuronal por lotería — Litch v2.

Cada lotería tiene su propia red y su propio historial persistente.
Cuantos más sorteos acumule, más patrones memoriza y mejor predice.

Ciclo de aprendizaje:
  aprender(nombre, sorteos_nuevos)
    → fusiona con historial en disco (nunca olvida)
    → reentrena la red con todos los datos acumulados
    → guarda pesos en disco → listo para la próxima vez

Features por candidato (14 entradas):
  0   frecuencia relativa global (caliente/frío total)
  1   frecuencia últimos 10 sorteos (recencia corta)
  2   frecuencia últimos 30 sorteos (recencia media)
  3   atraso normalizado (sorteos sin aparecer)
  4-6 ¿apareció en el sorteo -1/-2/-3?
  7-11 co-ocurrencia con los 5 números más frecuentes
  12  score Ley de Benford (primer dígito)
  13  paridad (0=par, 1=impar)
"""
import json
import math
import os
import time
from collections import Counter
from itertools import combinations

import numpy as np

from . import memoria as _mem

RUTA_DATA = _mem.RUTA_DATA

N_FEAT = 14   # dimensión del vector de entrada
OCU1   = 48   # neuronas capa oculta 1
OCU2   = 24   # neuronas capa oculta 2


# ─── Persistencia ─────────────────────────────────────────────────────────────

def _ruta_hist(nombre: str) -> str:
    safe = nombre.replace(" ", "_").replace("/", "_")
    return os.path.join(RUTA_DATA, f"loteria_hist_{safe}.json")

def _ruta_pesos(nombre: str) -> str:
    safe = nombre.replace(" ", "_").replace("/", "_")
    return os.path.join(RUTA_DATA, f"loteria_pesos_{safe}.npz")


def cargar_historial(nombre: str) -> list:
    """Carga el historial acumulado en disco ([] si no existe aún)."""
    ruta = _ruta_hist(nombre)
    if not os.path.exists(ruta):
        return []
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _guardar_historial(nombre: str, historial: list):
    os.makedirs(RUTA_DATA, exist_ok=True)
    with open(_ruta_hist(nombre), "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False)


def fusionar(nombre: str, sorteos_nuevos: list) -> tuple:
    """Añade sorteos_nuevos al historial en disco, sin duplicar.

    Devuelve (historial_completo, n_nuevos_reales).
    """
    existentes = cargar_historial(nombre)
    vistos = {tuple(sorted(s)) for s in existentes}
    nuevos = [s for s in sorteos_nuevos if tuple(sorted(s)) not in vistos]
    completo = existentes + nuevos
    _guardar_historial(nombre, completo)
    return completo, len(nuevos)


# ─── Features ─────────────────────────────────────────────────────────────────

def _build_features(candidato: int, historial: list, top5: list) -> np.ndarray:
    n = len(historial)
    if n == 0:
        return np.full(N_FEAT, 0.5, dtype=np.float64)

    todos = [x for s in historial for x in s]
    frec  = Counter(todos)
    total = len(todos) or 1

    # 0) Frecuencia global — escalada para evitar valores mínimos
    f0 = min(1.0, frec.get(candidato, 0) / total * 10.0)

    # 1) Recencia corta (últimos 10 sorteos)
    ul10 = [x for s in historial[-10:] for x in s]
    f1   = min(1.0, ul10.count(candidato) / max(1, len(ul10)) * 10.0)

    # 2) Recencia media (últimos 30 sorteos)
    ul30 = [x for s in historial[-30:] for x in s]
    f2   = min(1.0, ul30.count(candidato) / max(1, len(ul30)) * 10.0)

    # 3) Atraso: sorteos desde la última aparición
    atraso = n   # máximo si nunca apareció
    for i in range(n - 1, -1, -1):
        if candidato in historial[i]:
            atraso = n - 1 - i
            break
    f3 = min(1.0, atraso / max(1, n))

    # 4-6) ¿Apareció en los últimos 1/2/3 sorteos?
    f4 = 1.0 if n >= 1 and candidato in historial[-1] else 0.0
    f5 = 1.0 if n >= 2 and candidato in historial[-2] else 0.0
    f6 = 1.0 if n >= 3 and candidato in historial[-3] else 0.0

    # 7-11) Co-ocurrencia con los 5 más calientes
    pares = Counter()
    for s in historial:
        for par in combinations(sorted(set(s)), 2):
            pares[par] += 1
    max_par = max(pares.values()) if pares else 1
    cooc = []
    for hot in top5[:5]:
        key = tuple(sorted([candidato, hot]))
        cooc.append(pares.get(key, 0) / max_par)
    while len(cooc) < 5:
        cooc.append(0.0)

    # 12) Benford (primer dígito → qué tan "natural" es el número)
    s_str = str(abs(candidato))
    d = int(s_str[0]) if s_str and s_str[0] != "0" else 1
    d = max(1, d)
    f12 = math.log10(1 + 1 / d) / 0.301  # norm. a 1

    # 13) Paridad
    f13 = float(candidato % 2)

    return np.array([f0, f1, f2, f3, f4, f5, f6,
                     *cooc, f12, f13], dtype=np.float64)


# ─── Red neuronal dedicada por lotería ────────────────────────────────────────

class RedLoteria:
    """MLP 2 capas con Adam que aprende patrones de una lotería específica."""

    def __init__(self, nombre: str):
        self.nombre    = nombre
        self.entrenada = False
        self._init_pesos()
        self._cargar_pesos()

    def _init_pesos(self):
        rng      = np.random.default_rng(seed=hash(self.nombre) % (2 ** 32))
        self.W1  = rng.normal(0, np.sqrt(2.0 / N_FEAT), (N_FEAT, OCU1))
        self.b1  = np.zeros(OCU1)
        self.W2  = rng.normal(0, np.sqrt(2.0 / OCU1),  (OCU1,  OCU2))
        self.b2  = np.zeros(OCU2)
        self.W3  = rng.normal(0, np.sqrt(2.0 / OCU2),  (OCU2,  1))
        self.b3  = np.zeros(1)

    def _cargar_pesos(self):
        ruta = _ruta_pesos(self.nombre)
        if not os.path.exists(ruta):
            return
        try:
            d = np.load(ruta, allow_pickle=True)
            if (d["W1"].shape == (N_FEAT, OCU1)
                    and d["W3"].shape == (OCU2, 1)):
                self.W1, self.b1 = d["W1"], d["b1"]
                self.W2, self.b2 = d["W2"], d["b2"]
                self.W3, self.b3 = d["W3"], d["b3"]
                self.entrenada   = bool(d["entrenada"])
        except Exception:
            pass

    def _guardar_pesos(self):
        os.makedirs(RUTA_DATA, exist_ok=True)
        np.savez(_ruta_pesos(self.nombre),
                 W1=self.W1, b1=self.b1,
                 W2=self.W2, b2=self.b2,
                 W3=self.W3, b3=self.b3,
                 entrenada=self.entrenada)

    @staticmethod
    def _sig(z):
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))

    def _forward(self, X):
        a1 = np.tanh(X  @ self.W1 + self.b1)
        a2 = np.tanh(a1 @ self.W2 + self.b2)
        a3 = self._sig(a2 @ self.W3 + self.b3)
        return a1, a2, a3

    def entrenar(self, historial: list,
                 epocas: int = 450, lr: float = 0.003,
                 l2: float = 1e-4, batch: int = 32) -> bool:
        """Entrena con todo el historial acumulado.

        Estrategia de ejemplos:
          positivos: números que SÍ salieron en cada sorteo
          negativos: muestra (2×) de los que NO salieron ese día
        Así la red aprende qué números "debían salir" dado el contexto previo.
        """
        if len(historial) < 8:
            return False

        todos  = [x for s in historial for x in s]
        frec   = Counter(todos)
        pool   = sorted(frec.keys())
        top5   = [n for n, _ in frec.most_common(5)]

        X_list, y_list = [], []
        rng = np.random.default_rng(seed=7)

        for i, sorteo in enumerate(historial):
            contexto = historial[:i]   # sólo el pasado — no hay trampas
            if not contexto:
                continue
            positivos = list(set(sorteo))
            negativos = [c for c in pool if c not in set(sorteo)]
            n_neg = min(len(negativos), len(positivos) * 2)
            if n_neg == 0:
                continue
            neg_sel = rng.choice(negativos, n_neg, replace=False).tolist()

            for num in positivos:
                X_list.append(_build_features(num, contexto, top5))
                y_list.append(1.0)
            for num in neg_sel:
                X_list.append(_build_features(num, contexto, top5))
                y_list.append(0.0)

        if len(X_list) < 20:
            return False

        X   = np.array(X_list, dtype=np.float64)
        y   = np.array(y_list, dtype=np.float64).reshape(-1, 1)
        n   = len(X)
        idx = np.arange(n)

        # ── Adam ──
        mW1, vW1 = np.zeros_like(self.W1), np.zeros_like(self.W1)
        mb1, vb1 = np.zeros_like(self.b1), np.zeros_like(self.b1)
        mW2, vW2 = np.zeros_like(self.W2), np.zeros_like(self.W2)
        mb2, vb2 = np.zeros_like(self.b2), np.zeros_like(self.b2)
        mW3, vW3 = np.zeros_like(self.W3), np.zeros_like(self.W3)
        mb3, vb3 = np.zeros_like(self.b3), np.zeros_like(self.b3)
        t_adam = 0
        b1a, b2a, eps = 0.9, 0.999, 1e-8

        def adam(w, dw, mw, vw):
            mw = b1a * mw + (1 - b1a) * dw
            vw = b2a * vw + (1 - b2a) * dw ** 2
            bc1 = 1 - b1a ** t_adam
            bc2 = 1 - b2a ** t_adam
            return w - lr * (mw / bc1) / (np.sqrt(vw / bc2) + eps), mw, vw

        for _ in range(epocas):
            time.sleep(0)    # cede el GIL entre épocas — no bloquea hilos de trading
            rng.shuffle(idx)
            for start in range(0, n, batch):
                bx = X[idx[start: start + batch]]
                by = y[idx[start: start + batch]]
                nb = max(1, len(bx))
                t_adam += 1
                a1, a2, a3 = self._forward(bx)

                dz3 = (a3 - by) / nb
                dW3 = a2.T @ dz3 + l2 * self.W3
                db3 = dz3.sum(0)
                dz2 = (dz3 @ self.W3.T) * (1 - a2 ** 2)
                dW2 = a1.T @ dz2 + l2 * self.W2
                db2 = dz2.sum(0)
                dz1 = (dz2 @ self.W2.T) * (1 - a1 ** 2)
                dW1 = bx.T @ dz1 + l2 * self.W1
                db1 = dz1.sum(0)

                self.W3, mW3, vW3 = adam(self.W3, dW3, mW3, vW3)
                self.b3, mb3, vb3 = adam(self.b3, db3, mb3, vb3)
                self.W2, mW2, vW2 = adam(self.W2, dW2, mW2, vW2)
                self.b2, mb2, vb2 = adam(self.b2, db2, mb2, vb2)
                self.W1, mW1, vW1 = adam(self.W1, dW1, mW1, vW1)
                self.b1, mb1, vb1 = adam(self.b1, db1, mb1, vb1)

        self.entrenada = True
        self._guardar_pesos()
        return True

    def puntuar(self, candidatos: list, historial: list) -> dict:
        """Devuelve {número: probabilidad_0..1} para cada candidato."""
        if not self.entrenada or not historial or not candidatos:
            return {c: 0.5 for c in candidatos}
        todos = [x for s in historial for x in s]
        top5  = [n for n, _ in Counter(todos).most_common(5)]
        X     = np.array([_build_features(c, historial, top5) for c in candidatos],
                         dtype=np.float64)
        _, _, a3 = self._forward(X)
        return {c: float(a3[i, 0]) for i, c in enumerate(candidatos)}


# ─── Caché global (una instancia por lotería) ─────────────────────────────────

_cache: dict = {}

def _red(nombre: str) -> RedLoteria:
    if nombre not in _cache:
        _cache[nombre] = RedLoteria(nombre)
    return _cache[nombre]


# ─── API pública ──────────────────────────────────────────────────────────────

def aprender(nombre: str, sorteos_nuevos: list) -> tuple:
    """Memoriza sorteos_nuevos y reentrena la red.

    Devuelve (historial_total, n_nuevos, msg_estado).
    """
    historial, n_nuevos = fusionar(nombre, sorteos_nuevos)
    red = _red(nombre)
    ok  = red.entrenar(historial)
    if ok:
        msg = (f"Litch memorizó {len(historial)} sorteos de {nombre} "
               f"(+{n_nuevos} nuevos). Red neuronal reentrenada.")
    else:
        msg = (f"Historial guardado ({len(historial)} sorteos). "
               f"Se necesitan más datos para entrenar la red.")
    return historial, n_nuevos, msg


def predecir_red(nombre: str, historial_externo: list, n: int = 9) -> list:
    """Predicción neuronal pura usando la memoria acumulada + historial externo.

    Devuelve [(numero, score_0_100), ...] de mayor a menor.
    """
    hist_disco     = cargar_historial(nombre)
    hist_unificado = _unir(hist_disco, historial_externo)

    todos = [x for s in hist_unificado for x in s]
    if not todos:
        return []

    candidatos = sorted(set(todos))
    red = _red(nombre)
    if not red.entrenada and len(hist_unificado) >= 8:
        red.entrenar(hist_unificado)

    raw = red.puntuar(candidatos, hist_unificado)
    if not raw:
        return []

    mn  = min(raw.values())
    mx  = max(raw.values())
    rng = mx - mn if mx > mn else 1.0
    norm = {c: int((v - mn) / rng * 100) for c, v in raw.items()}
    return sorted(norm.items(), key=lambda x: x[1], reverse=True)[:n]


def predecir_combinado(nombre: str, historial_externo: list,
                       n: int = 9) -> list:
    """Fusión bayesiana de predictor clásico + red neuronal memorizada.

    Peso: 50% clásico + 50% red (cuando hay suficientes datos).
    Con menos de 15 sorteos en memoria, usa sólo el clásico.

    Devuelve [(numero, score_0_100), ...].
    """
    from . import loteria as _lot

    hist_disco     = cargar_historial(nombre)
    hist_unificado = _unir(hist_disco, historial_externo)

    if not hist_unificado:
        return _lot.predecir(historial_externo, n)

    clasicos_list = _lot.predecir(hist_unificado, n * 2)
    clasicos      = dict(clasicos_list)

    total_disc = len(hist_disco)
    if total_disc < 15:
        # Poca memoria: usar sólo el clásico
        return clasicos_list[:n]

    neuronales_list = predecir_red(nombre, hist_unificado, n * 2)
    neuronales      = dict(neuronales_list)

    todos_c = set(clasicos) | set(neuronales)
    mn_c    = min(clasicos.values(),   default=0)
    mn_n    = min(neuronales.values(), default=0)

    combinado = {}
    for c in todos_c:
        sc = clasicos.get(c,   mn_c)
        sn = neuronales.get(c, mn_n)
        # Peso adaptativo: más neuronal cuanta más memoria haya
        w_neural = min(0.55, 0.30 + total_disc / 500.0)
        w_class  = 1.0 - w_neural
        combinado[c] = int(w_class * sc + w_neural * sn)

    return sorted(combinado.items(), key=lambda x: x[1], reverse=True)[:n]


def estado_memoria(nombre: str) -> dict:
    """Devuelve el estado actual de la memoria de esta lotería."""
    hist = cargar_historial(nombre)
    red  = _red(nombre)
    return {
        "sorteos":   len(hist),
        "entrenada": red.entrenada,
        "nombre":    nombre,
    }


def resumen_memoria(nombre: str) -> str:
    e = estado_memoria(nombre)
    if e["sorteos"] == 0:
        return (f"Sin memoria para {nombre} aún. "
                f"Busca resultados para que Litch empiece a aprender.")
    estado_red = "entrenada y lista" if e["entrenada"] else "necesita más datos"
    return (f"Memoria de {nombre}: {e['sorteos']} sorteos memorizados · "
            f"Red neuronal: {estado_red}.")


def _unir(a: list, b: list) -> list:
    vistos = {tuple(sorted(s)) for s in a}
    extras = [s for s in b if tuple(sorted(s)) not in vistos]
    return a + extras
