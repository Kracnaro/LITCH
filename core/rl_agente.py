"""
Agente de Reinforcement Learning — Dueling DQN v3 para trading binario.
Implementación 100% NumPy — compatible con Python 3.14.

Mejoras v3 sobre v2:
  ✦ Estado extendido 37 features — añade RVI, CCI, Fisher RSI, franja horaria
                          y drawdown relativo de sesión. Contexto temporal y
                          de riesgo ahora llegan directamente a la red.
  ✦ Soft target update (Polyak τ=0.01) — actualización suave cada paso,
                          en lugar de copia hard cada 25 pasos. Convergencia
                          más estable en series cortas como las binarias.
  ✦ N-step returns (n=3) — acumula recompensas de 3 pasos antes de estimar
                          el valor target. Reduce el sesgo bootstrapping en
                          episodios cortos (velas de 1-5 minutos).
  ✦ Reward normalización — media y desv. estándar corriente de rewards.
                          Evita que una racha de wins/losses explote los Q-values.
  ✦ Reward shaping mejorado:
      +0.30 SKIP en caos (entropía > 0.85)
      +0.20 SKIP fuera de killzone Y drawdown > 4%  (no operar cuando el mercado es malo Y estás perdiendo)
      -0.25 trade en caos
      -0.40 trade con baja confianza softmax (<35%)
      +0.15 trade en killzone con señal fuerte     (bonus por timing correcto)

Arquitectura Dueling DQN:
  Entrada(37)
    → Troncal: Dense(72 ReLU) → Dense(56 ReLU)
      ├─ Stream Valor:   Dense(28 ReLU) → Dense(1)      V(s)
      └─ Stream Ventaja: Dense(28 ReLU) → Dense(3)      A(s, a)
  Q(s,a) = V(s) + A(s,a) − mean(A(s,:))

Estado (37 features):
  [0:20]  Últimas 20 velas como 0.0/1.0 (secuencia binaria)
  [20]    RSI normalizado [0, 1]
  [21]    Histograma MACD normalizado [0, 1]
  [22]    Posición en Bollinger Bands [0, 1]
  [23]    Stochastic %K normalizado [0, 1]
  [24]    Williams %R normalizado [0, 1]
  [25]    Momentum normalizado [0, 1]
  [26]    ATR normalizado [0, 1]
  [27]    Exponente Hurst [0, 1]          (>0.5 tendencia, <0.5 reversión)
  [28]    Entropía de permutación [0, 1]  (1 = caos, 0 = predecible)
  [29]    ADX normalizado [0, 1]          (fuerza de tendencia)
  [30]    EMA-triple: V=1.0 R=0.0 ?=0.5
  [31]    VWAP bias:  V=1.0 R=0.0 ?=0.5
  [32]    RVI normalizado [0, 1]          ← NUEVO v3
  [33]    CCI normalizado [0, 1]          ← NUEVO v3  (>0.5=overbought, <0.5=oversold)
  [34]    Fisher RSI normalizado [0, 1]   ← NUEVO v3
  [35]    Franja horaria UTC [0, 1]       ← NUEVO v3  (hora_utc / 24)
  [36]    Drawdown sesión [0, 1]          ← NUEVO v3  (0=sin pérdida, 1=en máximo DD)

Recompensas:
  +1.0   trade correcto
  -1.0   trade incorrecto
   0.0   SKIP en condiciones normales
  +0.30  SKIP inteligente en caos
  +0.20  SKIP fuera de killzone con drawdown > 4%
  -0.25  trade en caos
  -0.40  trade con baja confianza softmax (<35%)
  +0.15  trade en killzone activa con fuerte confianza

Persistencia: MEMORIA_AP/rl_agente.json
"""

import json
import os
import time
from collections import deque
import numpy as np

# ── Hiperparámetros ──────────────────────────────────────────────────────────
N_SEQ    = 20       # velas históricas en el estado
N_IND    = 17       # indicadores técnicos (12 anteriores + 5 nuevos v3)
INPUT_N  = N_SEQ + N_IND   # 37 entradas

