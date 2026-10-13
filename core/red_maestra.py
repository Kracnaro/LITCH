"""Red Maestra de Litch — Ensemble CNN-1D + LSTM + MLP + Meta-Red con Bagging.

Arquitectura del cerebro digital:
  Red A × 3  →  Pattern Detector  (últimas 10 velas, fingerprint de patrones)
  Red B × 3  →  LSTM Temporal     (últimas 30 velas, memoria de secuencias)
  Red C × 3  →  Statistical MLP   (28 features estadísticos)
  Meta  × 1  →  Synthesizer       (9 votos + contexto de mercado → decisión)
              ──────────────────────────────────────────────
              Total: 10 modelos coordinados en un solo cerebro digital

Bagging: cada arquitectura se entrena en 3 muestras bootstrap independientes.
  → 9 modelos base, cada uno ve datos ligeramente distintos.
  → La meta-red aprende cuál modelo vale más en cada condición de mercado.
  → Reduce el overfitting drásticamente (varianza ÷ N_BOOTSTRAP).

Error Memory: cada patrón fallido aumenta su peso hasta 4× en reentrenamiento.
  → Litch aprende de cada error y no lo vuelve a cometer igual.

Progress Tracker: precisión rolling-50, rolling-100, rolling-200 y total.
  → Medición continua del avance del cerebro.

Todo en NumPy puro — compatible con Python 3.14 (sin PyTorch necesario).
Inferencia ≈ 2-5 ms para los 10 modelos en CPU.
"""
import json
import os
import threading
import time

import numpy as np

from . import memoria as _mem

# ── Rutas de persistencia ─────────────────────────────────────────────────────
RUTA_PESOS = os.path.join(_mem.RUTA_DATA, "red_maestra_pesos.npz")
RUTA_STATS = os.path.join(_mem.RUTA_DATA, "red_maestra_stats.json")

# ── Hiperparámetros globales ──────────────────────────────────────────────────
SEQ_A   = 10   # CNN: ventana de los últimas N velas
SEQ_B   = 30   # LSTM: secuencia temporal de N velas
N_FEAT_C = 28  # MLP estadístico: número de features
N_BOOT   = 3   # Variantes bootstrap por arquitectura
LR_BASE  = 0.001
GRAD_CLIP = 5.0
MIN_TRAIN = 25  # mínimo de velas para empezar a entrenar


# ── Activaciones y utilidades ─────────────────────────────────────────────────

def _sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def _tanh(x):
    return np.tanh(np.clip(x, -50.0, 50.0))


def _relu(x):
    return np.maximum(0.0, x)


def _he(n_in, n_out):
    return np.random.randn(n_out, n_in) * np.sqrt(2.0 / n_in)


def _to_bin(seq) -> np.ndarray:
    """Convierte lista de 'V'/'R' o 0/1 a array float32."""
    out = []
    for v in seq:
        if isinstance(v, str):
            out.append(1.0 if v == "V" else 0.0)
        else:
            out.append(float(v))
    return np.array(out, dtype=np.float32)


# ── Adam Optimizer ────────────────────────────────────────────────────────────

_L2_LAMBDA   = 1e-4   # L2 regularization: λ|w|² — penaliza pesos grandes
_DROPOUT_P   = 0.12   # probabilidad de zeroing en Monte Carlo Dropout
_EARLY_PAT   = 5      # early stopping: épocas de paciencia sin mejora


class _Adam:
    def __init__(self, params, lr=LR_BASE, b1=0.9, b2=0.999, eps=1e-8,
                 l2=_L2_LAMBDA):
        self.lr  = lr
        self.b1  = b1
        self.b2  = b2
        self.eps = eps
        self.l2  = l2    # L2 regularization lambda
        self.t   = 0
        self.m   = [np.zeros_like(p) for p in params]
        self.v   = [np.zeros_like(p) for p in params]

    def step(self, params, grads):
        self.t += 1
        b1t = self.b1 ** self.t
        b2t = self.b2 ** self.t
        for idx, (p, g) in enumerate(zip(params, grads)):
            # L2 regularization: solo en pesos (matrices 2D), no en biases (1D)
            if self.l2 > 0 and p.ndim == 2:
                g = g + self.l2 * p
            gc = np.clip(g, -GRAD_CLIP, GRAD_CLIP)
            self.m[idx] = self.b1 * self.m[idx] + (1.0 - self.b1) * gc
            self.v[idx] = self.b2 * self.v[idx] + (1.0 - self.b2) * gc * gc
            mh = self.m[idx] / (1.0 - b1t)
            vh = self.v[idx] / (1.0 - b2t)
            p -= self.lr * mh / (np.sqrt(vh) + self.eps)


def _apply_dropout(a: np.ndarray, training: bool) -> np.ndarray:
    """Monte Carlo Dropout: durante entrenamiento zeroa neuronas con p=_DROPOUT_P.
    Durante inferencia escala por (1 - _DROPOUT_P) para mantener esperanza."""
    if training:
        mask = (np.random.rand(*a.shape) > _DROPOUT_P).astype(np.float32)
        return a * mask
    return a * (1.0 - _DROPOUT_P)


# ── Feature extractors ────────────────────────────────────────────────────────

