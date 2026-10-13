"""Litch Trading-IA — punto de entrada.

Asistente personal de IA bilingüe (español/inglés) con voz suave estilo
Jarvis, visión de pantalla, memoria de patrones, conocimiento online,
recordatorios, llave maestra TOTP y panel flotante. Entrena análisis de
mercado en el DEMO de IQ Option.

Uso:  python litch.py
"""  # v2.1
import os
import threading
import time
import tkinter as tk

from core import memoria, respaldo
from core.analisis import AnalizadorPatrones
from core.autocalibracion import AutoCalibracion
from core.broker_iq import BrokerUniversal
from core.cerebro import Cerebro, menciona_nombre
from core.consejero import Consejero
from core.interfaz import Interfaz
from core.loteria_avanzada import AnalizadorLoteria
from core.oido import Oido
from core.recordatorios import Recordatorios
from core.red_maestra import RedMaestra
from core.trading import AgenteTrading
from core.voz import Voz
from core import lector_libros as _libros
from core import meta_diaria as _meta_mod
from core.base_conocimiento import BaseConocimiento
from core.broker_ibkr import BrokerIBKR
from core.broker_schwab import BrokerSchwab
from core.explorador_broker import ExploradBroker
from core.watchdog import Watchdog
try:
    from core.ui_learner import UILearner as _UILearner, UILearnerDaemon as _UILearnerDaemon
    _UI_LEARNER_OK = True
except Exception:
    _UI_LEARNER_OK = False

try:
    from core import tv_feed as _tv_feed_mod
    _TV_FEED_OK = True
except Exception:
    _TV_FEED_OK = False
    _tv_feed_mod = None
from core import conciencia as _conciencia_mod
try:
    from core.overlay import OverlayRegion as _OverlayRegion
    _OVERLAY_DISPONIBLE = True
except Exception:
    _OVERLAY_DISPONIBLE = False

try:
    from core import senal_visual as _senal_visual_mod
    _SENAL_VISUAL_OK = True
except Exception:
    _SENAL_VISUAL_OK = False

try:
    from core import consejos_visual as _consejos_mod
    _CONSEJOS_OK = True
except Exception:
    _CONSEJOS_OK = False

try:
    from core.letrero_senal import LetreroSenal as _LetreroSenal
    _LETRERO_OK = True
except Exception:
    _LETRERO_OK = False


