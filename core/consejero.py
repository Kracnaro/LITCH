"""Consejero proactivo de Litch — habla por iniciativa propia.

Mientras trabajas, Litch observa el contexto (calibración, rachas de
aciertos o fallos, tiempo de sesión, estado del análisis) y de vez en
cuando te ofrece un consejo hablado, con tacto y sin ser pesado:
«Si me permite, señor, yo le recomendaría…».

Reglas: nunca habla más de una vez cada COOLDOWN minutos por iniciativa
propia (los consejos por evento, como tres fallos seguidos, tienen
prioridad). Se puede apagar desde el panel (botón Consejos) o por voz.
"""
import random
import threading
import time

COOLDOWN       = 720    # 12 minutos entre consejos espontáneos generales
COOLDOWN_OCIOSO = 2700  # 45 minutos entre avisos de "estoy ocioso"
REVISAR_CADA   = 60     # segundos entre evaluaciones de contexto (antes 45)


CONSEJOS_GENERALES_ES = [
    "Si me permite un consejo, señor: en el demo conviene probar una sola "
    "estrategia a la vez. Así sabremos qué funciona de verdad.",
    "Yo le recomendaría fijarse más en la tasa de acierto que en una operación "
    "suelta. Una muestra grande dice la verdad; una operación, no.",
    "Permítame sugerirle algo: las mejores decisiones se toman sin prisa. Si "
    "duda, esperar una vela más nunca es mala idea.",
    "Un apunte profesional, señor: registre lo que siente al operar. La "
    "disciplina emocional vale más que cualquier indicador.",
    "Le aconsejo revisar mi reporte de vez en cuando. Diga «Litch, estado» y "
    "le muestro mi precisión real, sin maquillaje.",
    "Si me permite: cuando el mercado está muy alternante, mi consejo es no "
    "operar. La ausencia de patrón también es información.",
]

CONSEJOS_GENERALES_EN = [
    "If I may, sir: on the demo it's wise to test one strategy at a time, so "
    "we know what truly works.",
    "I'd recommend watching the hit rate, not a single trade. Large samples "
    "tell the truth; one trade does not.",
    "Allow me a suggestion: the best decisions are unhurried. When in doubt, "
    "waiting one more candle never hurts.",
    "A professional note, sir: when the market alternates wildly, my advice "
    "is not to trade. The absence of a pattern is also information.",
]


