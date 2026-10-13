"""Agente de trading — observa el gráfico, aprende y actúa.

Ciclo rápido (250 ms):
  • Fase cierre  (primeros 2 s del período): lee color de la vela, verifica
    si la señal anterior acertó, registra y reentrena.
  • Fase pre-cálculo (5 s antes del cierre): lanza todos los modelos en un
    hilo background para tener la decisión lista al instante.
  • Al inicio del nuevo período: ejecuta el trade pre-calculado si hay
    consenso + Bayes + FalloDB aprueba.

Métodos de consenso (9 votos):
  1. Markov      — patrón de 3 velas con estadística bayesiana
  2. Estadística — análisis de frecuencias y rachas
  3. Red Maestra — CNN+LSTM+MLP ensemble
  4. Pronóstico  — entropía + ciclos + series temporales
  5. Indicadores — RSI, MACD, BB, Stoch, Williams, ATR, Hurst, Entropía, ADX, RVI, CCI, Fisher
  6. RL-DQN      — agente Q-learning que aprende de cada trade (Dueling DQN v3, 37 features)
  7. SMC/LWS     — BOS, CHoCH, Order Blocks, FVG, Liquidity Sweeps, Killzones
  8. Patrones    — 20 patrones de velas japonesas (Hammer, Engulfing, Morning Star, etc.)
  9. S/R         — Soporte y Resistencia automático (Pivots, Swing Points, Fibonacci)

Protecciones:
  • MonitorTrade  — vigila el P&L en tiempo real y activa Rollover si va en rojo
  • FalloDB       — correlaciona fallos, pausa en rachas de pérdidas, voz honesta
  • Kelly         — calcula tamaño óptimo de apuesta en cada señal
  • Stop temporal — pausa automática si pierdes N seguidos (evita destrucción de cuenta)

SOLO PARA CUENTA DEMO hasta alcanzar >60% de precisión en 100+ trades.
"""
import concurrent.futures as _cf
import csv
import os
import threading
import time

import numpy as np

from . import estadistica, inferencia, manos, pronostico, vision
from . import indicadores  as ind_mod
from . import analizador_smc as _smc
from . import memoria as mem_mod
from . import mente_claude as _fable
from . import conciencia as _con
from . import modo_practica as _practica_mod
from . import modo_profesional as _pro_mod
from .fallo_db             import FalloDB
from .monitor_trade        import MonitorTrade
from .rl_agente            import AgenteRL
from .session_tracker      import SessionTracker
from .risk_manager         import RiskManager
from .performance_tracker  import PerformanceTracker
from .signal_aggregator    import SignalAggregator
from . import detector_regimen as _dreg
from . import senal_visual as _sv
from . import periodo_config as _pc
from .capital_manager import CapitalManager as _CapitalManager
try:
    from .overlay import OverlayRegion as _Overlay
    _OVERLAY_OK = True
except Exception:
    _OVERLAY_OK = False

try:
    from . import consejos_visual as _cv
    _CV_OK = True
except Exception:
    _CV_OK = False


# ═══════════════════════════════════════════════════════════════════════════
#  PORTERO DE BROKER — un solo sitio donde se decide si este motor calla
# ═══════════════════════════════════════════════════════════════════════════
#
# El motor de este archivo es de OPCIONES BINARIAS: apuesta a si la próxima
# vela de 60 segundos sube o baja. Eso tiene sentido en IQ Option y no lo
# tiene en ningún otro sitio.
#
# Cuando la visión de Litch apunta a Interactive Brokers, este motor no debe
# decidir ni ejecutar nada. Ni siquiera "en falso": una operación que se da
# por hecha se anota como acierto o fallo, y contamina el aprendizaje entero.
#
# Se comprueban dos cosas, y basta con una:
#   · broker_visual == "tws"   → el señor puso la visión en IBKR
#   · TWS está abierto y al frente → aunque la etiqueta diga otra cosa
#
# Lo segundo protege del caso en que la etiqueta esté desactualizada. La
# regla es la de siempre en esta casa: ante la duda, no se opera.


def _vision_permite(app, clave, valor) -> bool:
    """¿Se acepta este cambio de configuración, o pisaría la visión total?"""
    try:
        from . import vision_total as _vt
        return _vt.proteger(app, clave, valor)
    except Exception:
        return True


_T_ULT_AVISO_IQ = [0.0]


# ═══════════════════════════════════════════════════════════════════════════
#  CONFIANZA HONESTA — la corrección que más dinero puede ahorrar
# ═══════════════════════════════════════════════════════════════════════════
#
# El señor perdió dinero real por esto y tenía toda la razón en señalarlo.
# En su captura el cartel grande decía «SUBE — Confianza 100 %» mientras
# el propio modelo, en el panel de la izquierda, decía SUBE 47 % / BAJA
# 53 %. El cartel recomendaba lo contrario que los números.
#
# Dos fallos distintos, los dos graves:
#
#  1) EL 100 %. Salía de `prob_bayes` cuando la posterior se colapsa. Un
#     modelo que ha fallado 1 de cada 5 veces en 1914 operaciones NO
#     puede estar seguro al 100 % de nada. Mostrar 100 % no es optimismo:
#     es una cifra falsa que invita a subir el tamaño de la apuesta.
#
#  2) «CONFIANZA ALTA» CON 4 VOTOS DE 11. Eso es un 36 % de acuerdo entre
#     métodos — apenas por encima de tirar una moneda. Llamarlo «alta»
#     es mentirle al que decide.
#
# La regla nueva: la confianza que se enseña no puede superar ni lo que
# dicen los votos ni lo que la historia respalda.

_TECHO_CONFIANZA = 0.92   # nunca más de esto, por bien que pinte


def confianza_calibrada(app, votos: int, prob: float, total: int = 11) -> float:
    """
    Confianza honesta Y calibrada.

    Dos correcciones encadenadas, y las dos hacen falta:

      1. `confianza_honesta` impide decir más de lo que sostienen los
         votos. Es un techo lógico.
      2. `calibrar_confianza` ajusta a lo que Litch ACIERTA de verdad en
         ese tramo. Es la corrección empírica.

    La primera evita mentir por construcción; la segunda, mentir por
    ignorancia. Un modelo puede ser coherente y estar equivocado.
    """
    base = confianza_honesta(votos, prob, total)
    try:
        from . import calibrar_confianza as _cal
        corregida, _ = _cal.corregir(app, base)
        return round(float(corregida), 3)
    except Exception:
        return base


def confianza_honesta(votos: int, prob: float, total: int = 11) -> float:
    """
    Confianza que se puede enseñar sin mentir.

    Se toma la MENOR de dos cosas:
      · lo que dicen los votos (acuerdo entre métodos)
      · lo que dice la probabilidad del modelo
    y se limita a un techo. Si los métodos no se ponen de acuerdo, da
    igual lo segura que esté la red: el conjunto no lo está.
    """
    try:
        v = max(0, min(int(votos), int(total)))
        p = float(prob)
        if not (0.0 <= p <= 1.0):
            p = 0.5
    except Exception:
        return 0.5
    acuerdo = v / max(1, total)
    # Un acuerdo de 4/11 (0.36) no puede sostener una confianza de 0.9
    return round(min(p, 0.5 + acuerdo * 0.5, _TECHO_CONFIANZA), 3)


def nivel_honesto(votos: int, total: int = 11) -> str:
    """
    Cómo llamar a ese nivel de acuerdo, sin inflarlo.

    Antes: 4 de 11 se llamaba «Alta». Ahora hace falta mayoría real.
    """
    try:
        v = int(votos)
    except Exception:
        return "Baja"
    if v >= int(total * 0.70):      # 8 de 11 o más
        return "Alta"
    if v >= int(total * 0.55):      # 6 de 11
        return "Media"
    if v >= int(total * 0.36):      # 4 de 11
        return "Baja"
    return "Muy baja"


def _motor_iq_debe_callar(app) -> bool:
    """
    ¿Este motor binario tiene que quedarse quieto ahora mismo?

    ━━━ LO QUE ESTABA MAL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    La primera versión callaba en cuanto TWS estuviera abierto y al
    frente. Como el señor tiene TWS abierto siempre, el motor quedó
    silenciado de forma permanente: dejaron de salir los letreros de
    predicción, dejó de analizar el gráfico, dejó de operar en IQ Option.

    Arreglé una cosa rompiendo otra. El problema real nunca fue «hay un
    TWS abierto» — era que los BOTONES calibrados de IQ Option habían
    quedado debajo de la ventana de TWS, así que cada clic caía dentro
    del bróker de acciones y la operación se daba por hecha sin existir.

    ━━━ LA COMPROBACIÓN CORRECTA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Se calla si, y solo si, se cumple una de estas:

      1. El señor lo apagó a mano (interruptor `motor_binario`).
      2. Los botones de IQ Option están tapados por TWS — entonces el
         clic no llegaría a su destino y el resultado sería inventado.

    Si IQ Option está visible y sus botones son alcanzables, el motor
    trabaja con normalidad aunque haya diez TWS abiertos detrás. Tener
    dos brókers abiertos es lo normal en esta casa, no una anomalía.
    """
    # 1. El interruptor del señor manda por encima de todo
    try:
        cfg = app.mem.get("config", {})
        v = cfg.get("motor_binario")
        if v is False:
            return True
        if v is True:
            return False          # encendido a mano: no se discute
    except Exception:
        pass

    # 2. ¿Los botones de IQ Option son alcanzables?
    #
    # Esta es la pregunta que de verdad importa. Si el botón SUBE está
    # debajo de TWS, pulsarlo no compra nada — pero el motor lo daría por
    # comprado. Ahí sí hay que callar, porque cualquier resultado que
    # anote sería falso.
    try:
        cfg = app.mem.get("config", {})
        verde = cfg.get("boton_verde")
        rojo  = cfg.get("boton_rojo")
        if not (verde and rojo):
            return False          # sin calibrar, ya se para en otro sitio
        from . import manos as _manos
        tapado_v = _manos._dentro_de_tws(int(verde[0]), int(verde[1]))
        tapado_r = _manos._dentro_de_tws(int(rojo[0]),  int(rojo[1]))
        if tapado_v and tapado_r:
            return True           # los dos tapados: no hay forma de operar
    except Exception:
        pass

    return False


def _avisar_motor_callado(app) -> None:
    """Lo dice una vez cada cinco minutos, no en cada señal."""
    try:
        if (time.time() - _T_ULT_AVISO_IQ[0]) < 300:
            return
        _T_ULT_AVISO_IQ[0] = time.time()
        apagado = app.mem.get("config", {}).get("motor_binario") is False
        if apagado:
            app.log("[MotorIQ] Apagado por usted. Dígame «enciende el motor "
                    "de IQ» cuando quiera que vuelva a analizar binarias.")
        else:
            app.log("[MotorIQ] Callado: los botones SUBE y BAJA de IQ Option "
                    "están tapados por la ventana de Interactive Brokers. "
                    "Pulsarlos no compraría nada y yo lo daría por comprado. "
                    "Traiga IQ Option al frente, o recalíbrelo.")
    except Exception:
        pass

try:
    from .grafo_conocimiento import GrafoConocimiento as _GrafoConocimiento
    _grafo = _GrafoConocimiento()
    _GRAFO_OK = True
except Exception as _e_grafo:
    _GRAFO_OK = False
    _grafo = None

# ── Voto 8: Patrones de Velas Japonesas ──────────────────────────────────────
try:
    from . import patrones_velas as _pv
    _PV_OK = True
except Exception:
    _PV_OK = False

# ── Voto 9: Soporte y Resistencia automático ─────────────────────────────────
try:
    from . import soporte_resistencia as _sr
    _SR_OK = True
except Exception:
    _SR_OK = False

# ── Voto 10: Motor de Scalping Institucional (EMA200 + RSI7 + Spread) ─────────
try:
    from . import scalping_engine as _sce
    _SCE_OK = True
except Exception:
    _SCE_OK = False

# ── Voto 11: Triple Barrera — López de Prado (AFML Cap. 3) ───────────────────
try:
    from . import triple_barrier as _tb
    _TB_OK = True
except Exception:
    _TB_OK = False

_LOG_CSV          = os.path.join(mem_mod.ruta_memoria_ap(), "training_log.csv")
_PG_OK            = manos.disponible()
_SECS_PRECALCULO  = 5     # segundos antes del cierre para pre-calcular
_COOLDOWN_CLICK   = 12    # segundos mínimos entre trades
_MAX_RACHA_LOSS   = 4     # pérdidas consecutivas → pausa automática
_PAUSA_MINUTOS    = 10    # minutos de pausa tras racha de pérdidas


# ── Utilidades ────────────────────────────────────────────────────────────────

def _kelly(p_win: float, payout: float = 0.85,
           dd_pct: float = 0.0, regimen: str = "neutral",
           racha_loss: int = 0, periodo_seg: int = 60) -> float:
    """
    Criterio de Kelly adaptativo para opciones binarias.

    f* = p − (1−p)/payout  (Kelly fraccionario).

    Ajustes adaptativos:
      • dd_pct      : reduce Kelly al aumentar el drawdown
      • regimen     : mercado caótico → mitad del Kelly; trending → Kelly completo
      • racha_loss  : cada pérdida consecutiva reduce Kelly un 15%
      • periodo_seg : timeframes cortos tienen Kelly máximo reducido
                      (5s→6%, 30s→9%, 1m→12%, 5m→16%, 30m→22%)
    """
    f = p_win - (1.0 - p_win) / max(payout, 0.1)
    f = max(0.0, f)

    # Factor por drawdown: 0% dd = 1.0, 5% dd = 0.75, 8% dd = 0.50
    if dd_pct > 0:
        dd_factor = max(0.35, 1.0 - dd_pct * 6.0)
        f *= dd_factor

    # Factor por régimen de mercado
    _reg_factores = {
        "trending_up":   1.00,
        "trending_down": 1.00,
        "ranging":       0.85,
        "breakout":      0.90,
        "chaotic":       0.50,
        "neutral":       0.90,
    }
    f *= _reg_factores.get(regimen.lower(), 0.90)

    # Penalización por racha de pérdidas (Anti-martingale inverso)
    if racha_loss >= 2:
        f *= max(0.30, 1.0 - (racha_loss - 1) * 0.15)

    # Cap según período: timeframes cortos = menos apuesta máxima
    try:
        from . import periodo_config as _pc_k
        kelly_cap = _pc_k.kelly_maximo(periodo_seg)
    except Exception:
        kelly_cap = 0.25
    return round(max(0.0, min(f, kelly_cap)), 3)

def _safe_pct(x) -> int:
    """Convierte prob/confianza a int 0-100 seguro; devuelve 0 si NaN/None/error."""
    try:
        v = float(x) if x is not None else 0.0
        return 0 if (v != v) else int(max(0.0, min(1.0, v)) * 100)
    except Exception:
        return 0


def _log_trade_csv(ts, patron, direccion, votos, prob, kelly_f, resultado=None):
    try:
        nuevo = not os.path.exists(_LOG_CSV)
        with open(_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["timestamp", "patron", "dir", "votos_6",
                             "prob", "kelly_pct", "resultado"])
            w.writerow([ts, patron, direccion, votos,
                        round(prob, 3), f"{kelly_f*100:.1f}%", resultado or ""])
    except Exception:
        pass


# ── Agente principal ─────────────────────────────────────────────────────────