N_ACCS   = 3        # acciones: SKIP / SUBE / BAJA
GAMMA    = 0.96     # factor de descuento
LR       = 0.0003   # learning rate ligeramente reducido para la red más grande
EPS0     = 0.85     # epsilon inicial
EPS_MIN  = 0.04     # epsilon mínimo
EPS_DEC  = 0.993    # decaimiento por episodio (levemente más rápido en v3)
BATCH    = 32       # muestras por actualización
BUF_MAX  = 5000     # replay buffer más grande para los nuevos features
TGT_TAU  = 0.01     # Polyak tau para soft target update (v3: soft en lugar de hard)
N_STEP   = 3        # N-step returns (v3)
H1, H2   = 72, 56  # troncal más grande para los 37 features
HV, HA   = 28, 28  # streams valor y ventaja
GCLIP    = 0.7      # gradient clipping ligeramente más estricto
PER_ALFA = 0.55     # PER: exponente de prioridad

_ARQU_VERSION = "dueling_v3"   # marcar incompatibilidad con v2

# Umbral de entropía para reward shaping "evitar el caos"
ENTROPIA_CAOS = 0.85


# ── Red Dueling DQN (NumPy puro) ─────────────────────────────────────────────

class _DuelingDQN:
    """
    Arquitectura Dueling DQN:
      Troncal compartido → [Stream Valor V(s)] + [Stream Ventaja A(s,a)]
      Q(s,a) = V(s) + (A(s,a) − mean_a A(s,a))

    Ventaja: el modelo aprende si un estado es bueno en general (V)
    independientemente de qué acción tomar (A). Para trading binario
    esto es crucial: "debo operar ahora?" (V) es distinto a "sube o baja?" (A).
    """

    def __init__(self, seed: int = None):
        if seed is not None:
            np.random.seed(seed)
        # Troncal compartido: INPUT_N → H1 → H2
        self.W1  = np.random.randn(INPUT_N, H1) * np.sqrt(2.0 / INPUT_N)
        self.b1  = np.zeros(H1)
        self.W2  = np.random.randn(H1, H2) * np.sqrt(2.0 / H1)
        self.b2  = np.zeros(H2)
        # Stream valor: H2 → HV → 1
        self.Wv1 = np.random.randn(H2, HV) * np.sqrt(2.0 / H2)
        self.bv1 = np.zeros(HV)
        self.Wv2 = np.random.randn(HV, 1)  * np.sqrt(2.0 / HV)
        self.bv2 = np.zeros(1)
        # Stream ventaja: H2 → HA → N_ACCS
        self.Wa1 = np.random.randn(H2, HA) * np.sqrt(2.0 / H2)
        self.ba1 = np.zeros(HA)
        self.Wa2 = np.random.randn(HA, N_ACCS) * np.sqrt(2.0 / HA)
        self.ba2 = np.zeros(N_ACCS)
        # Adam moments (inicializa al primer uso)
        self._t  = 0
        self._mp = [np.zeros_like(p) for p in self._pvec()]
        self._vp = [np.zeros_like(p) for p in self._pvec()]

    def _pvec(self):
        return [self.W1, self.b1, self.W2, self.b2,
                self.Wv1, self.bv1, self.Wv2, self.bv2,
                self.Wa1, self.ba1, self.Wa2, self.ba2]

    def forward(self, x: np.ndarray):
        """Retorna (Q-values, cache). Cache contiene activaciones para backprop."""
        # Troncal
        z1   = x @ self.W1 + self.b1
        a1   = np.maximum(0.0, z1)
        z2   = a1 @ self.W2 + self.b2
        a2   = np.maximum(0.0, z2)
        # Stream valor
        zv1  = a2 @ self.Wv1 + self.bv1
        av1  = np.maximum(0.0, zv1)
        v    = av1 @ self.Wv2 + self.bv2          # shape (1,)
        # Stream ventaja
        za1  = a2 @ self.Wa1 + self.ba1
        aa1  = np.maximum(0.0, za1)
        adv  = aa1 @ self.Wa2 + self.ba2          # shape (N_ACCS,)
        # Q combinado: V + (A - mean(A))
        q    = v[0] + adv - adv.mean()
        return q, (x, z1, a1, z2, a2, zv1, av1, za1, aa1, v, adv)

    def backward(self, cache, dq: np.ndarray):
        """Backpropagation completa a través de los dos streams."""
        x, z1, a1, z2, a2, zv1, av1, za1, aa1, v, adv = cache

        # Gradiente de Q = v + adv - mean(adv)
        # dQ/dadv[i] = 1 - 1/N_ACCS para i=a, -1/N_ACCS para otros
        # Aquí dq es el gradiente externo, se aplica proporcional
        # dQ/dv = 1  →  dv = dq.sum()
        dv_out   = np.array([dq.sum()])
        dadv_out = dq - dq.mean()  # gradiente sobre adv (descentrado)

        # Stream valor: backprop
        dWv2 = np.outer(av1, dv_out)
        dbv2 = dv_out.copy()
        dav1 = self.Wv2 @ dv_out
        dzv1 = dav1 * (zv1 > 0)
        dWv1 = np.outer(a2, dzv1)
        dbv1 = dzv1.copy()
        da2_v = self.Wv1 @ dzv1

        # Stream ventaja: backprop
        dWa2 = np.outer(aa1, dadv_out)
        dba2 = dadv_out.copy()
        daa1 = self.Wa2 @ dadv_out
        dza1 = daa1 * (za1 > 0)
        dWa1 = np.outer(a2, dza1)
        dba1 = dza1.copy()
        da2_a = self.Wa1 @ dza1

        # Troncal: combinar gradientes de ambos streams
        da2  = da2_v + da2_a
        dz2  = da2 * (z2 > 0)
        dW2  = np.outer(a1, dz2)
        db2  = dz2.copy()
        da1  = self.W2 @ dz2
        dz1  = da1 * (z1 > 0)
        dW1  = np.outer(x, dz1)
        db1  = dz1.copy()

        # Paso Adam con gradient clipping
        self._t += 1
        b1t = 0.9   ** self._t
        b2t = 0.999 ** self._t
        gs  = [dW1, db1, dW2, db2,
               dWv1, dbv1, dWv2, dbv2,
               dWa1, dba1, dWa2, dba2]
        for i, (p, g) in enumerate(zip(self._pvec(), gs)):
            g = np.clip(g, -GCLIP, GCLIP)
            self._mp[i] = 0.9   * self._mp[i] + 0.1    * g
            self._vp[i] = 0.999 * self._vp[i] + 0.001  * g * g
            mh = self._mp[i] / (1.0 - b1t)
            vh = self._vp[i] / (1.0 - b2t)
            p -= LR * mh / (np.sqrt(vh) + 1e-8)

    def clone_weights(self, src: '_DuelingDQN'):
        for dp, sp in zip(self._pvec(), src._pvec()):
            dp[:] = sp

    def to_dict(self) -> dict:
        return {k: getattr(self, k).tolist()
                for k in ("W1","b1","W2","b2",
                           "Wv1","bv1","Wv2","bv2",
                           "Wa1","ba1","Wa2","ba2")}

    def from_dict(self, d: dict):
        keys = ("W1","b1","W2","b2",
                "Wv1","bv1","Wv2","bv2",
                "Wa1","ba1","Wa2","ba2")
        for k in keys:
            if k not in d:
                raise ValueError(f"Clave faltante en checkpoint: {k}")
            arr = np.array(d[k], dtype=float)
            # Verificar forma compatible
            expected = getattr(self, k).shape
            if arr.shape != expected:
                raise ValueError(f"{k}: forma {arr.shape} ≠ esperada {expected}")
            setattr(self, k, arr)
        self._mp = [np.zeros_like(p) for p in self._pvec()]
        self._vp = [np.zeros_like(p) for p in self._pvec()]
        self._t  = 0


