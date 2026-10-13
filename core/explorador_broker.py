"""
ExploradBroker — Litch explora y aprende cualquier broker autónomamente.

Cuando el modo autónomo está activo (autoclick_on=True), este módulo:
  • Cada 45s  — captura estado completo del broker: activo, vencimiento,
                balance, payout, indicadores visibles, herramientas.
  • Cada 5min — consulta a Claude o Gemini para entender lo que ve
                y guarda el aprendizaje en base_conocimiento.
  • Cada sesión — adapta periodo_vela al vencimiento real detectado.

Compatibilidad:
  IQ Option, Quotex, Olymp Trade, Pocket Option, Deriv, Binomo,
  MetaTrader, IBKR, Schwab, Tastytrade, y cualquier broker nuevo
  que Litch aprende a identificar por visión.

Aprendizaje autónomo:
  Litch NUNCA deja de aprender. Cada feature del broker que detecta
  se guarda en base_conocimiento.json para usarlo en análisis futuros.
"""

import json
import os
import threading
import time

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

# ── Constantes de ciclo ───────────────────────────────────────────────────────
_CICLO_RAPIDO     = 45     # s entre análisis de estado cuando activo
_CICLO_LENTO      = 120    # s entre análisis cuando inactivo
_CICLO_IA         = 300    # s entre consultas a Claude/Ollama (5 min)
_CICLO_EXPLORACION = 180   # s entre exploraciones activas (click en features)

# Payouts conocidos para reconocerlos por número (sin OCR)
_PAYOUT_MARCAS = [0.80, 0.82, 0.83, 0.85, 0.87, 0.90, 0.92, 0.94, 0.95]


