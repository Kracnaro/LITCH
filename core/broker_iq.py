"""
BrokerUniversal — Litch aprende a operar en cualquier broker de trading.

Arquitectura de inteligencia autónoma:
─────────────────────────────────────
  BrokerUniversal   → estadísticas, ratón, calibración, consultas IA
  BrokerConsejero   → daemon proactivo: monitorea, aconseja, actúa

Ciclos de aprendizaje:
  • Cada trade registrado  → acumula stats (incluyendo hora del día)
  • Cada 5 trades          → re-evalúa silenciosamente el activo/duración
  • Cada 60s               → BrokerConsejero analiza y decide si sugerir
  • Cada 20 trades nuevos  → consulta a Claude/Ollama y guarda lección
  • Racha ≥ 4 pérdidas     → acción inmediata (cambio o consejo IA)

Con modo_autonomo + autoclick_on:
  → Litch aplica cambios en el broker SIN preguntar.
Sin modo_autonomo:
  → Litch solo sugiere por voz y espera tu confirmación.

IMPORTANTE: La IA (Claude/Ollama) SOLO asesora estrategia.
            Las decisiones de trading siguen siendo locales.
"""

import json
import os
import threading
import time
from typing import Optional

from . import memoria as mem_mod, vision

try:
    import pyautogui
    _PG_OK = True
except ImportError:
    _PG_OK = False

