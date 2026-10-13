"""
TradingView / Yahoo Finance Real-Time Feed — Litch v3

Proporciona velas OHLCV en tiempo real a través de Yahoo Finance (yfinance)
sin necesidad de abrir un broker ni capturar la pantalla.

Características:
  · Traduce símbolo del broker a ticker Yahoo (EURUSD → EURUSD=X)
  · Actualización cada N segundos (configurable, mínimo 5s)
  · Cachea las últimas 500 velas en memoria
  · Expone las velas a trading.py → mejora la predicción sin pantalla
  · Analiza el gráfico con Fable 5 (vision) si hay screenshot disponible
  · Fallback: si yfinance no está instalado, usa datos de pantalla normalmente
  · Estadísticas RSI / EMA / Bollinger calculadas directamente del feed
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

# ── Import opcional de yfinance ───────────────────────────────────────────────
try:
    import yfinance as _yf
    # Silenciar los mensajes de yfinance ("Failed to get ticker", "possibly delisted")
    import logging as _logging
    _logging.getLogger("yfinance").setLevel(_logging.CRITICAL)
    _logging.getLogger("yfinance.base").setLevel(_logging.CRITICAL)
    _logging.getLogger("yfinance.utils").setLevel(_logging.CRITICAL)
    _logging.getLogger("peewee").setLevel(_logging.CRITICAL)
    _logging.getLogger("urllib3").setLevel(_logging.CRITICAL)
    _YF_OK = True
except ImportError:
    _YF_OK = False
    _yf = None

try:
    import numpy as np
    _NP_OK = True
except ImportError:
    _NP_OK = False
    np = None

# ── Mapa broker → ticker Yahoo ────────────────────────────────────────────────
_TICKER_MAP: dict[str, str] = {
    # Forex (IQ Option OTC incluidos)
    "EURUSD":      "EURUSD=X",
    "EURUSD-OTC":  "EURUSD=X",
    "GBPUSD":      "GBPUSD=X",
    "GBPUSD-OTC":  "GBPUSD=X",
    "USDJPY":      "USDJPY=X",
    "USDJPY-OTC":  "USDJPY=X",
    "USDCHF":      "USDCHF=X",
    "USDCHF-OTC":  "USDCHF=X",
    "AUDUSD":      "AUDUSD=X",
    "AUDUSD-OTC":  "AUDUSD=X",
    "USDCAD":      "USDCAD=X",
    "USDCAD-OTC":  "USDCAD=X",
    "NZDUSD":      "NZDUSD=X",
    "NZDUSD-OTC":  "NZDUSD=X",
    "EURGBP":      "EURGBP=X",
    "EURGBP-OTC":  "EURGBP=X",
    "EURJPY":      "EURJPY=X",
    "EURJPY-OTC":  "EURJPY=X",
    "GBPJPY":      "GBPJPY=X",
    "GBPJPY-OTC":  "GBPJPY=X",
    # Índices
    "S&P500":      "^GSPC",
    "NASDAQ":      "^IXIC",
    "DOW":         "^DJI",
    "DAX":         "^GDAXI",
    # Cripto
    "BTCUSD":      "BTC-USD",
    "ETHUSD":      "ETH-USD",
    # Materias primas
    "XAUUSD":      "GC=F",
    "GOLD":        "GC=F",
    "OIL":         "CL=F",
    "SILVER":      "SI=F",
}

# ── Intervalo Yahoo → intervalo yfinance ──────────────────────────────────────
_PERIODO_A_INTERVAL: dict[int, str] = {
    5:   "1m",   # velas 5s → usar datos 1m, más finas no disponibles en Yahoo
    10:  "1m",
    15:  "1m",
    30:  "1m",
    60:  "1m",
    120: "2m",
    300: "5m",
    900: "15m",
    1800:"30m",
    3600:"1h",
}

_CACHE_VELAS = 500   # máximo de velas en memoria
_MIN_REFRESH = 5     # mínimo 5s entre llamadas a Yahoo


class TVFeed(threading.Thread):
    """
    Daemon que descarga velas OHLCV en tiempo real desde Yahoo Finance
    y las expone al sistema de trading de Litch.

    Uso:
        feed = TVFeed(app)
        feed.start()
        velas = feed.obtener_velas(n=100)   # lista de dicts OHLCV
        ultimo = feed.ultimo_precio()
    """

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchTVFeed")
        self.app       = app
        self._velas:    deque[dict] = deque(maxlen=_CACHE_VELAS)
        self._lock      = threading.Lock()
        self._ticker_yf = ""
        self._ultimo_dl = 0.0
        self._errores   = 0
        self._activo    = True
        self._intervalo = 30   # se actualiza dinámicamente
        self._periodo_s = 60   # periodo actual de vela en segundos
        self._backoff   = 0    # segundos extra de espera tras fallos consecutivos
        self._fallos_consec = 0  # fallos consecutivos para backoff

    # ════════════════════════════════════════════════════════════════════
    # API pública
    # ════════════════════════════════════════════════════════════════════

    def obtener_velas(self, n: int = 100) -> list[dict]:
        """Retorna las últimas N velas como lista de dicts {ts,o,h,l,c,v}."""
        with self._lock:
            todas = list(self._velas)
        return todas[-n:] if n < len(todas) else todas

    def ultimo_precio(self) -> float | None:
        """Precio de cierre de la última vela descargada."""
        with self._lock:
            if self._velas:
                return self._velas[-1].get("c")
        return None

    def indicadores(self) -> dict:
        """RSI(14), EMA(9), EMA(21), EMA(200), BB(20), tendencia, momentum."""
        velas = self.obtener_velas(250)
        if not _NP_OK or len(velas) < 14:
            return {}
        cierres = np.array([v["c"] for v in velas], dtype=float)
        return {
            "rsi_14":   _rsi(cierres, 14),
            "ema_9":    _ema(cierres, 9),
            "ema_21":   _ema(cierres, 21),
            "ema_200":  _ema(cierres, 200) if len(cierres) >= 200 else None,
            "bb_upper": _bb(cierres, 20)[0],
            "bb_lower": _bb(cierres, 20)[1],
            "bb_mid":   _bb(cierres, 20)[2],
            "tendencia": _tendencia(cierres),
            "momentum":  float(cierres[-1] - cierres[-5]) if len(cierres) >= 5 else 0.0,
            "ticker":    self._ticker_yf,
            "n_velas":   len(velas),
        }

    def estado(self) -> dict:
        """Estado del feed para mostrar en UI o logs."""
        return {
            "ok":       _YF_OK,
            "ticker":   self._ticker_yf,
            "n_velas":  len(self._velas),
            "errores":  self._errores,
            "ultimo_dl": self._ultimo_dl,
            "intervalo": self._intervalo,
        }

    def parar(self):
        self._activo = False

    # ════════════════════════════════════════════════════════════════════
    # Loop principal
    # ════════════════════════════════════════════════════════════════════

    def run(self):
        time.sleep(8)   # esperar a que Litch arranque completamente
        while self._activo:
            # Backoff exponencial: espera extra tras fallos consecutivos
            if self._backoff > 0:
                time.sleep(self._backoff)
                self._backoff = 0
                continue
            try:
                self._sincronizar_activo()
                if _YF_OK and self._ticker_yf:
                    self._descargar()
            except Exception as ex:
                self._fallos_consec += 1
                self._errores += 1
                # Solo loguear el primer fallo y cada 10 tras eso
                if self._fallos_consec <= 1 or self._fallos_consec % 10 == 0:
                    self.app.log(f"[TVFeed] Sin datos (fallo #{self._fallos_consec}): "
                                 f"{str(ex)[:60]}")
                # Backoff exponencial: 30s → 60s → 120s → máx 600s (10 min)
                self._backoff = min(600, 30 * (2 ** min(self._fallos_consec - 1, 4)))
                time.sleep(max(_MIN_REFRESH, self._intervalo))
                continue
            time.sleep(max(_MIN_REFRESH, self._intervalo))

    # ════════════════════════════════════════════════════════════════════
    # Lógica interna
    # ════════════════════════════════════════════════════════════════════

    def _sincronizar_activo(self):
        """Lee el activo actual del config y actualiza el ticker de Yahoo."""
        cfg = self.app.mem.get("config", {})
        # "asset_actual" es la clave canónica del sistema; "activo" es el fallback legacy
        activo_raw  = (cfg.get("asset_actual") or cfg.get("activo") or "EURUSD")
        activo      = activo_raw.upper().strip()
        self._periodo_s = int(cfg.get("periodo_vela", 60))

        # Intervalo de descarga: al menos 2× el periodo de vela, mínimo 5s
        self._intervalo = max(_MIN_REFRESH, min(60, self._periodo_s // 2))

        nuevo_ticker = _TICKER_MAP.get(activo)
        if not nuevo_ticker:
            # Intentar inferir: si tiene "/" separador (EUR/USD) normalizar
            activo_norm = activo.replace("/", "").replace(" ", "")
            nuevo_ticker = _TICKER_MAP.get(activo_norm,
                           activo_norm + "=X" if len(activo_norm) == 6 else "")

        if nuevo_ticker != self._ticker_yf:
            self._ticker_yf = nuevo_ticker
            with self._lock:
                self._velas.clear()   # resetear al cambiar activo
            if nuevo_ticker:
                self.app.log(f"[TVFeed] Activo cambiado → {activo} ({nuevo_ticker})")

    def _descargar(self):
        """Descarga las últimas velas de Yahoo Finance y las añade al buffer."""
        if not self._ticker_yf:
            return

        interval = _PERIODO_A_INTERVAL.get(
            self._periodo_s,
            "1m" if self._periodo_s <= 60 else "5m"
        )

        # Yahoo solo permite history de 7d para 1m, 60d para 2m-5m
        period = "1d" if interval == "1m" else "5d"

        ticker = _yf.Ticker(self._ticker_yf)
        df = ticker.history(period=period, interval=interval,
                            auto_adjust=True, prepost=True)

        if df is None or df.empty:
            self._fallos_consec += 1
            self._errores += 1
            # Backoff rápido cuando no hay datos (mercado cerrado / fin de semana)
            self._backoff = min(300, 60 * max(1, self._fallos_consec))
            return

        nuevas = 0
        with self._lock:
            ts_existentes = {v["ts"] for v in self._velas}
            for ts, row in df.iterrows():
                try:
                    ts_unix = int(ts.timestamp())
                    if ts_unix not in ts_existentes:
                        self._velas.append({
                            "ts": ts_unix,
                            "o":  float(row["Open"]),
                            "h":  float(row["High"]),
                            "l":  float(row["Low"]),
                            "c":  float(row["Close"]),
                            "v":  float(row.get("Volume", 0)),
                        })
                        ts_existentes.add(ts_unix)
                        nuevas += 1
                except Exception:
                    continue

        self._ultimo_dl = time.time()
        self._errores      = 0
        self._fallos_consec = 0   # resetear backoff tras éxito
        self._backoff      = 0

        if nuevas:
            self.app.log(f"[TVFeed] {self._ticker_yf}: +{nuevas} velas "
                         f"({len(self._velas)} total, intervalo={interval})")
            # Inyectar en secuencia si el app lo soporta
            self._inyectar_en_secuencia()

    def _inyectar_en_secuencia(self):
        """
        Agrega las velas más recientes a app.mem['secuencia'] para
        que todos los métodos de análisis las usen automáticamente.
        Solo añade velas más nuevas que las ya presentes.
        """
        try:
            sec = self.app.mem.get("secuencia")
            if sec is None:
                return
            with self._lock:
                velas = list(self._velas)
            if not velas:
                return

            # Timestamp de la última vela ya en secuencia
            ts_ultimo = sec[-1].get("ts", 0) if sec else 0

            nuevas = [v for v in velas if v.get("ts", 0) > ts_ultimo]
            if not nuevas:
                return

            for v in nuevas[-10:]:   # máximo 10 velas nuevas por ciclo (no inundar)
                sec.append(v)

            # Limitar secuencia a 5000 velas
            if len(sec) > 5000:
                del sec[:-5000]

        except Exception:
            pass


# ── Indicadores técnicos ──────────────────────────────────────────────────────

def _ema(arr, periodo: int) -> float | None:
    if not _NP_OK or len(arr) < periodo:
        return None
    k = 2.0 / (periodo + 1)
    ema = arr[:periodo].mean()
    for v in arr[periodo:]:
        ema = v * k + ema * (1 - k)
    return float(ema)


def _rsi(arr, periodo: int = 14) -> float | None:
    if not _NP_OK or len(arr) < periodo + 1:
        return None
    deltas = np.diff(arr)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g  = gains[:periodo].mean()
    avg_l  = losses[:periodo].mean()
    for i in range(periodo, len(gains)):
        avg_g = (avg_g * (periodo - 1) + gains[i])  / periodo
        avg_l = (avg_l * (periodo - 1) + losses[i]) / periodo
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return float(100.0 - 100.0 / (1.0 + rs))


def _bb(arr, periodo: int = 20) -> tuple[float | None, float | None, float | None]:
    if not _NP_OK or len(arr) < periodo:
        return None, None, None
    ventana = arr[-periodo:]
    mid     = float(ventana.mean())
    std     = float(ventana.std())
    return mid + 2 * std, mid - 2 * std, mid


def _tendencia(arr) -> str:
    if not _NP_OK or len(arr) < 10:
        return "lateral"
    m, b = np.polyfit(range(len(arr[-50:])), arr[-50:], 1) if len(arr) >= 50 else (0, 0)
    if m > 0.0001:
        return "alcista"
    if m < -0.0001:
        return "bajista"
    return "lateral"


# ── Análisis visual con Fable 5 ───────────────────────────────────────────────

def analizar_chart_con_fable(screenshot_b64: str, activo: str,
                              indicadores: dict | None = None,
                              app=None) -> str | None:
    """
    Envía el screenshot del gráfico a Fable 5 (vision) para análisis técnico.

    Retorna texto con el análisis (tendencia, soporte/resistencia, señal).
    Retorna None si Fable 5 no está disponible o hay error.
    """
    try:
        from . import mente_claude as _mc
        if not _mc.disponible():
            return None

        ind_txt = ""
        if indicadores:
            partes = []
            if indicadores.get("rsi_14") is not None:
                partes.append(f"RSI(14)={indicadores['rsi_14']:.1f}")
            if indicadores.get("ema_9") is not None:
                partes.append(f"EMA9={indicadores['ema_9']:.5f}")
            if indicadores.get("ema_21") is not None:
                partes.append(f"EMA21={indicadores['ema_21']:.5f}")
            if indicadores.get("tendencia"):
                partes.append(f"Tendencia={indicadores['tendencia']}")
            if indicadores.get("n_velas"):
                partes.append(f"N_velas={indicadores['n_velas']}")
            ind_txt = "Indicadores calculados: " + ", ".join(partes) + ".\n"

        prompt = (
            f"Analiza este gráfico de trading de {activo}. "
            f"{ind_txt}"
            "Dime en 3 puntos concisos:\n"
            "1) Tendencia actual (alcista/bajista/lateral) y nivel de confianza\n"
            "2) Soporte y resistencia más importantes visibles\n"
            "3) Señal recomendada ahora mismo (COMPRA/VENTA/ESPERAR) con razón técnica\n"
            "Sé breve y técnico. No uses introducciones."
        )

        return _mc.preguntar_con_imagen(prompt, screenshot_b64,
                                        idioma=getattr(app, "idioma", "es"))
    except Exception as ex:
        if app:
            app.log(f"[TVFeed/Fable] Error: {ex}")
        return None


# ── Función de conveniencia para obtener el feed desde cualquier módulo ────────

_feed_global: TVFeed | None = None


def obtener_feed() -> TVFeed | None:
    return _feed_global


def inicializar(app) -> TVFeed:
    global _feed_global
    if _feed_global is None or not _feed_global.is_alive():
        _feed_global = TVFeed(app)
        _feed_global.start()
        app.log("[TVFeed] Feed Yahoo Finance iniciado.")
    return _feed_global
