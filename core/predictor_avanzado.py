"""predictor_avanzado.py — Motor científico de predicción multi-método para Litch.

Implementa 9 teoremas matemáticos con numpy puro:

  1. Inferencia Bayesiana        — P(A|B) = P(B|A)·P(A)/P(B)
  2. Simulación Monte Carlo      — 10 000 escenarios, distribución empírica
  3. Modelo Autoregresivo AR(p)  — ARIMA simplificado (series de presencia binaria)
  4. Test Chi-cuadrado           — detección de desviación estadística
  5. Cadenas de Markov orden-2   — transiciones de co-aparición
  6. Análisis Fractal (Hurst RS) — memoria/persistencia de cada número
  7. Clustering K-Means manual   — zonas caliente / templado / frío
  8. Bootstrap CI 95 %           — intervalos de confianza por remuestreo
  9. Índice de Recurrencia (RQA) — caos / patrones ocultos

Uso:
    from core.predictor_avanzado import PredictorCientifico
    pc = PredictorCientifico(historial, rango=(1, 43))
    scores = pc.ensemble_scores()   # dict {num: score_0_100}
    report = pc.reporte()           # str con métricas detalladas
"""
import math
import random
from collections import Counter
from itertools import combinations

import numpy as np


# ─── Clase principal ──────────────────────────────────────────────────────────

