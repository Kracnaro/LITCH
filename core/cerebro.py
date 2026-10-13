"""Cerebro de Litch — bilingüe (español/inglés), comandos y conversación.

Detecta el idioma de cada frase y responde en ese idioma. Por micrófono
exige la palabra de activación "Litch" (o conversación reciente).
"""  # v2.0
import random
import re
import time

from . import (agente_web, conocimiento, conocimiento_trading, correo, estadistica, inferencia,
               laboratorio, matematica, memoria, mente, mente_claude,
               permisos as perms_mod, pronostico, respaldo)

VENTANA_CONVERSACION = 120  # segundos en modo conversación tras hablarle

# Variantes con las que Google STT suele transcribir "Litch" en español
VARIANTES_NOMBRE = (
    "litch", "lich", "lych", "lynch", "linch", "liche", "leach", "leech",
    # Lecturas fonéticas erróneas comunes en español:
    "félix", "felix", "fénix", "fenix", "litche", "lits", "lix",
    "leche", "lish", "leesh", "rich", "ritch",
)

PALABRAS_EN = {"the", "what", "who", "how", "is", "are", "my", "please", "time",
               "status", "stop", "start", "hello", "hi", "thanks", "thank",
               "remind", "search", "weather", "help", "you", "turn", "speak",
               "activate", "report", "good", "morning", "tell"}
PALABRAS_ES = {"el", "la", "los", "las", "que", "qué", "como", "cómo", "por",
               "para", "activa", "detén", "hola", "gracias", "ayuda", "estado",
               "hora", "busca", "clima", "recuérdame", "habla", "quién", "es",
               "de", "buenos", "buenas", "dime", "señor", "mercado", "y"}


def menciona_nombre(t):
    return any(v in t for v in VARIANTES_NOMBRE)


def detectar_idioma(t, defecto="es"):
    tokens = set(re.findall(r"[a-záéíóúüñ']+", t.lower()))
    puntos_en = len(tokens & PALABRAS_EN)
    puntos_es = len(tokens & PALABRAS_ES)
    if puntos_en > puntos_es:
        return "en"
    if puntos_es > puntos_en:
        return "es"
    return defecto