# ── Agente RL ────────────────────────────────────────────────────────────────

class AgenteRL:
    """
    Agente Dueling DQN para trading binario (V/R).

    API pública idéntica a la versión anterior — cambio transparente.
    """

    ACCION_SKIP = 0
    ACCION_SUBE = 1
    ACCION_BAJA = 2

    def __init__(self, ruta: str = None):
        self.red    = _DuelingDQN()
        self.target = _DuelingDQN()
        self.target.clone_weights(self.red)
        self.epsilon  = EPS0
        self.episodio = 0
        self.pasos    = 0
        self.ruta     = ruta
        # Replay buffer con deque
        self._buf    = deque(maxlen=BUF_MAX)
        self._priors = deque(maxlen=BUF_MAX)
        # Historial de trades
        self._trades = deque(maxlen=500)
        # Racha reciente de pérdidas (para epsilon adaptativo)
        self._racha_loss = 0
        # Entropía del último estado (para reward shaping)
        self._ult_entropia = 0.5
        # N-step buffer: [(s, a, r)] — acumula antes de insertar al replay
        self._nstep_buf: list = []
        # Normalización corriente de rewards
        self._reward_m  = 0.0   # media
        self._reward_s2 = 1.0   # varianza (welford)
        self._reward_n  = 0

        if ruta and os.path.exists(ruta):
            self._cargar()

    # ── Decidir ──────────────────────────────────────────────────────────────

    def decidir(self, sec: list, ind: dict = None) -> int:
        s = self._estado(sec, ind)
        if s is None:
            return self.ACCION_SKIP
        if np.random.random() < self.epsilon:
            return int(np.random.choice([0, 1, 2]))
        q, _ = self.red.forward(s)
        return int(np.argmax(q))

    def decidir_con_confianza(self, sec: list, ind: dict = None):
        """Devuelve (accion, confianza, q_values)."""
        s = self._estado(sec, ind)
        if s is None:
            return self.ACCION_SKIP, 0.0, np.zeros(N_ACCS)
        # Evitar exploración aleatoria en la inferencia (siempre greedy aquí)
        q, _ = self.red.forward(s)
        a    = int(np.argmax(q))
        eq   = np.exp(q - q.max())
        prob = eq / eq.sum()
        conf = float(prob[a])
        return a, conf, q

    # ── Aprender ─────────────────────────────────────────────────────────────

    def aprender(self, sec_ant: list, accion: int, reward: float,
                 sec_nuevo: list, ind_ant: dict = None,
                 ind_nuevo: dict = None, done: bool = False,
                 en_killzone: bool = False, dd_pct: float = 0.0):
        """Registra experiencia con reward shaping v3 y ejecuta entrenamiento.

        Nuevos parámetros:
            en_killzone : True si la killzone SMC/LWS está activa
            dd_pct      : drawdown de sesión como fracción [0, 1]
        """
        s  = self._estado(sec_ant,   ind_ant,  dd_pct=dd_pct)
        s2 = self._estado(sec_nuevo, ind_nuevo, dd_pct=dd_pct)
        if s is None or s2 is None:
            return

        # ── Reward shaping v3 ─────────────────────────────────────────────
        _ind_ant        = ind_ant or {}
        entropia_ant    = float(_ind_ant.get("entropia_perm") or self._ult_entropia)
        hurst_ant       = float(_ind_ant.get("hurst") or 0.5)
        mercado_caotico = entropia_ant > ENTROPIA_CAOS
        mercado_random  = hurst_ant < 0.45 and entropia_ant > 0.78

        q, _ = self.red.forward(s)

        if accion == self.ACCION_SKIP:
            if mercado_caotico or mercado_random:
                reward = 0.30
            elif not en_killzone and dd_pct > 0.04:
                # Buen SKIP: fuera de killzone y ya estamos en drawdown
                reward = max(reward, 0.20)
        else:
            if mercado_caotico:
                reward -= 0.25
            # Penalizar baja confianza softmax
            eq   = np.exp(q - q.max())
            conf = float((eq / eq.sum())[accion])
            if conf < 0.35:
                reward -= 0.40
            elif en_killzone and conf > 0.60:
                # Bonus por operar en buen momento con convicción
                reward += 0.15

        # ── Normalización de reward (Welford) ─────────────────────────────
        self._reward_n += 1
        delta = reward - self._reward_m
        self._reward_m  += delta / self._reward_n
        delta2 = reward - self._reward_m
        self._reward_s2 += delta * delta2
        std = max(0.5, float(np.sqrt(self._reward_s2 / max(1, self._reward_n - 1))))
        reward_norm = float(np.clip(reward / std, -3.0, 3.0))

        # ── N-step buffer ─────────────────────────────────────────────────
        self._nstep_buf.append((s, accion, reward_norm))
        if len(self._nstep_buf) >= N_STEP or done:
            # Calcular retorno acumulado para los primeros pasos del buffer
            g = 0.0
            for i, (_, _, r) in enumerate(reversed(self._nstep_buf)):
                g = r + GAMMA * g
            s0, a0, _ = self._nstep_buf[0]
            self._nstep_buf.pop(0)

            # Calcular prioridad PER
            if done:
                td_est = abs(g - float(q[a0]))
            else:
                q2_main, _ = self.red.forward(s2)
                q2_tgt, _  = self.target.forward(s2)
                td_est = abs(g + (GAMMA ** N_STEP) * float(q2_tgt[int(np.argmax(q2_main))])
                             - float(q[a0]))
            prioridad = (td_est + 1e-4) ** PER_ALFA

            self._buf.append((s0, a0, g, s2, done))
            self._priors.append(prioridad)

        if accion != self.ACCION_SKIP:
            self._trades.append((accion, reward))
            if reward < 0:
                self._racha_loss += 1
                if self._racha_loss >= 4 and self.epsilon < 0.45:
                    self.epsilon = min(0.45, self.epsilon * 1.30)
            else:
                self._racha_loss = 0

        if len(self._buf) >= BATCH:
            self._entrenar()

        # ── Soft target update (Polyak τ=0.01) — reemplaza hard copy ─────
        for dp, sp in zip(self.target._pvec(), self.red._pvec()):
            dp[:] = (1.0 - TGT_TAU) * dp + TGT_TAU * sp

        self.pasos    += 1
        self.episodio += 1
        if self.epsilon > EPS_MIN:
            self.epsilon = max(EPS_MIN, self.epsilon * EPS_DEC)

        if self.ruta and self.episodio % 25 == 0:
            self._guardar()

    # ── Métricas ─────────────────────────────────────────────────────────────

    def precision(self, ultimos: int = 50) -> float:
        trades = [r for _, r in list(self._trades)[-ultimos:] if _ != 0]
        if not trades:
            return 0.5
        return float(sum(1 for r in trades if r > 0) / len(trades))

    def estado_resumen(self) -> str:
        n_trades = len(self._trades)
        prec     = self.precision()
        return (f"RL-DuelingDQN: ep={self.episodio} ε={self.epsilon:.3f} "
                f"trades={n_trades} prec={int(prec*100)}% "
                f"buf={len(self._buf)}/{BUF_MAX}")

    # ── Construcción de estado ────────────────────────────────────────────────

    def _estado(self, sec: list, ind: dict = None,
                dd_pct: float = 0.0) -> np.ndarray | None:
        if len(sec) < N_SEQ:
            return None
        velas = np.array([1.0 if c == 'V' else 0.0
                          for c in sec[-N_SEQ:]], dtype=float)
        inds  = self._norm_ind(ind or {}, dd_pct=dd_pct)
        estado = np.concatenate([velas, inds])
        self._ult_entropia = float(inds[8])  # [28] entropía_perm
        return estado

    @staticmethod
    def _norm_ind(ind: dict, dd_pct: float = 0.0) -> np.ndarray:
        """Normaliza 17 indicadores a [0, 1]. Valores ausentes → 0.5."""
        def _n(k, lo, hi, df=0.5):
            v = ind.get(k)
            if v is None:
                return df
            return float(np.clip((v - lo) / (hi - lo + 1e-9), 0.0, 1.0))

        def _dir(k, df=0.5):
            v = ind.get(k)
            if v == "V":   return 1.0
            if v == "R":   return 0.0
            return df

        hora_utc = float(time.gmtime().tm_hour) / 24.0   # franja temporal

        return np.array([
            # ─ Indicadores clásicos ─────────────────────────────────────────
            _n("rsi",       0,    100,   0.5),   # [0]
            _n("macd_h",   -5,    5,     0.5),   # [1]
            _n("bb",        0,    1,     0.5),   # [2]
            _n("stoch_k",   0,    100,   0.5),   # [3]
            _n("wr",       -100,  0,     0.5),   # [4]
            _n("mom",      -10,   10,    0.5),   # [5]
            # ─ Indicadores de régimen ────────────────────────────────────────
            _n("atr",       0,    5,     0.5),   # [6]  ATR
            _n("hurst",     0,    1,     0.5),   # [7]  Hurst
            _n("entropia_perm", 0, 1,    0.5),   # [8]  Entropía
            _n("adx_fuerza", 0,  100,    0.3),   # [9]  ADX
            _dir("ema_triple"),                  # [10] EMA triple cruce
            _dir("vwap_bias"),                   # [11] VWAP sesgo
            # ─ Indicadores nuevos v3 ─────────────────────────────────────────
            _n("rvi",      -1,    1,     0.5),   # [12] Relative Vigor Index
            _n("cci",     -200,  200,    0.5),   # [13] CCI (>0.5=overbought)
            _n("fisher",   -3,    3,     0.5),   # [14] Fisher RSI transform
            float(hora_utc),                     # [15] Franja horaria UTC [0,1]
            float(np.clip(dd_pct, 0.0, 1.0)),   # [16] Drawdown de sesión [0,1]
        ], dtype=float)

    # ── Entrenamiento (Double DQN + PER) ─────────────────────────────────────

    def _entrenar(self):
        # Snapshot a lista para acceso O(1) — la deque tiene O(n) por índice
        buf_list = list(self._buf)
        n     = len(buf_list)
        probs = np.array(self._priors, dtype=float)
        probs /= (probs.sum() + 1e-9)
        idx   = np.random.choice(n, BATCH, replace=False, p=probs)
        for i in idx:
            s, a, r, s2, done = buf_list[i]
            q, cache = self.red.forward(s)
            if done:
                target_q = r
            else:
                # Double Q: elegir acción con red principal, evaluar con target
                q2_main, _ = self.red.forward(s2)
                a_max      = int(np.argmax(q2_main))
                q2_tgt, _  = self.target.forward(s2)
                target_q   = r + GAMMA * float(q2_tgt[a_max])

            td   = target_q - float(q[a])
            self._priors[i] = (abs(td) + 1e-4) ** PER_ALFA

            dq    = np.zeros(N_ACCS)
            dq[a] = -td
            self.red.backward(cache, dq)

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _guardar(self):
        try:
            d = {
                "arquitectura": _ARQU_VERSION,
                "input_n":    INPUT_N,
                "red":        self.red.to_dict(),
                "epsilon":    float(self.epsilon),
                "episodio":   int(self.episodio),
                "pasos":      int(self.pasos),
                "trades":     list(self._trades)[-200:],
                "reward_m":   float(self._reward_m),
                "reward_s2":  float(self._reward_s2),
                "reward_n":   int(self._reward_n),
            }
            with open(self.ruta, "w", encoding="utf-8") as f:
                json.dump(d, f)
        except Exception as e:
            print(f"[RL] Error al guardar: {e}")

    def _cargar(self):
        try:
            with open(self.ruta, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("arquitectura") != _ARQU_VERSION or d.get("input_n") != INPUT_N:
                print(f"[RL] Checkpoint incompatible "
                      f"(arq={d.get('arquitectura')} "
                      f"in={d.get('input_n')}≠{INPUT_N}) — "
                      f"iniciando {_ARQU_VERSION} desde cero.")
                return
            self.red.from_dict(d["red"])
            self.target.clone_weights(self.red)
            self.epsilon    = float(d.get("epsilon",  EPS_MIN))
            self.episodio   = int(d.get("episodio", 0))
            self.pasos      = int(d.get("pasos",    0))
            self._trades    = deque(d.get("trades", []), maxlen=500)
            self._reward_m  = float(d.get("reward_m",  0.0))
            self._reward_s2 = float(d.get("reward_s2", 1.0))
            self._reward_n  = int(d.get("reward_n",    0))
            print(f"[RL] {_ARQU_VERSION} cargado — ep={self.episodio} "
                  f"ε={self.epsilon:.3f} trades={len(self._trades)}")
        except Exception as e:
            print(f"[RL] No se pudo cargar pesos (reentrenando desde cero): {e}")