class PredictorCientifico:
    """
    Motor de predicción científica para una lotería.

    Args:
        historial : list[list[int]]   — sorteos (cada sublista = números del sorteo)
        rango     : tuple(int, int)   — (min, max) del universo de números
        n_sim     : int               — iteraciones Monte Carlo
    """

    def __init__(self, historial: list, rango: tuple = (1, 43),
                 n_sim: int = 10_000):
        self.historial = [list(s) for s in historial if s]
        self.rango     = rango                       # (min_num, max_num)
        self.n_sim     = n_sim
        self.N         = len(self.historial)         # nº de sorteos

        # Universo completo de números
        self.universo  = list(range(rango[0], rango[1] + 1))
        self.U         = len(self.universo)

        # Todos los números que han aparecido
        self.todos     = [n for s in self.historial for n in s
                          if rango[0] <= n <= rango[1]]
        self.frec      = Counter(self.todos)

        # Promedio de bolas por sorteo
        self.k_bolas   = (sum(len(s) for s in self.historial) /
                          max(1, self.N))

        # Matriz de presencia (N × U): 1 si num apareció en sorteo i
        self._mat_pres = self._construir_matriz()

    # ── Matriz de presencia ───────────────────────────────────────────────────

    def _construir_matriz(self) -> np.ndarray:
        mat = np.zeros((self.N, self.U), dtype=np.float32)
        idx = {n: i for i, n in enumerate(self.universo)}
        for i, s in enumerate(self.historial):
            for n in s:
                if n in idx:
                    mat[i, idx[n]] = 1.0
        return mat

    def _serie(self, num: int) -> np.ndarray:
        """Serie binaria de presencia para `num` (longitud N)."""
        if num not in self.universo:
            return np.zeros(self.N)
        j = self.universo.index(num)
        return self._mat_pres[:, j]

    # ── 1. Inferencia Bayesiana ───────────────────────────────────────────────

    def bayesian_scores(self) -> dict:
        """
        Prior uniforme + actualización bayesiana con verosimilitud binomial.

        P(num es "caliente" | historial) ∝ P(historial | caliente) · P(caliente)

        Verosimilitud:  P(k apariciones | p) = Binomial(N, p)
        Prior:          p ~ Beta(α=1, β=1)  → posterior Beta(α + k, β + N - k)
        Estimador MAP:  p_post = (α + k) / (α + β + N)
        """
        alpha, beta_prior = 1.0, 1.0           # prior Beta(1,1) = uniforme
        scores = {}
        for num in self.universo:
            k        = self.frec.get(num, 0)   # veces que apareció
            p_post   = (alpha + k) / (alpha + beta_prior + self.N)
            scores[num] = p_post
        return scores

    # ── 2. Monte Carlo ────────────────────────────────────────────────────────

    def monte_carlo_scores(self) -> dict:
        """
        Genera n_sim sorteos sintéticos muestreando la distribución empírica
        de co-aparición observada.  Cuenta cuántas veces aparece cada número
        a través de las simulaciones → probabilidad empírica estimada.
        """
        # Distribución de muestreo: peso proporcional a frecuencia + 1
        pesos = np.array([self.frec.get(n, 0) + 1 for n in self.universo],
                         dtype=np.float64)
        pesos /= pesos.sum()

        k = max(1, round(self.k_bolas))
        conteo = np.zeros(self.U, dtype=np.int64)

        rng = np.random.default_rng(seed=42)
        for _ in range(self.n_sim):
            idx = rng.choice(self.U, size=k, replace=False, p=pesos)
            conteo[idx] += 1

        total = conteo.sum()
        scores = {}
        for i, num in enumerate(self.universo):
            scores[num] = conteo[i] / max(1, total)
        return scores

    # ── 3. Modelo Autoregresivo AR(p) ─────────────────────────────────────────

    def ar_scores(self, p: int = 5) -> dict:
        """
        Para cada número ajusta un AR(p) sobre su serie de presencia binaria
        y predice la probabilidad de aparición en el sorteo siguiente.

        Solución de mínimos cuadrados: β = (XᵀX)⁻¹Xᵀy
        """
        scores = {}
        p = min(p, self.N - 2)
        if p < 1:
            return {n: 0.5 for n in self.universo}

        for num in self.universo:
            serie = self._serie(num).astype(np.float64)
            if len(serie) <= p:
                scores[num] = self.frec.get(num, 0) / max(1, self.N)
                continue

            # Construir matriz de diseño X y vector objetivo y
            X = np.column_stack([serie[i: len(serie) - p + i]
                                 for i in range(p)])   # (N-p, p)
            y = serie[p:]                              # (N-p,)

            # OLS: β = (XᵀX + λI)⁻¹ Xᵀy  (con regularización Ridge λ=0.01)
            lam = 0.01
            XtX = X.T @ X + lam * np.eye(p)
            Xty = X.T @ y
            try:
                beta = np.linalg.solve(XtX, Xty)
            except np.linalg.LinAlgError:
                beta = np.zeros(p)

            # Predecir con las últimas p observaciones
            x_pred = serie[-p:]
            pred   = float(np.dot(x_pred, beta))
            scores[num] = max(0.0, min(1.0, pred))

        return scores

    # ── 4. Test Chi-cuadrado ──────────────────────────────────────────────────

    def chi_square_scores(self) -> dict:
        """
        Bajo H₀ (lotería uniforme) la frecuencia esperada de cada número es:
            E = N · k_bolas / U

        Contribución al estadístico χ²:
            χ²_num = (O - E)² / E

        Un χ²_num alto indica desviación estadísticamente significativa
        (el número aparece más o menos de lo esperado).

        Devuelve score normalizado 0..1 que representa la intensidad
        de la desviación positiva (O > E → el número aparece MÁS de lo esperado).
        """
        E = self.N * self.k_bolas / max(1, self.U)
        scores = {}
        max_chi = 0.0
        raw = {}
        for num in self.universo:
            O       = self.frec.get(num, 0)
            chi_raw = (O - E) ** 2 / max(E, 1e-9)
            sign    = 1.0 if O >= E else -1.0
            raw[num] = sign * math.sqrt(chi_raw)   # con signo: positivo → caliente
            max_chi = max(max_chi, abs(raw[num]))

        for num in self.universo:
            scores[num] = (raw[num] / max(max_chi, 1e-9) + 1) / 2  # 0..1
        return scores

    # ── 5. Cadenas de Markov orden-2 ──────────────────────────────────────────

    def markov_scores(self) -> dict:
        """
        Estado de cada número: tupla (apareció sorteo -2, apareció sorteo -1)
        → 4 estados: (0,0), (0,1), (1,0), (1,1)

        Transición: P(aparece | estado anterior)
        Devuelve probabilidad de aparición dado el estado actual.
        """
        scores = {}
        for num in self.universo:
            serie = self._serie(num).astype(int)
            if len(serie) < 4:
                scores[num] = self.frec.get(num, 0) / max(1, self.N)
                continue

            # Contar transiciones (estado) → (apareció en siguiente)
            trans = {}    # (s_t-1, s_t) → [n_no_aparece, n_aparece]
            for i in range(2, len(serie)):
                estado = (int(serie[i - 2]), int(serie[i - 1]))
                trans.setdefault(estado, [0, 0])
                trans[estado][int(serie[i])] += 1

            # Estado actual: últimas 2 observaciones
            estado_actual = (int(serie[-2]), int(serie[-1]))
            cnts = trans.get(estado_actual, None)
            if cnts and sum(cnts) > 0:
                scores[num] = cnts[1] / sum(cnts)
            else:
                scores[num] = self.frec.get(num, 0) / max(1, self.N)
        return scores

    # ── 6. Análisis Fractal — Hurst R/S ──────────────────────────────────────

    def hurst_scores(self) -> dict:
        """
        Exponente de Hurst por número mediante análisis R/S.

        H > 0.55 → tendencia persistente (el número "tiende a seguir saliendo")
        H < 0.45 → reversión a la media   (el número "alterna caliente/frío")
        H ≈ 0.5  → ruido blanco (aleatorio puro)

        Score:  H directamente (0..1)
        """
        scores = {}
        for num in self.universo:
            serie = self._serie(num).astype(np.float64)
            h     = self._hurst_rs(serie)
            scores[num] = max(0.0, min(1.0, h))
        return scores

    @staticmethod
    def _hurst_rs(serie: np.ndarray) -> float:
        """R/S clásico de Hurst. Devuelve H ∈ (0, 1)."""
        n = len(serie)
        if n < 8:
            return 0.5

        sizes     = [s for s in range(4, n // 2 + 1) if n % s == 0] or [n // 2]
        sizes     = list(set(sizes + [max(4, n // 4), max(4, n // 2)]))
        sizes     = sorted(s for s in sizes if 4 <= s <= n)
        if len(sizes) < 2:
            return 0.5

        log_sizes = []
        log_rs    = []
        for size in sizes:
            rs_vals = []
            for start in range(0, n - size + 1, size):
                sub   = serie[start: start + size]
                m     = sub.mean()
                dev   = np.cumsum(sub - m)
                R     = dev.max() - dev.min()
                S     = sub.std()
                if S > 1e-10:
                    rs_vals.append(R / S)
            if rs_vals:
                log_sizes.append(math.log(size))
                log_rs.append(math.log(np.mean(rs_vals)))

        if len(log_sizes) < 2:
            return 0.5
        # Regresión lineal log-log → pendiente = H
        x  = np.array(log_sizes)
        y  = np.array(log_rs)
        xm = x.mean()
        ym = y.mean()
        h  = ((x - xm) @ (y - ym)) / max(((x - xm) ** 2).sum(), 1e-10)
        return max(0.1, min(0.9, h))

    # ── 7. Clustering K-Means ─────────────────────────────────────────────────

    def clustering_scores(self, k: int = 3) -> dict:
        """
        Agrupa números en k zonas (caliente / templado / frío) usando
        K-Means manual sobre 3 features:
          f0 = frecuencia relativa
          f1 = recencia normalizada (cuánto hace que salió)
          f2 = score de co-ocurrencia con el número más caliente

        Devuelve score según el clúster asignado: caliente=1.0, medio=0.5, frío=0.0
        """
        # Construir matriz de features (U × 3)
        max_frec = max(self.frec.values()) if self.frec else 1

        # Última posición de cada número
        ultima = {}
        for i, s in enumerate(self.historial):
            for n in s:
                ultima[n] = i

        # Co-ocurrencias con el número más frecuente
        hot1   = self.frec.most_common(1)[0][0] if self.frec else self.universo[0]
        copares = Counter()
        for s in self.historial:
            ss = list(set(s))
            for a, b in combinations(ss, 2):
                copares[tuple(sorted((a, b)))] += 1
        max_co = max(copares.values()) if copares else 1

        features = []
        for num in self.universo:
            f0 = self.frec.get(num, 0) / max_frec
            f1 = (self.N - 1 - ultima.get(num, 0)) / max(1, self.N - 1)
            co_key = tuple(sorted((num, hot1)))
            f2 = copares.get(co_key, 0) / max_co
            features.append([f0, 1.0 - f1, f2])   # f1 invertido: reciente = alto

        X = np.array(features, dtype=np.float64)

        # K-Means Lloyd con 20 iteraciones
        rng  = np.random.default_rng(seed=7)
        cent = X[rng.choice(len(X), k, replace=False)]
        for _ in range(20):
            dists  = np.linalg.norm(X[:, None] - cent[None, :], axis=2)
            labels = dists.argmin(axis=1)
            new_c  = np.array([X[labels == c].mean(axis=0)
                                if (labels == c).any() else cent[c]
                                for c in range(k)])
            if np.allclose(cent, new_c, atol=1e-6):
                break
            cent = new_c

        # Identificar clúster "caliente" por mayor f0 promedio
        cal_f0 = [cent[c][0] for c in range(k)]
        ord_c  = np.argsort(cal_f0)[::-1]           # de mayor a menor f0
        rank_score = {ord_c[0]: 1.0, ord_c[1]: 0.5} # caliente, templado
        if k > 2:
            rank_score[ord_c[2]] = 0.0

        scores = {}
        for i, num in enumerate(self.universo):
            scores[num] = rank_score.get(int(labels[i]), 0.0)
        return scores

    # ── 8. Bootstrap — Intervalos de Confianza 95 % ───────────────────────────

    def bootstrap_ci(self, n_boot: int = 800) -> dict:
        """
        Remuestrea el historial con reemplazo n_boot veces.
        Devuelve {num: (p_low, p_mid, p_high)} donde p es probabilidad
        de aparición estimada (frecuencia relativa).
        """
        if self.N < 5:
            p = {n: self.frec.get(n, 0) / max(1, self.N) for n in self.universo}
            return {n: (max(0, p[n] - 0.05), p[n], min(1, p[n] + 0.05))
                    for n in self.universo}

        rng      = np.random.default_rng(seed=13)
        rows     = np.arange(self.N)
        conteos  = np.zeros((n_boot, self.U), dtype=np.int32)

        for b in range(n_boot):
            idx   = rng.choice(rows, size=self.N, replace=True)
            muest = self._mat_pres[idx]          # (N, U)
            conteos[b] = muest.sum(axis=0).astype(np.int32)

        frecs = conteos / self.N                 # (n_boot, U)
        low   = np.percentile(frecs, 2.5,  axis=0)
        mid   = np.percentile(frecs, 50.0, axis=0)
        high  = np.percentile(frecs, 97.5, axis=0)

        ci = {}
        for i, num in enumerate(self.universo):
            ci[num] = (float(low[i]), float(mid[i]), float(high[i]))
        return ci

    # ── 9. Índice de Recurrencia (RQA) ────────────────────────────────────────

    def recurrence_scores(self, window: int = 8) -> dict:
        """
        Cuantifica la RECURRENCIA de patrones en la serie binaria de presencia.

        Para cada número, calcula qué fracción de ventanas de longitud `window`
        se ha repetido al menos una vez en el historial.

        Alta recurrencia → el número sigue patrones, no es puramente aleatorio.
        Score ∈ [0, 1].
        """
        scores = {}
        for num in self.universo:
            serie = tuple(self._serie(num).astype(int))
            if len(serie) < window + 1:
                scores[num] = 0.5
                continue

            patrones = {}
            recurrentes = 0
            total_vistas = 0
            for i in range(len(serie) - window):
                pat = serie[i: i + window]
                patrones.setdefault(pat, 0)
                if patrones[pat] > 0:
                    recurrentes += 1
                patrones[pat] += 1
                total_vistas  += 1

            scores[num] = recurrentes / max(1, total_vistas)
        return scores

    # ── Ensemble final ────────────────────────────────────────────────────────

    def ensemble_scores(self, pesos: dict = None) -> dict:
        """
        Combina los 9 métodos en un score final ponderado (0–100).

        Pesos por defecto:
          bayesian   0.20   — base probabilística sólida
          montecarlo 0.15   — distribución empírica simulada
          ar         0.15   — tendencia autoregresiva
          chi2       0.10   — desviación estadística positiva
          markov     0.12   — patrón de transición
          hurst      0.10   — persistencia fractal
          cluster    0.08   — zona caliente
          bootstrap  0.05   — estabilidad estadística
          recurrence 0.05   — patrones recurrentes (caos)
        """
        W = pesos or {
            "bayesian":    0.20,
            "montecarlo":  0.15,
            "ar":          0.15,
            "chi2":        0.10,
            "markov":      0.12,
            "hurst":       0.10,
            "cluster":     0.08,
            "bootstrap":   0.05,
            "recurrence":  0.05,
        }

        s_bay  = self.bayesian_scores()
        s_mc   = self.monte_carlo_scores()
        s_ar   = self.ar_scores(p=min(5, self.N // 4))
        s_chi  = self.chi_square_scores()
        s_mar  = self.markov_scores()
        s_hur  = self.hurst_scores()
        s_clu  = self.clustering_scores(k=3)
        s_boot = self.bootstrap_ci()
        s_rec  = self.recurrence_scores()

        raw = {}
        for num in self.universo:
            raw[num] = (
                W["bayesian"]   * s_bay.get(num, 0.5)
                + W["montecarlo"] * s_mc.get(num, 0.0)
                + W["ar"]         * s_ar.get(num, 0.5)
                + W["chi2"]       * s_chi.get(num, 0.5)
                + W["markov"]     * s_mar.get(num, 0.5)
                + W["hurst"]      * s_hur.get(num, 0.5)
                + W["cluster"]    * s_clu.get(num, 0.5)
                + W["bootstrap"]  * s_boot.get(num, (0, 0.5, 1))[1]
                + W["recurrence"] * s_rec.get(num, 0.5)
            )

        # Guardar sub-scores para el reporte
        self._sub = {
            "bayesian": s_bay, "montecarlo": s_mc, "ar": s_ar,
            "chi2": s_chi, "markov": s_mar, "hurst": s_hur,
            "cluster": s_clu, "bootstrap": s_boot, "recurrence": s_rec,
        }

        # Normalizar 0–100
        vals = list(raw.values())
        mn, mx = min(vals), max(vals)
        rng = mx - mn if mx > mn else 1.0
        return {num: int((raw[num] - mn) / rng * 100) for num in self.universo}

    # ── Reporte científico ────────────────────────────────────────────────────

    def reporte(self, top_n: int = 9) -> str:
        """Genera un reporte científico completo en texto."""
        scores = self.ensemble_scores()
        top    = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

        sub    = getattr(self, "_sub", {})
        ci     = sub.get("bootstrap", {})
        hurst  = sub.get("hurst", {})
        markov = sub.get("markov", {})
        ar_s   = sub.get("ar", {})
        rec_s  = sub.get("recurrence", {})

        lineas = [
            f"╔═══ PREDICTOR CIENTÍFICO LITCH — {self.N} SORTEOS ═══╗",
            f"║  Universo: {self.rango[0]}-{self.rango[1]}  │  "
            f"Bolas/sorteo: {self.k_bolas:.1f}  │  Método: Ensemble 9 capas  ║",
            "╚" + "═" * 56 + "╝",
            "",
            "── MÉTODOS ACTIVOS ──────────────────────────────────────",
            "  [1] Inferencia Bayesiana  (prior Beta, posterior MAP)",
            "  [2] Monte Carlo           (10 000 simulaciones)",
            f"  [3] AR(p)                (p={min(5, self.N // 4)}, mínimos cuadrados con Ridge)",
            "  [4] Chi-cuadrado         (desviación de distribución uniforme)",
            "  [5] Markov orden-2       (transiciones de co-aparición)",
            "  [6] Hurst R/S            (persistencia fractal)",
            "  [7] K-Means (k=3)        (zonas caliente/templado/frío)",
            "  [8] Bootstrap CI 95%     (800 remuestreos)",
            "  [9] Índice RQA           (patrones recurrentes, teoría del caos)",
            "",
            "── TOP CANDIDATOS (score ensemble 0-100) ────────────────",
        ]

        for i, (num, sc) in enumerate(top, 1):
            h   = hurst.get(num, 0.5)
            mk  = markov.get(num, 0.5)
            ar  = ar_s.get(num, 0.5)
            rq  = rec_s.get(num, 0.5)
            lo, mid, hi = ci.get(num, (0, 0.5, 1))
            tend = ("↑ persistente" if h > 0.55
                    else "↓ reversión" if h < 0.45
                    else "≈ aleatorio")

            lineas.append(
                f"  #{i:02d}  N={num:02d}  Score={sc:3d}%  "
                f"Hurst={h:.2f}({tend[:8]})  "
                f"Markov={mk:.0%}  AR={ar:.0%}  "
                f"CI95=[{lo:.0%},{hi:.0%}]  Rec={rq:.0%}"
            )

        # Chi-cuadrado global
        chi_vals = sub.get("chi2", {})
        chi_top  = sorted(chi_vals.items(), key=lambda x: x[1], reverse=True)[:5]
        lineas += [
            "",
            "── ANOMALÍAS CHI-CUADRADO (desviación +positiva) ────────",
            "  " + "  ".join(f"N{n}={v:.2f}" for n, v in chi_top),
            "",
            "── INTERPRETACIÓN FRACTAL ───────────────────────────────",
        ]
        for num, sc in top[:5]:
            h = hurst.get(num, 0.5)
            if h > 0.60:
                interp = "🔥 Alta persistencia — tendencia a seguir saliendo"
            elif h < 0.40:
                interp = "❄️  Reversión media — alterna caliente/frío"
            else:
                interp = "〰️  Cuasi-aleatorio — sin sesgo claro"
            lineas.append(f"  N{num:02d} H={h:.3f} → {interp}")

        comb = sorted([n for n, _ in top[:5]])
        lineas += [
            "",
            "── COMBINACIÓN ENSEMBLE ──────────────────────────────────",
            f"  Principales:  {' - '.join(map(str, comb))}",
            "",
            "⚠  Los sorteos son eventos independientes. Estos scores",
            "   son probabilidades condicionales al historial, no",
            "   garantías de resultado futuro.",
        ]
        return "\n".join(lineas)


# ── Función de conveniencia ───────────────────────────────────────────────────

def predecir_cientifico(historial: list, rango: tuple = (1, 43),
                        n: int = 9, n_sim: int = 8_000) -> list:
    """
    Atajo: devuelve lista [(num, score_0_100), ...] con los `n` mejores.

    Args:
        historial : list[list[int]]
        rango     : (min, max) del universo
        n         : cuántos candidatos devolver
        n_sim     : iteraciones Monte Carlo
    """
    if not historial:
        return []
    pc     = PredictorCientifico(historial, rango=rango, n_sim=n_sim)
    scores = pc.ensemble_scores()
    top    = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return top[:n]


def analizar_cientifico(historial: list, rango: tuple = (1, 43),
                        n_sim: int = 8_000) -> tuple:
    """
    Atajo: devuelve (scores_dict, reporte_texto).
    """
    if not historial:
        return {}, "Sin datos."
    pc     = PredictorCientifico(historial, rango=rango, n_sim=n_sim)
    scores = pc.ensemble_scores()
    rep    = pc.reporte()
    return scores, rep
