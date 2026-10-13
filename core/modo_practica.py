"""
modo_practica.py — Modo de práctica autónoma para aprendizaje acelerado (v4).

═══════════════════════════════════════════════════════════════════════════════
REGLAS DEL MODO PRÁCTICA — DEFINICIÓN DEFINITIVA
═══════════════════════════════════════════════════════════════════════════════

PRÁCTICA (cuenta DEMO):
  • Litch ejecuta clicks reales en la cuenta DEMO de IQ Option.
  • NO requiere auto-click ni modo_autonomo — funciona con el botón "Prc".
  • Objetivo: acumular experiencia real de mercado, aprender, perfeccionarse.
  • Protección de capital educativo: si el WR cae < 40% en 10 trades → pausa
    automática de 3 minutos para evitar pérdidas en espiral (modo productivo).
  • Anti-tilt: 3 pérdidas seguidas → pausa 90s.
  • Circuit breaker fuerte: 5 pérdidas en 8 trades → pausa 5 min (sesión tóxica).

MODO REAL (dinero real):
  • ÚNICA condición de activación: el usuario pulsa "Auto" (auto-click) Y además
    tiene activado el modo autónomo. AMBOS son necesarios.
  • Sin esas dos condiciones activas, Litch NUNCA ejecuta clicks reales aunque
    el usuario haya apagado el modo práctica.
  • Al desactivar práctica, el sistema vuelve a modo análisis (shadow): sólo
    predice y muestra señales, no ejecuta. Para volver a operar, el usuario
    debe activar Auto de nuevo explícitamente.

RESUMEN: Práctica = aprender. Real = Auto-Click activo. Sin Auto = solo análisis.
═══════════════════════════════════════════════════════════════════════════════
"""
import threading
import time

VOTOS_MIN  = 2       # mínimo de votos base (se adapta)
PROB_MIN   = 0.505   # umbral mínimo base
COOLDOWN   = 6       # segundos entre trades base

# Niveles de dificultad progresiva
_NIVELES = {
    "principiante": {"votos": 2, "prob": 0.505, "cd": 6,  "wr_objetivo": 0.55},
    "intermedio":   {"votos": 3, "prob": 0.520, "cd": 8,  "wr_objetivo": 0.58},
    "avanzado":     {"votos": 4, "prob": 0.535, "cd": 10, "wr_objetivo": 0.62},
    "experto":      {"votos": 5, "prob": 0.552, "cd": 12, "wr_objetivo": 0.65},
}
_PROGRESION_WR  = 0.62   # WR sostenido (últimos 20) para subir de nivel
_DESCENSO_WR    = 0.44   # WR sostenido para bajar de nivel
_ANTI_TILT_N    = 3      # pérdidas seguidas → pausa anti-tilt
_ANTI_TILT_SECS = 90     # duración de la pausa anti-tilt

# ── Circuit breaker productivo ────────────────────────────────────────────────
_CB_WR_UMBRAL    = 0.40   # WR < 40% en últimos 10 trades → pausa
_CB_DURACION_1   = 180    # pausa 3 min (primera activación)
_CB_DURACION_2   = 300    # pausa 5 min (segunda activación = sesión tóxica)
_CB_VENTANA      = 10     # trades a evaluar en el circuit breaker
_CB_FUERTE_L     = 5      # 5 pérdidas en 8 trades → circuit breaker fuerte
_CB_FUERTE_V     = 8

_instancia = None