class AgenteTrading(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True, name="LitchMainLoop")
        self.app = app
        self._detener        = False
        self._senal_prep     = None
        self._en_precalculo  = False
        self._ultima_vela_t  = 0.0
        self._ultimo_click_t = 0.0
        self._pausado_hasta       = 0.0    # timestamp fin de pausa por racha de pérdidas
        self._pausa_anunciada_fin = True   # True = ya anunciado (no hay pausa activa)

        # ── Agente RL (Dueling DQN) ──────────────────────────────────────────
        ruta_rl = os.path.join(mem_mod.ruta_memoria_ap(), "rl_agente.json")
        self.rl = AgenteRL(ruta=ruta_rl)
        self._rl_seq_ant = None
        self._rl_accion  = AgenteRL.ACCION_SKIP
        self._rl_ind_ant = {}
        self._ultimo_ind = {}
        self._ultimo_smc = {}

        # ── Calibrador de pesos de métodos (precis. reciente → voto ponderado) ─
        from .calibrador_metodos import CalibradorMetodos
        ruta_cal = os.path.join(mem_mod.ruta_memoria_ap(), "calibrador_metodos.json")
        self.calibrador = CalibradorMetodos(ruta=ruta_cal)

        # ── Base de datos de fallos ───────────────────────────────────────────
        ruta_fdb = os.path.join(mem_mod.ruta_memoria_ap(), "fallo_db.json")
        self.fdb = FalloDB(ruta_fdb)

        # ── Monitor de trade activo (Rollover) ────────────────────────────────
        self.monitor = MonitorTrade(app)
        self.monitor.start()

        # ── Sistema de Conciencia e Inteligencia Autónoma ─────────────────────
        # Reutiliza la instancia singleton ya creada en litch.py (si existe)
        # para evitar doble inicialización y mensajes duplicados.
        existing = getattr(app, "conciencia", None)
        self.conciencia = existing if existing is not None else _con.obtener(app)
        app.conciencia  = self.conciencia

        # ── Modo Práctica DEMO ────────────────────────────────────────────────
        self.practica   = _practica_mod.obtener(app)
        app.modo_practica = self.practica

        # ── Modo Profesional ──────────────────────────────────────────────────
        self.profesional      = _pro_mod.obtener(app)
        app.modo_profesional  = self.profesional

        # ── Contexto del trade en curso ───────────────────────────────────────
        self._trade_patron = ""      # patrón del trade en curso
        self._trade_dir    = ""      # dirección apostada
        self._trade_votos  = 0
        self._trade_prob   = 0.5
        self._trade_kelly  = 0.0
        self._trade_ts     = ""
        self._trade_monto  = 10.0   # monto del último trade (para Meta Diaria)
        self._pending_log  = None    # (ts, dir, votos, prob, kelly_f)
        self._razonamiento_actual   = {}  # contexto del trade para post-mortem
        self._trades_desde_autoeval = 0   # dispara auto-evaluación cada 10 trades
        self._ultimo_smc            = {}  # resultado del analizador SMC/LWS
        self._hist_rolling          = []  # últimos 30 resultados para motor adaptativo
        self._trade_ejecutado       = False  # True solo si el click físico se completó
        self._ultimo_regimen        = "neutral"  # régimen de mercado del último ciclo

        # ── Scanner veloz / auto-adaptativo ──────────────────────────────────
        self._color_vela_ant    = None   # último color leído por el scanner
        self._t_ultimo_cambio   = 0.0    # timestamp del último cambio de color
        self._hist_t_cambios    = []     # timestamps de cambios (estima período)
        self._recal_running     = False  # evita recalibraciones spam
        self._nueva_vela_flag   = False  # scanner detectó cambio de vela → trigger
        self._color_null_streak  = 0      # contador de ciclos sin leer color
        self._recal_fail_ts      = []    # timestamps de recalibración fallida (ventana 10 min)
        self._errores_consec     = 0     # contador de errores consecutivos en _ciclo()
        self._t_sin_grafico      = 0.0   # timestamp desde cuándo no se ve gráfico
        self._t_aviso_sin_graf   = 0.0   # última vez que se habló del gráfico faltante

        # ── Thread pool compartido — reutiliza hilos para RL/SMC/Red/Conciencia ─
        # En lugar de crear+destruir un thread por cada vela (cada 10s = cientos
        # de threads por hora), mantenemos un pool caliente. Reduce overhead de
        # creación de hilos y previene acumulación de threads en el OS.
        self._executor = _cf.ThreadPoolExecutor(max_workers=6,
                                                thread_name_prefix="LitchW")

        # ── Deduplicación de anuncios de señal ───────────────────────────────
        # Evita que LITCH diga "bajada probable 6/7" cada 10 segundos cuando
        # la señal no cambió. Solo habla si: dirección cambia, votos varían ≥2,
        # o pasaron ≥90 segundos desde el último anuncio.
        self._ultima_senal_dir   = None
        self._ultima_senal_votos = 0
        self._ultima_senal_t     = 0.0

        # ── Throttle del log de pausa ─────────────────────────────────────────
        # Sin esto, _en_pausa() imprime en el log cada 100ms → miles de líneas
        self._t_ultimo_log_pausa = 0.0

        # ── SessionTracker — rendimiento por franja horaria (30 min) ──────────
        _ruta_session = os.path.join(
            mem_mod.ruta_memoria_ap(), "session_tracker.json")
        self._session_tracker = SessionTracker(ruta=_ruta_session)

        # ── RiskManager — coordinador central de riesgo ───────────────────────
        # modo_pro se resuelve dinámicamente desde app en cada evaluar()
        self._risk_mgr = RiskManager(
            fdb=self.fdb,
            session_tracker=self._session_tracker,
            modo_pro=None,
        )

        # ── PerformanceTracker — analítica integral de rendimiento ────────────
        _ruta_perf = os.path.join(mem_mod.ruta_memoria_ap(), "perf_tracker.json")
        self._perf = PerformanceTracker(ruta=_ruta_perf)
        self._capital = _CapitalManager(app=self.app)

        # ── SignalAggregator — segunda capa de validación con pesos dinámicos ─
        self._sig_agg = SignalAggregator(calibrador=self.calibrador)

        # ── Canal 2: segundo gráfico/activo independiente (entrenamiento doble) ──
        # Reutiliza los mismos motores (red, RL, FalloDB) para que ambos
        # gráficos aceleren el aprendizaje de los mismos modelos, pero con
        # su propia secuencia, contexto de trade y cooldown — sin pisar el
        # estado del canal 1.
        self._c2 = {
            "color_vela_ant":  None,
            "t_ultimo_cambio": 0.0,
            "ultimo_click_t":  0.0,
            "trade_ejecutado": False,
            "rl_seq_ant":      None,
            "rl_accion":       AgenteRL.ACCION_SKIP,
            "rl_ind_ant":      {},
            "ultimo_ind":      {},
            "ultimo_smc":      {},
            "hist_rolling":    [],
            "trade_patron":    "",
            "trade_dir":       "",
            "trade_votos":     0,
            "trade_prob":      0.5,
            "trade_kelly":     0.0,
            "trade_monto":     10.0,
        }

    def parar(self):
        self._detener = True

    # ── Bucle principal ───────────────────────────────────────────────────────
    def run(self):
        self._auto_calibrar_inicio()
        threading.Thread(target=self._scanner_veloz_loop,
                         daemon=True, name="LitchScanVeloz").start()
        threading.Thread(target=self._loop_calibracion_periodica,
                         daemon=True, name="LitchCalibRetry").start()
        threading.Thread(target=self._loop_reporte_sesion,
                         daemon=True, name="LitchReporteSesion").start()
        threading.Thread(target=self._loop_contexto_pantalla,
                         daemon=True, name="LitchCtxPantalla").start()
        threading.Thread(target=self._loop_canal2,
                         daemon=True, name="LitchCanal2").start()
        # Canales 3 y 4 — activos solo si hay botones calibrados para ellos
        threading.Thread(target=lambda: self._loop_canal_extra(3),
                         daemon=True, name="LitchCanal3").start()
        threading.Thread(target=lambda: self._loop_canal_extra(4),
                         daemon=True, name="LitchCanal4").start()
        _t_ultimo_hb      = time.time()
        _t_ultimo_ovr_chk = time.time()   # verificación de override obsoleto c/30 min
        while not self._detener:
            # Heartbeat al watchdog cada 30 s
            if time.time() - _t_ultimo_hb >= 30:
                try:
                    self.app.watchdog.heartbeat()
                except Exception:
                    pass
                _t_ultimo_hb = time.time()

            # Verificar override de conciencia obsoleto cada 30 min
            if time.time() - _t_ultimo_ovr_chk >= 1800:
                try:
                    if hasattr(self.app, "conciencia") and self.app.conciencia:
                        self.app.conciencia.verificar_override_obsoleto()
                except Exception:
                    pass
                _t_ultimo_ovr_chk = time.time()

            if not self._listo():
                self._senal_prep     = None
                self._en_precalculo  = False
                self._errores_consec = 0   # no estaba listo, no son errores reales
                self._notificar_sin_grafico()
                time.sleep(1)
                continue
            # El sistema está listo — resetear estado "sin gráfico"
            if self._t_sin_grafico != 0.0:
                self._t_sin_grafico    = 0.0
                self._t_aviso_sin_graf = 0.0
            periodo = int(self.app.mem["config"].get("periodo_vela", 60))
            try:
                self._ciclo(periodo)
                _errores_consec = 0   # resetear contador en ciclo exitoso
            except Exception as e:
                # OJO: `_tb` a nivel de módulo es `triple_barrier` (línea
                # ~100). Aquí se importaba traceback con ESE MISMO alias, y
                # solo funcionaba porque el import local lo tapaba dentro de
                # esta función. Si algún día se mueve este bloque a otro
                # método, `_tb.format_exc()` llamaría a triple_barrier y
                # reventaría DENTRO del manejador de errores — el peor sitio
                # posible para un fallo. Se usa un nombre distinto.
                import traceback as _trc
                _errores_consec = getattr(self, "_errores_consec", 0) + 1
                self._errores_consec = _errores_consec
                a = self.app
                a.log(f"[Trading] ⚠ Error en ciclo #{_errores_consec}: "
                      f"{type(e).__name__}: {e}\n{_trc.format_exc()[-600:]}")

                # Auto-sanación por niveles según errores consecutivos
                # L1: 5 errores (antes 3) — reset suave
                # L2: 12 errores (antes 5) — recalibrar, con cooldown de 60s
                # L3: 20 errores (antes 10) — detener trading
                if _errores_consec == 5:
                    # Nivel 1: reset suave de estado del scanner
                    self._color_vela_ant    = None
                    self._color_null_streak = 0
                    self._senal_prep        = None
                    self._en_precalculo     = False
                    a.log("[AutoSanacion] L1: estado del scanner reseteado.")
                    time.sleep(2)

                elif _errores_consec == 12:
                    # Nivel 2: pausa 15s + recalibración (solo si no recalibró hace < 60s)
                    _ahora_l2 = time.time()
                    _t_ult_recal = getattr(self, "_t_ultimo_l2", 0.0)
                    if _ahora_l2 - _t_ult_recal < 60:
                        a.log("[AutoSanacion] L2: cooldown activo — omitiendo recalibración.")
                        time.sleep(5)
                    else:
                        self._t_ultimo_l2 = _ahora_l2
                        a.log("[AutoSanacion] L2: pausa 15s + re-calibración automática.")
                        try:
                            a.decir(a.txt(
                                "Detecté varios errores seguidos. Me recalibro automáticamente.",
                                "Detected repeated errors. Auto-recalibrating."))
                            from . import vision
                            res = vision.auto_calibrar_iq()
                            if res:
                                for k, v in res.items():
                                    if _vision_permite(a, k, v):
                                        a.mem["config"][k] = v
                                from . import memoria as _mm
                                _mm.guardar(a.mem)
                                a.log("[AutoSanacion] L2: recalibración exitosa.")
                            else:
                                a.log("[AutoSanacion] L2: IQ Option no visible.")
                        except Exception as _e2:
                            a.log(f"[AutoSanacion] L2: {_e2}")
                        time.sleep(15)

                elif _errores_consec == 20:
                    # Nivel 3: detener trading + alerta urgente + registro en crash log
                    a.trading_on = False
                    a.log("[AutoSanacion] L3: 20 errores consecutivos — trading DETENIDO.")
                    try:
                        wdg = getattr(a, "watchdog", None)
                        if wdg and hasattr(wdg, "_registrar_crash"):
                            wdg._registrar_crash(
                                "AutoSanacion_L3",
                                RuntimeError("10 errores consecutivos en _ciclo()"),
                                tb=_trc.format_exc())
                    except Exception:
                        pass
                    try:
                        a.decir(a.txt(
                            "Señor, he detenido el trading por múltiples errores consecutivos. "
                            "Revise el registro de fallos y dígame 'iniciar trading' cuando esté listo.",
                            "Sir, I have stopped trading due to multiple consecutive errors. "
                            "Please review the error log and say 'start trading' when ready."))
                    except Exception:
                        pass
                    time.sleep(30)

                elif _errores_consec > 10:
                    # Nivel 4: espera progresiva para no saturar el CPU
                    time.sleep(min(30, _errores_consec * 2))
                else:
                    time.sleep(2)
            time.sleep(0.10)

    # ── Auto-calibración al arrancar ─────────────────────────────────────────
    def _auto_calibrar_inicio(self):
        """Calibra automáticamente si IQ Option no está configurado aún."""
        a   = self.app
        cfg = a.mem.get("config", {})
        ya_calibrado = (cfg.get("region_grafico") and
                        cfg.get("boton_verde") and
                        cfg.get("boton_rojo"))
        if ya_calibrado:
            a.log("[Auto] Calibracion previa detectada — listo para operar.")
            return
        a.log("[Auto] Sin calibracion — buscando IQ Option en pantalla...")
        def _cal():
            time.sleep(1.0)   # espera que IQ Option sea visible
            try:
                res = vision.auto_calibrar_iq()
                if res:
                    for k, v in res.items():
                        if _vision_permite(a, k, v):
                            a.mem["config"][k] = v
                    mem_mod.guardar(a.mem)
                    detectados = ', '.join(res.keys())
                    a.log(f"[Auto] IQ Option calibrado: {detectados}")
                    a.decir(a.txt(
                        "Calibracion lista. Comenzare a operar en la proxima senal.",
                        "Calibration complete. Starting to trade on the next signal."))
                    # Activar análisis inmediato tras calibración exitosa
                    self._nueva_vela_flag = True
                else:
                    a.log("[Auto] IQ Option no visible en pantalla. Esperando apertura del broker.")
                    a.decir(a.txt(
                        "No veo ningun grafico en pantalla. "
                        "Abre el broker con el que deseas operar, "
                        "como IQ Option u otro broker compatible, "
                        "asegurate de que el grafico sea visible "
                        "y luego dime: Litch, calibra.",
                        "I cannot see any chart on screen. "
                        "Please open the broker you want to trade with, "
                        "such as IQ Option or another compatible broker, "
                        "make sure the chart is visible, "
                        "then say: Litch, calibrate."))
            except Exception as e:
                a.log(f"[Auto] Error calibracion: {e}")
        threading.Thread(target=_cal, daemon=True, name="AutoCalInicio").start()

    # ── Scanner veloz: detecta cambios de vela y período automáticamente ──────
    def _set_overlay_estado(self, estado: str):
        """Actualiza overlay y LED de visión en la UI de manera thread-safe."""
        try:
            ovl = getattr(self.app, "overlay", None)
            if ovl is not None:
                ovl.set_estado(estado)
                region = self.app.mem["config"].get("region_grafico")
                if region:
                    ovl.set_region(region)
        except Exception:
            pass
        # Actualizar LED en interfaz
        try:
            ui = getattr(self.app, "interfaz", None)
            if ui is not None:
                ui.root.after(0, lambda e=estado: ui._actualizar_vision_led(e))
        except Exception:
            pass

    def _scanner_veloz_loop(self):
        """Escaneo adaptativo: Blitz → 100ms; 10-30s → 250ms; 60s → hasta 2s."""
        _sv_tick = 0
        while not self._detener:
            try:
                a = self.app
                if a.activo and a.trading_on:
                    self._tick_scanner()
                elif not a.activo:
                    self._set_overlay_estado("inactivo")
                else:
                    self._set_overlay_estado("inactivo")
                # Actualizar contador de tiempo restante en señal visual cada ~1s
                _sv_tick += 1
                if _sv_tick >= 4:
                    _sv_tick = 0
                    try:
                        sv = _sv.obtener()
                        if sv is not None and sv._visible:
                            _periodo_loop = int(a.mem["config"].get("periodo_vela", 60))
                            _rest_loop = max(0, _periodo_loop - int(
                                time.time() - getattr(self, "_t_ultimo_cambio", time.time())))
                            sv.actualizar_tiempo(_rest_loop)
                    except Exception:
                        pass
            except Exception:
                pass
            periodo = int(self.app.mem["config"].get("periodo_vela", 60))
            if periodo <= 15:
                time.sleep(0.10)
            else:
                time.sleep(max(0.25, min(2.0, periodo / 30.0)))

    def _tick_scanner(self):
        a      = self.app
        region = a.mem["config"].get("region_grafico")

        # Sin región: buscar automáticamente (máximo una vez cada 60 s)
        if not region:
            self._set_overlay_estado("buscando")
            ahora = time.time()
            if not self._recal_running and ahora - self._t_ultimo_cambio > 60:
                self._recal_running    = True
                self._t_ultimo_cambio  = ahora
                def _r():
                    try:
                        res = vision.auto_calibrar_iq()
                        if res:
                            for k, v in res.items():
                                if _vision_permite(a, k, v):
                                    a.mem["config"][k] = v
                            mem_mod.guardar(a.mem)
                            a.log(f"[Auto] Region detectada: {res.get('region_grafico')}")
                    finally:
                        self._recal_running = False
                threading.Thread(target=_r, daemon=True, name="RecalScan").start()
            return

        color = vision.color_vela(region)
        if color is None:
            # Acumular fallos del scanner también
            self._color_null_streak = getattr(self, "_color_null_streak", 0) + 1
            # Después de 3 fallos seguidos ya mostramos "sin_grafico"
            if self._color_null_streak >= 3:
                self._set_overlay_estado("sin_grafico")
            # Si la visión está apuntando a Interactive Brokers, NO se
            # recalibra IQ Option. Antes sí lo hacía, y decía «recalibrando
            # IQ Option» con TWS en pantalla: incoherente y peligroso,
            # porque la autocalibración busca los botones verdes de IQ y
            # los encuentra donde no debe. En TWS el gráfico se lee con
            # vision_tws, no con el detector de velas binarias.
            _bv = a.mem["config"].get("broker_visual")
            if _bv == "tws":
                if (time.time() - getattr(self, "_t_aviso_sin_graf", 0.0)) > 180:
                    self._t_aviso_sin_graf = time.time()
                    a.log("[Trading] Visión en Interactive Brokers: no "
                          "recalibro IQ Option ni leo velas binarias aquí.")
                self._color_null_streak = 0
                return

            if self._color_null_streak >= 8 and not self._recal_running:
                # 8 × 2s = 16 s sin ver nada → recalibrar
                self._recal_running = True
                self._color_null_streak = 0
                def _r():
                    _ok = False
                    try:
                        res = vision.auto_calibrar_iq()
                        if res:
                            for k, v in res.items():
                                if _vision_permite(a, k, v):
                                    a.mem["config"][k] = v
                            mem_mod.guardar(a.mem)
                            n_g = 2 if res.get("boton_verde_2") else 1
                            a.log(f"[Auto] Re-calibrado desde scanner: {n_g} grafica(s) — {list(res.keys())}")
                            self._nueva_vela_flag = True
                            _ok = True
                    finally:
                        self._recal_running = False
                    if not _ok:
                        self._registrar_fallo_recal("scanner_null")
                        # Avisar por voz que no ve el gráfico
                        def _avisar_no_graf():
                            try:
                                if (time.time() - self._t_aviso_sin_graf) > 120:
                                    self._t_aviso_sin_graf = time.time()
                                    a.decir(a.txt(
                                        "No veo el grafico. "
                                        "Asegurate de que el broker este abierto y visible. "
                                        "Dime Litch calibra cuando el grafico este en pantalla.",
                                        "I cannot see the chart. "
                                        "Make sure the broker is open and the chart is visible. "
                                        "Say Litch calibrate when the chart is on screen."))
                            except Exception:
                                pass
                        threading.Thread(target=_avisar_no_graf, daemon=True,
                                         name="AvisoGraf").start()
                threading.Thread(target=_r, daemon=True, name="RecalScanNul").start()
                a.log("[Auto] Sin color en grafico — recalibrando IQ Option...")
            return

        ahora = time.time()
        ant   = self._color_vela_ant

        if ant is not None and ant != color:
            # Nueva vela detectada — registrar timestamp y activar procesamiento
            dt = ahora - self._t_ultimo_cambio
            if dt > 3:   # anti-parpadeo: mínimo 3 s entre cambios válidos
                self._hist_t_cambios.append(ahora)
                if len(self._hist_t_cambios) > 20:
                    self._hist_t_cambios = self._hist_t_cambios[-20:]
                self._t_ultimo_cambio = ahora

                # ★ TRIGGER: avisa al ciclo principal que hay nueva vela
                self._nueva_vela_flag = True

                dir_txt = "verde" if color == "V" else "roja"
                a.log(f"[Scanner] Nueva vela {dir_txt} detectada → procesando...")

                # Al inicio de nueva vela → ocultar señal visual del período anterior
                try:
                    sv = _sv.obtener()
                    if sv is not None:
                        sv.ocultar()
                except Exception:
                    pass

                # Estimar período con ≥3 transiciones
                if len(self._hist_t_cambios) >= 3:
                    diffs  = [self._hist_t_cambios[i+1] - self._hist_t_cambios[i]
                               for i in range(len(self._hist_t_cambios)-1)]
                    p_est  = int(np.median(diffs))
                    if 8 <= p_est <= 3600:
                        actual = int(a.mem["config"].get("periodo_vela", 60))
                        if abs(p_est - actual) > max(5, actual * 0.15):
                            a.mem["config"]["periodo_vela"] = p_est
                            a.log(f"[Auto] Periodo estimado: {p_est}s")

        # Color detectado con éxito → Litch está viendo el gráfico
        self._color_null_streak = 0
        self._set_overlay_estado("viendo")
        self._color_vela_ant = color

    def _listo(self):
        a   = self.app
        if not (a.activo and a.trading_on):
            return False
        practica    = getattr(a, "modo_practica",    None)
        profesional = getattr(a, "modo_profesional", None)
        if (practica and practica.activo) or (profesional and profesional.activo):
            return True
        return bool(a.mem["config"].get("region_grafico"))

    def _notificar_sin_grafico(self) -> None:
        """
        Detecta si el sistema no puede ver ningún gráfico y avisa por voz con
        instrucciones claras para abrir el broker. Habla una vez al inicio
        y luego cada 5 minutos si sigue sin gráfico.
        """
        a   = self.app
        cfg = a.mem.get("config", {})
        ahora = time.time()

        # ¿Hay región configurada pero no se ve color? → scanner lo maneja
        # ¿No hay región en absoluto? → eso es lo que nos interesa aquí
        sin_region  = not cfg.get("region_grafico")
        sin_botones = not (cfg.get("boton_verde") and cfg.get("boton_rojo"))

        if not (sin_region or sin_botones):
            # Ya hay configuración, el scanner se encargará
            self._t_sin_grafico = 0.0
            return

        # Empezar a contar el tiempo sin gráfico
        if self._t_sin_grafico == 0.0:
            self._t_sin_grafico = ahora

        tiempo_sin = ahora - self._t_sin_grafico
        intervalo_aviso = 300  # hablar cada 5 minutos máximo

        # Hablar solo si llevamos ≥10 s sin gráfico y el intervalo de aviso pasó
        if tiempo_sin < 10 or (ahora - self._t_aviso_sin_graf) < intervalo_aviso:
            return

        self._t_aviso_sin_graf = ahora

        # Construir mensaje inteligente según el estado exacto
        if sin_region and sin_botones:
            motivo = a.txt(
                "No veo ningun grafico ni botones de operacion configurados.",
                "I cannot see any chart or configured trading buttons.")
        elif sin_region:
            motivo = a.txt(
                "Tengo los botones configurados pero no veo el grafico.",
                "I have the buttons configured but cannot see the chart.")
        else:
            motivo = a.txt(
                "Veo el grafico pero no tengo los botones de compra y venta configurados.",
                "I can see the chart but do not have the buy and sell buttons configured.")

        instruccion = a.txt(
            "Para poder analizar el mercado y realizar operaciones, "
            "por favor abre el broker con el que deseas operar, "
            "asegurate de que el grafico sea visible en pantalla "
            "y luego dime: Litch, calibra.",
            "To analyze the market and place trades, "
            "please open the broker you want to trade with, "
            "make sure the chart is visible on screen, "
            "then tell me: Litch, calibrate.")

        mins = int(tiempo_sin // 60)
        if mins >= 1:
            espera = a.txt(
                f"Llevo {mins} minuto{'s' if mins != 1 else ''} sin ver ningun grafico. ",
                f"I have been without a chart for {mins} minute{'s' if mins != 1 else ''}. ")
        else:
            espera = ""

        a.log(f"[Trading] Sin grafico visible ({int(tiempo_sin)}s). {motivo}")
        a.decir(f"{espera}{motivo} {instruccion}")

    # ── Ciclo 250ms ───────────────────────────────────────────────────────────
    def _ciclo(self, periodo: int):
        ahora = time.time()

        # ── PRIORIDAD MÁXIMA: scanner detectó nueva vela en tiempo real ──────
        # Funciona con CUALQUIER período (30s, 60s, 5m, Blitz, Binaria, OTC)
        if self._nueva_vela_flag and ahora - self._ultima_vela_t > 3:
            self._nueva_vela_flag = False
            self._ultima_vela_t   = ahora
            self._en_precalculo   = False
            self.monitor.cerrar_trade()
            self._procesar_vela()
            if self._senal_prep:
                dir_p, votos_p, _prob_p, dec_p, patron_p = self._senal_prep
                self._senal_prep = None
                self._ejecutar_si_consenso(dir_p, votos_p, dec_p, patron=patron_p)
            return

        # ── Fallback: alineación por período conocido ─────────────────────────
        t_en_periodo = ahora % periodo
        t_para_fin   = periodo - t_en_periodo

        # Fase 1: Cierre de vela (primeros 2 s del período)
        if t_en_periodo < 2.0:
            if ahora - self._ultima_vela_t > periodo * 0.6:
                self._ultima_vela_t = ahora
                self._en_precalculo = False
                self.monitor.cerrar_trade()
                self._procesar_vela()
                if self._senal_prep:
                    dir_p, votos_p, _prob_p, dec_p, patron_p = self._senal_prep
                    self._senal_prep = None
                    self._ejecutar_si_consenso(dir_p, votos_p, dec_p, patron=patron_p)
                return

        # Fase 2: Pre-cálculo antes del cierre (adaptivo según período)
        secs_pre = max(4.0, periodo * 0.20) if periodo <= 60 else _SECS_PRECALCULO
        if (1.0 < t_para_fin <= secs_pre + 0.5
                and not self._en_precalculo
                and len(self.app.mem["secuencia"]) >= 3):
            self._en_precalculo = True
            threading.Thread(target=self._precalcular_senal,
                             daemon=True, name="LitchPreCalc").start()

    # ── Lectura y registro de la vela cerrada ─────────────────────────────────
    def _procesar_vela(self):
        a      = self.app
        region = a.mem["config"].get("region_grafico")
        color  = vision.color_vela(region)

        if color is None:
            self._color_null_streak += 1

            # Sin región: calibrar de inmediato
            if not region:
                if not self._recal_running:
                    self._recal_running = True
                    def _recal_sin_region():
                        try:
                            res = vision.auto_calibrar_iq()
                            if res:
                                for k, v in res.items():
                                    if _vision_permite(a, k, v):
                                        a.mem["config"][k] = v
                                mem_mod.guardar(a.mem)
                                n_graficas = 2 if res.get("boton_verde_2") else 1
                                a.log(f"[Auto] Calibrado: {n_graficas} grafica(s) — {', '.join(res.keys())}")
                                self._nueva_vela_flag  = True
                                self._color_null_streak = 0
                        except Exception as _e:
                            a.log(f"[Auto] Error: {_e}")
                        finally:
                            self._recal_running = False
                    threading.Thread(target=_recal_sin_region,
                                     daemon=True, name="RecalSinRegion").start()
                    a.log("[Auto] Sin grafico calibrado — detectando IQ Option...")
                return

            # Con región pero sin poder leer la vela → posible calibración obsoleta
            if self._color_null_streak == 1:
                a.log(f"[Vision] Grafico no legible (region={region}). "
                      f"Si persiste, IQ Option puede estar tapado o en modo diferente.")
            elif self._color_null_streak >= 5 and not self._recal_running:
                # 5 fallos seguidos → recalibrar aunque haya región guardada
                self._recal_running = True
                def _recal_obsoleta():
                    _ok = False
                    try:
                        a.log("[Auto] Recalibrando — calibracion puede estar obsoleta...")
                        res = vision.auto_calibrar_iq()
                        if res:
                            for k, v in res.items():
                                if _vision_permite(a, k, v):
                                    a.mem["config"][k] = v
                            mem_mod.guardar(a.mem)
                            n_graficas = 2 if res.get("boton_verde_2") else 1
                            a.log(f"[Auto] Re-calibrado: {n_graficas} grafica(s) — {', '.join(res.keys())}")
                            self._nueva_vela_flag   = True
                            self._color_null_streak = 0
                            _ok = True
                        else:
                            a.log("[Auto] IQ Option no visible — asegurate de que este abierto.")
                    except Exception as _e:
                        a.log(f"[Auto] Error recalibracion: {_e}")
                    finally:
                        self._recal_running = False
                    if not _ok:
                        self._registrar_fallo_recal("recal_obsoleta")
                threading.Thread(target=_recal_obsoleta,
                                 daemon=True, name="RecalObsoleta").start()
            return

        # ── Lectura exitosa — resetear contador de fallos ─────────────────────
        self._color_null_streak = 0

        a.log(f"Vela cerrada: {'verde' if color == 'V' else 'roja'}")

        acierto = a.analizador.verificar_pendiente(color)
        if acierto is not None:
            # Red neuronal y RL aprenden siempre (datos de mercado reales)
            try:
                a.red.registrar_resultado(acierto, a.mem["secuencia"])
            except Exception:
                pass

            res_str = "WIN" if acierto else "LOSS"

            # UILearner: registrar resultado del trade
            try:
                _ul = getattr(a, "ui_learner", None)
                if _ul is not None:
                    _ul.registrar_resultado(
                        "compra" if getattr(self, "_ultima_senal_dir", "V") == "V" else "venta",
                        "win" if acierto else "loss")
            except Exception:
                pass

            # ── Stats de modos: SOLO si hubo click real ───────────────────────
            _fue_trade_real = self._trade_ejecutado
            self._trade_ejecutado = False  # reset para el próximo trade

            if _fue_trade_real:
                # ── Modo Práctica ─────────────────────────────────────────────
                try:
                    practica = getattr(a, "modo_practica", None)
                    if practica and practica.activo:
                        practica.registrar_resultado(acierto)
                        a.log(f"[Practica] {res_str} | {practica.resumen()}")
                except Exception:
                    pass

                # ── Modo Profesional ──────────────────────────────────────────
                try:
                    profesional = getattr(a, "modo_profesional", None)
                    if profesional and profesional.activo:
                        profesional.registrar_resultado(
                            acierto, kelly=self._trade_kelly)
                        a.log(f"[PRO] {res_str} | {profesional.resumen()}")
                except Exception:
                    pass

                # ── Meta Diaria (P&L real en $) — nunca en modo Práctica DEMO ───
                # Las pérdidas de práctica son esperadas y no deben disparar el
                # stop loss real de la sesión (la Meta es solo para cuenta real).
                try:
                    meta = getattr(a, "meta_diaria", None)
                    _pract = getattr(a, "modo_practica", None)
                    _en_pract_now = bool(_pract and _pract.activo)
                    if meta and meta.activa and not _en_pract_now:
                        payout = (getattr(a, "broker", None).perfil.get("payout", 0.85)
                                  if hasattr(a, "broker") else 0.85)
                        meta.registrar_resultado(
                            acierto,
                            monto  = self._trade_monto,
                            payout = payout)
                except Exception as _me:
                    a.log(f"[Meta] Error: {_me}")
            else:
                dir_s = self._trade_dir or "?"
                dir_lbl = "SUBE" if dir_s == "V" else "BAJA"
                a.log(f"[Señal] {'OK' if res_str == 'WIN' else 'FAIL'} {res_str} "
                      f"indicaba {dir_lbl} — "
                      f"PREDICCION SIN TRADE REAL (pulsa Auto para operar con dinero real)")

            # ── Rolling history para motor adaptativo ─────────────────────────
            self._hist_rolling.append(res_str)
            if len(self._hist_rolling) > 30:
                self._hist_rolling = self._hist_rolling[-30:]

            # ── Registrar en FalloDB + SessionTracker ─────────────────────────
            _asset_reg   = str(a.mem.get("config", {}).get("asset", ""))
            _regimen_reg = str(getattr(self, "_ultimo_regimen", ""))
            _periodo_reg = int(a.mem.get("config", {}).get("periodo_vela", 60))
            try:
                self.fdb.registrar(
                    patron     = self._trade_patron or "?",
                    direccion  = self._trade_dir or "?",
                    votos      = self._trade_votos,
                    prob       = self._trade_prob,
                    indicadores= self._rl_ind_ant or self._ultimo_ind,
                    resultado  = res_str,
                    velas_seq  = list(a.mem["secuencia"]),
                    asset      = _asset_reg,
                    regimen    = _regimen_reg,
                    periodo    = _periodo_reg,
                )

                # El freno diario cuenta EN DINERO, no en número de
                # operaciones: perder 5 de 50 no es perder 5 de 2.000.
                # Se anota aquí, al conocer el resultado — una operación
                # abierta todavía no ha costado nada.
                try:
                    from . import freno_diario as _fdia
                    _fdia.anotar(a, str(res_str).upper() in ("WIN", "GANO"))
                except Exception:
                    pass
            except Exception as e:
                a.log(f"  FalloDB error: {e}")
            try:
                self._session_tracker.registrar(
                    resultado = res_str,
                    votos     = self._trade_votos)
            except Exception:
                pass
            try:
                _monto_reg  = float(a.mem.get("config", {}).get("monto", 1.0))
                _payout_reg = float(getattr(self, "_ultimo_payout", 0.85))
                _p_con_reg  = float(getattr(self, "_ultimo_p_conciencia", 0.5))
                self._perf.registrar(
                    resultado   = res_str,
                    monto       = _monto_reg,
                    payout      = _payout_reg,
                    votos       = self._trade_votos,
                    asset       = _asset_reg,
                    regimen     = _regimen_reg,
                    conciencia_p= _p_con_reg,
                )
            except Exception:
                pass
            # ConcienciaLitch: aprendizaje post-trade (k-NN + Bayes + RedOnline)
            try:
                _con_post = getattr(a, "conciencia", None)
                if _con_post is not None:
                    _vpk_post = getattr(self, "_votos_pend_cal_1", {})
                    _vid_post = [
                        int(bool(_vpk_post.get("markov",     (0, False))[1])),
                        int(bool(_vpk_post.get("estadist",   (0, False))[1])),
                        int(bool(_vpk_post.get("red",        (0, False))[1])),
                        int(bool(_vpk_post.get("pronostico", (0, False))[1])),
                        int(bool(_vpk_post.get("indicadores",(0, False))[1])),
                        int(bool(_vpk_post.get("rl",         (0, False))[1])),
                        int(bool(_vpk_post.get("smc",        (0, False))[1])),
                    ]
                    _rsi_post   = float(self._ultimo_ind.get("rsi", 50.0)) / 100.0
                    _hurst_post = float(self._ultimo_ind.get("hurst") or 0.5)
                    _hr_post    = list(getattr(self, "_hist_rolling", []))
                    _wr20_post  = (sum(1 for r in _hr_post[-20:] if r == "W") /
                                   len(_hr_post[-20:]) if len(_hr_post) >= 5 else 0.5)
                    _eval_cache = getattr(self, "_ultimo_eval_conciencia", {})
                    _p_pred_post = float(_eval_cache.get("p_compuesta", 0.5))
                    _con_post.aprender(
                        asset      = _asset_reg,
                        dir_       = str(self._trade_dir or "V"),
                        hora       = int(getattr(self, "_trade_hora_utc", int(time.gmtime().tm_hour))),
                        regime     = _regimen_reg,
                        votos      = self._trade_votos,
                        prob       = float(self._trade_prob or 0.5),
                        dia        = int(getattr(self, "_trade_dia", time.localtime().tm_wday)),
                        smc_en_kz  = bool(getattr(self, "_trade_smc_kz", False)),
                        kelly      = float(getattr(self, "_trade_kelly", 0.0)),
                        wr20       = _wr20_post,
                        rsi        = _rsi_post,
                        hurst      = _hurst_post,
                        votos_ind  = _vid_post,
                        resultado  = res_str,
                        p_pred     = _p_pred_post,
                        dd_pct     = float(getattr(self, "_trade_dd_pct", 0.0)),
                        slot_factor= float(getattr(self, "_trade_slot_f", 1.0)),
                    )
            except Exception:
                pass
            # Registrar en el HUD de flechas (historial ✓/✗)
            try:
                sv = _sv.obtener()
                if sv is not None:
                    sv.registrar_resultado(acierto)
            except Exception:
                pass

            # Actualizar panel de capital con nuevo saldo estimado
            if _CV_OK:
                try:
                    _cfg_cv   = a.mem.get("config", {})
                    _per_cv   = int(_cfg_cv.get("periodo_vela", 60))
                    _venc_cv  = int(_cfg_cv.get("vencimiento", _per_cv))
                    _monto_cv = float(_cfg_cv.get("monto_base") or
                                      _cfg_cv.get("monto") or 10.0)

                    # Tracking de saldo: base conocida + suma de P&L acumulado
                    _pnl_este = float(self._trade_monto) * (0.85 if acierto else -1.0)
                    _hist_pnl = getattr(self, "_historial_pnl", [])
                    _hist_pnl.append(_pnl_este)
                    if len(_hist_pnl) > 500:
                        _hist_pnl = _hist_pnl[-500:]
                    self._historial_pnl = _hist_pnl

                    # Saldo base: en orden de prioridad
                    _saldo_base = float(
                        _cfg_cv.get("saldo_inicial") or
                        _cfg_cv.get("saldo") or
                        a.mem.get("estadisticas", {}).get("saldo") or 0
                    )
                    # Solo calcular saldo estimado si tenemos un base conocido
                    if _saldo_base > 0:
                        _saldo_est = round(_saldo_base + sum(_hist_pnl), 2)
                    else:
                        _saldo_est = 0.0   # desconocido hasta que usuario lo diga

                    # Tendencia de pantalla (sin bloquear)
                    _tend_cv = "estable"
                    try:
                        from . import vision as _vis_c2
                        _vals_cv = _vis_c2.leer_valores_iq()
                        _tend_cv = _vals_cv.get("saldo_cambio", "estable")
                    except Exception:
                        pass

                    # Recomendación inteligente
                    _recom_cv = None
                    if _saldo_est > 0 and _monto_cv / _saldo_est > 0.04:
                        _opt_cv   = max(1, round(_saldo_est * 0.02))
                        _recom_cv = f"⚠ Baja monto a ${_opt_cv} (2% saldo)"
                    elif _monto_cv > 0 and _saldo_est > 0 and _monto_cv / _saldo_est < 0.003:
                        _opt_cv   = max(1, round(_saldo_est * 0.015))
                        _recom_cv = f"Puedes subir a ${_opt_cv} (1.5% saldo)"
                    elif 0 < _venc_cv < int(_per_cv * 0.6):
                        _recom_cv = f"⚠ Venc muy corto — sube a {_per_cv}s"
                    elif _venc_cv > _per_cv * 4:
                        _recom_cv = f"⚠ Venc muy largo — baja a {_per_cv}s"

                    cv_panel = _cv.obtener()
                    if cv_panel is not None:
                        cv_panel.actualizar(
                            saldo           = _saldo_est,
                            monto           = _monto_cv,
                            vencimiento_seg = _venc_cv,
                            periodo_seg     = _per_cv,
                            recomendacion   = _recom_cv,
                            saldo_tendencia = _tend_cv,
                        )
                except Exception:
                    pass

            # ── Enseñar al RL ─────────────────────────────────────────────────
            if self._rl_seq_ant is not None and self._rl_accion != AgenteRL.ACCION_SKIP:
                reward    = 1.0 if acierto else -1.0
                sec_nuevo = list(a.mem["secuencia"])
                try:
                    # Obtener dd_pct y en_killzone para reward shaping v3
                    _dd_rl  = float(profesional.stats().get("dd_actual", 0.0)) if profesional else 0.0
                    _kz_rl  = bool(self._ultimo_smc.get("en_kz", False))
                    self.rl.aprender(
                        self._rl_seq_ant, self._rl_accion, reward,
                        sec_nuevo, ind_ant=self._rl_ind_ant, ind_nuevo=self._ultimo_ind,
                        en_killzone=_kz_rl, dd_pct=_dd_rl)
                    est_n  = a.mem["estadisticas"]
                    tot_n  = est_n.get("aciertos", 0) + est_n.get("fallos", 0)
                    pwin_n = est_n.get("aciertos", 0) / tot_n * 100 if tot_n else 50
                    a.log(f"  RL aprende: {'ACIERTO' if acierto else 'FALLO'} | "
                          f"eps={self.rl.epsilon:.3f} | prec_rl={int(self.rl.precision()*100)}% | "
                          f"hist={tot_n} trades win={pwin_n:.0f}% | "
                          f"dd={_dd_rl:.1%} kz={'✓' if _kz_rl else '✗'}")
                except Exception as e_rl:
                    a.log(f"  RL error: {e_rl}")
                self._rl_seq_ant = None
                self._rl_accion  = AgenteRL.ACCION_SKIP

            # ── Calibrador: actualiza precisión reciente de cada método ────────
            # Se registran los votos que emitió cada método en el trade anterior.
            # Esto permite que el calibrador ajuste sus pesos en el próximo ciclo.
            try:
                _asset_cal1   = str(a.mem.get("config", {}).get("asset", ""))
                _periodo_cal1 = int(a.mem.get("config", {}).get("periodo_vela", 60))
                if getattr(self, "_votos_pend_cal_1", None):
                    for _m, (_prob, _confirmó) in self._votos_pend_cal_1.items():
                        self.calibrador.registrar(
                            _m, acierto if _confirmó else not acierto, _prob,
                            asset=_asset_cal1, periodo=_periodo_cal1)
                    self._votos_pend_cal_1 = None
            except Exception:
                pass

            # ── CSV, voz, pausa y post-mortem: solo en trades reales ─────────
            if _fue_trade_real:
                # Escribir CSV
                if self._pending_log:
                    ts_p, dir_p, vt_p, pb_p, kf_p = self._pending_log
                    _log_trade_csv(ts_p, self._trade_patron, dir_p, vt_p, pb_p, kf_p, res_str)
                    self._pending_log = None

                # Respuesta de voz
                if a.mem["config"].get("avisar_resultados", True):
                    if acierto:
                        racha = self.fdb.racha_actual()
                        if racha["tipo"] == "WIN" and racha["n"] >= 3:
                            a.decir(a.txt(
                                f"Acierto, senor. Llevamos {racha['n']} en racha. Mantengo la concentracion.",
                                f"Hit, sir. We're on a {racha['n']}-win streak. Staying focused."))
                        else:
                            a.decir(a.txt(
                                "Senal acertada, senor. Patron confirmado y memorizado.",
                                "Signal confirmed, sir. Pattern reinforced and memorized."))
                    else:
                        analisis = self.fdb.analizar_fallo(
                            self._trade_patron, self._rl_ind_ant or self._ultimo_ind,
                            idioma=a.idioma)
                        a.decir(analisis)

                # Pausa automática en racha de pérdidas
                if not acierto:
                    racha = self.fdb.racha_actual()
                    if racha["n"] >= _MAX_RACHA_LOSS:
                        self._activar_pausa()

                # ── Conciencia de error — aprende explícitamente de cada fallo ──
                if not acierto:
                    self._analizar_y_memorizar_error()

                # Post-mortem
                self._post_mortem_trade(acierto)

            # ── Registrar en BrokerUniversal (acumula stats → auto-optimiza) ──
            # ── BrokerUniversal: solo trades reales ───────────────────────────
            if _fue_trade_real:
                try:
                    broker_u = getattr(a, "broker", None)
                    if broker_u:
                        asset_cfg = (a.mem["config"].get("asset_actual")
                                     or a.mem["config"].get("area_asset", "IQ Option"))
                        dur_cfg   = int(a.mem["config"].get("periodo_vela", 60))
                        broker_u.registrar_trade(str(asset_cfg), dur_cfg, res_str,
                                                 monto=self._trade_monto)
                        self._trades_sesion = getattr(self, "_trades_sesion", 0) + 1
                        if self._trades_sesion % 5 == 0:
                            modo_activo = (
                                (a.autoclick_on and a.modo_autonomo)
                                or (getattr(a, "modo_practica",  None) and a.modo_practica.activo)
                                or (getattr(a, "modo_profesional", None) and a.modo_profesional.activo)
                            )
                            if modo_activo:
                                threading.Thread(target=broker_u.auto_optimizar,
                                                 daemon=True,
                                                 name="BrokerOptPost").start()
                except Exception as _be:
                    a.log(f"[Broker] Error post-trade: {_be}")

        if a.modo_autonomo:
            ajuste = a.analizador.autoajustar(a.idioma)
            if ajuste:
                a.decir(ajuste)

        a.analizador.registrar_vela(color)
        try:
            if a.red.quizas_reentrenar(a.mem["secuencia"]):
                a.log("Red neuronal reentrenada con datos nuevos.")
        except Exception as e:
            a.log(f"Red: {e}")

        if self._senal_prep is None:
            self._evaluar_y_loguear()

    # ── Motor Adaptativo — umbral dinámico de votos ───────────────────────────
    def _min_votos_adaptativo(self, aprendiendo: bool, hist=None) -> int:
        """
        Umbral de votos requerido con triple factor:
          1. Base según período de vela (periodo_config)
          2. Ajuste por WR reciente (±1 voto)
          3. Ajuste por modo (práctica / real)

        NUNCA baja de 3 votos (elimina operaciones con 1-2 votos).
        """
        a = self.app
        periodo = int(a.mem.get("config", {}).get("periodo_vela", 60))
        en_practica = bool(aprendiendo or
                          (hasattr(a, "modo_practica") and
                           getattr(a.modo_practica, "activo", False)))

        # Base del período
        base = _pc.votos_minimos(periodo, en_practica=en_practica)

        # Ajuste por WR reciente (solo en producción)
        if not en_practica:
            if hist is None:
                hist = self._hist_rolling
            ventana = hist[-20:] if len(hist) >= 10 else []
            if ventana:
                wr = sum(1 for r in ventana if r == "WIN") / len(ventana)
                if wr >= 0.65:
                    base = max(3, base - 1)   # racha buena → relajar 1 voto
                elif wr < 0.40:
                    base = min(7, base + 1)   # racha mala → exigir 1 voto más

        # Guardar período anterior para detectar cambios
        _periodo_ant = getattr(self, "_ultimo_periodo_detectado", periodo)
        if periodo != _periodo_ant:
            msg = _pc.cambio_detectado(_periodo_ant, periodo)
            if msg:
                try:
                    a.log(f"[Período] {msg}")
                    a.decir(msg)
                except Exception:
                    pass
            self._ultimo_periodo_detectado = periodo

        # NUNCA menos de 3 votos — protección contra ruido
        return max(3, base)

    def _modo_adaptativo_nombre(self) -> str:
        hist = self._hist_rolling
        if len(hist) < 10:
            return "produccion 4/11"
        ventana = hist[-20:]
        wr = sum(1 for r in ventana if r == "WIN") / len(ventana)
        if wr >= 0.60:  return f"ACTIVO wr={wr:.0%}"
        if wr >= 0.45:  return f"normal wr={wr:.0%}"
        if wr >= 0.35:  return f"CAUTO wr={wr:.0%}"
        return f"MUY-CAUTO wr={wr:.0%}"

    # ── Pausa automática (circuit breaker escalonado v3) ─────────────────────
    def _activar_pausa(self):
        """Circuit breaker con escalado: cada racha consecutiva multiplica la pausa.

        1ª activación:  10 min  (pausa estándar, calmarse)
        2ª activación:  20 min  (mercado adverso, reducir exposición)
        3ª+ activación: sesión suspendida hasta que el usuario intervenga manualmente
        """
        a = self.app
        # Contador de cuántas veces se ha activado el circuit breaker esta sesión
        self._cb_activaciones = getattr(self, "_cb_activaciones", 0) + 1
        n = self._cb_activaciones

        if n == 1:
            mins = _PAUSA_MINUTOS          # 10 min
            nivel = "nivel 1"
            recomendacion = "Revisa la sesion de mercado y el activo."
        elif n == 2:
            mins = _PAUSA_MINUTOS * 2      # 20 min
            nivel = "nivel 2"
            recomendacion = "Considera cambiar de activo o esperar la siguiente sesion."
        else:
            mins = 999 * 60                # prácticamente infinito — requiere reset manual
            nivel = "SUSPENSION DE SESION"
            recomendacion = "Di 'reanuda' cuando estés listo para seguir."

        self._pausado_hasta       = time.time() + mins * 60
        self._pausa_anunciada_fin = False

        a.log(f"[CIRCUIT BREAKER] {nivel} — {_MAX_RACHA_LOSS} perdidas seguidas "
              f"(activacion #{n}) — pausa de {mins if n < 3 else 'indefinida'} minutos. "
              f"{recomendacion}")

        if n < 3:
            a.decir(a.txt(
                f"Senor, llevo {_MAX_RACHA_LOSS} perdidas consecutivas. "
                f"Circuit breaker {nivel}. Me detengo {mins} minutos. {recomendacion}",
                f"Sir, {_MAX_RACHA_LOSS} consecutive losses. "
                f"Circuit breaker {nivel}. Pausing {mins} minutes. {recomendacion}"))
        else:
            a.decir(a.txt(
                f"Senor, tercer circuit breaker activado. Sesion suspendida. "
                "El mercado esta en mi contra hoy. Di reanuda cuando quieras continuar. "
                "Proteger el capital es la prioridad.",
                "Sir, third circuit breaker. Session suspended. "
                "The market is against us today. Say resume when ready. "
                "Capital protection is the priority."))

    def _en_pausa(self) -> bool:
        if time.time() < self._pausado_hasta:
            # Throttle: solo loguear una vez cada 30s — el ciclo corre cada 100ms
            # y sin esto inunda el log con miles de líneas "en pausa" por sesión.
            _ahora_p = time.time()
            if _ahora_p - self._t_ultimo_log_pausa >= 30:
                self._t_ultimo_log_pausa = _ahora_p
                restante = int((self._pausado_hasta - _ahora_p) / 60)
                self.app.log(f"[PAUSA] En pausa por rachas de perdidas ({restante} min restantes).")
            return True
        # Pausa terminó — anunciar reanudación una sola vez
        if not getattr(self, "_pausa_anunciada_fin", True):
            self._pausa_anunciada_fin = True
            self.app.log("[PAUSA] Pausa terminada. Retomando operativa.")
            self.app.decir(self.app.txt(
                "Pausa terminada, senor. Retomando operativa con mas cautela.",
                "Pause over, sir. Resuming operations with extra caution."))
        return False

    # ── Calibración periódica: reintenta si aún sin botones ──────────────────
    def _loop_calibracion_periodica(self):
        """Reintenta auto-calibración cada 45 s si algún modo autónomo está activo
        pero los botones aún no están configurados."""
        time.sleep(20)   # espera inicial para que todo arranque
        while not self._detener:
            time.sleep(45)
            try:
                a   = self.app
                cfg = a.mem.get("config", {})
                ya_ok = (cfg.get("boton_verde") and cfg.get("boton_rojo")
                         and cfg.get("region_grafico"))
                if ya_ok or self._recal_running:
                    continue
                en_modo = (
                    (a.autoclick_on and a.modo_autonomo)
                    or (getattr(a, "modo_practica",    None) and a.modo_practica.activo)
                    or (getattr(a, "modo_profesional", None) and a.modo_profesional.activo)
                )
                if not en_modo:
                    continue
                self._recal_running = True
                def _rcal():
                    try:
                        res = vision.auto_calibrar_iq()
                        if res:
                            for k, v in res.items():
                                if _vision_permite(a, k, v):
                                    a.mem["config"][k] = v
                            mem_mod.guardar(a.mem)
                            n = 2 if res.get("boton_verde_2") else 1
                            a.log(f"[Auto] Re-calibrado periódico: {n} gráfica(s)")
                            a.decir(a.txt(
                                "Calibracion exitosa, senor. Listo para operar.",
                                "Calibration successful, sir. Ready to trade."))
                            self._nueva_vela_flag = True
                        else:
                            a.log("[Auto] IQ Option no visible aún. Reintento en 45 s.")
                    finally:
                        self._recal_running = False
                threading.Thread(target=_rcal, daemon=True, name="CalibPeriodica").start()
            except Exception:
                pass

    # ── Reporte autónomo de sesión cada 20 trades ─────────────────────────────
    def _loop_reporte_sesion(self):
        """Anuncia progreso de la sesión cada 20 trades en modo autónomo."""
        _trades_ultimo_reporte = 0
        while not self._detener:
            time.sleep(30)
            try:
                a           = self.app
                practica    = getattr(a, "modo_practica",    None)
                profesional = getattr(a, "modo_profesional", None)
                en_practica = bool(practica    and practica.activo)
                en_pro      = bool(profesional and profesional.activo)
                if not (en_practica or en_pro):
                    _trades_ultimo_reporte = 0
                    continue

                # Con TWS delante no se informa de nada: el contador
                # `estadisticas` es acumulado de IQ Option y aquí no aplica.
                # Repetir «87 % en 13268 operaciones» cada pocos minutos,
                # con 0 operaciones en la sesión, es exactamente la clase de
                # cifra que invita a confiar en lo que no ocurrió.
                if _motor_iq_debe_callar(a):
                    continue

                est = a.mem["estadisticas"]
                tot = est.get("aciertos", 0) + est.get("fallos", 0)
                if tot - _trades_ultimo_reporte < 20 or tot == 0:
                    continue
                _trades_ultimo_reporte = tot

                tasa  = est.get("aciertos", 0) / tot * 100
                p_win = est.get("aciertos", 0) / tot
                kelly = p_win - (1 - p_win) / 0.85

                # El contador `estadisticas` es un acumulado histórico que
                # incluye las operaciones que nunca ocurrieron (las que el
                # motor dio por hechas con el clic bloqueado). Ese 87 % no
                # describe lo que Litch hace hoy.
                #
                # Se prefiere el número honesto: solo operaciones reales,
                # con su intervalo de confianza. Si el honesto no está
                # disponible se usa el viejo, pero avisando de qué es.
                _honesto = ""
                try:
                    from . import cuarentena_stats as _cq
                    _fdb = getattr(self, "fdb", None) or getattr(a, "fdb", None)
                    if _fdb is not None and getattr(_fdb, "trades", None):
                        _r = _cq.winrate_honesto(
                            [{**x, "resultado": x.get("res")}
                             for x in _fdb.trades], minimo=30)
                        if _r.get("wr") is not None:
                            _honesto = _r["texto"]
                            tasa = _r["wr"]
                            tot = _r["n"]
                            p_win = _r["wr"] / 100.0
                            kelly = p_win - (1 - p_win) / 0.85
                except Exception:
                    pass

                if en_practica:
                    modo_txt = "practica DEMO"
                    s        = practica.stats()
                    extra_es = (f"{s['wins']} aciertos y {s['losses']} fallos "
                                f"en esta sesion.")
                    extra_en = (f"{s['wins']} wins and {s['losses']} losses "
                                f"this session.")
                else:
                    modo_txt = "modo profesional"
                    s        = profesional.stats()
                    extra_es = f"P&L Kelly estimado: {profesional._pnl_kelly:.1f}."
                    extra_en = f"Estimated Kelly P&L: {profesional._pnl_kelly:.1f}."

                _cifra_es = (_honesto if _honesto
                             else f"{tot} operaciones, {tasa:.0f}% de acierto")
                a.decir(a.txt(
                    f"Reporte {modo_txt}: {_cifra_es} "
                    f"Kelly {'positivo' if kelly > 0 else 'negativo'}. {extra_es}",
                    f"{modo_txt.title()} report: {tot} total trades, {tasa:.0f}% accuracy. "
                    f"Kelly {'positive' if kelly > 0 else 'negative'}. {extra_en}"))

                # Sugerir profesional si práctica va bien
                if en_practica and tot >= 30 and tasa >= 60 and kelly > 0:
                    a.log(f"[Practica] {tasa:.0f}% WR en {tot} trades — "
                          f"condiciones para modo profesional OK")
                    a.decir(a.txt(
                        f"Senor, {tasa:.0f}% de precision en {tot} operaciones. "
                        "El rendimiento cumple los criterios para el modo profesional. "
                        "Puede activarlo cuando lo desee.",
                        f"Sir, {tasa:.0f}% accuracy over {tot} trades. "
                        "Performance meets professional mode criteria. "
                        "You may activate it whenever you wish."))
            except Exception:
                pass

    # ── Pre-cálculo en background ─────────────────────────────────────────────
    def _precalcular_senal(self):
        try:
            self._precalcular_senal_inner()
        except Exception as _pe:
            self.app.log(f"[PreCalc] Error interno (no crítico): {_pe}")
            self._senal_prep = None

    def _precalcular_senal_inner(self):
        a   = self.app
        sec = list(a.mem["secuencia"])
        if len(sec) < 3:
            return

        senal = a.analizador.evaluar()
        if not senal:
            senal = self._senal_estadistica_fallback(sec)
        if not senal:
            self._senal_prep = None
            return

        dir_sen, votos, prob, decision, patron = self._calcular_consenso(senal, sec)

        n    = len(sec)
        fase = "aprendizaje" if n < 30 else "produccion"
        a.log(f"[Pre-senal {_SECS_PRECALCULO}s] {'SUBE' if dir_sen=='V' else 'BAJA'} | "
              f"{_safe_pct(prob)}% | {votos}/11 votos | "
              f"Bayes={'ACTUAR' if decision['actuar'] else 'esperar'} | {fase}")

        nivel = nivel_honesto(votos)

        # Hablar solo si la dirección cambió, los votos variaron ≥2, o pasaron ≥90s.
        # Esto elimina el spam de "bajada probable 6/7" repetido en cada vela cuando
        # la señal es constante — LITCH solo habla cuando hay algo nuevo que decir.
        _ahora_pre     = time.time()
        _dir_nueva     = (dir_sen != self._ultima_senal_dir)
        _votos_nueva   = (abs(votos - self._ultima_senal_votos) >= 2)
        _t_expirada    = (_ahora_pre - self._ultima_senal_t >= 90)
        # Con Interactive Brokers delante, esta señal no significa nada: se
        # calcula sobre píxeles de TWS leídos como si fueran velas binarias.
        # Anunciarla en voz alta cientos de veces no solo es ruido — es
        # decirle al señor algo que no es verdad. Se calla.
        if _motor_iq_debe_callar(a):
            _dir_nueva = _votos_nueva = _t_expirada = False

        if _dir_nueva or _votos_nueva or _t_expirada:
            a.decir(a.txt(
                f"Senal pre-calculada: {'subida' if dir_sen=='V' else 'bajada'} probable. "
                f"{votos}/11 metodos coinciden. Confianza {nivel}.",
                f"Pre-calculated: likely {'rise' if dir_sen=='V' else 'fall'}. "
                f"{votos}/9 methods agree. {nivel} confidence."))
            self._ultima_senal_dir   = dir_sen
            self._ultima_senal_votos = votos
            self._ultima_senal_t     = _ahora_pre

        self._senal_prep = (dir_sen, votos, prob, decision, patron)

    # ── Visión completa de contexto — loop periódico ──────────────────────────
    def _loop_contexto_pantalla(self):
        """Cada 20s captura contexto de IQ Option. Cada 3min analiza el gráfico
        con Fable 5 (vision) para obtener análisis técnico profesional externo."""
        self._ctx_pantalla = {}
        self._ultimo_analisis_fable = {}  # último análisis recibido de Fable 5
        _t_ultimo_aviso_btn  = 0.0
        _t_ultimo_fable      = 0.0        # cooldown análisis Fable 5
        _COOLDOWN_FABLE      = 210        # 3.5 min entre llamadas a Fable 5
        while not self._detener:
            try:
                if not self.app.activo or not self.app.trading_on:
                    time.sleep(3)
                    continue
                ctx = vision.analizar_contexto_iq()

                # ── Consciencia situacional: ¿en qué app estamos? ─────────
                try:
                    from . import situacion as _sit
                    _tit = _sit.ventana_activa()
                    _app_det = _sit.app_detectada(_tit)
                    ctx["ventana_activa"] = _tit
                    ctx["app_al_frente"]  = _app_det
                    if _app_det != getattr(self, "_app_frente_ant", None):
                        self._app_frente_ant = _app_det
                        self.app.log(f"[Situacion] App al frente: {_app_det}"
                                     f" — «{_tit[:60]}»")
                except Exception:
                    pass

                self._ctx_pantalla = ctx

                # Avisar si los botones SUBE/BAJA no son visibles (broker oculto).
                # Si tenemos posiciones calibradas → verificar directamente esas
                # coordenadas (más preciso que el escaneo de zona genérico).
                a = self.app
                _botones_ok = ctx.get("botones_ok", True)
                if not _botones_ok:
                    try:
                        _cfg_v = a.mem["config"].get("boton_verde")
                        _cfg_r = a.mem["config"].get("boton_rojo")
                        if _cfg_v and _cfg_r:
                            _ok_v = vision.verificar_boton_activo(
                                _cfg_v[0], _cfg_v[1], True)
                            _ok_r = vision.verificar_boton_activo(
                                _cfg_r[0], _cfg_r[1], False)
                            # Si al menos uno pasa la verificación directa → OK
                            _botones_ok = _ok_v or _ok_r
                    except Exception:
                        pass

                if not _botones_ok:
                    ahora = time.time()
                    # Cooldown ampliado a 180s (antes 90s) para reducir mensajes
                    if ahora - _t_ultimo_aviso_btn > 180:
                        _t_ultimo_aviso_btn = ahora

                        # ── DECIR DÓNDE MIRÓ, NO SOLO QUE NO VIO ──────────
                        #
                        # «No veo los botones de trading» es un mensaje que
                        # suena a avería y no lo es. El señor tenía IQ Option
                        # a pantalla completa, con SUBE y BAJA delante de sus
                        # ojos, y Litch decía que no los veía. Parecía que el
                        # programa estaba roto.
                        #
                        # Lo que pasa de verdad es más sencillo: Litch mira
                        # unas coordenadas guardadas, y en esas coordenadas
                        # ya no está el botón — porque IQ Option cambió de
                        # disposición, o porque la pantalla es otra.
                        #
                        # Un diagnóstico que no dice dónde miró no se puede
                        # comprobar. Este sí.
                        _cv = a.mem.get("config", {}).get("boton_verde")
                        _cr = a.mem.get("config", {}).get("boton_rojo")
                        if _cv and _cr:
                            _det = (f"busco SUBE en ({int(_cv[0])},{int(_cv[1])}) "
                                    f"y BAJA en ({int(_cr[0])},{int(_cr[1])}), "
                                    f"y ahí no encuentro sus colores")
                            _sol = ("Si los botones se han movido de sitio, "
                                    "dígame «Litch calibra» con IQ Option "
                                    "delante y los vuelvo a localizar.")
                        else:
                            _det = "no tengo los botones calibrados todavía"
                            _sol = ("Dígame «Litch calibra» con IQ Option "
                                    "en pantalla.")
                        a.log(f"[Vision] {_det}. {_sol}")
                        if a.autoclick_on:
                            a.decir(a.txt(
                                f"Señor, {_det}. {_sol}",
                                f"Sir, {_det}. {_sol}"))

                # Detectar P&L muy negativo durante sesión de práctica
                if ctx.get("pl_color") == "rojo":
                    practica = getattr(self.app, "modo_practica", None)
                    if practica and practica.activo:
                        # Solo lo registra — la conciencia ya maneja la abstención
                        self._ctx_pantalla["sesion_negativa"] = True

                # ── Análisis del gráfico con Fable 5 (vision) cada 3.5 min ─────
                ahora_f = time.time()
                if ahora_f - _t_ultimo_fable > _COOLDOWN_FABLE:
                    try:
                        from . import tv_feed as _tvf_mod
                        _feed_ref = getattr(a, "tv_feed", None)
                        if _feed_ref and _feed_ref.estado().get("ok"):
                            # Centrar el gráfico antes del screenshot para análisis limpio
                            try:
                                _gc_f = getattr(a, "gestor_grafico", None)
                                if _gc_f is not None:
                                    _gc_f.centrar_para_fable()
                            except Exception:
                                pass
                            # Capturar screenshot actual
                            _img_full = vision.capturar_pantalla_completa()
                            if _img_full is not None:
                                import base64, cv2 as _cv2_f
                                _, _buf = _cv2_f.imencode(".jpg", _img_full,
                                    [_cv2_f.IMWRITE_JPEG_QUALITY, 75])
                                _b64 = base64.b64encode(_buf).decode()
                                _activo = a.mem.get("config", {}).get("activo", "EURUSD")
                                _ind_f  = _feed_ref.indicadores()
                                def _fable_tarea():
                                    res = _tvf_mod.analizar_chart_con_fable(
                                        _b64, _activo, _ind_f, a)
                                    if res:
                                        self._ultimo_analisis_fable = {
                                            "ts": time.time(),
                                            "texto": res,
                                            "activo": _activo,
                                        }
                                        a.log(f"[Fable5/Chart] {res[:120]}...")
                                threading.Thread(target=_fable_tarea,
                                                 daemon=True,
                                                 name="FableChart").start()
                                _t_ultimo_fable = ahora_f
                    except Exception:
                        pass

            except Exception:
                pass
            time.sleep(20)  # 20s: menos colisiones GDI con autocalib y explorador

    # ── Fallback estadístico cuando Markov no tiene señal ─────────────────────
    def _senal_estadistica_fallback(self, sec):
        try:
            voto = estadistica.analizar(sec)
        except Exception:
            return None
        # Más permisivo con pocas velas (arranque rápido en cualquier gráfica)
        umbral = 0.51 if len(sec) < 10 else 0.53
        if not voto or voto.get("confianza", 0) < umbral:
            return None
        senal = {
            "patron":       "estadistica_fallback",
            "direccion":    voto.get("candidata", "V"),
            "probabilidad": voto.get("confianza", 0.53),
            "observaciones": 0,
            "hora":         time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.app.analizador.senal_pendiente = senal
        return senal

    # ── Evaluar señal al vuelo ────────────────────────────────────────────────
    def _evaluar_y_loguear(self):
        a   = self.app
        sec = a.mem["secuencia"]
        n   = len(sec)
        if n < 3:
            a.log(f"Acumulando velas: {n}/3...")
            return

        senal = a.analizador.evaluar()
        if not senal:
            senal = self._senal_estadistica_fallback(sec)
        if not senal:
            a.log(f"Analizando patron ({n} velas acumuladas)...")
            return

        dir_sen, votos, prob, decision, patron = self._calcular_consenso(senal, sec)

        aprendiendo = n < 30
        fase        = "aprendizaje" if aprendiendo else "produccion"
        nivel       = nivel_honesto(votos)
        a.log(f"SENAL {'SUBE' if dir_sen=='V' else 'BAJA'} | {_safe_pct(prob)}% | "
              f"{votos}/11 votos | Bayes p={decision['probabilidad']:.2f} "
              f"{'ACTUAR' if decision['actuar'] else 'esperar'} | {fase}")

        # ── HUD profesional — señal visual flotante ───────────────────────────
        try:
            sv = _sv.obtener(root=getattr(a.interfaz, "root", None), app=a)
            if sv is not None:
                # Misma regla que en el cartel de ejecución: lo que se
                # enseña no puede superar lo que sostienen los votos.
                _conf_sv    = confianza_calibrada(
                    a, votos, float(decision.get("probabilidad", prob)))
                _periodo_sv = int(a.mem["config"].get("periodo_vela", 60))
                _t_rest     = max(0, _periodo_sv - int(
                    time.time() - getattr(self, "_t_ultimo_cambio", time.time())))
                _asset_sv   = str(a.mem.get("config", {}).get("asset", ""))
                _reg_sv     = str(getattr(self, "_ultimo_regimen", ""))
                # Detalle de qué método votó (lista de 7 bools: Markov,Est,Red,Pro,Ind,RL,SMC)
                _vdet = getattr(self, "_votos_ind_actual", [])
                sv._secs_total = _periodo_sv   # para la barra de tiempo correcta
                if votos >= 4 or _conf_sv >= 0.62:
                    sv.mostrar(
                        direccion      = dir_sen,
                        votos          = votos,
                        confianza      = _conf_sv,
                        secs_restantes = _t_rest,
                        patron         = patron or "",
                        regimen        = _reg_sv,
                        votos_detalle  = _vdet,
                        asset          = _asset_sv,
                    )
                    # También actualizar banner dentro de la ventana LITCH
                    try:
                        _urgente_ui = _t_rest > 0 and _t_rest <= 6
                        a.interfaz.root.after(0, lambda: a.interfaz.actualizar_banner_senal(
                            dir_sen, votos, _conf_sv, _t_rest, _urgente_ui))
                    except Exception:
                        pass
                elif votos <= 2:
                    sv.ocultar()
                    try:
                        a.interfaz.root.after(0, lambda: a.interfaz.actualizar_banner_senal(
                            "", 0, 0, 0))
                    except Exception:
                        pass
        except Exception:
            pass

        # ── Coherencia de mercado ────────────────────────────────────────────
        # Este motor predice la PRÓXIMA VELA, que es la pregunta de las
        # opciones binarias (vencimiento fijo, todo o nada). En acciones esa
        # pregunta no significa nada: no hay vencimiento, la pérdida la
        # define el stop y la ganancia puede correr.
        #
        # Si la visión está apuntando a Trader Workstation, mostrar aquí un
        # «BAJA 98%» sería aplicar el juego equivocado al tablero
        # equivocado. Mejor callarse y remitir al motor de acciones.
        #
        # OJO: no basta con mirar la etiqueta `broker_visual`. Esa etiqueta
        # se queda vieja: el señor calibró para TWS una vez y ahí sigue,
        # aunque hoy esté operando binarias. El resultado eran dos frases
        # seguidas que se contradecían — «Ejecutando compra, 8/11 modelos»
        # y acto seguido «estoy mirando Interactive Brokers, aquí no
        # predigo». Las dos no pueden ser verdad.
        #
        # Lo que manda es si el motor de binarias está trabajando. Si lo
        # está, esta advertencia sobra y no se dice.
        try:
            if _motor_iq_debe_callar(a) and \
                    a.mem.get("config", {}).get("broker_visual") == "tws":
                if not getattr(self, "_aviso_tws_dado", False):
                    self._aviso_tws_dado = True
                    a.log("[Coherencia] Mi visión apunta a Interactive "
                          "Brokers. No emito señales de vela siguiente sobre "
                          "acciones: ahí esa pregunta no aplica. Use "
                          "«analiza SPY» para el motor de acciones.")
                    try:
                        a.decir("Señor, estoy mirando Interactive Brokers. "
                                "Aquí no predigo la próxima vela: en acciones "
                                "eso no significa nada. Pídame que analice un "
                                "activo y le doy tendencia, stop y objetivo.")
                    except Exception:
                        pass
                return
        except Exception:
            pass

        # ── Letrero de predicción con razonamiento ───────────────────────────
        try:
            _letrero = getattr(a, "letrero", None)
            if _letrero is not None and (votos >= 4 or prob >= 0.60):
                _nombres_voto = [
                    "markov", "estadistica", "red", "pronostico",
                    "indicadores", "rl", "smc", "patrones", "sr",
                    "scalping", "triple"]
                _vdet_l = getattr(self, "_votos_ind_actual", [])
                _votos_dict = {}
                for _ki, _kn in enumerate(_nombres_voto):
                    if _ki < len(_vdet_l):
                        _votos_dict[_kn] = int(_vdet_l[_ki])
                _cfg_l   = a.mem.get("config", {})
                _monto_l = float(_cfg_l.get("monto_base") or _cfg_l.get("monto") or 0)
                _venc_l  = int(_cfg_l.get("vencimiento") or _cfg_l.get("periodo_vela", 60))
                _auto_l  = bool(a.autoclick_on and a.modo_autonomo)
                _dir_str = "SUBE" if dir_sen == "V" else "BAJA"
                a.interfaz.root.after(0, lambda: _letrero.mostrar(
                    direccion  = _dir_str,
                    confianza  = float(prob),
                    votos      = _votos_dict,
                    monto      = _monto_l,
                    vencimiento= _venc_l,
                    autonomo   = _auto_l,
                    ejecutando = False,
                ))
        except Exception:
            pass

        # Misma deduplicación de voz: solo hablar si hay algo nuevo
        _ahora_ev    = time.time()
        _dir_nueva   = (dir_sen != self._ultima_senal_dir)
        _vts_nueva   = (abs(votos - self._ultima_senal_votos) >= 2)
        _t_expirada  = (_ahora_ev - self._ultima_senal_t >= 90)
        if _dir_nueva or _vts_nueva or _t_expirada:
            a.decir(a.txt(
                f"Senal: probable {'subida' if dir_sen=='V' else 'bajada'}. "
                f"Coinciden {votos} de 11 metodos. Confianza {nivel}.",
                f"Signal: likely {'rise' if dir_sen=='V' else 'fall'}. "
                f"{votos} of 9 methods agree. {nivel} confidence."))
            self._ultima_senal_dir   = dir_sen
            self._ultima_senal_votos = votos
            self._ultima_senal_t     = _ahora_ev

        self._ejecutar_si_consenso(dir_sen, votos, decision, patron=patron)

    # ── Momentum de velas recientes ──────────────────────────────────────────
    def _momentum_reciente(self, sec: list, dir_sen: str) -> float:
        """Retorna un factor de ajuste [-0.25, +0.20] basado en las últimas 7 velas.

        Si las últimas velas van CONTRA la señal → penaliza (tendencia en contra).
        Si las últimas velas CONFIRMAN la señal → bonifica ligeramente.
        Esto evita el error más común: operar SUBE en medio de un downtrend fuerte.
        """
        n  = min(7, len(sec))
        if n < 3:
            return 0.0
        ultimas = sec[-n:]
        opuesta = "R" if dir_sen == "V" else "V"
        cant_contra = ultimas.count(opuesta)
        cant_favor  = ultimas.count(dir_sen)
        ratio_contra = cant_contra / n

        if ratio_contra >= 0.71:   # ≥5/7 velas en contra → penalización fuerte
            return -0.25
        if ratio_contra >= 0.57:   # 4/7 velas en contra → penalización media
            return -0.15
        if cant_favor >= 5:        # ≥5/7 velas a favor → bonus pequeño
            return 0.10
        return 0.0

    def _posiciones_abiertas_dir(self) -> tuple[int, int]:
        """Retorna (trades_sube_abiertos, trades_baja_abiertos) del monitor."""
        try:
            monitor = getattr(self, "monitor", None)
            if monitor is None:
                return 0, 0
            # MonitorTrade guarda el trade activo en _trade
            trade = getattr(monitor, "_trade", None)
            if trade is None:
                return 0, 0
            d = trade.get("dir", "")
            return (1, 0) if d == "V" else (0, 1)
        except Exception:
            return 0, 0

    def _votos_minimos_requeridos(self, _es_blitz: bool, _en_practica: bool) -> int:
        """Umbral de votos mínimo según período activo + contexto.

        Delega a periodo_config para consistencia total con _min_votos_adaptativo.
        NUNCA devuelve menos de 3 votos.
        """
        periodo = int(self.app.mem.get("config", {}).get("periodo_vela", 60))
        base = _pc.votos_minimos(periodo, en_practica=_en_practica)
        # Ajuste por racha de pérdidas (solo producción)
        if not _en_practica:
            try:
                hist = self.app.mem.get("historial", [])
                ultimos = [h for h in hist[-8:]
                           if h.get("resultado") in ("gano", "perdio")]
                if len(ultimos) >= 4:
                    perdidas = sum(1 for h in ultimos[-4:]
                                  if h["resultado"] == "perdio")
                    if perdidas >= 3:
                        base = min(7, base + 1)
            except Exception:
                pass
        return max(3, base)   # NUNCA menos de 3

    # ── Consenso de los 7 modelos ─────────────────────────────────────────────
    def _calcular_consenso(self, senal, sec):
        a       = self.app
        dir_sen = senal["direccion"]
        patron  = senal.get("patron", "?")

        # ★ TVFeed: actualizar caché OHLC con datos reales de Yahoo Finance ──
        # Esto hace que PatronesVelas, S/R, Scalping y TripleBarrera usen
        # precios reales en vez de datos estimados de la captura de pantalla.
        _feed = getattr(a, "tv_feed", None)
        if _feed:
            try:
                _velas_yf = _feed.obtener_velas(300)
                if _velas_yf:
                    a._velas_ohlc_cache = _velas_yf
            except Exception:
                pass

        # ★ Red Maestra via pool (CNN/LSTM puede tardar 50-150ms) —
        # El pool reutiliza un hilo caliente en vez de crear+destruir uno por vela.
        _res_red_holder = [{}]
        def _run_red():
            try:
                _res_red_holder[0] = (a.red.predecir_completo(sec)
                                      if hasattr(a.red, "predecir_completo") else {})
            except Exception:
                pass
        _f_red = self._executor.submit(_run_red)

        # Voto 2: Estadística  (rápido — puro Python)
        voto       = {}    # siempre definido antes de usarse más abajo
        confirma_e = False
        try:
            voto       = estadistica.analizar(sec) or {}
            confirma_e = voto.get("candidata") == dir_sen
        except Exception:
            pass

        # Voto 4: Pronóstico  (rápido — series temporales)
        confirma_p = False
        conf_pron  = 0.0
        try:
            pron       = pronostico.analizar(sec)
            confirma_p = pron.get("candidata") == dir_sen
            conf_pron  = pron.get("confianza", 0.0)
        except Exception:
            pass

        # Voto 5: Indicadores técnicos  (rápido — numpy)
        ind_res    = None
        confirma_i = False
        conf_ind   = 0.0
        try:
            ind_res = ind_mod.evaluar_senal(sec)
        except Exception:
            pass
        if ind_res:
            confirma_i = ind_res.get("candidata") == dir_sen
            conf_ind   = ind_res.get("confianza", 0.0)
            det = ind_res.get("detalle", {})
            # Detección de régimen con detector profesional
            try:
                _reg_obj = _dreg.detectar(sec)
                self._ultimo_regimen = _reg_obj.tipo.lower()
                self._ultimo_regimen_obj = _reg_obj
                # Si el mercado está caótico: penalizar confianza de señal
                if _reg_obj.tipo == "CHAOTIC" and _reg_obj.confianza > 0.65:
                    conf_ind *= 0.75
            except Exception:
                self._ultimo_regimen = ind_res.get("regimen", "neutral")
            self._ultimo_ind = {
                # Indicadores clásicos
                "rsi":     det.get("rsi"),
                "macd_h":  det.get("macd_h"),
                "bb":      det.get("bb"),
                "stoch_k": det.get("stoch_k"),
                "wr":      det.get("wr"),
                "mom":     det.get("mom"),
                # Indicadores avanzados
                "atr":           det.get("atr"),
                "hurst":         ind_res.get("hurst"),
                "entropia_perm": ind_res.get("entropia"),
                "adx_fuerza":    ind_res.get("adx_fuerza"),
                "ema_triple":    ind_res.get("ema_triple"),
                "vwap_bias":     ind_res.get("vwap_bias"),
                "regimen":       self._ultimo_regimen,
            }

        # ★ Fast-path: si Markov tiene alta confianza Y 2+ motores rápidos confirman,
        # no esperamos la Red Maestra para disparar — ahorramos hasta 150ms.
        # Para Blitz (≤15s) el fast-path es siempre activo para maximizar velocidad.
        _conf_markov_raw = float(senal.get("probabilidad", 0.55))
        _es_blitz  = int(self.app.mem["config"].get("periodo_vela", 60)) <= 15
        _via_rapida = _es_blitz or (_conf_markov_raw >= 0.75
                                    and sum([confirma_e, confirma_p, confirma_i]) >= 2)

        # Votos 6-11 via pool — reutiliza hilos calientes, sin crear+destruir por vela.
        _rl_holder  = [AgenteRL.ACCION_SKIP, 0.0]
        _smc_holder = [{}]
        _pv_holder  = [None]   # voto 8: patrón de velas
        _sr_holder  = [None]   # voto 9: soporte/resistencia
        _sce_holder = [None]   # voto 10: scalping institucional (EMA200+RSI7)
        _tb_holder  = [None]   # voto 11: triple barrera (López de Prado)

        def _run_rl():
            try:
                ac, cf, _ = self.rl.decidir_con_confianza(sec, self._ultimo_ind)
                _rl_holder[0] = ac
                _rl_holder[1] = cf
            except Exception:
                pass

        def _run_smc():
            try:
                _smc_holder[0] = _smc.analizar_completo(sec, self._ultimo_ind)
            except Exception:
                pass

        def _run_pv():
            if not _PV_OK:
                return
            try:
                # Pasar velas OHLC reales si el broker las tiene disponibles
                _velas_ohlc = getattr(a, "_velas_ohlc_cache", None)
                _pv_holder[0] = _pv.analizar(sec, _velas_ohlc)
            except Exception:
                pass

        def _run_sr():
            if not _SR_OK:
                return
            try:
                _velas_ohlc = getattr(a, "_velas_ohlc_cache", None)
                _sr_holder[0] = _sr.analizar(sec, _velas_ohlc)
            except Exception:
                pass

        def _run_sce():
            if not _SCE_OK:
                return
            try:
                _velas_ohlc = getattr(a, "_velas_ohlc_cache", None)
                _sce_holder[0] = _sce.analizar(sec, _velas_ohlc)
            except Exception:
                pass

        def _run_tb():
            if not _TB_OK:
                return
            try:
                _velas_ohlc = getattr(a, "_velas_ohlc_cache", None)
                _tb_holder[0] = _tb.analizar(sec, _velas_ohlc, dir_senal=dir_sen)
            except Exception:
                pass

        _to_votos = 0.025 if _es_blitz else 0.060
        _f_rl  = self._executor.submit(_run_rl)
        _f_smc = self._executor.submit(_run_smc)
        _f_pv  = self._executor.submit(_run_pv)
        _f_sr  = self._executor.submit(_run_sr)
        _f_sce = self._executor.submit(_run_sce)
        _f_tb  = self._executor.submit(_run_tb)
        for _fut in (_f_rl, _f_smc, _f_pv, _f_sr, _f_sce, _f_tb):
            try:
                _fut.result(timeout=_to_votos)
            except Exception:
                pass

        # Voto 6: RL-DQN
        accion_rl   = _rl_holder[0]
        conf_rl     = _rl_holder[1]
        confirma_rl = (
            (accion_rl == AgenteRL.ACCION_SUBE and dir_sen == "V") or
            (accion_rl == AgenteRL.ACCION_BAJA and dir_sen == "R"))

        # Voto 7: SMC/LWS
        smc_res      = _smc_holder[0]
        confirma_smc = (smc_res.get("votar", False)
                        and smc_res.get("dir") == dir_sen)
        if smc_res:
            self._ultimo_smc = smc_res

        # Voto 8: Patrones de Velas Japonesas
        pv_res       = _pv_holder[0]
        confirma_pv  = False
        conf_pv      = 0.0
        if _PV_OK and pv_res:
            confirma_pv, conf_pv = _pv.votar(pv_res, dir_sen)
            self._ultimo_patron_vela = pv_res

        # Voto 9: Soporte y Resistencia
        sr_res       = _sr_holder[0]
        confirma_sr  = False
        conf_sr      = 0.0
        if _SR_OK and sr_res:
            confirma_sr, conf_sr = _sr.votar(sr_res, dir_sen)
            self._ultimo_sr = sr_res

        # Voto 10: Scalping Institucional (EMA200 + RSI7 + Spread Guard)
        sce_res       = _sce_holder[0]
        confirma_sce  = False
        conf_sce      = 0.0
        if _SCE_OK and sce_res:
            confirma_sce, conf_sce = _sce.votar(sce_res, dir_sen)
            self._ultimo_sce = sce_res

        # Voto 11: Triple Barrera — López de Prado
        tb_res       = _tb_holder[0]
        confirma_tb  = False
        conf_tb      = 0.0
        if _TB_OK and tb_res:
            confirma_tb, conf_tb = _tb.votar(tb_res, dir_sen)
            self._ultimo_tb = tb_res

        # Voto 3: Red Maestra — colectar resultado del pool con timeout
        # Blitz: 15ms; fast-path: 30ms; normal: 100ms
        _red_timeout = 0.015 if _es_blitz else (0.030 if _via_rapida else 0.100)
        try:
            _f_red.result(timeout=_red_timeout)
        except Exception:
            pass
        res_red  = _res_red_holder[0]
        # Extraer resultado del hilo Red Maestra.
        # Si predecir_completo devolvió un dict completo, úsalo directo.
        # Si el hilo no terminó a tiempo (dict vacío), intentar predecir() síncrono
        # (es rápido gracias al caché — evita perder el voto de la red siempre).
        dir_red  = res_red.get("direccion") if res_red.get("entrenada") else None
        if dir_red is None:
            try:
                dir_red, _p_sync = a.red.predecir(sec)
                if res_red.get("probabilidad") is None and _p_sync is not None:
                    res_red["probabilidad"] = _p_sync
            except Exception:
                dir_red = None
        confirma_r = (dir_red == dir_sen) if dir_red else False
        prob_red   = res_red.get("probabilidad", 0.5)
        if not np.isfinite(prob_red):
            prob_red = 0.5

        # ── Votación ponderada por confianza × precisión reciente del método ──
        # Cada método aporta (confianza × peso_calibrador) votos.
        # El calibrador ajusta el peso según la precisión reciente de cada motor
        # (ventana de 60 trades): el que más acierta, más pesa en el consenso.
        # Basado en: Kakushadze & Serur + Brier Score online recalibration.

        # Pesos dinámicos del calibrador (si no hay datos suficientes → 1.0)
        try:
            _pw = self.calibrador.pesos_actuales()
        except Exception:
            _pw = {}

        # Normalizar confianzas a [0,1]
        conf_markov = float(np.clip(senal.get("probabilidad", 0.55), 0.5, 1.0))
        conf_estat  = float(np.clip(voto.get("confianza", 0.53), 0.5, 1.0))
        conf_red    = float(np.clip(abs(prob_red - 0.5) * 2.0, 0.0, 1.0)) if confirma_r else 0.0
        conf_pron_n = float(np.clip(conf_pron, 0.0, 1.0))
        conf_ind_n  = float(np.clip(conf_ind,  0.0, 1.0))
        conf_rl_n   = float(np.clip(conf_rl,   0.0, 1.0))
        conf_smc_n  = float(np.clip(smc_res.get("confianza", 0.6), 0.0, 1.0)) if confirma_smc else 0.0
        conf_pv_n   = float(np.clip(conf_pv,   0.0, 1.0))  if confirma_pv  else 0.0
        conf_sr_n   = float(np.clip(conf_sr,   0.0, 1.0))  if confirma_sr  else 0.0
        conf_sce_n  = float(np.clip(conf_sce,  0.0, 1.0))  if confirma_sce else 0.0
        conf_tb_n   = float(np.clip(conf_tb,   0.0, 1.0))  if confirma_tb  else 0.0

        # Voto de cada método: confianza × peso_calibrador
        # Pesos 8-11: 0.85 (confirman pero no lideran — apoyo cuantitativo)
        voto_markov = conf_markov              * _pw.get("markov",      1.0)
        voto_estat  = (conf_estat              * _pw.get("estadist",    1.0)
                       if confirma_e else (1.0 - conf_estat) * 0.3)
        voto_red    = max(conf_red, 0.5)       * _pw.get("red",         1.0) if confirma_r  else 0.0
        voto_pron   = conf_pron_n              * _pw.get("pronostico",  1.0) if confirma_p  else 0.0
        voto_ind    = conf_ind_n               * _pw.get("indicadores", 1.0) if confirma_i  else 0.0
        voto_rl     = conf_rl_n                * _pw.get("rl",          1.0) if confirma_rl else 0.0
        voto_smc    = conf_smc_n               * _pw.get("smc",         1.0) if confirma_smc else 0.0
        voto_pv     = conf_pv_n  * 0.85                                       if confirma_pv  else 0.0
        voto_sr     = conf_sr_n  * 0.85                                        if confirma_sr  else 0.0
        voto_sce    = conf_sce_n * 0.90        # EMA200+RSI7 — peso un poco mayor (estrategia probada)
        voto_tb     = conf_tb_n  * 0.85        # Triple Barrera — peso estándar

        # np.nansum trata NaN como 0 — protección ante salidas NaN de la red neuronal
        votos_pond  = float(np.nansum([voto_markov, voto_estat, voto_red,
                                       voto_pron, voto_ind, voto_rl, voto_smc,
                                       voto_pv, voto_sr, voto_sce, voto_tb]))

        # ★ Ajuste por momentum de velas recientes
        # Si las últimas velas van fuerte en contra → reduce votos; si confirman → bonus leve
        _momentum = self._momentum_reciente(sec, dir_sen)
        votos_pond = max(0.0, votos_pond + _momentum * 3.0)   # escala al rango de votos

        if _momentum <= -0.15:
            a.log(f"[Momentum] Penalización {_momentum:+.2f} — tendencia reciente en contra de {dir_sen}")

        # ★ Bonus TVFeed: indicadores de Yahoo Finance confirman la señal ─────
        # RSI + EMA + tendencia: si ≥2 confirman → +0.6 votos (moderado, no dominante)
        if _feed:
            try:
                _ind_yf = _feed.indicadores()
                if _ind_yf and _ind_yf.get("n_velas", 0) >= 20:
                    _rsi_yf   = _ind_yf.get("rsi_14")
                    _ema9_yf  = _ind_yf.get("ema_9")
                    _ema21_yf = _ind_yf.get("ema_21")
                    _tend_yf  = _ind_yf.get("tendencia", "lateral")
                    _confirms = 0
                    if dir_sen == "V":
                        if _rsi_yf is not None and _rsi_yf < 38:  _confirms += 1
                        if _ema9_yf and _ema21_yf and _ema9_yf > _ema21_yf: _confirms += 1
                        if _tend_yf == "alcista": _confirms += 1
                    else:
                        if _rsi_yf is not None and _rsi_yf > 62:  _confirms += 1
                        if _ema9_yf and _ema21_yf and _ema9_yf < _ema21_yf: _confirms += 1
                        if _tend_yf == "bajista": _confirms += 1
                    if _confirms >= 2:
                        votos_pond += 0.65
                        a.log(f"[TVFeed] +{0.65:.2f}v ({_confirms}/3 confirman: "
                              f"RSI={_rsi_yf:.0f if _rsi_yf else '?'} "
                              f"Tend={_tend_yf})")
            except Exception:
                pass

        # ★ Bonus Fable 5: análisis de chart visión (fresco ≤ 5 min) ──────────────
        _fable_cache = getattr(self, "_ultimo_analisis_fable", {})
        if _fable_cache and (time.time() - _fable_cache.get("ts", 0)) < 300:
            try:
                _texto_f5 = _fable_cache.get("texto", "").lower()
                # Parsear señal: COMPRA→V, VENTA→R, ESPERAR→neutro
                _dir_f5 = None
                if "compra" in _texto_f5 or "alcista" in _texto_f5:
                    _dir_f5 = "V"
                elif "venta" in _texto_f5 or "bajista" in _texto_f5:
                    _dir_f5 = "R"
                if _dir_f5 == dir_sen:
                    # Confirma nuestra dirección → +0.75 bonus (visión de Fable 5 es valiosa)
                    votos_pond += 0.75
                    a.log(f"[Fable5] +0.75v — análisis chart confirma {dir_sen}")
                elif _dir_f5 is not None and _dir_f5 != dir_sen:
                    # Contradicción → penalización leve
                    votos_pond = max(0.0, votos_pond - 0.50)
                    a.log(f"[Fable5] -0.50v — análisis chart contradice {dir_sen} (ve {_dir_f5})")
            except Exception:
                pass

        votos       = int(round(votos_pond))   # votos enteros para compatibilidad

        # Votos binarios (para log y FalloDB — ahora 11 métodos)
        votos_bin = (1
                     + (1 if confirma_e   else 0)
                     + (1 if confirma_r   else 0)
                     + (1 if confirma_p   else 0)
                     + (1 if confirma_i   else 0)
                     + (1 if confirma_rl  else 0)
                     + (1 if confirma_smc else 0)
                     + (1 if confirma_pv  else 0)
                     + (1 if confirma_sr  else 0)
                     + (1 if confirma_sce else 0)
                     + (1 if confirma_tb  else 0))

        # Vector para la Conciencia (11 votos individuales)
        self._votos_ind_actual = [
            1,                         # Markov (origen de dir_sen)
            int(confirma_e),
            int(confirma_r),
            int(confirma_p),
            int(confirma_i),
            int(confirma_rl),
            int(confirma_smc),
            int(confirma_pv),          # velas japonesas
            int(confirma_sr),          # soporte/resistencia
            int(confirma_sce),         # ← nuevo: scalping EMA200+RSI7
            int(confirma_tb),          # ← nuevo: triple barrera López de Prado
        ]

        # Motor Bayesiano (umbral adaptativo por entropía + flag practica)
        est    = a.mem["estadisticas"]
        tot    = est.get("aciertos", 0) + est.get("fallos", 0)
        prec_m = est.get("aciertos", 0) / tot if tot else 0.5
        prec_r = a.red.precision_aprox(sec) or 0.5
        n      = len(sec)
        _entropia_actual = self._ultimo_ind.get("entropia_perm")
        _en_practica_flag = bool(
            getattr(a, "modo_practica", None) and a.modo_practica.activo)
        _wr_sesion = prec_m if tot >= 20 else None
        decision = inferencia.decidir(sec, [
            {"direccion": dir_sen,                    "confianza": senal["probabilidad"],
             "precision": prec_m, "n": tot},
            {"direccion": voto.get("candidata"),      "confianza": voto.get("confianza", 0.53),
             "precision": 0.55,   "n": n},
            {"direccion": dir_red,                    "confianza": abs(prob_red - 0.5) * 2.0,
             "precision": prec_r,  "n": n},
            {"direccion": pron.get("candidata"),      "confianza": conf_pron,
             "precision": 0.54,   "n": n},
        ], entropia=_entropia_actual, en_practica=_en_practica_flag,
           wr_sesion=_wr_sesion)

        # Log detallado
        ms_txt  = f" {res_red.get('ms','?')}ms" if res_red else ""
        cnn_txt = (f"CNN:{_safe_pct(res_red.get('avg_A',0.5))}% "
                   f"LSTM:{_safe_pct(res_red.get('avg_B',0.5))}% "
                   f"MLP:{_safe_pct(res_red.get('avg_C',0.5))}%"
                   if res_red.get("entrenada") else "Maestra:aprendiendo")
        rl_acc  = ["SKIP", "SUBE", "BAJA"][accion_rl]
        try:
            fdb_pat = self.fdb.es_patron_problematico(patron)
        except Exception:
            fdb_pat = False
        smc_txt = (f"SMC:{'OK' if confirma_smc else 'NO'} "
                   f"[{smc_res.get('setup','?')} "
                   f"kz={'✓' if smc_res.get('en_kz') else '✗'}]"
                   if smc_res else "SMC:sin datos")
        pv_txt  = (f"Velas:{str(pv_res)}" if pv_res else "Velas:—")
        sr_txt  = (f"S/R:{'OK' if confirma_sr else 'NO'} {sr_res.texto[:30] if sr_res and sr_res.texto else '—'}"
                   if sr_res else "S/R:—")
        sce_txt = (f"Scalp:{'OK' if confirma_sce else 'NO'} "
                   f"EMA={getattr(sce_res,'tendencia_ema','?')[:3] if sce_res else '?'} "
                   f"RSI7={getattr(sce_res,'rsi7_actual',0.0):.0f}"
                   if sce_res else "Scalp:—")
        tb_txt  = (f"TB:{'OK' if confirma_tb else 'NO'} "
                   f"W={getattr(tb_res,'tasa_win',0.0):.0%}({getattr(tb_res,'n_eventos',0)}ev)"
                   if tb_res else "TB:—")
        a.log(f"  est {'OK' if confirma_e else 'NO'} | "
              f"Maestra {'OK' if confirma_r else 'NO'} ({_safe_pct(prob_red)}%){ms_txt} "
              f"[{cnn_txt}] | "
              f"pron {'OK' if confirma_p else 'NO'} ({_safe_pct(conf_pron)}%) | "
              f"ind {'OK' if confirma_i else 'NO'} ({_safe_pct(conf_ind)}%) | "
              f"RL {'OK' if confirma_rl else 'NO'} {rl_acc}({_safe_pct(conf_rl)}%) | "
              f"{smc_txt} | {pv_txt} | {sr_txt} | "
              f"{sce_txt} | {tb_txt} | "
              f"patron {'PROBLEMATICO' if fdb_pat else 'OK'} | "
              f"Bayes evid={decision['evidencia']} "
              f"racha {decision['racha']}/{decision['racha_esperada']}"
              + (" ⚡via-rapida" if _via_rapida else ""))

        decision["via_rapida"] = _via_rapida

        # Guardar confianzas + dirección de cada método para el calibrador.
        self._votos_pend_cal_1 = {
            "markov":      (float(conf_markov), True),
            "estadist":    (float(conf_estat),  bool(confirma_e)),
            "red":         (float(abs(prob_red - 0.5) * 2.0), bool(confirma_r)),
            "pronostico":  (float(conf_pron),   bool(confirma_p)),
            "indicadores": (float(conf_ind),    bool(confirma_i)),
            "rl":          (float(conf_rl),     bool(confirma_rl)),
            "smc":         (float(smc_res.get("confianza", 0.5) if smc_res else 0.5), bool(confirma_smc)),
            "velas":       (float(conf_pv),     bool(confirma_pv)),
            "sr":          (float(conf_sr),     bool(confirma_sr)),
            "scalping":    (float(conf_sce),    bool(confirma_sce)),
            "triple_bar":  (float(conf_tb),     bool(confirma_tb)),
        }

        # ── SignalAggregator: segunda capa de validación con pesos dinámicos ──
        try:
            _asset_agg  = str(a.mem.get("config", {}).get("asset", ""))
            _per_agg    = int(a.mem.get("config", {}).get("periodo_vela", 60))
            _dir_rl_agg = ("V" if accion_rl == AgenteRL.ACCION_SUBE
                           else ("R" if accion_rl == AgenteRL.ACCION_BAJA else None))
            senal_agg = self._sig_agg.agregar(
                markov      = {"direccion": dir_sen,           "confianza": conf_markov},
                estadistica = {"direccion": voto.get("candidata"), "confianza": conf_estat},
                red_maestra = {"direccion": dir_red,           "confianza": abs(prob_red - 0.5) * 2.0},
                pronostico  = {"direccion": pron.get("candidata"), "confianza": conf_pron},
                indicadores = {"direccion": ind_res.get("candidata") if ind_res else None,
                               "confianza": conf_ind},
                rl_agente   = {"direccion": _dir_rl_agg,       "confianza": conf_rl},
                smc         = {"direccion": smc_res.get("dir") if smc_res else None,
                               "confianza": smc_res.get("confianza", 0.5) if smc_res else 0.5},
                asset       = _asset_agg,
                periodo     = _per_agg,
            )
            decision["agg_score"]     = senal_agg.score
            decision["agg_conf"]      = senal_agg.confianza
            decision["agg_actuar"]    = senal_agg.actuar
            decision["agg_regimen"]   = senal_agg.regimen
            # Guardar el último p_conciencia estimado para el PerformanceTracker
            self._ultimo_p_conciencia = float(senal_agg.confianza)
            # Ajuste de votos según score del agregador (pesos dinámicos calibrados)
            _agg_dir_ok = (senal_agg.direccion == dir_sen) if senal_agg.direccion else False
            if senal_agg.actuar and _agg_dir_ok and senal_agg.score > 0.55:
                votos = min(11, votos + 1)
                a.log(f"  [Agg] {senal_agg.resumen()} → +1 voto total={votos}")
            elif senal_agg.actuar and not _agg_dir_ok and abs(senal_agg.score) > 0.55:
                votos = max(0, votos - 1)
                a.log(f"  [Agg] Contra-señal (score={senal_agg.score:+.2f} dir={senal_agg.direccion}) → -1 voto total={votos}")
            else:
                a.log(f"  [Agg] {senal_agg.resumen()}")
        except Exception:
            pass

        return dir_sen, votos, senal.get("probabilidad", 0.55), decision, patron

    # ── Ejecutar si hay consenso ──────────────────────────────────────────────
    def _ejecutar_si_consenso(self, dir_sen, votos, decision, patron: str = "?"):
        a            = self.app

        # ══════════════════════════════════════════════════════════════════
        #  PORTERO DE BROKER — la causa raíz de todo lo que salía mal
        # ══════════════════════════════════════════════════════════════════
        #
        # Con la visión apuntando a Interactive Brokers, este motor seguía
        # decidiendo y "ejecutando" opciones binarias cada pocos segundos.
        # Los clics se bloqueaban en manos.py — bien — pero el motor no se
        # enteraba: daba la operación por hecha, esperaba el resultado, y
        # anotaba victorias y rachas de operaciones que NUNCA existieron.
        # Así se llegó a un 87 % de aciertos sobre miles de trades fantasma.
        #
        # Bloquear el clic no bastaba. Había que apagar la decisión.
        #
        # Aquí se corta antes de decidir nada. En acciones no se apuesta a
        # la próxima vela de 60 segundos: eso no significa nada. Para IBKR
        # están rutinas_tws y piloto_tws, que es donde vive el criterio
        # correcto.
        if _motor_iq_debe_callar(a):
            _avisar_motor_callado(a)
            return

        # ── EL FRENO DIARIO — el «basta» escrito en frío ──────────────────
        #
        # Este va el PRIMERO de todos los porteros, y a propósito. Los
        # demás evitan errores puntuales; este evita la espiral: se pierde
        # una, se sube el tamaño para recuperar, se pierden dos más. Cuando
        # el señor no está delante no hay nadie que diga basta.
        #
        # Hasta hoy el límite se guardaba y nadie lo miraba. Le dije que
        # pararía y no paraba: un freno que no frena es peor que no tener
        # freno, porque da una seguridad falsa que hace apostar más.
        try:
            from . import freno_diario as _fd
            _ok_dia, _por_dia = _fd.puede_operar(a)
            if not _ok_dia:
                if (time.time() - getattr(self, "_t_aviso_freno", 0)) > 300:
                    self._t_aviso_freno = time.time()
                    a.log(f"[Freno] No opero: {_por_dia}.")
                return
            if _por_dia and "cuidado" in _por_dia:
                if (time.time() - getattr(self, "_t_aviso_margen", 0)) > 600:
                    self._t_aviso_margen = time.time()
                    a.decir(f"Señor, {_por_dia}.")
        except Exception:
            pass

        # ── LOS NÚMEROS DEL SEÑOR, NO LOS MÍOS ────────────────────────────
        #
        # Antes de decidir nada se relee el ticket de IQ Option: monto,
        # vencimiento y pago. El señor tenía CO$ 6.000 puestos y Litch
        # calculaba con 50 — un factor de 120 en todos sus frenos de
        # riesgo. Con la caché de 4 s esto no cuesta casi nada, y evita
        # operar con cifras de hace media hora.
        try:
            from . import leer_ticket_iq as _lti
            _lti.sincronizar(a, hablar=False)
        except Exception:
            pass

        # ── ¿ESTÁ CALIBRADA ESTA PANTALLA? ────────────────────────────────
        #
        # Litch puede haberse mudado al monitor 2 mientras sus coordenadas
        # de SUBE y BAJA siguen siendo las del 1. En ese estado el clic
        # sale y no llega: la operación se daría por hecha sin existir.
        #
        # Es el mismo fallo de las 86 operaciones fantasma, y por eso este
        # portero es duro: sin calibración para la pantalla actual, no se
        # opera. Ni en práctica — anotar resultados falsos envenena el
        # aprendizaje igual de rápido.
        try:
            from . import calibracion_por_monitor as _cpm
            from . import monitores as _monx
            _mact = _monx.monitor_de_barra(a)
            _hay_otros = len(_monx.listar()) > 1
            if _hay_otros and not _cpm.tiene(a, _mact["n"]):
                # Solo bloquea si la calibración actual NO cae dentro del
                # monitor donde está trabajando: si cae dentro, es que
                # nunca se movió y todo está bien.
                _bv = a.mem.get("config", {}).get("boton_verde")
                _fuera = True
                if _bv and len(_bv) >= 2:
                    _fuera = not (_mact["x"] <= _bv[0] < _mact["x"] + _mact["w"]
                                  and _mact["y"] <= _bv[1] < _mact["y"] + _mact["h"])
                if _fuera:
                    if (time.time() - getattr(self, "_t_aviso_calmon", 0)) > 180:
                        self._t_aviso_calmon = time.time()
                        a.decir(f"Señor, estoy en el monitor {_mact['n']} pero "
                                f"mis botones SUBE y BAJA están calibrados en "
                                f"otra pantalla. Pulsaría donde no es, así que "
                                f"no opero. Dígame «Litch calibra» aquí.")
                    return
        except Exception:
            pass

        # ── ¿EL TAMAÑO DE LA APUESTA ES SENSATO? ──────────────────────────
        #
        # El señor tenía CO$ 1.500 puestos sobre un saldo de CO$ 1.501: el
        # 99,9 % de la cuenta en una operación de un minuto. Con un 80 %
        # de aciertos, una de cada cinco veces se lo lleva todo.
        #
        # Litch no puede impedírselo —es su dinero— pero sí decírselo
        # antes, no después.
        try:
            from . import mercado_y_tamano as _myt
            _cfgm = a.mem.get("config", {})
            _cap = _cfgm.get("saldo") or _cfgm.get("capital") or 0
            _mto = _cfgm.get("monto_broker") or _cfgm.get("monto_base") or 0
            if _cap and _mto:
                _ev = _myt.evaluar_tamano(_cap, _mto, _cfgm.get("divisa", ""))
                if _ev.get("grave") and \
                        (time.time() - getattr(self, "_t_aviso_tam", 0)) > 300:
                    self._t_aviso_tam = time.time()
                    a.decir(_ev["mensaje"])
        except Exception:
            pass

        # ── ¿LA VELA Y EL VENCIMIENTO HABLAN EL MISMO IDIOMA? ─────────────
        #
        # Analizar velas de 5 minutos para operar 30 segundos es pedirle al
        # gráfico que diga lo que pasa dentro de media vela. La señal sale
        # igual, pero no significa nada. Se avisa una vez cada 10 minutos
        # — no en cada operación, que sería ruido.
        try:
            from . import escala_temporal as _et
            _cfgt = a.mem.get("config", {})
            _coh = _et.coherencia(int(_cfgt.get("periodo_vela") or 60),
                                  int(_cfgt.get("vencimiento") or 60))
            if not _coh["ok"]:
                if (time.time() - getattr(self, "_t_aviso_escala", 0)) > 600:
                    self._t_aviso_escala = time.time()
                    a.decir(f"Señor, un aviso: {_coh['motivo']}. Mis "
                            f"señales salen igual, pero valen menos de lo "
                            f"que parecen.")
        except Exception:
            pass

        practica     = getattr(a, "modo_practica",    None)
        profesional  = getattr(a, "modo_profesional", None)
        _en_practica = bool(practica    and practica.activo)
        _en_pro      = bool(profesional and profesional.activo) and not _en_practica
        _es_blitz    = int(a.mem["config"].get("periodo_vela", 60)) <= 15

        autonomo_ok  = (a.autoclick_on and a.modo_autonomo)

        # ── Meta Diaria: informativa en modo autónomo, bloqueante en manual ──
        meta = getattr(a, "meta_diaria", None)
        if meta and not _en_practica:
            puede_meta, razon_meta = meta.puede_tradear()
            if not puede_meta:
                if autonomo_ok:
                    a.log(f"[Meta] {razon_meta} — modo Auto continua operando.")
                else:
                    a.log(f"[Meta] Trade bloqueado — {razon_meta}")
                    return

        # ── Piso absoluto de votos: NUNCA operar con < 3/11 en ningún modo ─────
        # ── EL FILTRO QUE SEPARA GANAR DE PERDER ──────────────────────────
        #
        # Litch acierta el 78 % de media. El equilibrio con pago 85 % está
        # en 54 %. Parece que basta con operar siempre — y no basta.
        #
        # Ese 78 % es un promedio. Debajo hay contextos donde acierta el
        # 90 % y otros donde acierta el 45 %. Operar en los segundos
        # regala justo lo que ganan los primeros: el promedio sale bien y
        # la cuenta sale mal.
        #
        # Aquí se comprueba si en ESTE contexto —estos votos, este patrón—
        # la ventaja está demostrada por encima del equilibrio. Si no, se
        # salta la operación. En modo práctica no bloquea: ahí el objetivo
        # es reunir datos, y saltarse las malas impediría aprender de ellas.
        try:
            from . import filtro_ventaja as _fv
            _prac = getattr(getattr(a, "modo_practica", None), "activo", False)
            _ok_v, _por_v = _fv.permitir(a, votos, patron)
            if not _ok_v:
                if _prac:
                    a.log(f"[Ventaja] Operaría igual por estar en práctica, "
                          f"pero sepa que {_por_v}.")
                else:
                    a.log(f"[Ventaja] Salto esta operación: {_por_v}.")
                    return
        except Exception:
            pass

        _VOTOS_PISO = 3
        if votos < _VOTOS_PISO:
            a.log(f"[FiltroVotos] {votos}/11 — señal demasiado débil (mínimo {_VOTOS_PISO}). Skip.")
            return

        # ── Flash-crash gate ──────────────────────────────────────────────────
        if time.time() < getattr(self, "_flash_crash_hasta", 0.0):
            restante = int(self._flash_crash_hasta - time.time())
            a.log(f"[FlashCrash] Trade bloqueado por posible flash crash "
                  f"({restante}s restantes).")
            return

        # ══ MEMORIA DE REFUERZO: patrones dorados y peligrosos ═══════════════
        # Litch recuerda con qué patrones GANA (los refuerza con un voto extra
        # y más probabilidad) y con cuáles PIERDE (los evita). Consulta con
        # caché de 60s: costo casi cero por trade.
        _es_dorado = False
        try:
            if patron and patron != "?":
                _ver = self.fdb.veredicto_patron(patron, dir_sen)
                if _ver["tipo"] == "peligroso":
                    a.log(f"[MemoriaRefuerzo] ✗ Patron '{patron}' {dir_sen}: "
                          f"WR {_ver['wr']}% en {_ver['n']} trades — "
                          f"histórico perdedor. Trade evitado.")
                    return
                if _ver["tipo"] == "dorado":
                    _es_dorado = True
                    votos = min(11, votos + 1)
                    decision["probabilidad"] = min(
                        0.95, decision.get("probabilidad", 0.5) + 0.05)
                    a.log(f"[MemoriaRefuerzo] ★ Patron dorado '{patron}' "
                          f"{dir_sen}: WR {_ver['wr']}% en {_ver['n']} trades "
                          f"— señal reforzada (+1 voto).")
        except Exception:
            pass

        # ══ CORTACIRCUITOS DE RIESGO (Manual 13, integrado) ══════════════════
        # Consulta las guardias de riesgo antes de operar: en ROJO no opera,
        # en naranja/amarillo reduce el tamaño. La disciplina no se negocia
        # por euforia (error C4 del catálogo de IA).
        try:
            if not _en_practica:
                from . import guardias_riesgo as _gr
                _veredicto = _gr.evaluar_antes_de_operar(a)
                if not _veredicto["operar"]:
                    a.log(f"[Cortacircuitos] {_veredicto['nivel']}: "
                          f"{_veredicto['razon']} — trade bloqueado.")
                    return
                self._factor_tamano_riesgo = _veredicto["factor_tamano"]
                if _veredicto["nivel"] != "VERDE":
                    a.log(f"[Cortacircuitos] {_veredicto['nivel']} — "
                          f"tamaño al {int(_veredicto['factor_tamano']*100)}%. "
                          f"{_veredicto['razon']}")
            else:
                self._factor_tamano_riesgo = 1.0
        except Exception:
            self._factor_tamano_riesgo = 1.0

        # ══ UMBRAL DE VOTOS APRENDIDO ════════════════════════════════════════
        # Litch calcula qué umbral de votos maximizó su tasa de aciertos real
        # (fdb._votos_optimos). Aquí lo APLICA: fuera del modo práctica, si la
        # señal trae menos votos que su óptimo aprendido, se abstiene — salvo
        # que el patrón sea dorado (evidencia propia más fuerte).
        try:
            if not _en_practica and not _es_dorado:
                _vt_opt = self.fdb._votos_optimos_cacheado()
                if _vt_opt and votos < _vt_opt:
                    a.log(f"[UmbralAprendido] {votos}/11 votos < óptimo "
                          f"histórico {_vt_opt} — me abstengo (mi historial "
                          f"dice que estas señales no son rentables).")
                    return
        except Exception:
            pass

        if not autonomo_ok and not _en_practica and not _en_pro:
            # Shadow hover: mueve el ratón al botón sin clickear (feedback visual)
            self._shadow_hover(dir_sen, votos, decision)
            return

        # ── Pausa por racha de pérdidas ──────────────────────────────────────
        # Práctica y modo autónomo real: no pausar — el usuario decide operar.
        # Practica: aprende incluso en rachas malas.
        # Autónomo: Auto-click es la única llave, el sistema no se detiene solo.
        if not _en_practica and not autonomo_ok and self._en_pausa():
            return
        if autonomo_ok and time.time() < self._pausado_hasta:
            mins_r = int((self._pausado_hasta - time.time()) / 60)
            a.log(f"[Racha] {_MAX_RACHA_LOSS} perdidas detectadas "
                  f"({mins_r} min de pausa recomendada) — modo Auto continua.")

        prob_bayes  = decision.get("probabilidad", 0.5)
        n_velas     = len(a.mem["secuencia"])
        aprendiendo = n_velas < 30

        # Kelly adaptativo con drawdown, régimen y racha
        est        = a.mem["estadisticas"]
        tot_trades = est.get("aciertos", 0) + est.get("fallos", 0)
        p_win      = est.get("aciertos", 0) / tot_trades if tot_trades >= 10 else prob_bayes
        _dd_kelly  = float(profesional.stats().get("dd_actual", 0.0)) if profesional else 0.0
        _reg_kelly = getattr(self, "_ultimo_regimen", "neutral")
        _rl_kelly  = int(getattr(self.fdb, "_racha_actual_n", 0))
        _per_kelly = int(a.mem.get("config", {}).get("periodo_vela", 60))
        kelly_f    = _kelly(p_win, dd_pct=_dd_kelly,
                            regimen=_reg_kelly, racha_loss=_rl_kelly,
                            periodo_seg=_per_kelly)

        # ── CapitalManager — conciencia de saldo, monto y vencimiento ────────────
        try:
            _cfg_cap   = a.mem.get("config", {})
            _saldo_cap = float(_cfg_cap.get("saldo", 0) or
                               a.mem.get("estadisticas", {}).get("saldo", 0) or 0)
            _monto_cap = float(_cfg_cap.get("monto_base") or
                               _cfg_cap.get("monto") or 10.0)
            _venc_cap  = int(_cfg_cap.get("vencimiento", _per_kelly))
            self._capital.actualizar(_saldo_cap, _monto_cap, _venc_cap)
            _ev_cap = self._capital.evaluar(
                kelly_f          = kelly_f,
                votos            = votos,
                confianza        = prob_bayes,
                periodo_vela_seg = _per_kelly,
            )
            # Avisar si hay algo relevante (saldo, monto excesivo, vencimiento mal)
            if _ev_cap.mensaje:
                a.log(f"[Capital] {_ev_cap.mensaje}")
                try:
                    a.decir(_ev_cap.mensaje)
                except Exception:
                    pass
            # Log compacto cada 10 trades
            _tc_cap = est.get("aciertos", 0) + est.get("fallos", 0)
            if _tc_cap > 0 and _tc_cap % 10 == 0:
                a.log(self._capital.estado_texto())
        except Exception as _ec:
            a.log(f"[Capital] error: {_ec}")

        # ── ConcienciaLitch: evaluación pre-trade (k-NN + Bayes + RedOnline) ──────
        try:
            _con = getattr(a, "conciencia", None)
            if _con is not None:
                _hora_con  = int(time.strftime("%H"))
                _dia_con   = time.localtime().tm_wday
                _asset_con = str(a.mem.get("config", {}).get("asset", ""))
                _reg_con   = str(getattr(self, "_ultimo_regimen", "neutral"))
                _smc_kz_c  = bool(self._ultimo_smc.get("en_kz", False))
                _hr_c      = list(getattr(self, "_hist_rolling", []))
                _wr20_c    = (sum(1 for r in _hr_c[-20:] if r == "W") /
                              len(_hr_c[-20:]) if len(_hr_c) >= 5 else 0.5)
                _rsi_c     = float(self._ultimo_ind.get("rsi", 50.0)) / 100.0
                _hurst_c   = float(self._ultimo_ind.get("hurst") or 0.5)
                _vpk_c     = getattr(self, "_votos_pend_cal_1", {})
                _vid_c     = [
                    int(bool(_vpk_c.get("markov",     (0, False))[1])),
                    int(bool(_vpk_c.get("estadist",   (0, False))[1])),
                    int(bool(_vpk_c.get("red",        (0, False))[1])),
                    int(bool(_vpk_c.get("pronostico", (0, False))[1])),
                    int(bool(_vpk_c.get("indicadores",(0, False))[1])),
                    int(bool(_vpk_c.get("rl",         (0, False))[1])),
                    int(bool(_vpk_c.get("smc",        (0, False))[1])),
                ]
                _dd_c  = float(profesional.stats().get("dd_actual", 0.0)) if profesional else 0.0
                _stf_c = self._session_tracker.factor_confianza()
                _eval_c = _con.evaluar(
                    asset      = _asset_con,
                    dir_       = dir_sen,
                    hora       = _hora_con,
                    regime     = _reg_con,
                    votos      = votos,
                    prob       = prob_bayes,
                    dia        = _dia_con,
                    smc_en_kz  = _smc_kz_c,
                    kelly      = kelly_f,
                    wr20       = _wr20_c,
                    rsi        = _rsi_c,
                    hurst      = _hurst_c,
                    votos_ind  = _vid_c,
                    dd_pct     = _dd_c,
                    slot_factor= _stf_c,
                )
                self._ultimo_eval_conciencia = _eval_c
                _p_comp = _eval_c.get("p_compuesta", 0.5)
                # En Profesional: la conciencia puede bloquear el trade
                if _en_pro and _eval_c.get("debe_abstenerse"):
                    a.log(f"[Conciencia] Abstención — {_eval_c.get('razon', '?')} "
                          f"(P={_p_comp:.2f} umbral={_eval_c.get('umbral_efectivo',0.57):.2f})")
                    return
                # En cualquier modo: loguear cuando recomienda abstenerse
                if _eval_c.get("debe_abstenerse"):
                    a.log(f"[Conciencia] Recomendaría abstenerse: "
                          f"{_eval_c.get('razon', '?')} (P={_p_comp:.2f}) — modo continúa.")
                elif _eval_c.get("n_episodios", 0) >= 10:
                    a.log(f"[Conciencia] P_comp={_p_comp:.2f} "
                          f"(eps={_eval_c['n_episodios']} upd={_con.red.n_updates})")
        except Exception:
            pass

        # ── Filtros de contexto inteligente ──────────────────────────────────────
        # En PRÁCTICA y en MODO AUTÓNOMO REAL los filtros están desactivados:
        # el objetivo es aprender de TRADES REALES sin que el sistema se bloquee.
        # En modo PROFESIONAL aplican todos (capital institucional — máxima cautela).

        # 1. Umbral mínimo adaptativo: solo Profesional
        _votos_min_ctx = self._votos_minimos_requeridos(_es_blitz, _en_practica)
        if votos < _votos_min_ctx and _en_pro:
            a.log(f"[PRO-Filtro] {votos}/{_votos_min_ctx} votos requeridos. Skip.")
            return

        # 1b. Gate de régimen caótico: solo Profesional
        _regimen = getattr(self, "_ultimo_regimen", "neutral")
        if _regimen == "chaotic" and _en_pro:
            if votos < 6:
                a.log(f"[PRO-Régimen] Mercado caótico — señal cancelada "
                      f"({votos}/11 votos, se requieren 6).")
                return
            a.log(f"[PRO-Régimen] Mercado caótico pero {votos}/11 votos — precaución.")

        # 2. Anti-correlación: solo Profesional
        if _en_pro:
            try:
                monitor    = getattr(self, "monitor", None)
                _trade_act = getattr(monitor, "_trade", None) if monitor else None
                if _trade_act and _trade_act.get("dir") == dir_sen:
                    ctx = getattr(self, "_ctx_pantalla", {})
                    pl_negativo = ctx.get("pl_color") == "rojo"
                    import time as _t_now
                    elapsed = _t_now.time() - _trade_act.get("inicio", _t_now.time())
                    if elapsed > 5 and pl_negativo and votos < 6:
                        a.log(f"[PRO-Filtro] Trade abierto y P&L negativo — "
                              f"necesito 6+ votos. Solo {votos}/9.")
                        return
            except Exception:
                pass

        # 3. Momentum fuerte en contra: solo Profesional
        _mom = self._momentum_reciente(a.mem.get("secuencia", []), dir_sen)
        if _en_pro and _mom <= -0.25 and votos < 5:
            a.log(f"[PRO-Momentum] Downtrend fuerte contra {dir_sen}. "
                  f"Solo {votos}/11 votos — cancelada.")
            return

        # Auto-click (autonomo_ok) tiene prioridad absoluta: cuando está activo
        # se salta tanto los filtros de Práctica como los de Pro y va directo
        # al bloque autonomous (solo cooldown). Así el usuario que presionó Auto
        # opera en tiempo real aunque Práctica DEMO siga activa en background.
        if _en_practica and not autonomo_ok:
            # Práctica: aprendizaje por acción — el módulo practica decide si puede
            puede, razon = practica.puede_ejecutar(votos, prob_bayes)
            if not puede:
                a.log(f"[Practica] Esperando — {razon}")
                return

        elif _en_pro and not autonomo_ok:
            # Profesional: 6/11 votos + prob alta + Kelly positivo
            puede, razon = profesional.puede_ejecutar(votos, prob_bayes, kelly_f)
            if not puede:
                a.log(f"[PRO] No ejecuta: {razon}")
                return
            # FalloDB — bloquea patrones adversos
            try:
                if self.fdb.es_patron_problematico(patron) and n_velas >= 30:
                    a.log(f"[PRO] FalloDB bloquea patron '{patron}' — historial adverso.")
                    return
            except Exception:
                pass
            # SessionTracker — franja horaria × votos
            try:
                hora_h_now = int(time.strftime("%H"))
                riesgo     = self.fdb.riesgo_hora_votos(hora_h_now, votos)
                if not riesgo["ok"] and riesgo["n"] >= 8:
                    a.log(f"[PRO] FalloDB hora×votos: {riesgo['razon']} → bloqueado")
                    return
            except Exception:
                pass
            # SessionTracker — ¿es un slot históricamente viable?
            try:
                viable, motivo_slot = self._session_tracker.slot_viable()
                if not viable:
                    a.log(f"[PRO] SessionTracker: {motivo_slot} → skip")
                    return
            except Exception:
                pass
            # Info de sesión y SMC (solo informan)
            hora_ok  = profesional.hora_optima()
            smc_dir  = self._ultimo_smc.get("dir", "")
            smc_kz   = self._ultimo_smc.get("en_kz", False)
            smc_conf = (smc_dir == dir_sen) if smc_dir else None
            ses_info = profesional._sesion_actual()
            a.log(f"[PRO] SMC={('OK' if smc_conf else 'NO') if smc_conf is not None else '?'} "
                  f"kz={'✓' if smc_kz else '✗'} | "
                  f"sesion={ses_info['nombre']}×{ses_info['factor']:.2f} | "
                  f"factor_st={self._session_tracker.factor_confianza():.2f} | "
                  f"kelly={kelly_f:.3f}")

        else:
            # ── Modo Autónomo Real — Auto-click es la única llave ─────────────
            # Filtros mínimos: cooldown técnico + slot históricamente crítico con señal débil.
            ahora    = time.time()
            periodo  = int(a.mem["config"].get("periodo_vela", 60))
            cooldown = max(5, min(_COOLDOWN_CLICK, periodo - 4))
            if ahora - self._ultimo_click_t < cooldown:
                restante = int(cooldown - (ahora - self._ultimo_click_t))
                a.log(f"[Cooldown] {restante}s para el proximo trade.")
                return
            # SessionTracker — slot históricamente muy malo + señal débil → skip suave
            try:
                _viable_st, _motivo_st = self._session_tracker.slot_viable()
                _factor_st = self._session_tracker.factor_confianza()
                if not _viable_st:
                    if _factor_st < 0.70 and votos < 5:
                        a.log(f"[Auto] Slot crítico ({_motivo_st}) + {votos}/11 votos — señal débil, skip.")
                        return
                    else:
                        a.log(f"[Auto] Franja débil ({_motivo_st}) factor={_factor_st:.2f} — Auto continúa.")
            except Exception:
                pass

        try:
            a.red.registrar_prediccion(a.mem["secuencia"], dir_sen)
        except Exception:
            pass

        # ── Guardar contexto del trade ────────────────────────────────────────
        ahora  = time.time()
        ts     = time.strftime("%Y-%m-%d %H:%M:%S")

        self._rl_seq_ant    = list(a.mem["secuencia"])
        self._rl_accion     = (AgenteRL.ACCION_SUBE if dir_sen == "V"
                               else AgenteRL.ACCION_BAJA)
        self._rl_ind_ant    = dict(self._ultimo_ind)
        self._trade_patron  = patron
        self._trade_dir     = dir_sen
        self._trade_votos   = votos
        self._trade_prob    = prob_bayes
        self._trade_kelly   = kelly_f
        self._trade_ts      = ts
        self._pending_log   = (ts, dir_sen, votos, prob_bayes, kelly_f)
        self._trade_monto   = float(a.mem["config"].get("monto_base", 10.0))
        # Cortacircuitos: reducir el monto según el nivel de riesgo (Manual 13).
        # Nunca por debajo del mínimo de $1. En VERDE el factor es 1.0.
        try:
            _factor_r = float(getattr(self, "_factor_tamano_riesgo", 1.0))
            if _factor_r < 1.0:
                self._trade_monto = max(1.0, round(self._trade_monto * _factor_r, 2))
        except Exception:
            pass
        # Contexto para ConcienciaLitch.aprender() post-trade
        self._trade_hora_utc = int(time.gmtime().tm_hour)
        self._trade_dia      = time.localtime().tm_wday
        self._trade_smc_kz   = bool(self._ultimo_smc.get("en_kz", False))
        self._trade_dd_pct   = float(profesional.stats().get("dd_actual", 0.0)) if profesional else 0.0
        self._trade_slot_f   = self._session_tracker.factor_confianza()
        # Registrar vencimiento activo para CapitalManager y logs
        _venc_trade = int(a.mem["config"].get("vencimiento", _per_kelly))
        a.mem["config"]["vencimiento"] = _venc_trade
        # _votos_pend_cal_1 fue asignado en _calcular_consenso() con valores reales

        if _en_practica:
            prefijo = "[PRACTICA DEMO]"
        elif _en_pro:
            prefijo = "[PRO]"
        else:
            prefijo = "  "

        rentable = kelly_f > 0
        a.log(f"{prefijo} Kelly({_safe_pct(p_win)}% win) = "
              f"{kelly_f*100:.1f}% | {'RENTABLE' if rentable else 'BORDE'} | "
              f"{votos}/11 votos | p={prob_bayes:.2f}")

        # En modo Pro: ajustar monto con Kelly si el broker lo permite
        if _en_pro:
            try:
                cfg_monto = float(a.mem["config"].get("monto_base", 10.0))
                monto_opt = profesional.calcular_monto(kelly_f, cfg_monto)
                broker    = getattr(a, "broker", None)
                if broker and hasattr(broker, "set_monto"):
                    broker.set_monto(monto_opt)
                    a.log(f"[PRO] Monto Kelly: ${monto_opt:.0f}")
            except Exception:
                pass

        # ── Conciencia: evaluación pre-trade con timeout (no bloquea el click) ──
        if self.conciencia is not None:
            try:
                _asset   = a.mem["config"].get("asset_actual", "IQ Option")
                _hora    = int(time.strftime("%H"))
                _dia     = int(time.strftime("%w"))
                _ind     = self._ultimo_ind or {}
                _smc_pre = self._ultimo_smc or {}
                _roll20  = self._hist_rolling[-20:]
                _pw20    = (sum(1 for r in _roll20 if r == "WIN") /
                            max(len(_roll20), 1) * 100 if _roll20 else 50.0)
                _con_holder = [{}]
                # Capturar dd_pct y slot_factor para conciencia v3
                _dd_con  = 0.0
                _sf_con  = 1.0
                try:
                    _dd_con = float(profesional.stats().get("dd_actual", 0.0)) if profesional else 0.0
                except Exception:
                    pass
                try:
                    _sf_con = float(self._session_tracker.factor_confianza())
                except Exception:
                    pass
                def _eval_con():
                    try:
                        _con_holder[0] = self.conciencia.evaluar(
                            asset       = str(_asset),
                            dir_        = dir_sen,
                            hora        = _hora,
                            regime      = _ind.get("regimen") or self._ultimo_regimen or "neutral",
                            votos       = votos,
                            prob        = prob_bayes,
                            dia         = _dia,
                            smc_en_kz   = bool(_smc_pre.get("en_kz", False)),
                            kelly       = kelly_f,
                            wr20        = _pw20,
                            rsi         = _ind.get("rsi") or 50.0,
                            hurst       = _ind.get("hurst") or 0.5,
                            votos_ind   = getattr(self, "_votos_ind_actual", [1,0,0,0,0,0,0]),
                            dd_pct      = _dd_con,
                            slot_factor = _sf_con,
                        )
                    except Exception:
                        pass
                # Conciencia via pool — sin crear/destruir hilo por trade
                _f_con   = self._executor.submit(_eval_con)
                _via_rap = decision.get("via_rapida", False)
                _to_con  = (0.015 if _es_blitz
                            else 0.035 if (_via_rap or _en_practica)
                            else 0.070)
                try:
                    _f_con.result(timeout=_to_con)
                except Exception:
                    pass
                con_res = _con_holder[0] if _con_holder[0] else {}
                if con_res:
                    p_con = con_res.get("p_compuesta", 0.5)
                    n_eps = con_res.get("n_episodios", 0)
                    a.log(f"  [Conciencia] p_comp={p_con:.3f} eps={n_eps} bay={con_res.get('p_bayesiana',0):.3f} "
                          f"{'⚠ ABSTENERSE: ' + con_res['razon'] if con_res.get('debe_abstenerse') else '✓ adelante'}")
                    _override = con_res.get("override", "auto")
                    # Override manual forzado: siempre se aplica, sin importar el modo
                    if _override == "forzar_abstener":
                        a.log("[Conciencia] Señal rechazada — abstención FORZADA por el usuario.")
                        return
                    # Abstención automática: solo en modo Profesional (15+ episodios)
                    # En modo autónomo real la conciencia es solo informativa —
                    # el Auto-click es la única llave.
                    if _en_pro and con_res.get("debe_abstenerse") and n_eps >= 15:
                        a.log("[Conciencia] PRO: Señal rechazada — abstención recomendada.")
                        return
                    if autonomo_ok and con_res.get("debe_abstenerse"):
                        a.log("[Conciencia] Abstención recomendada — modo Auto continua.")
            except Exception as _ce:
                a.log(f"[Conciencia] Error pre-trade: {_ce}")

        # ── Verificación de monto e inversión antes de operar ────────────────
        try:
            _cfg_vt   = a.mem.get("config", {})
            _monto_vt = float(_cfg_vt.get("monto_base") or _cfg_vt.get("monto") or 0.0)
            _venc_vt  = int(_cfg_vt.get("vencimiento", 0))
            _per_vt   = int(_cfg_vt.get("periodo_vela", 60))
            # Vencimiento por defecto = período de vela si no está configurado
            if _venc_vt <= 0:
                _venc_vt = _per_vt
            _venc_min_vt = _venc_vt // 60
            _venc_seg_vt = _venc_vt % 60
            _venc_str_vt = (f"{_venc_min_vt}min" if _venc_seg_vt == 0
                            else f"{_venc_min_vt}min {_venc_seg_vt}s")
            dir_lbl_vt = "SUBE ▲" if dir_sen == "V" else "BAJA ▼"
            a.log(f"[PreTrade] ${_monto_vt:.0f} | Venc={_venc_str_vt} | {dir_lbl_vt}")
            # Alerta si monto es cero o negativo — evita trade sin dinero
            if _monto_vt <= 0:
                a.log("[PreTrade] ⛔ Monto es 0. Configura el monto en el panel.")
                try:
                    a.decir(a.txt(
                        "Señor, el monto de inversión es cero. No puedo operar sin capital configurado.",
                        "Sir, the investment amount is zero. I cannot trade without a configured amount."))
                except Exception:
                    pass
                return
            # Alerta si monto parece excesivo (>$500 en demo = posible error)
            _tipo_cta_vt = _cfg_vt.get("tipo_cuenta", "demo")
            if _tipo_cta_vt == "demo" and _monto_vt > 500:
                a.log(f"[PreTrade] ⚠ Monto ${_monto_vt:.0f} alto para demo — verifica la configuración.")
            # Alerta si monto en real >$200 sin confirmación explícita
            if _tipo_cta_vt == "real" and _monto_vt > 200:
                a.log(f"[PreTrade] ⚠ REAL: monto ${_monto_vt:.0f} — asegúrese de que es correcto.")
            # Alerta si vencimiento es muy largo para el período de vela
            if _venc_vt > _per_vt * 3:
                a.log(f"[PreTrade] ⚠ Venc={_venc_str_vt} muy largo para período {_per_vt}s — considera reducirlo.")
            # Guardar para el log post-trade
            self._trade_monto_confirmado  = _monto_vt
            self._trade_venc_confirmado   = _venc_vt
        except Exception:
            pass

        # ── Letrero: "ejecutando ahora" antes del click ──────────────────────
        try:
            _letrero_ej = getattr(a, "letrero", None)
            if _letrero_ej is not None:
                _vdet_ej = getattr(self, "_votos_ind_actual", [])
                _nms_ej  = ["markov","estadistica","red","pronostico",
                             "indicadores","rl","smc","patrones","sr","scalping","triple"]
                _vd_ej   = {n: int(_vdet_ej[i]) if i < len(_vdet_ej) else 0
                            for i, n in enumerate(_nms_ej)}
                _cfg_ej  = a.mem.get("config", {})
                _mn_ej   = float(_cfg_ej.get("monto_base") or _cfg_ej.get("monto") or 0)
                _vc_ej   = int(_cfg_ej.get("vencimiento") or _cfg_ej.get("periodo_vela", 60))
                _dir_ej  = "SUBE" if dir_sen == "V" else "BAJA"
                # El cartel NUNCA muestra más confianza de la que sostienen
                # los votos. Ver confianza_honesta().
                _conf_ej = confianza_calibrada(a, _vd_ej, float(prob_bayes))
                a.interfaz.root.after(0, lambda: _letrero_ej.mostrar(
                    direccion  = _dir_ej,
                    confianza  = _conf_ej,
                    votos      = _vd_ej,
                    monto      = _mn_ej,
                    vencimiento= _vc_ej,
                    autonomo   = True,
                    ejecutando = True,
                ))
        except Exception:
            pass

        # ── Ejecutar click PRIMERO, narrar via pool (sin retrasar el trade) ──
        self._trade_ejecutado = self._ejecutar_click(dir_sen)
        self._executor.submit(
            self._narrar_razonamiento,
            dir_sen, votos, patron, prob_bayes, p_win, decision)

        if self._trade_ejecutado:
            dir_lbl      = "SUBE" if dir_sen == "V" else "BAJA"
            asset        = (a.mem["config"].get("asset_actual")
                            or a.mem["config"].get("broker_activo", "broker"))
            monto_t      = self._trade_monto
            _venc_log    = getattr(self, "_trade_venc_confirmado",
                                   int(a.mem["config"].get("vencimiento",
                                       a.mem["config"].get("periodo_vela", 60))))
            _vm_log      = _venc_log // 60
            _vs_log      = _venc_log % 60
            _venc_str_l  = f"{_vm_log}min" if _vs_log == 0 else f"{_vm_log}min {_vs_log}s"
            tipo_cuenta  = a.mem["config"].get("tipo_cuenta", "demo")
            if tipo_cuenta == "real":
                a.log(f">>> TRADE REAL  ⚠  {dir_lbl} | ${monto_t:.0f} | venc={_venc_str_l} | "
                      f"{votos}/11 votos | {asset} | DINERO REAL")
            else:
                a.log(f">>> TRADE DEMO  🎮  {dir_lbl} | ${monto_t:.0f} | venc={_venc_str_l} | "
                      f"{votos}/11 votos | {asset} | cuenta demo")
            self._ultimo_click_t = ahora
            if _en_practica:
                practica.registrar_click()
            elif _en_pro:
                profesional.registrar_click()
            # Activar monitor de trade (Rollover si va en rojo)
            periodo = int(a.mem["config"].get("periodo_vela", 60))
            self.monitor.abrir_trade(dir_sen, duracion=periodo)
        else:
            a.log("[Trading] ⚠ Click FALLIDO — trade NO registrado. Re-calibrando...")
            # Limpiar pending_log para que no se cuente como trade real
            self._pending_log = None
            threading.Thread(target=self._recalibrar_urgente,
                             daemon=True, name="RecalUrg").start()

    # ── Shadow hover: muestra visualmente el intento sin clickear ─────────────

    def _shadow_hover(self, dir_sen: str, votos: int, decision: dict) -> None:
        """Mueve el ratón al botón SUBE/BAJA para mostrar la intención de
        Litch — feedback visual sin ejecutar trade real."""
        prob    = decision.get("probabilidad", 0.5)
        dir_txt = "SUBE" if dir_sen == "V" else "BAJA"
        self.app.log(
            f"[Sombra] Indicaria {dir_txt} ({votos}/11 votos, p={prob:.2f}) "
            f"— pulsa el boton AUTO para que Litch opere con dinero real")

        # HUD profesional siempre activo (incluso sin autoclick)
        try:
            sv = _sv.obtener(root=getattr(self.app.interfaz, "root", None), app=self.app)
            if sv is not None:
                _periodo_sh = int(self.app.mem["config"].get("periodo_vela", 60))
                _t_rest_sh  = max(0, _periodo_sh - int(
                    time.time() - getattr(self, "_t_ultimo_cambio", time.time())))
                _asset_sh   = str(self.app.mem.get("config", {}).get("asset", ""))
                _reg_sh     = str(getattr(self, "_ultimo_regimen", ""))
                _vdet_sh    = getattr(self, "_votos_ind_actual", [])
                sv._secs_total = _periodo_sh
                if votos >= 3 or prob >= 0.60:
                    sv.mostrar(
                        direccion      = dir_sen,
                        votos          = votos,
                        confianza      = prob,
                        secs_restantes = _t_rest_sh,
                        patron         = getattr(self, "_trade_patron", "") or "",
                        regimen        = _reg_sh,
                        votos_detalle  = _vdet_sh,
                        asset          = _asset_sh,
                    )
        except Exception:
            pass

        # ══ SIN AUTOCLICK EL MOUSE NO SE TOCA ═══════════════════════════
        # Antes aquí se movía el cursor al botón como "hover fantasma".
        # Eliminado: la señal se muestra SOLO con el letrero HUD flotante
        # (flecha, votos, confianza y cuenta regresiva en tiempo real).
        # El único botón que autoriza mover el mouse es AUTO.
        return

    # ── Click físico ──────────────────────────────────────────────────────────
    def _ejecutar_click(self, direccion) -> bool:
        """Ejecuta click en SUBE/BAJA. Retorna True si el click se completó.

        Pre-click inteligente:
          1. Verifica que la posición almacenada sigue mostrando el color correcto.
          2. Si no → re-detecta en tiempo real con auto_calibrar_iq().
          3. Actualiza las coordenadas en config y memoria.
          4. Sin calibración manual: Litch siempre sabe dónde están los botones.
        """
        if not _PG_OK:
            self.app.log("pyautogui no disponible: no puedo hacer click.")
            return False
        cfg      = self.app.mem["config"]
        clave    = "boton_verde" if direccion == "V" else "boton_rojo"
        es_verde = (direccion == "V")
        coords   = cfg.get(clave)

        # ── Verificación visual pre-click + re-detección con múltiples capas ──
        #
        # Política de resiliencia (orden de prioridad):
        #   1. Verificar que la posición guardada sigue mostrando el color correcto
        #   2. Si falla → re-detectar con auto_calibrar_iq() (umbral reducido)
        #   3. Si falla → intentar UILearner (aprendizaje visual)
        #   4. Si falla → inferir desde el botón contrario (offset dinámico)
        #   5. Si todo falla → usar las coords guardadas de todos modos (NUNCA
        #      abortar un trade por un fallo de verificación visual pasajero)
        #
        # La verificación visual es ADVISORY: los fallos pasajeros (animaciones
        # post-trade, hover state, reflejos) NO deben bloquear operaciones.
        # El único motivo legítimo de abortar es no tener NINGUNA coordenada.

        _coords_guardadas = coords   # guardar antes de cualquier modificación

        # Paso 1: verificación rápida
        _verif_ok = bool(coords) and vision.verificar_boton_activo(
            coords[0], coords[1], es_verde)

        if not _verif_ok:
            if coords:
                self.app.log(
                    f"[Click] Botón {clave} ({coords[0]},{coords[1]}) "
                    "no confirmado visualmente — buscando en pantalla...")

            # Paso 2: re-detección con auto_calibrar_iq (umbral reducido a 150px)
            try:
                fresh = vision.auto_calibrar_iq()
            except Exception:
                fresh = {}

            if fresh.get(clave):
                coords = fresh[clave]
                cfg.update(fresh)
                try:
                    from . import memoria as _mm_click
                    _mm_click.guardar(self.app.mem)
                except Exception:
                    pass
                self.app.log(
                    f"[Click] Botones re-detectados — {clave}: {coords}.")

            else:
                # Paso 3: UILearner como fuente de coordenadas
                _ul = getattr(self.app, "ui_learner", None)
                _ul_pos = None
                if _ul is not None:
                    try:
                        _ul_pos = _ul.obtener_pos("compra" if es_verde else "venta")
                    except Exception:
                        pass
                if _ul_pos:
                    coords = list(_ul_pos)
                    self.app.log(
                        f"[Click] UILearner provee posición: {coords}.")

                else:
                    # Paso 4: inferir desde el botón contrario con offset dinámico
                    clave_alt  = "boton_rojo" if es_verde else "boton_verde"
                    coords_alt = (cfg.get(clave_alt) or
                                  (fresh or {}).get(clave_alt))
                    if coords_alt:
                        # Offset dinámico: si tenemos ambas posiciones guardadas,
                        # usar la diferencia real (más preciso que el 85px fijo)
                        bv = cfg.get("boton_verde")
                        br = cfg.get("boton_rojo")
                        if bv and br:
                            dyn_offset = br[1] - bv[1]   # diferencia real en Y
                            offset = -dyn_offset if es_verde else dyn_offset
                        else:
                            offset = -110 if es_verde else 110   # default IQ Option
                        coords = [coords_alt[0], coords_alt[1] + offset]
                        self.app.log(
                            f"[Click] {clave} no visible — infiriendo de "
                            f"{clave_alt} (offset {offset}px).")

                    else:
                        # Paso 5: ÚLTIMO RECURSO — usar las coords guardadas aunque
                        # la verificación visual haya fallado. Esto puede ocurrir
                        # durante animaciones post-trade de IQ Option (el color del
                        # botón cambia 300–500ms tras una operación). Es preferible
                        # intentar el click que perder la señal.
                        if _coords_guardadas:
                            coords = _coords_guardadas
                            self.app.log(
                                f"[Click] Usando coordenadas guardadas como "
                                f"último recurso: {coords}.")
                        else:
                            self.app.log(
                                "[Click] Sin coordenadas de botones. "
                                "Abre IQ Option y espera la auto-calibración.")
                            return False

        dir_txt = "SUBE" if direccion == "V" else "BAJA"
        try:
            # Aplicar monto configurado en IQ Option solo si está en modo manual
            if cfg.get("monto_modo_manual"):
                broker = getattr(self.app, "broker", None)
                if broker and hasattr(broker, "set_monto_iq"):
                    try:
                        broker.set_monto_iq(float(cfg.get("monto_base", 10.0)))
                    except Exception:
                        pass

            periodo_vela = int(cfg.get("periodo_vela", 60))
            region_pl    = cfg.get("region_pl")

            def _verificar():
                return vision.verificar_trade_abierto(region_pl)

            # Enfocar ventana del broker — Electron/Chromium requiere foco de
            # Windows para procesar clicks externos de pyautogui correctamente.
            # En Blitz (≤15s) lo omitimos para no perder ms críticos.
            if periodo_vela > 15:
                manos.enfocar_broker()
                time.sleep(0.07)   # 70ms — Windows procesa el cambio de foco

            # Blitz (≤15s): click instantáneo sin verificación ni retry.
            # Otros períodos: verificación adaptativa sin bloquear más de 120ms.
            ok = manos.click_con_retry(
                coords[0], coords[1],
                verificar_fn=_verificar if region_pl else None,
                periodo_vela=periodo_vela,
                max_intentos=1 if periodo_vela <= 15 else 2)
            self.app.log(f"▶ [CLICK] {dir_txt} ({coords[0]}, {coords[1]})"
                         + (" ✓" if ok else " ⚠ sin confirmar"))

            # UILearner: registrar click ejecutado (aprendizaje visual)
            try:
                _ul = getattr(self.app, "ui_learner", None)
                if _ul is not None:
                    _ul.notificar_click(
                        "compra" if es_verde else "venta",
                        coords[0], coords[1])
            except Exception:
                pass

            # Aparcar cursor en background — NO bloquea el loop de trading
            manos.aparcar_cursor_async(cfg.get("region_grafico"), periodo_vela)
            return True
        except Exception as e:
            self.app.log(f"[Trading] Error al hacer click: {e}")
            return False

    def _recalibrar_urgente(self) -> None:
        """Recalibra inmediatamente cuando un botón falla — sin esperar al ciclo normal."""
        if self._recal_running:
            return
        self._recal_running = True
        try:
            from . import vision as vis_mod, memoria as mem_mod
            res = vis_mod.auto_calibrar_iq()
            if res:
                cfg = self.app.mem["config"]
                n = 0
                for k, v in res.items():
                    if _vision_permite(a, k, v):
                        cfg[k] = v
                    n += 1
                mem_mod.guardar(self.app.mem)
                self.app.log(f"[RecalUrg] Re-calibrado OK ({n} elementos). Próxima señal clicará.")
            else:
                self._registrar_fallo_recal("urgente")
                self.app.log("[RecalUrg] IQ Option no detectado. ¿Está visible en pantalla?")
        except Exception as e:
            self.app.log(f"[RecalUrg] Error: {e}")
        finally:
            self._recal_running = False

    def _registrar_fallo_recal(self, origen: str = "") -> None:
        """
        Registra una recalibración fallida.
        Si hay ≥3 fallos en 10 minutos → detiene el trading automáticamente
        y alerta por voz para que el usuario intervenga.
        """
        ahora = time.time()
        # Limpiar fallos fuera de la ventana de 10 minutos
        self._recal_fail_ts = [t for t in self._recal_fail_ts if ahora - t < 600]
        self._recal_fail_ts.append(ahora)

        n = len(self._recal_fail_ts)
        self.app.log(f"[Vision] Fallo de recalibración #{n}/3 en últimos 10 min "
                     f"(origen={origen}).")

        if n >= 3:
            self._recal_fail_ts.clear()
            a = self.app
            a.log("[Vision] ⚠ 3 recalibraciones fallidas — pausando trading para proteger capital.")
            try:
                a.set_trading(False, hablar=False)
            except Exception:
                pass
            try:
                a.decir(a.txt(
                    "Atención: no puedo ver el gráfico de IQ Option. "
                    "He pausado el trading automáticamente para proteger el capital. "
                    "Asegúrate de que IQ Option esté visible en pantalla y dime 'reanudar trading'.",
                    "Warning: I cannot see the IQ Option chart. "
                    "Trading has been paused to protect your capital. "
                    "Make sure IQ Option is visible and say 'resume trading'."))
            except Exception:
                pass

    # ── Canal 2: segundo gráfico/activo independiente ─────────────────────────
    # Permite operar dos gráficas a la vez (mismo u otro activo) — cada una
    # con su propia secuencia, señal y click, pero alimentando los mismos
    # motores de aprendizaje (red neuronal, RL, FalloDB) para entrenar el
    # doble de rápido, tal como se entrena con la vista dividida de IQ Option.

    def _listo_canal2(self) -> bool:
        a = self.app
        if not (a.activo and a.trading_on):
            return False
        return bool(a.mem["config"].get("region_grafico_2"))

    def _loop_canal2(self):
        """Bucle independiente del canal 2 — detecta cambio de vela en su
        propia región y dispara su propio ciclo de análisis/ejecución."""
        _err2 = 0
        while not self._detener:
            periodo = int(self.app.mem["config"].get("periodo_vela", 60))
            time.sleep(max(0.25, min(1.5, periodo / 40.0)))
            try:
                if not self._listo_canal2():
                    _err2 = 0
                    continue
                a       = self.app
                region2 = a.mem["config"].get("region_grafico_2")
                color   = vision.color_vela(region2)
                if color is None:
                    continue
                ahora = time.time()
                ant   = self._c2["color_vela_ant"]
                if ant is not None and ant != color and ahora - self._c2["t_ultimo_cambio"] > 3:
                    self._c2["t_ultimo_cambio"] = ahora
                    self._procesar_vela_canal2(color)
                self._c2["color_vela_ant"] = color
                _err2 = 0
            except Exception as e:
                _err2 += 1
                try:
                    self.app.log(f"[Canal2] ⚠ Error #{_err2}: {type(e).__name__}: {e}")
                except Exception:
                    pass
                if _err2 == 3:
                    self._c2["color_vela_ant"] = None
                    self.app.log("[AutoSanacion] Canal2-L1: estado reseteado.")
                    time.sleep(2)
                elif _err2 == 6:
                    self.app.log("[AutoSanacion] Canal2-L2: canal pausado 20s.")
                    time.sleep(20)
                elif _err2 >= 10:
                    self.app.log("[AutoSanacion] Canal2-L3: demasiados errores — canal detenido.")
                    try:
                        self.app.decir(self.app.txt(
                            "El canal dos presenta errores repetidos y se ha suspendido.",
                            "Channel two has repeated errors and has been suspended."))
                    except Exception:
                        pass
                    break

    def _procesar_vela_canal2(self, color: str) -> None:
        a    = self.app
        sec2 = a.mem["secuencia_2"]

        acierto = self.app.analizador2.verificar_pendiente(color)
        if acierto is not None:
            try:
                a.red.registrar_resultado(acierto, sec2)
            except Exception:
                pass

            res_str  = "WIN" if acierto else "LOSS"
            fue_real = self._c2["trade_ejecutado"]
            self._c2["trade_ejecutado"] = False

            if fue_real:
                try:
                    practica = getattr(a, "modo_practica", None)
                    if practica and practica.activo:
                        practica.registrar_resultado(acierto)
                except Exception:
                    pass
                try:
                    profesional = getattr(a, "modo_profesional", None)
                    if profesional and profesional.activo:
                        profesional.registrar_resultado(acierto, kelly=self._c2["trade_kelly"])
                except Exception:
                    pass
                try:
                    meta = getattr(a, "meta_diaria", None)
                    _pract_c2 = getattr(a, "modo_practica", None)
                    if meta and meta.activa and not bool(_pract_c2 and _pract_c2.activo):
                        payout = (getattr(a, "broker", None).perfil.get("payout", 0.85)
                                  if hasattr(a, "broker") else 0.85)
                        meta.registrar_resultado(
                            acierto, monto=self._c2["trade_monto"], payout=payout)
                except Exception:
                    pass
                a.log(f"[Canal2] {res_str} | dir={self._c2['trade_dir']} "
                      f"patron='{self._c2['trade_patron']}'")
            else:
                a.log(f"[Canal2] {res_str} (señal sin trade real — solo aprendizaje)")

            self._c2["hist_rolling"].append(res_str)
            if len(self._c2["hist_rolling"]) > 30:
                self._c2["hist_rolling"] = self._c2["hist_rolling"][-30:]

            _asset_c2   = str(a.mem.get("config", {}).get("asset", ""))
            _periodo_c2 = int(a.mem.get("config", {}).get("periodo_vela", 60))
            try:
                self.fdb.registrar(
                    patron      = self._c2["trade_patron"] or "?",
                    direccion   = self._c2["trade_dir"] or "?",
                    votos       = self._c2["trade_votos"],
                    prob        = self._c2["trade_prob"],
                    indicadores = self._c2["rl_ind_ant"] or self._c2["ultimo_ind"],
                    resultado   = res_str,
                    velas_seq   = list(sec2),
                    asset       = _asset_c2,
                    periodo     = _periodo_c2,
                )

                # El freno diario cuenta EN DINERO, no en número de
                # operaciones: perder 5 de 50 no es perder 5 de 2.000.
                # Se anota aquí, al conocer el resultado — una operación
                # abierta todavía no ha costado nada.
                try:
                    from . import freno_diario as _fdia
                    _fdia.anotar(a, str(res_str).upper() in ("WIN", "GANO"))
                except Exception:
                    pass
            except Exception as e:
                a.log(f"[Canal2] FalloDB error: {e}")
            try:
                self._session_tracker.registrar(
                    resultado = res_str,
                    votos     = self._c2["trade_votos"])
            except Exception:
                pass
            try:
                _monto_c2  = float(a.mem.get("config", {}).get("monto", 1.0))
                _payout_c2 = float(getattr(self, "_ultimo_payout", 0.85))
                self._perf.registrar(
                    resultado = res_str,
                    monto     = _monto_c2,
                    payout    = _payout_c2,
                    votos     = self._c2["trade_votos"],
                    asset     = _asset_c2,
                    regimen   = str(getattr(self, "_ultimo_regimen", "")),
                )
            except Exception:
                pass

            # Actualizar calibrador con las confianzas reales de canal2
            try:
                if getattr(self, "_votos_pend_cal_2", None):
                    for _m, (_prob, _confirmó) in self._votos_pend_cal_2.items():
                        self.calibrador.registrar(
                            _m, acierto if _confirmó else not acierto, _prob,
                            asset=_asset_c2, periodo=_periodo_c2)
                    self._votos_pend_cal_2 = None
            except Exception:
                pass

            if self._c2["rl_seq_ant"] is not None and self._c2["rl_accion"] != AgenteRL.ACCION_SKIP:
                reward = 1.0 if acierto else -1.0
                try:
                    _dd_c2 = float(profesional.stats().get("dd_actual", 0.0)) if profesional else 0.0
                    _kz_c2 = bool(self._ultimo_smc.get("en_kz", False))
                    self.rl.aprender(
                        self._c2["rl_seq_ant"], self._c2["rl_accion"], reward, list(sec2),
                        ind_ant=self._c2["rl_ind_ant"], ind_nuevo=self._c2["ultimo_ind"],
                        en_killzone=_kz_c2, dd_pct=_dd_c2)
                except Exception as e_rl:
                    a.log(f"[Canal2] RL error: {e_rl}")
                self._c2["rl_seq_ant"] = None
                self._c2["rl_accion"]  = AgenteRL.ACCION_SKIP

        self.app.analizador2.registrar_vela(color)
        try:
            if a.red.quizas_reentrenar(sec2):
                a.log("[Canal2] Red neuronal reentrenada con datos del canal 2.")
        except Exception:
            pass

        try:
            self._evaluar_y_operar_canal2()
        except Exception as _ec2:
            self.app.log(f"[Canal2] Error en evaluación (no crítico): {_ec2}")

    def _senal_estadistica_fallback_canal2(self, sec):
        try:
            voto = estadistica.analizar(sec)
        except Exception:
            return None
        umbral = 0.51 if len(sec) < 10 else 0.53
        if not voto or voto.get("confianza", 0) < umbral:
            return None
        senal = {
            "patron":        "estadistica_fallback",
            "direccion":     voto.get("candidata", "V"),
            "probabilidad":  voto.get("confianza", 0.53),
            "observaciones": 0,
            "hora":          time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.app.analizador2.senal_pendiente = senal
        return senal

    def _evaluar_y_operar_canal2(self) -> None:
        a   = self.app
        sec = a.mem["secuencia_2"]
        if len(sec) < 3:
            return
        senal = self.app.analizador2.evaluar()
        if not senal:
            senal = self._senal_estadistica_fallback_canal2(sec)
        if not senal:
            return
        dir_sen, votos, prob, decision, patron = self._calcular_consenso_canal2(senal, sec)
        a.log(f"[Canal2] SENAL {'SUBE' if dir_sen == 'V' else 'BAJA'} | {_safe_pct(prob)}% | "
              f"{votos}/11 votos | Bayes {'ACTUAR' if decision['actuar'] else 'esperar'}")
        self._ejecutar_si_consenso_canal2(dir_sen, votos, decision, patron=patron)

    def _calcular_consenso_canal2(self, senal, sec):
        """Réplica del consenso de 9 motores para el canal 2 — mismos motores
        compartidos (red, RL, FalloDB) pero contexto/bookkeeping propio."""
        a       = self.app
        dir_sen = senal["direccion"]
        patron  = senal.get("patron", "?")

        voto       = {}
        confirma_e = False
        try:
            voto       = estadistica.analizar(sec) or {}
            confirma_e = voto.get("candidata") == dir_sen
        except Exception:
            pass

        # Red Maestra via pool (NO síncrona) — igual que Canal 1, con timeout adaptativo
        _res_red2_holder = [{}]
        def _run_red2():
            try:
                _res_red2_holder[0] = (a.red.predecir_completo(sec)
                                       if hasattr(a.red, "predecir_completo") else {})
            except Exception:
                pass
        _es_blitz2 = int(a.mem["config"].get("periodo_vela", 60)) <= 15
        _f_red2 = self._executor.submit(_run_red2)

        pron       = {}
        confirma_p = False
        conf_pron  = 0.0
        try:
            pron       = pronostico.analizar(sec) or {}
            confirma_p = pron.get("candidata") == dir_sen
            conf_pron  = pron.get("confianza", 0.0)
        except Exception:
            pass

        ind_res    = None
        confirma_i = False
        conf_ind   = 0.0
        try:
            ind_res = ind_mod.evaluar_senal(sec)
        except Exception:
            pass
        if ind_res:
            confirma_i = ind_res.get("candidata") == dir_sen
            conf_ind   = ind_res.get("confianza", 0.0)
            det = ind_res.get("detalle", {})
            self._c2["ultimo_ind"] = {
                "rsi":     det.get("rsi"),
                "macd_h":  det.get("macd_h"),
                "bb":      det.get("bb"),
                "stoch_k": det.get("stoch_k"),
                "wr":      det.get("wr"),
                "mom":     det.get("mom"),
                "hurst":         ind_res.get("hurst"),
                "entropia_perm": ind_res.get("entropia"),
            }

        # Colectar Red Maestra canal 2 — 15ms Blitz, 100ms normal
        _red2_to = 0.015 if _es_blitz2 else 0.100
        try:
            _f_red2.result(timeout=_red2_to)
        except Exception:
            pass
        res_red  = _res_red2_holder[0]
        dir_red  = res_red.get("direccion") if res_red.get("entrenada") else None
        if dir_red is None:
            try:
                dir_red, _ = a.red.predecir(sec)
            except Exception:
                dir_red = None
        confirma_r = dir_red == dir_sen
        prob_red   = res_red.get("probabilidad", 0.5)
        if not np.isfinite(prob_red):
            prob_red = 0.5

        # RL y SMC via pool — igual que en canal 1
        _rl2_holder  = [AgenteRL.ACCION_SKIP, 0.0]
        _smc2_holder = [{}]

        def _run_rl2():
            try:
                ac, cf, _ = self.rl.decidir_con_confianza(sec, self._c2["ultimo_ind"])
                _rl2_holder[0] = ac
                _rl2_holder[1] = cf
            except Exception:
                pass

        def _run_smc2():
            try:
                _smc2_holder[0] = _smc.analizar_completo(sec, self._c2["ultimo_ind"])
            except Exception:
                pass

        _to_c2  = 0.025 if _es_blitz2 else 0.055
        _f_rl2  = self._executor.submit(_run_rl2)
        _f_smc2 = self._executor.submit(_run_smc2)
        try:
            _f_rl2.result(timeout=_to_c2)
        except Exception:
            pass
        try:
            _f_smc2.result(timeout=_to_c2)
        except Exception:
            pass

        accion_rl   = _rl2_holder[0]
        conf_rl     = _rl2_holder[1]
        confirma_rl = (
            (accion_rl == AgenteRL.ACCION_SUBE and dir_sen == "V") or
            (accion_rl == AgenteRL.ACCION_BAJA and dir_sen == "R"))

        smc_res      = _smc2_holder[0]
        confirma_smc = (smc_res.get("votar", False) and smc_res.get("dir") == dir_sen)
        if smc_res:
            self._c2["ultimo_smc"] = smc_res

        try:
            _pw2 = self.calibrador.pesos_actuales()
        except Exception:
            _pw2 = {}

        conf_markov = float(np.clip(senal.get("probabilidad", 0.55), 0.5, 1.0))
        conf_estat  = float(np.clip(voto.get("confianza", 0.53), 0.5, 1.0))
        conf_red    = float(np.clip(abs(prob_red - 0.5) * 2.0, 0.0, 1.0)) if confirma_r else 0.0
        conf_pron_n = float(np.clip(conf_pron, 0.0, 1.0))
        conf_ind_n  = float(np.clip(conf_ind,  0.0, 1.0))
        conf_rl_n   = float(np.clip(conf_rl,   0.0, 1.0))
        conf_smc_n  = float(np.clip(smc_res.get("confianza", 0.6), 0.0, 1.0)) if confirma_smc else 0.0

        voto_markov = conf_markov              * _pw2.get("markov",      1.0)
        voto_estat  = (conf_estat              * _pw2.get("estadist",    1.0)
                       if confirma_e else (1.0 - conf_estat) * 0.3)
        voto_red    = max(conf_red, 0.5)       * _pw2.get("red",         1.0) if confirma_r  else 0.0
        voto_pron   = conf_pron_n              * _pw2.get("pronostico",  1.0) if confirma_p  else 0.0
        voto_ind    = conf_ind_n               * _pw2.get("indicadores", 1.0) if confirma_i  else 0.0
        voto_rl     = conf_rl_n                * _pw2.get("rl",          1.0) if confirma_rl else 0.0
        voto_smc    = conf_smc_n               * _pw2.get("smc",         1.0) if confirma_smc else 0.0

        votos_pond = float(np.nansum([voto_markov, voto_estat, voto_red,
                                       voto_pron, voto_ind, voto_rl, voto_smc]))
        votos      = int(round(votos_pond))

        est    = a.mem["estadisticas_2"]
        tot    = est.get("aciertos", 0) + est.get("fallos", 0)
        prec_m = est.get("aciertos", 0) / tot if tot else 0.5
        prec_r = a.red.precision_aprox(sec) or 0.5
        n      = len(sec)
        _wr_sesion2 = prec_m if tot >= 20 else None
        decision = inferencia.decidir(sec, [
            {"direccion": dir_sen,                    "confianza": senal["probabilidad"],
             "precision": prec_m, "n": tot},
            {"direccion": voto.get("candidata"),      "confianza": voto.get("confianza", 0.53),
             "precision": 0.55,   "n": n},
            {"direccion": dir_red,                    "confianza": abs(prob_red - 0.5) * 2.0,
             "precision": prec_r,  "n": n},
            {"direccion": pron.get("candidata"),      "confianza": conf_pron,
             "precision": 0.54,   "n": n},
        ], wr_sesion=_wr_sesion2)

        # Guardar confianzas + flag de dirección para el calibrador (canal 2)
        self._votos_pend_cal_2 = {
            "markov":      (float(conf_markov), True),
            "estadist":    (float(conf_estat),  bool(confirma_e)),
            "red":         (float(abs(prob_red - 0.5) * 2.0), bool(confirma_r)),
            "pronostico":  (float(conf_pron),   bool(confirma_p)),
            "indicadores": (float(conf_ind),    bool(confirma_i)),
            "rl":          (float(conf_rl),     bool(confirma_rl)),
            "smc":         (float(smc_res.get("confianza", 0.5) if smc_res else 0.5), bool(confirma_smc)),
        }

        return dir_sen, votos, senal["probabilidad"], decision, patron

    def _ejecutar_si_consenso_canal2(self, dir_sen, votos, decision, patron: str = "?") -> None:
        a           = self.app
        if _motor_iq_debe_callar(a):     # ver el portero del canal 1
            return
        practica    = getattr(a, "modo_practica",    None)
        profesional = getattr(a, "modo_profesional", None)
        _en_practica = bool(practica    and practica.activo)
        _en_pro      = bool(profesional and profesional.activo) and not _en_practica
        autonomo_ok  = (a.autoclick_on and a.modo_autonomo)

        if not (_en_practica or _en_pro or autonomo_ok):
            return   # canal 2 no opera fuera de Practica/Pro/Autonomo (sin shadow hover)

        if votos < 3:   # piso absoluto — igual que canal 1
            return

        meta = getattr(a, "meta_diaria", None)
        if meta and not _en_practica:
            puede_meta, _r = meta.puede_tradear()
            if not puede_meta:
                return

        if not _en_practica and self._en_pausa():
            return   # misma pausa global anti-martingala (no aplica en Practica)

        prob_bayes  = decision.get("probabilidad", 0.5)
        sec2        = a.mem["secuencia_2"]
        n_velas     = len(sec2)
        aprendiendo = n_velas < 30

        est        = a.mem["estadisticas_2"]
        tot_trades = est.get("aciertos", 0) + est.get("fallos", 0)
        p_win      = est.get("aciertos", 0) / tot_trades if tot_trades >= 10 else prob_bayes
        kelly_f    = _kelly(p_win)

        if _en_practica:
            puede, _r = practica.puede_ejecutar(votos, prob_bayes)
            if not puede:
                return
        elif _en_pro:
            puede, _r = profesional.puede_ejecutar(votos, prob_bayes, kelly_f)
            if not puede:
                return
            if self.fdb.es_patron_problematico(patron) and n_velas >= 30:
                return
        else:
            if self.fdb.es_patron_problematico(patron) and n_velas >= 50:
                return
            min_votos = self._min_votos_adaptativo(aprendiendo, hist=self._c2["hist_rolling"])
            if votos < min_votos:
                return
            bayes_ok = decision.get("actuar") or (aprendiendo and prob_bayes > 0.52)
            if not bayes_ok:
                return
            ahora    = time.time()
            periodo  = int(a.mem["config"].get("periodo_vela", 60))
            cooldown = max(5, min(_COOLDOWN_CLICK, periodo - 4))
            if ahora - self._c2["ultimo_click_t"] < cooldown:
                return

        try:
            a.red.registrar_prediccion(sec2, dir_sen)
        except Exception:
            pass

        self._c2["rl_seq_ant"]   = list(sec2)
        self._c2["rl_accion"]    = (AgenteRL.ACCION_SUBE if dir_sen == "V"
                                    else AgenteRL.ACCION_BAJA)
        self._c2["rl_ind_ant"]   = dict(self._c2["ultimo_ind"])
        self._c2["trade_patron"] = patron
        self._c2["trade_dir"]    = dir_sen
        self._c2["trade_votos"]  = votos
        self._c2["trade_prob"]   = prob_bayes
        self._c2["trade_kelly"]  = kelly_f
        self._c2["trade_monto"]  = float(a.mem["config"].get("monto_base", 10.0))

        prefijo = ("[Canal2/PRACTICA]" if _en_practica else
                   "[Canal2/PRO]" if _en_pro else "[Canal2]")
        a.log(f"{prefijo} {'SUBE' if dir_sen == 'V' else 'BAJA'} | {votos}/11 votos | "
              f"p={prob_bayes:.2f} | Kelly={kelly_f:.3f}")

        self._c2["trade_ejecutado"] = self._ejecutar_click_canal2(dir_sen)
        if self._c2["trade_ejecutado"]:
            self._c2["ultimo_click_t"] = time.time()
            if _en_practica:
                practica.registrar_click()
            elif _en_pro:
                profesional.registrar_click()
        else:
            a.log("[Canal2] Click FALLIDO — trade no registrado.")

    def _ejecutar_click_canal2(self, direccion) -> bool:
        if not _PG_OK:
            return False
        cfg    = self.app.mem["config"]
        clave  = "boton_verde_2" if direccion == "V" else "boton_rojo_2"
        coords = cfg.get(clave)
        if not coords:
            self.app.log("[Canal2] Boton no calibrado para el segundo grafico.")
            return False
        dir_txt = "SUBE" if direccion == "V" else "BAJA"
        try:
            periodo = int(self.app.mem["config"].get("periodo_vela", 60))
            manos.click_trade(coords[0], coords[1], periodo)
            self.app.log(f"▶ [CLICK Canal2] {dir_txt} ({coords[0]}, {coords[1]})")
            # Aparcar cursor en background — no bloquea canal 2
            manos.aparcar_cursor_async(
                self.app.mem["config"].get("region_grafico_2"), periodo)
            return True
        except Exception as e:
            self.app.log(f"[Canal2] Error al hacer click: {e}")
            return False

    # ── Canales extra genéricos (3, 4, …) — un solo bucle parametrizado ─────

    def _loop_canal_extra(self, n: int) -> None:
        """Bucle principal para Canal N (n ∈ {3, 4, …}).
        Misma lógica que Canal 2 pero completamente parametrizada."""
        cn = {
            "color_vela_ant":  None, "t_ultimo_cambio": 0.0,
            "ultimo_click_t":  0.0,  "trade_ejecutado": False,
            "rl_seq_ant":  None,     "rl_accion": AgenteRL.ACCION_SKIP,
            "rl_ind_ant":  {},       "ultimo_ind": {},
            "ultimo_smc":  {},       "hist_rolling": [],
            "trade_patron": "",      "trade_dir": "",
            "trade_votos":  0,       "trade_prob": 0.5,
            "trade_kelly":  0.0,     "trade_monto": 10.0,
        }
        kcfg  = f"region_grafico_{n}"
        _errn = 0
        while not self._detener:
            periodo = int(self.app.mem["config"].get("periodo_vela", 60))
            time.sleep(max(0.25, min(1.5, periodo / 40.0)))
            try:
                a = self.app
                if not (a.activo and a.trading_on):
                    _errn = 0
                    continue
                region = a.mem["config"].get(kcfg)
                if not region:
                    continue
                color = vision.color_vela(region)
                if color is None:
                    continue
                ahora = time.time()
                ant   = cn["color_vela_ant"]
                if ant is not None and ant != color and ahora - cn["t_ultimo_cambio"] > 3:
                    cn["t_ultimo_cambio"] = ahora
                    self._procesar_vela_extra(n, cn, color)
                cn["color_vela_ant"] = color
                _errn = 0
            except Exception as e:
                _errn += 1
                try:
                    self.app.log(f"[Canal{n}] ⚠ Error #{_errn}: {type(e).__name__}: {e}")
                except Exception:
                    pass
                if _errn == 3:
                    cn["color_vela_ant"] = None
                    self.app.log(f"[AutoSanacion] Canal{n}-L1: estado reseteado.")
                    time.sleep(2)
                elif _errn == 6:
                    self.app.log(f"[AutoSanacion] Canal{n}-L2: canal pausado 20s.")
                    time.sleep(20)
                elif _errn >= 10:
                    self.app.log(f"[AutoSanacion] Canal{n}-L3: demasiados errores — canal detenido.")
                    try:
                        self.app.decir(self.app.txt(
                            f"El canal {n} presenta errores repetidos y se ha suspendido.",
                            f"Channel {n} has repeated errors and has been suspended."))
                    except Exception:
                        pass
                    break

    def _procesar_vela_extra(self, n: int, cn: dict, color: str) -> None:
        a    = self.app
        tag  = f"[Canal{n}]"
        secn = a.mem.setdefault(f"secuencia_{n}", [])
        analizador = getattr(a, f"analizador{n}", None)
        if analizador is None:
            return

        acierto = analizador.verificar_pendiente(color)
        if acierto is not None:
            try:
                a.red.registrar_resultado(acierto, secn)
            except Exception:
                pass
            res_str  = "WIN" if acierto else "LOSS"
            fue_real = cn["trade_ejecutado"]
            cn["trade_ejecutado"] = False

            if fue_real:
                try:
                    practica = getattr(a, "modo_practica", None)
                    if practica and practica.activo:
                        practica.registrar_resultado(acierto)
                except Exception:
                    pass
                try:
                    profesional = getattr(a, "modo_profesional", None)
                    if profesional and profesional.activo:
                        profesional.registrar_resultado(acierto, kelly=cn["trade_kelly"])
                except Exception:
                    pass
                try:
                    meta = getattr(a, "meta_diaria", None)
                    _pract_cx = getattr(a, "modo_practica", None)
                    if meta and meta.activa and not bool(_pract_cx and _pract_cx.activo):
                        payout = (getattr(a, "broker", None).perfil.get("payout", 0.85)
                                  if hasattr(a, "broker") else 0.85)
                        meta.registrar_resultado(
                            acierto, monto=cn["trade_monto"], payout=payout)
                except Exception:
                    pass
                a.log(f"{tag} {'WIN' if acierto else 'LOSS'} | dir={cn['trade_dir']} "
                      f"patron='{cn['trade_patron']}'")
            else:
                a.log(f"{tag} {res_str} (señal sin trade real — solo aprendizaje)")

            cn["hist_rolling"].append(res_str)
            if len(cn["hist_rolling"]) > 30:
                cn["hist_rolling"] = cn["hist_rolling"][-30:]

            try:
                self.fdb.registrar(
                    patron      = cn["trade_patron"] or "?",
                    direccion   = cn["trade_dir"] or "?",
                    votos       = cn["trade_votos"],
                    prob        = cn["trade_prob"],
                    indicadores = cn["rl_ind_ant"] or cn["ultimo_ind"],
                    resultado   = res_str,
                    velas_seq   = list(secn),
                )

                # El freno diario cuenta EN DINERO, no en número de
                # operaciones: perder 5 de 50 no es perder 5 de 2.000.
                # Se anota aquí, al conocer el resultado — una operación
                # abierta todavía no ha costado nada.
                try:
                    from . import freno_diario as _fdia
                    _fdia.anotar(a, str(res_str).upper() in ("WIN", "GANO"))
                except Exception:
                    pass
            except Exception as e:
                a.log(f"{tag} FalloDB error: {e}")

            if cn["rl_seq_ant"] is not None and cn["rl_accion"] != AgenteRL.ACCION_SKIP:
                reward = 1.0 if acierto else -1.0
                try:
                    _dd_cn = float(profesional.stats().get("dd_actual", 0.0)) if profesional else 0.0
                    _kz_cn = bool(self._ultimo_smc.get("en_kz", False))
                    self.rl.aprender(
                        cn["rl_seq_ant"], cn["rl_accion"], reward, list(secn),
                        ind_ant=cn["rl_ind_ant"], ind_nuevo=cn["ultimo_ind"],
                        en_killzone=_kz_cn, dd_pct=_dd_cn)
                except Exception as e_rl:
                    a.log(f"{tag} RL error: {e_rl}")
                cn["rl_seq_ant"] = None
                cn["rl_accion"]  = AgenteRL.ACCION_SKIP

        analizador.registrar_vela(color)
        try:
            if a.red.quizas_reentrenar(secn):
                a.log(f"{tag} Red neuronal reentrenada con datos del canal {n}.")
        except Exception:
            pass

        if len(secn) < 3:
            return
        senal = analizador.evaluar()
        if not senal:
            try:
                voto = estadistica.analizar(secn) or {}
            except Exception:
                voto = {}
            umbral = 0.51 if len(secn) < 10 else 0.53
            if voto and voto.get("confianza", 0) >= umbral:
                senal = {
                    "patron":        "estadistica_fallback",
                    "direccion":     voto.get("candidata", "V"),
                    "probabilidad":  voto.get("confianza", 0.53),
                    "observaciones": 0,
                    "hora":          time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                analizador.senal_pendiente = senal
        if not senal:
            return

        dir_sen, votos, prob, decision, patron = self._consenso_extra(n, cn, senal, secn)
        a.log(f"{tag} SENAL {'SUBE' if dir_sen == 'V' else 'BAJA'} | {_safe_pct(prob)}% | "
              f"{votos}/11 votos | Bayes {'ACTUAR' if decision['actuar'] else 'esperar'}")
        self._ejecutar_si_extra(n, cn, dir_sen, votos, decision, patron=patron)

    def _consenso_extra(self, n: int, cn: dict, senal: dict, sec: list):
        """Votación 9-motores para Canal N — modelos compartidos con Canal 1 y 2."""
        a       = self.app
        dir_sen = senal["direccion"]
        patron  = senal.get("patron", "?")

        voto       = {}
        confirma_e = False
        try:
            voto       = estadistica.analizar(sec) or {}
            confirma_e = voto.get("candidata") == dir_sen
        except Exception:
            pass

        res_red = {}
        try:
            res_red = a.red.predecir_completo(sec) if hasattr(a.red, "predecir_completo") else {}
        except Exception:
            pass
        dir_red = res_red.get("direccion") if res_red.get("entrenada") else None
        if dir_red is None:
            try:
                dir_red, _ = a.red.predecir(sec)
            except Exception:
                dir_red = None
        confirma_r = dir_red == dir_sen
        prob_red   = res_red.get("probabilidad", 0.5)
        if not np.isfinite(prob_red):
            prob_red = 0.5

        pron       = {}
        confirma_p = False
        conf_pron  = 0.0
        try:
            pron       = pronostico.analizar(sec) or {}
            confirma_p = pron.get("candidata") == dir_sen
            conf_pron  = pron.get("confianza", 0.0)
        except Exception:
            pass

        ind_res    = None
        confirma_i = False
        conf_ind   = 0.0
        try:
            ind_res = ind_mod.evaluar_senal(sec)
        except Exception:
            pass
        if ind_res:
            confirma_i = ind_res.get("candidata") == dir_sen
            conf_ind   = ind_res.get("confianza", 0.0)
            det = ind_res.get("detalle", {})
            cn["ultimo_ind"] = {
                "rsi":     det.get("rsi"),
                "macd_h":  det.get("macd_h"),
                "bb":      det.get("bb"),
                "stoch_k": det.get("stoch_k"),
                "wr":      det.get("wr"),
                "mom":     det.get("mom"),
                "hurst":         ind_res.get("hurst"),
                "entropia_perm": ind_res.get("entropia"),
            }

        # RL y SMC en paralelo — igual que en canales 1 y 2
        _rlx_holder  = [AgenteRL.ACCION_SKIP, 0.0]
        _smcx_holder = [{}]

        def _run_rlx():
            try:
                ac, cf, _ = self.rl.decidir_con_confianza(sec, cn["ultimo_ind"])
                _rlx_holder[0] = ac
                _rlx_holder[1] = cf
            except Exception:
                pass

        def _run_smcx():
            try:
                _smcx_holder[0] = _smc.analizar_completo(sec, cn["ultimo_ind"])
            except Exception:
                pass

        _t_rlx  = threading.Thread(target=_run_rlx,  daemon=True, name=f"VotoRL_C{n}")
        _t_smcx = threading.Thread(target=_run_smcx, daemon=True, name=f"VotoSMC_C{n}")
        _t_rlx.start()
        _t_smcx.start()
        _t_rlx.join(timeout=0.055)
        _t_smcx.join(timeout=0.055)

        accion_rl   = _rlx_holder[0]
        conf_rl     = _rlx_holder[1]
        confirma_rl = (
            (accion_rl == AgenteRL.ACCION_SUBE and dir_sen == "V") or
            (accion_rl == AgenteRL.ACCION_BAJA and dir_sen == "R"))

        smc_res      = _smcx_holder[0]
        confirma_smc = (smc_res.get("votar", False) and smc_res.get("dir") == dir_sen)
        if smc_res:
            cn["ultimo_smc"] = smc_res

        try:
            _pwx = self.calibrador.pesos_actuales()
        except Exception:
            _pwx = {}

        conf_markov = float(np.clip(senal.get("probabilidad", 0.55), 0.5, 1.0))
        conf_estat  = float(np.clip(voto.get("confianza", 0.53), 0.5, 1.0))
        conf_red    = float(np.clip(abs(prob_red - 0.5) * 2.0, 0.0, 1.0)) if confirma_r else 0.0
        conf_pron_n = float(np.clip(conf_pron, 0.0, 1.0))
        conf_ind_n  = float(np.clip(conf_ind,  0.0, 1.0))
        conf_rl_n   = float(np.clip(conf_rl,   0.0, 1.0))
        conf_smc_n  = float(np.clip(smc_res.get("confianza", 0.6), 0.0, 1.0)) if confirma_smc else 0.0

        voto_markov = conf_markov              * _pwx.get("markov",      1.0)
        voto_estat  = (conf_estat              * _pwx.get("estadist",    1.0)
                       if confirma_e else (1.0 - conf_estat) * 0.3)
        voto_red    = max(conf_red, 0.5)       * _pwx.get("red",         1.0) if confirma_r  else 0.0
        voto_pron   = conf_pron_n              * _pwx.get("pronostico",  1.0) if confirma_p  else 0.0
        voto_ind    = conf_ind_n               * _pwx.get("indicadores", 1.0) if confirma_i  else 0.0
        voto_rl     = conf_rl_n                * _pwx.get("rl",          1.0) if confirma_rl else 0.0
        voto_smc    = conf_smc_n               * _pwx.get("smc",         1.0) if confirma_smc else 0.0

        votos_pond = float(np.nansum([voto_markov, voto_estat, voto_red,
                                       voto_pron, voto_ind, voto_rl, voto_smc]))
        votos      = int(round(votos_pond))

        est    = a.mem.get(f"estadisticas_{n}", {})
        tot    = est.get("aciertos", 0) + est.get("fallos", 0)
        prec_m = est.get("aciertos", 0) / tot if tot else 0.5
        prec_r = a.red.precision_aprox(sec) or 0.5
        nl     = len(sec)
        _wr_sesion3 = prec_m if tot >= 20 else None
        decision = inferencia.decidir(sec, [
            {"direccion": dir_sen,                    "confianza": senal["probabilidad"],
             "precision": prec_m, "n": tot},
            {"direccion": voto.get("candidata"),      "confianza": voto.get("confianza", 0.53),
             "precision": 0.55,   "n": nl},
            {"direccion": dir_red,                    "confianza": abs(prob_red - 0.5) * 2.0,
             "precision": prec_r,  "n": nl},
            {"direccion": pron.get("candidata"),      "confianza": conf_pron,
             "precision": 0.54,   "n": nl},
        ], wr_sesion=_wr_sesion3)

        return dir_sen, votos, senal["probabilidad"], decision, patron

    def _ejecutar_si_extra(self, n: int, cn: dict, dir_sen: str, votos: int,
                           decision: dict, patron: str = "?") -> None:
        a            = self.app
        if _motor_iq_debe_callar(a):     # ver el portero del canal 1
            return
        tag          = f"[Canal{n}]"
        practica     = getattr(a, "modo_practica",    None)
        profesional  = getattr(a, "modo_profesional", None)
        _en_practica = bool(practica    and practica.activo)
        _en_pro      = bool(profesional and profesional.activo) and not _en_practica
        autonomo_ok  = (a.autoclick_on and a.modo_autonomo)

        if not (_en_practica or _en_pro or autonomo_ok):
            return

        meta = getattr(a, "meta_diaria", None)
        if meta and not _en_practica:
            puede_meta, _r = meta.puede_tradear()
            if not puede_meta:
                return

        if not _en_practica and self._en_pausa():
            return

        prob_bayes  = decision.get("probabilidad", 0.5)
        secn        = a.mem.get(f"secuencia_{n}", [])
        n_velas     = len(secn)
        aprendiendo = n_velas < 30

        est        = a.mem.get(f"estadisticas_{n}", {})
        tot_trades = est.get("aciertos", 0) + est.get("fallos", 0)
        p_win      = est.get("aciertos", 0) / tot_trades if tot_trades >= 10 else prob_bayes
        kelly_f    = _kelly(p_win)

        if _en_practica:
            puede, _r = practica.puede_ejecutar(votos, prob_bayes)
            if not puede:
                return
        elif _en_pro:
            puede, _r = profesional.puede_ejecutar(votos, prob_bayes, kelly_f)
            if not puede:
                return
            if self.fdb.es_patron_problematico(patron) and n_velas >= 30:
                return
        else:
            if self.fdb.es_patron_problematico(patron) and n_velas >= 50:
                return
            min_votos = self._min_votos_adaptativo(aprendiendo, hist=cn["hist_rolling"])
            if votos < min_votos:
                return
            bayes_ok = decision.get("actuar") or (aprendiendo and prob_bayes > 0.52)
            if not bayes_ok:
                return
            ahora    = time.time()
            periodo  = int(a.mem["config"].get("periodo_vela", 60))
            cooldown = max(5, min(_COOLDOWN_CLICK, periodo - 4))
            if ahora - cn["ultimo_click_t"] < cooldown:
                return

        try:
            a.red.registrar_prediccion(secn, dir_sen)
        except Exception:
            pass

        # ── Consulta al Grafo de Conocimiento ────────────────────────────────
        _grafo_prob = None
        if _GRAFO_OK and _grafo is not None:
            try:
                import time as _ti_gq
                _ctx_q = {
                    "patron":     patron or "",
                    "regimen":    cn.get("ultimo_ind", {}).get("regime", ""),
                    "hora":       str(int(_ti_gq.strftime("%H"))),
                    "activo":     a.mem.get("config", {}).get("asset_actual", ""),
                    "votos":      str(votos),
                    "sesion":     (self._session_tracker.sesion_actual()
                                   if hasattr(self, "_session_tracker") else ""),
                }
                _grafo_prob = _grafo.probabilidad_contextual(_ctx_q)
                # Bloquear si el grafo indica alta probabilidad de pérdida
                if _grafo_prob < 0.42 and votos < 6:
                    a.log(f"[Grafo] Contexto desfavorable ({_grafo_prob:.0%}) — omitiendo señal {votos}/9")
                    return
                if _grafo_prob >= 0.65:
                    a.log(f"[Grafo] Contexto favorable {_grafo_prob:.0%} — señal reforzada")
            except Exception:
                pass

        cn["rl_seq_ant"]   = list(secn)
        cn["rl_accion"]    = (AgenteRL.ACCION_SUBE if dir_sen == "V"
                              else AgenteRL.ACCION_BAJA)
        cn["rl_ind_ant"]   = dict(cn["ultimo_ind"])
        cn["trade_patron"] = patron
        cn["trade_dir"]    = dir_sen
        cn["trade_votos"]  = votos
        cn["trade_prob"]   = prob_bayes
        cn["trade_kelly"]  = kelly_f
        cn["trade_monto"]  = float(a.mem["config"].get("monto_base", 10.0))

        base_tag = f"Canal{n}"
        prefijo  = (f"[{base_tag}/PRACTICA]" if _en_practica else
                    f"[{base_tag}/PRO]"       if _en_pro      else f"[{base_tag}]")
        _grafo_tag = (f" | Grafo={_grafo_prob:.0%}" if _grafo_prob is not None else "")
        a.log(f"{prefijo} {'SUBE' if dir_sen == 'V' else 'BAJA'} | {votos}/11 votos | "
              f"p={prob_bayes:.2f} | Kelly={kelly_f:.3f}{_grafo_tag}")

        cn["trade_ejecutado"] = self._click_extra(n, cn, dir_sen)
        if cn["trade_ejecutado"]:
            cn["ultimo_click_t"] = time.time()
            if _en_practica:
                practica.registrar_click()
            elif _en_pro:
                profesional.registrar_click()
        else:
            a.log(f"{tag} Click FALLIDO — trade no registrado.")

    def _click_extra(self, n: int, cn: dict, direccion: str) -> bool:
        if not _PG_OK:
            return False
        a      = self.app
        cfg    = a.mem["config"]
        clave  = f"boton_verde_{n}" if direccion == "V" else f"boton_rojo_{n}"
        coords = cfg.get(clave)
        if not coords:
            a.log(f"[Canal{n}] Boton no calibrado.")
            return False
        dir_txt = "SUBE" if direccion == "V" else "BAJA"
        try:
            manos.mover_humano(coords[0], coords[1], duracion=0.055)
            manos.click_rapido(coords[0], coords[1])
            a.log(f"▶ [CLICK Canal{n}] {dir_txt} ({coords[0]}, {coords[1]})")
            time.sleep(0.25)
            manos.aparcar_cursor(cfg.get(f"region_grafico_{n}"))
            return True
        except Exception as e:
            a.log(f"[Canal{n}] Error al hacer click: {e}")
            return False

    # ── Auto-consciencia: Litch entiende lo que hace ──────────────────────────

    def _sesion_actual(self) -> str:
        """Sesión de mercado basada en hora UTC."""
        h = time.gmtime().tm_hour
        if   7 <= h < 10:  return "apertura Londres (killzone 65-70%)"
        elif 13 <= h < 17: return "solapamiento NY-Londres (killzone 70-75%)"
        elif 10 <= h < 13: return "Londres media sesión"
        elif 17 <= h < 22: return "NY tarde"
        elif  0 <= h <  7: return "Asia — baja volatilidad"
        else:               return "transición de sesiones"

    def _contexto_indicadores(self) -> str:
        """Resumen breve del estado actual de los indicadores técnicos."""
        ind = self._ultimo_ind or {}
        p   = []

        rsi = ind.get("rsi")
        if rsi is not None:
            if   rsi < 30: p.append(f"RSI {rsi:.0f} (sobreventa extrema)")
            elif rsi < 45: p.append(f"RSI {rsi:.0f} (zona bajista)")
            elif rsi > 70: p.append(f"RSI {rsi:.0f} (sobrecompra)")
            elif rsi > 55: p.append(f"RSI {rsi:.0f} (zona alcista)")
            else:          p.append(f"RSI {rsi:.0f} (neutral)")

        macd = ind.get("macd_h")
        if macd is not None:
            p.append("MACD alcista" if macd > 0 else "MACD bajista")

        hurst = ind.get("hurst")
        if hurst is not None:
            if   hurst > 0.60: p.append(f"mercado tendencial (H={hurst:.2f})")
            elif hurst < 0.40: p.append(f"reversión a la media (H={hurst:.2f})")

        bb = ind.get("bb")
        if bb is not None:
            if   bb < -0.7: p.append("bajo banda Bollinger")
            elif bb >  0.7: p.append("sobre banda Bollinger")

        return " | ".join(p)

    def _narrar_razonamiento(self, dir_sen: str, votos: int, patron: str,
                              prob: float, p_win: float, decision: dict):
        """
        Registra POR QUÉ entra en el trade y lo narra por voz.
        LOG: análisis completo (modelos + SMC + indicadores + sesión).
        VOZ: resumen ejecutivo de 1-2 oraciones con el setup LWS.
        """
        a       = self.app
        ind     = self._ultimo_ind or {}
        smc     = self._ultimo_smc or {}
        dir_txt = "SUBIDA" if dir_sen == "V" else "BAJADA"
        sesion  = self._sesion_actual()
        ctx     = self._contexto_indicadores()

        est  = a.mem["estadisticas"]
        tot  = est.get("aciertos", 0) + est.get("fallos", 0)
        tasa = est.get("aciertos", 0) / tot * 100 if tot else 50.0

        # Construir info SMC para el log
        smc_setup = smc.get("setup", "")
        smc_narr  = smc.get("narrativa", "")
        kz        = smc.get("killzone", {})
        kz_txt    = (f"Killzone {kz.get('nombre','?')} ({kz.get('tasa','?')})"
                     if kz.get("activa") else f"fuera de killzone ({kz.get('nombre','?')})")

        # Log detallado (siempre se registra)
        a.log(
            f"[Razonamiento] {dir_txt} | patron='{patron}' | {votos}/11 modelos | "
            f"sesion={sesion} | {ctx or 'ind neutros'} | "
            f"Bayes p={_safe_pct(prob)}% | tasa_hist={tasa:.0f}% ({tot} trades)"
        )
        if smc_narr:
            a.log(f"[SMC/LWS] Setup='{smc_setup}' | {smc_narr} | {kz_txt}")

        # Contexto win-rate últimos 20 trades
        _rolling = getattr(self, "_hist_rolling", [])
        _wr20 = (sum(1 for r in _rolling[-20:] if r == "WIN") /
                 max(len(_rolling[-20:]), 1) * 100
                 if _rolling else tasa)

        # Kelly actual
        _tot_r = est.get("aciertos", 0) + est.get("fallos", 0)
        _pw    = est.get("aciertos", 0) / _tot_r if _tot_r else 0.5
        _kelly_val = _pw - (1 - _pw) / max(
            a.broker.perfil.get("payout", 0.85) if hasattr(a, "broker") else 0.85, 0.1)

        # Guardar contexto para el post-mortem
        self._razonamiento_actual = {
            "dir": dir_sen, "votos": votos, "patron": patron,
            "sesion": sesion, "prob": prob, "tasa": tasa,
            "rsi":    ind.get("rsi"), "macd": ind.get("macd_h"),
            "hurst":  ind.get("hurst"),
            "smc_setup":   smc_setup,
            "smc_bos":     smc.get("bos",   False),
            "smc_choch":   smc.get("choch", False),
            "smc_ob":      smc.get("ob",    False),
            "smc_sweep":   smc.get("sweep", False),
            "smc_en_kz":   smc.get("en_kz", False),
            # ── campos para la Conciencia ──────────────────────────────────
            "hora":       int(time.strftime("%H")),
            "dia":        int(time.strftime("%w")),
            "wr20":       _wr20,
            "kelly":      _kelly_val,
            "votos_ind":  getattr(self, "_votos_ind_actual", [1,0,0,0,0,0,0]),
            "smc_regime": ind.get("regimen") or self._ultimo_regimen or "neutral",
        }

        # Voz: resumen ejecutivo con el setup LWS
        rsi = ind.get("rsi")
        rsi_v = ""
        if rsi is not None:
            if   rsi < 35: rsi_v = f"RSI {rsi:.0f} sobreventa."
            elif rsi > 65: rsi_v = f"RSI {rsi:.0f} sobrecompra."

        smc_voz = ""
        if smc.get("bos"):
            smc_voz = "BOS confirmado."
        elif smc.get("choch"):
            smc_voz = "CHoCH detectado."
        elif smc.get("sweep"):
            smc_voz = "Sweep de liquidez."
        elif smc.get("ob"):
            smc_voz = "Order Block activo."

        kz_voz = f"Killzone {kz.get('nombre','')}." if kz.get("activa") else ""

        a.decir(a.txt(
            f"Ejecutando {'compra' if dir_sen == 'V' else 'venta'}, senor. "
            f"{votos}/11 modelos. {smc_voz} {rsi_v} {kz_voz}".strip(),
            f"Executing {'buy' if dir_sen == 'V' else 'sell'}, sir. "
            f"{votos}/9 models. {smc_voz} {rsi_v} {kz_voz}".strip()))

        # ── Fable 5: explicación técnica de la señal (background) ─────────────
        threading.Thread(
            target=self._fable5_explicar_senal,
            args=(dir_sen, votos, patron, ind, smc, sesion, prob, tasa),
            daemon=True, name="F5Señal").start()

    def _analizar_y_memorizar_error(self):
        """Análisis profundo cuando pierde — identifica el error y lo memoriza.

        Litch es consciente de sus errores: sabe qué pasó, por qué falló,
        y guarda el patrón para no repetirlo.
        """
        import os as _os
        a = self.app

        try:
            # ── Contexto del fallo ───────────────────────────────────────────
            sec      = list(a.mem.get("secuencia", []))
            dir_pred = self._trade_dir or "?"
            votos    = self._trade_votos
            patron   = self._trade_patron or "?"
            ind      = dict(self._rl_ind_ant or self._ultimo_ind)
            n_sec    = len(sec)
            ultimas5 = sec[-5:] if n_sec >= 5 else sec

            # Calcular qué tan fuerte iba la tendencia contra la señal
            opuesta   = "R" if dir_pred == "V" else "V"
            cant_cont = ultimas5.count(opuesta)
            tend_txt  = (f"{cant_cont}/{len(ultimas5)} velas iban en contra"
                         if cant_cont > 0 else "tendencia no era clara")

            rsi_val  = ind.get("rsi")
            mom_val  = self._momentum_reciente(sec, dir_pred)

            # ── Diagnóstico ──────────────────────────────────────────────────
            causas = []
            if mom_val <= -0.15:
                causas.append(f"momentum contra la señal ({mom_val:+.2f})")
            if rsi_val is not None:
                if dir_pred == "V" and rsi_val > 70:
                    causas.append(f"RSI sobrecomprado ({rsi_val:.0f}) al entrar SUBE")
                elif dir_pred == "R" and rsi_val < 30:
                    causas.append(f"RSI sobrevendido ({rsi_val:.0f}) al entrar BAJA")
            if cant_cont >= 3:
                causas.append(f"tendencia reciente fuerte en contra ({cant_cont}/5 velas)")
            if votos <= 3:
                causas.append(f"señal débil ({votos}/11 votos)")
            if not causas:
                causas.append("mercado en rango/ruido — señal válida pero resultado adverso")

            causa_txt = "; ".join(causas)
            dir_txt   = "SUBE" if dir_pred == "V" else "BAJA"

            # ── Registrar en el log de conocimiento ──────────────────────────
            msg_es = (f"Error reconocido — predicción {dir_txt} incorrecta. "
                      f"Causa: {causa_txt}. Memorizado para evitar repetirlo.")
            a.log(f"[Conciencia] ⚠ {msg_es}")

            # ── Guardar en base de conocimiento de errores ───────────────────
            from . import memoria as _mem_mod
            ruta_errores = _os.path.join(
                _mem_mod.ruta_memoria_ap(), "errores_reconocidos.jsonl")
            import json as _json, time as _tm
            entrada = {
                "ts":      _tm.strftime("%Y-%m-%d %H:%M:%S"),
                "dir":     dir_pred,
                "patron":  patron,
                "votos":   votos,
                "causas":  causas,
                "momentum": round(mom_val, 3),
                "ultimas5": ultimas5,
                "rsi":     round(rsi_val, 1) if rsi_val else None,
            }
            try:
                with open(ruta_errores, "a", encoding="utf-8") as fh:
                    fh.write(_json.dumps(entrada, ensure_ascii=False) + "\n")
            except Exception:
                pass

            # ── FalloDB ya aprende, pero también penalizamos el patrón ───────
            try:
                self.fdb.penalizar_patron(patron, causa=causa_txt)
            except Exception:
                pass

            # ── Voz de reconocimiento de error (breve, honesta) ──────────────
            def _hablar():
                try:
                    if len(causas) == 1 and "ruido" in causas[0]:
                        txt = a.txt(
                            "Perdida por ruido de mercado. Sin patron claro a evitar.",
                            "Market noise loss. No clear pattern to avoid.")
                    elif "momentum" in causa_txt:
                        txt = a.txt(
                            f"Reconozco el error: entre {dir_txt} con tendencia en contra. "
                            "No lo repetire en las mismas condiciones.",
                            f"I recognize the error: I entered {dir_txt} against the trend. "
                            "I will not repeat it under the same conditions.")
                    else:
                        txt = a.txt(
                            f"Error registrado: {dir_txt} fue incorrecto aqui. "
                            "Ajustando mis parametros para mejorar.",
                            f"Error logged: {dir_txt} was wrong here. "
                            "Adjusting parameters to improve.")
                    a.voz.decir(txt, a.idioma)
                except Exception:
                    pass
            threading.Thread(target=_hablar, daemon=True, name="ErrVoz").start()

        except Exception as _e:
            a.log(f"[Conciencia] Error en análisis de fallo: {_e}")

    def _post_mortem_trade(self, acierto: bool):
        """
        Analiza el resultado tras el cierre de vela.
        Extrae la lección principal y la registra.
        Cada 10 trades dispara la auto-evaluación global.
        """
        a   = self.app
        raz = self._razonamiento_actual
        if not raz:
            return

        dir_txt = "SUBIDA" if raz.get("dir") == "V" else "BAJADA"
        votos   = raz.get("votos", 0)
        patron  = raz.get("patron", "?")
        sesion  = raz.get("sesion", "?")
        rsi     = raz.get("rsi")

        # Diagnosticar causa probable
        if not acierto:
            if rsi is not None and 35 <= rsi <= 55:
                leccion = "RSI en zona neutral — evitar entradas sin confirmación adicional."
            elif "Asia" in sesion or "transición" in sesion:
                leccion = "Entrada fuera de killzone — baja liquidez amplifica falsas señales."
            elif votos < 4:
                leccion = f"Solo {votos}/11 votos — consenso insuficiente para producción."
            else:
                leccion = "El precio tomó liquidez en sentido contrario — posible trampa."
        else:
            if rsi is not None and ((rsi < 35 and raz.get("dir") == "V")
                                    or (rsi > 65 and raz.get("dir") == "R")):
                leccion = "RSI en extremo confirmó el rebote — patrón fiable."
            elif votos >= 5:
                leccion = "Consenso alto (5-7 modelos) acertó — mantener umbral."
            else:
                leccion = "Sesión + patrón alineados funcionaron correctamente."

        # Lección adicional desde SMC
        smc_setup = raz.get("smc_setup", "")
        en_kz     = raz.get("smc_en_kz", False)
        if not acierto:
            if not en_kz:
                leccion += " | Entrada fuera de killzone — mayor riesgo de señal falsa."
            elif raz.get("smc_sweep"):
                leccion += " | Sweep detectado pero no fue suficiente — revisar confirmación adicional."
        else:
            if raz.get("smc_sweep"):
                leccion += " | Sweep de liquidez acertó — patrón LWS fiable."
            elif raz.get("smc_ob") and en_kz:
                leccion += " | OB en killzone funcionó — combinación óptima LWS."

        a.log(
            f"[Post-mortem] {'WIN' if acierto else 'LOSS'}: {dir_txt} | "
            f"patron='{patron}' | {votos}/7 | sesion={sesion} | "
            f"SMC='{smc_setup}' | {leccion}"
        )

        # ── Conciencia: aprendizaje online con resultado real ────────────────────
        try:
            if self.conciencia is not None:
                _asset = self.app.mem.get("config", {}).get("asset_actual", "IQ Option")
                _res   = "WIN" if acierto else "LOSS"
                # Obtener dd_pct y slot_factor para conciencia.aprender() v3
                _dd_learn = 0.0
                _sf_learn = 1.0
                try:
                    _dd_learn = float(profesional.stats().get("dd_actual", 0.0)) if profesional else 0.0
                except Exception:
                    pass
                try:
                    _sf_learn = float(self._session_tracker.factor_confianza())
                except Exception:
                    pass
                self.conciencia.aprender(
                    asset       = _asset,
                    dir_        = raz.get("dir", "V"),
                    hora        = raz.get("hora", int(time.strftime("%H"))),
                    regime      = raz.get("smc_regime", "neutral"),
                    votos       = raz.get("votos", 0),
                    prob        = raz.get("prob", 0.5),
                    dia         = raz.get("dia", int(time.strftime("%w"))),
                    smc_en_kz   = bool(raz.get("smc_en_kz", False)),
                    kelly       = raz.get("kelly", 0.0),
                    wr20        = raz.get("wr20", 50.0),
                    rsi         = raz.get("rsi") or 50.0,
                    hurst       = raz.get("hurst") or 0.5,
                    votos_ind   = raz.get("votos_ind", [1,0,0,0,0,0,0]),
                    resultado   = _res,
                    p_pred      = raz.get("prob", 0.5),
                    dd_pct      = _dd_learn,
                    slot_factor = _sf_learn,
                )
        except Exception as _ec:
            self.app.log(f"[Conciencia] Error aprender: {_ec}")

        # ── Asset Scanner: actualizar WR por activo ─────────────────────────
        try:
            from . import asset_scanner as _asc_mod
            _asc = _asc_mod.obtener()
            if _asc is not None:
                _asset_actual = a.mem.get("config", {}).get("asset_actual", "EURUSD-OTC")
                _asc.actualizar_resultado(_asset_actual, gano=acierto)
        except Exception:
            pass

        # ── Grafo de Conocimiento: entrena con cada resultado ───────────────────
        if _GRAFO_OK and _grafo is not None:
            try:
                import time as _ti_g
                _contexto_grafo = {
                    "patron":     raz.get("patron", ""),
                    "regimen":    raz.get("smc_regime", ""),
                    "hora":       str(raz.get("hora", int(_ti_g.strftime("%H")))),
                    "activo":     a.mem.get("config", {}).get("asset_actual", ""),
                    "votos":      str(raz.get("votos", 0)),
                    "sesion":     raz.get("sesion", ""),
                    "dia_semana": str(raz.get("dia", int(_ti_g.strftime("%w")))),
                }
                _grafo.registrar(_contexto_grafo, gano=acierto)
                # Log cada 10 trades con estadísticas del grafo
                if self._trades_desde_autoeval % 10 == 0:
                    a.log(_grafo.resumen_texto())
            except Exception as _eg:
                pass

        # ── Fable 5: autopsia de pérdidas inesperadas (background) ──────────────
        raz_snapshot = dict(raz)   # copia antes de limpiar
        threading.Thread(target=self._fable5_postmortem,
                         args=(acierto, raz_snapshot),
                         daemon=True, name="F5PostMortem").start()

        # Contador → auto-evaluación cada 10 trades
        self._trades_desde_autoeval += 1
        if self._trades_desde_autoeval >= 10:
            self._trades_desde_autoeval = 0
            threading.Thread(target=self._autoevaluar, daemon=True,
                             name="LitchAutoEval").start()

        self._razonamiento_actual = {}

    def _autoevaluar(self):
        """
        Auto-evaluación global cada 10 trades.
        Analiza tasa de aciertos, Kelly, mejor activo y horas problemáticas.
        """
        a   = self.app
        est = a.mem["estadisticas"]
        tot = est.get("aciertos", 0) + est.get("fallos", 0)
        if tot < 10:
            return

        tasa  = est.get("aciertos", 0) / tot * 100
        p_win = est.get("aciertos", 0) / tot
        kelly = p_win - (1 - p_win) / 0.85
        estado_k = "rentable" if kelly > 0 else "en borde — necesito mas precision"

        racha    = self.fdb.racha_actual()
        horarios = self.fdb.horarios_malos()

        mejor_asset = "sin datos"
        mejor_wr    = 0.0
        try:
            tabla = a.broker.tabla_assets()
            if tabla:
                mejor_asset = tabla[0]["asset"]
                mejor_wr    = tabla[0]["wr"]
        except Exception:
            pass

        a.log(
            f"[AutoEval] {tot} trades | tasa={tasa:.1f}% | "
            f"Kelly={kelly:.3f} ({estado_k}) | "
            f"racha={racha['n']}{racha['tipo']} | "
            f"mejor={mejor_asset}({mejor_wr:.0f}%) | "
            f"horas_malas={list(horarios)[:3] if horarios else 'ninguna'}"
        )

        hora_txt = ""
        if horarios:
            hora_txt = a.txt(
                f"Horas dificiles: {', '.join(list(horarios)[:2])}.",
                f"Hard hours: {', '.join(list(horarios)[:2])}.")

        # Estado de la killzone actual
        kz_actual = _smc.killzone_activa()
        kz_txt    = (f"Killzone activa: {kz_actual['nombre']} ({kz_actual['tasa']})."
                     if kz_actual["activa"] else "")

        # HABLAR solo cada 15 min (el log queda siempre; la voz no satura).
        # Antes hablaba cada 10 trades = spam constante en sesiones largas.
        _ahora_ev = time.time()
        if _ahora_ev - getattr(self, "_t_ultima_autoeval_voz", 0.0) >= 900:
            self._t_ultima_autoeval_voz = _ahora_ev
            a.decir(a.txt(
                f"Auto-evaluacion de {tot} trades: {tasa:.0f}% de aciertos, {estado_k}. "
                f"Mejor activo: {mejor_asset} con {mejor_wr:.0f}%. {hora_txt} {kz_txt}",
                f"Self-assessment over {tot} trades: {tasa:.0f}% accuracy, {estado_k}. "
                f"Best asset: {mejor_asset} at {mejor_wr:.0f}%. {hora_txt} {kz_txt}").strip())

        # ── Fable 5: diagnóstico profundo cada 10 trades ──────────────────────
        threading.Thread(target=self._fable5_autoeval,
                         args=(tot, tasa, kelly, racha, mejor_asset,
                               mejor_wr, horarios),
                         daemon=True, name="F5AutoEval").start()

    # ─── Métodos Fable 5 ────────────────────────────────────────────────────────

    def _fable5_explicar_senal(self, dir_sen: str, votos: int, patron: str,
                                ind: dict, smc: dict, sesion: str,
                                prob: float, tasa: float):
        """
        Fable 5 explica en tiempo real POR QUÉ se ejecuta este trade.
        Corre en hilo background para no bloquear el trading.
        Solo se activa si hay 4+ votos (señal de calidad).
        """
        if votos < 4 or not _fable.disponible():
            return
        a = self.app
        try:
            dir_txt  = "SUBIDA" if dir_sen == "V" else "BAJADA"
            rsi_v    = f"{ind.get('rsi', '?'):.1f}" if ind.get('rsi') else "N/D"
            macd_v   = f"{ind.get('macd_h', 0):.4f}"
            hurst_v  = f"{ind.get('hurst', 0.5):.3f}"
            entr_v   = f"{ind.get('entropia_perm', 0.5):.3f}"
            setup    = smc.get("setup", "ninguno")
            narr_smc = smc.get("narrativa", "")
            en_kz    = "SÍ" if smc.get("en_kz") else "NO"

            contexto = (
                f"SEÑAL: {dir_txt}  Votos: {votos}/7  Patrón: {patron}\n"
                f"Sesión: {sesion}  Prob. Bayes: {prob:.0%}  WR histórico: {tasa:.0f}%\n"
                f"RSI: {rsi_v}  MACD-H: {macd_v}  Hurst: {hurst_v}  Entropía: {entr_v}\n"
                f"SMC Setup: {setup}  En Killzone: {en_kz}\n"
                f"Narrativa SMC: {narr_smc or 'ninguna'}"
            )
            pregunta = (
                "Analiza esta señal de trading en 3 oraciones técnicas:\n"
                "1) ¿Qué confluencia de indicadores valida esta entrada?\n"
                "2) ¿Cuál es el mayor riesgo específico de este setup?\n"
                "3) ¿Bajo qué condición debería ignorarse esta señal?\n"
                "Respuesta directa, sin repetir los datos dados. Sin disclaimers."
            )
            respuesta = _fable.responder_analisis(pregunta, contexto=contexto)
            if respuesta:
                a.log(f"[Fable5/Señal] {respuesta[:300]}")
        except Exception as e:
            a.log(f"[Fable5/Señal] Error: {e}")

    def _fable5_postmortem(self, acierto: bool, raz: dict):
        """
        Fable 5 hace autopsia profunda de PÉRDIDAS INESPERADAS (votos >= 4).
        Identifica la causa raíz matemática del fallo.
        Corre en hilo background.
        """
        votos = raz.get("votos", 0)
        if acierto or votos < 4 or not _fable.disponible():
            return
        a = self.app
        try:
            dir_txt = "SUBIDA" if raz.get("dir") == "V" else "BAJADA"
            contexto = (
                f"PÉRDIDA INESPERADA (votos={votos}/7):\n"
                f"Dirección apostada: {dir_txt}\n"
                f"Patrón: {raz.get('patron','?')}  Sesión: {raz.get('sesion','?')}\n"
                f"RSI={raz.get('rsi','?')}  MACD-H={raz.get('macd','?')}  "
                f"Hurst={raz.get('hurst','?')}\n"
                f"SMC setup: {raz.get('smc_setup','ninguno')}\n"
                f"BOS={raz.get('smc_bos')}  CHoCH={raz.get('smc_choch')}  "
                f"Sweep={raz.get('smc_sweep')}  OB={raz.get('smc_ob')}  "
                f"En_KZ={raz.get('smc_en_kz')}\n"
                f"Prob. Bayes: {raz.get('prob',0):.0%}  WR histórico: {raz.get('tasa',50):.0f}%"
            )
            pregunta = (
                "Este trade tenía alta confluencia pero resultó en PÉRDIDA. "
                "Diagnóstico en 3 puntos:\n"
                "1) ¿Qué indicador o combinación falló y por qué matemáticamente?\n"
                "2) ¿Qué patrón de trampa de mercado explica este fallo?\n"
                "3) ¿Qué condición adicional evitaría esta entrada en el futuro?\n"
                "Sé específico con los valores dados. Técnico y directo."
            )
            respuesta = _fable.responder_analisis(pregunta, contexto=contexto)
            if respuesta:
                a.log(f"[Fable5/PostMortem] {respuesta[:400]}")
                # Si el diagnóstico es crítico, lo dice por voz (primeras 180 chars)
                resumen_voz = respuesta[:180].split(".")[0] + "."
                a.decir(a.txt(
                    f"Análisis de pérdida: {resumen_voz}",
                    f"Loss analysis: {resumen_voz}"))
        except Exception as e:
            a.log(f"[Fable5/PostMortem] Error: {e}")

    def _fable5_autoeval(self, tot: int, tasa: float, kelly: float,
                         racha: dict, mejor_asset: str, mejor_wr: float,
                         horarios):
        """
        Fable 5 genera recomendaciones estratégicas cada 10 trades.
        Combina matemática (Kelly, Hurst, tasa) con conocimiento de libros.
        """
        if not _fable.disponible():
            return
        a = self.app
        try:
            racha_txt  = f"{racha.get('n',0)} {racha.get('tipo','?')}"
            horas_txt  = ", ".join(list(horarios)[:3]) if horarios else "ninguna"
            kelly_pct  = f"{kelly:.1%}"

            contexto = (
                f"SESIÓN ACTUAL — {tot} trades acumulados\n"
                f"Win Rate: {tasa:.1f}%  (objetivo >60% para rentabilidad)\n"
                f"Kelly Criterion: {kelly_pct} "
                f"({'RENTABLE' if kelly > 0 else 'EN PÉRDIDA'})\n"
                f"Racha actual: {racha_txt}\n"
                f"Mejor activo: {mejor_asset} ({mejor_wr:.0f}% WR)\n"
                f"Horas problemáticas: {horas_txt}\n"
                f"Payout broker: 85%  (break-even: WR > 54.1%)"
            )
            pregunta = (
                f"Análisis estratégico de sesión — {tot} trades:\n"
                f"1) Con WR={tasa:.0f}% y Kelly={kelly_pct}, ¿cuál es mi estado "
                f"matemático de rentabilidad y qué debo ajustar primero?\n"
                f"2) ¿Qué sugieren las horas problemáticas ({horas_txt}) sobre "
                f"el horario óptimo de trading?\n"
                f"3) Una acción concreta para el próximo bloque de 10 trades.\n"
                f"4) ¿Debo continuar o pausar según el criterio Kelly?\n"
                f"Técnico, directo, con números. Sin disclaimers."
            )
            respuesta = _fable.responder_analisis(pregunta, contexto=contexto)
            if respuesta:
                a.log(f"[Fable5/AutoEval] {respuesta[:500]}")
                # Voz: primer punto del análisis
                primer_punto = respuesta[:220].split("\n")[0]
                a.decir(a.txt(
                    f"Fable dice: {primer_punto}",
                    f"Fable says: {primer_punto}"))
        except Exception as e:
            a.log(f"[Fable5/AutoEval] Error: {e}")
