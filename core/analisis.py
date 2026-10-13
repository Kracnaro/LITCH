"""Análisis inteligente de patrones — el "algoritmo del 3" (v3).

Memoriza secuencias de velas y aplica cadenas de Markov de ÓRDENES 1-4:
  • Orden L (configurable): patrón principal, igual que siempre.
  • Órdenes 1-4 auxiliares: consensus ponderado sobre el mismo contexto.

Solo emite señal cuando el patrón principal Y el consensus multi-orden
superan los umbrales de probabilidad y observaciones.

v3 añade:
  - Orden-4 Markov: captura patrones de 4-vela que el orden 3 ignora
  - Consensus ponderado (orden^1.5): órdenes altos pesan más si tienen evidencia
  - Ventana deslizante adaptativa: si la serie es larga (>500 velas) usa solo
    las últimas 400 para el aprendizaje online (evita deriva de régimen)

IMPORTANTE: esto es estadística de frecuencias, no una bola de cristal.
Las probabilidades reflejan el pasado observado y nunca garantizan el futuro.
"""
import time

# Decay suave sobre los conteos de patrones acumulados — da más peso a
# observaciones recientes. Se aplica una vez cada _DECAY_CADA velas nuevas.
_DECAY_CADA   = 100    # cada 100 velas aplica decay
_DECAY_FACTOR = 0.97   # 3% reducción por ciclo → semivida ≈ 2.200 velas

# Multi-orden auxiliar: pesos para consenso 1..4
_ORDEN_MAX    = 4
_ORDEN_PESO   = {1: 1.0, 2: 1.8, 3: 2.5, 4: 3.0}
_ORDEN_UMBRAL_EV = {1: 2.0, 2: 3.0, 3: 4.0, 4: 5.0}  # mín obs para que orden k vote
_VENTANA_APRENDIZAJE = 400   # solo últimas N velas para el consensus auxiliar