class ModoPractica:
    """Modo de práctica autónoma para cuenta DEMO (v3)."""

    def __init__(self, app):
        self.app       = app
        self._broker_practica = ""
        self._activo   = False
        self._ultimo_t = 0.0
        self._n_trades = 0
        self._n_wins   = 0
        self._n_losses = 0
        self._lock     = threading.Lock()
        # Umbrales adaptativos
        self._nivel     = "principiante"
        self._votos_min = VOTOS_MIN
        self._prob_min  = PROB_MIN
        self._cooldown  = COOLDOWN
        # Historial de resultados para ajuste adaptativo
        self._hist_resultados: list[str] = []
        # Anti-tilt
        self._racha_loss_actual  = 0
        self._tilt_hasta: float  = 0.0    # timestamp fin de pausa anti-tilt
        # Circuit breaker productivo
        self._cb_hasta: float    = 0.0    # timestamp fin de circuit breaker
        self._cb_activaciones    = 0      # conteo de activaciones en sesión
        # Rachas máximas registradas
        self._max_racha_win  = 0
        self._max_racha_loss = 0
        self._racha_win_act  = 0
        # Timing de sesión
        self._ts_inicio: float   = 0.0
        # Hito de progreso (voz cada 10 trades)
        self._ultimo_hito_voz = 0
        # P&L equivalente estimado (monto/payout de config)
        self._pl_ganancia: float   = 0.0
        self._pl_perdida: float    = 0.0
        # Re-entrada conservadora post circuit-breaker (+1 voto por N trades)
        self._cb_entradas_conserv: int = 0

    # ── Estado ────────────────────────────────────────────────────────────────

    @property
    def activo(self) -> bool:
        return self._activo

    @staticmethod
    def _broker_del_usuario(app) -> str:
        """¿En qué broker está trabajando el usuario AHORA?

        Litch no elige el broker: lo elige quien está delante. Si hay una
        ventana de Trader Workstation abierta, es ahí donde se practica —
        aunque IQ Option también esté abierto, aunque la calibración vieja
        apunte a otro sitio.

        Antes esto no se preguntaba: «modo práctica» arrancaba el motor de
        opciones binarias contra IQ Option pasara lo que pasara. El usuario
        tenía IBKR delante y Litch se ponía a operar en otra plataforma.
        """
        try:
            from . import vision_tws as _vt
            if _vt.ventana_tws():
                return "ibkr"
        except Exception:
            pass
        try:
            if app.mem.get("config", {}).get("broker_visual") == "tws":
                return "ibkr"
        except Exception:
            pass
        return "iq"

    def activar(self) -> None:
        # ── ¿Dónde quiere practicar el usuario? ─────────────────────────────
        _broker = self._broker_del_usuario(self.app)
        if _broker == "ibkr":
            self.app.log("[Practica] Trader Workstation detectado. La "
                         "práctica va a IBKR, no a IQ Option.")
            try:
                from . import practica_ibkr as _pi
                _pi.activar(self.app)

                # ── ESTO FALTABA, Y ERA TODO EL PROBLEMA ────────────────
                # Antes se hacía `return` aquí sin marcar `_activo`. La
                # práctica de IBKR arrancaba de verdad, pero para el resto
                # de Litch el modo práctica seguía APAGADO: la interfaz no
                # encendía el botón, el motor no relajaba sus filtros, la
                # meta diaria lo contaba como operación real y el señor
                # veía que "no se activa".
                #
                # Está en práctica. Que sea en otro bróker no lo cambia.
                with self._lock:
                    self._activo    = True
                    self._ts_inicio = time.time()
                    self._tilt_hasta = 0.0
                    self._racha_loss_actual = 0
                    self._racha_win_act     = 0
                self._broker_practica = "ibkr"
                try:
                    self.app.mem["config"]["practica_on_save"] = True
                    self.app.mem["config"]["practica_broker"]  = "ibkr"
                    from . import memoria as _mem_mod
                    _mem_mod.guardar(self.app.mem)
                except Exception:
                    pass
                # Que el botón se encienda: sin esto el señor no tiene
                # forma de saber que sí está funcionando.
                self._actualizar_ui(True)
                self.app.log("[Practica] MODO PRACTICA ACTIVADO — bróker: "
                             "Interactive Brokers (aprendizaje sin operar).")
                return          # NO se arranca el motor de binarias
            except Exception as _e_pi:
                self.app.log(f"[Practica] No pude arrancar la práctica de "
                             f"IBKR: {_e_pi}")
                self.app.decir("Veo Interactive Brokers abierto pero no "
                               "consigo arrancar la práctica ahí. No voy a "
                               "ponerme a operar en IQ Option en su lugar: "
                               "no era eso lo que me pidió.")
                return

        self._broker_practica = "iq"

        with self._lock:
            self._activo    = True
            self._ts_inicio = time.time()
            self._tilt_hasta = 0.0
            self._racha_loss_actual = 0
            self._racha_win_act     = 0
        try:
            self.app.mem["config"]["practica_on_save"] = True
            from . import memoria as _mem_mod
            _mem_mod.guardar(self.app.mem)
        except Exception:
            pass
        cfg = self.app.mem.get("config", {})
        tiene_region   = bool(cfg.get("region_grafico"))
        tiene_botones  = bool(cfg.get("boton_verde")) and bool(cfg.get("boton_rojo"))
        tipo_cuenta    = cfg.get("tipo_cuenta", "demo")
        if tipo_cuenta == "real":
            self.app.log(
                "[Practica] ATENCION: Practica activada en CUENTA REAL. "
                "Trades van a dinero verdadero. Di 'cuenta demo' para practicar sin riesgo.")
        nivel_cfg = _NIVELES[self._nivel]
        self.app.log("[Practica] MODO PRACTICA ACTIVADO")
        self.app.log(f"[Practica] Nivel={self._nivel.upper()} | "
                     f"votos>={nivel_cfg['votos']} | "
                     f"prob>={nivel_cfg['prob']:.3f} | "
                     f"cooldown={nivel_cfg['cd']}s | "
                     f"objetivo WR={nivel_cfg['wr_objetivo']:.0%}")
        self.app.log(f"[Practica] Calibracion: region={'OK' if tiene_region else 'FALTA'} | "
                     f"botones={'OK' if tiene_botones else 'FALTA'}")

        if not getattr(self.app, "trading_on", False):
            try:
                self.app.set_trading(True, hablar=False)
                self.app.log("[Practica] Trading activado automaticamente.")
            except Exception:
                self.app.log("[Practica] Activa el boton Trading manualmente.")

        cfg2 = self.app.mem.get("config", {})
        if not (cfg2.get("boton_verde") and cfg2.get("boton_rojo") and cfg2.get("region_grafico")):
            self.app.log("[Practica] Botones no calibrados — detectando IQ Option...")
            threading.Thread(target=self._auto_calibrar,
                             daemon=True, name="PracticaCal").start()
        else:
            self.app.log("[Practica] Botones calibrados. Listo para operar.")

        self.app.decir(
            f"Modo practica activado. Nivel {self._nivel}. "
            "Operare en demo para aprender haciendo. "
            "Anti tilt activo: tras tres perdidas seguidas hare una pausa de noventa segundos.")
        self._actualizar_ui(True)

    def _auto_calibrar(self) -> None:
        """Auto-detecta botones IQ Option y región del gráfico."""
        try:
            from . import vision as vis_mod
            from . import memoria as mem_mod
            res = vis_mod.auto_calibrar_iq()
            if not res:
                self.app.log("[Practica] No detecte IQ Option. Asegurate de que este visible.")
                return
            cfg = self.app.mem["config"]
            n = 0
            if res.get("boton_verde"):
                cfg["boton_verde"] = res["boton_verde"]
                n += 1
                self.app.log(f"[Practica] SUBE detectado: {res['boton_verde']}")
            if res.get("boton_rojo"):
                cfg["boton_rojo"] = res["boton_rojo"]
                n += 1
                self.app.log(f"[Practica] BAJA detectado: {res['boton_rojo']}")
            if res.get("region_grafico"):
                # Si la visión está en pantalla completa, este recorte la
                # encogería en silencio. Ya pasó una vez: el señor la puso
                # en 1920×1080 y minutos después era un rectángulo pequeño
                # otra vez, sin que nadie hubiera tocado nada.
                _permitido = True
                try:
                    from . import vision_total as _vtot
                    _permitido = _vtot.proteger(self.app, "region_grafico",
                                              res["region_grafico"])
                except Exception:
                    pass
                if _permitido:
                    cfg["region_grafico"] = res["region_grafico"]
                    n += 1
                    self.app.log(f"[Practica] Grafico detectado: {res['region_grafico']}")
                else:
                    self.app.log("[Practica] Ignoro el recorte del gráfico: "
                                 "mi visión está en pantalla completa.")
            if n > 0:
                mem_mod.guardar(self.app.mem)
                if n >= 2:
                    self.app.decir("Listo. Detente IQ Option. Empezare a operar en la proxima senal.")
                else:
                    self.app.log("[Practica] Calibracion parcial. Ve a Calibrar para ajustar.")
            else:
                self.app.log("[Practica] No detecte elementos. Ve a Calibrar -> Auto-calibrar.")
        except Exception as e:
            self.app.log(f"[Practica] Error auto-calibracion: {e}")

    def desactivar(self) -> None:
        with self._lock:
            self._activo = False
        try:
            self.app.mem["config"].pop("practica_on_save", None)
            from . import memoria as _mem_mod
            _mem_mod.guardar(self.app.mem)
        except Exception:
            pass
        # Resumen de sesión al desactivar
        resumen = self._resumen_sesion()
        self.app.log(f"[Practica] Sesion finalizada: {resumen}")
        self.app.decir(resumen[:220])
        self._actualizar_ui(False)
        # ── Aviso sobre el estado tras salir de práctica ──────────────────────
        # Si Auto-Click + Autónomo están activos → opera con dinero real.
        # Si no → modo análisis puro (shadow), no ejecuta clicks.
        _autoclick_on = getattr(self.app, "autoclick_on", False)
        _autonomo_on  = getattr(self.app, "modo_autonomo", False)
        # HONESTIDAD: el dinero es real SOLO si la cuenta registrada es real.
        _es_real = (self.app.mem["config"].get("tipo_cuenta", "demo") == "real")
        _dinero  = "dinero real" if _es_real else "dinero DEMO de practica"
        if _autoclick_on and _autonomo_on:
            self.app.log(
                f"[Practica] Transición a modo autónomo — auto-click activo. "
                f"Operando con {_dinero}.")
            try:
                self.app.decir(
                    f"Practica desactivada. Auto clic esta activo, senor: "
                    f"ahora operare con {_dinero}. Mantengo la misma disciplina.")
            except Exception:
                pass
        else:
            self.app.log(
                f"[Practica] Modo analisis. Auto-click inactivo — solo observo. "
                f"Active el boton Auto para operar con {_dinero}.")
            try:
                self.app.decir(
                    "Practica desactivada. Modo analisis activo: observo y predigo "
                    "pero no ejecuto. Para operar, active el boton Auto.")
            except Exception:
                pass

    def toggle(self) -> bool:
        if self._activo:
            self.desactivar()
        else:
            self.activar()
        return self._activo

    def _actualizar_ui(self, estado: bool) -> None:
        try:
            self.app.interfaz.root.after(
                0, lambda: self.app.interfaz._actualizar_banner_practica(estado))
        except Exception:
            pass

    # ── Decisión de ejecución ─────────────────────────────────────────────────

    def puede_ejecutar(self, votos: int, prob: float) -> tuple:
        """Devuelve (puede: bool, razon: str)."""
        if not self._activo:
            return False, "practica inactiva"
        ahora = time.time()
        # Circuit breaker productivo: pausa cuando el mercado está tóxico
        if ahora < self._cb_hasta:
            restante = int(self._cb_hasta - ahora)
            return False, f"pausa productiva: {restante}s (WR bajo, espera momento mejor)"
        # Anti-tilt: pausa tras racha de pérdidas
        if ahora < self._tilt_hasta:
            restante = int(self._tilt_hasta - ahora)
            return False, f"pausa anti-tilt: {restante}s"
        _extra_v = 1 if self._cb_entradas_conserv > 0 else 0
        _min_req = self._votos_min + _extra_v
        if votos < _min_req:
            sfx = " (+1 cautela post-CB)" if _extra_v else ""
            return False, f"votos {votos}/{_min_req} insuficientes{sfx}"
        if prob < self._prob_min:
            return False, f"prob {prob:.3f} < {self._prob_min:.3f}"
        restante = self._cooldown - (ahora - self._ultimo_t)
        if restante > 0:
            return False, f"cooldown {int(restante)+1}s"
        return True, "OK"

    def registrar_click(self) -> None:
        with self._lock:
            self._ultimo_t = time.time()
            self._n_trades += 1
            if self._cb_entradas_conserv > 0:
                self._cb_entradas_conserv -= 1

    def registrar_resultado(self, acierto: bool) -> None:
        with self._lock:
            if acierto:
                self._n_wins += 1
                self._racha_win_act      += 1
                self._racha_loss_actual   = 0
                if self._racha_win_act > self._max_racha_win:
                    self._max_racha_win = self._racha_win_act
            else:
                self._n_losses += 1
                self._racha_loss_actual += 1
                self._racha_win_act      = 0
                if self._racha_loss_actual > self._max_racha_loss:
                    self._max_racha_loss = self._racha_loss_actual
            self._hist_resultados.append("WIN" if acierto else "LOSS")
            if len(self._hist_resultados) > 60:
                self._hist_resultados = self._hist_resultados[-60:]
            racha_loss_snap = self._racha_loss_actual
            n_trades_snap   = self._n_trades

        # P&L equivalente estimado (usa config en tiempo real)
        _cfg_pl   = self.app.mem.get("config", {})
        _monto_pl = float(_cfg_pl.get("monto_base") or _cfg_pl.get("monto") or 10.0)
        _pay_pl   = float(_cfg_pl.get("payout", 0.82))
        if acierto:
            self._pl_ganancia += _monto_pl * _pay_pl
        else:
            self._pl_perdida  += _monto_pl

        # Anti-tilt: activar pausa (fuera del lock para no bloquear)
        if racha_loss_snap >= _ANTI_TILT_N:
            self._tilt_hasta        = time.time() + _ANTI_TILT_SECS
            self._racha_loss_actual = 0   # resetear contador
            try:
                self.app.log(
                    f"[Practica] Anti-tilt: {racha_loss_snap} perdidas seguidas. "
                    f"Pausa de {_ANTI_TILT_SECS}s para evitar operar en modo reactivo.")
                self.app.decir(
                    f"Tres perdidas seguidas. Pausa de {_ANTI_TILT_SECS} segundos. "
                    "Respira y espera. El mercado no va a ningún lado.")
            except Exception:
                pass

        # ── Circuit breaker productivo ─────────────────────────────────────────
        with self._lock:
            hist_snap = list(self._hist_resultados[-_CB_FUERTE_V:])

        # Circuito 1: WR < 40% en últimos 10 trades
        if len(self._hist_resultados) >= _CB_VENTANA:
            ventana10 = self._hist_resultados[-_CB_VENTANA:]
            wr10 = sum(1 for r in ventana10 if r == "WIN") / _CB_VENTANA
            if wr10 < _CB_WR_UMBRAL and time.time() >= self._cb_hasta:
                self._cb_activaciones += 1
                dur = _CB_DURACION_2 if self._cb_activaciones >= 2 else _CB_DURACION_1
                self._cb_hasta = time.time() + dur
                self._cb_entradas_conserv = 5   # +1 voto mínimo en próximos 5 trades
                try:
                    self.app.log(
                        f"[Practica] Circuit breaker: WR={wr10:.0%} en últimos "
                        f"{_CB_VENTANA} trades — pausa {dur//60} min (activación #{self._cb_activaciones}).")
                    if self._cb_activaciones >= 2:
                        self.app.decir(
                            f"Señor, el mercado está muy en contra hoy. "
                            f"WR del {wr10:.0%} — pauso cinco minutos. "
                            "Cuando el mercado no respeta los patrones, no operar ES la estrategia.")
                    else:
                        self.app.decir(
                            f"Pausa productiva de tres minutos. "
                            f"WR del {wr10:.0%} — necesito que el mercado se estabilice "
                            "antes de continuar. No es tilt, es disciplina.")
                except Exception:
                    pass

        # Circuito 2: 5 pérdidas en 8 últimos trades → sesión tóxica
        if (len(hist_snap) >= _CB_FUERTE_V
                and sum(1 for r in hist_snap if r == "LOSS") >= _CB_FUERTE_L
                and time.time() >= self._cb_hasta):
            self._cb_activaciones += 1
            self._cb_hasta = time.time() + _CB_DURACION_2
            self._cb_entradas_conserv = 5   # +1 voto mínimo en próximos 5 trades
            try:
                self.app.log(
                    f"[Practica] Circuit breaker fuerte: {_CB_FUERTE_L}/{_CB_FUERTE_V} perdidas — "
                    f"sesión tóxica. Pausa de 5 min.")
                self.app.decir(
                    "Señor, cinco de los últimos ocho trades han sido pérdidas. "
                    "Hay algo estructural en el mercado ahora que no puedo predecir. "
                    "Pauso cinco minutos. Quizás convenga cambiar de activo.")
            except Exception:
                pass

        # Hito de progreso: hablar cada 10 trades
        if n_trades_snap > 0 and n_trades_snap % 10 == 0 and n_trades_snap != self._ultimo_hito_voz:
            self._ultimo_hito_voz = n_trades_snap
            threading.Thread(target=self._anunciar_progreso,
                             daemon=True, name="PracticaHito").start()

        self._ajustar_umbrales()

    def _anunciar_progreso(self) -> None:
        """Anuncia el progreso por voz cada 10 trades."""
        try:
            s = self.stats()
            objetivo = _NIVELES[self._nivel]["wr_objetivo"]
            distancia = s["wr"] / 100 - objetivo
            if distancia >= 0:
                estado = f"objetivo de {objetivo:.0%} superado. Excelente trabajo."
            else:
                estado = f"objetivo de {objetivo:.0%} a {abs(distancia):.0%} de distancia."
            pl_net = self._pl_ganancia - self._pl_perdida
            pl_str = (f"P L equivalente: {'mas' if pl_net >= 0 else 'menos'} "
                      f"{abs(pl_net):.2f} dolares. "
                      if (self._pl_ganancia + self._pl_perdida) > 0 else "")
            self.app.decir(
                f"Reporte de practica: {s['trades']} trades. "
                f"Win rate {s['wr']:.0f}%. {estado} "
                f"{pl_str}"
                f"Nivel actual: {self._nivel}.")
        except Exception:
            pass

    def _resumen_sesion(self) -> str:
        """Genera resumen completo de la sesión para log y voz."""
        s   = self.stats()
        dur = int(time.time() - self._ts_inicio) // 60 if self._ts_inicio else 0
        objetivo = _NIVELES[self._nivel]["wr_objetivo"]
        logro    = "OBJETIVO SUPERADO" if (s["wr"] / 100) >= objetivo else "debajo del objetivo"
        pl_net   = s["pl_neto"]
        pl_txt   = f" | P&L≈${pl_net:+.2f}" if (s["pl_ganancia"] + s["pl_perdida"]) > 0 else ""
        return (f"Sesion practica {dur}min — "
                f"{s['trades']} trades, W={s['wins']} L={s['losses']} "
                f"WR={s['wr']:.0f}% ({logro}){pl_txt} | "
                f"mejor racha win={self._max_racha_win} | "
                f"peor racha loss={self._max_racha_loss} | "
                f"nivel={self._nivel.upper()}")

    def _ajustar_umbrales(self) -> None:
        """Adapta nivel de dificultad y umbrales según rendimiento reciente."""
        with self._lock:
            hist = list(self._hist_resultados)
        ventana = hist[-20:]
        n = len(ventana)
        if n < 10:
            return

        wr             = sum(1 for r in ventana if r == "WIN") / n
        nivel_ant      = self._nivel
        niveles_orden  = ["principiante", "intermedio", "avanzado", "experto"]
        idx_actual     = niveles_orden.index(self._nivel)

        # Progresión de nivel
        if wr >= _PROGRESION_WR and idx_actual < len(niveles_orden) - 1:
            nuevo_nivel     = niveles_orden[idx_actual + 1]
            self._nivel     = nuevo_nivel
            cfg_n           = _NIVELES[nuevo_nivel]
            self._votos_min = cfg_n["votos"]
            self._prob_min  = cfg_n["prob"]
            self._cooldown  = cfg_n["cd"]
            self.app.log(
                f"[Practica] Nivel subido: {nivel_ant} → {nuevo_nivel} "
                f"(WR={wr:.0%} sostenido)")
            try:
                self.app.decir(
                    f"Nivel subido a {nuevo_nivel}. "
                    f"Win rate sostenido de {wr:.0%}. Subiendo los estándares.")
            except Exception:
                pass
        # Descenso de nivel
        elif wr < _DESCENSO_WR and idx_actual > 0:
            nuevo_nivel     = niveles_orden[idx_actual - 1]
            self._nivel     = nuevo_nivel
            cfg_n           = _NIVELES[nuevo_nivel]
            self._votos_min = cfg_n["votos"]
            self._prob_min  = cfg_n["prob"]
            self._cooldown  = cfg_n["cd"]
            self.app.log(
                f"[Practica] Nivel bajado: {nivel_ant} → {nuevo_nivel} "
                f"(WR={wr:.0%}, bajo el mínimo)")
        else:
            # Ajuste micro dentro del nivel
            cfg_n = _NIVELES[self._nivel]
            if wr >= 0.58:
                self._votos_min = cfg_n["votos"]
                self._prob_min  = cfg_n["prob"]
                self._cooldown  = cfg_n["cd"]
            elif wr < 0.48:
                self._votos_min = min(cfg_n["votos"] + 1, 5)
                self._prob_min  = min(cfg_n["prob"] + 0.015, 0.57)
                self._cooldown  = min(cfg_n["cd"] + 6, 30)

        if self._nivel != nivel_ant:
            self.app.log(
                f"[Practica] Umbral activo — "
                f"votos≥{self._votos_min} | prob≥{self._prob_min:.3f} | "
                f"cooldown={self._cooldown}s")

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        tot = self._n_wins + self._n_losses
        dur = int(time.time() - self._ts_inicio) if self._ts_inicio else 0
        return {
            "trades":         self._n_trades,
            "wins":           self._n_wins,
            "losses":         self._n_losses,
            "wr":             round(self._n_wins / tot * 100, 1) if tot else 0.0,
            "nivel":          self._nivel,
            "max_racha_win":  self._max_racha_win,
            "max_racha_loss": self._max_racha_loss,
            "duracion_min":   dur // 60,
            "objetivo_wr":    _NIVELES[self._nivel]["wr_objetivo"],
            "en_tilt_pausa":  time.time() < self._tilt_hasta,
            "pl_ganancia":    round(self._pl_ganancia, 2),
            "pl_perdida":     round(self._pl_perdida,  2),
            "pl_neto":        round(self._pl_ganancia - self._pl_perdida, 2),
        }

    def resumen(self) -> str:
        s = self.stats()
        pl_txt = f" | P&L≈${s['pl_neto']:+.2f}" if (s["pl_ganancia"] + s["pl_perdida"]) > 0 else ""
        return (f"Practica {s['nivel'].upper()}: {s['trades']} trades | "
                f"W={s['wins']} L={s['losses']} | "
                f"WR={s['wr']:.0f}% (obj={s['objetivo_wr']:.0%}){pl_txt} | "
                f"racha_win={s['max_racha_win']} racha_loss={s['max_racha_loss']} | "
                f"umbral≥{self._votos_min}v p≥{self._prob_min:.3f} "
                f"cd={self._cooldown}s")


# ── Singleton ─────────────────────────────────────────────────────────────────

def obtener(app=None) -> "ModoPractica | None":
    global _instancia
    if _instancia is None and app is not None:
        _instancia = ModoPractica(app)
    return _instancia