class LitchApp:
    def __init__(self):
        self.mem = memoria.cargar()
        # SIEMPRE arrancan en OFF — el usuario activa manualmente
        # según su flujo: configura → calibra → activa Sistema → activa Trading
        self.activo       = False
        self.trading_on   = False
        self.autoclick_on = False
        self.modo_autonomo = False
        # El idioma solo cambia si el señor lo pide con el botón 🌐. Nunca
        # por accidente. Un valor raro guardado en memoria (o un idioma que
        # Litch no habla) vuelve a español, que es el idioma de esta casa.
        _idi = str(self.mem["config"].get("idioma", "es") or "es").lower().strip()
        self.idioma = _idi if _idi in ("es", "en") else "es"
        self.usar_claude = bool(self.mem["config"].get("usar_claude", False))
        self.usar_ollama = bool(self.mem["config"].get("usar_ollama", True))

        # ── Analizador avanzado de lotería (MLP + 9 métodos estadísticos) ──
        _ruta_lot = os.path.join(memoria.ruta_memoria_ap(), "loteria_avanzada_mlp.json")
        self.loteria_av = AnalizadorLoteria(n_numeros=49, ruta=_ruta_lot)

        self.voz = Voz(al_hablar=self._orbe_hablando)
        self.analizador = AnalizadorPatrones(self.mem, lambda: memoria.guardar(self.mem))
        self.analizador2 = AnalizadorPatrones(
            self.mem, lambda: memoria.guardar(self.mem), sufijo="_2")
        self.analizador3 = AnalizadorPatrones(
            self.mem, lambda: memoria.guardar(self.mem), sufijo="_3")
        self.analizador4 = AnalizadorPatrones(
            self.mem, lambda: memoria.guardar(self.mem), sufijo="_4")
        self.red = RedMaestra()
        self.cerebro = Cerebro(self)
        self.recordatorios = Recordatorios(self)
        self.oido = Oido(self._desde_microfono, self.idioma, al_grabar=self._orbe_grabando)
        # Conciencia disponible desde el arranque (antes del agente de trading)
        self.conciencia = _conciencia_mod.obtener(self)
        self.agente = AgenteTrading(self)   # inicia FalloDB + MonitorTrade internamente
        self.agente.start()
        self.broker = BrokerUniversal(self)
        self.meta_diaria = _meta_mod.obtener(self)
        self.autocalib = AutoCalibracion(self)
        self.autocalib.start()

        # ── UILearner: aprendizaje visual de interfaz, agnóstico de idioma ───
        self.ui_learner = None
        if _UI_LEARNER_OK:
            try:
                self.ui_learner = _UILearner(self)
                _UILearnerDaemon(self.ui_learner).start()
                self.log("[UILearner] Sistema de aprendizaje visual iniciado.")
            except Exception as _ule:
                self.log(f"[UILearner] No disponible: {_ule}")

        # ── TVFeed: datos OHLCV en tiempo real vía Yahoo Finance ─────────────
        self.tv_feed = None
        if _TV_FEED_OK:
            try:
                self.tv_feed = _tv_feed_mod.inicializar(self)
            except Exception as _tvex:
                self.log(f"[TVFeed] No disponible: {_tvex}")

        # ── GestorGrafico: centra y ajusta zoom del gráfico periódicamente ───
        try:
            from core import chart_controls as _cc_mod
            self.gestor_grafico = _cc_mod.iniciar(self)
        except Exception as _gge:
            self.gestor_grafico = None
            self.log(f"[Chart] Gestor no disponible: {_gge}")

        threading.Thread(target=self._cuidador, daemon=True).start()
        self.respaldo_auto = False
        threading.Thread(target=self._respaldo_periodico, daemon=True).start()
        self.consejos_on = True
        self.consejero = Consejero(self)
        self.consejero.start()
        self.interfaz = Interfaz(self)

        # ── GUARDIÁN DE CIERRE ──────────────────────────────────────────
        # El señor perdió una operación porque Litch se cerró en silencio,
        # sin dejar rastro de por qué. Esto engancha las tres vías de
        # salida (botón, excepción no capturada, fin del intérprete) y
        # escribe un latido en disco cada 5 segundos. Si vuelve a caerse,
        # al arrancar sabremos cuándo, haciendo qué, y con cuánto dinero
        # expuesto.
        # ── LA BARRA SE ANCLA SOLA ──────────────────────────────────────
        # Los monitores cambian: se desconectan, se cambia la resolución,
        # Windows los reordena al despertar del suspendido. Sin esto, la
        # barra se queda con el ancho de una pantalla que ya no existe.
        try:
            from core import monitores as _mon
            _mon.anclar_barra(self, forzar=True)
            _mon.vigilar(self)
        except Exception as _e_mon:
            self.log(f"[Monitores] No pude vigilar el anclaje: {_e_mon}")

        try:
            from core import guardian_cierre as _gc
            _gc.instalar(self)
            _aviso_previo = _gc.revisar_arranque(self)
            if _aviso_previo:
                self._aviso_cierre_previo = _aviso_previo
        except Exception as _e_gc:
            self.log(f"[Guardián] No pude instalarlo: {_e_gc}")
        # Overlay de visión activa — requiere el root de la interfaz
        self.overlay = None
        if _OVERLAY_DISPONIBLE:
            try:
                # Se le pasa la interfaz para que el marco pueda preguntarle
                # cuánto mide la barra AHORA, en vez de suponerlo. Así el
                # borde sube solo cuando el señor pliega la barra.
                self.overlay = _OverlayRegion(self.interfaz.root, self.interfaz)
                self.overlay.iniciar()
            except Exception as _e:
                self.log(f"[Overlay] No disponible: {_e}")

        # ── Señal visual flotante (flechas de dirección) ─────────────────────
        self.senal_visual = None
        if _SENAL_VISUAL_OK:
            try:
                self.senal_visual = _senal_visual_mod.obtener(
                    root=self.interfaz.root, app=self)
                self.log("[SenalVisual] Flechas de señal activadas.")
            except Exception as _e:
                self.log(f"[SenalVisual] No disponible: {_e}")

        # ── Letrero de predicción con razonamiento ────────────────────────────
        self.letrero = None
        if _LETRERO_OK:
            try:
                self.letrero = _LetreroSenal(self)
                self.log("[Letrero] Letrero de señal con razonamiento activo.")
            except Exception as _le:
                self.log(f"[Letrero] No disponible: {_le}")

        # ── Panel de recomendaciones de capital ───────────────────────────────
        self.consejos_visual = None
        if _CONSEJOS_OK:
            try:
                self.consejos_visual = _consejos_mod.obtener(
                    root=self.interfaz.root, app=self)
                self.log("[Capital HUD] Panel de capital activado.")
            except Exception as _e:
                self.log(f"[Capital HUD] No disponible: {_e}")
        self.var_respaldo_auto = tk.BooleanVar(value=False)
        # Recuperar índice de libros del disco (no bloquea el arranque)
        _libros.inicializar()
        # Auto-indexar los manuales de LIBROS/ en segundo plano: así el
        # conocimiento de los brokers y del trading está disponible sin que
        # el usuario tenga que decir "carga mis libros" cada vez.
        def _auto_cargar_libros():
            try:
                time.sleep(12)   # dejar arrancar todo primero
                res = _libros.cargar_libros(callback=None)
                n = res.get("nuevos", 0) if isinstance(res, dict) else 0
                tot = res.get("total", 0) if isinstance(res, dict) else 0
                if tot:
                    self.log(f"[Libros] Manuales indexados: {tot} "
                             f"({n} nuevos). Conocimiento de brokers activo.")
            except Exception as _elb:
                self.log(f"[Libros] Auto-carga no disponible: {_elb}")
        threading.Thread(target=_auto_cargar_libros, daemon=True,
                         name="LitchAutoLibros").start()

        # ── Brokers profesionales (acciones reales) ─────────────────────────
        self.broker_ibkr   = BrokerIBKR(self)
        self.broker_schwab = BrokerSchwab(self)

        # ── Base de conocimiento persistente ────────────────────────────────
        self.conocimiento = BaseConocimiento(self)

        # ── Alimentador de conocimiento de internet ──────────────────────────
        try:
            from core.knowledge_feeder import obtener as _get_kf
            self.knowledge_feeder = _get_kf(app=self)
            self.knowledge_feeder.iniciar()
            # Scanner de activos (evalúa cuál es el mejor para operar)
            from core.asset_scanner import obtener as _get_sc
            self.asset_scanner = _get_sc(app=self)
            self.log("[KnowledgeFeed] Iniciado — tasas, noticias y conceptos de trading")
        except Exception as _e_kf:
            self.log(f"[KnowledgeFeed] No disponible: {_e_kf}")
            self.knowledge_feeder = None
            self.asset_scanner   = None

        # ── Explorador autónomo de broker ────────────────────────────────────
        # Aprende el broker desde pantalla: activo, vencimiento, payout,
        # herramientas e indicadores. Se activa con el modo autónomo.
        self.explorador = ExploradBroker(self)
        self.explorador.start()

        # ── AutoAprendizaje: guarda TODO lo aprendido cada 5 min y al cerrar ─
        try:
            from core import autoaprendizaje as _aa_mod
            self.autoaprendizaje = _aa_mod.iniciar(self)
            self.log("[AutoAprendizaje] Guardado continuo de conocimiento activo.")
        except Exception as _e_aa:
            self.autoaprendizaje = None
            self.log(f"[AutoAprendizaje] No disponible: {_e_aa}")

        # ── Tareas programadas (cron interno estilo Jarvis/Hermes) ──────────
        try:
            from core import tareas_programadas as _tp_mod
            self.tareas = _tp_mod.iniciar(self)
        except Exception as _e_tp:
            self.tareas = None
            self.log(f"[Tareas] No disponible: {_e_tp}")

        # ── Preparación automática de Interactive Brokers ────────────────────
        # Al abrir Litch, se prepara TODO lo de IBKR solo: detecta TWS,
        # verifica que la cuenta sea simulada, calibra la visión y conecta
        # la API.
        #
        # PERO NO EMPIEZA A OPERAR SOLO. Y es a propósito.
        #
        # Un programa que abre operaciones nada más arrancar es un programa
        # que opera cuando usted no está mirando, con una configuración que
        # no ha revisado ese día. Litch deja todo listo y espera su
        # «activa el modo Wall Street». Ese segundo de decisión suya es
        # justo lo que separa una herramienta de un accidente.
        try:
            threading.Thread(target=self._preparar_ibkr, daemon=True,
                             name="LitchPrepararIBKR").start()
        except Exception as _e_pi:
            self.log(f"[IBKR] No pude preparar: {_e_pi}")

        # ── Arsenal de capacidades (banner estilo Hermes Agent) ─────────────
        try:
            self.log(
                "[Arsenal] Herramientas: trading(11 motores) · red maestra "
                "CNN+LSTM+MLP · RL-DQN · SMC/liquidez · memoria de refuerzo "
                "· umbral aprendido · anti-tilt · flash-crash guard · "
                "vision pantalla completa · UILearner · voz ES/EN · "
                "practica DEMO · modo nocturno · entrenador historico · "
                "tareas programadas · loteria(Baloto/Astro) · 12 manuales "
                "· brokers: IQ Option, IBKR(paper 7497), Schwab · "
                "respaldo nube · watchdog anti-crash · autoguardado 5min")
        except Exception:
            pass

        # ── Watchdog anti-crash ─────────────────────────────────────────────
        self.watchdog = Watchdog(self)
        self._registrar_hilos_watchdog()
        self.watchdog.start()

    # --- Interactive Brokers: preparación al arrancar ---------------------

    def _preparar_ibkr(self):
        """Deja IBKR listo para trabajar, sin abrir ninguna operación.

        Corre en segundo plano para no retrasar el arranque. Si TWS no está
        abierto, se calla: no tiene sentido dar la lata cada vez que Litch
        se abre para otra cosa.
        """
        import time as _t
        _t.sleep(6)      # dejar que la interfaz termine de montarse

        try:
            from core import vision_tws as _vt
            v = _vt.ventana_tws()
            if not v:
                return          # sin TWS no hay nada que preparar
        except Exception:
            return

        pasos = []

        # 1. ¿Es cuenta simulada? Lo primero y lo innegociable.
        try:
            est = _vt.leer_estado_tws(self)
            if est.get("es_paper") is False:
                self.log("[IBKR] ⛔ TWS abierto con una cuenta REAL. No "
                         "preparo nada. Cambie a la simulada (DU).")
                self.decir("Señor, veo Interactive Brokers abierto con una "
                           "cuenta real. No voy a prepararme para operar "
                           "ahí. Cambie a la cuenta simulada.")
                return
            if est.get("es_paper") is True:
                pasos.append(f"cuenta {est.get('cuenta','DU…')} simulada ✓")
        except Exception:
            pass

        # 2. Calibrar la visión al gráfico de TWS
        try:
            cfg = self.mem.get("config", {})
            if cfg.get("broker_visual") != "tws":
                _vt.calibrar_para_tws(self)
                pasos.append("visión calibrada al gráfico de TWS")
            else:
                pasos.append("visión ya apuntaba a TWS")
        except Exception:
            pass

        # 3. Conectar la API (solo paper; el conector se desconecta solo
        #    si el servidor responde con una cuenta real)
        try:
            br = getattr(self, "broker_ibkr", None)
            if br is not None and not getattr(br, "esta_conectado", False):
                if br.conectar(modo="paper"):
                    pasos.append("API conectada al puerto 7497")
                else:
                    pasos.append("API sin conectar (habilítela en TWS)")
        except Exception as e:
            pasos.append(f"API no disponible ({e})")

        # 4. Vigilante de posiciones — cierra el ciclo de aprendizaje.
        #    Sin él, Litch anota lo que abre y nunca lo que le pasó
        #    después: un diario que nadie lee.
        try:
            from core import vigilante_posiciones as _vp
            _vp.obtener(self)
            pasos.append("vigilante de posiciones en marcha")
        except Exception as e:
            self.log(f"[Vigilante] No pude iniciarlo: {e}")

        # 5. Gestor de posición — mueve el stop a equilibrio a +1R.
        #    Es lo que hace un operador con oficio: convertir una operación
        #    que va bien en una que ya no puede perder.
        try:
            from core import gestor_posicion as _gp
            _gp.obtener(self)
            pasos.append("gestor de stops activo")
        except Exception as e:
            self.log(f"[Gestor] No pude iniciarlo: {e}")

        # 6. ¿Está calibrado el ticket?
        try:
            from core import piloto_tws as _pt
            if not _pt.esta_calibrado(self):
                pasos.append("falta calibrar el ticket "
                             "(diga «calibra el ticket de TWS»)")
        except Exception:
            pass

        if not pasos:
            return

        self.log("[IBKR] Preparación automática: " + " · ".join(pasos))

        # 7. Contarlo, y dejar clarísimo que NO ha empezado a operar
        try:
            from core import motor_acciones as _ma
            _, horario = _ma.mercado_abierto()
        except Exception:
            horario = ""

        self.decir(
            "Señor, he preparado Interactive Brokers solo. " +
            " ".join(pasos[:2]) + ". " + horario + " "
            "No he abierto ninguna operación y no lo haré por mi cuenta: "
            "cuando quiera que empiece, dígame «activa el modo Wall "
            "Street».")

    # --- utilidades -------------------------------------------------------
    def txt(self, es, en):
        """Texto según el idioma actual."""
        return en if self.idioma == "en" else es

    def decir(self, texto, idioma=None):
        self.log(texto)
        self.voz.decir(texto, idioma or self.idioma)

    def log(self, texto):
        try:
            self.interfaz.log(texto)
        except Exception:
            print(texto)

    # --- idioma -----------------------------------------------------------
    def set_idioma(self, idioma):
        self.idioma = "en" if idioma == "en" else "es"
        self.mem["config"]["idioma"] = self.idioma
        memoria.guardar(self.mem)
        self.oido.set_idioma(self.idioma)
        self._refrescar()

    # --- interruptores ----------------------------------------------------
    def set_activo(self, valor, hablar=False):
        self.activo = bool(valor)
        if hablar:
            self.voz.decir(self.txt("Sistemas reactivados." if valor
                                    else "Entrando en modo de espera.",
                                    "Systems back online." if valor
                                    else "Entering standby mode."), self.idioma)
        self._refrescar()

    def set_trading(self, valor, hablar=False):
        self.trading_on = bool(valor)
        self.mem["config"]["trading_on_save"] = self.trading_on
        memoria.guardar(self.mem)
        if valor and not self.mem["config"].get("region_grafico"):
            self.decir(self.txt(
                "Antes de analizar necesito calibrar el gráfico, señor. "
                "Abra Calibrar y pulse '🤖 Auto-calibrar' para que lo detecte solo.",
                "Before analyzing I need to calibrate the chart, sir. "
                "Open Calibrate and press '🤖 Auto-calibrate' to detect it automatically."))
        elif hablar:
            self.voz.decir(self.txt(
                "Análisis de mercado activado. Observando el gráfico."
                if valor else "Análisis de mercado detenido.",
                "Market analysis activated. Watching the chart."
                if valor else "Market analysis stopped."), self.idioma)
        self._refrescar()

    def set_autoclick(self, valor, hablar=False):
        """Activa el modo autónomo completo — un solo botón lo enciende todo.

        El modo autónomo se activa SIN requerir TOTP.  El usuario controla
        el encendido/apagado directamente desde el botón Auto-click.
        """
        self.autoclick_on = bool(valor)
        self.mem["config"]["autoclick_on_save"] = bool(valor)
        if valor:
            # Modo autónomo directo — sin TOTP
            self.modo_autonomo = True
            self.mem["config"]["modo_autonomo_save"] = True
            # ── Activar análisis de mercado si no estaba encendido ─────────
            if not self.trading_on:
                self.trading_on = True
                self.mem["config"]["trading_on_save"] = True
            # Auto-click y Práctica DEMO son mutuamente excluyentes:
            # cuando el usuario activa el modo real, detenemos la práctica.
            try:
                practica = getattr(self, "modo_practica", None)
                if practica and practica.activo:
                    practica.desactivar()
                    self.mem["config"]["practica_on_save"] = False
                    self.log("[Auto] Practica DEMO desactivada — modo real activo.")
            except Exception:
                pass
            memoria.guardar(self.mem)
            # ── Detectar botones en pantalla ahora mismo ──────────────────────
            # Con la nueva visión inteligente, SIEMPRE se puede operar:
            # _ejecutar_click() detecta los botones en tiempo real antes de cada
            # trade. Disparamos auto-calibración ahora para tener las coords listas,
            # pero el modo autónomo funciona aunque aún no hayan sido detectadas.
            if hasattr(self, "autocalib"):
                self.autocalib.calibrar_ahora()
            if hablar:
                monto_b = self.mem["config"].get("monto_base", 10.0)
                calibrado = (self.mem["config"].get("boton_verde")
                             and self.mem["config"].get("boton_rojo"))
                # HONESTIDAD: el mensaje refleja la cuenta REAL o DEMO según
                # lo registrado — nunca decir "dinero real" si estamos en demo.
                _es_real = (self.tipo_cuenta == "real")
                _cta_es = "dinero real" if _es_real else "dinero DEMO de practica"
                _cta_en = "real money" if _es_real else "DEMO practice money"
                if calibrado:
                    self.decir(self.txt(
                        f"Modo autonomo activado, senor. Operare con {_cta_es}: "
                        f"${monto_b:.0f} por trade en cada senal valida. "
                        "Para pausar pulse Auto de nuevo.",
                        f"Autonomous mode on, sir. I will trade with {_cta_en}: "
                        f"${monto_b:.0f} per trade on valid signals. "
                        "Press Auto again to pause."))
                else:
                    self.decir(self.txt(
                        f"Modo autonomo activado con {_cta_es}. Buscando botones "
                        "del broker en pantalla. Asegurese de que el broker "
                        "este visible, senor.",
                        f"Autonomous mode on with {_cta_en}. Looking for broker "
                        "buttons on screen. Make sure the broker is visible, sir."))
            # Gesto de confirmación — mueve el cursor al botón de compra
            # para que el usuario vea que el mouse está bajo control
            threading.Thread(target=self._gesto_confirmacion,
                             daemon=True, name="GestoAutoClick").start()
            # Lanzar auto-optimización del broker en background
            try:
                threading.Thread(target=lambda: (
                    __import__('time').sleep(2),
                    self.broker.auto_optimizar()
                ), daemon=True, name="BrokerOptAutoStart").start()
            except Exception:
                pass
        else:
            self.modo_autonomo = False
            self.mem["config"]["modo_autonomo_save"] = False
            memoria.guardar(self.mem)
            if hablar:
                self.voz.decir(self.txt(
                    "Auto-click pausado. Solo observo y sugiero señales.",
                    "Auto-click paused. Watching and suggesting only."),
                    self.idioma)
        self._refrescar()

    # ── Tipo de cuenta — demo vs real ─────────────────────────────────────────

    @property
    def tipo_cuenta(self) -> str:
        """'demo' o 'real'. Nunca None: 'demo' es el valor seguro por defecto."""
        return self.mem["config"].get("tipo_cuenta", "demo")

    def set_tipo_cuenta(self, tipo: str, hablar: bool = True) -> None:
        """Registra si el usuario está en cuenta DEMO o cuenta REAL de IQ Option.

        Litch ajusta sus mensajes, logs y advertencias según este valor.
        La cuenta siempre es demo hasta que el usuario lo cambie explícitamente.
        """
        tipo = tipo.lower().strip()
        if tipo not in ("demo", "real"):
            return
        anterior = self.mem["config"].get("tipo_cuenta", "demo")
        self.mem["config"]["tipo_cuenta"] = tipo
        memoria.guardar(self.mem)

        # Actualizar banner en la UI
        try:
            self.interfaz.root.after(
                0, lambda: self.interfaz._actualizar_banner_cuenta(tipo))
        except Exception:
            pass

        if not hablar or tipo == anterior:
            return

        if tipo == "real":
            # Práctica DEMO no tiene sentido en cuenta real — desactivar
            try:
                practica = getattr(self, "modo_practica", None)
                if practica and practica.activo:
                    practica.desactivar()
                    self.log("[Cuenta] Practica DEMO desactivada — cuenta real seleccionada.")
            except Exception:
                pass
            self.decir(self.txt(
                "Registrado, senor. Operamos en CUENTA REAL — cada trade del Auto-click "
                "mueve dinero verdadero. Le marcare '>>> TRADE REAL' en cada operacion. "
                "Presione Auto cuando este listo para operar.",
                "Noted, sir. We are on the REAL account — every Auto-click trade "
                "moves real money. I will log '>>> REAL TRADE' for each operation. "
                "Press Auto when you are ready to trade."))
        else:
            self.decir(self.txt(
                "Registrado, senor. Cuenta DEMO activa — practique sin riesgo. "
                "Active Practica para que opere autonomamente y acumule experiencia.",
                "Noted, sir. DEMO account active — practice without risk. "
                "Activate Practice so I can trade autonomously and build experience."))

    def _gesto_confirmacion(self):
        """Mueve el cursor brevemente a SUBE→BAJA→origen al activar auto-click.

        Demuestra al usuario que el mouse está bajo control. Usa print()
        en lugar de self.log() para evitar tocar tkinter desde un hilo.
        """
        import time as _t
        try:
            import pyautogui as _pg
            _pg.FAILSAFE = False
            cfg = self.mem.get("config", {})
            bv  = cfg.get("boton_verde")
            br  = cfg.get("boton_rojo")
            if not bv or not br:
                return
            ox, oy = _pg.position()
            _pg.moveTo(bv[0], bv[1], duration=0.35, _pause=False)
            _t.sleep(0.25)
            _pg.moveTo(br[0], br[1], duration=0.25, _pause=False)
            _t.sleep(0.20)
            _pg.moveTo(ox, oy, duration=0.30, _pause=False)
            print("[Litch] ✓ Gesto confirmación: mouse en control.")
        except Exception as _e:
            print(f"[Litch] Gesto omitido: {_e}")

    def set_modo_autonomo(self, valor, hablar=True):
        self.modo_autonomo = bool(valor)
        if not valor:
            self.autoclick_on = False
        memoria.guardar(self.mem)
        if hablar:
            self.decir(self.txt(
                "Modo autónomo activado, señor. Actuaré y me auto-ajustaré sin "
                "pedirle confirmación. Usted puede revocarlo cuando guste."
                if valor else
                "Modo autónomo desactivado. Vuelvo a pedirle confirmación para todo.",
                "Autonomous mode activated, sir. I will act and self-tune without "
                "asking. You may revoke it at any time."
                if valor else
                "Autonomous mode deactivated. I'll ask for confirmation again."))
        self._refrescar()

    def set_usar_claude(self, valor: bool, hablar: bool = False):
        """Activa o desactiva Claude como cerebro de chat (requiere API key)."""
        self.usar_claude = bool(valor)
        self.mem["config"]["usar_claude"] = self.usar_claude
        memoria.guardar(self.mem)
        if hablar:
            from core import mente_claude
            if valor:
                if mente_claude.disponible():
                    self.decir(self.txt(
                        "Conectado a Claude, senor. Usare la inteligencia de Anthropic "
                        "para sus consultas generales. El trading sigue local.",
                        "Connected to Claude, sir. I'll use Anthropic's intelligence "
                        "for general queries. Trading stays local."))
                else:
                    self.decir(self.txt(
                        "Toggle de Claude activado pero no encontre una API key. "
                        "Agrega tu clave en data/config_claude.json o en la variable "
                        "de entorno ANTHROPIC_API_KEY.",
                        "Claude toggle is on but no API key found. "
                        "Add your key to data/config_claude.json or set "
                        "the ANTHROPIC_API_KEY environment variable."))
            else:
                self.decir(self.txt(
                    "Desconectado de Claude. Usando el cerebro local.",
                    "Disconnected from Claude. Using local brain."))
        self._refrescar()

    def set_consejos(self, valor, hablar=True):
        self.consejos_on = bool(valor)
        self.mem["config"]["consejos_on_save"] = self.consejos_on
        memoria.guardar(self.mem)
        if hablar:
            self.voz.decir(self.txt(
                "Consejero activado. Le compartiré recomendaciones mientras trabaja."
                if valor else "Entendido, señor. Guardaré mis consejos para cuando los pida.",
                "Advisor on. I'll share recommendations as you work."
                if valor else "Understood, sir. I'll keep my advice until you ask."),
                self.idioma)
        self._refrescar()

    def set_microfono(self, valor):
        if valor:
            if not self.oido.disponible():
                self.decir(self.txt(
                    "El reconocimiento de voz no está instalado. Revise las "
                    "dependencias, señor.",
                    "Speech recognition is not installed. Check the dependencies, sir."))
            elif self.oido.iniciar():
                self.mem["config"]["mic_on_save"] = True
                memoria.guardar(self.mem)
                self.voz.decir(self.txt(
                    "Micrófono activo. Llámeme por mi nombre: Litch.",
                    "Microphone active. Call me by my name: Litch."), self.idioma)
        else:
            self.oido.detener()
            self.mem["config"]["mic_on_save"] = False
            memoria.guardar(self.mem)
            self.voz.decir(self.txt("Micrófono apagado.", "Microphone off."),
                           self.idioma)
        self._refrescar()

    def _refrescar(self):
        try:
            self.interfaz.root.after(0, self.interfaz.actualizar)
        except Exception:
            pass

    # --- orbe ---------------------------------------------------------------
    def _orbe_hablando(self, valor):
        try:
            self.interfaz.orbe.set_hablando(valor)
        except Exception:
            pass

    def _orbe_grabando(self, valor):
        """Activa el indicador visual de grabación de voz."""
        try:
            self.interfaz.orbe.set_escuchando(valor)
            if valor:
                self.interfaz.root.after(0, lambda: self.interfaz.log(
                    "● Capturando voz... (procesando con STT)"))
        except Exception:
            pass

    # --- entradas -----------------------------------------------------------
    def entrada_chat(self, texto):
        resultado = self.cerebro.procesar(texto, origen="chat")
        if not resultado:
            return ""
        respuesta, idioma = resultado
        self.voz.decir(respuesta, idioma)
        return respuesta

    def _desde_microfono(self, texto):
        self.log(f"Escuché: «{texto}»")
        try:
            self.interfaz.orbe.set_escuchando(True)
            self.interfaz.root.after(1500,
                                     lambda: self.interfaz.orbe.set_escuchando(False))
        except Exception:
            pass
        # Procesar en hilo separado: el micrófono sigue libre mientras Ollama responde
        threading.Thread(target=self._procesar_voz, args=(texto,),
                         daemon=True, name="LitchProcesa").start()

    def _procesar_voz(self, texto):
        """Procesa una frase de voz en segundo plano; no bloquea el micrófono."""
        if not self.activo:
            t = texto.lower()
            if menciona_nombre(t) and any(p in t for p in (
                    "despierta", "actívate", "enciende", "wake up", "resume")):
                self.set_activo(True)
                self.decir(self.txt("Sistemas reactivados, señor.",
                                    "Systems back online, sir."))
            return
        resultado = self.cerebro.procesar(texto, origen="voz")
        if resultado:
            respuesta, idioma = resultado
            self.log(f"Litch: «{respuesta}»")
            self.voz.decir(respuesta, idioma)

    # --- watchdog: registro de hilos críticos --------------------------------
    def _registrar_hilos_watchdog(self):
        """Registra todos los hilos vitales para reinicio automático."""
        wdg = self.watchdog
        a   = self

        # ── AgenteTrading (ahora llamado LitchMainLoop) ──────────────────────
        # Si muere, reiniciar es complejo (tiene estado interno). Solo monitoreamos
        # y alertamos; el AgenteTrading raramente muere en producción.
        def _restart_main():
            a.log("[Watchdog] ⚠ AgenteTrading (LitchMainLoop) ha muerto — reiniciando...")
            new_agente = __import__("core.trading", fromlist=["AgenteTrading"]).AgenteTrading(a)
            a.agente = new_agente
            new_agente.start()
        wdg.registrar("LitchMainLoop", _restart_main, critico=True)

        # ── Scanner veloz — se lanza desde AgenteTrading.run(); no tiene restart autónomo
        wdg.registrar("LitchScanVeloz", lambda: None, critico=False)

        # ── Canal 2
        def _restart_c2():
            threading.Thread(target=a.agente._loop_canal2,
                             daemon=True, name="LitchCanal2").start()
        wdg.registrar("LitchCanal2", _restart_c2, critico=False)

        # ── Canales 3 y 4
        def _restart_c3():
            threading.Thread(target=lambda: a.agente._loop_canal_extra(3),
                             daemon=True, name="LitchCanal3").start()
        def _restart_c4():
            threading.Thread(target=lambda: a.agente._loop_canal_extra(4),
                             daemon=True, name="LitchCanal4").start()
        wdg.registrar("LitchCanal3", _restart_c3, critico=False)
        wdg.registrar("LitchCanal4", _restart_c4, critico=False)

        # ── AutoCalib
        def _restart_autocalib():
            from core.autocalibracion import AutoCalibracion
            a.autocalib = AutoCalibracion(a)
            a.autocalib.start()
        wdg.registrar("LitchAutoCalib", _restart_autocalib, critico=False)

        # ── Consejero (ahora tiene nombre LitchConsejero gracias al fix)
        def _restart_consejero():
            from core.consejero import Consejero
            a.consejero = Consejero(a)
            a.consejero.start()
        wdg.registrar("LitchConsejero", _restart_consejero, critico=False)

        # ── ExploradBroker
        def _restart_explorador():
            from core.explorador_broker import ExploradBroker
            a.explorador = ExploradBroker(a)
            a.explorador.start()
        wdg.registrar("LitchExplorador", _restart_explorador, critico=False)

    # --- cuidador: pendiente de ti ------------------------------------------
    def _cuidador(self):
        # El heartbeat principal lo hace AgenteTrading cada 30s.
        # Este cuidador solo hace el recordatorio de pausa cada 90 minutos.
        _inicio_sesion = time.time()
        while True:
            time.sleep(5400)   # cada 90 minutos
            if self.activo:
                self.decir(self.txt(
                    "Señor, llevamos hora y media de sesión. Le recomiendo una "
                    "pausa breve, estirar las piernas y tomar agua. El mercado "
                    "seguirá aquí cuando regrese.",
                    "Sir, we've been at this for ninety minutes. I recommend a "
                    "short break, stretching, and some water. The market will "
                    "still be here when you return."))

    # --- atajos para el cerebro -----------------------------------------------
    def abrir_loteria(self):
        try:
            self.interfaz.root.after(0, self.interfaz.abrir_loteria)
        except Exception:
            pass

    def resumen_trading(self) -> str:
        """Resumen completo de rendimiento de trading (voz / chat)."""
        partes = [self.agente.fdb.resumen(idioma=self.idioma)]

        # Modo Práctica
        practica = getattr(self, "modo_practica", None)
        if practica and practica.activo:
            s = practica.stats()
            partes.append(self.txt(
                f"Practica DEMO activa: {s['trades']} trades, {s['wr']:.0f}% WR, "
                f"umbral adaptativo {practica._votos_min} votos.",
                f"DEMO practice active: {s['trades']} trades, {s['wr']:.0f}% WR, "
                f"adaptive threshold {practica._votos_min} votes."))

        # Modo Profesional
        profesional = getattr(self, "modo_profesional", None)
        if profesional and profesional.activo:
            s = profesional.stats()
            partes.append(self.txt(
                f"Modo profesional: {s['trades']} trades, {s['wr']:.0f}% WR, "
                f"Kelly P&L {s['pnl_kelly']:+.2f}.",
                f"Professional mode: {s['trades']} trades, {s['wr']:.0f}% WR, "
                f"Kelly P&L {s['pnl_kelly']:+.2f}."))

        # Meta Diaria
        meta = getattr(self, "meta_diaria", None)
        if meta and meta.activa:
            s   = meta.stats()
            sgn = "+" if s["pnl"] >= 0 else ""
            partes.append(self.txt(
                f"Meta diaria: {sgn}${s['pnl']:.2f} de ${s['meta_gan']:.0f}. "
                f"{s['wins']}W {s['losses']}L.",
                f"Daily target: {sgn}${s['pnl']:.2f} of ${s['meta_gan']:.0f}. "
                f"{s['wins']}W {s['losses']}L."))

        # Conciencia
        con = getattr(self, "conciencia", None)
        if con and len(con.memoria) >= 5:
            ece = con.meta.ece()
            cal = "bien calibrada" if ece < 0.08 else "calibrando"
            partes.append(self.txt(
                f"Conciencia: {len(con.memoria)} episodios, {con.red.n_updates} updates "
                f"red MLP, {cal} (ECE={ece:.3f}).",
                f"Consciousness: {len(con.memoria)} episodes, {con.red.n_updates} MLP "
                f"updates, {('well calibrated' if ece < 0.08 else 'calibrating')} "
                f"(ECE={ece:.3f})."))

        return " ".join(partes)

    def set_usar_ollama(self, valor: bool, hablar: bool = False):
        """Activa o desactiva Ollama como cerebro de chat offline."""
        self.usar_ollama = bool(valor)
        self.mem["config"]["usar_ollama"] = self.usar_ollama
        memoria.guardar(self.mem)
        if hablar:
            from core import mente
            if valor:
                if mente.disponible():
                    self.decir(self.txt(
                        "Ollama local activo, senor. Conversare sin internet cuando "
                        "Claude no este disponible.",
                        "Local Ollama active, sir. I'll converse offline when "
                        "Claude is unavailable."))
                else:
                    self.decir(self.txt(
                        "Toggle Ollama activado, pero Ollama no esta corriendo. "
                        "Instala y arranca Ollama en localhost:11434.",
                        "Ollama toggle on, but Ollama isn't running. "
                        "Install and start Ollama at localhost:11434."))
            else:
                self.decir(self.txt(
                    "Ollama desactivado. Usando Claude o el cerebro de reglas.",
                    "Ollama off. Using Claude or the rules engine."))
        self._refrescar()

    # --- restauración de sesión -----------------------------------------------
    def _restaurar_sesion(self) -> list:
        """
        Restaura silenciosamente todos los toggles de la sesión anterior.
        Se llama al arrancar, antes del saludo. No habla ni pide confirmación.
        Devuelve lista de nombres de lo que fue activado.
        """
        cfg = self.mem["config"]
        restaurados = []

        # ══ ARRANQUE LIMPIO ══════════════════════════════════════════════
        # NADA que actúe se auto-activa al iniciar. El usuario es quien
        # enciende cada función cuando la necesita:
        #   · Auto-click / modo autónomo  → botón AUTO
        #   · Trading (análisis)          → botón Trd
        #   · Práctica DEMO               → botón Prc
        #   · Micrófono                   → botón Mic
        # Solo se restauran preferencias pasivas (consejos, idioma).
        cfg.pop("modo_autonomo_save", None)
        cfg.pop("autoclick_on_save", None)
        self.modo_autonomo = False
        self.autoclick_on  = False

        self.trading_on = False
        cfg["trading_on_save"] = False

        # Práctica DEMO NUNCA se restaura sola: ejecuta clicks en el demo.
        cfg["practica_on_save"] = False

        # Consejos (preferencia pasiva — no mueve nada)
        self.consejos_on = bool(cfg.get("consejos_on_save", True))

        memoria.guardar(self.mem)
        self._refrescar()
        return restaurados

    # --- cierre limpio con guardado total ---------------------------------
    def cerrar_app(self):
        """Guarda TODO y cierra Litch de forma ordenada.

        Se ejecuta al cerrar la ventana (X). Nunca se cuelga: cada paso va
        protegido y hay un temporizador de seguridad que fuerza la salida
        a los 5 segundos aunque algún hilo se resista.
        """
        if getattr(self, "_cerrando", False):
            return
        self._cerrando = True

        # 0) Salida forzada garantizada (por si algo bloquea)
        def _forzar_salida():
            time.sleep(5)
            os._exit(0)
        threading.Thread(target=_forzar_salida, daemon=True,
                         name="LitchSalidaForzada").start()

        print("[Litch] Cerrando: guardando memoria y aprendizaje...")

        # 1) Apagar actuadores primero (que nada mueva el mouse al cerrar)
        self.autoclick_on  = False
        self.modo_autonomo = False
        self.trading_on    = False
        for _obj, _met in (
                (getattr(self, "gestor_grafico", None), "parar"),
                (getattr(self, "agente", None),         "parar"),
                (getattr(self, "consejero", None),      "parar"),
                (getattr(self, "watchdog", None),       "parar"),
                (getattr(self, "modo_practica", None),  "desactivar"),
                (getattr(self, "oido", None),           "detener")):
            try:
                if _obj and hasattr(_obj, _met):
                    getattr(_obj, _met)()
            except Exception:
                pass

        # 2) Guardar todo el conocimiento aprendido
        _guardados = []
        def _try(nombre, fn):
            try:
                fn()
                _guardados.append(nombre)
            except Exception as _e:
                print(f"[Litch] Aviso al guardar {nombre}: {_e}")

        _try("memoria",       lambda: memoria.guardar(self.mem))
        _try("red_maestra",   lambda: (self.red._guardar_todo(),
                                       self.red._guardar_stats()))
        _try("analisis",      lambda: self.analizador.guardar()
             if hasattr(self.analizador, "guardar") else None)
        _try("loteria_MLP",   lambda: self.loteria_av._guardar()
             if hasattr(self.loteria_av, "_guardar") else None)
        _ag = getattr(self, "agente", None)
        if _ag is not None:
            _try("fallo_db",  lambda: _ag.fdb._guardar()
                 if hasattr(getattr(_ag, "fdb", None), "_guardar") else None)
            for _atr in ("rl", "rl_agente", "perf", "performance"):
                _o = getattr(_ag, _atr, None)
                if _o is not None and hasattr(_o, "_guardar"):
                    _try(_atr, _o._guardar)
        _con = getattr(self, "conciencia", None)
        if _con is not None:
            for _met in ("guardar_todo", "_guardar_todo", "persistir"):
                if hasattr(_con, _met):
                    _try("conciencia", getattr(_con, _met))
                    break
        _aa = getattr(self, "autoaprendizaje", None)
        if _aa is not None and hasattr(_aa, "guardar_todo"):
            _try("autoaprendizaje", _aa.guardar_todo)

        print(f"[Litch] Guardado al cerrar: {', '.join(_guardados) or 'nada'}.")

        # 3) Cerrar la interfaz (los hilos daemon mueren con el proceso)
        try:
            self.interfaz.root.destroy()
        except Exception:
            pass
        os._exit(0)

    def calibrar_ahora(self):
        """Fuerza una calibración completa de pantalla inmediatamente."""
        self.autocalib.calibrar_ahora()
        self.decir(self.txt(
            "Re-calibrando pantalla ahora mismo, senor.",
            "Re-calibrating screen right now, sir."))

    def calibrar_rollover_auto(self):
        """Intenta detectar automáticamente el área del P&L en pantalla."""
        resultado = self.agente.monitor.calibrar_region_pl_auto()
        if resultado:
            self.mem["config"].update(resultado)
            memoria.guardar(self.mem)
            self.decir(self.txt(
                "Detecte el area de P&L en pantalla. Ahora puedo vigilar si vas ganando o perdiendo.",
                "I detected the P&L area on screen. I can now monitor whether you're winning or losing."))
        else:
            self.decir(self.txt(
                "No pude detectar el area de P&L automaticamente. Calibrala manualmente en el menu Calibrar.",
                "Couldn't auto-detect the P&L area. Please calibrate it manually in the Calibrate menu."))

    def analizar_loteria_av(self, cuantos: int = 6) -> dict:
        """Análisis avanzado (9 métodos + MLP neural) sobre el historial guardado."""
        historial = self.mem.get("loteria", {}).get("historial", [])
        return self.loteria_av.analizar(historial, cuantos=cuantos)

    def resumen_loteria_av(self) -> str:
        """Resumen en texto del análisis de lotería para voz o chat."""
        historial = self.mem.get("loteria", {}).get("historial", [])
        return self.loteria_av.resumen_texto(historial, idioma=self.idioma)

    def abrir_calibracion(self):
        try:
            self.interfaz.root.after(0, self.interfaz.abrir_calibracion)
        except Exception:
            pass

    def abrir_seguridad(self):
        try:
            self.interfaz.root.after(0, self.interfaz.abrir_seguridad)
        except Exception:
            pass

    def abrir_broker(self):
        try:
            self.interfaz.root.after(0, self.interfaz.abrir_broker)
        except Exception:
            pass

    def abrir_meta(self):
        try:
            self.interfaz.root.after(0, self.interfaz.abrir_meta)
        except Exception:
            pass

    def lecciones_broker_texto(self) -> str:
        """Resumen hablado de las últimas lecciones que la IA le enseñó a Litch."""
        lecciones = self.broker.lecciones_recientes(3)
        if not lecciones:
            return self.txt(
                "Aun no tengo lecciones de la IA sobre el broker, senor. "
                "Opera mas trades para que aprenda y consulte.",
                "No AI broker lessons yet, sir. Trade more so I can learn and consult.")
        partes = []
        for i, l in enumerate(reversed(lecciones), 1):
            fecha = l.get("fecha", "")[:10]
            texto = l.get("leccion", "")[:120]
            partes.append(f"Leccion {i} ({fecha}): {texto}")
        return self.txt(
            "Ultimas lecciones que la IA me enseno sobre el broker: " +
            " — ".join(partes),
            "Latest AI broker lessons: " + " — ".join(partes))

    def abrir_nube(self):
        try:
            self.interfaz.root.after(0, self.interfaz.abrir_nube)
        except Exception:
            pass

    # --- respaldo automático -------------------------------------------------
    def toggle_respaldo_auto(self):
        self.respaldo_auto = bool(self.var_respaldo_auto.get())
        self.decir(self.txt(
            "Respaldo automático activado, señor. Guardaré mi memoria en sus "
            "cuentas cada media hora." if self.respaldo_auto else
            "Respaldo automático desactivado.",
            "Automatic backup on, sir. I'll save my memory to your accounts "
            "every half hour." if self.respaldo_auto else
            "Automatic backup off."))

    def _respaldo_periodico(self):
        while True:
            time.sleep(1800)  # 30 minutos
            if getattr(self, "respaldo_auto", False):
                try:
                    resultado = respaldo.respaldar(self)
                    self.log(resultado)
                except Exception as e:
                    self.log(f"Respaldo automático falló: {e}")

    # ------------------------------------------------------------------
    def iniciar(self):
        # Restaurar sesión anterior antes de saludar
        restaurados = self._restaurar_sesion()

        velas    = len(self.mem["secuencia"])
        patrones = len(self.mem["patrones"])
        if velas:
            saludo = self.txt(
                f"Buenas, senor. Sistemas en linea. Memoria: {velas} velas "
                f"y {patrones} patrones. Listo para continuar.",
                f"Good day, sir. Systems online. Memory: {velas} candles "
                f"and {patrones} patterns. Ready to continue.")
        else:
            saludo = self.txt(
                "Buenas, senor. Litch en linea. Iniciando calibracion automatica.",
                "Good day, sir. Litch online. Starting auto-calibration.")

        if restaurados:
            saludo += self.txt(
                f" Sesion anterior restaurada: {', '.join(restaurados)}.",
                f" Previous session restored: {', '.join(restaurados)}.")
        else:
            saludo += self.txt(
                " Todos los modulos en espera: usted decide que activar.",
                " All modules on standby: you decide what to activate.")

        self.decir(saludo)
        self.interfaz.iniciar()


def _registrar_error(exc):
    """Guarda cualquier error de arranque para poder diagnosticarlo."""
    import datetime
    import os
    import traceback
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "MEMORIA_AP", "error_arranque.txt")
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(f"Error de arranque de Litch — {datetime.datetime.now()}\n")
            f.write("=" * 60 + "\n")
            f.write(traceback.format_exc())
    except Exception:
        pass
    print("\n" + "=" * 60)
    print("  LITCH NO PUDO ARRANCAR. Detalle del error:")
    print("=" * 60)
    traceback.print_exc()
    print("=" * 60)
    print("  Se guardó el detalle en  data/error_arranque.txt")
    print("=" * 60)


if __name__ == "__main__":
    try:
        LitchApp().iniciar()
    except Exception as e:
        _registrar_error(e)
        try:
            input("\nPresiona ENTER para cerrar...")
        except Exception:
            pass