def _feats_A(seq_bin: np.ndarray) -> np.ndarray:
    """23 features de patrón local para Red A (CNN-style).

    Captura: raw 10 velas + 2-grams + one-hot del patrón de las últimas 3
    velas + momentum local. Equivalent to what a 1-D CNN kernel would detect.
    """
    n = SEQ_A
    if len(seq_bin) >= n:
        s = seq_bin[-n:].copy()
    else:
        pad = np.zeros(n - len(seq_bin), dtype=np.float32)
        s = np.concatenate([pad, seq_bin])

    # (10) Raw sequence
    raw = s.astype(np.float32)

    # (4) 2-gram frequencies: GG GR RG RR
    if len(s) > 1:
        pairs = np.array([
            np.sum((s[:-1] == 1) & (s[1:] == 1)),
            np.sum((s[:-1] == 1) & (s[1:] == 0)),
            np.sum((s[:-1] == 0) & (s[1:] == 1)),
            np.sum((s[:-1] == 0) & (s[1:] == 0)),
        ], dtype=np.float32) / (len(s) - 1)
    else:
        pairs = np.array([0.25, 0.25, 0.25, 0.25], dtype=np.float32)

    # (8) One-hot del patrón de las últimas 3 velas (2³ = 8 posibles)
    last3 = s[-3:].astype(int)
    idx3  = last3[0] * 4 + last3[1] * 2 + last3[2]
    oh3   = np.zeros(8, dtype=np.float32)
    oh3[idx3] = 1.0

    # (1) Momentum local (últimas 3 vs últimas 7)
    mom = float(np.mean(s[-3:])) - float(np.mean(s[-7:])) if len(s) >= 7 else 0.0

    return np.concatenate([raw, pairs, oh3, [mom]])  # 23 features


def _feats_C(seq) -> np.ndarray:
    """28 features estadísticos para Red C.

    Incluye: raw-14, run_length, momentum(5/12/25), Shannon entropy,
    EWMA crossover, alternación, densidades, trend, std.
    """
    sb = _to_bin(seq)
    n  = len(sb)

    # Pad si falta historia
    if n < 30:
        sb = np.concatenate([np.full(30 - n, 0.5, dtype=np.float32), sb])

    s30 = sb[-30:]; s20 = sb[-20:]; s14 = sb[-14:]
    s12 = sb[-12:]; s10 = sb[-10:]; s7  = sb[-7:]
    s5  = sb[-5:];  s3  = sb[-3:]

    # (14) Raw últimas 14
    raw14 = s14.astype(np.float32)

    # (1) Run length normalizado
    run = 1
    for i in range(len(sb) - 2, -1, -1):
        if sb[i] == sb[-1]:
            run += 1
        else:
            break
    run_n = float(min(run, 15)) / 15.0

    # (3) Momentum en ventanas 5, 12, 25
    mom5  = float(np.mean(s5)) - float(np.mean(sb[-10:-5]))
    mom12 = float(np.mean(s12)) - float(np.mean(sb[-24:-12])) if len(sb) >= 24 else 0.0
    mom25 = float(np.mean(sb[-25:])) - 0.5 if len(sb) >= 25 else 0.0

    # (1) Shannon entropy (últimas 20)
    # Guardamos frente a NaN (historial corto) y p=0/1 exactos (todas las velas iguales)
    _p_raw = float(np.mean(s20)) if len(s20) >= 2 else 0.5
    if not np.isfinite(_p_raw):
        _p_raw = 0.5
    p = np.clip(_p_raw, 1e-7, 1.0 - 1e-7)
    with np.errstate(divide="ignore", invalid="ignore"):
        ent = -(p * np.log2(p) + (1.0 - p) * np.log2(1.0 - p))
    if not np.isfinite(ent):
        ent = 1.0   # entropía máxima cuando no se puede calcular

    # (1) EWMA crossover
    def _ewma(a, alpha):
        e = float(a[0])
        for x in a[1:]:
            e = alpha * float(x) + (1.0 - alpha) * e
        return e

    ewma_fast = _ewma(s10, 0.30)
    ewma_slow = _ewma(s20, 0.10)
    ewma_x    = ewma_fast - ewma_slow

    # (1) Alternation rate (últimas 7)
    alt = float(np.sum(np.diff(s7) != 0)) / 6.0 if len(s7) >= 2 else 0.5

    # (3) Green density en ventanas 5, 10, 20
    d5  = float(np.mean(s5))
    d10 = float(np.mean(s10))
    d20 = float(np.mean(s20))

    # (1) Switching frequency últimas 20
    sw = float(np.sum(np.diff(s20) != 0)) / 19.0 if len(s20) >= 2 else 0.5

    # (1) Linear trend últimas 5
    xi   = np.arange(len(s5), dtype=np.float32)
    trend = float(np.polyfit(xi, s5, 1)[0]) if len(s5) >= 2 else 0.0

    # (1) Recent vs long-term difference
    diff_avg = float(np.mean(s5)) - float(np.mean(s30))

    # (1) Std últimas 10
    std10 = float(np.std(s10))

    return np.array([
        *raw14,
        run_n, mom5, mom12, mom25, ent, ewma_x,
        alt, d5, d10, d20, sw, trend, diff_avg, std10,
    ], dtype=np.float32)  # 14 + 14 = 28


# ── Red A: Pattern Detector (MLP sobre CNN-style features) ──────────────────