class ExploradBroker(threading.Thread):
    """
    Daemon que aprende el broker mirando la pantalla y registrando conocimiento.

    Uso desde litch.py:
        self.explorador = ExploradBroker(self)
        self.explorador.start()
    """

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchExplorador")
        self.app             = app
        self._estado_actual  = {}    # último estado conocido del broker
        self._t_ultimo_ia    = 0.0   # última consulta a IA
        self._t_ultimo_expl  = 0.0   # última exploración activa
        self._sesion_inicio  = time.time()
        self._discoveries    = []    # lista de descubrimientos nuevos esta sesión
        self._lock           = threading.Lock()

    # ── Loop principal ────────────────────────────────────────────────────────

    def run(self):
        time.sleep(8)   # esperar a que todo arranque
        while True:
            try:
                # Ciclo adaptativo: más frecuente en modo autónomo
                autonomo = getattr(self.app, "autoclick_on", False)
                trading  = getattr(self.app, "trading_on",   False)
                ciclo    = _CICLO_RAPIDO if (autonomo or trading) else _CICLO_LENTO

                self._ciclo_observacion()

                if autonomo and time.time() - self._t_ultimo_ia >= _CICLO_IA:
                    self._consultar_ia_sobre_broker()
                    self._t_ultimo_ia = time.time()

                if autonomo and time.time() - self._t_ultimo_expl >= _CICLO_EXPLORACION:
                    self._explorar_herramientas_broker()
                    self._t_ultimo_expl = time.time()

            except Exception as e:
                try:
                    self.app.log(f"[Explorador] Error ciclo: {e}")
                except Exception:
                    pass
            time.sleep(ciclo)

    # ── Ciclo de observación: leer estado del broker desde pantalla ───────────

    def _ciclo_observacion(self):
        """Lee y actualiza el estado del broker desde la pantalla."""
        from . import vision as vis
        img = vis.capturar_pantalla_completa()
        if img is None:
            return

        estado = self._analizar_imagen_broker(img)
        if not estado:
            return

        # Detectar cambios relevantes respecto al estado previo
        self._detectar_cambios(estado)

        with self._lock:
            self._estado_actual = estado

        # Adaptar periodo_vela automáticamente según vencimiento detectado
        venc = estado.get("vencimiento_seg")
        if venc and isinstance(venc, int) and venc > 0:
            cfg_actual = int(self.app.mem["config"].get("periodo_vela", 60))
            if abs(venc - cfg_actual) > max(5, cfg_actual * 0.20):
                self.app.mem["config"]["periodo_vela"] = venc
                self.app.log(
                    f"[Explorador] Vencimiento ajustado automáticamente: "
                    f"{venc}s (era {cfg_actual}s).")

        # Guardar activo detectado
        activo = estado.get("activo")
        if activo and activo != self.app.mem["config"].get("asset_actual"):
            self.app.mem["config"]["asset_actual"] = activo
            from . import memoria as _mm
            _mm.guardar(self.app.mem)

    # ── Análisis de imagen del broker ─────────────────────────────────────────

    def _analizar_imagen_broker(self, img) -> dict:
        """
        Extrae el estado del broker desde la imagen.

        Usa detección visual de color/brillo (sin OCR) para ubicar regiones
        y usar Claude si está disponible para leer los valores de texto.
        Returns dict con: broker, activo, vencimiento_seg, balance_visible,
                          payout_pct, n_posiciones, indicadores_activos
        """
        if not _NP:
            return {}

        h, w = img.shape[:2]
        estado = {}

        # ── 1. Detectar broker por autocalibracion ───────────────────────────
        broker = self.app.mem["config"].get("broker_activo", "iq_option")
        estado["broker"] = broker

        # ── 2. Detectar payout por color en panel derecho ───────────────────
        # Los brokers muestran el % de beneficio en texto blanco sobre fondo oscuro
        # en el panel lateral derecho. Buscamos zona de texto brillante.
        panel_d   = img[:, int(w * 0.80):, :]
        lum_d     = panel_d.astype(float).mean(axis=2)
        zonas_bri = (lum_d > 200).sum()
        if zonas_bri > 100:
            estado["panel_derecho_activo"] = True

        # ── 3. Detectar P&L y número de posiciones ───────────────────────────
        ctx = {}
        try:
            from . import vision as vis
            ctx = vis.analizar_contexto_iq()
        except Exception:
            pass
        estado["pl_color"]           = ctx.get("pl_color", "desconocido")
        estado["pl_positivo"]        = ctx.get("pl_positivo")
        estado["n_posiciones"]       = ctx.get("posiciones_abiertas", 0)
        estado["botones_visibles"]   = ctx.get("botones_ok", False)

        # ── 4. Detectar indicadores activos por zonas de color específico ─────
        # La zona inferior del gráfico suele tener ventanas de indicadores con
        # líneas de color saturado (RSI, Bollinger, MACD, etc.)
        zona_ind  = img[int(h * 0.70):, int(w * 0.10):int(w * 0.85), :]
        if _NP and zona_ind.size > 0:
            sat = self._calcular_saturacion(zona_ind)
            estado["indicadores_detectados"] = int(sat > 40)  # 1 si hay zona saturada

        # ── 5. Usar Claude para leer texto si está disponible ────────────────
        if getattr(self.app, "usar_claude", False):
            texto = self._leer_pantalla_con_ia(img, "rapido")
            if texto:
                datos_ia = self._parsear_respuesta_ia(texto)
                estado.update(datos_ia)
                # Auto-detectar tipo de cuenta (demo / real) y notificar al app
                tipo_ia = str(datos_ia.get("tipo_cuenta", "")).lower().strip()
                if tipo_ia in ("demo", "real"):
                    cfg_tipo = self.app.mem["config"].get("tipo_cuenta")
                    if cfg_tipo != tipo_ia:
                        self.app.mem["config"]["tipo_cuenta"] = tipo_ia
                        self.app.log(
                            f"[Explorador] Cuenta detectada por IA: {tipo_ia.upper()}")
                        try:
                            self.app.interfaz.root.after(
                                0,
                                lambda t=tipo_ia: self.app.interfaz
                                    ._actualizar_banner_cuenta(t))
                        except Exception:
                            pass

        # ── 6. Detectar vencimiento desde historial de cambio de velas ───────
        # AgenteTrading ya estima esto en _tick_scanner — lo tomamos de ahí
        periodo_estimado = self.app.mem["config"].get("periodo_vela")
        if periodo_estimado:
            estado["vencimiento_seg"] = int(periodo_estimado)

        return estado

    def _calcular_saturacion(self, zona) -> float:
        """Saturación media de la zona (0-100). Alta = indicadores coloridos activos."""
        r = zona[:, :, 2].astype(float)
        g = zona[:, :, 1].astype(float)
        b = zona[:, :, 0].astype(float)
        cmax = np.maximum(np.maximum(r, g), b)
        cmin = np.minimum(np.minimum(r, g), b)
        delta = cmax - cmin
        sat = np.where(cmax > 10, delta / (cmax + 1e-6), 0)
        return float(sat.mean() * 100)

    # ── Leer pantalla con IA ──────────────────────────────────────────────────

    def _leer_pantalla_con_ia(self, img, modo: str = "rapido") -> str:
        """
        Envía un screenshot a Claude para extraer información del broker.

        modo 'rapido'  → solo extrae valores numéricos clave (vencimiento, balance, payout)
        modo 'profundo' → análisis completo de toda la UI
        """
        try:
            import base64, io
            try:
                from PIL import Image as _PIL
                buf = io.BytesIO()
                _PIL.fromarray(img[:, :, ::-1]).save(buf, format="JPEG", quality=72)
                img_b64 = base64.b64encode(buf.getvalue()).decode()
            except ImportError:
                # Sin Pillow: capturar directamente con mss
                from . import vision as vis
                import mss as _mss
                # Usar la imagen recibida ya como numpy
                try:
                    import cv2
                    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 72])
                    if not ok:
                        return ""
                    img_b64 = base64.b64encode(enc.tobytes()).decode()
                except Exception:
                    return ""

            if modo == "rapido":
                prompt = (
                    "Eres el asistente de trading Litch. Analiza esta captura de pantalla "
                    "de un broker de trading binario/opciones.\n\n"
                    "Responde SOLO con este JSON (sin explicación, sin markdown):\n"
                    '{"activo": "par o activo visible", "vencimiento": "valor y unidad ej: 1 min", '
                    '"vencimiento_seg": numero_en_segundos, "balance": "valor con $", '
                    '"payout": porcentaje_numerico, "n_posiciones": numero, '
                    '"broker": "nombre del broker", "indicadores": ["lista de indicadores visibles"], '
                    '"tipo_cuenta": "demo o real segun lo que veas en pantalla (texto demo/practice/real o color)"}'
                )
            else:
                prompt = (
                    "Eres el asistente de trading Litch. Analiza COMPLETAMENTE esta "
                    "captura de pantalla del broker.\n\n"
                    "Describe:\n"
                    "1. Qué broker es y qué tipo de operación muestra\n"
                    "2. Activo, vencimiento, balance, payout visibles\n"
                    "3. Qué indicadores o herramientas técnicas están activas\n"
                    "4. Qué features del broker se pueden ver (timeframes, tipos de orden, etc)\n"
                    "5. Qué posiciones están abiertas y en qué estado (ganando/perdiendo)\n"
                    "6. Cualquier información relevante para el análisis de mercado\n\n"
                    "Formato: JSON estructurado con claves descriptivas."
                )

            from . import mente_claude as mc
            if not mc.disponible():
                return ""

            respuesta = mc.preguntar_con_imagen(
                prompt=prompt,
                imagen_b64=img_b64,
                max_tokens=400 if modo == "rapido" else 800
            )
            return respuesta or ""
        except Exception as e:
            self.app.log(f"[Explorador] Error IA lectura pantalla: {e}")
            return ""

    def _parsear_respuesta_ia(self, texto: str) -> dict:
        """Extrae datos estructurados de la respuesta de la IA."""
        datos = {}
        try:
            # Intentar parsear como JSON
            inicio = texto.find("{")
            fin    = texto.rfind("}") + 1
            if inicio >= 0 and fin > inicio:
                obj = json.loads(texto[inicio:fin])
                if obj.get("activo"):
                    datos["activo"] = str(obj["activo"])
                if obj.get("vencimiento_seg"):
                    try:
                        datos["vencimiento_seg"] = int(obj["vencimiento_seg"])
                    except (ValueError, TypeError):
                        pass
                if obj.get("payout"):
                    try:
                        datos["payout_pct"] = float(obj["payout"]) / 100.0
                    except (ValueError, TypeError):
                        pass
                if obj.get("balance"):
                    datos["balance_texto"] = str(obj["balance"])
                if obj.get("broker"):
                    datos["broker_ia"] = str(obj["broker"])
                if obj.get("indicadores") and isinstance(obj["indicadores"], list):
                    datos["indicadores_activos"] = obj["indicadores"]
                if obj.get("n_posiciones") is not None:
                    try:
                        datos["n_posiciones"] = int(obj["n_posiciones"])
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass
        return datos

    # ── Detectar cambios ──────────────────────────────────────────────────────

    def _detectar_cambios(self, nuevo: dict):
        """Compara con estado previo y reporta/guarda cambios relevantes."""
        previo = self._estado_actual
        if not previo:
            return

        cambios = []

        # Activo cambió
        if (nuevo.get("activo") and
                nuevo.get("activo") != previo.get("activo")):
            cambios.append(f"activo: {previo.get('activo')} → {nuevo.get('activo')}")

        # Vencimiento cambió significativamente
        v_nuevo = nuevo.get("vencimiento_seg", 0)
        v_previo = previo.get("vencimiento_seg", 0)
        if v_nuevo and v_previo and abs(v_nuevo - v_previo) > 10:
            cambios.append(f"vencimiento: {v_previo}s → {v_nuevo}s")

        # Indicadores nuevos detectados
        ind_nuevo  = set(nuevo.get("indicadores_activos", []))
        ind_previo = set(previo.get("indicadores_activos", []))
        nuevos_ind = ind_nuevo - ind_previo
        if nuevos_ind:
            cambios.append(f"nuevos indicadores: {', '.join(nuevos_ind)}")

        if cambios:
            for c in cambios:
                self.app.log(f"[Explorador] Cambio detectado — {c}")
                self._discoveries.append({"ts": time.time(), "cambio": c})
                # INTEGRACIÓN DEL MANUAL: al ver un elemento, consultar qué
                # hace y cómo se usa — Litch no solo lo ve, lo entiende.
                try:
                    from . import conocimiento_brokers as _cb
                    ficha = _cb.funcion_de_elemento(c)
                    if ficha:
                        self.app.log("[Explorador] Manual → "
                                     + ficha.split(chr(10))[1].strip())
                except Exception:
                    pass
                # Guardar en base de conocimiento
                try:
                    bc = getattr(self.app, "conocimiento", None)
                    if bc:
                        bc.guardar(
                            "sesiones", f"cambio_{int(time.time())}",
                            {"broker": nuevo.get("broker"), "cambio": c,
                             "ts": time.strftime("%H:%M:%S")},
                            fuente="explorador")
                except Exception:
                    pass

    # ── Consulta profunda a IA ────────────────────────────────────────────────

    def _consultar_ia_sobre_broker(self):
        """Cada 5 minutos: análisis profundo del broker con IA y guarda conocimiento."""
        from . import vision as vis
        img = vis.capturar_pantalla_completa()
        if img is None:
            return

        self.app.log("[Explorador] Analizando broker con IA (análisis profundo)...")

        texto = self._leer_pantalla_con_ia(img, "profundo")
        if not texto:
            return

        datos = self._parsear_respuesta_ia(texto)

        # Guardar en base de conocimiento
        try:
            bc = getattr(self.app, "conocimiento", None)
            if bc:
                broker = datos.get("broker_ia") or self.app.mem["config"].get("broker_activo", "broker")
                bc.guardar(
                    "brokers",
                    f"{broker}_{time.strftime('%Y%m%d_%H%M')}",
                    {
                        "analisis_ia": texto[:800],
                        "datos_extraidos": datos,
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "sesion_minutos": int((time.time() - self._sesion_inicio) / 60),
                    },
                    fuente="explorador_ia")
                self.app.log(
                    f"[Explorador] Conocimiento guardado sobre {broker}. "
                    f"Indicadores detectados: {datos.get('indicadores_activos', 'N/A')}")
        except Exception as e:
            self.app.log(f"[Explorador] Error guardando conocimiento: {e}")

        # Si detectó un broker nuevo, registrarlo
        broker_ia = datos.get("broker_ia", "").lower().strip()
        if broker_ia and broker_ia not in ("broker", ""):
            self._registrar_broker_nuevo(broker_ia, datos)

        # Actualizar payout en config si la IA lo detectó
        payout = datos.get("payout_pct")
        if payout and 0.5 <= payout <= 0.99:
            self.app.mem["config"]["payout_actual"] = payout

    def _registrar_broker_nuevo(self, nombre: str, datos: dict):
        """Si la IA detecta un broker que no estaba en PERFILES, lo registra."""
        from . import broker_iq as biq
        nombre_clave = nombre.lower().replace(" ", "_").replace(".", "")
        if nombre_clave not in biq.PERFILES:
            venc = datos.get("vencimiento_seg")
            payout = datos.get("payout_pct", 0.85)
            bc = getattr(self.app, "conocimiento", None)
            if bc:
                bc.guardar(
                    "brokers", f"nuevo_{nombre_clave}",
                    {
                        "nombre": nombre,
                        "clave":  nombre_clave,
                        "payout_detectado": payout,
                        "vencimiento_detectado_seg": venc,
                        "nota": "Broker detectado automáticamente por visión IA.",
                        "ts":   time.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    fuente="explorador")
            self.app.log(
                f"[Explorador] ✦ Broker nuevo aprendido: '{nombre}' "
                f"(payout≈{int(payout*100)}%).")

    # ── Exploración activa de herramientas ────────────────────────────────────

    def _explorar_herramientas_broker(self):
        """
        En modo autónomo, Litch puede explorar el broker con el mouse para
        aprender features que aún no conoce.

        SEGURIDAD: Solo explora áreas que NO son los botones SUBE/BAJA para
        no accionar trades accidentalmente durante la exploración.
        """
        if not getattr(self.app, "autoclick_on", False):
            return

        try:
            import pyautogui as _pag
            _pag.FAILSAFE = False
        except ImportError:
            return

        cfg = self.app.mem["config"]
        rg  = cfg.get("region_grafico")
        bv  = cfg.get("boton_verde")
        br  = cfg.get("boton_rojo")

        if not bv or not br:
            return   # Sin botones calibrados, no explorar (riesgo de click accidental)

        # Zona segura para explorar: área del gráfico (lejos de los botones de trade)
        if rg:
            # Hover sobre el gráfico para ver tooltips
            try:
                from . import manos as _manos
                cx = int((rg[0] + rg[2]) / 2)
                cy = int((rg[1] + rg[3]) / 2)
                # Mover el mouse al centro del gráfico — el broker muestra el precio
                _manos.indicar_hover(cx, cy, 0.5)
            except Exception:
                pass

        # Leer tooltip/precio que aparece al hacer hover
        from . import vision as vis
        img = vis.capturar_pantalla_completa()
        if img is not None:
            estado = self._analizar_imagen_broker(img)
            with self._lock:
                self._estado_actual.update(estado)

        self.app.log("[Explorador] Exploración activa completada.")

    # ── API pública ───────────────────────────────────────────────────────────

    def estado(self) -> dict:
        """Devuelve una copia del último estado conocido del broker."""
        with self._lock:
            return dict(self._estado_actual)

    def descubrimientos_sesion(self) -> list:
        """Lista de cambios y descubrimientos detectados en esta sesión."""
        return list(self._discoveries)

    def resumen_sesion(self) -> str:
        """Texto legible del estado del broker para voz o chat."""
        e = self.estado()
        if not e:
            return self.app.txt(
                "Aún analizando el broker. En un momento tendré más información.",
                "Still analyzing the broker. I'll have more info shortly.")

        partes = []
        if e.get("broker"):
            from . import broker_iq as biq
            nombre = biq.PERFILES.get(e["broker"], {}).get("nombre", e["broker"])
            partes.append(self.app.txt(f"Broker: {nombre}", f"Broker: {nombre}"))
        if e.get("activo"):
            partes.append(self.app.txt(
                f"Activo: {e['activo']}", f"Asset: {e['activo']}"))
        if e.get("vencimiento_seg"):
            mins = e["vencimiento_seg"] // 60
            segs = e["vencimiento_seg"] % 60
            v_txt = (f"{mins} min" if segs == 0 else f"{mins}m {segs}s"
                     if mins > 0 else f"{segs}s")
            partes.append(self.app.txt(
                f"Vencimiento: {v_txt}", f"Expiry: {v_txt}"))
        if e.get("payout_pct"):
            partes.append(self.app.txt(
                f"Payout: {int(e['payout_pct']*100)}%",
                f"Payout: {int(e['payout_pct']*100)}%"))
        if e.get("n_posiciones"):
            partes.append(self.app.txt(
                f"Posiciones abiertas: {e['n_posiciones']}",
                f"Open positions: {e['n_posiciones']}"))
        if e.get("indicadores_activos"):
            partes.append(self.app.txt(
                f"Indicadores: {', '.join(e['indicadores_activos'])}",
                f"Indicators: {', '.join(e['indicadores_activos'])}"))
        if e.get("balance_texto"):
            partes.append(self.app.txt(
                f"Balance: {e['balance_texto']}",
                f"Balance: {e['balance_texto']}"))
        if e.get("pl_color") and e["pl_color"] != "neutro":
            partes.append(self.app.txt(
                f"P&L: {'positivo' if e.get('pl_positivo') else 'negativo'}",
                f"P&L: {'positive' if e.get('pl_positivo') else 'negative'}"))

        disc = len(self._discoveries)
        if disc > 0:
            partes.append(self.app.txt(
                f"{disc} cambios detectados en la sesión.",
                f"{disc} changes detected this session."))

        return " — ".join(partes) if partes else self.app.txt(
            "Broker observado, datos inicializando.",
            "Broker observed, data initializing.")