class Cerebro:
    def __init__(self, app):
        self.app = app
        self.ultima_interaccion = 0.0
        self._fue_default = False

    # ------------------------------------------------------------------
    def procesar(self, texto, origen="chat"):
        """Devuelve (respuesta, idioma) o None si debe ignorar (voz ajena)."""
        t = texto.lower().strip()
        if origen == "voz":
            en_conversacion = (time.time() - self.ultima_interaccion) < VENTANA_CONVERSACION
            if menciona_nombre(t):
                for v in VARIANTES_NOMBRE:
                    t = t.replace(v, " ")
                t = t.strip(" ,.")
            elif not en_conversacion:
                return None  # no me hablaban a mí
        self.ultima_interaccion = time.time()
        idioma = detectar_idioma(t, self.app.idioma)
        self._fue_default = False
        respuesta = self._responder(t if t else "hola", idioma)
        # Fallback cuando las reglas no entendieron:
        #   1) Claude (Anthropic) si está activo y tiene key
        #   2) Ollama local
        #   3) Respuesta de reglas (ya asignada arriba)
        if self._fue_default:
            usar_cl = getattr(self.app, "usar_claude", False)
            usar_ol = getattr(self.app, "usar_ollama", True)
            if usar_cl and mente_claude.disponible():
                self.app.log("Litch: consultando a Claude…")
                pensada = mente_claude.responder(
                    texto, self.app.mem.get("conversaciones"), idioma)
                if pensada:
                    respuesta = pensada
            elif usar_ol and mente.disponible():
                self.app.log("Litch: pensando (Ollama)…")
                pensada = mente.responder(texto, self.app.mem.get("conversaciones"))
                if pensada:
                    respuesta = pensada
        memoria.registrar_conversacion(self.app.mem, origen, texto, respuesta)
        memoria.guardar(self.app.mem)
        return respuesta, idioma

    # ------------------------------------------------------------------
    def _responder(self, t, idioma):
        a = self.app

        # Cambio de idioma (entendido en ambos)
        if re.search(r"speak english|habla ingl[eé]s|in english", t):
            a.set_idioma("en")
            return "Of course, sir. Switching to English. I'm listening."
        if re.search(r"speak spanish|habla espa[ñn]ol|en espa[ñn]ol", t):
            a.set_idioma("es")
            return "Por supuesto, señor. Cambiando a español. Le escucho."

        if idioma == "en":
            return self._responder_en(t)
        return self._responder_es(t)

    # ------------------------------------------------------------------
    def _responder_es(self, t):
        a = self.app

        def tiene(*palabras):
            return any(p in t for p in palabras)

        # --- Recordatorios ----------------------------------------------
        m = re.search(r"recu[eé]rdame (?:que )?(.+?) (?:en|dentro de) (\d+) "
                      r"(segundos?|minutos?|horas?)", t)
        if m:
            return a.recordatorios.crear(m.group(1), int(m.group(2)),
                                         m.group(3), "es")

        # --- Clima --------------------------------------------------------
        m = re.search(r"(?:clima|tiempo) (?:en |de )(.+)", t)
        if m:
            reporte = conocimiento.clima(m.group(1).strip(" ?¿"), "es")
            return reporte or "No pude consultar el clima ahora, señor."

        # --- Noticias financieras ----------------------------------------
        if tiene("noticias", "novedades del mercado", "noticias financieras"):
            titulos = agente_web.noticias_rss(6)
            if titulos:
                return "Noticias recientes del mercado, señor: " + " // ".join(titulos[:5])
            return "No pude obtener noticias ahora, señor. Revisa la conexión."

        # --- Precio / datos de símbolo -----------------------------------
        m = re.search(r"(?:precio|cotizaci[oó]n|datos)(?: de| del?)?\s+([A-Z]{1,5}(?:[-/][A-Z]{1,5})?)", t.upper())
        if m and tiene("precio", "cotización", "cotizacion", "datos de"):
            simbolo = m.group(1)
            dato = agente_web.datos_mercado(simbolo)
            if dato:
                return (f"{dato['simbolo']} cotiza a {dato['precio']} {dato['moneda']} "
                        f"en {dato['mercado']}, señor.")
            return f"No pude obtener el precio de {simbolo} ahora, señor."

        # --- Correo electrónico ------------------------------------------
        if tiene("lee mi correo", "leer correo", "qué correos", "que correos",
                 "revisa mi correo", "bandeja de entrada"):
            return correo.resumen_inbox(5, "es")

        m_email = re.search(
            r"env[ií]a (?:un )?correo a ([^\s,]+).+?(?:sobre|que diga|diciendo|con asunto) (.+)",
            t)
        if m_email or (tiene("envía", "enviar", "manda") and tiene("correo", "email", "mail")):
            if m_email:
                dest   = m_email.group(1).strip()
                asunto = m_email.group(2).strip()[:60]
                ok, msg = correo.enviar(dest, asunto, asunto)
                return msg
            return ("Diga: «envía un correo a [email] sobre [asunto]», señor. "
                    "Si no tiene cuentas configuradas, ábralas en el panel «📧 Correo e IA».")

        # --- Permisos ----------------------------------------------------
        if tiene("permisos", "qué permisos", "que permisos", "mis permisos"):
            return perms_mod.resumen()
        if tiene("concede permiso", "activa permiso", "dame permiso de"):
            m_p = re.search(r"permiso (?:de |para )(.+)", t)
            if m_p:
                clave = m_p.group(1).strip().replace(" ", "_")
                if clave in perms_mod.CATALOGO:
                    perms_mod.conceder(clave)
                    return f"Permiso «{clave}» concedido, señor."
            return "No reconocí el permiso. Diga el nombre exacto o use el panel de correo e IA."

        # --- Investigación profunda --------------------------------------
        m_inv = re.search(r"(?:investiga|investígame|investígale) (?:sobre |acerca de )?(.+)", t)
        if m_inv:
            tema = m_inv.group(1).strip(" ?¿")
            self.app.log(f"Investigando: {tema}…")
            return agente_web.investigar(tema, "es")

        # --- Búsqueda rápida online --------------------------------------
        m = (re.search(r"(?:busca|b[uú]scame|consulta)(?: sobre| acerca de)? (.+)", t)
             or re.search(r"(?:qui[eé]n|qu[eé]) (?:es|son|fue|significa) (.+)", t))
        if m:
            tema = m.group(1).strip(" ?¿")
            return agente_web.respuesta_rapida(tema, "es") or conocimiento.buscar(tema, "es")

        # --- Control del sistema -------------------------------------
        if tiene("pausa", "pausar", "duérmete", "descansa", "desactívate"):
            a.set_activo(False)
            return "Entendido, señor. Entro en modo de espera. Dígame «actívate» cuando me necesite."
        if tiene("despierta", "actívate", "enciende", "reanuda", "actívame"):
            a.set_activo(True)
            return "Sistemas reactivados. Estoy a su disposición."

        # --- Modo autónomo / auto-click ----------------------------------
        if tiene("modo autónomo", "modo autonomo", "libre albedrío",
                 "libre albedrio", "llave maestra", "autonomía", "autonomia"):
            if a.modo_autonomo:
                a.set_autoclick(False)
                return ("Modo autónomo desactivado, señor. Puede reactivarlo con "
                        "el botón AUTO o diciéndome «activa el auto-click».")
            a.set_autoclick(True)
            return ("Modo autónomo activado. Operaré en demo y me auto-ajustaré "
                    "sin pedirle confirmación. Diga «desactiva el auto-click» para parar.")

        # --- Trading ---------------------------------------------------
        if tiene("trading", "análisis", "analiza el gráfico", "mercado"):
            if tiene("activa", "inicia", "enciende", "comienza", "empieza"):
                a.set_trading(True)
                return ("Análisis de mercado activado. Observaré cada vela del demo de IQ Option "
                        "y memorizaré los patrones. Le avisaré cuando detecte una señal estadística.")
            if tiene("desactiva", "detén", "para", "apaga", "pausa"):
                a.set_trading(False)
                return "Análisis de mercado detenido. Los patrones aprendidos quedan guardados."
        if tiene("click", "clic"):
            if tiene("activa", "enciende", "permite", "autoriza"):
                a.set_autoclick(True)
                return ("Auto-click activado. Operaré en modo autónomo completo. "
                        "Puede desactivarlo cuando quiera.")
            if tiene("desactiva", "apaga", "quita", "revoca", "detén"):
                a.set_autoclick(False)
                return "Auto-click desactivado. Solo le sugeriré las señales por voz."

        # --- Consejero ---------------------------------------------------
        if tiene("consejo", "aconséjame", "aconsejame", "recomienda",
                 "recomiéndame", "recomiendame", "qué me recomiendas",
                 "que me recomiendas", "qué harías", "que harias"):
            if tiene("apaga", "desactiva", "silencia", "no más", "no mas"):
                a.set_consejos(False, hablar=False)
                return "Entendido, señor. Guardaré mis consejos para cuando los pida."
            if tiene("activa", "enciende", "quiero"):
                a.set_consejos(True, hablar=False)
                return "Consejero activado. Le iré compartiendo recomendaciones, señor."
            return a.consejero.consejo_inmediato()

        # --- Información -----------------------------------------------
        if tiene("respald", "guarda en la nube", "copia de seguridad",
                 "sube a la nube", "nube"):
            if tiene("registr", "agrega", "añade", "nueva cuenta", "configura"):
                a.abrir_nube()
                return ("Abriendo el panel de nube, señor. Allí registra sus correos y "
                        "las carpetas que sincronizan TeraBox, Drive o Dropbox.")
            resultado = respaldo.respaldar(a)
            return resultado
        if tiene("red neuronal", "neurona", "qué predice la red", "que predice la red",
                 "predicción de la red", "prediccion de la red"):
            d, p = a.red.predecir(a.mem["secuencia"])
            if d is None:
                return ("Mi red neuronal aún no tiene entrenamiento suficiente, señor. "
                        "Necesito observar más velas para que aprenda.")
            prec = a.red.precision_aprox(a.mem["secuencia"])
            extra = f" Su precisión sobre el histórico es {int(prec*100)}%." if prec else ""
            lado = "subida (verde)" if d == "V" else "bajada (roja)"
            return (f"Mi red neuronal predice {lado} con {int(p*100 if d=='V' else (1-p)*100)}% "
                    f"de probabilidad.{extra}")
        if tiene("bayes", "bayesiano", "inferencia", "fusión", "fusion",
                 "decisión maestra", "decision maestra"):
            sec = a.mem["secuencia"]
            if len(sec) < 10:
                return ("Aún tengo pocas velas observadas para una fusión bayesiana "
                        "seria, señor. Active el trading y déjeme aprender.")
            voto = estadistica.analizar(sec)
            d_red, p_red = a.red.predecir(sec)
            est = a.mem["estadisticas"]
            tot = est.get("aciertos", 0) + est.get("fallos", 0)
            opiniones = [
                {"direccion": voto["candidata"], "confianza": voto["confianza"],
                 "precision": 0.55, "n": len(sec)},
                {"direccion": d_red, "confianza": abs(p_red - 0.5) * 2,
                 "precision": a.red.precision_aprox(sec) or 0.5, "n": len(sec)},
                {"direccion": None if not tot else voto["candidata"],
                 "confianza": 0.5,
                 "precision": est.get("aciertos", 0) / tot if tot else 0.5, "n": tot},
            ]
            return inferencia.resumen(inferencia.decidir(sec, opiniones), "es")
        if tiene("segundo método", "segundo metodo", "consenso", "qué opinas del mercado",
                 "que opinas del mercado"):
            return estadistica.resumen(a.mem["secuencia"], "es")
        if tiene("pronóstico", "pronostico", "análisis avanzado", "analisis avanzado",
                 "entropía", "entropia", "benford", "autocorrelación", "autocorrelacion",
                 "ewma", "tendencia avanzada", "qué tan predecible", "que tan predecible"):
            sec = a.mem["secuencia"]
            if len(sec) < 15:
                return ("Aún tengo pocas velas observadas para el pronóstico avanzado, "
                        "señor. Active el trading y déjeme aprender al menos 15 velas.")
            return pronostico.resumen_texto(sec, "es")

        # --- SMC / LWS — análisis de estructura en tiempo real ---------------
        # --- Consciencia situacional: dónde estoy y qué hago --------------
        if tiene("dónde estás", "donde estas", "dónde estas", "donde estás",
                 "qué estás haciendo", "que estas haciendo", "situación",
                 "situacion", "en qué ventana", "en que ventana",
                 "eres consciente", "qué haces ahora", "que haces ahora"):
            try:
                from . import situacion as _sit
                return _sit.resumen_situacion(a, idioma=a.idioma)
            except Exception as _e_sit:
                return f"No pude generar el informe de situación: {_e_sit}"

        if tiene("qué estás viendo", "que estas viendo", "qué ves", "que ves",
                 "explícame lo que haces", "explicame lo que haces",
                 "qué análisis tienes", "que analisis tienes",
                 "analiza el mercado ahora", "análisis smc", "analisis smc",
                 "estructura de mercado", "dime tu análisis", "dime tu analisis",
                 "explícame qué hiciste", "explicame que hiciste",
                 "por qué entraste", "por que entraste"):
            from . import analizador_smc as _smc
            sec = a.mem["secuencia"]
            if len(sec) < 8:
                return ("Aún tengo pocas velas para el análisis SMC, señor. "
                        "Necesito al menos 8 velas para detectar estructura.")
            smc  = _smc.analizar_completo(sec, getattr(a.agente, "_ultimo_ind", {}))
            kz   = smc.get("killzone", {})
            raz  = getattr(a.agente, "_razonamiento_actual", {})
            lineas = [
                f"Estructura: {smc.get('estructura','?')} | "
                f"BOS: {'sí' if smc.get('bos') else 'no'} | "
                f"CHoCH: {'sí' if smc.get('choch') else 'no'}",
                f"Order Block: {'detectado' if smc.get('ob') else 'ninguno'} | "
                f"FVG: {'detectado' if smc.get('fvg') else 'ninguno'} | "
                f"Sweep: {'detectado' if smc.get('sweep') else 'ninguno'}",
                f"Killzone: {kz.get('nombre','?')} ({'activa' if kz.get('activa') else 'inactiva'}) "
                f"— tasa histórica {kz.get('tasa','?')}",
                f"Setup: {smc.get('setup','sin setup')} | "
                f"Confianza SMC: {int(smc.get('confianza',0)*100)}%",
            ]
            if raz.get("smc_setup"):
                lineas.append(f"Último trade: {raz.get('smc_setup','?')} | "
                              f"{raz.get('votos',0)}/7 modelos")
            if smc.get("narrativa"):
                lineas.append(f"Detalle: {smc.get('narrativa','')}")

            # ── Comprensión de PANTALLA COMPLETA (no solo el gráfico) ────
            try:
                ctx = getattr(a.agente, "_ctx_pantalla", {}) or {}
                if ctx:
                    partes_ctx = []
                    if ctx.get("app_al_frente"):
                        partes_ctx.append(f"app al frente: {ctx['app_al_frente']}")
                    if "activo" in ctx:
                        partes_ctx.append(f"activo {ctx['activo']}")
                    if "payout" in ctx:
                        partes_ctx.append(f"payout {ctx['payout']}")
                    partes_ctx.append(
                        "botones SUBE/BAJA visibles" if ctx.get("botones_ok", True)
                        else "⚠ botones NO visibles")
                    lineas.append("Pantalla: " + ", ".join(partes_ctx) + ".")
            except Exception:
                pass
            try:
                ul = getattr(a, "ui_learner", None)
                if ul is not None:
                    with ul._lock:
                        _elems = [f for f, e in ul._mapa.items()
                                  if getattr(e, "activo", False)]
                    if _elems:
                        lineas.append(
                            f"Herramientas del broker que he aprendido a "
                            f"ubicar ({len(_elems)}): "
                            + ", ".join(sorted(_elems)[:10]) + ".")
            except Exception:
                pass
            try:
                fable = getattr(a.agente, "_ultimo_analisis_fable", {}) or {}
                if fable.get("resumen") or fable.get("analisis"):
                    lineas.append("Análisis visual externo: "
                                  + str(fable.get("resumen")
                                        or fable.get("analisis"))[:200])
            except Exception:
                pass
            return "\n".join(lineas)

        if tiene("killzone", "kill zone", "qué hora es para operar",
                 "mejor hora", "hora de trading", "ventana de trading"):
            from . import analizador_smc as _smc
            kz = _smc.killzone_activa()
            if kz["activa"]:
                return (f"Estamos en {kz['nombre']}, señor. "
                        f"Horario {kz['horario']}. "
                        f"Tasa histórica: {kz['tasa']}. "
                        f"Es una de las mejores ventanas para operar.")
            return (f"Estamos en '{kz['nombre']}', señor — fuera de killzone. "
                    f"Horario {kz['horario']}. Tasa histórica: {kz['tasa']}. "
                    f"Recomiendo esperar la próxima killzone: London Open (07-10 UTC) "
                    f"o NY Open (13:30-16 UTC).")

        if tiene("bos", "choch", "break of structure", "change of character",
                 "qué es el bos", "que es el bos", "qué es el choch"):
            from . import analizador_smc as _smc
            sec = a.mem["secuencia"]
            if len(sec) >= 8:
                est = _smc.detectar_estructura(sec)
                extra = f"\nEstado actual: {est['info']}" if est.get("info") else ""
            else:
                extra = ""
            return (conocimiento_trading.buscar("bos choch estructura mercado", "es")
                    + extra)

        if tiene("order block", "bloque de orden", "ob alcista", "ob bajista",
                 "zona de demanda", "zona de oferta"):
            from . import analizador_smc as _smc
            sec = a.mem["secuencia"]
            if len(sec) >= 8:
                ob = _smc.detectar_order_block(sec)
                extra = f"\nOB detectado ahora: {ob['descripcion']}" if ob else \
                        "\nEn este momento: ningún OB válido detectado."
            else:
                extra = ""
            return (conocimiento_trading.buscar("order block válido", "es") + extra)

        if tiene("sweep", "liquidity sweep", "barrida de liquidez",
                 "trampa del mercado", "falsa ruptura"):
            from . import analizador_smc as _smc
            sec = a.mem["secuencia"]
            if len(sec) >= 8:
                sweep = _smc.detectar_liquidity_sweep(sec)
                extra = f"\nSweep detectado ahora: {sweep['descripcion']}" if sweep else \
                        "\nEn este momento: no detecto sweep de liquidez activo."
            else:
                extra = ""
            return (conocimiento_trading.buscar("liquidity sweep", "es") + extra)
        # Predicción de secuencias numéricas con el motor matemático
        m = re.search(r"(?:sigue|continúa|continua|predice|siguiente).*?"
                      r"([\d\.\,\-\s]{5,})", t)
        if m and tiene("secuencia", "sucesión", "sucesion", "serie", "patrón",
                       "patron", "número", "numero", "sigue", "predice", "siguiente"):
            nums = [float(x) for x in re.findall(r"-?\d+\.?\d*", m.group(1))]
            if len(nums) >= 3:
                return matematica.predecir_secuencia(nums, "es")
        if tiene("estado", "reporte", "resumen", "estadística", "estadisticas",
                 "cómo vas", "como vas", "qué has aprendido", "que has aprendido"):
            return a.analizador.resumen("es")
        # --- Memoria aprendida -------------------------------------------
        if tiene("cuánto has aprendido", "cuanto has aprendido",
                 "memoria ap", "peso de tu memoria", "peso de la memoria",
                 "cuánto pesa", "cuanto pesa", "qué has memorizado",
                 "que has memorizado", "memoria aprendida", "abre tu memoria",
                 "carpeta de memoria"):
            peso = memoria.peso_memoria()
            ruta = memoria.ruta_memoria_ap()
            return (f"{peso} "
                    f"La carpeta está en: {ruta}")

        # --- Libros y documentos -------------------------------------------
        if tiene("carga los libros", "carga mis libros", "aprende del libro",
                 "aprende de los libros", "importa los libros",
                 "lee los libros", "escanea los libros",
                 "actualiza los libros", "procesa los libros"):
            from . import lector_libros as _lb
            logs = []
            def _cb(msg):
                logs.append(msg)
                a.log(msg)
            import threading as _thr
            def _cargar():
                res = _lb.cargar_libros(callback=_cb)
                if res["nuevos"] == 0 and not res["errores"]:
                    a.decir(a.txt(
                        f"Ya tenía todos los libros cargados, señor. "
                        f"{res['total']} libros con {res['chunks']} fragmentos.",
                        f"All books already loaded, sir. {res['total']} books, "
                        f"{res['chunks']} chunks."))
                elif res["nuevos"] > 0:
                    a.decir(a.txt(
                        f"Libros cargados, señor. {res['nuevos']} nuevos procesados. "
                        f"Total: {res['total']} libros con {res['chunks']} fragmentos "
                        f"listos para responder preguntas.",
                        f"Books loaded, sir. {res['nuevos']} new. "
                        f"Total: {res['total']} books, {res['chunks']} chunks indexed."))
                else:
                    errs = " | ".join(res["errores"][:2])
                    a.decir(a.txt(
                        f"Tuve problemas al cargar, señor: {errs}",
                        f"I had trouble loading, sir: {errs}"))
            _thr.Thread(target=_cargar, daemon=True, name="LitchLibros").start()
            return ("Cargando los libros de la carpeta LIBROS/ en segundo plano, señor. "
                    "Le aviso cuando termine.")

        if tiene("qué libros tienes", "que libros tienes", "libros cargados",
                 "cuántos libros", "cuantos libros", "lista de libros",
                 "qué has leído", "que has leido", "libros disponibles"):
            from . import lector_libros as _lb
            lista = _lb.listar_libros()
            if not lista:
                return ("No tengo ningún libro cargado aún, señor. "
                        "Copie sus PDF o TXT en la carpeta LIBROS/ y dígame "
                        "'carga mis libros'.")
            txt = "\n".join(
                f"  • {lb['nombre']} ({lb['chunks']} fragmentos, cargado {lb['fecha']})"
                for lb in lista)
            return (f"Tengo {len(lista)} libro(s) indexado(s), señor:\n{txt}\n"
                    f"Total de fragmentos buscables: {_lb.total_chunks()}")

        if tiene("busca en los libros", "busca en mis libros",
                 "qué dicen los libros", "que dicen los libros",
                 "qué dice el libro", "que dice el libro",
                 "encuéntrame en los libros", "encuentrame en los libros",
                 "en tus libros", "en mis libros", "consulta los libros"):
            from . import lector_libros as _lb
            # Extraer la pregunta real (lo que va después de la frase clave)
            sub = re.sub(
                r"(busca en (los|mis) libros|qué dicen (los|mis) libros sobre|"
                r"que dicen (los|mis) libros sobre|qué dice el libro sobre|"
                r"que dice el libro sobre|en (tus|mis) libros|consulta los libros)",
                "", t).strip(" ,.")
            pregunta = sub if sub else t
            if not _lb.disponible():
                return ("No tengo libros cargados aún, señor. "
                        "Copie sus archivos en LIBROS/ y diga 'carga mis libros'.")
            resultados = _lb.buscar(pregunta, top_n=2)
            if not resultados:
                return (f"No encontré nada sobre '{pregunta}' en mis libros, señor. "
                        f"¿Puede reformular la pregunta?")
            lineas = []
            for r in resultados:
                lineas.append(
                    f"📖 [{r['libro']}] (relevancia: {r['score']}):\n"
                    f"  «{r['texto'][:350].strip()}…»")
            return "\n\n".join(lineas)

        if tiene("hora"):
            return "Son las " + time.strftime("%H:%M") + ", señor."
        if tiene("fecha", "día es hoy", "dia es hoy"):
            return "Hoy es " + time.strftime("%d de %B de %Y") + "."
        if tiene("teorema", "auditar", "auditoría", "auditoria", "sesgo",
                 "están estafando", "estan estafando", "es aleatorio", "peso de las bolas"):
            hist = a.mem["loteria"].get("historial") or []
            if not hist:
                a.abrir_loteria()
                return ("Abra el módulo de lotería y cargue los sorteos, señor. Luego "
                        "pulse «Auditar teorema» y le diré si hay sesgo real o es puro azar.")
            return laboratorio.informe(hist, "es")
        if tiene("lotería", "loteria"):
            a.abrir_loteria()
            return ("Abriendo el módulo de lotería. Cargue los sorteos: tengo dos modos, "
                    "«Frecuencias» y «Auditar teorema», que prueba con chi-cuadrado y "
                    "backtest si el sorteo tiene sesgo o es azar puro.")
        if tiene("predic", "sugier", "números para", "numeros para",
                 "análisis avanzad", "analisis avanzad",
                 "qué números", "que numeros", "dame números", "dame numeros",
                 "combinación", "combinacion"):
            hist = a.mem.get("loteria", {}).get("historial") or []
            if not hist:
                a.abrir_loteria()
                return ("Necesito historial de sorteos para analizarlos, señor. Abra el "
                        "módulo de lotería y cargue los datos. Luego usaré 9 métodos "
                        "estadísticos y una red neuronal para sugerirle los candidatos.")
            return a.resumen_loteria_av()
        if tiene("como voy", "cómo voy", "mis estadísticas", "mis estadisticas",
                 "cuánto llevo", "cuanto llevo", "rendimiento", "resultados",
                 "gané", "gane", "perdí", "perdi", "cuántos aciertos", "cuantos aciertos"):
            return a.resumen_trading()
        if tiene("por qué fallé", "por que falle", "por qué pierdo", "por que pierdo",
                 "mis fallos", "mis errores", "qué aprend", "que aprend",
                 "analiza mis fallos", "por qué falla"):
            fdb = a.agente.fdb
            malos = fdb.patrones_problematicos()
            racha = fdb.racha_actual()
            lineas = [fdb.resumen(idioma="es")]
            if malos:
                lineas.append("Patrones que más me fallan: " +
                              ", ".join(f"'{p}' ({int(f*100)}%)" for p, f in malos[:3]) + ".")
            if racha["tipo"] == "LOSS" and racha["n"] >= 2:
                lineas.append(f"Llevo {racha['n']} pérdidas seguidas ahora mismo.")
            # Estadísticas por activo
            try:
                stats_a = fdb.stats_por_activo()
                if stats_a:
                    mejor = max(stats_a.items(), key=lambda x: x[1]["wr"])
                    peor  = min(stats_a.items(), key=lambda x: x[1]["wr"])
                    lineas.append(
                        f"Mejor activo: {mejor[0]} WR={mejor[1]['wr']}% "
                        f"({mejor[1]['n']} ops). "
                        f"Peor activo: {peor[0]} WR={peor[1]['wr']}% "
                        f"({peor[1]['n']} ops).")
            except Exception:
                pass
            return " ".join(lineas)

        if tiene("mejores horas", "mejores franjas", "mejor momento para operar",
                 "cuándo operar", "cuando operar", "horario óptimo",
                 "peores horas", "franjas malas", "horarios del día"):
            try:
                st = a.agente._session_tracker
                mejores = st.mejores_franjas(3)
                peores  = st.peores_franjas(3)
                comp    = st.stats_completos()
                partes  = []
                if mejores:
                    partes.append("Mejores franjas: " + " | ".join(
                        f"{f['hora']}({f['sesion']}) WR={f['wr']}%({f['n']}ops)"
                        for f in mejores))
                if peores:
                    partes.append("Peores franjas: " + " | ".join(
                        f"{f['hora']} WR={f['wr']}%"
                        for f in peores))
                ses_data = comp.get("sesiones", {})
                if ses_data:
                    partes.append("Por sesión: " + " | ".join(
                        f"{k.upper()} WR={v['wr']}%({v['n']}ops)"
                        for k, v in ses_data.items()))
                if not partes:
                    return ("Todavía no tengo suficientes datos de franja horaria, señor. "
                            "Sigo aprendiendo con cada trade.")
                return " ".join(partes)
            except Exception as e:
                return f"SessionTracker no disponible: {e}"

        if tiene("profit factor", "expectativa matemática", "expectativa matematica",
                 "reporte completo", "estadísticas avanzadas", "estadisticas avanzadas",
                 "análisis completo de rendimiento", "analisis completo de rendimiento",
                 "performance completo", "métricas avanzadas", "metricas avanzadas"):
            try:
                perf = getattr(a.agente, "_perf", None)
                if perf is None:
                    return "Módulo de análisis de rendimiento no disponible, señor."
                if not perf._trades:
                    return "Todavía no hay trades registrados en el tracker, señor."
                r = perf.reporte_completo()
                votos_str = " | ".join(
                    f"{v}v: WR={d['wr']:.0f}%({d['n']})"
                    for v, d in r["wr_por_votos"].items()
                )
                return (
                    f"Análisis avanzado: WR 10t={r['wr_10']:.0f}% "
                    f"20t={r['wr_20']:.0f}% 50t={r['wr_50']:.0f}%. "
                    f"Profit Factor={r['profit_factor']:.2f}. "
                    f"Expectativa=${r['expectativa']:.3f}/trade. "
                    f"Sharpe={r['sharpe_50']:.2f}. "
                    f"P&L total={r['pnl_total']:+.2f}$. MaxDD=${r['max_dd']:.2f}. "
                    f"Mejor racha={r['max_racha_win']}wins. "
                    f"WR por votos: {votos_str}, señor."
                )
            except Exception as e:
                return f"Error en análisis de rendimiento: {e}"

        if tiene("mejor momento para operar", "mejor hora para operar",
                 "cuándo debería operar", "cuando deberia operar",
                 "franja óptima", "franja optima", "hora óptima histórica",
                 "hora optima historica"):
            try:
                perf = getattr(a.agente, "_perf", None)
                if perf and len(perf._trades) >= 15:
                    return perf.mejor_momento()
                st = a.agente._session_tracker
                mejores = st.mejores_franjas(2)
                if mejores:
                    return ("Por SessionTracker: " + " | ".join(
                        f"{f['hora']}({f['sesion']}) WR={f['wr']}%({f['n']}ops)"
                        for f in mejores) + ", señor.")
                return "Todavía no tengo suficientes datos para calcular el mejor momento, señor."
            except Exception as e:
                return f"Error al calcular mejor momento: {e}"

        # ── Inicializar saldo via voz ──────────────────────────────────────────
        import re as _re_cap
        _m_saldo = _re_cap.search(
            r"(?:mi saldo|saldo actual|tengo|cuenta con|cuenta tiene|balance)"
            r"\s*(?:es|son|de|:)?\s*\$?\s*([\d][,\d]*(?:\.\d+)?)",
            t, _re_cap.IGNORECASE)
        if _m_saldo:
            try:
                _saldo_nuevo = float(_m_saldo.group(1).replace(",", ""))
                cfg = a.mem.get("config", {})
                cfg["saldo"]         = _saldo_nuevo
                cfg["saldo_inicial"] = _saldo_nuevo
                a.mem["config"]      = cfg
                # Resetear historial P&L para recalcular desde este punto
                if hasattr(a.agente, "_historial_pnl"):
                    a.agente._historial_pnl = []
                # Actualizar panel de capital inmediatamente con saldo nuevo
                try:
                    from . import consejos_visual as _cv_c
                    cv = _cv_c.obtener()
                    if cv:
                        _m_cv  = float(cfg.get("monto", 1.0)
                                       or cfg.get("monto_base", 1.0) or 1.0)
                        _v_cv  = int(cfg.get("vencimiento",
                                             cfg.get("periodo_vela", 60)))
                        _p_cv  = int(cfg.get("periodo_vela", 60))
                        # Recomendación inmediata de monto
                        _recom = None
                        if _m_cv / _saldo_nuevo > 0.04:
                            _opt = max(1, round(_saldo_nuevo * 0.02))
                            _recom = f"⚠ Baja monto a ${_opt} (2% del saldo)"
                        cv.actualizar(
                            saldo           = _saldo_nuevo,
                            monto           = _m_cv,
                            vencimiento_seg = _v_cv,
                            periodo_seg     = _p_cv,
                            recomendacion   = _recom,
                            saldo_tendencia = "estable",
                        )
                except Exception:
                    pass
                _opt_monto = max(1, round(_saldo_nuevo * 0.02))
                return (f"Entendido, señor. Saldo registrado: ${_saldo_nuevo:,.2f}. "
                        f"Monto óptimo recomendado: ${_opt_monto} (2% del capital). "
                        f"Recalibré mi gestión de riesgo desde este punto.")
            except Exception as _ec:
                return f"No pude leer el saldo: {_ec}"

        if tiene("estado del capital", "cuánto tengo", "cuanto tengo",
                 "monto recomendado", "cuánto debo invertir", "cuanto debo invertir",
                 "gestión de capital", "gestion de capital",
                 "riesgo por trade", "cuánto apostar", "cuanto apostar",
                 "analiza mi capital", "revisa el capital"):
            try:
                cm = getattr(a.agente, "_capital", None)
                if cm is None:
                    return "El gestor de capital no está inicializado, señor."
                cfg = a.mem.get("config", {})
                saldo = float(cfg.get("saldo", 0))
                monto = float(cfg.get("monto", 1.0))
                venc  = int(cfg.get("vencimiento", 60))
                per   = int(cfg.get("periodo_vela", 60))
                cm.actualizar(saldo, monto, venc)
                ev = cm.evaluar(kelly_f=0.08, votos=5, confianza=0.65,
                                periodo_vela_seg=per)
                from .capital_manager import _seg_a_texto
                lineas = [
                    f"Saldo actual: ${ev.saldo:.2f}.",
                    f"Monto configurado: ${ev.monto_configurado:.0f} "
                    f"({ev.riesgo_pct:.1%} del capital).",
                    f"Monto óptimo según Kelly: ${ev.monto_recomendado:.0f}.",
                    f"Vencimiento: {_seg_a_texto(venc)} — "
                    f"período de vela: {_seg_a_texto(per)}.",
                    f"Aguanta {ev.trades_restantes} pérdidas consecutivas.",
                ]
                if ev.mensaje:
                    lineas.append(ev.mensaje)
                return " ".join(lineas)
            except Exception as e:
                return f"Error en gestor de capital: {e}"

        if tiene("grafo", "mapa mental", "relaciones aprendidas", "qué sé del mercado",
                 "que se del mercado", "conocimiento acumulado", "estadísticas del grafo",
                 "que patrones conoces", "qué patrones conoces"):
            try:
                from .grafo_conocimiento import GrafoConocimiento as _GK
                import os as _os
                _ruta_gk = _os.path.join(
                    _os.path.dirname(__file__), "..", "memoria_ap", "grafo_conocimiento.json")
                _gk = _GK(_ruta_gk)
                st = _gk.estadisticas()
                if st["nodos"] == 0:
                    return ("El grafo de conocimiento está vacío, señor. "
                            "Comenzará a aprender desde el primer trade ejecutado.")
                resp = (
                    f"Mi grafo de conocimiento tiene {st['nodos']} conceptos conectados "
                    f"por {st['aristas']} relaciones de experiencia real. "
                )
                if st["nodo_estrella"]:
                    nombre = st["nodo_estrella"].split(":", 1)[-1].upper()
                    resp += (f"El factor con mayor tasa de éxito es '{nombre}' "
                             f"con {st['wr_estrella']:.0%} de aciertos. ")
                cfg  = a.mem.get("config", {})
                _ctx = {
                    "activo":  cfg.get("asset_actual", ""),
                    "hora":    __import__("time").strftime("%H"),
                }
                prob_ctx = _gk.probabilidad_contextual(_ctx)
                if prob_ctx > 0.5:
                    resp += (f"Para el activo y hora actuales, el grafo estima "
                             f"{prob_ctx:.0%} de probabilidad de éxito.")
                return resp
            except Exception as e:
                return f"[Grafo] No disponible: {e}"

        if tiene("sharpe", "ratio sharpe", "calidad de señales",
                 "drawdown", "pérdida máxima sesión", "proteccion capital"):
            pro = getattr(a, "modo_profesional", None)
            if not pro or not pro.activo:
                return ("El modo profesional no está activo, señor. "
                        "Active primero el modo profesional para ver métricas de riesgo.")
            s = pro.stats()
            return (f"Sharpe de sesión: {s['sharpe']:+.2f} | "
                    f"Drawdown actual: {s['dd_actual']:.1f}% "
                    f"(máximo esta sesión: {s['dd_max']*100:.1f}%) | "
                    f"P&L sesión: {s['pnl_sesion']:+.1f}$ | "
                    f"Sesión: {s['sesion']} ×{s['factor_ses']:.2f} | "
                    f"Cooldown adaptativo: {s['cooldown']}s | "
                    f"{'⛔ DETENIDO POR DRAWDOWN' if s['dd_detenido'] else '✓ Operando'}")
        if tiene("resumen de riesgo", "estado de riesgo", "risk manager",
                 "evalúa el riesgo", "cómo está el riesgo", "como esta el riesgo",
                 "gestor de riesgo"):
            try:
                rm = getattr(a.agente, "_risk_mgr", None)
                if rm is None:
                    return "El gestor de riesgo centralizado todavía no está activo, señor."
                return rm.resumen()
            except Exception as e:
                return f"RiskManager no disponible: {e}"

        if tiene("nivel de practica", "nivel practica", "como va la practica",
                 "estado de practica", "estadisticas de practica", "practica stats"):
            try:
                pr = getattr(a, "practica", None)
                if pr is None or not pr.activo:
                    return ("El modo práctica no está activo, señor. "
                            "Di «activar práctica» para iniciarlo.")
                return pr.resumen()
            except Exception as e:
                return f"Error obteniendo stats de práctica: {e}"

        if tiene("mejor racha", "racha maxima", "record de aciertos",
                 "cuantos aciertos seguidos", "cuántos aciertos seguidos"):
            try:
                pr = getattr(a, "practica", None)
                if pr and pr.activo:
                    s = pr.stats()
                    return (f"Mejor racha de aciertos en práctica: {s['max_racha_win']} seguidos. "
                            f"Peor racha: {s['max_racha_loss']} pérdidas seguidas, señor.")
                return ("El modo práctica no está activo, señor. "
                        "Actívalo para ver rachas.")
            except Exception:
                return "No hay datos de racha disponibles, señor."

        if tiene("indicadores activos", "cuántos indicadores", "cuantos indicadores",
                 "que indicadores usa", "qué indicadores usa"):
            return ("Actualmente uso 22 indicadores técnicos: RSI, MACD, Bollinger, "
                    "Stocástico, Williams R, ATR, Momentum, ROC, OBV, Hurst, Entropía, "
                    "Racha, EMA triple, VWAP, Divergencia RSI, RVI, CCI, Fisher RSI, "
                    "Supertrend, Keltner, Elder Ray, CMO y Volume Profile. "
                    "Todo integrado en el consenso de 7 métodos, señor.")

        if tiene("mejores patrones", "patrones exitosos", "golden patterns",
                 "patrones que funcionan", "qué patrones ganan", "que patrones ganan"):
            try:
                fdb = getattr(a.agente, "fdb", None)
                if fdb is None:
                    return "FalloDB no disponible, señor."
                dorados = fdb.patrones_exitosos(min_wr=0.68)
                if not dorados:
                    return ("Todavía no tengo suficientes datos para identificar patrones "
                            "dorados, señor. Sigo aprendiendo.")
                top3 = dorados[:3]
                partes = " | ".join(
                    f"{p['patron']}→{p['dir']} WR={p['wr']}%({p['n']}ops)"
                    for p in top3)
                return (f"Mis mejores {len(top3)} patrones con WR≥68%: {partes}. "
                        f"Total patrones dorados identificados: {len(dorados)}, señor.")
            except Exception as e:
                return f"Error al consultar patrones: {e}"

        if tiene("peores patrones", "patrones peligrosos", "danger patterns",
                 "que patrones evitar", "qué patrones evitar", "patrones que fallan"):
            try:
                fdb = getattr(a.agente, "fdb", None)
                if fdb is None:
                    return "FalloDB no disponible, señor."
                peligrosos = fdb.peores_patrones(max_wr=0.38)
                if not peligrosos:
                    return "No hay patrones peligrosos identificados con suficiente historia, señor."
                top3 = peligrosos[:3]
                partes = " | ".join(
                    f"{p['patron']}→{p['dir']} WR={p['wr']}%({p['n']}ops)"
                    for p in top3)
                return (f"Patrones más peligrosos (WR≤38%): {partes}. "
                        f"Los estoy bloqueando activamente, señor.")
            except Exception as e:
                return f"Error al consultar patrones peligrosos: {e}"

        if tiene("recalibra", "re-calibra", "calibra pantalla", "calibra ahora",
                 "calibrar pantalla", "detecta botones", "busca botones"):
            a.calibrar_ahora()
            return "Re-calibrando todos los elementos de pantalla ahora mismo, senor."
        if tiene("rollover", "salida anticipada", "calibrar rollover",
                 "calibrar venta", "boton venta", "boton rollover"):
            a.calibrar_rollover_auto()
            return "Intentando detectar el área de P&L y el botón Rollover automáticamente."
        if tiene("pausa", "descansa", "para de operar", "deja de hacer trades",
                 "para el trading", "detén el trading"):
            a.agente._pausado_hasta = time.time() + 30 * 60
            return ("Entendido, señor. Me detengo 30 minutos. "
                    "Dime cuando quieras continuar o di «reanuda».")
        if tiene("reanuda", "continua", "sigue operando", "reactiva el trading",
                 "vuelve a tradear", "inicia trading", "reinicia trading",
                 "activa el trading", "vuelve a operar"):
            a.agente._pausado_hasta = 0.0
            # Resetear circuit breaker también (usuario autoriza explícitamente)
            if hasattr(a.agente, "_cb_activaciones"):
                a.agente._cb_activaciones = 0
            if not a.trading_on:
                a.trading_on = True
                if hasattr(a.agente, "_errores_consec"):
                    a.agente._errores_consec = 0
                return ("Trading reactivado, señor. Circuit breaker y errores reseteados. "
                        "Estoy atento al gráfico.")
            return ("Reanudando operaciones, señor. "
                    "Circuit breaker reseteado. Estoy atento al gráfico.")
        if tiene("calibra", "calibrar", "configura los botones", "configurar pantalla"):
            a.abrir_calibracion()
            return "Abriendo la calibración. Marcaremos el gráfico y los botones de compra y venta."

        # --- Cambio de monto / vencimiento por voz -----------------------
        _m_monto_voz = re.search(
            r"(?:monto|inversión|inversion|invertir).*?(\d+(?:\.\d+)?)",
            t, re.IGNORECASE)
        if _m_monto_voz and tiene("monto", "inversión", "inversion", "invertir",
                                  "cambiar a", "pon", "poner"):
            try:
                _new_m = float(_m_monto_voz.group(1))
                if 1 <= _new_m <= 10000:
                    a.mem["config"]["monto_base"] = _new_m
                    a.mem["config"]["monto_modo_manual"] = True
                    from . import memoria as _mem_voz
                    _mem_voz.guardar(a.mem)
                    try:
                        a.interfaz._qmonto_var.set(str(int(_new_m)))
                        a.interfaz._barra_monto_var.set(str(int(_new_m)))
                    except Exception:
                        pass
                    return f"Monto ajustado a ${_new_m:.0f}, señor."
            except Exception:
                pass

        _m_venc_voz = re.search(
            r"(?:vencimiento|cierre|expira|cerrar|tiempo|minuto|segundo).*?(\d+)\s*"
            r"(minuto|min|segundo|seg|s\b|m\b)?",
            t, re.IGNORECASE)
        if _m_venc_voz and tiene("vencimiento", "cierre", "tiempo de cierre",
                                 "expira en", "cerrar en", "operación de"):
            try:
                _n_vz = int(_m_venc_voz.group(1))
                _u_vz = (_m_venc_voz.group(2) or "").lower()
                _seg_vz = _n_vz * 60 if ("min" in _u_vz or _u_vz == "m") else _n_vz
                if 10 <= _seg_vz <= 3600:
                    a.mem["config"]["vencimiento"] = _seg_vz
                    from . import memoria as _mem_voz2
                    _mem_voz2.guardar(a.mem)
                    try:
                        a.interfaz._qvenc_var.set(str(_seg_vz))
                        a.interfaz._barra_venc_var.set(str(_seg_vz))
                    except Exception:
                        pass
                    _vm = _seg_vz // 60
                    _vs = _seg_vz % 60
                    _vt = f"{_vm}min" if _vs == 0 else f"{_vm}min {_vs}s"
                    return f"Vencimiento ajustado a {_vt}, señor. Las posiciones cerrarán en ese tiempo."
            except Exception:
                pass

        # --- Control del gráfico (zoom / centrado) -----------------------
        if tiene("centra el gráfico", "centra el grafico", "centrar gráfico",
                 "centrar grafico", "recentra", "ajusta el gráfico", "ajusta el grafico",
                 "grafico al centro", "gráfico al centro"):
            try:
                _gc_v = getattr(a, "gestor_grafico", None)
                if _gc_v is not None:
                    _gc_v.centrar_para_fable()
                    return "Gráfico centrado, señor."
                from . import chart_controls as _cc_v
                cfg_v = a.mem.get("config", {})
                ok_v = _cc_v.centrar(cfg_v.get("region_grafico"), cfg_v)
                return "Gráfico centrado, señor." if ok_v else "No pude centrar el gráfico. Verifique la calibración."
            except Exception:
                return "No pude centrar el gráfico. Verifique la calibración."

        if tiene("zoom más", "zoom mas", "acerca el gráfico", "acerca el grafico",
                 "ampliar gráfico", "ampliar grafico", "zoom in", "más detalle"):
            try:
                from . import chart_controls as _cc_v
                cfg_v = a.mem.get("config", {})
                ok_v = _cc_v.zoom_in(cfg_v.get("region_grafico"), cfg_v)
                return "Zoom aumentado, señor." if ok_v else "No pude hacer zoom. Verifique la calibración."
            except Exception:
                return "No pude hacer zoom. Verifique la calibración."

        if tiene("zoom menos", "aleja el gráfico", "aleja el grafico",
                 "alejar gráfico", "alejar grafico", "zoom out", "vista panorámica",
                 "vista panoramica", "ver más velas", "ver mas velas"):
            try:
                from . import chart_controls as _cc_v
                cfg_v = a.mem.get("config", {})
                ok_v = _cc_v.zoom_out(cfg_v.get("region_grafico"), cfg_v)
                return "Zoom reducido, señor." if ok_v else "No pude reducir el zoom. Verifique la calibración."
            except Exception:
                return "No pude reducir el zoom. Verifique la calibración."

        if tiene("zoom óptimo", "zoom optimo", "zoom ideal", "vista óptima",
                 "vista optima", "ajusta el zoom", "configurar zoom"):
            try:
                from . import chart_controls as _cc_v
                cfg_v = a.mem.get("config", {})
                periodo_v = int(cfg_v.get("periodo_vela", 60))
                ok_v = _cc_v.zoom_optimo(cfg_v.get("region_grafico"), cfg_v, periodo_v)
                return "Vista óptima aplicada, señor." if ok_v else "No pude ajustar el zoom. Verifique la calibración."
            except Exception:
                return "No pude ajustar el zoom. Verifique la calibración."

        # --- Instrucciones de broker / qué abrir -------------------------
        if tiene("qué broker abrir", "que broker abrir", "qué plataforma abrir",
                 "qué necesito abrir", "cómo empezar a operar", "como empezar a operar",
                 "no veo el gráfico", "no ves el grafico", "por qué no ves el gráfico",
                 "por que no ves el grafico", "qué falta para operar", "que falta para operar",
                 "no hay gráfico", "falta el gráfico", "abre el broker",
                 "dime qué abrir", "qué tengo que abrir"):
            cfg = a.mem.get("config", {})
            tiene_region  = bool(cfg.get("region_grafico"))
            tiene_botones = bool(cfg.get("boton_verde") and cfg.get("boton_rojo"))
            if tiene_region and tiene_botones:
                return ("Ya veo el gráfico y tengo los botones configurados. "
                        "Estoy listo para operar, señor. "
                        "Si desea comenzar diga: «activa el trading».")
            if tiene_region and not tiene_botones:
                return ("Veo el gráfico pero me faltan los botones de compra y venta. "
                        "Diga «Litch, calibra» para que los configure ahora mismo.")
            return (
                "Para que pueda analizar el mercado y operar, necesito ver un gráfico en pantalla. "
                "Abra el broker con el que desea operar — "
                "IQ Option es el que mejor conozco, pero también funciono con "
                "Interactive Brokers, Charles Schwab u otras plataformas con gráfico visible. "
                "Una vez abierto y con el gráfico visible, dígame: «Litch, calibra» "
                "y me configuro automáticamente. "
                "¿Qué broker desea usar, señor?"
            )

        # --- Tipo de cuenta: REAL vs DEMO ─────────────────────────────────
        # Va ANTES del bloque Práctica para que "demo" sea más específico.
        if tiene("cuenta real", "dinero real", "en real", "estoy en real",
                 "cambiar a real", "cambio a real", "opero en real",
                 "cuenta de verdad", "modo real account", "real money",
                 "real account", "cuenta verdadera", "soy real"):
            a.set_tipo_cuenta("real", hablar=False)
            return ("Registrado, señor. Operamos en CUENTA REAL — cada click del "
                    "Auto-click mueve dinero verdadero. Veré '>>> TRADE REAL' en el "
                    "log con cada operación. Presione Auto cuando esté listo.")

        if tiene("cuenta demo", "estoy en demo", "cambiar a demo", "cambio a demo",
                 "opero en demo", "cuenta de practica", "demo account",
                 "modo demo cuenta", "cuenta practice"):
            a.set_tipo_cuenta("demo", hablar=False)
            return ("Registrado, señor. Cuenta DEMO activa — practique sin riesgo. "
                    "Active Práctica para que opere autónomamente y aprenda haciendo.")

        if tiene("que cuenta", "qué cuenta", "tipo de cuenta", "en cual cuenta",
                 "demo o real", "real o demo", "which account", "tipo cuenta"):
            tipo = a.mem["config"].get("tipo_cuenta")
            if tipo == "real":
                return ("Operamos en CUENTA REAL, señor. Cada operación del "
                        "Auto-click usa dinero verdadero.")
            elif tipo == "demo":
                return ("Operamos en CUENTA DEMO, señor. "
                        "Las operaciones son de práctica sin riesgo real.")
            return ("No sé aún en qué cuenta estamos, señor. "
                    "Dígame 'cuenta real' o 'cuenta demo' para registrarlo.")

        # --- PILOTO AUTÓNOMO (Litch trabaja y aprende solo) ----------------
        if tiene("piloto autónomo", "piloto autonomo",
                 "trabaja solo", "hazlo tú solo", "hazlo tu solo",
                 "modo autónomo total", "modo autonomo total",
                 "aprende operando", "practica operando"):
            try:
                from . import piloto_autonomo as _pau
                if tiene("cómo va", "como va", "en qué nivel",
                         "en que nivel", "estado"):
                    return _pau.resumen(a)
                return _pau.alternar(a)
            except Exception as _e_pau:
                return f"No pude con el piloto autónomo: {_e_pau}"

        if tiene("en qué nivel estás", "en que nivel estas",
                 "tu nivel de autonomía", "tu nivel de autonomia",
                 "cuánta autonomía tienes", "cuanta autonomia tienes"):
            try:
                from . import piloto_autonomo as _pau
                return _pau.resumen(a)
            except Exception as _e_pn:
                return f"No pude leer el nivel: {_e_pn}"

        # --- PLEGAR LA BARRA (para que Litch vea más pantalla) -------------
        if tiene("esconde la barra", "oculta la barra", "pliega la barra",
                 "quita la barra", "baja la barra",
                 "muestra la barra", "despliega la barra",
                 "sube la barra", "vuelve a mostrar la barra"):
            try:
                _itf = getattr(a, "interfaz", None)
                if _itf is None:
                    return "No tengo la interfaz iniciada, señor."
                _esconder = not tiene("muestra", "despliega", "sube",
                                      "vuelve a mostrar")
                _itf.root.after(0, lambda: _itf._plegar_ribbon(
                    forzar=_esconder))
                if _esconder:
                    return ("Barra plegada, señor. Ahora veo 76 píxeles más "
                            "de pantalla: lo que antes quedaba debajo de la "
                            "barra estaba fuera de mi vista.")
                return "Barra desplegada, señor."
            except Exception as _e_pl:
                return f"No pude plegar la barra: {_e_pl}"

        # --- APRENDIZAJE ACTIVO DE IBKR (Litch toma el ratón) --------------
        if tiene("aprende a usar interactive", "aprende interactive brokers",
                 "aprendizaje activo", "aprende a usar tws",
                 "explora tws con el mouse", "explora tws con el ratón",
                 "empieza a aprender ibkr"):
            try:
                from . import aprendizaje_ibkr as _ai
                return _ai.alternar(a)
            except Exception as _e_ai:
                return f"No pude con el aprendizaje: {_e_ai}"

        if tiene("cuánto sabes de tws", "cuanto sabes de tws",
                 "qué has verificado", "que has verificado",
                 "progreso del aprendizaje", "ya dominas tws",
                 "qué brokers has aprendido", "que brokers has aprendido",
                 "cuánto sabes del broker", "cuanto sabes del broker"):
            try:
                from . import aprendizaje_broker as _ab
                return _ab.resumen(a)
            except Exception as _e_ar:
                return f"No pude leer el progreso: {_e_ar}"

        if tiene("qué broker ves", "que broker ves",
                 "qué broker tengo abierto", "que broker tengo abierto",
                 "reconoces este broker"):
            try:
                from . import aprendizaje_broker as _ab
                return _ab.que_veo(a)
            except Exception as _e_qv:
                return f"No pude mirar: {_e_qv}"

        if tiene("aprende este broker", "aprende el broker",
                 "aprende esta plataforma", "estudia este broker"):
            try:
                from . import aprendizaje_broker as _ab
                return _ab.alternar(a)
            except Exception as _e_ab:
                return f"No pude arrancar: {_e_ab}"

        # --- MAPA DEL CÓDIGO EN LA BÓVEDA ----------------------------------
        if tiene("mapea el código", "mapea el codigo",
                 "documenta el código", "documenta el codigo",
                 "actualiza el mapa del código",
                 "actualiza el mapa del codigo"):
            try:
                from . import mapa_codigo as _mcod
                return _mcod.generar(a)
            except Exception as _e_mc:
                return f"No pude mapear el código: {_e_mc}"

        # --- CONSULTAR LA BÓVEDA (el "segundo cerebro") --------------------
        #
        # Esta es la mitad que faltaba. Antes Litch solo ESCRIBÍA notas;
        # ahora las LEE antes de responder. Y las correcciones del usuario
        # pesan más que su propio análisis: él ha visto números, el usuario
        # ha visto el mercado.
        if tiene("según tus notas", "segun tus notas", "busca en tu bóveda",
                 "busca en tu boveda", "qué sabes tú de", "que sabes tu de",
                 "consulta tu memoria", "qué tienes sobre",
                 "que tienes sobre", "revisa tus notas"):
            try:
                from . import consulta_boveda as _cbv
                # Quitar la fórmula de la pregunta para quedarse con el tema
                _q = texto
                for _f in ("según tus notas", "segun tus notas",
                           "busca en tu bóveda", "busca en tu boveda",
                           "qué sabes tú de", "que sabes tu de",
                           "consulta tu memoria", "qué tienes sobre",
                           "que tienes sobre", "revisa tus notas",
                           "litch", "sobre", ","):
                    _q = _q.replace(_f, " ")
                _q = " ".join(_q.split())
                if not _q:
                    return _cbv.estado(a)
                return _cbv.responder(a, _q)
            except Exception as _e_cb:
                return f"No pude consultar la bóveda: {_e_cb}"

        if tiene("qué hay en tu bóveda", "que hay en tu boveda",
                 "estado de la bóveda", "estado de la boveda",
                 "cuántas notas tienes", "cuantas notas tienes"):
            try:
                from . import consulta_boveda as _cbv
                return _cbv.estado(a)
            except Exception as _e_eb:
                return f"No pude leer la bóveda: {_e_eb}"

        # --- BÓVEDA DE OBSIDIAN --------------------------------------------
        if tiene("actualiza la bóveda", "actualiza la boveda",
                 "exporta a obsidian", "actualiza obsidian",
                 "vuelca tu memoria", "escribe tus notas"):
            try:
                from . import boveda_obsidian as _bo
                return _bo.actualizar(a)
            except Exception as _e_bo:
                return f"No pude actualizar la bóveda: {_e_bo}"

        if tiene("dónde está la bóveda", "donde esta la boveda",
                 "abre obsidian", "dónde están tus notas",
                 "donde estan tus notas"):
            try:
                from . import boveda_obsidian as _bo
                return (f"Mi bóveda está en:\n\n  {_bo.ruta_boveda()}\n\n"
                        f"Ábrala desde Obsidian con «Abrir carpeta como "
                        f"bóveda» y empiece por «00 Índice». Si ve algo que "
                        f"he aprendido mal, corríjalo bajo «Mis notas»: eso "
                        f"no lo sobrescribo nunca.")
            except Exception as _e_rb:
                return f"No pude localizarla: {_e_rb}"

        # --- PRÁCTICA EN IBKR (no en IQ Option) ----------------------------
        if tiene("qué has aprendido de tws", "que has aprendido de tws",
                 "qué sabes ya de interactive", "que sabes ya de interactive",
                 "resumen de la práctica", "resumen de la practica",
                 "cómo va tu aprendizaje", "como va tu aprendizaje"):
            try:
                from . import practica_ibkr as _pi
                return _pi.resumen(a)
            except Exception as _e_pr:
                return f"No pude leer lo aprendido: {_e_pr}"

        if tiene("practica en ibkr", "practica en interactive",
                 "estudia interactive", "aprende interactive",
                 "explora interactive", "explora tws"):
            try:
                from . import practica_ibkr as _pi
                if tiene("para", "detén", "deten", "desactiva"):
                    return _pi.desactivar(a)
                return _pi.activar(a)
            except Exception as _e_pa:
                return f"No pude arrancar la práctica: {_e_pa}"

        # --- CONEXIÓN CON IBKR ---------------------------------------------
        #
        # UNA SOLA CONEXIÓN. Antes esto abría una segunda con ConexionIBKR,
        # y quedaban dos: la que opera (broker_ibkr, clientId 10) y otra
        # aparte. Dos conexiones consumen dos plazas de TWS y, lo que es
        # peor, la reconexión automática protegía a la que NO operaba.
        # Ahora broker_ibkr tiene su propia reconexión y es la única.
        if tiene("conecta con ibkr", "conéctate a ibkr", "conectate a ibkr",
                 "conecta con interactive", "conecta la api",
                 "conéctate a interactive", "conectate a interactive"):
            try:
                _br = getattr(a, "broker_ibkr", None)
                if _br is None:
                    return ("No tengo el conector de IBKR iniciado, señor. "
                            "Revise que TWS esté abierto y reinícieme.")
                if getattr(_br, "esta_conectado", False):
                    return ("Ya estaba conectado, señor.\n\n"
                            + _br.resumen())
                if _br.conectar(modo="paper"):
                    return ("Conectado a Interactive Brokers en la cuenta "
                            "simulada.\n\n" + _br.resumen())
                return ("No pude conectar, señor. Mire el registro: le he "
                        "dejado ahí los cuatro puntos que suelen fallar "
                        "(TWS abierto, API habilitada, puerto 7497 y "
                        "127.0.0.1 en IPs de confianza).")
            except Exception as _e_ci:
                return f"No pude conectar: {_e_ci}"

        if tiene("estado de la conexión", "estado de la conexion",
                 "cómo va la conexión", "como va la conexion",
                 "sigues conectado", "estás conectado a ibkr",
                 "estas conectado a ibkr"):
            try:
                _br = getattr(a, "broker_ibkr", None)
                if _br is None:
                    return "No tengo el conector de IBKR iniciado, señor."
                if not getattr(_br, "esta_conectado", False):
                    _rec = getattr(_br, "_reconectando", False)
                    return ("Sin conexión con Interactive Brokers"
                            + (", pero estoy reconectando ahora mismo."
                               if _rec else
                               ". Dígame «conecta con IBKR»."))
                _txt = _br.resumen()
                _n = getattr(_br, "_reconexiones", 0)
                if _n:
                    _txt += (f"\n\nHe tenido que reconectar {_n} vez/veces "
                             f"en esta sesión. Es normal si TWS reinició.")
                return _txt
            except Exception as _e_ce:
                return f"No pude leer el estado: {_e_ce}"

        if tiene("desconecta de ibkr", "desconéctate de ibkr",
                 "desconectate de ibkr", "cierra la conexión con ibkr"):
            try:
                _br = getattr(a, "broker_ibkr", None)
                if _br is None or not getattr(_br, "esta_conectado", False):
                    return "No había conexión abierta, señor."
                _br.desconectar()
                return ("Desconectado de Interactive Brokers, señor. No "
                        "reconectaré solo: la desconexión la pidió usted.\n\n"
                        "Sus órdenes de stop siguen puestas en el servidor "
                        "de IBKR aunque yo no esté conectado — eso no cambia.")
            except Exception as _e_cd:
                return f"No pude desconectar: {_e_cd}"

        # --- COLCHÓN DE MARGEN (AGENTE.md D.5) -----------------------------
        if tiene("cómo está mi margen", "como esta mi margen",
                 "excess liquidity", "colchón de margen",
                 "colchon de margen", "me pueden liquidar",
                 "cuánto margen me queda", "cuanto margen me queda"):
            try:
                from . import protocolo_agente as _pa
                return _pa.informe_liquidez(a)
            except Exception as _e_ml:
                return f"No pude leer el margen: {_e_ml}"

        # --- REGLA PDT (bloqueo de 90 días con cuenta pequeña) -------------
        if tiene("regla pdt", "day trades", "cuántos day trades",
                 "cuantos day trades", "pattern day trader",
                 "me pueden bloquear la cuenta"):
            try:
                from . import guardia_pdt as _pdt
                return _pdt.estado(a)
            except Exception as _e_pdt:
                return f"No pude comprobar la regla PDT: {_e_pdt}"

        # --- GESTIÓN DE POSICIONES ABIERTAS --------------------------------
        if tiene("cómo van mis posiciones", "como van mis posiciones",
                 "mis posiciones abiertas", "gestión de posiciones",
                 "gestion de posiciones", "cómo van las operaciones abiertas",
                 "estado de mis stops", "dónde están mis stops"):
            try:
                from . import gestor_posicion as _gp
                return _gp.estado(a)
            except Exception as _e_gp:
                return f"No pude leer las posiciones: {_e_gp}"

        if tiene("revisa los stops", "ajusta los stops",
                 "mueve los stops", "protege las posiciones"):
            try:
                from . import gestor_posicion as _gp
                return _gp.revisar_ahora(a)
            except Exception as _e_gp2:
                return f"No pude revisar los stops: {_e_gp2}"

        # --- RESULTADOS EN ACCIONES (el ciclo de aprendizaje) --------------
        if tiene("cómo van mis acciones", "como van mis acciones",
                 "resultado en acciones", "mis operaciones de acciones",
                 "cuánto llevo ganado", "cuanto llevo ganado",
                 "resumen de acciones", "mi rendimiento en wall street"):
            try:
                from . import vigilante_posiciones as _vp
                return _vp.resumen(a)
            except Exception as _e_vr:
                return f"No pude leer los resultados: {_e_vr}"

        if tiene("revisa las posiciones", "comprueba las posiciones",
                 "se cerró alguna", "se cerro alguna",
                 "actualiza las operaciones"):
            try:
                from . import vigilante_posiciones as _vp
                return _vp.revisar_ahora(a)
            except Exception as _e_vr2:
                return f"No pude revisar: {_e_vr2}"

        # --- MODO WALL STREET ----------------------------------------------
        if tiene("activa el modo wall street", "modo wall street",
                 "activa wall street", "empieza a operar acciones",
                 "opera en wall street", "modo bolsa"):
            try:
                from . import modo_wallstreet as _ws
                if tiene("apaga", "desactiva", "detén", "deten", "para"):
                    return _ws.desactivar(a)
                if tiene("estado", "cómo va", "como va", "qué llevas"):
                    return _ws.estado(a)
                _ejec = tiene("ejecutando", "que opere", "de verdad",
                              "ejecuta")
                return _ws.activar(a, ejecutar=_ejec)
            except Exception as _e_ws:
                return f"No pude con el modo Wall Street: {_e_ws}"

        if tiene("cómo va wall street", "como va wall street",
                 "estado de wall street", "estado del modo bolsa"):
            try:
                from . import modo_wallstreet as _ws
                return _ws.estado(a)
            except Exception as _e_ws2:
                return f"No pude leer el estado: {_e_ws2}"

        # --- RUTINAS DE OPERACIÓN EN IBKR ----------------------------------
        if tiene("revisión de apertura", "revision de apertura",
                 "revisa antes de operar", "checklist de apertura",
                 "estamos listos para operar", "revisión previa"):
            try:
                from . import rutinas_tws as _rt
                return _rt.revision_apertura(a).texto()
            except Exception as _e_ra2:
                return f"No pude hacer la revisión: {_e_ra2}"

        if tiene("ensayo general", "qué sabes hacer ya", "que sabes hacer ya",
                 "autoevalúate", "autoevaluate", "qué te falta",
                 "que te falta", "estás listo", "estas listo"):
            try:
                from . import rutinas_tws as _rt
                return _rt.ensayo_general(a)
            except Exception as _e_eg:
                return f"No pude autoevaluarme: {_e_eg}"

        if tiene("prepara una operación", "prepara una operacion",
                 "prepárame una operación", "preparame una operacion",
                 "arma una operación", "arma una operacion",
                 "rutina completa"):
            try:
                from . import rutinas_tws as _rt
                import re as _re_ro
                _m = _re_ro.search(
                    r"\b(SPY|VOO|QQQ|AAPL|MSFT|NVDA|AMZN|GOOGL|TSLA|META)\b",
                    texto.upper())
                _ejec = tiene("ejecuta", "de verdad", "envíala", "enviala")
                return _rt.preparar_operacion_verificada(
                    a, _m.group(1) if _m else "SPY", ejecutar=_ejec).texto()
            except Exception as _e_po:
                return f"No pude preparar la operación: {_e_po}"

        # ══════════════════════════════════════════════════════════════════
        #  TOCAR PARA APRENDER — se reconoce por INTENCIÓN, no por frase
        # ══════════════════════════════════════════════════════════════════
        #
        # La primera versión exigía decir «explora el bróker» o «practica
        # con el manual», palabra por palabra. El señor dijo «toca para
        # aprender», «empieza a hacer clic», «toca la pantalla para
        # aprender» — y Litch respondió «¿desea que busque información?».
        #
        # El comando existía y era inalcanzable hablando. Eso es peor que
        # no tenerlo, porque parece que el sistema está roto cuando lo
        # roto es el oído.
        #
        # Ahora se cruzan dos listas: un verbo de acción y una palabra de
        # contexto. «Toca … aprender», «clic … broker», «prueba … pantalla»
        # — todas caen. Y se tolera que el reconocimiento de voz escriba
        # «lich», «líder» o «leach» en vez de «Litch».
        _VERBOS_TOCAR = ("toca", "toque", "tocar", "clic", "click", "pulsa",
                         "pulse", "presiona", "explora", "explore", "explorar",
                         "prueba", "pruebe", "probar", "ensaya", "ensayar",
                         "interactua", "interactúa", "interactuar",
                         "manipula", "manipular", "usa las herramientas",
                         "practica", "practique", "practicar", "practiqu",
                         "comprueba", "comprobar", "verifica el manual")
        _CTX_APRENDER = ("aprend", "practic", "broker", "bróker", "pantalla",
                         "interactive", "tws", "funcion", "herramienta",
                         "manual", "boton", "botón", "ensay")
        _quiere_tocar = (any(v in t for v in _VERBOS_TOCAR)
                         and any(c in t for c in _CTX_APRENDER))
        # «no toques nada» / «deja de tocar» NO es una orden de empezar
        _es_parar = tiene("deja de", "para de", "detente", "no toques",
                          "no tocar", "basta")

        # --- EL CEREBRO AUTÓNOMO -------------------------------------------
        if tiene("cerebro autónomo", "cerebro autonomo",
                 "modo autónomo completo", "modo autonomo completo",
                 "vigílate sola", "vigilate sola", "repárate sola",
                 "reparate sola", "trabaja sola"):
            try:
                from . import cerebro_autonomo as _ca
                return _ca.alternar(a)
            except Exception as _e_ca:
                return f"No pude: {_e_ca}"

        if tiene("ajusta el monto solo", "ajusta el monto sola",
                 "tamaño automático", "tamano automatico"):
            try:
                from . import cerebro_autonomo as _ca
                return _ca.activar_tamano_auto(a, True)
            except Exception as _e_ta:
                return f"No pude: {_e_ta}"

        # --- ¿POR QUÉ NO OPERA? (los 14 eslabones) -------------------------
        if tiene("por qué no operas", "porque no operas",
                 "por qué no haces clic", "porque no haces clic",
                 "por qué no interactúas", "porque no interactuas",
                 "qué te falta para operar", "que te falta para operar",
                 "diagnóstico completo", "diagnostico completo"):
            try:
                from . import porque_no_opera as _pno
                return _pno.informe(a)
            except Exception as _e_pn:
                return f"No pude diagnosticar: {_e_pn}"

        if tiene("prueba el ratón", "prueba el raton", "el ratón funciona",
                 "el raton funciona", "puedes mover el ratón",
                 "puedes mover el raton"):
            try:
                from . import porque_no_opera as _pno
                return _pno.probar_clic(a)
            except Exception as _e_pc:
                return f"No pude probarlo: {_e_pc}"

        # --- CONFIGURARSE SOLA ---------------------------------------------
        if tiene("detecta iq option", "detéctate", "detectate",
                 "configúrate sola", "configurate sola", "búscate todo",
                 "buscate todo", "autoconfigúrate", "autoconfigurate",
                 "encuentra los botones", "busca los botones"):
            try:
                from . import autoconfigurar as _ac
                return _ac.ejecutar(a)
            except Exception as _e_ac:
                return f"No pude detectar: {_e_ac}"

        # --- ENTRENAMIENTO AUTOMÁTICO --------------------------------------
        if tiene("entrena sola", "entrénate", "entrenate",
                 "entrenamiento automático", "entrenamiento automatico",
                 "empieza a entrenar", "deja de entrenar", "para de entrenar"):
            try:
                from . import entrenador as _en
                return _en.alternar(a)
            except Exception as _e_en:
                return f"No pude: {_e_en}"

        if tiene("cómo va el entrenamiento", "como va el entrenamiento",
                 "estás mejorando", "estas mejorando", "has mejorado",
                 "tu progreso"):
            try:
                from . import entrenador as _en
                return _en.informe(a)
            except Exception as _e_ei:
                return f"No pude leerlo: {_e_ei}"

        # --- EL FRENO DIARIO -----------------------------------------------
        if tiene("cómo va el día", "como va el dia", "cuánto llevo hoy",
                 "cuanto llevo hoy", "el día de hoy", "el dia de hoy",
                 "freno diario", "cuánto he perdido hoy",
                 "cuanto he perdido hoy"):
            try:
                from . import freno_diario as _fd
                return _fd.informe(a)
            except Exception as _e_fd:
                return f"No pude leerlo: {_e_fd}"

        if tiene("levanta el freno", "quita el freno", "reinicia el freno",
                 "vuelve a operar hoy"):
            try:
                from . import freno_diario as _fd
                return _fd.reiniciar(a)
            except Exception as _e_fr:
                return f"No pude levantarlo: {_e_fr}"

        # --- CALIBRACIÓN POR MONITOR ---------------------------------------
        if tiene("traslada la calibración", "traslada la calibracion",
                 "traslada las coordenadas", "copia la calibración",
                 "copia la calibracion"):
            try:
                from . import calibracion_por_monitor as _cpm
                from . import monitores as _mon2
                _ms = _mon2.listar()
                _act = _mon2.monitor_de_barra(a)
                _otros = [m for m in _ms if m["n"] != _act["n"]]
                if not _otros:
                    return "Solo tengo una pantalla, señor."
                _n, _msg = _cpm.trasladar(a, _otros[0], _act)
                return _msg
            except Exception as _e_tr:
                return f"No pude trasladarla: {_e_tr}"

        if tiene("qué monitores están calibrados", "que monitores estan calibrados",
                 "calibración por monitor", "calibracion por monitor"):
            try:
                from . import calibracion_por_monitor as _cpm
                return _cpm.estado(a)
            except Exception as _e_ce:
                return f"No pude leerlo: {_e_ce}"

        # --- TAMAÑO POR OPERACIÓN (Kelly fraccionado) ----------------------
        if tiene("tamaño por operación", "tamano por operacion",
                 "kelly", "cuánto pongo en cada", "cuanto pongo en cada",
                 "tabla de tamaños", "tabla de tamanos"):
            try:
                from . import tamano_kelly as _tk
                return _tk.informe(a)
            except Exception as _e_tk:
                return f"No pude calcularlo: {_e_tk}"

        # --- CALIBRACIÓN: ¿acierta lo que dice? ----------------------------
        if tiene("estás calibrada", "estas calibrada", "tu calibración",
                 "tu calibracion", "aciertas lo que dices",
                 "tus porcentajes son reales", "ece"):
            try:
                from . import calibrar_confianza as _cal
                return _cal.informe(a)
            except Exception as _e_cal:
                return f"No pude calcularlo: {_e_cal}"

        # --- DÓNDE TIENE VENTAJA -------------------------------------------
        if tiene("dónde tienes ventaja", "donde tienes ventaja",
                 "dónde ganas", "donde ganas", "en qué horas ganas",
                 "en que horas ganas", "tu ventaja real"):
            try:
                from . import filtro_ventaja as _fv
                return _fv.informe(a)
            except Exception as _e_fv:
                return f"No pude calcularlo: {_e_fv}"

        # --- PREPARARSE PARA ENTRENAR SOLA ---------------------------------
        if tiene("prepárate para entrenar", "preparate para entrenar",
                 "voy a dejarte entrenando", "te voy a dejar entrenando",
                 "estás lista para entrenar", "estas lista para entrenar",
                 "prepárate", "preparate", "revisión de entrenamiento",
                 "revision de entrenamiento"):
            try:
                from . import preparar_entrenamiento as _pe
                return _pe.informe(a)
            except Exception as _e_pe:
                return f"No pude revisarme: {_e_pe}"

        _m_lim = re.search(r"l[ií]mite (?:de )?p[eé]rdida[s]?\s+"
                           r"(?:diaria?\s+)?(?:de\s+|en\s+)?"
                           r"((?:co\$|us\$|\$|€)?\s*[\d.,]+)", t)
        if _m_lim:
            try:
                from . import monto_real as _mr
                from . import preparar_entrenamiento as _pe
                _d = _mr.interpretar(_m_lim.group(1))
                if _d["monto"]:
                    return _pe.fijar_limite(a, _d["monto"])
            except Exception as _e_lim:
                return f"No pude fijar el límite: {_e_lim}"

        # --- MERCADO Y TAMAÑO DE POSICIÓN ----------------------------------
        _m_saldo = re.search(
            r"(?:mi saldo|saldo|capital|tengo|cuenta)\s+(?:es\s+|de\s+)?"
            r"((?:co\$|us\$|\$|€)?\s*[\d.,]+)", t)
        if _m_saldo and tiene("saldo", "capital"):
            try:
                from . import monto_real as _mr
                from . import memoria as _m
                _d = _mr.interpretar(_m_saldo.group(1))
                if _d["monto"]:
                    a.mem.setdefault("config", {})["saldo"] = _d["monto"]
                    if _d["divisa"]:
                        a.mem["config"]["divisa"] = _d["divisa"]
                    _m.guardar(a.mem)
                    from . import mercado_y_tamano as _myt
                    return (f"Anotado: capital {_mr.formatear(_d['monto'], _d['divisa'])}.\n\n"
                            + _myt.sugerir(a))
            except Exception as _e_sa:
                return f"No pude anotar el saldo: {_e_sa}"

        if tiene("cuánto debo invertir", "cuanto debo invertir",
                 "cuánto poner", "cuanto poner", "tamaño de posición",
                 "tamano de posicion", "cuánto arriesgo", "cuanto arriesgo"):
            try:
                from . import mercado_y_tamano as _myt
                return _myt.sugerir(a)
            except Exception as _e_ts:
                return f"No pude calcularlo: {_e_ts}"

        if tiene("qué mercado", "que mercado", "en qué estoy operando",
                 "en que estoy operando", "qué activo es", "que activo es",
                 "qué es otc", "que es otc", "esto es otc"):
            try:
                from . import mercado_y_tamano as _myt
                return _myt.informe(a)
            except Exception as _e_mi:
                return f"No pude identificarlo: {_e_mi}"

        # --- ESCALA TEMPORAL: VELA, VENCIMIENTO Y ZOOM ---------------------
        if tiene("ajusta el gráfico", "ajusta el grafico", "centra el gráfico",
                 "centra el grafico", "ajusta el zoom", "encuadra el gráfico",
                 "encuadra el grafico", "acomoda el gráfico",
                 "acomoda el grafico"):
            try:
                from . import escala_temporal as _et
                return _et.ajustar(a, ejecutar=True)
            except Exception as _e_et:
                return f"No pude ajustar el gráfico: {_e_et}"

        if tiene("cuadra la vela", "escala temporal", "vela y vencimiento",
                 "qué vela debo usar", "que vela debo usar",
                 "la vela es correcta", "el tiempo cuadra"):
            try:
                from . import escala_temporal as _et
                return _et.explicar(a)
            except Exception as _e_ee:
                return f"No pude explicarlo: {_e_ee}"

        # --- EN QUÉ MONITOR MIRAR ------------------------------------------
        # Mover la BARRA de sitio — distinto de dónde MIRA Litch
        _m_barra = re.search(
            r"(?:mueve|muevete|muévete|pasa|lleva|pon|ponte|cambia)\s+"
            r"(?:la\s+barra\s+)?(?:te\s+)?(?:a\s+|al\s+|en\s+|el\s+|la\s+)*"
            r"(?:monitor|pantalla)\s*(?:n[uú]mero\s*)?(\d)", t)
        if _m_barra:
            try:
                from . import monitores as _mo
                return _mo.mover_barra(a, int(_m_barra.group(1)))
            except Exception as _e_mb:
                return f"No pude mover la barra: {_e_mb}"

        _m_mon = re.search(
            r"(?:mira|usa|vete|trabaja|ve|opera|analiza)\s+"
            r"(?:en\s+|el\s+|la\s+|al\s+|a\s+)*"
            r"(?:monitor|pantalla)\s*(?:n[uú]mero\s*)?(\d)", t)
        if _m_mon:
            try:
                from . import monitores as _mo
                return _mo.fijar(a, int(_m_mon.group(1)))
            except Exception as _e_mo:
                return f"No pude cambiar de monitor: {_e_mo}"

        if tiene("elige tú el monitor", "elige tu el monitor",
                 "monitor automático", "monitor automatico",
                 "sigue al bróker", "sigue al broker"):
            try:
                from . import monitores as _mo
                return _mo.automatico(a)
            except Exception as _e_ma:
                return f"No pude ponerlo en automático: {_e_ma}"

        if tiene("qué monitores", "que monitores", "cuántas pantallas",
                 "cuantas pantallas", "en qué monitor", "en que monitor",
                 "qué pantalla ves", "que pantalla ves"):
            try:
                from . import monitores as _mo
                return _mo.descripcion(a)
            except Exception as _e_md2:
                return f"No pude listarlos: {_e_md2}"

        # --- LEER EL TICKET DE IQ OPTION -----------------------------------
        # Que Litch trabaje con LOS NÚMEROS DEL SEÑOR, no con los suyos.
        if tiene("calibra el ticket", "calibrar el ticket",
                 "calibra el monto", "señala el monto", "senala el monto"):
            try:
                from . import leer_ticket_iq as _lt
                return _lt.calibrar(a)
            except Exception as _e_lt:
                return f"No pude calibrar el ticket: {_e_lt}"

        if tiene("lee el ticket", "lee mi pantalla", "sincroniza el monto",
                 "actualiza el monto", "lee el monto", "lee los valores"):
            try:
                from . import leer_ticket_iq as _lt
                return _lt.sincronizar(a, hablar=False)
            except Exception as _e_ls:
                return f"No pude leerlo: {_e_ls}"

        if tiene("con qué números", "con que numeros", "qué valores usas",
                 "que valores usas", "con cuánto operas", "con cuanto operas",
                 "qué monto usas", "que monto usas", "qué vencimiento",
                 "que vencimiento"):
            try:
                from . import leer_ticket_iq as _lt
                return _lt.descripcion(a)
            except Exception as _e_ld:
                return f"No pude decirlo: {_e_ld}"

        # --- POR QUÉ SE CERRÓ LA VEZ PASADA --------------------------------
        if tiene("por qué te cerraste", "porque te cerraste",
                 "por qué te caíste", "porque te caiste",
                 "historial de cierres", "últimos cierres", "ultimos cierres",
                 "por qué se cerró", "porque se cerro"):
            try:
                from . import guardian_cierre as _gc
                _r = _gc.revisar_arranque(a) or ""
                return ((_r + "\n\n" if _r else "") + _gc.historial(10))
            except Exception as _e_gc2:
                return f"No pude revisarlo: {_e_gc2}"

        # --- MONTO Y DIVISA REALES ------------------------------------------
        # Manda lo que el señor tiene puesto en el bróker, no lo que Litch
        # llevara guardado. «CO$ 2.000» y «US$ 50» no se parecen en nada.
        _m_monto = re.search(
            r"(?:opero|operar|invierto|invertir|monto|apuesto|pongo|uso)\s+"
            r"(?:con\s+|de\s+)?"
            r"((?:co\$|us\$|mx\$|ar\$|r\$|€|£|\$)?\s*[\d.,]+)"
            r"\s*(pesos?|d[oó]lares?|euros?|reales?|libras?|cop|usd|eur)?", t)
        if _m_monto:
            try:
                from . import monto_real as _mr
                _cru = _m_monto.group(1)
                _uni = (_m_monto.group(2) or "").lower()
                _d = _mr.interpretar(_cru)
                if not _d["divisa"] and _uni:
                    _d["divisa"] = ("CO$" if "peso" in _uni or "cop" in _uni
                                    else "US$" if "dol" in _uni or "usd" in _uni
                                    else "€" if "euro" in _uni else "")
                if _d["monto"]:
                    return _mr.fijar(a, _d["monto"], _d["divisa"])
            except Exception as _e_mm:
                return f"No pude anotar el monto: {_e_mm}"

        if tiene("con cuánto operas", "con cuanto operas", "qué monto usas",
                 "que monto usas", "cuánto inviertes", "cuanto inviertes",
                 "qué divisa", "que divisa"):
            try:
                from . import monto_real as _mr
                return _mr.descripcion(a)
            except Exception as _e_md:
                return f"No pude leerlo: {_e_md}"

        # --- ¿CONVIENE OPERAR? LA MATEMÁTICA DEL PAGO ----------------------
        if tiene("conviene operar", "tengo ventaja", "tienes ventaja",
                 "vale la pena operar", "esperanza matemática",
                 "esperanza matematica", "punto de equilibrio",
                 "cuánto necesito acertar", "cuanto necesito acertar"):
            try:
                from . import ventaja_real as _vr
                import re as _re_vr
                _m = _re_vr.search(r"(\d{2,3})\s*%", texto)
                _pago = float(_m.group(1)) if _m else 85.0
                _cfg = a.mem.get("config", {})
                _mon = float(_cfg.get("monto_base") or _cfg.get("monto") or 50)
                _act = str(_cfg.get("asset", ""))
                return (_vr.explicar(_pago, _mon) + "\n\n" +
                        _vr.veredicto(a, _pago, _mon, _act))
            except Exception as _e_vr:
                return f"No pude calcularlo: {_e_vr}"

        # --- EL CUADRO DE CONFIRMACIÓN DE IQ OPTION ------------------------
        if tiene("cuadro de confirmación", "cuadro de confirmacion",
                 "botón de confirmación", "boton de confirmacion",
                 "confirmar la compra", "qué sabes de la confirmación",
                 "que sabes de la confirmacion", "comprar en un click"):
            try:
                from . import confirmacion_iq as _ci
                return _ci.explicar()
            except Exception as _e_ci:
                return f"No pude explicarlo: {_e_ci}"

        if tiene("confirmo yo", "yo confirmo", "voy a estar pendiente",
                 "voy a monitorear", "estoy monitoreando",
                 "no confirmes tú", "no confirmes tu"):
            try:
                a.mem.setdefault("config", {})["confirmar_yo"] = True
                from . import memoria as _m
                _m.guardar(a.mem)
                return ("Entendido, señor. Preparo la operación y le dejo el "
                        "cuadro de confirmación abierto: confirma usted. "
                        "Hasta que no pulse CONFIRMAR no doy la operación por "
                        "hecha ni anoto ningún resultado — porque hasta ese "
                        "momento no existe.")
            except Exception as _e_cy:
                return f"No pude configurarlo: {_e_cy}"

        if tiene("confirma tú", "confirma tu", "confirma sola",
                 "confirma automáticamente", "confirma automaticamente"):
            try:
                a.mem.setdefault("config", {})["confirmar_yo"] = False
                from . import memoria as _m
                _m.guardar(a.mem)
                return ("De acuerdo, señor. Confirmo yo, pero después "
                        "compruebo que el cuadro se cerró de verdad. Si "
                        "sigue abierto, la operación no salió y no la anoto.")
            except Exception as _e_ct:
                return f"No pude configurarlo: {_e_ct}"

        # --- INTERRUPTOR DEL MOTOR DE BINARIAS (IQ Option) -----------------
        # El señor manda sobre el motor, no la heurística. Antes se apagaba
        # solo en cuanto veía TWS abierto y se quedaba mudo para siempre.
        if tiene("enciende el motor", "activa el motor", "vuelve a predecir",
                 "quiero predicciones", "enciende iq", "activa iq option",
                 "vuelve a analizar el gráfico", "vuelve a analizar el grafico"):
            try:
                a.mem["config"]["motor_binario"] = True
                from . import memoria as _m
                _m.guardar(a.mem)
                return ("Motor de binarias encendido, señor. Vuelvo a "
                        "analizar el gráfico y a sacar los letreros de "
                        "predicción. Seguirá funcionando aunque tenga "
                        "Interactive Brokers abierto detrás.")
            except Exception as _e_me:
                return f"No pude encenderlo: {_e_me}"

        if tiene("apaga el motor", "desactiva el motor", "no predigas",
                 "apaga iq", "deja de analizar el gráfico",
                 "deja de analizar el grafico"):
            try:
                a.mem["config"]["motor_binario"] = False
                from . import memoria as _m
                _m.guardar(a.mem)
                return ("Motor de binarias apagado, señor. Dejo de analizar "
                        "velas y de predecir. Dígame «enciende el motor» "
                        "cuando quiera que vuelva.")
            except Exception as _e_ma:
                return f"No pude apagarlo: {_e_ma}"

        if tiene("por qué no predices", "porque no predices",
                 "por qué no analizas", "porque no analizas",
                 "estado del motor", "por qué no operas", "porque no operas"):
            try:
                from . import trading as _tr
                cfg = a.mem.get("config", {})
                sw = cfg.get("motor_binario")
                callado = _tr._motor_iq_debe_callar(a)
                l = ["ESTADO DEL MOTOR DE BINARIAS (IQ Option)", ""]
                l.append(f"· Interruptor: "
                         + ("encendido a mano" if sw is True else
                            "apagado a mano" if sw is False else "automático"))
                v, r = cfg.get("boton_verde"), cfg.get("boton_rojo")
                l.append(f"· Botones calibrados: "
                         + ("SUBE y BAJA ✓" if (v and r) else "FALTAN — "
                            "calíbrelos con «Litch calibra»"))
                if v and r:
                    try:
                        from . import manos as _mn
                        tv = _mn._dentro_de_tws(int(v[0]), int(v[1]))
                        tr_ = _mn._dentro_de_tws(int(r[0]), int(r[1]))
                        l.append(f"· ¿Alcanzables?: "
                                 + ("NO, los tapa Interactive Brokers"
                                    if (tv and tr_) else "sí"))
                    except Exception:
                        pass
                l.append(f"· Trading activo: {'sí' if a.trading_on else 'no'}")
                l.append(f"· Sistema activo: {'sí' if a.activo else 'no'}")
                l.append("")
                l.append("CONCLUSIÓN: " + ("estoy callado." if callado
                                           else "estoy analizando."))
                if callado:
                    l.append("Dígame «enciende el motor» y vuelvo a predecir.")
                elif not (a.activo and a.trading_on):
                    l.append("El motor puede, pero falta activar Sistema y "
                             "Trading en la barra.")
                return "\n".join(l)
            except Exception as _e_em:
                return f"No pude diagnosticarlo: {_e_em}"

        # Configurar el bróker siguiendo el instructivo del señor
        if tiene("configura el bróker", "configura el broker", "configura tws",
                 "configúrame el bróker", "configurame el broker",
                 "sigue el instructivo", "sigue el manual paso a paso",
                 "acomoda el bróker", "acomoda el broker"):
            try:
                from . import configurar_tws as _ct
                return _ct.todo(a)
            except Exception as _e_ct:
                return f"No pude configurar: {_e_ct}"

        if tiene("qué sabes configurar", "que sabes configurar",
                 "qué puedes configurar", "que puedes configurar"):
            try:
                from . import configurar_tws as _ct
                return _ct.listar()
            except Exception as _e_cl:
                return f"No pude listarlo: {_e_cl}"

        if _quiere_tocar and not _es_parar:
            # El fallo silencioso de antes: si algo aquí dentro reventaba,
            # el señor no veía NADA — ni respuesta ni error. Decía «toca
            # para aprender» cuatro veces y Litch se quedaba muda. Ahora
            # todo camino devuelve una frase, incluso el camino del fallo.
            _res = ""
            try:
                from . import practica_dirigida as _pd
                _res = _pd.alternar(a)
            except Exception as _e_pd:
                a.log(f"[Cerebro] Práctica dirigida falló: {_e_pd}")
                try:
                    from . import explorador_activo as _ex
                    _res = _ex.alternar(a)
                except Exception as _e_ex:
                    a.log(f"[Cerebro] Explorador falló: {_e_ex}")
                    _res = (f"Quiero tocar para aprender, señor, pero algo "
                            f"me lo impide: {_e_pd}. Compruebe que TWS está "
                            f"abierto y que pulsó AUTO — sin AUTO no tengo "
                            f"permiso para mover el ratón.")
            return _res or ("Entendí que quiere que toque para aprender, "
                            "pero no obtuve respuesta del explorador. "
                            "Dígame «¿qué puedes tocar?» y le digo en qué "
                            "estado estoy.")

        if _quiere_tocar and _es_parar:
            try:
                from . import practica_dirigida as _pd
                from . import explorador_activo as _ex
                r = []
                if getattr(_pd, "_inst", None) and _pd._inst.activo:
                    r.append(_pd.alternar(a))
                if getattr(_ex, "_inst", None) and _ex._inst.activo:
                    r.append(_ex.alternar(a))
                return " ".join(r) if r else "No estaba tocando nada, señor."
            except Exception as _e_dp:
                return f"No pude detenerlo: {_e_dp}"

        if tiene("qué has comprobado", "que has comprobado",
                 "manual comprobado", "qué herramientas dominas",
                 "que herramientas dominas"):
            try:
                from . import practica_dirigida as _pd
                return _pd.resumen(a)
            except Exception as _e_pr:
                return f"No pude leerlo: {_e_pr}"

        # --- PERMISOS: qué puede tocar Litch ahora --------------------------
        if tiene("qué puedes tocar", "que puedes tocar", "tus permisos",
                 "qué permisos tienes", "que permisos tienes",
                 "puedes enviar órdenes", "puedes enviar ordenes"):
            try:
                from . import permisos_broker as _pb
                return _pb.informe(a)
            except Exception as _e_pb:
                return f"No pude leer mis permisos: {_e_pb}"

        # --- EXPLORACIÓN ACTIVA DEL BRÓKER (clic y mide) -------------------
        if tiene("explora el bróker", "explora el broker", "explora tws",
                 "aprende haciendo clic", "explora interactive",
                 "empieza a explorar", "deja de explorar",
                 "para de explorar"):
            try:
                from . import explorador_activo as _ex
                return _ex.alternar(a)
            except Exception as _e_ex:
                return f"No pude explorar: {_e_ex}"

        if tiene("qué sabes del bróker", "que sabes del broker",
                 "mapa del bróker", "mapa del broker",
                 "qué has aprendido del broker", "que has aprendido del broker"):
            try:
                from . import explorador_activo as _ex
                return _ex.resumen(a)
            except Exception as _e_er:
                return f"No pude leer el mapa: {_e_er}"

        # --- CUARENTENA DE ESTADÍSTICAS CONTAMINADAS -----------------------
        if tiene("limpia las estadísticas", "limpia las estadisticas",
                 "cuarentena", "estadísticas falsas", "estadisticas falsas",
                 "revisa tus estadísticas", "revisa tus estadisticas",
                 "operaciones falsas", "trades falsos"):
            try:
                from . import cuarentena_stats as _cq
                return _cq.limpiar_todo(a)
            except Exception as _e_cq:
                return f"No pude hacer la cuarentena: {_e_cq}"

        # --- VISIÓN DE PANTALLA COMPLETA -----------------------------------
        if tiene("ve toda la pantalla", "mira toda la pantalla",
                 "visión completa", "vision completa",
                 "pantalla completa", "amplía tu visión", "amplia tu vision",
                 "ver toda la pantalla"):
            try:
                from . import vision_total as _vtot
                return _vtot.activar(a)
            except Exception as _e_vt:
                return f"No pude ampliar la visión: {_e_vt}"

        if tiene("qué estás viendo", "que estas viendo",
                 "cuánto ves", "cuanto ves", "tu campo de visión",
                 "tu campo de vision", "qué alcanzas a ver",
                 "que alcanzas a ver"):
            try:
                from . import vision_total as _vtot
                return _vtot.estado(a)
            except Exception as _e_ve:
                return f"No pude decirlo: {_e_ve}"

        if tiene("vuelve a iq option", "visión de iq", "vision de iq",
                 "restaura la visión de iq", "restaura la vision de iq"):
            try:
                from . import vision_total as _vtot
                return _vtot.restaurar_iq(a)
            except Exception as _e_vr:
                return f"No pude restaurarla: {_e_vr}"

        if tiene("verifica los datos", "verificar datos de mercado",
                 "el precio es real", "el precio está retrasado",
                 "el precio esta retrasado", "datos retrasados",
                 "datos en vivo", "revisa los datos de mercado"):
            try:
                from . import rutinas_tws as _rt
                import re as _re_vd
                _m = _re_vd.search(
                    r"\b(SPY|VOO|QQQ|AAPL|MSFT|NVDA|AMZN|GOOGL|TSLA|META)\b",
                    texto.upper())
                return _rt.verificar_datos(
                    a, _m.group(1) if _m else "SPY").texto()
            except Exception as _e_vd:
                return f"No pude verificar los datos: {_e_vd}"

        if tiene("qué rutinas tienes", "que rutinas tienes",
                 "lista tus rutinas", "tus procedimientos"):
            try:
                from . import rutinas_tws as _rt
                return _rt.listar_rutinas()
            except Exception as _e_lr:
                return f"No pude listarlas: {_e_lr}"

        # --- DIAGNÓSTICO: ¿por qué no ves TWS? -----------------------------
        if tiene("por qué no ves tws", "porque no ves tws",
                 "no ves interactive", "qué ventanas ves",
                 "que ventanas ves", "lista las ventanas",
                 "diagnostico de ventanas", "diagnóstico de ventanas"):
            try:
                from . import vision_tws as _vt3
                return _vt3.diagnostico_ventanas()
            except Exception as _e_dv:
                return f"No pude listar las ventanas: {_e_dv}"

        # --- VERIFICACIÓN DE CUENTA IBKR (la pregunta que más importa) -----
        if tiene("en qué cuenta estoy", "en que cuenta estoy",
                 "verifica la cuenta", "es simulada", "¿es real la cuenta",
                 "es real la cuenta", "qué cuenta de ibkr",
                 "que cuenta de ibkr", "confirma la cuenta"):
            try:
                _br = getattr(a, "broker_ibkr", None)
                if _br is not None and hasattr(_br, "verificar_cuenta"):
                    _v = _br.verificar_cuenta()
                    _msg = _v.get("mensaje", "")
                    # Segunda opinión: lo que veo en la ventana de TWS
                    try:
                        from . import vision_tws as _vt2
                        _e2 = _vt2.leer_estado_tws(a)
                        if _e2.get("tws_abierta"):
                            _p2 = _e2.get("es_paper")
                            _msg += (f" Además, en el título de TWS veo "
                                     f"{_e2.get('cuenta') or 'sin número'}: "
                                     + ("también simulada."
                                        if _p2 is True else
                                        "⚠ parece REAL." if _p2 is False
                                        else "no distingo el tipo."))
                    except Exception:
                        pass
                    return _msg
                return ("No tengo el conector de Interactive Brokers "
                        "iniciado, señor. Puedo mirar el título de TWS, "
                        "pero la confirmación buena viene de la API.")
            except Exception as _e_vc:
                return f"No pude verificar la cuenta: {_e_vc}"

        # --- PANEL SENCILLO ------------------------------------------------
        if tiene("panel sencillo", "panel simple", "abre el panel",
                 "modo fácil", "modo facil", "ventana sencilla",
                 "hazlo más fácil", "hazlo mas facil"):
            try:
                from . import panel_simple as _ps
                _raiz = getattr(getattr(a, "interfaz", None), "root", None)
                return _ps.abrir(a, _raiz)
            except Exception as _e_ps2:
                return f"No pude abrir el panel: {_e_ps2}"

        # --- CONCIENCIA DE PANTALLA COMPLETA -------------------------------
        if tiene("qué ves en la pantalla", "que ves en la pantalla",
                 "describe la pantalla", "mira toda la pantalla",
                 "qué estás viendo", "que estas viendo",
                 "ve la pantalla completa", "analiza la pantalla"):
            try:
                from . import conciencia_pantalla as _cpv
                return _cpv.describir_pantalla(a)
            except Exception as _e_dp:
                return f"No pude leer la pantalla: {_e_dp}"

        if tiene("observa la pantalla", "aprende la pantalla",
                 "aprende mi distribución", "aprende mi distribucion",
                 "estudia la pantalla"):
            try:
                from . import conciencia_pantalla as _cpv
                return _cpv.observar_y_aprender(a)
            except Exception as _e_op:
                return f"No pude observar: {_e_op}"

        if tiene("qué has aprendido de la pantalla",
                 "que has aprendido de la pantalla",
                 "resumen de la pantalla", "mapa de la pantalla"):
            try:
                from . import conciencia_pantalla as _cpv
                return _cpv.resumen_aprendido()
            except Exception as _e_ra:
                return f"No pude resumir: {_e_ra}"

        if tiene("hay algo estorbando", "hay algún diálogo", "hay algun dialogo",
                 "está despejado", "esta despejado", "revisa si hay ventanas"):
            try:
                from . import conciencia_pantalla as _cpv
                return _cpv.detectar_dialogo(a).get("mensaje", "")
            except Exception as _e_dd:
                return f"No pude revisar: {_e_dd}"

        # --- ESCUELA DE INTERACTIVE BROKERS --------------------------------
        if tiene("qué herramientas tiene ibkr", "que herramientas tiene ibkr",
                 "qué herramientas tiene interactive",
                 "que herramientas tiene interactive",
                 "herramientas de tws", "qué sabes de ibkr",
                 "que sabes de ibkr", "lista de herramientas"):
            try:
                from . import escuela_ibkr as _ei
                return _ei.listar()
            except Exception as _e_li:
                return f"No pude listar: {_e_li}"

        if tiene("siguiente lección", "siguiente leccion", "próxima lección",
                 "proxima leccion", "enséñame algo", "ensename algo",
                 "empecemos la escuela", "clase de ibkr"):
            try:
                from . import escuela_ibkr as _ei
                return _ei.siguiente_leccion(a)
            except Exception as _e_sl:
                return f"No pude dar la lección: {_e_sl}"

        if tiene("lección aprendida", "leccion aprendida", "ya lo entendí",
                 "ya lo entendi", "siguiente tema", "lo tengo claro"):
            try:
                from . import escuela_ibkr as _ei
                return _ei.marcar_aprendida(a)
            except Exception as _e_ma:
                return f"No pude anotarlo: {_e_ma}"

        if tiene("mi progreso", "cuánto llevo aprendido",
                 "cuanto llevo aprendido", "progreso de la escuela",
                 "qué he aprendido", "que he aprendido"):
            try:
                from . import escuela_ibkr as _ei
                return _ei.progreso(a)
            except Exception as _e_pr:
                return f"No pude leer el progreso: {_e_pr}"

        if tiene("consejo del día", "consejo del dia", "dame un consejo",
                 "algún consejo", "algun consejo"):
            try:
                from . import escuela_ibkr as _ei
                return _ei.consejo_del_dia()
            except Exception as _e_cd:
                return f"No pude darle el consejo: {_e_cd}"

        if tiene("explícame el", "explicame el", "explícame la", "explicame la",
                 "qué es el bracket", "que es el bracket", "para qué sirve",
                 "para que sirve", "qué es una orden", "que es una orden"):
            try:
                from . import escuela_ibkr as _ei
                _clave = _ei._buscar(texto)
                if _clave:
                    return _ei.explicar(_clave)
            except Exception:
                pass      # si no es de IBKR, que siga el flujo normal

        # --- PILOTO TWS: Litch opera Trader Workstation con sus manos ------
        if tiene("calibra el ticket", "calibrar el ticket",
                 "calibra el ticket de tws", "calibra los campos",
                 "calibra tws", "enséñame dónde está cada campo",
                 "ensename donde esta cada campo"):
            try:
                from . import piloto_tws as _pt
                return _pt.calibrar_ticket(a)
            except Exception as _e_ct:
                return f"No pude iniciar la calibración: {_e_ct}"

        if tiene("estado de la calibración", "estado de la calibracion",
                 "¿está calibrado", "esta calibrado", "calibración de tws",
                 "calibracion de tws"):
            try:
                from . import piloto_tws as _pt
                return _pt.estado_calibracion(a)
            except Exception as _e_ec:
                return f"No pude leer el estado: {_e_ec}"

        if tiene("enséñame tws", "ensename tws", "enséñame a operar",
                 "ensename a operar", "lección de tws", "leccion de tws",
                 "muéstrame tws", "muestrame tws", "recorrido de tws",
                 "enséñame interactive", "ensename interactive"):
            try:
                from . import piloto_tws as _pt
                import re as _re_l
                m = _re_l.search(r"\b(SPY|VOO|QQQ|AAPL|MSFT|NVDA|AMZN|GOOGL)\b",
                                 texto.upper())
                return _pt.leccion_guiada(a, m.group(1) if m else "SPY")
            except Exception as _e_lg:
                return f"No pude dar la lección: {_e_lg}"

        if tiene("pon el simbolo", "pon el símbolo", "carga el simbolo",
                 "carga el símbolo", "cambia el activo en tws"):
            try:
                from . import piloto_tws as _pt
                import re as _re_s
                m = _re_s.search(r"\b(SPY|VOO|QQQ|AAPL|MSFT|NVDA|AMZN|GOOGL|TSLA|META)\b",
                                 texto.upper())
                if not m:
                    return "¿Qué símbolo cargo? Por ejemplo: 'pon el símbolo SPY'."
                _ensayo = not tiene("de verdad", "hazlo real", "ejecuta")
                return _pt.poner_simbolo(a, m.group(1), ensayo=_ensayo)
            except Exception as _e_ps:
                return f"No pude cargar el símbolo: {_e_ps}"

        if tiene("prepara la orden en tws", "arma la orden en tws",
                 "llena el ticket", "prepara el ticket"):
            try:
                from . import piloto_tws as _pt
                import re as _re_o
                m = _re_o.search(r"\b(SPY|VOO|QQQ|AAPL|MSFT|NVDA|AMZN|GOOGL)\b",
                                 texto.upper())
                sim = m.group(1) if m else "SPY"
                acc = "VENDER" if tiene("vend", "corto") else "COMPRAR"
                mc = _re_o.search(r"\b(\d{1,4})\s*(acciones|unidades)?\b", t)
                cant = int(mc.group(1)) if mc else 1
                _ensayo = not tiene("de verdad", "hazlo real", "ejecuta")
                return _pt.preparar_orden(a, sim, acc, cant, ensayo=_ensayo)
            except Exception as _e_po:
                return f"No pude preparar la orden: {_e_po}"

        if tiene("confirma el envío", "confirma el envio", "pulsa enviar",
                 "envía la orden en tws", "envia la orden en tws"):
            try:
                from . import piloto_tws as _pt
                return _pt.pulsar_enviar(a)
            except Exception as _e_pe:
                return f"No pude enviar: {_e_pe}"

        # --- APRENDIZ: Litch observa al usuario operar TWS y aprende -------
        if tiene("observa tws", "obsérvame operar", "observame operar",
                 "modo aprendiz", "aprende mirándome", "aprende mirandome",
                 "mírame operar", "mirame operar", "aprende viendo"):
            try:
                from . import aprendiz_tws as _ap
                ap = _ap.obtener(a)
                a.aprendiz_tws = ap
                if tiene("detén", "deten", "para", "apaga", "desactiva"):
                    return ap.desactivar()
                return ap.activar()
            except Exception as _e_ap:
                return f"No pude activar el modo aprendiz: {_e_ap}"

        if tiene("qué has aprendido de tws", "que has aprendido de tws",
                 "lecciones de tws", "qué aprendiste mirándome",
                 "que aprendiste mirandome", "resumen del aprendiz"):
            try:
                from . import aprendiz_tws as _ap
                return _ap.obtener(a).resumen()
            except Exception:
                pass

        # --- VISIÓN de IBKR / TWS (ver el broker en tiempo real) -----------
        if tiene("calibra para ibkr", "calibra para tws", "calibra ibkr",
                 "calibra tws", "mira interactive", "ve a interactive",
                 "apunta a tws", "cambia a ibkr", "modo ibkr"):
            try:
                from . import vision_tws as _vt
                return _vt.calibrar_para_tws(a)
            except Exception as _e_vt:
                return f"No pude calibrar para TWS: {_e_vt}"

        if tiene("vuelve a iq", "calibra para iq", "modo iq option",
                 "cambia a iq"):
            try:
                from . import vision_tws as _vt
                return _vt.volver_a_iq(a)
            except Exception:
                pass

        if tiene("ves tws", "ves interactive", "ves el broker",
                 "estado de tws", "qué ves en tws", "que ves en tws",
                 "ves ibkr", "estado visual ibkr"):
            try:
                from . import vision_tws as _vt
                return _vt.leer_estado_tws(a)["mensaje"]
            except Exception as _e_ve:
                return f"No pude revisar TWS: {_e_ve}"

        # --- Memoria de ACCIONES (qué gana y qué pierde en Wall Street) ----
        if tiene("memoria de acciones", "qué has aprendido de acciones",
                 "que has aprendido de acciones", "mis setups",
                 "mejores setups", "setups que ganan", "setups que pierden",
                 "rendimiento en acciones", "cómo vas en wall street",
                 "como vas en wall street"):
            try:
                from . import memoria_acciones as _mem_a
                return _mem_a.obtener().resumen("es")
            except Exception as _e_mm:
                return f"No pude leer la memoria de acciones: {_e_mm}"

        # --- Motor de ACCIONES (Wall Street) -------------------------------
        if tiene("analiza spy", "analiza voo", "analiza qqq", "analiza aapl",
                 "analiza msft", "analiza la accion", "analiza la acción",
                 "qué opinas de spy", "que opinas de spy", "analiza wall street"):
            try:
                from . import motor_acciones as _ma
                import re as _re_a
                m = _re_a.search(r"\b(SPY|VOO|QQQ|AAPL|MSFT|NVDA|TSLA|AMZN|GOOGL|META)\b",
                                 texto.upper())
                sim = m.group(1) if m else "SPY"
                return _ma.resumen_analisis(a, sim)
            except Exception as _e_ma:
                return f"No pude analizar: {_e_ma}"

        if tiene("prepara la operación", "prepara la operacion",
                 "plan de operación", "plan de operacion",
                 "prepara una compra", "prepara un trade", "arma la orden"):
            try:
                from . import motor_acciones as _ma
                import re as _re_p
                m = _re_p.search(r"\b(SPY|VOO|QQQ|AAPL|MSFT|NVDA|TSLA|AMZN|GOOGL|META)\b",
                                 texto.upper())
                sim = m.group(1) if m else "SPY"
                plan = _ma.preparar_operacion(a, sim)
                return plan["mensaje"]
            except Exception as _e_pp:
                return f"No pude preparar la operación: {_e_pp}"

        if tiene("qué activos", "que activos", "qué acciones compro",
                 "que acciones compro", "activos recomendados",
                 "qué me recomiendas comprar", "que me recomiendas comprar"):
            try:
                from . import motor_acciones as _ma
                return _ma.activos_sugeridos()
            except Exception:
                pass

        # --- TWS: conocimiento operativo (pantalla, protocolo, checklist) --
        if tiene("estoy listo para operar", "estas listo para operar",
                 "estás listo para operar", "checklist wall street",
                 "listo para wall street", "puedo operar en wall street",
                 "estado para operar"):
            try:
                from . import tws_operacion as _tws
                return _tws.checklist_listo(a)
            except Exception as _e_t:
                return f"No pude revisar el estado: {_e_t}"

        if tiene("pantalla de tws", "mapa de tws", "qué hay en tws",
                 "que hay en tws", "cómo es tws", "como es tws",
                 "explícame tws", "explicame tws"):
            try:
                from . import tws_operacion as _tws
                return _tws.mapa_pantalla("es")
            except Exception:
                pass

        if tiene("cómo calibro tws", "como calibro tws", "calibrar tws",
                 "calibrar en tws", "calibra para tws"):
            try:
                from . import tws_operacion as _tws
                return _tws.guia_calibracion("es")
            except Exception:
                pass

        if tiene("protocolo de acciones", "cómo operas acciones",
                 "como operas acciones", "cómo se operan acciones",
                 "protocolo wall street"):
            try:
                from . import tws_operacion as _tws
                return _tws.protocolo("es")
            except Exception:
                pass

        if tiene("diferencia entre binarias y acciones",
                 "binarias vs acciones", "diferencia acciones binarias"):
            try:
                from . import tws_operacion as _tws
                return _tws.diferencia("es")
            except Exception:
                pass

        # --- IBKR: conectar y operar acciones (paper primero) --------------
        if tiene("conecta ibkr", "conectar ibkr", "conéctate a ibkr",
                 "conectate a ibkr", "conecta interactive", "conectar tws",
                 "conecta con tws", "conéctate a interactive"):
            try:
                br = getattr(a, "broker_ibkr", None)
                if br is None:
                    return "El módulo de IBKR no está disponible, señor."
                # SIEMPRE paper por defecto (seguridad Manual 13)
                _modo = "real" if tiene("real", "en vivo", "dinero real") else "paper"
                if _modo == "real":
                    return ("Por seguridad no conecto a la cuenta REAL desde "
                            "un comando de voz, señor. Primero demuestre "
                            "resultados en paper; luego lo hacemos juntos "
                            "con confirmación explícita.")
                ok = br.conectar(modo="paper")
                if ok:
                    return ("Conectado a Interactive Brokers en cuenta PAPER "
                            "(simulada), señor. Puedo cotizar, comprar y "
                            "vender acciones con dinero ficticio. Dígame "
                            "'cotiza VOO' o 'compra 1 de SPY'.")
                return ("No pude conectar. Verifique que TWS esté abierto en "
                        "modo Paper y que la API esté habilitada (puerto "
                        "7497). Diga 'diagnóstico IBKR' para revisarlo.")
            except Exception as _e_ib:
                return f"Error al conectar con IBKR: {_e_ib}"

        if tiene("cotiza ", "cotización de", "cotizacion de", "precio de ",
                 "cuánto vale ", "cuanto vale "):
            try:
                br = getattr(a, "broker_ibkr", None)
                if br is not None and getattr(br, "esta_conectado", False):
                    import re as _re_c
                    m = _re_c.search(r"\b([A-Z]{1,5})\b", texto.upper())
                    if m:
                        sim = m.group(1)
                        c = br.cotizacion(sim)
                        if c:
                            return (f"{sim}: último {c.get('ultimo','?')} | "
                                    f"compra {c.get('bid','?')} / venta "
                                    f"{c.get('ask','?')}, señor.")
                        return f"No obtuve cotización de {sim}, señor."
            except Exception:
                pass

        if tiene("posiciones ibkr", "mis posiciones", "qué tengo comprado",
                 "que tengo comprado", "mi cartera ibkr"):
            try:
                br = getattr(a, "broker_ibkr", None)
                if br is None or not getattr(br, "esta_conectado", False):
                    return ("No estoy conectado a IBKR, señor. Diga "
                            "'conecta IBKR' con TWS abierto en paper.")
                pos = br.posiciones()
                if not pos:
                    return "No tiene posiciones abiertas en IBKR, señor."
                lineas = [f"· {p.get('simbolo','?')}: {p.get('cantidad',0)} "
                          f"@ {p.get('precio_medio','?')}" for p in pos[:10]]
                return "Posiciones en IBKR:\n" + "\n".join(lineas)
            except Exception as _e_p:
                return f"No pude leer las posiciones: {_e_p}"

        # --- Guardias de riesgo / cortacircuitos (Manual 13 integrado) ----
        if tiene("cómo está mi riesgo", "como esta mi riesgo", "mi riesgo",
                 "cortacircuitos", "nivel de riesgo", "estoy diversificado",
                 "cuánto puedo perder", "cuanto puedo perder",
                 "debería seguir operando", "deberia seguir operando"):
            try:
                from . import guardias_riesgo as _gr
                return _gr.resumen_riesgo(a, idioma=a.idioma)
            except Exception as _e_gr:
                return f"No pude evaluar el riesgo: {_e_gr}"

        # --- Tareas programadas (cron interno estilo Jarvis) --------------
        if tiene("tareas programadas", "que tienes programado",
                 "qué tienes programado", "tareas pendientes programadas"):
            tp = getattr(a, "tareas", None)
            return tp.listar() if tp else "El programador no está activo, señor."

        if tiene("borra las tareas", "elimina las tareas",
                 "cancela las tareas", "limpia las tareas"):
            tp = getattr(a, "tareas", None)
            return tp.limpiar() if tp else "El programador no está activo, señor."

        if (tiene("programa", "agenda", "programar", "agendar")
                and ("a las" in t or re.search(r"\d{1,2}[:h.]\d{2}", t))):
            tp = getattr(a, "tareas", None)
            if tp is None:
                return "El programador no está activo, señor."
            try:
                from . import tareas_programadas as _tpm
                accion, hora, diaria = _tpm.interpretar_orden(t)
                if accion is None and hora is None:
                    return ("No entendí la hora, señor. Ejemplo: 'programa "
                            "el modo nocturno a las 22:00'.")
                if accion is None:
                    return ("Entendí la hora pero no la acción. Puedo "
                            "programar: modo nocturno, entrenamiento, "
                            "práctica, análisis, respaldo, guardado, "
                            "reporte o apagar.")
                return tp.agregar(hora, accion, diaria)
            except Exception as _e_tp:
                return f"No pude programar la tarea: {_e_tp}"

        # --- Modo nocturno (entrenamiento continuo toda la noche) -------
        if tiene("modo nocturno", "entrenamiento nocturno", "entrena toda la noche",
                 "entrenamiento continuo", "night mode", "train all night"):
            try:
                from . import entrenador_historico as _eh
                if tiene("detén", "deten", "para", "apaga", "stop", "desactiva"):
                    return _eh.detener_modo_nocturno()
                return _eh.iniciar_modo_nocturno(a)
            except Exception as _e_n:
                return f"No pude gestionar el modo nocturno: {_e_n}"

        # --- Diagnóstico IBKR --------------------------------------------
        if tiene("diagnostico ibkr", "diagnóstico ibkr", "prueba ibkr",
                 "revisa ibkr", "estado ibkr", "listo para ibkr",
                 "interactive brokers listo", "conexion ibkr", "conexión ibkr"):
            try:
                from . import ibkr_diagnostico as _ibd
                return _ibd.resumen_texto(idioma=a.idioma)
            except Exception as _e_ib:
                return f"No pude ejecutar el diagnóstico IBKR: {_e_ib}"

        # --- Entrenamiento histórico con datos reales -------------------
        if tiene("entrena con historial", "entrenamiento historico",
                 "entrenamiento histórico", "entrena con el mercado",
                 "entrenate solo", "entrénate solo", "entrena tu red",
                 "entrena con datos reales", "pre-entrena", "preentrena"):
            try:
                from . import entrenador_historico as _eh
                if _eh.en_curso():
                    return ("Ya estoy entrenando con historial, señor. "
                            "Le avisaré al terminar.")
                if not _eh.disponible():
                    return ("Necesito yfinance para descargar historial real. "
                            "Ejecute: pip install yfinance")
                _eh.entrenar_en_fondo(a)
                return ("Iniciando entrenamiento con miles de velas reales de "
                        "EUR/USD, GBP/USD, USD/JPY, oro y Bitcoin en varios "
                        "timeframes, señor. Trabajaré en segundo plano y le "
                        "avisaré al terminar.")
            except Exception as _e_eh:
                return f"No pude iniciar el entrenamiento histórico: {_e_eh}"

        # --- Modo Práctica DEMO ----------------------------------------
        if tiene("práctica", "practica", "demo", "entrenamiento", "practica demo",
                 "empieza a practicar", "comienza a practicar", "entrena",
                 "practica autonoma", "práctica autónoma", "opera en demo"):
            practica = getattr(a, "modo_practica", None)
            if not practica:
                return "El módulo de práctica no está disponible, señor."
            if tiene("desactiva", "detén", "para", "apaga", "desconecta", "stop"):
                if practica.activo:
                    practica.desactivar()
                    s = practica.stats()
                    return (f"Modo práctica desactivado. Sesión: {s['trades']} trades, "
                            f"WR {s['wr']:.0f}%, señor.")
                return "El modo práctica ya estaba inactivo, señor."
            # Activar
            practica.activar()
            return ("Modo práctica DEMO activado, señor. Operaré en la cuenta demo con umbrales "
                    "reducidos para aprender lo más rápido posible. Cada trade me enseña "
                    "un patrón nuevo. Puede pedirme 'cómo voy' cuando quiera.")

        # --- Modo Profesional ------------------------------------------
        if tiene("modo profesional", "profesional", "professional mode",
                 "activa profesional", "opera en real", "capital real",
                 "empieza profesional"):
            profesional = getattr(a, "modo_profesional", None)
            if not profesional:
                return "El módulo profesional no está disponible, señor."
            if tiene("desactiva", "detén", "para", "apaga", "stop"):
                if profesional.activo:
                    profesional.desactivar()
                    s = profesional.stats()
                    return (f"Modo profesional desactivado. Sesión: {s['trades']} trades, "
                            f"WR {s['wr']:.0f}%, Kelly P&L {s['pnl_kelly']:+.2f}, "
                            f"Sharpe {s['sharpe']:+.2f}, DD_max {s['dd_actual']:.1f}%, señor.")
                return "El modo profesional ya estaba inactivo, señor."
            # Verificar si tiene suficiente práctica
            practica = getattr(a, "modo_practica", None)
            from . import modo_profesional as _pro_mod
            if practica:
                s_p = practica.stats()
                listo = _pro_mod.ModoProfesional.deberia_activarse(s_p)
                if not listo and s_p["trades"] > 0:
                    a.log(f"[PRO] Práctica: {s_p['trades']} trades WR={s_p['wr']:.0f}% "
                          f"— bajo criterio mínimo (30t/60%WR)")
            # Leer capital inicial para el gate de drawdown
            _cap_ini = 0.0
            try:
                _cap_ini = float(a.mem.get("config", {}).get("saldo_inicio", 0.0))
            except Exception:
                pass
            profesional.activar(capital_inicio=_cap_ini)
            ses_info = profesional._sesion_actual()
            return (f"Modo profesional activado, señor. "
                    f"Filtros: 5/7 motores, prob>{_pro_mod.PROB_MIN:.3f}, Kelly>{_pro_mod.KELLY_MIN}. "
                    f"Sesión actual: {ses_info['nombre']} (factor×{ses_info['factor']:.2f}). "
                    "Solo opero con señales de máxima calidad.")

        # --- Override manual de abstención (Conciencia) -----------------
        if tiene("no te abstengas", "opera siempre", "ignora la conciencia",
                 "fuerza las operaciones", "forzar operar", "no pares de operar",
                 "override operar", "activa override", "opera a pesar de todo",
                 "sigue operando", "desactiva la abstención", "desactiva abstencion",
                 "no te frenes", "no te detengas por conciencia"):
            con = getattr(a, "conciencia", None)
            if con is None:
                from . import conciencia as _con_mod
                con = _con_mod.obtener(a)
            if con:
                msg = con.set_override("forzar_actuar")
                return (f"Entendido, señor. {msg} "
                        f"Tenga en cuenta que la conciencia seguirá aprendiendo "
                        f"en segundo plano para mejorar sus recomendaciones.")
            return "El sistema de conciencia no está disponible, señor."

        if tiene("abstente", "no operes", "para de operar por conciencia",
                 "fuerza la abstención", "fuerza abstencion", "override abstener",
                 "pausa por conciencia", "detente por conciencia",
                 "bloquea las operaciones", "congela el trading"):
            con = getattr(a, "conciencia", None)
            if con is None:
                from . import conciencia as _con_mod
                con = _con_mod.obtener(a)
            if con:
                msg = con.set_override("forzar_abstener")
                return f"Entendido, señor. {msg}"
            return "El sistema de conciencia no está disponible, señor."

        if tiene("conciencia automática", "conciencia automatica",
                 "modo automático conciencia", "modo auto conciencia",
                 "deja decidir a la conciencia", "que decida la conciencia",
                 "restaura la conciencia", "quita el override",
                 "conciencia normal", "desactiva el override"):
            con = getattr(a, "conciencia", None)
            if con is None:
                from . import conciencia as _con_mod
                con = _con_mod.obtener(a)
            if con:
                msg = con.set_override("auto")
                return f"Perfecto, señor. {msg}"
            return "El sistema de conciencia no está disponible, señor."

        if tiene("estado conciencia", "override activo", "cómo está la conciencia",
                 "como esta la conciencia", "qué modo conciencia",
                 "modo de abstención", "modo de abstencion"):
            con = getattr(a, "conciencia", None)
            if con is None:
                from . import conciencia as _con_mod
                con = _con_mod.obtener(a)
            if con:
                modo = con.estado_override()
                ece  = con.meta.ece()
                n    = con.meta.n_trades()
                brier= con.meta.brier()
                cal_estado = con.meta.estado_calibracion()
                clueless, wr_rec = con.meta.zona_clueless(12)
                zona_txt = (f"ZONA CLUELESS (WR reciente={wr_rec:.0%} — mercado caótico)"
                            if clueless else f"Zona normal (WR reciente={wr_rec:.0%})")
                return (f"Conciencia: {modo} | "
                        f"Calibración ECE={ece:.3f} [{cal_estado}] | "
                        f"Brier={brier:.3f} | "
                        f"{n} observaciones | {zona_txt}.")
            return "La conciencia no está inicializada aún, señor."

        if tiene("muestra las flechas", "activa flechas", "activa señal visual",
                 "activa senal visual", "quiero ver las flechas", "señal en pantalla",
                 "senal en pantalla", "muestra la señal", "muestra la senal"):
            sv = getattr(a, "senal_visual", None)
            if sv is None:
                from . import senal_visual as _sv_mod
                sv = _sv_mod.obtener(root=getattr(a.interfaz, "root", None), app=a)
            if sv:
                return ("Señales visuales activadas, señor. "
                        "Verá flechas en pantalla cuando haya señal con 4+ votos "
                        "o confianza mayor al 65%.")
            return "Las señales visuales no están disponibles en este momento, señor."

        if tiene("oculta las flechas", "oculta la señal", "quita las flechas",
                 "desactiva flechas", "sin flechas", "oculta senal visual"):
            try:
                from . import senal_visual as _sv_mod
                sv = _sv_mod.obtener()
                if sv:
                    sv.ocultar()
                return "Señales visuales ocultadas, señor."
            except Exception:
                return "No hay señal visual activa, señor."

        if tiene("muestra el letrero", "mostrar letrero", "letrero de señal",
                 "letrero prediccion", "activa letrero", "letrero razonamiento",
                 "show signal banner", "prediction banner"):
            letrero = getattr(a, "letrero", None)
            if letrero:
                letrero.toggle()
                return ("Letrero de predicción activado, señor. "
                        "Mostrará la dirección, confianza y qué métodos votaron "
                        "en cada señal.")
            return "El letrero de predicción no está disponible en este momento, señor."

        if tiene("oculta el letrero", "ocultar letrero", "esconde letrero",
                 "hide banner", "quita el letrero"):
            letrero = getattr(a, "letrero", None)
            if letrero:
                letrero.ocultar()
                return "Letrero ocultado, señor."
            return "No hay letrero activo, señor."

        if tiene("zona clueless", "mercado caotico", "mercado caótico",
                 "estás adivinando", "estas adivinando", "confianza en tus predicciones",
                 "cuánto confías", "cuanto confias", "te estás equivocando mucho",
                 "te estas equivocando mucho"):
            con = getattr(a, "conciencia", None)
            if con is None:
                return "El sistema de conciencia no está disponible, señor."
            clueless, wr_rec = con.meta.zona_clueless(12)
            ece  = con.meta.ece()
            n    = con.meta.n_trades()
            if clueless:
                return (f"Señor, estoy en zona de bajo rendimiento. "
                        f"Mi WR de las últimas 12 predicciones es {wr_rec:.0%}, "
                        f"por debajo del 45%. El mercado está en régimen caótico. "
                        f"ECE={ece:.3f} ({con.meta.estado_calibracion()}). "
                        f"Recomiendo reducir el monto o pausar hasta que el mercado "
                        f"recupere estructura.")
            return (f"Mis predicciones están bien calibradas, señor. "
                    f"WR reciente={wr_rec:.0%} (últimas 12). "
                    f"ECE={ece:.3f} [{con.meta.estado_calibracion()}]. "
                    f"{n} observaciones en memoria. Condiciones normales.")

        if tiene("régimen de mercado", "regimen de mercado", "tipo de mercado",
                 "cómo está el mercado", "como esta el mercado",
                 "está en tendencia", "esta en tendencia", "hay tendencia",
                 "mercado trending", "mercado ranging", "mercado en rango"):
            try:
                reg_obj = getattr(a.agente, "_ultimo_regimen_obj", None)
                if reg_obj is None:
                    reg_txt = str(getattr(a.agente, "_ultimo_regimen", "desconocido"))
                    return (f"El régimen detectado es '{reg_txt}', señor. "
                            "Inicia trading para obtener el análisis completo.")
                factor = reg_obj.factor_confianza
                favorable = "favorable para operar" if reg_obj.es_favorable else "desfavorable — recomiendo precaución"
                return (f"Régimen actual: {reg_obj.tipo}. "
                        f"Confianza: {reg_obj.confianza:.0%}. "
                        f"Hurst={reg_obj.hurst:.3f} ADX={reg_obj.adx:.1f}. "
                        f"Factor señal: ×{factor:.2f}. "
                        f"Mercado {favorable}, señor. "
                        f"{reg_obj.descripcion}.")
            except Exception as e:
                return f"Error al consultar régimen: {e}"

        # --- Diagnóstico y reporte de salud del sistema ------------------
        if tiene("qué errores hay", "reporte de salud", "estado del sistema",
                 "cómo estás de salud", "hay errores", "diagnóstico",
                 "crash log", "registro de fallos", "errores internos",
                 "estado de los hilos", "cómo están los hilos"):
            partes = []
            # Errores consecutivos del loop
            err_c = getattr(getattr(a, "agente", None), "_errores_consec", 0)
            if err_c > 0:
                partes.append(f"Loop principal: {err_c} errores consecutivos activos.")
            else:
                partes.append("Loop principal: sin errores activos.")
            # Estado watchdog
            wdg = getattr(a, "watchdog", None)
            if wdg:
                partes.append(wdg.resumen())
                # Último crash
                try:
                    from .watchdog import leer_crash_log
                    crashes = leer_crash_log(1)
                    if crashes:
                        c = crashes[-1]
                        partes.append(f"Último crash: {c['ts']} en '{c['hilo']}' — {c['tipo']}: {c['error'][:80]}")
                    else:
                        partes.append("Sin crashes registrados.")
                except Exception:
                    pass
            # Trading on/off + estado del gráfico
            partes.append(f"Trading: {'activo' if a.trading_on else 'DETENIDO'}.")
            cfg = a.mem.get("config", {})
            if cfg.get("region_grafico") and cfg.get("boton_verde"):
                partes.append("Gráfico: visible y configurado.")
            elif cfg.get("region_grafico"):
                partes.append("Gráfico: visible pero sin botones.")
            else:
                partes.append("Gráfico: NO DETECTADO — abra el broker.")
            return " | ".join(partes)

        # --- Meta Diaria -----------------------------------------------
        if tiene("meta", "objetivo del día", "objetivo diario", "cuánto quiero ganar",
                 "cuanto quiero ganar", "ganancia del día", "ganancia diaria",
                 "meta diaria", "stop loss del día", "stop del dia"):
            meta = getattr(a, "meta_diaria", None)
            if not meta:
                from . import meta_diaria as _meta_mod
                meta = _meta_mod.obtener(a)
                a.meta_diaria = meta
            if tiene("desactiva", "cancela", "quita", "stop"):
                if meta.activa:
                    meta.desactivar()
                    return "Meta diaria desactivada, señor. Operaré sin límite de ganancia."
                return "No había meta diaria activa, señor."
            if tiene("estado", "cómo va", "como va", "progreso", "cuánto llevo"):
                s = meta.stats()
                if not s["activa"]:
                    return "No hay meta diaria configurada, señor. Dígame un monto para activarla."
                sgn = "+" if s["pnl"] >= 0 else ""
                return (f"Meta diaria: {sgn}${s['pnl']:.2f} de ${s['meta_gan']:.0f}. "
                        f"{s['wins']}W {s['losses']}L. "
                        f"{'Completada.' if s['completada'] else 'En curso.'}")
            # Buscar número en el texto
            numeros = re.findall(r'\d+(?:[.,]\d+)?', t)
            if len(numeros) >= 2:
                mg = float(numeros[0].replace(",", "."))
                sp = float(numeros[1].replace(",", "."))
                meta.configurar(mg, sp)
                return (f"Meta diaria configurada: objetivo +${mg:.0f}, "
                        f"stop -${sp:.0f}. Comenzando operativa, señor.")
            if len(numeros) == 1:
                mg = float(numeros[0].replace(",", "."))
                sp = mg * 0.5
                meta.configurar(mg, sp)
                return (f"Meta diaria: +${mg:.0f} con stop automático en -${sp:.0f}. "
                        f"Listo, señor.")
            # Sin número: abrir panel
            try:
                a.interfaz.root.after(0, a.interfaz.abrir_meta)
            except Exception:
                pass
            return ("Abriendo el panel de meta diaria. Allí puede configurar "
                    "su objetivo y el stop de pérdidas, señor.")

        if tiene("recomienda meta", "recomendar meta", "qué meta poner", "que meta poner",
                 "meta recomendada", "cuál es la meta ideal", "cual es la meta ideal",
                 "meta sugerida", "meta basada en historial"):
            try:
                meta = getattr(a, "meta_diaria", None)
                if meta is None:
                    return "Módulo de meta diaria no disponible, señor."
                rec = meta.recomendar_meta()
                if rec["sesiones"] < 5:
                    return ("Necesito al menos 5 sesiones con meta configurada para hacer "
                            "una recomendación estadística sólida, señor. "
                            f"Solo tengo {rec['sesiones']}.")
                return (f"{rec['texto']} "
                        f"Win rate histórico: {rec['wr_historico']:.0f}%. "
                        f"Recomiendo: meta +${rec['meta_sugerida']:.0f}, "
                        f"stop -${rec['stop_sugerido']:.0f}, señor.")
            except Exception as e:
                return f"Error al calcular meta recomendada: {e}"

        # --- Estado completo de autonomía --------------------------------
        if tiene("estado de autonomía", "estado autonomia", "cómo estás operando",
                 "como estas operando", "resumen autonomo", "resumen autónomo",
                 "qué modos tienes activos", "que modos tienes activos"):
            lineas = []
            practica    = getattr(a, "modo_practica",    None)
            profesional = getattr(a, "modo_profesional", None)
            meta        = getattr(a, "meta_diaria",      None)
            lineas.append(f"Trading: {'activo' if a.trading_on else 'detenido'}.")
            if practica and practica.activo:
                s = practica.stats()
                lineas.append(f"Práctica DEMO activa: {s['trades']} trades, WR {s['wr']:.0f}%, "
                              f"umbral {practica._votos_min}v.")
            if profesional and profesional.activo:
                s = profesional.stats()
                lineas.append(f"Modo profesional activo: {s['trades']} trades, WR {s['wr']:.0f}%.")
            if meta and meta.activa:
                s = meta.stats()
                sgn = "+" if s["pnl"] >= 0 else ""
                lineas.append(f"Meta diaria: {sgn}${s['pnl']:.2f} / ${s['meta_gan']:.0f}.")
            if not lineas[1:]:
                lineas.append("No hay modo autónomo activo. Diga 'activa práctica' para comenzar.")
            return " ".join(lineas)

        # --- Conversación ----------------------------------------------
        if tiene("hola", "buenos días", "buenas tardes", "buenas noches", "qué tal", "que tal"):
            return random.choice([
                "Hola, señor. Todos los sistemas operativos. ¿En qué puedo asistirle?",
                "A sus órdenes. El panel está activo y la memoria de patrones cargada.",
                "Buenas. ¿Analizamos el mercado o prefiere revisar las estadísticas?",
            ])
        if tiene("quién eres", "quien eres", "cómo te llamas", "como te llamas",
                 "qué eres", "que eres"):
            return ("Soy Litch, su asistente personal de inteligencia artificial. Hablo "
                    "español e inglés, observo su pantalla, aprendo patrones del mercado "
                    "en demo, busco información en línea y cuido de usted. Cuanto más "
                    "trabajamos juntos, más aprendo.")
        if tiene("gracias"):
            return random.choice(["Para servirle, señor.", "Un placer, como siempre.",
                                  "No hay de qué. Sigo atento."])
        if tiene("ayuda", "qué puedes hacer", "que puedes hacer", "funciones", "comandos"):
            return (
                "INTERACTIVE BROKERS — lo que más le sirve ahora:\n"
                "  · «toca para aprender» — hago clic por la pantalla, mido "
                "qué cambia y lo memorizo\n"
                "  · «¿qué has comprobado?» — qué herramientas domino ya y "
                "cuáles no\n"
                "  · «¿qué puedes tocar?» — mi nivel de acceso y por qué\n"
                "  · «¿qué estás viendo?» — cuánta pantalla alcanzo\n"
                "  · «revisión de apertura» — las comprobaciones antes de "
                "operar\n"
                "  · «prepara una operación» — análisis, tamaño y bracket\n"
                "  · «verifica los datos» — ¿el precio es de ahora o de hace "
                "15 minutos?\n"
                "  · «conecta con IBKR» · «activa el modo Wall Street»\n"
                "\n"
                "RESTO: buscar en internet, investigar a fondo, noticias, "
                "precio de activos, leer y enviar correo, recordatorios, "
                "clima, lotería, calibrar pantalla, inglés.\n"
                "\n"
                "Para lo del bróker no hace falta la frase exacta: dígamelo "
                "como le salga —«empieza a hacer clic», «prueba las "
                "funciones», «explora»— y le entiendo.")
        if tiene("riesgo", "dinero real", "cuenta real", "invertir de verdad"):
            return ("Mi consejo profesional, señor: las opciones binarias tienen ventaja "
                    "matemática para la casa. Trabajo solo en demo para aprender sin "
                    "riesgo. No le recomendaré operar dinero real, y nunca lo haré por usted.")

        # --- Manual de funciones de los brokers (integrado en su cerebro) ------
        if tiene("cómo funciona", "como funciona", "cómo se usa", "como se usa",
                 "cómo uso", "como uso", "para qué sirve", "para que sirve",
                 "qué es el", "que es el", "qué es la", "que es la",
                 "bracket", "trailing stop", "stop limit", "orden limit",
                 "orden market", "transmit", "payout", "vencimiento",
                 "linea de compra", "línea de compra", "puerto paper",
                 "regla pdt", "time in force", "fractional", "fracciones",
                 "botón sube", "boton sube", "botón baja", "boton baja",
                 "cómo opero", "como opero", "cómo funciona iq", "como funciona iq",
                 "cómo funciona ibkr", "como funciona ibkr",
                 "manual de iq", "manual de ibkr", "funciones del broker"):
            try:
                from . import conocimiento_brokers as _cb
                if tiene("qué sabes usar", "que sabes usar", "qué funciones",
                         "que funciones", "capacidades del broker"):
                    return _cb.resumen_capacidades("es")
                resp = _cb.buscar(t, "es")
                if resp:
                    return resp
            except Exception:
                pass

        # --- Conocimiento profesional de trading --------------------------------
        if tiene("vela", "candlestick", "doji", "martillo", "hammer", "engulfing",
                 "estrella de la mañana", "estrella de la tarde", "marubozu",
                 "harami", "patrón de vela", "patron de vela", "nube oscura",
                 "piercing", "tres soldados", "tres cuervos", "spinning top",
                 "qué significa esta vela", "que significa esta vela",
                 "explica la vela", "explica el patrón", "explica el patron"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("scalping", "scalp", "estrategia de entrada", "entrada rápida",
                 "entrada rapida", "ema cruce", "cruce de medias", "bollinger bands",
                 "vwap scalping", "apertura new york", "apertura de ny",
                 "estrategia de scalping", "como hacer scalping"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("bull trap", "bear trap", "smart money", "fomo", "fud",
                 "short squeeze", "capitulacion", "capitulación", "rally",
                 "correccion", "corrección", "liquidez del mercado", "stop hunt",
                 "dinero inteligente", "trampa alcista", "trampa bajista",
                 "qué es un toro", "que es un toro", "qué es un oso", "que es un oso",
                 "mercado alcista", "mercado bajista", "bull market", "bear market"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("sesión de trading", "sesion de trading", "sesión del mercado",
                 "sesion del mercado", "qué sesión", "que sesion",
                 "cuándo operar", "cuando operar", "horario de trading",
                 "apertura del mercado", "cierre del mercado", "solapamiento",
                 "sesion de tokio", "sesion de londres", "sesion de nueva york",
                 "sesion actual", "qué sesión tenemos", "que sesion tenemos"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp
            return conocimiento_trading.resumen_sesion_actual()

        if tiene("trailing stop", "stop por estructura", "stop atr", "stop fijo",
                 "breakeven", "break even", "metodo de stop", "método de stop",
                 "cómo poner el stop", "como poner el stop",
                 "métodos de stop", "metodos de stop", "stop seguidor"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("price action", "acción de precio", "accion de precio",
                 "order block", "fair value gap", "imbalance", "fvg",
                 "bos", "choch", "cambio de carácter", "cambio de caracter",
                 "zona de oferta", "zona de demanda", "soporte y resistencia",
                 "fibonacci", "confluencia", "estructura del mercado",
                 "ruptura de estructura", "break of structure",
                 "captura de liquidez", "liquidity grab"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("gestión de riesgo", "gestion de riesgo", "manejo de riesgo",
                 "tamaño de posicion", "tamanio de posicion", "revenge trading",
                 "pérdida diaria", "perdida diaria", "limite diario",
                 "regla del 1", "regla del 2", "ratio riesgo beneficio",
                 "relacion riesgo", "win rate necesario", "winrate"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("tradingview", "trading view", "screener", "pine script",
                 "alertas de trading", "indicadores en tradingview",
                 "como usar tradingview", "cómo usar tradingview"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("explica el vwap", "explica el rsi", "explica el macd",
                 "explica el atr", "explica bollinger", "explica ichimoku",
                 "qué es el vwap", "que es el vwap", "qué es el rsi",
                 "que es el rsi", "qué es el macd", "que es el macd",
                 "qué es el atr", "que es el atr", "qué indicador usar",
                 "que indicador usar", "cómo usar el indicador",
                 "como usar el indicador"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("plan de trading", "plan diario", "plan del día", "plan del dia",
                 "cómo preparar el día", "como preparar el dia",
                 "estrategia del día", "estrategia del dia",
                 "apertura de nueva york", "cierre de nueva york",
                 "power hour", "swing trading", "almuerzo ny",
                 "cuando NO operar", "cuando no operar"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("smc", "ict", "smart money", "inner circle", "ciclo amd",
                 "market maker model", "ote", "optimal trade entry",
                 "premium y descuento", "breaker block", "displacement",
                 "inducement", "killzone", "kill zone", "london sweep",
                 "dinero institucional", "qué es el smc", "que es el smc"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("latino wall street", "latinowallstreet", "lws",
                 "gabriela berrospi", "alan burak", "cursos de trading",
                 "academia de trading", "gallo mañanero"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        if tiene("broker express", "exness", "xm broker", "etoro",
                 "interactive brokers", "pepperstone",
                 "qué broker usar", "que broker usar",
                 "mejor broker", "broker recomendado"):
            resp = conocimiento_trading.buscar(t, "es")
            if resp:
                return resp

        # ── Interactive Brokers ─────────────────────────────────────────────
        if tiene("interactive brokers", "ibkr", "ib broker",
                 "tws", "trader workstation"):
            bc = getattr(a, "conocimiento", None)
            if bc:
                if tiene("qué es", "que es", "cuéntame", "explicame",
                         "explica", "cuenta"):
                    return bc.leer("brokers", "ibkr_que_es") or (
                        "Interactive Brokers es el broker más completo del mundo. "
                        "Acceso a 150+ mercados, comisiones ultra-bajas y API profesional.")
                if tiene("ventaja", "bueno", "mejor"):
                    return bc.leer("brokers", "ibkr_ventajas") or "IBKR tiene las comisiones más bajas del mercado."
                if tiene("cómo abrir", "como abrir", "cuenta", "registro"):
                    return bc.leer("brokers", "ibkr_como_abrir_cuenta") or "Ve a ibkr.com para abrir tu cuenta."
                if tiene("api", "python", "código", "codigo", "programar"):
                    return bc.leer("brokers", "ibkr_api_python") or "Usa ib_insync: pip install ib_insync"
                if tiene("orden", "tipos de orden", "market", "limit", "stop"):
                    return bc.leer("brokers", "ibkr_ordenes") or "IBKR soporta MARKET, LIMIT, STOP, STOP_LIMIT y TRAILING."
                if tiene("horario", "cuándo", "cuando"):
                    return bc.leer("brokers", "ibkr_horarios") or "Acciones US: 09:30-16:00 ET. Forex: 24/5."
                if tiene("riesgo", "gestión", "gestion", "stop loss", "kelly"):
                    return bc.leer("brokers", "ibkr_gestion_riesgo") or "Nunca arriesgar más del 1% por trade."
                if tiene("conectar", "conecta", "papel", "paper", "demo", "practica"):
                    ibkr = getattr(a, "broker_ibkr", None)
                    if ibkr:
                        ok = ibkr.conectar(modo="paper")
                        return ("Conectado a IBKR en modo PAPEL. Puedes practicar sin riesgo real." if ok
                                else "No pude conectar. Asegúrate de que TWS esté abierto con API habilitada.")
                # Respuesta general sobre IBKR
                return (bc.leer("brokers", "ibkr_que_es") or
                        "Interactive Brokers es mi broker objetivo para cuando esté completamente entrenado.")

        # ── Charles Schwab ──────────────────────────────────────────────────
        if tiene("schwab", "charles schwab", "thinkorswim", "tos"):
            bc = getattr(a, "conocimiento", None)
            if bc:
                if tiene("qué es", "que es", "cuéntame", "explicame", "explica"):
                    return bc.leer("brokers", "schwab_que_es") or (
                        "Charles Schwab es el mayor broker retail de EEUU, con $9 trillones en activos.")
                if tiene("ventaja", "bueno", "mejor"):
                    return bc.leer("brokers", "schwab_ventajas") or "Sin comisiones en acciones y ETFs US."
                if tiene("cómo abrir", "como abrir", "cuenta", "registro"):
                    return bc.leer("brokers", "schwab_como_abrir_cuenta") or "Ve a schwab.com para abrir tu cuenta."
                if tiene("api", "python", "código", "codigo", "programar"):
                    return bc.leer("brokers", "schwab_api") or "Schwab usa OAuth2. pip install requests"
                if tiene("thinkorswim", "tos", "plataforma"):
                    return bc.leer("brokers", "schwab_thinkorswim") or "Thinkorswim es la mejor plataforma de análisis del mercado."
                if tiene("orden", "tipos", "market", "limit", "stop"):
                    return bc.leer("brokers", "schwab_ordenes") or "Schwab soporta MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING."
                if tiene("instrumento", "etf", "accion", "opcion", "bono"):
                    return bc.leer("brokers", "schwab_instrumentos") or "Schwab ofrece acciones, ETFs, opciones, futuros y bonos."
                if tiene("riesgo", "gestión", "gestion"):
                    return bc.leer("brokers", "schwab_gestion_riesgo") or "Nunca arriesgar más del 1% por trade."
                return (bc.leer("brokers", "schwab_que_es") or
                        "Charles Schwab es uno de los brokers más seguros y profesionales del mundo.")

        # ── Base de conocimiento: búsqueda general ──────────────────────────
        if tiene("qué sabes", "que sabes", "sabes sobre", "cuéntame sobre",
                 "base de conocimiento", "lo que aprendiste", "tus conocimientos"):
            bc = getattr(a, "conocimiento", None)
            if bc:
                resultado = bc.responder(t)
                if resultado:
                    return resultado
                return ("Puedo decirte lo que sé sobre brokers, trading, mercados, "
                        "acciones, riesgo y estrategias. Pregúntame algo específico.")

        # ── Cuándo pasar a acciones reales ──────────────────────────────────
        if tiene("cuándo pasar", "cuando pasar", "acciones reales",
                 "pasar a schwab", "pasar a ibkr", "bolsa real",
                 "ya estoy listo", "estoy listo para"):
            bc = getattr(a, "conocimiento", None)
            if bc:
                return bc.leer("trading", "cuando_pasar_acciones") or (
                    "Para pasar a acciones reales necesitas al menos 3 meses con WR > 60% "
                    "y práctica en paper trading. Sigue entrenando conmigo en IQ Option primero.")

        # ── Watchdog / estado del sistema ───────────────────────────────────
        if tiene("watchdog", "estado hilos", "estado sistema",
                 "crashes", "errores del sistema", "crash log"):
            wdg = getattr(a, "watchdog", None)
            if wdg:
                from .watchdog import leer_crash_log
                crashes = leer_crash_log(5)
                resumen = wdg.resumen()
                if crashes:
                    ultimo = crashes[-1]
                    return (f"{resumen}\n"
                            f"Último crash: {ultimo['ts']} en '{ultimo['hilo']}': "
                            f"{ultimo['error'][:100]}")
                return f"{resumen}\nSin crashes registrados. Todo funciona correctamente."

        if tiene("horario colombia", "horario mexico", "horario argentina",
                 "killzone colombia", "killzone mexico", "killzone argentina",
                 "cuándo operar en colombia", "cuando operar en colombia"):
            resp = conocimiento_trading.buscar("killzone latam colombia", "es")
            if resp:
                return resp

        # --- Broker universal ----------------------------------------
        if tiene("configura el broker", "configurar broker", "aplica la mejor config",
                 "aplica configuracion optima", "programa el broker",
                 "ponme la mejor configuracion", "ajusta el broker"):
            cfg = a.broker.mejor_config()
            if cfg["trades"] < 5:
                return ("No tengo suficientes datos todavia, senor. "
                        "Opera al menos 5 trades para que empiece a aprender.")
            res = a.broker.aplicar_config_completa()
            ok  = sum(res.values())
            if ok == 0:
                a.abrir_broker()
                return ("No tengo los elementos de la interfaz calibrados, senor. "
                        "Abre el panel de broker y calibralos primero.")
            return (f"Configuracion aplicada: {cfg['asset']} a {cfg['duracion']}s "
                    f"con ${cfg['monto']:.0f}. Tasa de exito: {cfg['win_rate']:.0f}%, senor.")
        # ── IQ Option API — conexión directa ─────────────────────────────────
        import re as _re_iq
        _m_cuenta = _re_iq.search(
            r"(?:mi cuenta|cuenta iq|iq option|login|correo|email).*?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})[:\s]+(\S+)",
            t, _re_iq.IGNORECASE)
        if _m_cuenta:
            _email_iq = _m_cuenta.group(1)
            _pass_iq  = _m_cuenta.group(2)
            try:
                from .brokers.iq_option_api import IQOptionBroker as _IQB
                _iqb = _IQB()
                _iqb.guardar_credenciales(_email_iq, _pass_iq)
                ok_iq, msg_iq = _iqb.conectar()
                if ok_iq:
                    # Guardar instancia en el app para uso posterior
                    a._iq_api_broker = _iqb
                    _saldo_demo = _iqb.saldo("demo")
                    _saldo_real = _iqb.saldo("real")
                    return (f"Perfecto señor, conectado a IQ Option vía API directa. "
                            f"Saldo demo: ${_saldo_demo:,.2f}. Saldo real: ${_saldo_real:,.2f}. "
                            f"Ahora puedo leer velas en tiempo real y operar sin ver la pantalla.")
                else:
                    return f"No pude conectar a IQ Option: {msg_iq}"
            except Exception as _e_iq:
                return f"Error conectando a IQ Option API: {_e_iq}"

        if tiene("conectar iq", "conectar iq option", "conecta iq", "api iq option",
                 "usa api iq", "conectar api"):
            _iqb_ex = getattr(a, "_iq_api_broker", None)
            if _iqb_ex and _iqb_ex.conectado:
                return f"Ya estoy conectado a IQ Option vía API, señor. {_iqb_ex.resumen()}"
            from .brokers.iq_option_api import IQOptionBroker as _IQB2
            _iqb2 = _IQB2()
            ok2, msg2 = _iqb2.conectar()
            if ok2:
                a._iq_api_broker = _iqb2
                return f"Conectado a IQ Option API: {msg2}"
            return (f"Para conectar dime: 'mi cuenta IQ Option es TuEmail:TuContraseña'. "
                    f"Razón: {msg2}")

        if tiene("explorar mercado", "escanear activos", "explorar activos",
                 "qué activos hay", "que activos hay", "mercado ahora",
                 "oportunidades de mercado"):
            try:
                from .asset_scanner import obtener as _get_sc
                _sc = _get_sc(app=a)
                _broker_iq = getattr(a, "_iq_api_broker", None)
                return _sc.resumen_texto(5)
            except Exception as _e_sc:
                return f"Error escaneando activos: {_e_sc}"

        if tiene("noticias", "noticias económicas", "noticias del mercado",
                 "qué hay en el mercado", "que hay en el mercado",
                 "noticias financieras", "contexto macro"):
            try:
                from .knowledge_feeder import obtener as _get_kf
                _kf = _get_kf(app=a)
                _nots = _kf.noticias_recientes(4)
                if not _nots:
                    _kf._actualizar_noticias()
                    _nots = _kf.noticias_recientes(4)
                if _nots:
                    _tasas = _kf.tasas_actuales()
                    _eur = _tasas.get("EUR/USD", "?")
                    resp = f"EUR/USD actual: {_eur}. Noticias: "
                    resp += ". ".join(n.get("titulo", "")[:60] for n in _nots[:3])
                    return resp
                return "Sin noticias disponibles. Actualizando en background..."
            except Exception as _e_kf:
                return f"Error leyendo noticias: {_e_kf}"

        if tiene("actualizar conocimiento", "aprende de internet", "busca en internet",
                 "actualiza información", "aprende ahora", "conocimiento web"):
            try:
                from .knowledge_feeder import obtener as _get_kf2
                _kf2 = _get_kf2(app=a)
                import threading as _thr
                _thr.Thread(target=_kf2.actualizar_ahora, daemon=True,
                            name="KFUpdate").start()
                return ("Iniciando actualización de conocimiento desde internet, señor. "
                        "Descargaré conceptos de análisis técnico, noticias y tasas de cambio. "
                        "Estará listo en unos minutos.")
            except Exception as _e_kf2:
                return f"Error actualizando: {_e_kf2}"

        if tiene("conectar interactive", "conectar ibkr", "interactive brokers",
                 "conectar schwab", "charles schwab"):
            _nombre_b = ("ibkr" if "interactive" in t or "ibkr" in t else "schwab")
            try:
                from .broker_universal import obtener as _get_bu
                _bu = _get_bu(app=a)
                ok_b, msg_b = _bu.conectar(_nombre_b)
                if ok_b:
                    return (f"Conectado a {'Interactive Brokers' if _nombre_b == 'ibkr' else 'Charles Schwab'}, señor. "
                            + msg_b)
                return msg_b
            except Exception as _e_b:
                return f"Error: {_e_b}"

        if tiene("mejor activo", "que activo", "cual es el mejor", "mejor par",
                 "que par funciona", "estadisticas del broker", "como voy por activo"):
            try:
                from .asset_scanner import obtener as _get_sc2
                return _get_sc2(app=a).resumen_texto(3)
            except Exception:
                pass
            return a.broker.resumen_texto()
        if tiene("abre el broker", "panel del broker", "muestra el broker",
                 "estadisticas por activo", "rendimiento por activo"):
            a.abrir_broker()
            return "Abriendo el panel de broker, senor."
        if tiene("cambia a iq option", "usar iq option", "broker iq"):
            a.broker.cambiar_broker("iq_option")
            return "Broker cambiado a IQ Option, senor."
        if tiene("cambia a quotex", "usar quotex", "broker quotex"):
            a.broker.cambiar_broker("quotex")
            return "Broker cambiado a Quotex, senor."
        if tiene("cambia a deriv", "usar deriv", "broker deriv"):
            a.broker.cambiar_broker("deriv")
            return "Broker cambiado a Deriv, senor."
        if tiene("cambia a binomo", "usar binomo", "broker binomo"):
            a.broker.cambiar_broker("binomo")
            return "Broker cambiado a Binomo, senor."
        if tiene("recalibra el broker", "calibra el broker", "detecta el broker",
                 "escanea el broker", "encontrar los campos"):
            resultado = a.broker.calibrar_ui_auto()
            if resultado:
                return (f"Detecto: {', '.join(resultado.keys())}. "
                        "Puedo configurar el broker automaticamente ahora, senor.")
            a.abrir_broker()
            return ("No pude detectar los elementos automaticamente, senor. "
                    "Abre el panel de broker y calibralos manualmente.")
        if tiene("consulta a la ia sobre el broker", "pregunta a claude sobre el broker",
                 "pide consejo sobre el broker", "mejor estrategia broker",
                 "que broker usar", "que activo me recomiendas"):
            consejo = a.broker.consultar_ia()
            return consejo
        if tiene("que aprendiste del broker", "lecciones del broker", "que te enseno la ia",
                 "leccion de trading", "que sabes del mercado", "ensenanzas de la ia"):
            return a.lecciones_broker_texto()
        if tiene("aprende ahora del broker", "consulta la ia ahora", "fuerza aprendizaje",
                 "aprende del mercado ya", "actualiza tu conocimiento"):
            a.broker.consejero._trades_desde_ia = 99  # forzar ciclo IA en próximo tick
            return a.txt(
                "Forzando una consulta de aprendizaje a la IA en el proximo ciclo, senor.",
                "Forcing an AI learning query on the next cycle, sir.")

        # --- Ollama toggle -------------------------------------------
        if tiene("activa ollama", "enciende ollama", "usa ollama",
                 "conecta ollama", "ollama local"):
            a.set_usar_ollama(True, hablar=True)
            return ""
        if tiene("desactiva ollama", "apaga ollama", "sin ollama",
                 "desconecta ollama", "quita ollama"):
            a.set_usar_ollama(False, hablar=True)
            return ""

        # --- Claude toggle -------------------------------------------
        if tiene("conecta claude", "conéctate a claude", "activa claude",
                 "usa claude", "enciende claude", "conectar claude"):
            a.set_usar_claude(True, hablar=True)
            return ""
        if tiene("desconecta claude", "desconéctate de claude", "desactiva claude",
                 "apaga claude", "sin claude", "desconectar claude"):
            a.set_usar_claude(False, hablar=True)
            return ""
        if tiene("estado claude", "claude activo", "claude conectado", "claude disponible"):
            from . import mente_claude as _mc
            on  = getattr(a, "usar_claude", False)
            key = _mc.disponible()
            return (f"Claude está {'ACTIVO' if on else 'INACTIVO'}. "
                    f"API key: {'configurada' if key else 'no encontrada'}.")

        # --- Respuesta por defecto --------------------------------------
        self._fue_default = True
        return random.choice([
            "Entendido, señor, aunque no estoy seguro de haberle comprendido del todo. Diga «ayuda» para ver mis funciones.",
            "Interesante. ¿Desea que busque información sobre eso en línea? Diga «Litch, busca» seguido del tema.",
            "No tengo una rutina para eso todavía, pero lo he anotado en mi memoria, señor.",
        ])

    # ------------------------------------------------------------------
    def _responder_en(self, t):
        a = self.app

        def tiene(*palabras):
            return any(p in t for p in palabras)

        m = re.search(r"remind me (?:to )?(.+?) in (\d+) (seconds?|minutes?|hours?)", t)
        if m:
            return a.recordatorios.crear(m.group(1), int(m.group(2)),
                                         m.group(3), "en")

        m = re.search(r"weather (?:in |at |for )(.+)", t)
        if m:
            reporte = conocimiento.clima(m.group(1).strip(" ?"), "en")
            return reporte or "I couldn't check the weather right now, sir."

        # --- Market news -------------------------------------------------
        if tiene("market news", "financial news", "latest news"):
            titulos = agente_web.noticias_rss(6)
            if titulos:
                return "Latest market news, sir: " + " // ".join(titulos[:5])
            return "Could not fetch news right now, sir. Check your connection."

        # --- Price / market data -----------------------------------------
        m_sym = re.search(r"(?:price|quote|data)(?: of| for)?\s+([A-Z]{1,5})", t.upper())
        if m_sym and tiene("price", "quote", "data"):
            simbolo = m_sym.group(1)
            dato = agente_web.datos_mercado(simbolo)
            if dato:
                return (f"{dato['simbolo']} is at {dato['precio']} {dato['moneda']} "
                        f"on {dato['mercado']}, sir.")
            return f"Could not retrieve price for {m_sym.group(1)}, sir."

        # --- Email -------------------------------------------------------
        if tiene("read my email", "check my email", "inbox", "my emails"):
            return correo.resumen_inbox(5, "en")

        m_send = re.search(
            r"send (?:an? )?email to ([^\s,]+).+?(?:about|subject|saying) (.+)", t)
        if m_send or (tiene("send", "email", "mail") and tiene("to")):
            if m_send:
                dest   = m_send.group(1).strip()
                asunto = m_send.group(2).strip()[:60]
                ok, msg = correo.enviar(dest, asunto, asunto)
                return msg
            return ("Say: «send an email to [address] about [subject]», sir. "
                    "If you have no accounts set up, open the «📧 Email & AI» panel.")

        # --- Permissions -------------------------------------------------
        if tiene("permissions", "my permissions", "what permissions"):
            return perms_mod.resumen()

        # --- Deep research -----------------------------------------------
        m_res = re.search(r"(?:research|investigate)(?: about| on)? (.+)", t)
        if m_res:
            tema = m_res.group(1).strip(" ?")
            self.app.log(f"Researching: {tema}…")
            return agente_web.investigar(tema, "en")

        # --- Quick web search -------------------------------------------
        m = (re.search(r"(?:search|look up|find)(?: for| about)? (.+)", t)
             or re.search(r"(?:what|who) (?:is|are|was) (.+)", t))
        if m:
            tema = m.group(1).strip(" ?")
            return agente_web.respuesta_rapida(tema, "en") or conocimiento.buscar(tema, "en")

        if tiene("pause", "sleep", "stand down", "go to sleep"):
            a.set_activo(False)
            return "Understood, sir. Entering standby mode. Say «wake up» when you need me."
        if tiene("wake up", "resume", "power on"):
            a.set_activo(True)
            return "Systems back online. At your service."

        if tiene("autonomous", "free will", "master key", "auto-click", "autoclick"):
            if a.modo_autonomo:
                a.set_autoclick(False)
                return ("Autonomous mode off, sir. Press the AUTO button or say "
                        "'activate auto-click' to resume.")
            a.set_autoclick(True)
            return ("Autonomous mode on. I'll operate and self-tune without asking. "
                    "Say 'deactivate auto-click' to stop.")

        if tiene("trading", "market", "analysis"):
            if tiene("start", "activate", "turn on", "begin"):
                a.set_trading(True)
                return ("Market analysis activated. I'll watch every candle on the IQ Option "
                        "demo and memorize the patterns.")
            if tiene("stop", "deactivate", "turn off", "halt"):
                a.set_trading(False)
                return "Market analysis stopped. Everything I learned is saved."
        if tiene("click"):
            if tiene("activate", "turn on", "enable", "authorize"):
                a.set_autoclick(True)
                return "Auto-click activated. I'll operate autonomously. You may revoke it anytime."
            if tiene("deactivate", "turn off", "disable", "revoke"):
                a.set_autoclick(False)
                return "Auto-click disabled. I'll only suggest signals by voice."

        if tiene("advice", "advise", "recommend", "what would you do", "suggestion"):
            if tiene("turn off", "disable", "stop"):
                a.set_consejos(False, hablar=False)
                return "Understood, sir. I'll keep my advice until you ask."
            if tiene("turn on", "enable"):
                a.set_consejos(True, hablar=False)
                return "Advisor on. I'll share recommendations as you work, sir."
            return a.consejero.consejo_inmediato()
        if tiene("backup", "cloud", "save to cloud"):
            if tiene("register", "add", "new account", "configure"):
                a.abrir_nube()
                return ("Opening the cloud panel, sir. Register your emails and the folders "
                        "synced by TeraBox, Drive or Dropbox there.")
            return respaldo.respaldar(a)
        if tiene("second method", "consensus", "what do you think of the market"):
            return estadistica.resumen(a.mem["secuencia"], "en")
        if tiene("forecast", "advanced analysis", "entropy", "benford",
                 "autocorrelation", "ewma", "predictable", "advanced trend"):
            sec = a.mem["secuencia"]
            if len(sec) < 15:
                return ("Not enough candles for advanced forecast yet, sir. "
                        "Activate trading and let me observe at least 15 candles.")
            return pronostico.resumen_texto(sec, "en")
        m = re.search(r"(?:continue|predict|next|sequence|series).*?"
                      r"([\d\.\,\-\s]{5,})", t)
        if m and tiene("sequence", "series", "pattern", "number", "predict", "next"):
            nums = [float(x) for x in re.findall(r"-?\d+\.?\d*", m.group(1))]
            if len(nums) >= 3:
                return matematica.predecir_secuencia(nums, "en")
        if tiene("status", "report", "summary", "how are you doing", "what have you learned"):
            return a.analizador.resumen("en")
        # --- Learned memory weight ---------------------------------------
        if tiene("how much have you learned", "memory size", "memory weight",
                 "learned memory", "memoria ap", "memory folder"):
            peso = memoria.peso_memoria()
            ruta = memoria.ruta_memoria_ap()
            return f"{peso} Folder path: {ruta}"

        # --- Chart control (zoom / center) — English ----------------------
        if tiene("center the chart", "centre the chart", "recenter", "center chart",
                 "fit the chart", "reset the view", "center view"):
            try:
                _gc_v = getattr(a, "gestor_grafico", None)
                if _gc_v is not None:
                    _gc_v.centrar_para_fable()
                    return "Chart centered, sir."
                from . import chart_controls as _cc_v
                cfg_v = a.mem.get("config", {})
                ok_v = _cc_v.centrar(cfg_v.get("region_grafico"), cfg_v)
                return "Chart centered, sir." if ok_v else "Couldn't center the chart. Please check calibration."
            except Exception:
                return "Couldn't center the chart. Please check calibration."

        if tiene("zoom in", "zoom closer", "close up", "magnify", "more detail"):
            try:
                from . import chart_controls as _cc_v
                cfg_v = a.mem.get("config", {})
                ok_v = _cc_v.zoom_in(cfg_v.get("region_grafico"), cfg_v)
                return "Zoomed in, sir." if ok_v else "Couldn't zoom in. Please check calibration."
            except Exception:
                return "Couldn't zoom in. Please check calibration."

        if tiene("zoom out", "zoom back", "wide view", "panoramic", "more candles"):
            try:
                from . import chart_controls as _cc_v
                cfg_v = a.mem.get("config", {})
                ok_v = _cc_v.zoom_out(cfg_v.get("region_grafico"), cfg_v)
                return "Zoomed out, sir." if ok_v else "Couldn't zoom out. Please check calibration."
            except Exception:
                return "Couldn't zoom out. Please check calibration."

        if tiene("optimal zoom", "best zoom", "ideal view", "auto zoom"):
            try:
                from . import chart_controls as _cc_v
                cfg_v = a.mem.get("config", {})
                periodo_v = int(cfg_v.get("periodo_vela", 60))
                ok_v = _cc_v.zoom_optimo(cfg_v.get("region_grafico"), cfg_v, periodo_v)
                return "Optimal view applied, sir." if ok_v else "Couldn't adjust zoom. Please check calibration."
            except Exception:
                return "Couldn't adjust zoom. Please check calibration."

        # --- Broker / chart instructions (English) -----------------------
        if tiene("what broker to open", "which platform to open", "how to start trading",
                 "can't see the chart", "no chart", "chart not visible", "missing chart",
                 "what do i need to open", "open the broker", "need a broker",
                 "why no chart", "what to open"):
            cfg = a.mem.get("config", {})
            tiene_region  = bool(cfg.get("region_grafico"))
            tiene_botones = bool(cfg.get("boton_verde") and cfg.get("boton_rojo"))
            if tiene_region and tiene_botones:
                return ("I can see the chart and have the buttons configured, sir. "
                        "Ready to trade. Say 'activate trading' to begin.")
            if tiene_region and not tiene_botones:
                return ("I can see the chart but I'm missing the buy and sell buttons. "
                        "Say 'Litch, calibrate' and I'll configure them right now.")
            return (
                "To analyze the market and place trades, I need a chart visible on screen. "
                "Open the broker you want to trade with — "
                "I know IQ Option best, but I also work with "
                "Interactive Brokers, Charles Schwab, or any other platform with a visible chart. "
                "Once open, say 'Litch, calibrate' and I'll configure myself automatically. "
                "Which broker would you like to use, sir?"
            )

        if tiene("time"):
            return "It's " + time.strftime("%H:%M") + ", sir."
        if tiene("date", "day is it"):
            return "Today is " + time.strftime("%B %d, %Y") + "."
        if tiene("theorem", "audit", "bias", "is it random", "ball weight", "rigged"):
            hist = a.mem["loteria"].get("historial") or []
            if not hist:
                a.abrir_loteria()
                return ("Open the lottery module and load the draws, sir. Then press "
                        "«Audit theorem» and I'll tell you if there's real bias or pure chance.")
            return laboratorio.informe(hist, "en")
        if tiene("lottery"):
            a.abrir_loteria()
            return ("Opening the lottery module. Load the draws: I have two modes, "
                    "«Frequencies» and «Audit theorem», which uses chi-squared and a "
                    "backtest to test for bias versus pure chance, sir.")
        if tiene("predict number", "suggest number", "lottery number",
                 "advanced analysis", "which number", "best number",
                 "give me number", "combination"):
            hist = a.mem.get("loteria", {}).get("historial") or []
            if not hist:
                a.abrir_loteria()
                return ("I need lottery draw history first, sir. Open the lottery module "
                        "and load the data. Then I'll run 9 statistical methods plus a "
                        "neural network to suggest the top candidates.")
            return a.resumen_loteria_av()
        if tiene("how am i doing", "my stats", "my results", "my performance",
                 "how many wins", "how many losses", "win rate", "profit"):
            perf = getattr(a.agente, "_perf", None)
            if perf and len(perf._trades) >= 5:
                return perf.resumen_texto(idioma="en")
            return a.resumen_trading()

        if tiene("best time to trade", "best trading hour", "optimal time",
                 "when should i trade", "best session", "performance by hour"):
            try:
                perf = getattr(a.agente, "_perf", None)
                if perf is None:
                    return "Performance tracker not available, sir."
                return perf.mejor_momento()
            except Exception as e:
                return f"Error getting performance data: {e}"

        if tiene("profit factor", "expectancy", "sharpe", "calmar",
                 "deep stats", "advanced stats", "full performance report"):
            try:
                perf = getattr(a.agente, "_perf", None)
                if perf is None:
                    return "Performance tracker not available, sir."
                if not perf._trades:
                    return "No trades registered yet, sir."
                r = perf.reporte_completo()
                votos_str = " | ".join(
                    f"{v}v: WR={d['wr']:.0f}%({d['n']})"
                    for v, d in r["wr_por_votos"].items()
                )
                return (
                    f"Advanced performance: WR 10t={r['wr_10']:.0f}% "
                    f"20t={r['wr_20']:.0f}% 50t={r['wr_50']:.0f}%. "
                    f"Profit Factor={r['profit_factor']:.2f}. "
                    f"Expectancy=${r['expectativa']:.3f}/trade. "
                    f"Sharpe={r['sharpe_50']:.2f}. "
                    f"P&L={r['pnl_total']:+.2f}. MaxDD=${r['max_dd']:.2f}. "
                    f"WR by votes: {votos_str}, sir."
                )
            except Exception as e:
                return f"Error: {e}"
        if tiene("why did i lose", "why do i fail", "my failures", "my errors",
                 "what did you learn", "analyze failures", "why are you losing"):
            fdb = a.agente.fdb
            malos = fdb.patrones_problematicos()
            racha = fdb.racha_actual()
            lineas = [fdb.resumen(idioma="en")]
            if malos:
                lineas.append("Problematic patterns: " +
                              ", ".join(f"'{p}' ({int(f*100)}%)" for p, f in malos[:3]) + ".")
            if racha["tipo"] == "LOSS" and racha["n"] >= 2:
                lineas.append(f"Currently on a {racha['n']}-loss streak, sir.")
            return " ".join(lineas)
        if tiene("recalibrate", "re-calibrate", "calibrate screen", "calibrate now",
                 "find buttons", "detect buttons", "scan screen"):
            a.calibrar_ahora()
            return "Re-calibrating all screen elements right now, sir."
        if tiene("rollover", "early exit", "calibrate rollover", "sell button"):
            a.calibrar_rollover_auto()
            return "Attempting to auto-detect the P&L area and Rollover button, sir."
        if tiene("pause trading", "stop trading", "take a break", "stop the trades"):
            a.agente._pausado_hasta = time.time() + 30 * 60
            return "Understood, sir. Pausing for 30 minutes. Say 'resume' when you're ready."
        if tiene("resume trading", "resume", "start again", "continue trading",
                 "restart trading", "activate trading", "start trading"):
            a.agente._pausado_hasta = 0.0
            if not a.trading_on:
                a.trading_on = True
                if hasattr(a.agente, "_errores_consec"):
                    a.agente._errores_consec = 0
                return ("Trading reactivated, sir. Error counter reset. "
                        "Watching the chart.")
            return "Resuming operations, sir. I'm watching the chart."
        if tiene("calibrate", "calibration"):
            a.abrir_calibracion()
            return "Opening calibration. We'll mark the chart and the buy and sell buttons."

        # --- Practice mode (demo) ----------------------------------------
        if tiene("practice", "practice mode", "demo mode", "start practicing",
                 "begin training", "train", "demo account", "operate on demo"):
            practica = getattr(a, "modo_practica", None)
            if not practica:
                return "The practice module is not available, sir."
            if tiene("stop", "disable", "deactivate", "turn off"):
                if practica.activo:
                    practica.desactivar()
                    s = practica.stats()
                    return (f"Practice mode deactivated. Session: {s['trades']} trades, "
                            f"WR {s['wr']:.0f}%, sir.")
                return "Practice mode was already inactive, sir."
            practica.activar()
            return ("Practice mode activated, sir. I'll operate on the demo account with "
                    "reduced thresholds to learn as fast as possible. Each trade teaches me "
                    "a new pattern. Ask 'how am I doing' anytime.")

        # --- Professional mode -------------------------------------------
        if tiene("professional mode", "professional trading", "real trading",
                 "activate professional", "go professional", "real capital"):
            profesional = getattr(a, "modo_profesional", None)
            if not profesional:
                return "The professional module is not available, sir."
            if tiene("stop", "disable", "deactivate", "turn off"):
                if profesional.activo:
                    profesional.desactivar()
                    s = profesional.stats()
                    return (f"Professional mode off. Session: {s['trades']} trades, "
                            f"WR {s['wr']:.0f}%, Kelly P&L {s['pnl_kelly']:+.2f}, sir.")
                return "Professional mode was already inactive, sir."
            profesional.activar()
            return ("Professional mode activated, sir. I'll apply maximum filters: "
                    "5/7 engines in agreement, high Bayesian probability, positive Kelly. "
                    "Only the highest-quality signals will be traded.")

        # --- Consciousness abstention override (English) -----------------
        if tiene("don't abstain", "force trade", "ignore conscience",
                 "override trade", "force operate", "keep trading",
                 "disable abstention", "trade anyway", "bypass conscience"):
            con = getattr(a, "conciencia", None)
            if con is None:
                from . import conciencia as _con_mod
                con = _con_mod.obtener(a)
            if con:
                msg = con.set_override("forzar_actuar")
                return (f"Understood, sir. Override active: I'll trade on every valid signal, "
                        f"ignoring abstention recommendations. "
                        f"Consciousness continues learning in the background.")
            return "Consciousness system unavailable, sir."

        if tiene("abstain", "stop trading conscience", "force abstain",
                 "pause conscience", "block trading conscience"):
            con = getattr(a, "conciencia", None)
            if con is None:
                from . import conciencia as _con_mod
                con = _con_mod.obtener(a)
            if con:
                msg = con.set_override("forzar_abstener")
                return f"Understood, sir. {msg}"
            return "Consciousness system unavailable, sir."

        if tiene("auto conscience", "automatic conscience",
                 "let conscience decide", "remove override", "restore conscience",
                 "normal conscience", "disable override"):
            con = getattr(a, "conciencia", None)
            if con is None:
                from . import conciencia as _con_mod
                con = _con_mod.obtener(a)
            if con:
                msg = con.set_override("auto")
                return f"Perfect, sir. {msg}"
            return "Consciousness system unavailable, sir."

        if tiene("conscience status", "override status", "abstention mode"):
            con = getattr(a, "conciencia", None)
            if con is None:
                from . import conciencia as _con_mod
                con = _con_mod.obtener(a)
            if con:
                modo = con.estado_override()
                return (f"Consciousness: {modo} | ECE={con.meta.ece():.3f} | "
                        f"{con.meta.n_trades()} observations.")
            return "Consciousness not initialized yet, sir."

        # --- Daily target ------------------------------------------------
        if tiene("daily target", "daily goal", "profit target", "stop loss limit",
                 "how much to earn", "daily limit", "set a goal"):
            meta = getattr(a, "meta_diaria", None)
            if not meta:
                from . import meta_diaria as _meta_mod
                meta = _meta_mod.obtener(a)
                a.meta_diaria = meta
            if tiene("cancel", "remove", "clear", "deactivate", "stop"):
                if meta.activa:
                    meta.desactivar()
                    return "Daily target deactivated, sir. I'll trade without a profit cap."
                return "No daily target was active, sir."
            if tiene("status", "progress", "how is it going"):
                s = meta.stats()
                if not s["activa"]:
                    return "No daily target configured, sir. Tell me an amount to activate one."
                sgn = "+" if s["pnl"] >= 0 else ""
                return (f"Daily target: {sgn}${s['pnl']:.2f} of ${s['meta_gan']:.0f}. "
                        f"{s['wins']}W {s['losses']}L. "
                        f"{'Completed.' if s['completada'] else 'In progress.'}")
            numeros = re.findall(r'\d+(?:[.,]\d+)?', t)
            if len(numeros) >= 2:
                mg = float(numeros[0].replace(",", "."))
                sp = float(numeros[1].replace(",", "."))
                meta.configurar(mg, sp)
                return (f"Daily target set: goal +${mg:.0f}, stop -${sp:.0f}. "
                        f"Starting operations, sir.")
            if len(numeros) == 1:
                mg = float(numeros[0].replace(",", "."))
                sp = mg * 0.5
                meta.configurar(mg, sp)
                return (f"Daily target: +${mg:.0f} with automatic stop at -${sp:.0f}. Ready, sir.")
            try:
                a.interfaz.root.after(0, a.interfaz.abrir_meta)
            except Exception:
                pass
            return "Opening the daily target panel, sir."

        # --- Autonomy status ---------------------------------------------
        if tiene("autonomy status", "what modes are active", "active modes",
                 "are you trading", "are you operating"):
            lineas = []
            practica    = getattr(a, "modo_practica",    None)
            profesional = getattr(a, "modo_profesional", None)
            meta        = getattr(a, "meta_diaria",      None)
            lineas.append(f"Trading: {'active' if a.trading_on else 'stopped'}.")
            if practica and practica.activo:
                s = practica.stats()
                lineas.append(f"Practice mode active: {s['trades']} trades, WR {s['wr']:.0f}%.")
            if profesional and profesional.activo:
                s = profesional.stats()
                lineas.append(f"Professional mode active: {s['trades']} trades, WR {s['wr']:.0f}%.")
            if meta and meta.activa:
                s = meta.stats()
                sgn = "+" if s["pnl"] >= 0 else ""
                lineas.append(f"Daily target: {sgn}${s['pnl']:.2f} / ${s['meta_gan']:.0f}.")
            if not lineas[1:]:
                lineas.append("No autonomous mode active. Say 'activate practice' to begin.")
            return " ".join(lineas)

        if tiene("hello", "hi ", "good morning", "good afternoon", "good evening") or t == "hi":
            return random.choice([
                "Hello, sir. All systems operational. How may I assist you?",
                "At your service. Panel active and pattern memory loaded.",
                "Greetings. Shall we analyze the market or review the statistics?",
            ])
        if tiene("who are you", "your name", "what are you"):
            return ("I am Litch, your personal AI assistant. I speak Spanish and English, "
                    "watch your screen, learn market patterns on the demo account, search "
                    "the web, and look after you. The more we work, the more I learn.")
        if tiene("thank"):
            return random.choice(["At your service, sir.", "A pleasure, as always.",
                                  "Anytime. I remain on watch."])
        if tiene("help", "what can you do", "commands"):
            return ("I can: start/stop trading, manage auto-click with master key, "
                    "search the web («Litch, search…»), deep research («research X»), "
                    "market news, asset prices («price AAPL»), read your email "
                    "(«read my email»), send emails autonomously, manage permissions, "
                    "set reminders, check weather, analyze lottery, calibrate screen, "
                    "and switch languages. Use the «📧 Email & AI» panel to configure "
                    "accounts and permissions.")
        if tiene("real money", "real account", "risk"):
            return ("My professional advice, sir: binary options carry a built-in "
                    "mathematical edge for the house. I work on demo only, and I will "
                    "never trade real money for you.")

        # --- Professional trading knowledge ----------------------------------
        if tiene("candlestick", "candle pattern", "doji", "hammer", "engulfing",
                 "morning star", "evening star", "marubozu", "harami",
                 "shooting star", "hanging man", "three soldiers", "three crows",
                 "dark cloud", "piercing line", "spinning top",
                 "what does this candle mean", "explain the pattern",
                 "candle meaning", "bearish candle", "bullish candle"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("scalping strategy", "scalping method", "how to scalp",
                 "ema crossover", "rsi scalping", "bollinger scalp",
                 "vwap scalping", "ny open scalp", "new york open strategy",
                 "quick entry", "fast entry", "liquidity sweep scalp"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("bull trap", "bear trap", "smart money", "fomo", "fud",
                 "short squeeze", "capitulation", "dead cat bounce", "rally",
                 "correction", "market liquidity", "stop hunt", "dumb money",
                 "what is a bull market", "what is a bear market",
                 "bull market", "bear market", "market cycle"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("trading session", "market session", "what session is it",
                 "when to trade", "trading hours", "market open", "market close",
                 "london session", "new york session", "tokyo session",
                 "session overlap", "best time to trade", "current session"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp
            return conocimiento_trading.resumen_sesion_actual()

        if tiene("trailing stop", "structure stop", "atr stop", "fixed stop",
                 "breakeven stop", "stop loss method", "how to set stop",
                 "stop methods", "time stop"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("price action", "order block", "fair value gap", "fvg",
                 "bos", "choch", "change of character", "supply zone",
                 "demand zone", "support and resistance", "fibonacci",
                 "confluence", "market structure", "liquidity grab",
                 "imbalance zone", "break of structure"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("risk management", "position sizing", "position size",
                 "revenge trading", "daily loss limit", "one percent rule",
                 "two percent rule", "risk reward", "rr ratio", "risk reward ratio",
                 "win rate needed", "minimum win rate"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("tradingview", "pine script", "tv screener", "trading view",
                 "tradingview alerts", "how to use tradingview",
                 "tradingview indicators", "set up tradingview"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("explain vwap", "explain rsi", "explain macd", "explain atr",
                 "explain bollinger", "explain ichimoku", "explain stochastic",
                 "what is vwap", "what is rsi", "what is macd", "what is atr",
                 "what indicator", "how to use the indicator"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("trading plan", "daily trading plan", "market open plan",
                 "ny open plan", "ny close plan", "power hour",
                 "swing trading", "ny lunch", "when not to trade",
                 "avoid trading"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("smc", "ict", "smart money concepts", "inner circle",
                 "amd cycle", "market maker model", "ote", "optimal trade entry",
                 "premium and discount", "breaker block", "displacement",
                 "inducement", "killzone", "kill zone", "london sweep",
                 "institutional money", "what is smc", "what is ict"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("latino wall street", "latinowallstreet", "lws",
                 "gabriela berrospi", "alan burak", "trading academy",
                 "trading course latam"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("broker express", "exness broker", "xm broker", "etoro",
                 "interactive brokers", "pepperstone",
                 "which broker to use", "best broker latam"):
            resp = conocimiento_trading.buscar(t, "en")
            if resp:
                return resp

        if tiene("interactive brokers", "ibkr", "ib broker", "tws"):
            bc = getattr(a, "conocimiento", None)
            if bc:
                if tiene("what is", "tell me", "explain"):
                    return bc.leer("brokers", "ibkr_que_es") or (
                        "Interactive Brokers is the world's most complete broker. "
                        "Access to 150+ markets, ultra-low commissions and professional API.")
                if tiene("connect", "paper", "demo"):
                    ibkr = getattr(a, "broker_ibkr", None)
                    if ibkr:
                        ok = ibkr.conectar(modo="paper")
                        return ("Connected to IBKR paper trading. No real money at risk, sir." if ok
                                else "Could not connect. Make sure TWS is open with API enabled, sir.")
                return bc.leer("brokers", "ibkr_que_es") or "IBKR is my target broker for real stock trading, sir."

        if tiene("schwab", "charles schwab", "thinkorswim"):
            bc = getattr(a, "conocimiento", None)
            if bc:
                if tiene("what is", "tell me", "explain"):
                    return bc.leer("brokers", "schwab_que_es") or (
                        "Charles Schwab is the largest retail broker in the US, with $9 trillion in assets.")
                return bc.leer("brokers", "schwab_que_es") or "Schwab is one of the safest brokers in the world, sir."

        # --- Broker universal ----------------------------------------
        if tiene("configure broker", "apply best config", "set broker",
                 "program broker", "apply optimal", "best setup"):
            cfg = a.broker.mejor_config()
            if cfg["trades"] < 5:
                return ("Not enough data yet, sir. "
                        "Trade at least 5 times so I can start learning.")
            res = a.broker.aplicar_config_completa()
            ok  = sum(res.values())
            if ok == 0:
                a.abrir_broker()
                return ("Broker UI not calibrated yet, sir. "
                        "Open the broker panel and calibrate the elements first.")
            return (f"Config applied: {cfg['asset']} at {cfg['duracion']}s "
                    f"with ${cfg['monto']:.0f}. Win rate: {cfg['win_rate']:.0f}%, sir.")
        if tiene("best asset", "which asset", "broker stats", "asset performance",
                 "broker performance", "how am i doing per asset"):
            return a.broker.resumen_texto()
        if tiene("open broker", "broker panel", "show broker stats",
                 "performance by asset"):
            a.abrir_broker()
            return "Opening the broker panel, sir."
        if tiene("switch to iq option", "use iq option", "iq option broker"):
            a.broker.cambiar_broker("iq_option")
            return "Switched to IQ Option, sir."
        if tiene("switch to quotex", "use quotex"):
            a.broker.cambiar_broker("quotex")
            return "Switched to Quotex, sir."
        if tiene("switch to deriv", "use deriv"):
            a.broker.cambiar_broker("deriv")
            return "Switched to Deriv, sir."
        if tiene("calibrate broker", "scan broker", "detect broker",
                 "find broker fields"):
            resultado = a.broker.calibrar_ui_auto()
            if resultado:
                return (f"Detected: {', '.join(resultado.keys())}. "
                        "I can now configure the broker automatically, sir.")
            a.abrir_broker()
            return ("Could not auto-detect broker elements, sir. "
                    "Open the broker panel to calibrate them manually.")
        if tiene("ask ai about broker", "ai broker advice", "best broker strategy",
                 "broker recommendation", "which asset should i use"):
            return a.broker.consultar_ia()
        if tiene("what did you learn", "broker lessons", "ai lessons", "what has ai taught you",
                 "trading lessons", "your knowledge"):
            return a.lecciones_broker_texto()
        if tiene("force learning", "learn now", "update knowledge", "consult ai now"):
            a.broker.consejero._trades_desde_ia = 99
            return a.txt(
                "Forcing an AI learning query on the next cycle, sir.",
                "Forcing an AI learning query on the next cycle, sir.")

        # --- Ollama toggle -------------------------------------------
        if tiene("enable ollama", "activate ollama", "use ollama",
                 "ollama on", "local ollama"):
            a.set_usar_ollama(True, hablar=True)
            return ""
        if tiene("disable ollama", "deactivate ollama", "ollama off",
                 "turn off ollama"):
            a.set_usar_ollama(False, hablar=True)
            return ""

        # --- Claude toggle -------------------------------------------
        if tiene("connect claude", "connect to claude", "activate claude",
                 "use claude", "enable claude", "switch to claude"):
            a.set_usar_claude(True, hablar=True)
            return ""
        if tiene("disconnect claude", "disconnect from claude", "disable claude",
                 "deactivate claude", "turn off claude"):
            a.set_usar_claude(False, hablar=True)
            return ""
        if tiene("claude status", "is claude active", "claude connected"):
            from . import mente_claude as _mc
            on  = getattr(a, "usar_claude", False)
            key = _mc.disponible()
            return (f"Claude is {'ACTIVE' if on else 'INACTIVE'}, sir. "
                    f"API key: {'configured' if key else 'not found'}.")

        self._fue_default = True
        return random.choice([
            "Understood, sir, though I'm not certain I follow. Say «help» to hear my functions.",
            "Interesting. Shall I search the web for that? Say «Litch, search» followed by the topic.",
            "I don't have a routine for that yet, but I've noted it in my memory, sir.",
        ])