class _RedA:
    """MLP 23→32→16→1 entrenada sobre fingerprint de patrones locales."""

    N_IN = 23

    def __init__(self, lr=LR_BASE):
        self.W1 = _he(self.N_IN, 32)
        self.b1 = np.zeros(32)
        self.W2 = _he(32, 16)
        self.b2 = np.zeros(16)
        self.W3 = _he(16, 1)
        self.b3 = np.zeros(1)
        self._opt = _Adam(self._p(), lr)

    def _p(self):
        return [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]

    def predict(self, seq_bin) -> float:
        sb = _to_bin(seq_bin) if not isinstance(seq_bin, np.ndarray) else seq_bin
        x  = _feats_A(sb)
        a1 = _relu(self.W1 @ x + self.b1)
        a2 = _relu(self.W2 @ a1 + self.b2)
        return float(_sig(self.W3 @ a2 + self.b3)[0])

    def train_one(self, seq_bin, y_true: float, w: float = 1.0):
        sb = _to_bin(seq_bin) if not isinstance(seq_bin, np.ndarray) else seq_bin
        x  = _feats_A(sb)
        a1 = _relu(self.W1 @ x + self.b1)
        a2 = _relu(self.W2 @ a1 + self.b2)
        y  = _sig(self.W3 @ a2 + self.b3)[0]

        err = (y - y_true) * w
        dW3 = err * a2.reshape(1, -1)
        db3 = np.array([err])
        d2  = (self.W3.T * err).flatten() * (a2 > 0)
        dW2 = np.outer(d2, a1)
        db2 = d2.copy()
        d1  = (self.W2.T @ d2) * (a1 > 0)
        dW1 = np.outer(d1, x)
        db1 = d1.copy()
        self._opt.step(self._p(), [dW1, db1, dW2, db2, dW3, db3])

    def train(self, seqs, labels, weights=None, epochs=50):
        if weights is None:
            weights = np.ones(len(seqs))
        for _ in range(epochs):
            for i in np.random.permutation(len(seqs)):
                self.train_one(seqs[i], float(labels[i]), float(weights[i]))


# ── Red B: LSTM Temporal Memory ───────────────────────────────────────────────

class _RedB_LSTM:
    """LSTM(hidden=16) de una capa → Dense → sigmoid. BPTT truncado 10 pasos."""

    def __init__(self, seq_len=SEQ_B, hidden=16, lr=LR_BASE):
        self.seq_len = seq_len
        self.hs = hidden
        self.lr = lr
        c = hidden + 1  # concat dim: hidden + 1 input feature
        sc = 0.08
        self.Wf = np.random.randn(hidden, c) * sc
        self.Wi = np.random.randn(hidden, c) * sc
        self.Wg = np.random.randn(hidden, c) * sc
        self.Wo = np.random.randn(hidden, c) * sc
        self.bf = np.zeros(hidden)
        self.bi = np.zeros(hidden)
        self.bg = np.zeros(hidden)
        self.bo = np.zeros(hidden)
        self.Wy = np.random.randn(1, hidden) * sc
        self.by = np.zeros(1)
        self._opt = _Adam(self._p(), lr)

    def _p(self):
        return [self.Wf, self.Wi, self.Wg, self.Wo,
                self.bf, self.bi, self.bg, self.bo,
                self.Wy, self.by]

    def _forward(self, seq_bin):
        sb = _to_bin(seq_bin) if not isinstance(seq_bin, np.ndarray) else seq_bin
        T  = min(len(sb), self.seq_len)
        data = sb[-T:].astype(np.float32)
        h, c = np.zeros(self.hs), np.zeros(self.hs)
        cache = []
        for t in range(T):
            x = np.array([data[t]], dtype=np.float32)
            z = np.concatenate([h, x])
            f  = _sig(self.Wf @ z + self.bf)
            i  = _sig(self.Wi @ z + self.bi)
            g  = _tanh(self.Wg @ z + self.bg)
            o  = _sig(self.Wo @ z + self.bo)
            c2 = f * c + i * g
            h2 = o * _tanh(c2)
            cache.append((z, f, i, g, o, c, c2, h, h2))
            h, c = h2, c2
        y = _sig(self.Wy @ h + self.by)[0]
        return float(y), cache, h

    def predict(self, seq_bin) -> float:
        y, _, _ = self._forward(seq_bin)
        return y

    def train_one(self, seq_bin, y_true: float, w: float = 1.0):
        y, cache, h_last = self._forward(seq_bin)
        T = len(cache)
        if T == 0:
            return

        # Output layer gradient
        d_out = (y - y_true) * w
        dWy = d_out * h_last.reshape(1, -1)
        dby = np.array([d_out])
        dh  = (self.Wy.T * d_out).flatten()
        dc  = np.zeros(self.hs)

        dWf = np.zeros_like(self.Wf); dWi = np.zeros_like(self.Wi)
        dWg = np.zeros_like(self.Wg); dWo = np.zeros_like(self.Wo)
        dbf = np.zeros_like(self.bf); dbi = np.zeros_like(self.bi)
        dbg = np.zeros_like(self.bg); dbo = np.zeros_like(self.bo)

        # Truncated BPTT — last min(T, 10) steps
        for t in reversed(range(max(0, T - 10), T)):
            z, f, i, g, o, c_prev, c_curr, h_prev, h_curr = cache[t]
            tc = _tanh(c_curr)

            do  = dh * tc
            dc += dh * o * (1.0 - tc * tc)
            df  = dc * c_prev
            di  = dc * g
            dg_ = dc * i
            dc  = dc * f  # gradient to previous cell

            do_p = do  * o * (1.0 - o)
            df_p = df  * f * (1.0 - f)
            di_p = di  * i * (1.0 - i)
            dg_p = dg_ * (1.0 - g * g)

            dWf += np.outer(df_p, z)
            dWi += np.outer(di_p, z)
            dWg += np.outer(dg_p, z)
            dWo += np.outer(do_p, z)
            dbf += df_p; dbi += di_p
            dbg += dg_p; dbo += do_p

            # Gradient to previous h
            dh = (self.Wf.T @ df_p + self.Wi.T @ di_p +
                  self.Wg.T @ dg_p + self.Wo.T @ do_p)[:self.hs]

        self._opt.step(self._p(),
                       [dWf, dWi, dWg, dWo,
                        dbf, dbi, dbg, dbo,
                        dWy, dby])

    def train(self, seqs, labels, weights=None, epochs=30):
        if weights is None:
            weights = np.ones(len(seqs))
        for _ in range(epochs):
            for i in np.random.permutation(len(seqs)):
                self.train_one(seqs[i], float(labels[i]), float(weights[i]))