# ── Perfiles de broker conocidos ─────────────────────────────────────────────
PERFILES = {
    "iq_option": {
        "nombre":     "IQ Option",
        "payout":     0.85,
        "assets":     ["EUR/USD OTC", "EUR/AUD OTC", "AUD/USD OTC",
                       "USD/JPY OTC", "GBP/USD OTC", "EUR/GBP OTC",
                       "NZD/USD OTC", "EUR/CAD OTC", "USD/CAD OTC"],
        "duraciones": [15, 30, 60, 120, 300],
    },
    "quotex": {
        "nombre":     "Quotex",
        "payout":     0.92,
        "assets":     ["EUR/USD", "EUR/AUD", "GBP/USD", "USD/JPY",
                       "AUD/USD", "EUR/GBP", "NZD/USD", "USD/CAD"],
        "duraciones": [60, 120, 180, 300, 600],
    },
    "deriv": {
        "nombre":     "Deriv",
        "payout":     0.80,
        "assets":     ["AUD/USD", "EUR/AUD", "EUR/USD", "GBP/USD",
                       "USD/JPY", "USD/CAD", "USD/CHF"],
        "duraciones": [60, 120, 300, 900, 1800],
    },
    "binomo": {
        "nombre":     "Binomo",
        "payout":     0.87,
        "assets":     ["EUR/USD", "GBP/USD", "USD/JPY", "EUR/JPY",
                       "AUD/USD", "NZD/USD"],
        "duraciones": [60, 120, 300],
    },
    "olymp_trade": {
        "nombre":     "Olymp Trade",
        "payout":     0.82,
        "assets":     ["EUR/USD", "EUR/AUD", "USD/JPY", "GBP/USD",
                       "AUD/USD", "EUR/JPY"],
        "duraciones": [60, 120, 300, 600],
    },
    "pocket_option": {
        "nombre":     "Pocket Option",
        "payout":     0.92,
        "assets":     ["EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY",
                       "NZD/USD", "EUR/GBP", "USD/CAD"],
        "duraciones": [60, 120, 180, 300, 600],
    },
    "exness": {
        "nombre":     "Exness",
        "payout":     0.85,
        "assets":     ["EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY",
                       "USD/CHF", "NZD/USD", "EUR/GBP", "USD/CAD"],
        "duraciones": [60, 120, 300, 900],
    },
    "xm": {
        "nombre":     "XM Global",
        "payout":     0.83,
        "assets":     ["EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY",
                       "NZD/USD", "EUR/GBP"],
        "duraciones": [60, 120, 300, 900],
    },
    "metatrader": {
        "nombre":     "MetaTrader",
        "payout":     0.80,
        "assets":     ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY",
                       "NZDUSD", "USDCAD", "USDCHF", "XAUUSD"],
        "duraciones": [60, 300, 900, 1800, 3600],
    },
    "generico": {
        "nombre":     "Broker",
        "payout":     0.80,
        "assets":     ["EUR/USD", "EUR/AUD", "USD/JPY", "GBP/USD"],
        "duraciones": [60, 120, 300],
    },

    # ── Brokers profesionales (bolsa real / Wall Street) ─────────────────────
    # Recomendados por comunidades de trading latinoamericanas (LatinWallSt, etc.)
    # payout = rendimiento neto esperado sobre posiciones ganadoras (estimado)

    "interactive_brokers": {
        "nombre":     "Interactive Brokers (IBKR)",
        "payout":     0.95,   # margen real, sin spread típico
        "assets":     ["SPY", "QQQ", "AAPL", "TSLA", "AMZN", "MSFT",
                       "NVDA", "META", "GOOGL", "AMD", "NFLX", "BABA",
                       "EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "El broker más completo del mundo. Acceso a NYSE, NASDAQ, AMEX, "
                      "forex, futuros y opciones. Muy usado por traders Latino-WallSt.",
    },
    "td_ameritrade": {
        "nombre":     "TD Ameritrade / Thinkorswim",
        "payout":     0.94,
        "assets":     ["SPY", "QQQ", "AAPL", "TSLA", "AMZN", "MSFT",
                       "NVDA", "META", "GOOGL", "AMD", "SPX", "NDX",
                       "/ES", "/NQ", "/CL", "/GC"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Plataforma TOS (Thinkorswim) — referente en opciones y análisis técnico.",
    },
    "charles_schwab": {
        "nombre":     "Charles Schwab",
        "payout":     0.94,
        "assets":     ["SPY", "QQQ", "AAPL", "TSLA", "AMZN", "MSFT",
                       "NVDA", "META", "GOOGL", "BRK.B", "JPM", "V",
                       "SCHD", "VTI", "VXUS"],
        "duraciones": [60, 300, 900, 3600, 86400],
        "notas":      "El mayor broker retail de EEUU. Integra Thinkorswim desde 2020.",
    },
    "tastytrade": {
        "nombre":     "Tastytrade",
        "payout":     0.94,
        "assets":     ["SPY", "QQQ", "IWM", "AAPL", "TSLA", "AMZN",
                       "NVDA", "AMD", "META", "GOOGL", "SPX", "NDX",
                       "/ES", "/NQ", "/GC", "/SI", "/CL"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Favorito de traders de opciones en Latinoamérica. "
                      "Comisiones bajas y UI profesional.",
    },
    "etrade": {
        "nombre":     "E*TRADE",
        "payout":     0.93,
        "assets":     ["SPY", "QQQ", "AAPL", "TSLA", "MSFT", "AMZN",
                       "NVDA", "META", "GOOGL", "BAC", "C", "WMT",
                       "XLF", "XLK", "XLE"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Uno de los primeros brokers online. Muy popular en EEUU y Latam.",
    },
    "tradestation": {
        "nombre":     "TradeStation",
        "payout":     0.94,
        "assets":     ["SPY", "QQQ", "AAPL", "TSLA", "AMZN", "NVDA",
                       "META", "GOOGL", "AMD", "SPX", "NDX",
                       "/ES", "/NQ", "/YM", "/GC", "/CL"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Plataforma profesional con algoritmos, muy usada por traders activos.",
    },
    "webull": {
        "nombre":     "Webull",
        "payout":     0.93,
        "assets":     ["SPY", "QQQ", "AAPL", "TSLA", "AMZN", "MSFT",
                       "NVDA", "META", "GOOGL", "AMD", "NFLX", "COIN",
                       "AMC", "GME", "RIVN"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Muy popular entre traders latinos en EEUU. Sin comisiones en acciones.",
    },
    "etoro": {
        "nombre":     "eToro",
        "payout":     0.85,
        "assets":     ["SPY", "AAPL", "TSLA", "AMZN", "MSFT", "NVDA",
                       "META", "GOOGL", "BTC/USD", "ETH/USD", "XRP/USD",
                       "EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
        "duraciones": [60, 300, 900, 3600, 86400],
        "notas":      "El mayor broker de copy-trading del mundo. Enorme comunidad latina. "
                      "Acciones reales + CFDs + cripto.",
    },
    "ig_group": {
        "nombre":     "IG Group",
        "payout":     0.88,
        "assets":     ["SPX 500", "US Tech 100", "Wall Street", "Germany 40",
                       "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
                       "XAU/USD", "XAG/USD", "Brent Crude", "Natural Gas",
                       "AAPL", "TSLA", "AMZN", "MSFT"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Líder mundial en CFDs. Regulado en UK, AU, US. Muy profesional.",
    },
    "oanda": {
        "nombre":     "OANDA",
        "payout":     0.87,
        "assets":     ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
                       "USD/CAD", "USD/CHF", "NZD/USD", "EUR/GBP",
                       "XAU/USD", "XAG/USD", "SPX500", "US30", "NAS100",
                       "BCO/USD", "NATGAS/USD"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Referente en forex. Sin comisiones por operación. Muy preciso.",
    },
    "saxo_bank": {
        "nombre":     "Saxo Bank",
        "payout":     0.90,
        "assets":     ["SPY", "QQQ", "AAPL", "TSLA", "MSFT", "AMZN",
                       "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
                       "XAU/USD", "XAG/USD", "Brent", "SPX", "DAX",
                       "NIKKEI", "CAC40"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Broker institucional danés. Uno de los más completos y regulados del mundo.",
    },
    "robinhood": {
        "nombre":     "Robinhood",
        "payout":     0.92,
        "assets":     ["SPY", "QQQ", "AAPL", "TSLA", "AMZN", "MSFT",
                       "NVDA", "META", "GOOGL", "AMD", "NFLX", "COIN",
                       "BTC/USD", "ETH/USD", "DOGE/USD"],
        "duraciones": [60, 300, 900, 3600, 86400],
        "notas":      "Sin comisiones. Popular entre traders jóvenes latinoamericanos en EEUU.",
    },
    "degiro": {
        "nombre":     "DEGIRO",
        "payout":     0.90,
        "assets":     ["SPY", "AAPL", "TSLA", "MSFT", "AMZN", "NVDA",
                       "META", "GOOGL", "DAX", "CAC40", "AEX",
                       "EUR/USD", "XAU/USD"],
        "duraciones": [60, 300, 900, 3600, 86400],
        "notas":      "Muy popular en España, Colombia, Argentina y México. "
                      "Comisiones muy bajas para acciones europeas y US.",
    },
    "ninjatrader": {
        "nombre":     "NinjaTrader",
        "payout":     0.93,
        "assets":     ["/ES", "/NQ", "/YM", "/RTY", "/GC", "/SI",
                       "/CL", "/NG", "/ZB", "/ZN",
                       "EUR/USD", "GBP/USD", "USD/JPY"],
        "duraciones": [60, 300, 900, 3600, 14400],
        "notas":      "Especializado en futuros. Muy usado por traders avanzados. "
                      "Soporta algoritmos y backtesting.",
    },
}

# Elementos de UI que Litch aprende a localizar
ELEMENTOS_UI = {
    "campo_monto":       "Campo donde se escribe el monto de apuesta",
    "selector_duracion": "Zona del selector de tiempo / vencimiento",
    "area_asset":        "Zona del nombre del activo actual",
    "boton_confirmar":   "Botón confirmar / aplicar (si existe)",
}

MIN_VALIDO        = 15    # trades mínimos para estadística fiable
KELLY_CAP         = 0.05  # máximo 5% del balance por trade
CICLO_CONSEJERO   = 60    # BrokerConsejero revisa cada 60s
TRADES_PARA_IA    = 20    # consultar IA cada N trades nuevos
MIN_VOZ_INTERVALO = 300   # no repetir sugerencia de voz antes de 5min
UMBRAL_MEJORA     = 8.0   # % mínimo de ventaja para sugerir cambio de activo


# ── Utilidades ────────────────────────────────────────────────────────────────

def _wr(stats: dict) -> float:
    w = stats.get("wins", 0)
    l = stats.get("losses", 0)
    return w / (w + l) if (w + l) > 0 else 0.50


def _kelly(p_win: float, payout: float) -> float:
    f = p_win - (1.0 - p_win) / max(payout, 0.01)
    return max(0.0, min(f, KELLY_CAP))


def _fuera_de_tws(x, y) -> bool:
    """¿Está esta coordenada libre de Interactive Brokers?

    Todos los clics de IQ Option usan posiciones absolutas de pantalla
    calibradas en su día. Si TWS ocupa ahora esa zona —porque IQ Option se
    cerró, o porque se movieron las ventanas— el clic entraría en el broker
    de acciones. Un clic de opciones binarias dentro de TWS no tiene ningún
    resultado bueno posible, así que se comprueba antes.
    """
    try:
        from . import manos as _manos
        if _manos._dentro_de_tws(x, y):
            print(f"[BrokerIQ] ⛔ Clic bloqueado en ({x},{y}): cae dentro "
                  f"de Interactive Brokers. Recalibre IQ Option.")
            return False
    except Exception:
        pass      # si el guardián falla, no se bloquea el uso normal
    return True


def _click_r(x: int, y: int):
    if _PG_OK and _fuera_de_tws(x, y):
        pyautogui.click(x, y, _pause=False)


# ─────────────────────────────────────────────────────────────────────────────
# BrokerConsejero — daemon proactivo de inteligencia
# ─────────────────────────────────────────────────────────────────────────────

class BrokerConsejero(threading.Thread):
    """
    Daemon que vive en segundo plano monitoreando el rendimiento del broker.

    Actúa como el "asesor interno" de Litch:
      - Detecta si hay un activo mejor disponible y lo sugiere
      - Con modo_autonomo: aplica los cambios directamente
      - Cada N trades, consulta a la IA (Claude/Ollama) y guarda la lección
      - Aprende de cada lección para mejorar sus decisiones futuras
    """

    def __init__(self, broker):
        super().__init__(daemon=True, name="BrokerConsejero")
        self._broker = broker
        self._app    = broker.app
        self._activo = True
        self._trades_desde_ia  = 0
        self._ultima_sugerencia = 0.0
        self._racha_perdidas    = 0

    def run(self):
        time.sleep(18)  # esperar arranque completo de la app
        # Auto-calibrar UI del broker al primer arranque
        try:
            estado = self._broker.estado_calibracion()
            if not all(estado.values()):
                self._app.log("[BrokerConsejero] Auto-calibrando UI del broker...")
                self._broker.calibrar_ui_auto()
        except Exception:
            pass
        while self._activo:
            try:
                self._ciclo()
            except Exception as e:
                self._app.log(f"[BrokerConsejero] Error: {e}")
            time.sleep(CICLO_CONSEJERO)

    # ── Ciclo principal ───────────────────────────────────────────────────────

    def _ciclo(self):
        app = self._app
        if not app.activo or not app.trading_on:
            return

        self._analizar_rendimiento()

        # Aprendizaje con IA cada TRADES_PARA_IA trades, pero como MÍNIMO cada
        # 15 min: cada consulta a Ollama es pesada en CPU y en sesiones largas
        # se disparaba sin parar, calentando el equipo y compitiendo con el
        # análisis en tiempo real. El cooldown lo mantiene ágil.
        _ahora_ia = __import__("time").time()
        if (self._trades_desde_ia >= TRADES_PARA_IA and
                _ahora_ia - getattr(self, "_t_ultima_ia", 0.0) >= 900):
            self._trades_desde_ia = 0
            self._t_ultima_ia = _ahora_ia
            threading.Thread(target=self._aprender_de_ia,
                             daemon=True, name="BrokerAprender").start()

    # ── Análisis proactivo ────────────────────────────────────────────────────

    def _analizar_rendimiento(self):
        app    = self._app
        broker = self._broker

        # Respetar intervalo mínimo entre sugerencias por voz
        if time.time() - self._ultima_sugerencia < MIN_VOZ_INTERVALO:
            return

        tabla        = broker.tabla_assets()
        asset_actual = app.mem["config"].get("asset_actual", "")
        if not tabla:
            return

        mejor        = tabla[0]
        stats_actual = next((r for r in tabla if r["asset"] == asset_actual), None)

        if not stats_actual:
            return

        diferencia = mejor["wr"] - stats_actual["wr"]
        es_autonomo = app.modo_autonomo and app.autoclick_on

        # ── Sugerir si hay alternativa claramente mejor ──────────────────────
        if (mejor["asset"] != asset_actual
                and diferencia >= UMBRAL_MEJORA
                and mejor["total"] >= MIN_VALIDO):

            self._ultima_sugerencia = time.time()

            if es_autonomo:
                app.log(f"[BrokerConsejero] Autónomo → cambiando a {mejor['asset']}")
                app.decir(app.txt(
                    f"Senor, detecto que {mejor['asset']} tiene {mejor['wr']:.0f}% "
                    f"de exito frente al {stats_actual['wr']:.0f}% de {asset_actual}. "
                    f"Aplicando el cambio automaticamente.",
                    f"Sir, {mejor['asset']} has {mejor['wr']:.0f}% success rate vs "
                    f"{stats_actual['wr']:.0f}% of {asset_actual}. Applying now."))
                threading.Thread(target=broker._bg_optimizar, args=(True,),
                                 daemon=True, name="BrokerAutoOpt").start()
            else:
                app.decir(app.txt(
                    f"Senor, {mejor['asset']} me da {mejor['wr']:.0f}% de exito en "
                    f"{mejor['total']} trades, {diferencia:.0f}% mas que {asset_actual}. "
                    f"Te recomiendo cambiarlo. Di 'configura el broker' para aplicarlo.",
                    f"Sir, {mejor['asset']} gives me {mejor['wr']:.0f}% success over "
                    f"{mejor['total']} trades, {diferencia:.0f}% better than {asset_actual}. "
                    f"I recommend switching. Say 'configure broker' to apply."))

        # ── Advertencia de hora mala ─────────────────────────────────────────
        elif stats_actual and stats_actual["total"] >= 10:
            score_hora = broker._score_hora_actual(asset_actual)
            if score_hora < 0.45:
                hora_txt = time.strftime("%H:%M")
                self._ultima_sugerencia = time.time()
                app.decir(app.txt(
                    f"Senor, historicamente las {hora_txt} no es mi mejor hora "
                    f"para {asset_actual}. Considera esperar o cambiar de activo.",
                    f"Sir, historically {hora_txt} is not my best time "
                    f"for {asset_actual}. Consider waiting or switching assets."))

    # ── Aprendizaje con IA ────────────────────────────────────────────────────

    def _aprender_de_ia(self):
        app    = self._app
        broker = self._broker

        tabla  = broker.tabla_assets()
        cfg    = broker.mejor_config()

        if not tabla:
            return

        # Construir contexto detallado
        lineas_stats = [
            f"{r['asset']}: {r['wr']:.0f}% ({r['total']} trades)"
            for r in tabla[:6]
        ]
        hora_score = {
            asset: broker._score_hora_actual(asset)
            for asset in [r["asset"] for r in tabla[:3]]
        }
        hora_txt = time.strftime("%H:%M")
        dia_txt  = time.strftime("%A")

        lecciones_previas = broker._cargar_lecciones()
        contexto_lecciones = ""
        if lecciones_previas:
            u = lecciones_previas[-1]
            contexto_lecciones = (
                f" Mi ultima leccion de IA ({u.get('fecha','')[:10]}): "
                f"{u.get('leccion','')[:120]}."
            )

        contexto = (
            f"Hora: {hora_txt} ({dia_txt}). "
            f"Broker: {cfg['broker']} (payout {broker.perfil.get('payout',0.85)*100:.0f}%). "
            f"Activo actual: {cfg['asset']} a {cfg['duracion']}s. "
            f"Stats por activo: {'; '.join(lineas_stats)}. "
            f"Score de hora para top activos: "
            f"{', '.join(f'{a}={v:.0%}' for a,v in hora_score.items())}."
            f"{contexto_lecciones}"
        )

        pregunta = (
            f"Analiza esta situación de trading en profundidad:\n"
            f"1) ¿Qué activo y duración debo priorizar AHORA con estos datos?\n"
            f"2) ¿La hora actual ({hora_txt}) favorece el trading en los top activos?\n"
            f"3) ¿Qué patrón o error debo corregir en mi operativa reciente?\n"
            f"4) Consejo específico de gestión de riesgo para el contexto actual.\n"
            f"Responde con puntos numerados, técnico y directo. Sin disclaimers genéricos."
        )

        respuesta = None
        try:
            if getattr(app, "usar_claude", False):
                from . import mente_claude
                if mente_claude.disponible():
                    # Usar responder_analisis para análisis más profundo con Fable 5
                    respuesta = mente_claude.responder_analisis(pregunta, contexto=contexto)
            if not respuesta and getattr(app, "usar_ollama", True):
                from . import mente
                if mente.disponible():
                    respuesta = mente.responder(f"{contexto}\n{pregunta}")
        except Exception as e:
            app.log(f"[BrokerConsejero] Error IA: {e}")

        if respuesta:
            broker._guardar_leccion(contexto, respuesta)
            app.log(f"[BrokerConsejero] Nueva leccion IA: {respuesta[:80]}…")
            app.decir(app.txt(
                f"Leccion nueva de la IA: {respuesta[:200]}",
                f"New AI lesson: {respuesta[:200]}"))

    # ── Notificaciones desde registrar_trade ─────────────────────────────────

    def notificar_trade(self, resultado: str):
        """Actualiza el contador y la racha de pérdidas."""
        self._trades_desde_ia += 1
        if resultado == "LOSS":
            self._racha_perdidas += 1
        else:
            self._racha_perdidas = 0

        # Reacción inmediata a racha de pérdidas
        if self._racha_perdidas >= 4:
            threading.Thread(
                target=self._reaccionar_racha,
                args=(self._racha_perdidas,),
                daemon=True, name="BrokerRacha").start()

    def _reaccionar_racha(self, n: int):
        app    = self._app
        broker = self._broker
        app.log(f"[BrokerConsejero] Racha de {n} pérdidas detectada")

        cfg          = broker.mejor_config()
        asset_actual = app.mem["config"].get("asset_actual", "")
        es_autonomo  = app.modo_autonomo and app.autoclick_on

        if cfg["asset"] != asset_actual and cfg["trades"] >= MIN_VALIDO:
            if es_autonomo:
                app.decir(app.txt(
                    f"Senor, {n} perdidas seguidas. Cambiando a {cfg['asset']} "
                    f"que me da {cfg['win_rate']:.0f}% de exito.",
                    f"Sir, {n} consecutive losses. Switching to {cfg['asset']} "
                    f"with {cfg['win_rate']:.0f}% success rate."))
                broker._bg_optimizar(forzar=True)
            else:
                app.decir(app.txt(
                    f"Senor, {n} perdidas seguidas. Mi mejor alternativa es "
                    f"{cfg['asset']} con {cfg['win_rate']:.0f}% de exito. "
                    f"Di 'configura el broker' para aplicarlo.",
                    f"Sir, {n} consecutive losses. My best alternative is "
                    f"{cfg['asset']} with {cfg['win_rate']:.0f}% win rate. "
                    f"Say 'configure broker' to apply."))
        else:
            # Sin datos suficientes → consultar IA
            sit = (
                f"Llevo {n} perdidas seguidas con {asset_actual}. "
                f"Sin alternativas con suficientes datos. ¿Que recomiendas?"
            )
            consejo = broker.consultar_ia(sit)
            if consejo:
                app.log(f"[BrokerConsejero/IA] {consejo[:100]}")
                app.decir(consejo[:200])

        self._racha_perdidas = 0  # reset para no repetir

    def detener(self):
        self._activo = False


# ─────────────────────────────────────────────────────────────────────────────
# BrokerUniversal — motor principal
# ─────────────────────────────────────────────────────────────────────────────

class BrokerUniversal:
    """
    Controla cualquier broker de trading desde el ratón.

    Aprende la UI de cada plataforma, acumula estadísticas multi-factor
    (asset × duración × hora del día) y trabaja junto al BrokerConsejero
    para operar de forma autónoma e inteligente.
    """

    def __init__(self, app):
        self.app       = app
        self._lock     = threading.Lock()
        self._ruta_stats     = os.path.join(mem_mod.ruta_memoria_ap(), "broker_stats.json")
        self._ruta_config    = os.path.join(mem_mod.ruta_memoria_ap(), "broker_config.json")
        self._ruta_lecciones = os.path.join(mem_mod.ruta_memoria_ap(), "broker_lecciones.json")
        self._stats: dict    = {}
        self._ui_cfg: dict   = {}
        self._cargar()

        # Daemon proactivo — arranca junto al broker
        self.consejero = BrokerConsejero(self)
        self.consejero.start()

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _cargar(self):
        for ruta, attr in ((self._ruta_stats, "_stats"),
                           (self._ruta_config, "_ui_cfg")):
            try:
                with open(ruta, encoding="utf-8") as f:
                    setattr(self, attr, json.load(f))
            except Exception:
                setattr(self, attr, {})

    def _guardar_stats(self):
        try:
            with open(self._ruta_stats, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _guardar_config(self):
        try:
            with open(self._ruta_config, "w", encoding="utf-8") as f:
                json.dump(self._ui_cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── Lecciones de IA ───────────────────────────────────────────────────────

    def _cargar_lecciones(self) -> list:
        try:
            with open(self._ruta_lecciones, encoding="utf-8") as f:
                return json.load(f).get("lecciones", [])
        except Exception:
            return []

    def _guardar_leccion(self, contexto: str, leccion: str):
        lecciones = self._cargar_lecciones()
        lecciones.append({
            "fecha":    time.strftime("%Y-%m-%dT%H:%M:%S"),
            "contexto": contexto[:300],
            "leccion":  leccion[:500],
        })
        # Conservar solo las últimas 30 lecciones
        if len(lecciones) > 30:
            lecciones = lecciones[-30:]
        try:
            with open(self._ruta_lecciones, "w", encoding="utf-8") as f:
                json.dump({"lecciones": lecciones}, f,
                          ensure_ascii=False, indent=2)
        except Exception:
            pass

    def lecciones_recientes(self, n: int = 5) -> list:
        return self._cargar_lecciones()[-n:]

    # ── Broker activo ─────────────────────────────────────────────────────────

    @property
    def broker_activo(self) -> str:
        return self.app.mem["config"].get("broker_activo", "iq_option")

    @property
    def perfil(self) -> dict:
        return PERFILES.get(self.broker_activo, PERFILES["generico"])

    @property
    def _ui(self) -> dict:
        return self._ui_cfg.setdefault(self.broker_activo, {})

    def cambiar_broker(self, clave: str) -> bool:
        if clave not in PERFILES and clave not in self._ui_cfg:
            return False
        self.app.mem["config"]["broker_activo"] = clave
        mem_mod.guardar(self.app.mem)
        nombre = PERFILES.get(clave, {}).get("nombre", clave)
        self.app.log(f"[Broker] Activo → {nombre}")
        return True

    # ── Registro de trades con hora del día ───────────────────────────────────

    def registrar_trade(self, asset: str, duracion: int, resultado: str,
                        monto: float = None):
        """
        Registra un trade acumulando:
          - wins/losses totales
          - wins/losses por hora del día (cuándo operar)
          - wins/losses por monto (qué cifra funciona mejor)
        """
        broker = self.broker_activo
        hora   = time.strftime("%H")  # "09", "14", etc.

        with self._lock:
            b = self._stats.setdefault(broker, {})
            b.setdefault(asset, {})
            dur_k = str(duracion)
            b[asset].setdefault(dur_k, {
                "wins": 0, "losses": 0,
                "ultima": "",
                "por_hora":  {},
                "por_monto": {},
            })
            s = b[asset][dur_k]
            # Compatibilidad con registros viejos sin por_monto
            s.setdefault("por_monto", {})

            # Estadística global
            if resultado == "WIN":
                s["wins"] += 1
            else:
                s["losses"] += 1
            s["ultima"] = time.strftime("%Y-%m-%dT%H:%M:%S")

            # Estadística por hora
            s["por_hora"].setdefault(hora, {"wins": 0, "losses": 0})
            if resultado == "WIN":
                s["por_hora"][hora]["wins"] += 1
            else:
                s["por_hora"][hora]["losses"] += 1

            # Estadística por monto (aprende qué cifra rinde más)
            if monto is not None and monto > 0:
                m_k = str(int(round(monto)))
                s["por_monto"].setdefault(m_k, {"wins": 0, "losses": 0})
                if resultado == "WIN":
                    s["por_monto"][m_k]["wins"] += 1
                else:
                    s["por_monto"][m_k]["losses"] += 1

            self._guardar_stats()

        # Notificar al consejero (racha, conteo para IA)
        self.consejero.notificar_trade(resultado)

    # ── Scoring multi-factor ──────────────────────────────────────────────────

    def _score_hora_actual(self, asset: str) -> float:
        """
        Win rate del activo en la hora actual del día.
        Devuelve 0.5 si no hay datos suficientes.
        """
        hora = time.strftime("%H")
        stats = self.stats_broker().get(asset, {})
        wins = losses = 0
        for dur_s in stats.values():
            h = dur_s.get("por_hora", {}).get(hora, {})
            wins   += h.get("wins",   0)
            losses += h.get("losses", 0)
        total = wins + losses
        return wins / total if total >= 5 else 0.50

    def score_asset(self, asset: str) -> float:
        """
        Puntaje compuesto (0–1) para un activo:
          70% win rate histórico + 30% rendimiento en la hora actual
        """
        durs  = self.stats_broker().get(asset, {})
        w_tot = sum(d.get("wins",   0) for d in durs.values())
        l_tot = sum(d.get("losses", 0) for d in durs.values())
        total = w_tot + l_tot
        if total < MIN_VALIDO:
            return 0.50

        wr_global = w_tot / total
        wr_hora   = self._score_hora_actual(asset)
        return 0.70 * wr_global + 0.30 * wr_hora

    # ── Análisis y recomendaciones ────────────────────────────────────────────

    def stats_broker(self) -> dict:
        return self._stats.get(self.broker_activo, {})

    def mejor_asset(self) -> str:
        mejor, mejor_score = None, 0.0
        for asset in self.stats_broker():
            sc = self.score_asset(asset)
            if sc > mejor_score:
                mejor_score, mejor = sc, asset
        assets = self.perfil.get("assets", ["EUR/AUD OTC"])
        return mejor or self.app.mem["config"].get("asset_actual", assets[0])

    def mejor_duracion(self, asset: str) -> int:
        stats = self.stats_broker().get(asset, {})
        durs_perfil = self.perfil.get("duraciones", [60])
        mejor_dur, mejor_wr = durs_perfil[0], 0.0
        for dur_k, s in stats.items():
            total = s.get("wins", 0) + s.get("losses", 0)
            if total < MIN_VALIDO:
                continue
            wr = s.get("wins", 0) / total
            if wr > mejor_wr:
                mejor_wr, mejor_dur = wr, int(dur_k)
        return mejor_dur

    def mejor_monto(self) -> float:
        """Elige el monto óptimo:
        1. Si hay lista 'montos_test' configurada → elige el de mejor win rate
           (los no probados se prueban primero por rotación).
        2. Si no → Kelly clásico sobre el balance demo."""
        # Modo manual: el usuario fija el monto directamente
        if self.app.mem["config"].get("monto_modo_manual"):
            return float(self.app.mem["config"].get("monto_base", 10.0))

        # Lista de montos a probar/rotar
        montos_cfg = str(self.app.mem["config"].get("montos_test", "")).strip()
        if montos_cfg:
            montos = []
            for m in montos_cfg.split(","):
                try:
                    v = float(m.strip())
                    if v > 0:
                        montos.append(v)
                except ValueError:
                    pass
            if montos:
                return self._mejor_monto_de_lista(montos)

        # Fallback: Kelly clásico
        asset  = self.mejor_asset()
        dur_k  = str(self.mejor_duracion(asset))
        s      = self.stats_broker().get(asset, {}).get(dur_k, {})
        total  = s.get("wins", 0) + s.get("losses", 0)
        p_win  = s.get("wins", 0) / total if total >= 10 else 0.541
        payout = self.perfil.get("payout", 0.85)
        frac   = _kelly(p_win, payout)
        bal    = float(self.app.mem["config"].get("balance_demo", 10000))
        return max(1.0, round(frac * bal, 2))

    def _mejor_monto_de_lista(self, montos: list) -> float:
        """De los montos configurados, devuelve el de mejor win rate.
        Los que tienen < 5 trades se prueban primero (rotación de exploración)."""
        stats = self.stats_broker()
        resultados = []
        for m in montos:
            m_k = str(int(round(m)))
            wins = losses = 0
            for durs in stats.values():
                for dur_s in durs.values():
                    pm = dur_s.get("por_monto", {}).get(m_k, {})
                    wins   += pm.get("wins",   0)
                    losses += pm.get("losses", 0)
            total = wins + losses
            wr    = wins / total if total >= 5 else None
            resultados.append((m, total, wr))

        # Exploración primero: si algún monto tiene < 5 trades, probarlo
        sin_datos = [r for r in resultados if r[2] is None]
        if sin_datos:
            return sin_datos[0][0]

        # Explotación: el de mayor win rate
        mejor = max(resultados, key=lambda x: x[2])
        return mejor[0]

    def tabla_montos(self) -> list:
        """Stats resumidas por monto configurado — para mostrar en el UI."""
        montos_cfg = str(self.app.mem["config"].get("montos_test", "")).strip()
        if not montos_cfg:
            return []
        montos = []
        for m in montos_cfg.split(","):
            try:
                v = float(m.strip())
                if v > 0:
                    montos.append(v)
            except ValueError:
                pass
        stats  = self.stats_broker()
        filas  = []
        for m in montos:
            m_k = str(int(round(m)))
            wins = losses = 0
            for durs in stats.values():
                for dur_s in durs.values():
                    pm = dur_s.get("por_monto", {}).get(m_k, {})
                    wins   += pm.get("wins",   0)
                    losses += pm.get("losses", 0)
            total = wins + losses
            wr    = round(wins / total * 100, 1) if total >= 1 else None
            filas.append({"monto": m, "wins": wins, "losses": losses,
                          "total": total, "wr": wr})
        return filas

    def mejor_config(self) -> dict:
        asset    = self.mejor_asset()
        duracion = self.mejor_duracion(asset)
        monto    = self.mejor_monto()
        dur_k    = str(duracion)
        s        = self.stats_broker().get(asset, {}).get(dur_k, {})
        total    = s.get("wins", 0) + s.get("losses", 0)
        wr       = _wr(s) * 100 if total > 0 else 0.0
        score_h  = self._score_hora_actual(asset)
        return {
            "broker":    self.perfil.get("nombre", self.broker_activo),
            "asset":     asset,
            "duracion":  duracion,
            "monto":     monto,
            "win_rate":  round(wr, 1),
            "trades":    total,
            "score_hora": round(score_h * 100, 1),
        }

    def tabla_assets(self) -> list:
        """Lista de assets ordenada por score compuesto (win rate + hora)."""
        filas = []
        for asset, durs in self.stats_broker().items():
            w = sum(d.get("wins",   0) for d in durs.values())
            l = sum(d.get("losses", 0) for d in durs.values())
            total = w + l
            if total == 0:
                continue
            filas.append({
                "asset":      asset,
                "wins":       w,
                "losses":     l,
                "total":      total,
                "wr":         round(w / total * 100, 1),
                "score_hora": round(self._score_hora_actual(asset) * 100, 1),
                "score_comp": round(self.score_asset(asset) * 100, 1),
            })
        return sorted(filas, key=lambda x: x["score_comp"], reverse=True)

    def resumen_texto(self) -> str:
        cfg   = self.mejor_config()
        total = sum(s.get("wins", 0) + s.get("losses", 0)
                    for durs in self.stats_broker().values()
                    for s in durs.values())
        if total == 0:
            return self.app.txt(
                f"Aun sin estadisticas para {cfg['broker']}, senor. "
                "Opera primero para que empiece a aprender.",
                f"No stats yet for {cfg['broker']}, sir. Trade first so I can learn.")
        hora_adv = ""
        if cfg["score_hora"] < 45:
            hora_adv = self.app.txt(
                " Atencion: la hora actual no favorece este activo historicamente.",
                " Note: current hour is historically weak for this asset.")
        if self.app.idioma == "es":
            return (f"En {cfg['broker']}: te recomiendo {cfg['asset']} a "
                    f"{cfg['duracion']}s con ${cfg['monto']:.0f}. "
                    f"Tasa de exito {cfg['win_rate']:.0f}% ({cfg['trades']} trades), "
                    f"score de hora actual {cfg['score_hora']:.0f}%.{hora_adv}")
        return (f"On {cfg['broker']}: I recommend {cfg['asset']} at "
                f"{cfg['duracion']}s with ${cfg['monto']:.0f}. "
                f"Win rate {cfg['win_rate']:.0f}% ({cfg['trades']} trades), "
                f"current hour score {cfg['score_hora']:.0f}%.{hora_adv}")

    # ── Auto-optimización ─────────────────────────────────────────────────────

    def auto_optimizar(self, forzar: bool = False):
        if not (self.app.autoclick_on and self.app.modo_autonomo) and not forzar:
            return
        threading.Thread(target=self._bg_optimizar, args=(forzar,),
                         daemon=True, name="BrokerOpt").start()

    def _bg_optimizar(self, forzar: bool = False):
        app = self.app
        cfg = self.mejor_config()
        asset_actual = app.mem["config"].get("asset_actual", "")
        dur_actual   = int(app.mem["config"].get("periodo_vela", 30))
        cambia_asset = cfg["asset"] != asset_actual and cfg["trades"] >= MIN_VALIDO
        cambia_dur   = cfg["duracion"] != dur_actual  and cfg["trades"] >= MIN_VALIDO

        if not forzar and not cambia_asset and not cambia_dur:
            return

        app.log(f"[Broker] Óptimo → {cfg['asset']} | "
                f"{cfg['duracion']}s | ${cfg['monto']:.0f} | "
                f"{cfg['win_rate']:.1f}% | hora: {cfg['score_hora']:.0f}%")

        if cambia_asset and self.set_asset(cfg["asset"]):
            app.mem["config"]["asset_actual"] = cfg["asset"]
            mem_mod.guardar(app.mem)
            if not forzar:  # ya habló el consejero si es forzado
                app.decir(app.txt(
                    f"Cambiando a {cfg['asset']}, mi mejor rendimiento: "
                    f"{cfg['win_rate']:.0f}%, senor.",
                    f"Switching to {cfg['asset']}, best performer: "
                    f"{cfg['win_rate']:.0f}%, sir."))

        if cambia_dur and self.set_duracion(cfg["duracion"]):
            app.mem["config"]["periodo_vela"] = cfg["duracion"]
            mem_mod.guardar(app.mem)

        # Monto: solo cambiar automáticamente si NO está en modo manual
        # (si monto_modo_manual=True el usuario controla el monto — no tocar)
        if not app.mem["config"].get("monto_modo_manual"):
            if hasattr(self, "set_monto_iq"):
                self.set_monto_iq(cfg["monto"])
            else:
                self.set_monto(cfg["monto"])

        # Cambiar período del gráfico si cambió la duración
        if cambia_dur and hasattr(self, "configurar_periodo_iq"):
            self.configurar_periodo_iq(cfg["duracion"])

    # ── Control del ratón ─────────────────────────────────────────────────────

    def _pos(self, elemento: str) -> Optional[list]:
        pos = self._ui.get(elemento) or self.app.mem["config"].get(elemento)
        return pos if pos and len(pos) >= 2 else None

    def set_monto(self, monto: float) -> bool:
        pos = self._pos("campo_monto")
        if not pos or not _PG_OK:
            self.app.log("[Broker] campo_monto sin calibrar.")
            return False
        try:
            _click_r(int(pos[0]), int(pos[1]))
            time.sleep(0.12)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.06)
            monto_str = f"{monto:.2f}".rstrip("0").rstrip(".")
            pyautogui.typewrite(monto_str, interval=0.04)
            pyautogui.press("tab")
            time.sleep(0.10)
            self.app.log(f"[Broker] Monto → ${monto_str}")
            return True
        except Exception as e:
            self.app.log(f"[Broker] Error monto: {e}")
            return False

    def set_duracion(self, segundos: int) -> bool:
        pos = self._pos("selector_duracion")
        if not pos or not _PG_OK:
            self.app.log("[Broker] selector_duracion sin calibrar.")
            return False
        try:
            _click_r(int(pos[0]), int(pos[1]))
            time.sleep(0.35)
            duraciones = self.perfil.get("duraciones", [60, 120, 300])
            try:
                idx = duraciones.index(segundos)
            except ValueError:
                idx = 0
            _dx, _dy = int(pos[0]), int(pos[1]) + 30 + idx * 32
            if not _fuera_de_tws(_dx, _dy):
                return False
            pyautogui.click(_dx, _dy)
            time.sleep(0.20)
            self.app.log(f"[Broker] Duración → {segundos}s")
            return True
        except Exception as e:
            self.app.log(f"[Broker] Error duración: {e}")
            return False

    def set_asset(self, nombre: str) -> bool:
        """
        Flujo universal de cambio de activo:
        clic en área → búsqueda → escribir nombre → Down → Enter
        Funciona en IQ Option, Quotex, Deriv, Binomo, Olymp Trade, etc.
        """
        pos = self._pos("area_asset")
        if not pos or not _PG_OK:
            self.app.log("[Broker] area_asset sin calibrar.")
            return False
        try:
            _click_r(int(pos[0]), int(pos[1]))
            time.sleep(0.55)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.06)
            base = nombre.replace(" OTC", "").replace("/", "").strip()
            pyautogui.typewrite(base, interval=0.07)
            time.sleep(0.65)
            pyautogui.press("down")
            time.sleep(0.15)
            pyautogui.press("enter")
            time.sleep(0.30)
            self.app.log(f"[Broker] Asset → {nombre}")
            return True
        except Exception as e:
            self.app.log(f"[Broker] Error asset: {e}")
            return False

    def aplicar_config_completa(self, cfg: Optional[dict] = None) -> dict:
        """Aplica asset + duración + monto. Devuelve dict con resultados."""
        if cfg is None:
            cfg = self.mejor_config()
        resultado = {"asset": False, "duracion": False, "monto": False}
        if self.set_asset(cfg["asset"]):
            resultado["asset"] = True
        time.sleep(0.3)
        if self.set_duracion(cfg["duracion"]):
            resultado["duracion"] = True
        time.sleep(0.3)
        if self.set_monto(cfg["monto"]):
            resultado["monto"] = True
        ok = sum(resultado.values())
        self.app.log(f"[Broker] Config aplicada: {ok}/3 OK")
        return resultado

    # ── Calibración automática de UI ──────────────────────────────────────────

    def calibrar_ui_auto(self) -> dict:
        """Detecta automáticamente los controles de IQ Option en la pantalla.

        Usa vision.detectar_ui_iq() primero (más específico para IQ Option),
        con fallback al método genérico de brillo si no detecta nada.
        También usa la posición del botón SUBE como ancla cuando está calibrado.
        """
        # Método 1: detección específica IQ Option
        resultado = vision.detectar_ui_iq()

        # Método 2: si falla, usar ancla en botón SUBE calibrado
        if not resultado.get("campo_monto"):
            btn_v = (self._pos("boton_verde")
                     or self.app.mem["config"].get("boton_verde"))
            if btn_v and len(btn_v) >= 2:
                bx, by = int(btn_v[0]), int(btn_v[1])
                # En IQ Option: monto está ~250px abajo de SUBE, mismo X
                resultado["campo_monto"]       = [bx, by + 250]
                resultado["selector_duracion"] = [bx, by - 140]
                self.app.log("[Broker] UI estimada desde boton SUBE.")

        # Método 3: fallback genérico (brillo)
        if not resultado.get("campo_monto"):
            try:
                import numpy as np
                img = vision.capturar_pantalla_completa()
                if img is not None:
                    h, w = img.shape[:2]
                    xo, yo = int(w * 0.60), int(h * 0.35)
                    sub = img[yo:, xo:]
                    r = sub[:, :, 2].astype(float)
                    g = sub[:, :, 1].astype(float)
                    b = sub[:, :, 0].astype(float)
                    mask = (r > 180) & (g > 180) & (b > 180)
                    ys, xs = np.where(mask)
                    if len(ys) > 200:
                        cx = int(xs.mean()) + xo
                        cy = int(ys.mean()) + yo
                        resultado["campo_monto"]       = [cx, cy]
                        resultado["selector_duracion"] = [cx, max(30, cy - 60)]
            except Exception:
                pass

        if resultado:
            self._ui.update(resultado)
            self._guardar_config()
            for k, v in resultado.items():
                # El portero de la visión: si el señor la puso en
                # pantalla completa, una recalibración no puede
                # encogerla en silencio. Ya pasó tres veces.
                _ok_v = True
                try:
                    from . import vision_total as _vt_p
                    _ok_v = _vt_p.proteger(self.app, k, v)
                except Exception:
                    pass
                if _ok_v:
                    self.app.mem["config"][k] = v
            mem_mod.guardar(self.app.mem)
            self.app.log(f"[Broker] UI calibrada: {list(resultado.keys())}")
        return resultado

    # ── Control específico IQ Option ──────────────────────────────────────────

    def set_monto_iq(self, monto: float) -> bool:
        """Establece el monto en IQ Option.

        IQ Option acepta click en el campo y escritura directa.
        También intenta con triple-click (seleccionar todo) antes de escribir.
        """
        pos = self._pos("campo_monto")
        if not pos or not _PG_OK:
            self.app.log("[Broker] campo_monto sin calibrar — usa Broker → Auto-calibrar.")
            return False
        try:
            x, y = int(pos[0]), int(pos[1])
            if not _fuera_de_tws(x, y):
                return False
            # Triple-click para seleccionar el valor anterior completo
            pyautogui.click(x, y, clicks=3, interval=0.07, _pause=False)
            time.sleep(0.10)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            monto_str = f"{monto:.2f}".rstrip("0").rstrip(".")
            pyautogui.typewrite(monto_str, interval=0.05)
            time.sleep(0.08)
            pyautogui.press("tab")
            time.sleep(0.10)
            self.app.log(f"[Broker] Monto IQ → ${monto_str}")
            return True
        except Exception as e:
            self.app.log(f"[Broker] Error monto IQ: {e}")
            return False

    def configurar_periodo_iq(self, segundos: int) -> bool:
        """Cambia el período de la gráfica en IQ Option.

        Intenta hacer clic en el selector de período que aparece en la esquina
        inferior izquierda del gráfico (muestra "1m", "5m", etc.).
        """
        if not _PG_OK:
            return False
        region = self.app.mem["config"].get("region_grafico")
        if not region or len(region) < 4:
            self.app.log("[Broker] Sin región calibrada para cambiar período.")
            return False
        try:
            gx1, gy1, gx2, gy2 = [int(v) for v in region]
            # El selector de período está en la esquina inferior-izquierda del gráfico
            px = gx1 + 70   # ~70px desde el borde izquierdo
            py = gy2 - 20   # ~20px sobre el borde inferior
            if not _fuera_de_tws(px, py):
                return False
            pyautogui.click(px, py, _pause=False)
            time.sleep(0.45)
            # Mapa de segundos a índice aproximado en el menú de IQ Option
            _mapa = {5: 0, 10: 1, 15: 2, 30: 3, 60: 4, 120: 5, 300: 6}
            idx   = _mapa.get(segundos, 4)   # default 1 min
            for _ in range(idx):
                pyautogui.press("down")
                time.sleep(0.08)
            pyautogui.press("enter")
            time.sleep(0.25)
            self.app.log(f"[Broker] Período gráfica → {segundos}s")
            return True
        except Exception as e:
            self.app.log(f"[Broker] Error período: {e}")
            return False

    def guardar_posicion(self, elemento: str, x: int, y: int):
        self._ui[elemento] = [x, y]
        self._guardar_config()
        self.app.mem["config"][elemento] = [x, y]
        mem_mod.guardar(self.app.mem)
        self.app.log(f"[Broker] {elemento} → ({x}, {y})")

    def estado_calibracion(self) -> dict:
        return {elem: (self._pos(elem) is not None) for elem in ELEMENTOS_UI}

    # ── Consulta estratégica a IA ─────────────────────────────────────────────

    def consultar_ia(self, situacion: str = "") -> str:
        """
        Consulta a Claude o Ollama para orientación estratégica.
        Incorpora lecciones previas para que Litch aprenda progresivamente.
        """
        if not situacion:
            tabla  = self.tabla_assets()
            lineas = [f"{r['asset']}: {r['wr']:.0f}% score {r['score_comp']:.0f}%"
                      for r in tabla[:5]]
            cfg    = self.mejor_config()
            situacion = (
                f"Broker: {cfg['broker']}. "
                f"Payout: {self.perfil.get('payout', 0.85)*100:.0f}%. "
                f"Stats: {'; '.join(lineas) if lineas else 'sin datos'}. "
                f"Hora actual: {time.strftime('%H:%M')}."
            )

        # Incorporar lección más reciente si existe
        lecciones = self._cargar_lecciones()
        if lecciones:
            u = lecciones[-1]
            situacion += f" Leccion previa de IA: {u.get('leccion','')[:100]}."

        pregunta = (
            f"Consulta estratégica de Litch:\n"
            f"1) ¿Qué activo y duración priorizarías AHORA con estos datos de mercado?\n"
            f"2) ¿El horario actual favorece o perjudica el trading en los activos disponibles?\n"
            f"3) ¿Qué monto recomiendas según la volatilidad y el win rate actual?\n"
            f"4) Una regla de gestión de riesgo específica para el contexto dado.\n"
            f"Responde con puntos numerados, técnico y directo."
        )

        try:
            if getattr(self.app, "usar_claude", False):
                from . import mente_claude
                if mente_claude.disponible():
                    r = mente_claude.responder_analisis(pregunta, contexto=situacion)
                    if r:
                        return r
            if getattr(self.app, "usar_ollama", True):
                from . import mente
                if mente.disponible():
                    r = mente.responder(pregunta)
                    if r:
                        return r
        except Exception as e:
            self.app.log(f"[Broker] Error IA: {e}")

        cfg = self.mejor_config()
        return self.app.txt(
            f"Segun mis datos: usa {cfg['asset']} a {cfg['duracion']}s con "
            f"${cfg['monto']:.0f} ({cfg['win_rate']:.0f}% exito, {cfg['trades']} trades).",
            f"Based on my data: use {cfg['asset']} at {cfg['duracion']}s with "
            f"${cfg['monto']:.0f} ({cfg['win_rate']:.0f}% win rate, {cfg['trades']} trades).")

    # ── Resumen de sesión con Fable 5 ─────────────────────────────────────────

    def resumen_sesion_ia(self) -> str:
        """
        Análisis completo de sesión por Fable 5.
        Agrega todos los trades, patrones de éxito/fallo, horarios,
        activos y genera un plan concreto para la próxima sesión.
        Devuelve el reporte como string (también lo loguea).
        """
        try:
            from . import mente_claude as _mc
            if not _mc.disponible():
                return "Fable 5 no disponible (configura la API key de Claude)."
        except Exception:
            return "Módulo de IA no disponible."

        app = self.app
        est = app.mem.get("estadisticas", {})
        tot = est.get("aciertos", 0) + est.get("fallos", 0)
        if tot < 3:
            return "Necesitas al menos 3 trades para generar un resumen de sesión."

        tasa     = est.get("aciertos", 0) / tot * 100
        p_win    = est.get("aciertos", 0) / tot
        kelly    = p_win - (1.0 - p_win) / max(self.perfil.get("payout", 0.85), 0.1)

        # Top activos
        tabla    = self.tabla_assets()
        top3     = [f"{r['asset']}(WR={r['wr']:.0f}%,n={r['total']})"
                    for r in tabla[:3]] if tabla else ["sin datos"]

        # Lecciones previas (últimas 3)
        lecciones = self._cargar_lecciones()[-3:]
        lecc_txt  = " | ".join(
            f"[{l.get('fecha','')[:10]}] {l.get('leccion','')[:80]}"
            for l in lecciones) if lecciones else "ninguna"

        # Racha actual y horas malas (si FalloDB está disponible)
        try:
            from .fallo_db import FalloDB as _fdb
            from . import memoria as _mem_mod
            _ruta_fdb = os.path.join(_mem_mod.ruta_memoria_ap(), "fallo_db.json")
            fdb      = _fdb(_ruta_fdb)
            racha    = fdb.racha_actual()
            horarios = fdb.horarios_malos()
            racha_txt = f"{racha.get('n',0)} {racha.get('tipo','?')}"
            horas_txt = ", ".join(list(horarios)[:4]) if horarios else "ninguna"
        except Exception:
            racha_txt = "N/D"
            horas_txt = "N/D"

        # Mejor configuración actual
        cfg = self.mejor_config()

        contexto = (
            f"═══ RESUMEN DE SESIÓN TRADING ═══\n"
            f"Total trades: {tot}  |  Win Rate: {tasa:.1f}%\n"
            f"Aciertos: {est.get('aciertos',0)}  |  Fallos: {est.get('fallos',0)}\n"
            f"Kelly Criterion: {kelly:.3f} "
            f"({'RENTABLE' if kelly > 0 else 'EN PÉRDIDA — WR debe superar 54.1%'})\n"
            f"Racha actual: {racha_txt}\n"
            f"Top activos: {' / '.join(top3)}\n"
            f"Activo recomendado: {cfg['asset']} a {cfg['duracion']}s\n"
            f"Horas con más pérdidas: {horas_txt}\n"
            f"Payout: {self.perfil.get('payout', 0.85)*100:.0f}%\n"
            f"Lecciones IA previas: {lecc_txt}"
        )

        pregunta = (
            "Análisis completo de sesión de trading — genera un informe ejecutivo:\n\n"
            "1) DIAGNÓSTICO MATEMÁTICO: ¿Qué dice el Kelly Criterion sobre la "
            "rentabilidad actual? ¿Qué Win Rate exacto se necesita y cuánto falta?\n\n"
            "2) PATRONES DE FALLO: Basado en las horas problemáticas y las lecciones "
            "previas, ¿qué error sistemático está cometiendo el sistema?\n\n"
            "3) ACTIVO ÓPTIMO: ¿Por qué es el activo recomendado el mejor ahora y "
            "en qué horario específico es más efectivo?\n\n"
            "4) PLAN SIGUIENTE SESIÓN: 3 acciones concretas y medibles para mejorar "
            "el Win Rate en los próximos 20 trades.\n\n"
            "5) SEÑAL DE ALERTA: ¿Hay algún patrón en los datos que indique que se "
            "debe pausar el trading por riesgo de sobreentrenamiento o destrucción de cuenta?\n\n"
            "Sé específico con números. Técnico y directo. Sin disclaimers genéricos."
        )

        try:
            respuesta = _mc.responder_analisis(pregunta, contexto=contexto)
            if respuesta:
                reporte = (
                    f"{'═'*60}\n"
                    f"INFORME FABLE 5 — RESUMEN DE SESIÓN\n"
                    f"{'═'*60}\n"
                    f"{contexto}\n"
                    f"{'─'*60}\n"
                    f"ANÁLISIS FABLE 5:\n{respuesta}\n"
                    f"{'═'*60}"
                )
                app.log(f"[Fable5/Sesión] {respuesta[:200]}…")
                # Guardar como lección
                self._guardar_leccion(contexto, respuesta[:300])
                return reporte
        except Exception as e:
            app.log(f"[Fable5/Sesión] Error: {e}")

        return f"No se pudo generar el resumen. Contexto capturado:\n{contexto}"