class Consejero(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True, name="LitchConsejero")
        self.app = app
        self._detener = False
        self._ultimo_consejo = 0.0
        self._ultimo_ocioso  = 0.0   # cooldown separado para mensaje "estoy ocioso"
        self._ult_aciertos = 0
        self._ult_fallos = 0
        self._ultimo_consejo_racha = 0.0   # cooldown para consejos de racha
        self._aviso_calibrar = False
        self._ultimo_obs_bayesiana = 0.0   # cooldown 4h entre observaciones bayesianas
        self._ultima_clave_bayesiana = ""  # evitar repetir la misma condición

    def parar(self):
        self._detener = True

    # ------------------------------------------------------------------
    def run(self):
        time.sleep(90)  # deja arrancar todo con calma
        while not self._detener:
            try:
                if self.app.activo and getattr(self.app, "consejos_on", True):
                    self._evaluar()
            except Exception as e:
                print(f"[Consejero] {e}")
            time.sleep(REVISAR_CADA)

    # ------------------------------------------------------------------
    def _decir(self, texto, forzar=False):
        ahora = time.time()
        if not forzar and ahora - self._ultimo_consejo < COOLDOWN:
            return False
        self._ultimo_consejo = ahora
        self.app.decir(texto)
        return True

    def _evaluar(self):
        a = self.app
        est = a.mem["estadisticas"]
        aciertos = est.get("aciertos", 0)
        fallos = est.get("fallos", 0)

        # 1) Eventos prioritarios: racha de fallos o de aciertos reciente
        nuevos_fallos = fallos - self._ult_fallos
        nuevos_aciertos = aciertos - self._ult_aciertos
        self._ult_fallos = fallos
        self._ult_aciertos = aciertos
        # Cooldown propio para consejos de racha: en rachas largas (demo/OTC)
        # antes se repetían sin parar, gastando voz y CPU. Máx 1 cada 10 min.
        _COOLDOWN_RACHA = 600
        _puede_racha = (time.time() - self._ultimo_consejo_racha) >= _COOLDOWN_RACHA
        if nuevos_fallos >= 3 and _puede_racha:
            self._ultimo_consejo_racha = time.time()
            self._decir(a.txt(
                "Señor, llevamos tres señales fallidas seguidas. Yo le recomendaría "
                "pausar el análisis unos minutos: cuando el mercado no respeta los "
                "patrones, la jugada profesional es no operar.",
                "Sir, three missed signals in a row. I'd recommend pausing for a few "
                "minutes: when the market ignores its patterns, the professional move "
                "is not to trade."), forzar=True)
            return
        if nuevos_aciertos >= 3 and _puede_racha:
            self._ultimo_consejo_racha = time.time()
            self._decir(a.txt(
                "Tres aciertos seguidos, señor. Mi consejo: no aumente el ritmo por "
                "euforia. La ley de Littlewood dice que las rachas son normales; la "
                "disciplina es lo que no lo es.",
                "Three hits in a row, sir. My advice: don't speed up out of euphoria. "
                "Littlewood's law says streaks are normal; discipline is what's rare."),
                forzar=True)
            return

        # 2) Falta calibración y el trading está apagado
        if not a.mem["config"].get("region_grafico") and not self._aviso_calibrar:
            self._aviso_calibrar = True
            self._decir(a.txt(
                "Permítame una sugerencia, señor: aún no hemos calibrado el gráfico "
                "de IQ Option. Abra el menú Calibrar y en un minuto quedo listo para "
                "observar el mercado por usted.",
                "Allow me a suggestion, sir: we haven't calibrated the IQ Option chart "
                "yet. Open the Calibrate menu and within a minute I'll be watching the "
                "market for you."))
            return

        # 3) Trading apagado con calibración lista — cooldown propio de 45 min
        ahora = time.time()
        if (a.mem["config"].get("region_grafico") and not a.trading_on
                and ahora - self._ultimo_ocioso > COOLDOWN_OCIOSO):
            self._ultimo_ocioso = ahora
            if self._decir(a.txt(
                    "Señor, tengo el gráfico calibrado y estoy ocioso. ¿Le parece si "
                    "activo el análisis y voy memorizando patrones mientras usted "
                    "hace otras cosas?",
                    "Sir, the chart is calibrated and I'm idle. Shall I start the "
                    "analysis and memorize patterns while you do other things?")):
                return

        # 4) Conciencia Litch: calibración o patrón horario notable
        con = getattr(a, "conciencia", None)
        if con is not None:
            try:
                # 4a) Calibración pobre — aviso cuando meta.ece() > 0.12 con
                # suficiente muestra. Cooldown LARGO propio (1 hora): la
                # condición persiste mientras se recalibra, y repetirla cada
                # 12 min es ruido inútil. Se dice una vez y se calla.
                _ahora_ece = time.time()
                if (con.meta.n_trades() >= 20 and con.meta.ece() > 0.12
                        and _ahora_ece - getattr(self, "_ultimo_aviso_ece", 0.0) >= 3600):
                    if self._decir(a.txt(
                            f"Señor, mi calibración probabilística está baja: "
                            f"ECE={con.meta.ece():.2f}. Significa que mis estimaciones de confianza "
                            "no coinciden bien con los resultados reales. Le pido paciencia "
                            "mientras ajusto mis pesos internos.",
                            f"Sir, my probabilistic calibration is low: "
                            f"ECE={con.meta.ece():.2f}. My confidence estimates don't match results "
                            "well. Please allow me time to adjust my internal weights.")):
                        self._ultimo_aviso_ece = _ahora_ece
                        return
                # 4b) Mejores condiciones bayesianas — cooldown 4h y no repetir misma clave
                _ahora_b = time.time()
                _COOLDOWN_BAYES = 14400  # 4 horas entre observaciones bayesianas
                if (_ahora_b - self._ultimo_obs_bayesiana > _COOLDOWN_BAYES
                        and con.meta.n_trades() >= 30):
                    top = con.creencias.top(3)
                    if top:
                        mejor = top[0]
                        p_top = mejor["p"]
                        clave_nueva = mejor["clave"]
                        if p_top > 0.63 and clave_nueva != self._ultima_clave_bayesiana:
                            clave_p = clave_nueva.split("|")
                            hora_p  = clave_p[1] if len(clave_p) > 1 else "?"
                            dir_p   = clave_p[3] if len(clave_p) > 3 else "?"
                            dir_txt = ("SUBE" if dir_p == "V" else "BAJA") if dir_p in ("V","R") else dir_p
                            if self._decir(a.txt(
                                    f"Una observación histórica, señor: en el período de las {hora_p}h "
                                    f"con señal de {dir_txt}, mi tasa de acierto bayesiana es del "
                                    f"{p_top:.0%} ({mejor['obs']:.0f} muestras). Vale la pena tenerlo en cuenta.",
                                    f"A historical observation, sir: around {hora_p}h with {dir_txt} signal, "
                                    f"my Bayesian win rate is {p_top:.0%} ({mejor['obs']:.0f} samples). "
                                    "Worth keeping in mind.")):
                                self._ultimo_obs_bayesiana = _ahora_b
                                self._ultima_clave_bayesiana = clave_nueva
                                return
            except Exception:
                pass

        # 5) Consejo general espaciado — sin repetir el último elegido
        consejos = (CONSEJOS_GENERALES_EN if a.idioma == "en"
                    else CONSEJOS_GENERALES_ES)
        _ult = getattr(self, "_ult_consejo_gen", "")
        _opciones = [c for c in consejos if c != _ult] or consejos
        _elegido = random.choice(_opciones)
        if self._decir(_elegido):
            self._ult_consejo_gen = _elegido

    # ------------------------------------------------------------------
    def consejo_inmediato(self):
        """Consejo a petición («Litch, aconséjame»)."""
        a = self.app
        est = a.mem["estadisticas"]
        total = est.get("aciertos", 0) + est.get("fallos", 0)
        if not a.mem["config"].get("region_grafico"):
            return a.txt(
                "Mi recomendación inmediata, señor: calibremos el gráfico del demo. "
                "Sin ojos sobre el mercado no puedo ayudarle a especular.",
                "My immediate recommendation, sir: let's calibrate the demo chart. "
                "Without eyes on the market I can't help you trade.")
        if total < 20:
            return a.txt(
                "Yo le aconsejaría paciencia, señor: aún tengo poca evidencia "
                f"({total} señales verificadas). Deje el análisis activo un buen rato; "
                "la ley de los grandes números trabaja a nuestro favor.",
                f"I'd advise patience, sir: I only have {total} verified signals. Keep "
                "the analysis running; the law of large numbers works for us.")
        precision = est.get("aciertos", 0) / total
        if precision >= 0.58:
            return a.txt(
                f"Con una precisión histórica del {precision:.0%}, mi consejo es "
                "mantener la estrategia exactamente como está y no tocarla. Lo que "
                "funciona no se interrumpe, señor.",
                f"With {precision:.0%} historical accuracy, my advice is to keep the "
                "strategy exactly as it is. Don't fix what works, sir.")
        return a.txt(
            f"Mi precisión histórica es del {precision:.0%}, señor. Le recomendaría "
            "dejarme en modo sugerencia, sin auto-click, hasta que la fusión "
            "bayesiana muestre ventaja sostenida. Honestidad ante todo.",
            f"My historical accuracy is {precision:.0%}, sir. I'd recommend keeping me "
            "in suggestion mode, no auto-click, until the Bayesian fusion shows a "
            "sustained edge. Honesty first.")