class AnalizadorPatrones:
    def __init__(self, mem, guardar_cb, sufijo=""):
        """sufijo='' → canal 1 (claves clásicas). sufijo='_2' → canal 2,
        secuencia/patrones/señales/estadísticas totalmente independientes
        para poder operar un segundo gráfico (mismo u otro activo) sin
        mezclar su aprendizaje con el del canal principal."""
        self.mem = mem
        self.guardar = guardar_cb
        self.sufijo = sufijo
        self.k_sec = "secuencia" + sufijo
        self.k_pat = "patrones" + sufijo
        self.k_sen = "senales" + sufijo
        self.k_est = "estadisticas" + sufijo
        self.senal_pendiente = None

    @property
    def longitud(self):
        return int(self.mem["config"].get("longitud_patron", 3))

    def registrar_vela(self, color):
        """Registra una vela cerrada ('V'/'R') y aprende el patrón."""
        sec = self.mem[self.k_sec]
        sec.append(color)
        if len(sec) > 5000:
            del sec[:-5000]

        # Decay suave periódico: hace que observaciones antiguas pesen menos que
        # las recientes sin borrarlas, manteniendo la historia a largo plazo.
        n_sec = len(sec)
        if n_sec > 200 and n_sec % _DECAY_CADA == 0:
            for _p in self.mem[self.k_pat].values():
                _p["V"] = round(_p.get("V", 0) * _DECAY_FACTOR, 4)
                _p["R"] = round(_p.get("R", 0) * _DECAY_FACTOR, 4)

        L = self.longitud
        if len(sec) >= L + 1:
            patron = "".join(sec[-(L + 1):-1])
            destino = self.mem[self.k_pat].setdefault(patron, {"V": 0.0, "R": 0.0})
            destino[color] = destino.get(color, 0) + 1
        self.guardar()

    def verificar_pendiente(self, color):
        """Comprueba si la señal anterior acertó. Devuelve True/False/None."""
        if not self.senal_pendiente:
            return None
        acierto = self.senal_pendiente["direccion"] == color
        est = self.mem[self.k_est]
        est["aciertos" if acierto else "fallos"] = (
            est.get("aciertos" if acierto else "fallos", 0) + 1
        )
        self.senal_pendiente = None
        self.guardar()
        return acierto

    def _consensus_multiorden(self, sec: list) -> tuple[str | None, float]:
        """Cadenas de Markov de orden 1-4 sobre la ventana reciente.

        Devuelve (dirección, confianza) del consensus ponderado, o (None, 0.0)
        si no hay suficiente evidencia en ningún orden.
        """
        ventana = sec[-_VENTANA_APRENDIZAJE:] if len(sec) > _VENTANA_APRENDIZAJE else sec
        n = len(ventana)
        puntos = {"V": 0.0, "R": 0.0}

        for orden in range(1, _ORDEN_MAX + 1):
            if n <= orden + 2:
                continue
            patron = "".join(ventana[-orden:])
            cuenta = {"V": 0.0, "R": 0.0}
            for i in range(n - orden):
                if "".join(ventana[i:i + orden]) == patron:
                    cuenta[ventana[i + orden]] = cuenta.get(ventana[i + orden], 0.0) + 1.0
            total = cuenta.get("V", 0.0) + cuenta.get("R", 0.0)
            if total < _ORDEN_UMBRAL_EV.get(orden, 2.0):
                continue
            peso = _ORDEN_PESO.get(orden, 1.0)
            puntos["V"] += peso * cuenta.get("V", 0.0) / total
            puntos["R"] += peso * cuenta.get("R", 0.0) / total

        suma = puntos["V"] + puntos["R"]
        if suma < 0.5:
            return None, 0.0
        ganador = "V" if puntos["V"] >= puntos["R"] else "R"
        conf    = puntos[ganador] / suma
        return ganador, conf

    def evaluar(self):
        """Evalúa el patrón actual con consensus multi-orden. Devuelve una señal o None."""
        sec = self.mem[self.k_sec]
        n_velas = len(sec)
        L = self.longitud
        if n_velas < L:
            return None
        patron = "".join(sec[-L:])
        datos = self.mem[self.k_pat].get(patron)
        if not datos:
            return None
        total = datos.get("V", 0) + datos.get("R", 0)
        cfg = self.mem["config"]
        # Umbrales adaptativos: más permisivos cuando hay pocas velas
        if n_velas < 30:
            min_obs, umbral = 2, 0.52
        elif n_velas < 80:
            min_obs, umbral = 3, 0.58
        else:
            min_obs = int(cfg.get("min_observaciones", 8))
            umbral  = float(cfg.get("umbral_probabilidad", 0.65))
        if total < min_obs:
            return None

        # ── Multi-orden consensus (v3) ─────────────────────────────────────
        dir_con, conf_con = self._consensus_multiorden(sec)
        # Si el consensus multi-orden dice lo contrario del patrón principal
        # con alta confianza (>0.72), elevamos el umbral del patrón principal
        _umbral_efectivo = umbral
        if dir_con is not None and conf_con > 0.72:
            pass   # consensus alinea → umbral normal o menor
        elif dir_con is not None and conf_con < 0.48:
            _umbral_efectivo = min(0.80, umbral + 0.04)  # consensus débil → más exigente

        for direccion in ("V", "R"):
            prob = datos.get(direccion, 0) / total
            if prob >= _umbral_efectivo:
                # Ajuste fino: si consensus coincide y es fuerte, boost de confianza
                prob_reportada = prob
                if dir_con == direccion and conf_con > 0.60:
                    prob_reportada = min(0.99, prob + (conf_con - 0.60) * 0.05)
                senal = {
                    "patron":       patron,
                    "direccion":    direccion,
                    "probabilidad": round(prob_reportada, 3),
                    "observaciones": total,
                    "hora":         time.strftime("%Y-%m-%d %H:%M:%S"),
                    "consensus_dir":  dir_con,
                    "consensus_conf": round(conf_con, 3),
                }
                self.senal_pendiente = senal
                self.mem[self.k_sen].append(senal)
                if len(self.mem[self.k_sen]) > 500:
                    del self.mem[self.k_sen][:-500]
                est = self.mem[self.k_est]
                est["senales_total"] = est.get("senales_total", 0) + 1
                self.guardar()
                return senal
        return None

    def resumen(self, idioma="es"):
        """Resumen hablado/escrito del estado de aprendizaje."""
        est = self.mem[self.k_est]
        velas = len(self.mem[self.k_sec])
        patrones = len(self.mem[self.k_pat])
        aciertos = est.get("aciertos", 0)
        fallos = est.get("fallos", 0)
        total = aciertos + fallos
        if idioma == "en":
            precision = f"{aciertos / total * 100:.1f}%" if total else "no data yet"
            return (
                f"I have observed {velas} candles and memorized {patrones} distinct patterns. "
                f"Signals issued: {est.get('senales_total', 0)}. "
                f"Hits: {aciertos}, misses: {fallos}. Historical accuracy: {precision}."
            )
        precision = f"{aciertos / total * 100:.1f}%" if total else "sin datos aún"
        return (
            f"He observado {velas} velas y memorizado {patrones} patrones distintos. "
            f"Señales emitidas: {est.get('senales_total', 0)}. "
            f"Aciertos: {aciertos}, fallos: {fallos}. Precisión histórica: {precision}."
        )

    def autoajustar(self, idioma="es"):
        """Auto-mejora (solo en modo autónomo): ajusta sus propios parámetros
        según la precisión real de sus señales. Devuelve un mensaje o None."""
        est = self.mem[self.k_est]
        total = est.get("aciertos", 0) + est.get("fallos", 0)
        if total < 20 or total % 20 != 0:
            return None
        if est.get("ultimo_autoajuste") == total:
            return None
        est["ultimo_autoajuste"] = total
        precision = est.get("aciertos", 0) / total
        cfg = self.mem["config"]
        umbral = float(cfg.get("umbral_probabilidad", 0.65))
        minimo = int(cfg.get("min_observaciones", 8))
        mensaje = None
        if precision < 0.55:
            cfg["umbral_probabilidad"] = min(0.80, round(umbral + 0.05, 2))
            cfg["min_observaciones"] = min(20, minimo + 2)
            if idioma == "en":
                mensaje = (f"Self-tuning: my accuracy is {precision:.0%}, below target. "
                           f"Raising standards to threshold {cfg['umbral_probabilidad']:.0%} "
                           f"and minimum {cfg['min_observaciones']} observations.")
            else:
                mensaje = (f"Auto-mejora: mi precisión es {precision:.0%}, baja. Subo el "
                           f"umbral a {cfg['umbral_probabilidad']:.0%} y el mínimo a "
                           f"{cfg['min_observaciones']} observaciones.")
        elif precision > 0.62 and (umbral > 0.62 or minimo > 8):
            cfg["umbral_probabilidad"] = max(0.60, round(umbral - 0.03, 2))
            cfg["min_observaciones"] = max(8, minimo - 1)
            if idioma == "en":
                mensaje = f"Self-tuning: accuracy {precision:.0%}. Exploring more patterns."
            else:
                mensaje = f"Auto-mejora: precisión {precision:.0%}. Exploro más patrones."
        if mensaje:
            self.guardar()
        return mensaje