# ── Red C: Enhanced Statistical MLP ───────────────────────────────────────────

class _RedC_MLP:
    """MLP estadístico 28→64→32→16→1 con He init y Adam."""

    N_IN = N_FEAT_C  # 28

    def __init__(self, lr=LR_BASE):
        self.W1 = _he(self.N_IN, 64)
        self.b1 = np.zeros(64)
        self.W2 = _he(64, 32)
        self.b2 = np.zeros(32)
        self.W3 = _he(32, 16)
        self.b3 = np.zeros(16)
        self.W4 = _he(16, 1)
        self.b4 = np.zeros(1)
        self._opt = _Adam(self._p(), lr)

    def _p(self):
        return [self.W1, self.b1, self.W2, self.b2,
                self.W3, self.b3, self.W4, self.b4]

    def predict(self, seq) -> float:
        x  = _feats_C(seq)
        a1 = _relu(self.W1 @ x + self.b1)
        a2 = _relu(self.W2 @ a1 + self.b2)
        a3 = _relu(self.W3 @ a2 + self.b3)
        return float(_sig(self.W4 @ a3 + self.b4)[0])

    def train_one(self, seq, y_true: float, w: float = 1.0):
        x  = _feats_C(seq)
        a1 = _apply_dropout(_relu(self.W1 @ x + self.b1),  training=True)
        a2 = _apply_dropout(_relu(self.W2 @ a1 + self.b2), training=True)
        a3 = _apply_dropout(_relu(self.W3 @ a2 + self.b3), training=True)
        y  = _sig(self.W4 @ a3 + self.b4)[0]

        err = (y - y_true) * w
        dW4 = err * a3.reshape(1, -1);     db4 = np.array([err])
        d3  = (self.W4.T * err).flatten() * (a3 > 0)
        dW3 = np.outer(d3, a2);           db3 = d3.copy()
        d2  = (self.W3.T @ d3) * (a2 > 0)
        dW2 = np.outer(d2, a1);           db2 = d2.copy()
        d1  = (self.W2.T @ d2) * (a1 > 0)
        dW1 = np.outer(d1, x);            db1 = d1.copy()
        self._opt.step(self._p(), [dW1, db1, dW2, db2, dW3, db3, dW4, db4])

    def train(self, seqs, labels, weights=None, epochs=50):
        if weights is None:
            weights = np.ones(len(seqs))
        n = len(seqs)
        # Early stopping: separar 10% como validación si hay datos suficientes
        val_n   = max(1, n // 10) if n >= 20 else 0
        tr_idx  = np.arange(n - val_n)
        val_idx = np.arange(n - val_n, n)
        best_val = float("inf");  no_imp = 0
        best_w   = [p.copy() for p in self._p()]
        for ep in range(epochs):
            for i in np.random.permutation(tr_idx):
                self.train_one(seqs[i], float(labels[i]), float(weights[i]))
            # Validación (sin dropout — inferencia)
            if val_n > 0:
                val_loss = 0.0
                for j in val_idx:
                    x  = _feats_C(seqs[j])
                    a1 = _apply_dropout(_relu(self.W1 @ x  + self.b1), training=False)
                    a2 = _apply_dropout(_relu(self.W2 @ a1 + self.b2), training=False)
                    a3 = _apply_dropout(_relu(self.W3 @ a2 + self.b3), training=False)
                    yp = float(_sig(self.W4 @ a3 + self.b4)[0])
                    yt = float(labels[j])
                    val_loss += (yp - yt) ** 2
                val_loss /= val_n
                if val_loss < best_val - 1e-5:
                    best_val = val_loss
                    no_imp   = 0
                    for bp, p in zip(best_w, self._p()):
                        bp[:] = p
                else:
                    no_imp += 1
                    if no_imp >= _EARLY_PAT:
                        for bp, p in zip(best_w, self._p()):
                            p[:] = bp
                        break


# ── Meta-Red: Synthesizer ─────────────────────────────────────────────────────

class _MetaRed:
    """Sintetiza los 9 votos de las redes base + condición de mercado → decisión.

    Input (15): [3 probs_A] [3 probs_B] [3 probs_C]
                [conf_A conf_B conf_C] [volatilidad trend entropía]
    """

    N_IN = 15

    def __init__(self, lr=LR_BASE * 0.5):
        self.W1 = _he(self.N_IN, 24)
        self.b1 = np.zeros(24)
        self.W2 = _he(24, 12)
        self.b2 = np.zeros(12)
        self.W3 = _he(12, 1)
        self.b3 = np.zeros(1)
        self._opt = _Adam(self._p(), lr)

    def _p(self):
        return [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]

    def _make_x(self, pA, pB, pC, seq) -> np.ndarray:
        p9 = np.array(pA + pB + pC, dtype=np.float32)

        # Confidence per group: 1 - 4*std (high std = low agreement)
        def conf(g):
            return float(np.clip(1.0 - 4.0 * np.std(g), 0.0, 1.0))

        confs = np.array([conf(pA), conf(pB), conf(pC)], dtype=np.float32)

        # Market state from recent candles
        sb    = _to_bin(seq[-20:] if len(seq) >= 20 else seq)
        arr20 = np.concatenate([
            np.full(20 - len(sb), 0.5, dtype=np.float32), sb])
        vol   = float(np.sum(np.diff(arr20) != 0)) / 19.0
        trend = float(np.mean(arr20[-5:])) - float(np.mean(arr20))
        _pp_raw = float(np.mean(arr20)) if len(arr20) >= 2 else 0.5
        if not np.isfinite(_pp_raw):
            _pp_raw = 0.5
        pp   = np.clip(_pp_raw, 1e-7, 1.0 - 1e-7)
        with np.errstate(divide="ignore", invalid="ignore"):
            ent_ = -(pp * np.log2(pp) + (1.0 - pp) * np.log2(1.0 - pp))
        if not np.isfinite(ent_):
            ent_ = 1.0
        market = np.array([vol, trend, ent_], dtype=np.float32)

        return np.concatenate([p9, confs, market])

    def predict(self, pA, pB, pC, seq) -> float:
        x  = self._make_x(pA, pB, pC, seq)
        a1 = _relu(self.W1 @ x + self.b1)
        a2 = _relu(self.W2 @ a1 + self.b2)
        return float(_sig(self.W3 @ a2 + self.b3)[0])

    def train_one(self, pA, pB, pC, seq, y_true: float, w: float = 1.0):
        x  = self._make_x(pA, pB, pC, seq)
        a1 = _apply_dropout(_relu(self.W1 @ x + self.b1),  training=True)
        a2 = _apply_dropout(_relu(self.W2 @ a1 + self.b2), training=True)
        y  = _sig(self.W3 @ a2 + self.b3)[0]
        err = (y - y_true) * w
        dW3 = err * a2.reshape(1, -1);    db3 = np.array([err])
        d2  = (self.W3.T * err).flatten() * (a2 > 0)
        dW2 = np.outer(d2, a1);          db2 = d2.copy()
        d1  = (self.W2.T @ d2) * (a1 > 0)
        dW1 = np.outer(d1, x);           db1 = d1.copy()
        self._opt.step(self._p(), [dW1, db1, dW2, db2, dW3, db3])


# ── Error Memory ──────────────────────────────────────────────────────────────

class _ErrorMemory:
    """Cataloga patrones fallidos y amplifica su peso en el reentrenamiento."""

    MAX = 600

    def __init__(self):
        self._dict: dict = {}   # key -> {"total": int, "errors": int}

    def _key(self, seq) -> str:
        s = list(seq[-6:] if len(seq) >= 6 else seq)
        return "".join("V" if (v == "V" or v == 1) else "R" for v in s)

    def registrar(self, seq, acerto: bool):
        key = self._key(seq)
        if key in self._dict:
            self._dict[key]["total"] += 1
            if not acerto:
                self._dict[key]["errors"] += 1
        else:
            self._dict[key] = {"total": 1, "errors": 0 if acerto else 1}
            if len(self._dict) > self.MAX:
                # Eliminar el de menor tasa de error para hacer sitio
                worst = min(self._dict,
                            key=lambda k: self._dict[k]["errors"] / max(1, self._dict[k]["total"]))
                del self._dict[worst]

    def peso(self, seq) -> float:
        """Retorna peso extra 1.0 – 4.0 para secuencias con historial de error."""
        e = self._dict.get(self._key(seq))
        if e and e["total"] >= 3:
            return 1.0 + (e["errors"] / e["total"]) * 3.0
        return 1.0

    def patrones_peligrosos(self) -> list:
        """Top 10 patrones con mayor tasa de error."""
        con_historia = [
            {"k": k, "total": v["total"], "errors": v["errors"]}
            for k, v in self._dict.items() if v["total"] >= 3
        ]
        con_historia.sort(key=lambda x: -x["errors"] / x["total"])
        return con_historia[:10]

    def to_list(self):
        return [{"k": k, "total": v["total"], "errors": v["errors"]}
                for k, v in self._dict.items()]

    def from_list(self, d):
        self._dict = {}
        if isinstance(d, list):
            for e in d:
                if "k" in e:
                    self._dict[e["k"]] = {"total": e.get("total", 1),
                                          "errors": e.get("errors", 0)}


# ── Progress Tracker ──────────────────────────────────────────────────────────

class _ProgressTracker:
    """Mide precisión rolling-50, rolling-100, rolling-200 y total."""

    def __init__(self):
        self._hist:     list = []   # 1 = acierto, 0 = fallo
        self._total:    int  = 0
        self._aciertos: int  = 0

    def registrar(self, acerto: bool):
        val = 1 if acerto else 0
        self._hist.append(val)
        self._total    += 1
        self._aciertos += val
        if len(self._hist) > 600:
            self._hist = self._hist[-600:]

    def stats(self) -> dict:
        if not self._hist:
            return {"total": 0, "pct_total": 50.0,
                    "rolling_50": 50.0, "rolling_100": 50.0,
                    "rolling_200": 50.0, "tendencia": "sin datos"}

        def pct(n):
            n = min(n, len(self._hist))
            return round(100.0 * sum(self._hist[-n:]) / n, 1) if n else 50.0

        r50  = pct(50)
        r100 = pct(100)
        r200 = pct(200)
        total_pct = round(100.0 * self._aciertos / self._total, 1)

        if r50 > r100 + 2:
            tendencia = "mejorando"
        elif r50 < r100 - 2:
            tendencia = "empeorando"
        else:
            tendencia = "estable"

        return {
            "total":       self._total,
            "pct_total":   total_pct,
            "rolling_50":  r50,
            "rolling_100": r100,
            "rolling_200": r200,
            "tendencia":   tendencia,
        }

    def to_dict(self):
        return {"hist": self._hist[-600:],
                "total": self._total, "aciertos": self._aciertos}

    def from_dict(self, d):
        self._hist     = d.get("hist", [])
        self._total    = d.get("total", 0)
        self._aciertos = d.get("aciertos", 0)


# ── Red Maestra — Orquestador principal ───────────────────────────────────────

class RedMaestra:
    """
    Cerebro digital de Litch: 10 modelos coordinados en un solo ensemble.

    API compatible con la vieja RedNeuronal:
      predecir(seq)                     → (direccion, probabilidad)
      predecir_completo(seq)            → dict con breakdown completo
      registrar_prediccion(seq, dir)
      registrar_resultado(acerto, seq)
      quizas_reentrenar(seq)            → bool
      precision_aprox(seq)              → float | None
      resumen(seq)                      → str
      progreso()                        → dict con métricas de avance
    """

    def __init__(self):
        self._redes_A: list = [_RedA()      for _ in range(N_BOOT)]
        self._redes_B: list = [_RedB_LSTM() for _ in range(N_BOOT)]
        self._redes_C: list = [_RedC_MLP()  for _ in range(N_BOOT)]
        self._meta         = _MetaRed()
        self._err_mem      = _ErrorMemory()
        self._tracker      = _ProgressTracker()

        self._entrenada      = False
        self._entrenando     = False
        self._micro_entrend  = False   # guard: evita micro-trains concurrentes
        self._lock           = threading.Lock()

        self._pending = None       # (seq_list, direccion) para linking resultado
        self._outcomes: list = []  # (seq_bin, seq_orig, y_true, w)

        self._cargar()

    # ── Predicción ───────────────────────────────────────────────────────────

    def predecir(self, seq) -> tuple:
        """API compatible: retorna (direccion, probabilidad)."""
        d = self.predecir_completo(seq)
        return d["direccion"], d["probabilidad"]

    def predecir_completo(self, seq) -> dict:
        """Predicción completa con breakdown de los 10 modelos.

        Nunca se bloquea por entrenamiento: copia referencias en <1µs.
        """
        if not self._entrenada or len(seq) < 10:
            return {
                "direccion":   None,
                "probabilidad": 0.5,
                "confianza":    0.0,
                "entrenada":    False,
                "probs_A":      [0.5] * N_BOOT,
                "probs_B":      [0.5] * N_BOOT,
                "probs_C":      [0.5] * N_BOOT,
                "prob_meta":    0.5,
                "avg_A": 0.5, "avg_B": 0.5, "avg_C": 0.5,
                "ms": 0.0,
            }

        # Snapshot instantáneo de referencias (≪1µs) — jamás bloquea trading
        with self._lock:
            rA   = self._redes_A[:]
            rB   = self._redes_B[:]
            rC   = self._redes_C[:]
            meta = self._meta

        # Inferencia SIN lock (solo lectura, sin modificar pesos)
        sb = _to_bin(seq)
        t0 = time.perf_counter()
        pA = [r.predict(sb)  for r in rA]
        pB = [r.predict(sb)  for r in rB]
        pC = [r.predict(seq) for r in rC]
        p_meta = meta.predict(pA, pB, pC, seq)

        ms = (time.perf_counter() - t0) * 1000.0

        avg_A = float(np.mean(pA))
        avg_B = float(np.mean(pB))
        avg_C = float(np.mean(pC))

        all9      = pA + pB + pC
        std9      = float(np.std(all9))
        confianza = float(np.clip(1.0 - std9 * 3.0, 0.0, 1.0))

        dir_ = "V" if p_meta >= 0.5 else "R"

        return {
            "direccion":    dir_,
            "probabilidad": p_meta,
            "confianza":    confianza,
            "entrenada":    True,
            "probs_A":      pA,
            "probs_B":      pB,
            "probs_C":      pC,
            "prob_meta":    p_meta,
            "avg_A":        avg_A,
            "avg_B":        avg_B,
            "avg_C":        avg_C,
            "ms":           round(ms, 2),
        }

    # ── Outcome registration (aprendizaje por resultado) ─────────────────────

    def registrar_prediccion(self, seq, direccion: str):
        """Guarda la predicción pendiente ANTES de ejecutar la operación."""
        self._pending = (list(seq), direccion)

    def registrar_resultado(self, acerto: bool, seq=None):
        """Registra el resultado DESPUÉS de que cierre la vela."""
        self._tracker.registrar(acerto)

        s_ref = seq if seq is not None else (
            self._pending[0] if self._pending else None)
        if s_ref is not None:
            self._err_mem.registrar(s_ref, acerto)

        if self._pending is not None:
            prev_seq, prev_dir = self._pending
            self._pending = None

            # y_true: 1 si la dirección prevista fue correcta
            y_true = 1.0 if ((prev_dir == "V") == acerto) else 0.0
            sb     = _to_bin(prev_seq)
            w      = self._err_mem.peso(prev_seq)
            self._outcomes.append((sb, list(prev_seq), y_true, w))
            if len(self._outcomes) > 300:
                self._outcomes = self._outcomes[-300:]

            if len(self._outcomes) >= 10 and not self._micro_entrend:
                self._micro_entrend = True
                threading.Thread(
                    target=self._micro_train,
                    daemon=True,
                    name="MaestMicro").start()

        self._guardar_stats()

    def _micro_train(self):
        """Micro-entrena con los últimos 30 outcomes (2 mini-épocas online)."""
        try:
            with self._lock:
                batch = list(self._outcomes[-30:])
            for _ep in range(2):   # 2 pases → aprendizaje online 2× más efectivo
                idxs = list(range(len(batch)))
                np.random.shuffle(idxs)
                for i in idxs:
                    sb, seq_orig, y_true, w = batch[i]
                    for r in self._redes_A:
                        r.train_one(sb, y_true, w)
                    for r in self._redes_B:
                        r.train_one(sb, y_true, w)
                    for r in self._redes_C:
                        r.train_one(seq_orig, y_true, w)
                    pA = [r.predict(sb)       for r in self._redes_A]
                    pB = [r.predict(sb)       for r in self._redes_B]
                    pC = [r.predict(seq_orig) for r in self._redes_C]
                    self._meta.train_one(pA, pB, pC, seq_orig, y_true, w)
        finally:
            self._micro_entrend = False

    # ── Entrenamiento completo (background) ──────────────────────────────────

    def entrenar(self, seq):
        """Lanza entrenamiento completo en background si hay datos suficientes."""
        if len(seq) < MIN_TRAIN or self._entrenando:
            return
        self._entrenando = True
        threading.Thread(
            target=self._entrenar_fondo,
            args=(list(seq),),
            daemon=True,
            name="MaestTrain").start()

    def _entrenar_fondo(self, seq):
        """Entrena las 3×3 redes con bagging + meta-red.

        El entrenamiento ocurre en instancias temporales FUERA del lock.
        El lock solo se adquiere ≈1ms para el swap final de punteros.
        Esto garantiza que predecir_completo() nunca se bloquea.
        """
        try:
            # Limitar a las 1500 velas más recientes: patrones antiguos pesan menos
            # y reducir el dataset 3-4× hace el entrenamiento ~10× más rápido.
            if len(seq) > 1500:
                seq = seq[-1500:]
            sb  = _to_bin(seq)
            n   = len(sb)
            min_win = SEQ_B + 1
            if n < min_win:
                return

            # ── 1. Construir dataset (sin lock) ───────────────────────────────
            seqs_bin, seqs_orig, labels, weights = [], [], [], []
            for i in range(min_win, n):
                w_bin  = list(sb[max(0, i - SEQ_B):i])
                w_orig = seq[max(0, i - SEQ_B):i]
                label  = float(sb[i])
                wt     = self._err_mem.peso(w_orig)
                seqs_bin.append(w_bin)
                seqs_orig.append(w_orig)
                labels.append(label)
                weights.append(wt)

            N   = len(labels)
            lbl = np.array(labels, dtype=np.float32)
            wts = np.array(weights, dtype=np.float32)

            # ── 2. Crear instancias FRESH (sin lock) ──────────────────────────
            redes_A = [_RedA()      for _ in range(N_BOOT)]
            redes_B = [_RedB_LSTM() for _ in range(N_BOOT)]
            redes_C = [_RedC_MLP()  for _ in range(N_BOOT)]
            meta    = _MetaRed()

            # ── 3. Bagging: entrenar 9 modelos en paralelo lógico (sin lock) ─
            for k in range(N_BOOT):
                idx = np.random.choice(N, N, replace=True)
                sb_ = [seqs_bin[i]  for i in idx]
                so_ = [seqs_orig[i] for i in idx]
                lb_ = lbl[idx]
                wb_ = wts[idx]
                redes_A[k].train(sb_, lb_, wb_, epochs=50)
                redes_B[k].train(sb_, lb_, wb_, epochs=30)
                redes_C[k].train(so_, lb_, wb_, epochs=50)

            # ── 4. Calcular votos para meta-red (sin lock) ───────────────────
            meta_pA, meta_pB, meta_pC = [], [], []
            for i in range(N):
                meta_pA.append([r.predict(seqs_bin[i])  for r in redes_A])
                meta_pB.append([r.predict(seqs_bin[i])  for r in redes_B])
                meta_pC.append([r.predict(seqs_orig[i]) for r in redes_C])

            for _ in range(60):
                for i in np.random.permutation(N):
                    meta.train_one(
                        meta_pA[i], meta_pB[i], meta_pC[i],
                        seqs_orig[i], labels[i], float(wts[i]))

            # ── 5. Swap atómico ≈ <1ms — lo único que toca el lock ───────────
            with self._lock:
                self._redes_A  = redes_A
                self._redes_B  = redes_B
                self._redes_C  = redes_C
                self._meta     = meta
                self._entrenada = True

            self._guardar_todo()
        finally:
            self._entrenando = False

    def quizas_reentrenar(self, seq) -> bool:
        """Reentrena en background cada 20 velas nuevas. Retorna True si inició."""
        n = len(seq)
        if n >= MIN_TRAIN and n % 20 == 0 and not self._entrenando:
            self.entrenar(seq)
            return True
        return False

    # ── Métricas ─────────────────────────────────────────────────────────────

    def progreso(self) -> dict:
        """Retorna dict con métricas rolling-50/100/200 y total."""
        return self._tracker.stats()

    def precision_aprox(self, seq=None) -> float:
        s = self._tracker.stats()
        if s["total"] < 5:
            return 0.5
        return s["pct_total"] / 100.0

    def resumen(self, seq=None) -> str:
        s = self._tracker.stats()
        peligrosos = self._err_mem.patrones_peligrosos()
        if not self._entrenada:
            return (f"Red Maestra: aún sin entrenar. "
                    f"Necesito al menos {MIN_TRAIN} velas observadas.")
        lineas = [
            f"Red Maestra · CNN×3 + LSTM×3 + MLP×3 + Meta = 10 modelos",
            f"Precisión total: {s['pct_total']}%  ({s['total']} velas verificadas)",
            f"Rolling-50:  {s['rolling_50']}%  | "
            f"Rolling-100: {s['rolling_100']}%  | "
            f"Rolling-200: {s['rolling_200']}%",
            f"Tendencia: {s['tendencia']}",
            f"Patrones peligrosos memorizados: {len(peligrosos)}",
        ]
        if peligrosos:
            top = peligrosos[0]
            lineas.append(
                f"Patrón más conflictivo: «{top['k']}» "
                f"({top['errors']}/{top['total']} errores)")
        return "\n".join(lineas)

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _guardar_todo(self):
        try:
            os.makedirs(_mem.RUTA_DATA, exist_ok=True)
            d = {"entrenada": np.array([int(self._entrenada)])}
            for k, r in enumerate(self._redes_A):
                d[f"A{k}W1"]=r.W1; d[f"A{k}b1"]=r.b1
                d[f"A{k}W2"]=r.W2; d[f"A{k}b2"]=r.b2
                d[f"A{k}W3"]=r.W3; d[f"A{k}b3"]=r.b3
            for k, r in enumerate(self._redes_B):
                d[f"B{k}Wf"]=r.Wf; d[f"B{k}Wi"]=r.Wi
                d[f"B{k}Wg"]=r.Wg; d[f"B{k}Wo"]=r.Wo
                d[f"B{k}bf"]=r.bf; d[f"B{k}bi"]=r.bi
                d[f"B{k}bg"]=r.bg; d[f"B{k}bo"]=r.bo
                d[f"B{k}Wy"]=r.Wy; d[f"B{k}by"]=r.by
            for k, r in enumerate(self._redes_C):
                d[f"C{k}W1"]=r.W1; d[f"C{k}b1"]=r.b1
                d[f"C{k}W2"]=r.W2; d[f"C{k}b2"]=r.b2
                d[f"C{k}W3"]=r.W3; d[f"C{k}b3"]=r.b3
                d[f"C{k}W4"]=r.W4; d[f"C{k}b4"]=r.b4
            d["MW1"]=self._meta.W1; d["Mb1"]=self._meta.b1
            d["MW2"]=self._meta.W2; d["Mb2"]=self._meta.b2
            d["MW3"]=self._meta.W3; d["Mb3"]=self._meta.b3
            np.savez_compressed(RUTA_PESOS, **d)
        except Exception:
            pass
        self._guardar_stats()

    def _guardar_stats(self):
        try:
            os.makedirs(_mem.RUTA_DATA, exist_ok=True)
            with open(RUTA_STATS, "w", encoding="utf-8") as f:
                json.dump({
                    "tracker": self._tracker.to_dict(),
                    "errores": self._err_mem.to_list(),
                }, f, ensure_ascii=False)
        except Exception:
            pass

    def _cargar(self):
        try:
            if os.path.exists(RUTA_PESOS):
                d = dict(np.load(RUTA_PESOS, allow_pickle=True))
                self._entrenada = bool(int(d.get("entrenada", [0])[0]))
                for k, r in enumerate(self._redes_A):
                    if f"A{k}W1" in d:
                        r.W1=d[f"A{k}W1"]; r.b1=d[f"A{k}b1"]
                        r.W2=d[f"A{k}W2"]; r.b2=d[f"A{k}b2"]
                        r.W3=d[f"A{k}W3"]; r.b3=d[f"A{k}b3"]
                for k, r in enumerate(self._redes_B):
                    if f"B{k}Wf" in d:
                        r.Wf=d[f"B{k}Wf"]; r.Wi=d[f"B{k}Wi"]
                        r.Wg=d[f"B{k}Wg"]; r.Wo=d[f"B{k}Wo"]
                        r.bf=d[f"B{k}bf"]; r.bi=d[f"B{k}bi"]
                        r.bg=d[f"B{k}bg"]; r.bo=d[f"B{k}bo"]
                        r.Wy=d[f"B{k}Wy"]; r.by=d[f"B{k}by"]
                for k, r in enumerate(self._redes_C):
                    if f"C{k}W1" in d:
                        r.W1=d[f"C{k}W1"]; r.b1=d[f"C{k}b1"]
                        r.W2=d[f"C{k}W2"]; r.b2=d[f"C{k}b2"]
                        r.W3=d[f"C{k}W3"]; r.b3=d[f"C{k}b3"]
                        r.W4=d[f"C{k}W4"]; r.b4=d[f"C{k}b4"]
                if "MW1" in d:
                    self._meta.W1=d["MW1"]; self._meta.b1=d["Mb1"]
                    self._meta.W2=d["MW2"]; self._meta.b2=d["Mb2"]
                    self._meta.W3=d["MW3"]; self._meta.b3=d["Mb3"]
        except Exception:
            pass

        try:
            if os.path.exists(RUTA_STATS):
                with open(RUTA_STATS, encoding="utf-8") as f:
                    sd = json.load(f)
                self._tracker.from_dict(sd.get("tracker", {}))
                self._err_mem.from_list(sd.get("errores", []))
        except Exception:
            pass
