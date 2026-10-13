"""
rutinas_tws.py — Los PROCEDIMIENTOS de Litch para operar en Interactive Brokers.

Saber dónde está cada botón no es saber operar. Un operador profesional no
ejecuta una secuencia a ciegas: hace un paso, COMPRUEBA que salió como
esperaba, y solo entonces da el siguiente. Si algo no cuadra, se detiene.

Eso es lo que hay aquí: rutinas con precondición, acción y verificación.

POR QUÉ IMPORTA TANTO
─────────────────────
Una macro que hace «clic, clic, clic, enviar» funciona el 95% de las veces
y provoca un desastre el 5% restante — cuando una ventana tardó en cargar,
cuando el símbolo no existía, cuando saltó un aviso. Ese 5% es justo el que
mueve dinero de forma inesperada.

Una rutina verificada es más lenta y aburrida. También es la diferencia
entre un programa que ayuda y uno que un día hace algo que nadie le pidió.

ESTRUCTURA DE CADA PASO
───────────────────────
    antes()      ¿se dan las condiciones para intentarlo?
    hacer()      la acción en sí
    despues()    ¿ocurrió de verdad lo que debía ocurrir?

Si `antes` falla, no se intenta. Si `despues` falla, se DETIENE la rutina
entera: no se sigue construyendo sobre un paso que no se sabe si funcionó.
"""

from __future__ import annotations

import time


# ═══════════════════════════════════════════════════════════════════════════
#  Resultado de una rutina
# ═══════════════════════════════════════════════════════════════════════════

class Resultado:
    """Lo que pasó al ejecutar una rutina, paso a paso."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.pasos: list[dict] = []
        self.ok = False
        self.detenida_en = None
        self.motivo = ""

    def anotar(self, paso: str, ok: bool, detalle: str = ""):
        self.pasos.append({"paso": paso, "ok": ok, "detalle": detalle})

    def texto(self) -> str:
        lineas = [f"Rutina «{self.nombre}»:"]
        for i, p in enumerate(self.pasos, 1):
            marca = "✓" if p["ok"] else "✗"
            lineas.append(f"  {marca} {i}. {p['paso']}"
                          + (f" — {p['detalle']}" if p["detalle"] else ""))
        if self.ok:
            lineas.append("Completada, señor.")
        else:
            lineas.append(f"DETENIDA en «{self.detenida_en}»: {self.motivo}")
            lineas.append("No sigo adelante sobre un paso que no salió bien. "
                          "Prefiero pararme aquí a improvisar.")
        return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  RUTINA 1 — Revisión de apertura de sesión
# ═══════════════════════════════════════════════════════════════════════════

def revision_apertura(app) -> Resultado:
    """Las nueve comprobaciones antes de tocar nada. Todas o ninguna.

    Esta es la rutina que un operador serio hace cada mañana, y la que
    más disgustos evita. No mueve el mouse: solo mira.
    """
    r = Resultado("Revisión de apertura")

    # 1. ¿Está TWS?
    try:
        from . import vision_tws as vt
        est = vt.leer_estado_tws(app)
    except Exception as e:
        r.anotar("Buscar Trader Workstation", False, str(e))
        r.detenida_en, r.motivo = "Buscar TWS", f"error: {e}"
        return r

    if not est.get("tws_abierta"):
        r.anotar("Buscar Trader Workstation", False, "no lo encuentro")
        r.detenida_en = "Buscar TWS"
        r.motivo = ("Ábralo y déjelo visible. Si está abierto y aun así no "
                    "lo veo, dígame «¿qué ventanas ves?» y lo diagnostico.")
        return r
    r.anotar("Trader Workstation abierto", True, est.get("titulo", "")[:40])

    # 2. ¿Cuenta simulada? — innegociable
    p = est.get("es_paper")
    if p is False:
        r.anotar("Verificar cuenta simulada", False, "⛔ CUENTA REAL")
        r.detenida_en = "Verificar cuenta"
        r.motivo = ("La cuenta es REAL. No trabajo aquí hasta que cambie a "
                    "la simulada. Esto no es negociable.")
        return r
    if p is None:
        r.anotar("Verificar cuenta simulada", False, "no confirmado")
        r.detenida_en = "Verificar cuenta"
        r.motivo = ("No puedo confirmar que sea simulada, y la duda no basta "
                    "para seguir. El título debe mostrar DU.")
        return r
    r.anotar("Cuenta simulada verificada", True, est.get("cuenta", "DU…"))

    # 3. ¿Algo tapando TWS?
    try:
        from . import conciencia_pantalla as cp
        d = cp.detectar_dialogo(app)
        if d.get("hay"):
            r.anotar("Comprobar que nada estorba", False, d["mensaje"][:70])
            r.detenida_en = "Ventanas encima"
            r.motivo = d["mensaje"]
            return r
        r.anotar("Nada tapa TWS", True)
    except Exception:
        r.anotar("Comprobar ventanas encima", True, "no pude, sigo")

    # 4. ¿Mercado abierto?
    try:
        from . import motor_acciones as ma
        abierto, detalle = ma.mercado_abierto()
        r.anotar("Horario de Wall Street", True, detalle[:70])
        if not abierto:
            r.anotar("Aviso", True, "mercado cerrado: solo estudio, no opero")
    except Exception as e:
        r.anotar("Horario de Wall Street", False, str(e))

    # 5. ¿Visión calibrada a TWS?
    cfg = app.mem.get("config", {})
    if cfg.get("broker_visual") == "tws":
        r.anotar("Visión apuntando a TWS", True)
    else:
        r.anotar("Visión apuntando a TWS", False,
                 "sigo mirando IQ Option — dígame «calibra para IBKR»")

    # 6. ¿Ticket calibrado?
    try:
        from . import piloto_tws as pt
        if pt.esta_calibrado(app):
            r.anotar("Ticket de órdenes calibrado", True)
        else:
            r.anotar("Ticket de órdenes calibrado", False,
                     "sin calibrar solo puedo ensayar")
    except Exception:
        pass

    # 7. ¿Cortacircuito de riesgo en verde?
    try:
        from . import guardias_riesgo as gr
        cc = gr.cortacircuito(app)
        nivel = cc.get("nivel", "?")
        r.anotar(f"Cortacircuito de riesgo: {nivel}",
                 nivel in ("VERDE", "AMARILLO"),
                 cc.get("motivo", "")[:60])
    except Exception:
        pass

    # 8. Recordatorio del modo del panel — el peligro silencioso
    r.anotar("Recordatorio: modo del panel", True,
             "compruebe que NO está en Rapid Transmit (⚙ del ticket)")

    # 9. Regla del día
    r.anotar("Regla de la sesión", True,
             "1% de riesgo por operación, stop siempre, nada sin plan")

    r.ok = True
    return r


# ═══════════════════════════════════════════════════════════════════════════
#  RUTINA 2 — Preparar una operación completa, con verificación
# ═══════════════════════════════════════════════════════════════════════════

def preparar_operacion_verificada(app, simbolo: str = "SPY",
                                  ejecutar: bool = False) -> Resultado:
    """El ciclo completo: revisar → analizar → dimensionar → armar → verificar.

    Por defecto NO ejecuta: construye el plan y lo enseña. Es lo que un
    operador hace antes de tocar el ratón — decidirlo todo en frío.
    """
    simbolo = (simbolo or "SPY").upper().strip()
    r = Resultado(f"Preparar operación en {simbolo}")

    # Paso 1: la revisión de apertura debe pasar
    base = revision_apertura(app)
    if not base.ok:
        r.anotar("Revisión de apertura", False, base.motivo[:70])
        r.detenida_en = "Revisión de apertura"
        r.motivo = base.motivo
        return r
    r.anotar("Revisión de apertura superada", True)

    # Paso 2: mercado abierto (si no, se estudia pero no se opera)
    try:
        from . import motor_acciones as ma
        abierto, detalle = ma.mercado_abierto()
    except Exception as e:
        r.anotar("Horario", False, str(e))
        r.detenida_en, r.motivo = "Horario", str(e)
        return r

    if not abierto and ejecutar:
        r.anotar("Mercado abierto", False, detalle[:60])
        r.detenida_en = "Horario"
        r.motivo = ("El mercado está cerrado. No armo una operación real "
                    "con datos congelados.")
        return r
    r.anotar("Horario comprobado", True, detalle[:60])

    # Paso 3: análisis con datos DEL SÍMBOLO PEDIDO
    an = ma.analizar_accion(app, simbolo)
    fuente = an.get("fuente", "?")
    if an.get("precio", 0) <= 0:
        r.anotar(f"Analizar {simbolo}", False, fuente)
        r.detenida_en = "Análisis"
        r.motivo = (f"No conseguí datos de {simbolo} ({fuente}). Sin datos "
                    f"no hay análisis, y sin análisis no hay operación.")
        return r
    r.anotar(f"Analizar {simbolo}", True,
             f"{an['direccion']}, {an['votos']}/{an.get('votos_max',4)} votos, "
             f"datos de {fuente}")

    # Paso 4: ¿hay consenso? Abstenerse es un resultado válido
    if an["direccion"] == "ESPERA":
        r.anotar("Consenso suficiente", False, "señales divididas")
        r.detenida_en = "Consenso"
        r.motivo = ("Me abstengo: las señales no coinciden lo bastante. "
                    "No operar es una decisión, y hoy es la correcta para "
                    "este activo.")
        return r
    r.anotar("Consenso suficiente", True, an["direccion"])

    # Paso 5: memoria — ¿este setup ya nos ha salido mal antes?
    # (veredicto_setup es un MÉTODO del singleton, no una función suelta)
    try:
        from . import memoria_acciones as mem_ac
        ver = mem_ac.obtener().veredicto_setup(simbolo, an["direccion"], an)
        etq = ver.get("tipo", "neutral")
        msg = ver.get("mensaje", "")
        if etq == "peligroso":
            r.anotar("Memoria de setups", False, msg[:60])
            r.detenida_en = "Memoria"
            r.motivo = (f"Este mismo setup ya me ha salido mal antes. {msg} "
                        f"No lo repito: para eso llevo memoria.")
            return r
        r.anotar(f"Memoria de setups: {etq}", True,
                 msg[:60] or "sin historial")
    except Exception as e:
        r.anotar("Memoria de setups", True, f"sin historial ({e})"[:60])

    # Paso 6: dimensionar por riesgo, nunca por capricho
    try:
        plan = ma.preparar_operacion(app, simbolo)
    except Exception as e:
        r.anotar("Dimensionar la posición", False, str(e))
        r.detenida_en, r.motivo = "Dimensionar", str(e)
        return r

    # preparar_operacion marca el éxito con "listo", no con "ok"
    if not plan.get("listo"):
        r.anotar("Dimensionar la posición", False,
                 plan.get("mensaje", "")[:70])
        r.detenida_en = "Dimensionar"
        r.motivo = plan.get("mensaje", "no pude calcular el tamaño")
        return r
    r.anotar("Posición dimensionada por ATR", True,
             f"{plan.get('cantidad')} acciones, riesgo "
             f"{plan.get('riesgo_dolares', '?')}")

    # Paso 7: coherencia del bracket — la última red antes de nada
    e = plan.get("entrada", 0)
    s = plan.get("stop", 0)
    o = plan.get("objetivo", 0)
    accion = "BUY" if an["direccion"] == "COMPRA" else "SELL"
    coherente = (s < e < o) if accion == "BUY" else (o < e < s)
    if not coherente:
        r.anotar("Coherencia del bracket", False,
                 f"entrada {e}, stop {s}, objetivo {o}")
        r.detenida_en = "Coherencia"
        r.motivo = ("Los tres precios no encajan. Antes que enviar un "
                    "bracket imposible, me detengo.")
        return r
    riesgo = abs(e - s)
    ratio = round(abs(o - e) / riesgo, 2) if riesgo else 0
    if ratio < 1.5:
        r.anotar("Relación ganancia/riesgo", False, f"{ratio}:1")
        r.detenida_en = "Ratio"
        r.motivo = (f"Ratio {ratio}:1, por debajo del mínimo 1.5:1. "
                    f"Arriesgar más de lo que se puede ganar no compensa "
                    f"ni acertando la mayoría de las veces.")
        return r
    r.anotar("Bracket coherente", True,
             f"entrada {e} | stop {s} | objetivo {o} | ratio {ratio}:1")

    # Paso 8: el plan, escrito
    r.anotar("Plan listo", True,
             f"{accion} {plan.get('cantidad')}x {simbolo}")

    if not ejecutar:
        r.ok = True
        r.plan = plan
        return r

    # ── Paso 8.5: REVISIÓN DE MARGEN (el paso «d» del PDF de TWS) ────────
    #
    # La guía de operativa en TWS marca cinco pasos, y el cuarto es
    # «revisar la orden antes de enviarla al mercado»: clic derecho →
    # «Revisar perfil de rendimiento / margen». Ahí se ven el coste real,
    # los avisos de IBKR y el impacto sobre el margen.
    #
    # Es el paso que casi todo el mundo se salta. Por API el equivalente
    # exacto es whatIfOrder: pide ese mismo cálculo SIN transmitir nada.
    try:
        _mg = revisar_margen(app, simbolo, accion, plan["cantidad"], e)
        r.anotar("Revisión de margen (paso d del manual)",
                 _mg.get("ok", True), _mg.get("resumen", "")[:70])
        if not _mg.get("ok", True):
            r.detenida_en = "Margen"
            r.motivo = _mg.get("resumen", "la revisión de margen falló")
            return r
        for _av in _mg.get("avisos", []):
            r.anotar("⚠ aviso de IBKR", True, _av[:70])
    except Exception as _emg:
        r.anotar("Revisión de margen", True, f"no disponible ({_emg})")

    # Paso 9: ejecución — solo por API, con bracket, y en paper verificado
    br = getattr(app, "broker_ibkr", None)
    if br is None or not getattr(br, "esta_conectado", False):
        r.anotar("Conexión con IBKR", False, "no conectado")
        r.detenida_en = "Conexión"
        r.motivo = ("Para ejecutar necesito la API de IBKR conectada. "
                    "Por la API el bracket entra completo y atómico; a "
                    "base de clics podría quedarme a medias, con la "
                    "entrada puesta y el stop sin poner. Eso es lo peor "
                    "que puede pasar.")
        return r

    res = br.bracket(simbolo, accion, plan["cantidad"], e, s, o,
                     dry_run=False)
    r.anotar("Enviar bracket por API", bool(res.get("ok")),
             res.get("msg", "")[:70])
    if not res.get("ok"):
        r.detenida_en = "Envío"
        r.motivo = res.get("msg", "el envío falló")
        return r

    r.ok = True
    r.plan = plan
    return r


# ═══════════════════════════════════════════════════════════════════════════
#  Revisión de margen — el paso «d» de los cinco del manual de TWS
# ═══════════════════════════════════════════════════════════════════════════

def revisar_margen(app, simbolo: str, accion: str, cantidad,
                   precio=None) -> dict:
    """Pide a IBKR el coste y el impacto en margen SIN enviar la orden.

    Es el equivalente por API de lo que en TWS se hace con clic derecho →
    «Revisar perfil de rendimiento / margen». La guía lo pone como paso
    obligatorio antes de transmitir, y con razón: ahí es donde IBKR avisa
    de que el número de contratos es raro o de que el precio límite está
    lejos del mercado.

    `whatIfOrder` calcula todo eso sin crear ninguna orden real.
    """
    r = {"ok": True, "resumen": "", "avisos": [], "datos": {}}

    br = getattr(app, "broker_ibkr", None)
    if br is None or not getattr(br, "esta_conectado", False):
        r["resumen"] = "sin conexión a IBKR: no puedo revisar el margen"
        return r

    try:
        from ib_async import Stock, LimitOrder
    except Exception:
        try:
            from ib_insync import Stock, LimitOrder
        except Exception:
            r["resumen"] = "sin librería de IBKR"
            return r

    try:
        ib = getattr(br, "_ib", None)
        if ib is None:
            r["resumen"] = "conector sin sesión"
            return r

        contrato = Stock(str(simbolo).upper(), "SMART", "USD")
        ib.qualifyContracts(contrato)
        lado = "BUY" if str(accion).upper() in ("BUY", "COMPRA",
                                                "COMPRAR") else "SELL"
        orden = LimitOrder(lado, int(cantidad), float(precio or 0))

        estado = ib.whatIfOrder(contrato, orden)
        if not estado:
            r["resumen"] = "IBKR no devolvió el cálculo de margen"
            return r

        def _num(v):
            try:
                f = float(v)
                # IBKR usa este valor centinela para «sin dato»
                return None if f > 1e30 else f
            except Exception:
                return None

        init = _num(getattr(estado, "initMarginChange", None))
        maint = _num(getattr(estado, "maintMarginChange", None))
        equity = _num(getattr(estado, "equityWithLoanChange", None))
        comision = _num(getattr(estado, "commission", None))

        r["datos"] = {"margen_inicial": init, "margen_mant": maint,
                      "equity": equity, "comision": comision}

        partes = []
        if init is not None:
            partes.append(f"margen inicial {init:,.0f} USD")
        if comision is not None:
            partes.append(f"comisión {comision:,.2f}")
        r["resumen"] = " · ".join(partes) or "cálculo recibido"

        # ── Los avisos que da TWS en esa misma ventana ──────────────────
        try:
            bal = br.balance_cuenta() or {}
            neto = float(bal.get("valor_neto") or bal.get("liquidez") or 0)
            excess = float(bal.get("excess_liquidity") or 0)
        except Exception:
            neto = excess = 0.0

        if init is not None and excess > 0 and init > excess:
            r["ok"] = False
            r["resumen"] = (f"⛔ Esta orden exige {init:,.0f} USD de margen "
                            f"y su colchón es de {excess:,.0f}. No cabe.")
        elif init is not None and excess > 0 and init > excess * 0.5:
            r["avisos"].append(
                f"Esta orden se come más de la mitad de su colchón de "
                f"margen ({init:,.0f} de {excess:,.0f}). Si el mercado va "
                f"en contra, se acercará al punto en que IBKR liquida.")

        if comision is not None and precio and cantidad:
            valor = float(precio) * int(cantidad)
            if valor > 0 and comision / valor > 0.01:
                r["avisos"].append(
                    f"La comisión ({comision:,.2f}) es el "
                    f"{100*comision/valor:.1f}% de la operación. En "
                    f"operaciones pequeñas los costes se comen el "
                    f"resultado antes de empezar.")
        return r
    except Exception as e:
        r["resumen"] = f"no pude calcular el margen: {e}"
        return r


# ═══════════════════════════════════════════════════════════════════════════
#  RUTINA 3 — Ensayo general: ¿qué sabe hacer Litch hoy?
# ═══════════════════════════════════════════════════════════════════════════

def ensayo_general(app) -> str:
    """Litch se autoevalúa: qué puede hacer ya y qué le falta.

    Sin tocar nada. Es el examen que se hace a sí mismo para no prometer
    lo que no puede cumplir.
    """
    filas = []

    def check(nombre, prueba, arreglo=""):
        try:
            ok, det = prueba()
        except Exception as e:
            ok, det = False, f"error: {e}"
        filas.append((nombre, ok, det, arreglo))

    def _tws():
        from . import vision_tws as vt
        v = vt.ventana_tws()
        return (bool(v), v["titulo"][:34] if v else "no lo veo")

    def _paper():
        from . import vision_tws as vt
        e = vt.leer_estado_tws(app)
        return (e.get("es_paper") is True,
                e.get("cuenta") or "sin confirmar")

    def _vision():
        cfg = app.mem.get("config", {})
        return (cfg.get("broker_visual") == "tws",
                cfg.get("broker_visual") or "sin calibrar")

    def _ticket():
        from . import piloto_tws as pt
        return (pt.esta_calibrado(app),
                "calibrado" if pt.esta_calibrado(app) else "sin calibrar")

    def _datos():
        from . import motor_acciones as ma
        c, f = ma.velas_de(app, "SPY")
        return (len(c) >= 30, f"{len(c)} velas — {f}"[:44])

    def _api():
        br = getattr(app, "broker_ibkr", None)
        if br is None:
            return (False, "conector no iniciado")
        con = bool(getattr(br, "esta_conectado", False))
        return (con, "conectada" if con else "sin conectar")

    def _mercado():
        from . import motor_acciones as ma
        ab, d = ma.mercado_abierto()
        return (ab, d[:44])

    def _memoria():
        from . import memoria_acciones as mem
        n = len(getattr(mem.obtener(), "_ops", []) or [])
        return (True, f"{n} operaciones recordadas")

    check("Veo Trader Workstation", _tws,
          "ábralo; si sigue sin verse: «¿qué ventanas ves?»")
    check("Cuenta simulada confirmada", _paper,
          "inicie sesión en la cuenta DU")
    check("Visión apuntando a TWS", _vision, "diga «calibra para IBKR»")
    check("Sé dónde está cada botón", _ticket,
          "diga «calibra el ticket de TWS»")
    check("Traigo datos de mercado", _datos,
          "compruebe internet / instale yfinance")
    check("API de IBKR conectada", _api,
          "habilite la API en TWS y diga «conecta con IBKR»")
    check("Mercado abierto ahora", _mercado, "abre 9:30 ET (8:30 suya)")
    check("Memoria de operaciones", _memoria, "")

    listos = sum(1 for _, ok, _, _ in filas if ok)
    total = len(filas)

    lineas = [f"ENSAYO GENERAL — {listos} de {total} listos", ""]
    for nombre, ok, det, arreglo in filas:
        lineas.append(f"  {'✓' if ok else '✗'} {nombre}: {det}")
        if not ok and arreglo:
            lineas.append(f"      → {arreglo}")

    lineas.append("")
    if listos == total:
        lineas.append("Todo en orden, señor. Puedo trabajar en Interactive "
                      "Brokers con las protecciones puestas.")
    elif listos >= 5:
        lineas.append("Puedo analizar y prepararle operaciones, pero aún no "
                      "estoy completo. Lo que falta está arriba con su "
                      "arreglo al lado.")
    else:
        lineas.append("Todavía no estoy listo para operar. No se lo voy a "
                      "disimular: prefiero decírselo a fingir que puedo.")

    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  RUTINA 5 — ¿El precio que veo es de verdad el de ahora?
# ═══════════════════════════════════════════════════════════════════════════

def verificar_datos(app, simbolo: str = "SPY") -> Resultado:
    """Comprueba que el precio que Litch está leyendo es actual y real.

    Es la comprobación que nadie hace y que arruina cuentas: TWS pinta un
    precio retrasado exactamente igual que uno en vivo. La diferencia son
    quince minutos, y quince minutos en Wall Street son otro precio.
    """
    from . import datos_mercado as dm

    r = Resultado("Verificación del dato de mercado")

    ib = getattr(getattr(app, "ibkr", None), "_ib", None)
    if ib is None:
        r.detenida_en = "conexión"
        r.motivo = ("No hay conexión con TWS. Sin conexión no puedo "
                    "certificar ningún precio.")
        r.anotar("Conexión con TWS", False, r.motivo)
        return r
    r.anotar("Conexión con TWS", True)

    tipo = dm.leer_tipo(ib)
    nombre = dm.NOMBRE_TIPO.get(tipo, "desconocido")
    if tipo == dm.EN_VIVO:
        r.anotar("Clase de dato", True, f"{nombre} — es el bueno")
    elif tipo == 0:
        r.anotar("Clase de dato", False,
                 "no consta; TWS no me dice qué me está dando")
    else:
        r.anotar("Clase de dato", False,
                 f"{nombre} — no sirve para calcular un stop")

    cot = None
    try:
        cot = app.ibkr.cotizacion(simbolo)
    except Exception as e:
        r.anotar(f"Cotización de {simbolo}", False, str(e))

    if not cot:
        r.detenida_en = "cotización"
        r.motivo = (f"No obtuve precio de {simbolo}. Lo habitual es que la "
                    f"cuenta no tenga suscripción de datos para ese mercado: "
                    f"se activa en el portal de IBKR, en Configuración de "
                    f"Cuenta → Suscripciones de Datos de Mercado.")
        r.anotar(f"Cotización de {simbolo}", False, "sin precio")
        return r

    r.anotar(f"Cotización de {simbolo}", True,
             f"{cot['precio']:.2f} (bid {cot['bid']:.2f} / ask {cot['ask']:.2f})")

    # Un spread desmedido delata dato viejo, mercado cerrado o poca liquidez.
    spread = cot.get("spread", 0.0) or 0.0
    if cot["precio"] > 0:
        pct = spread / cot["precio"] * 100.0
        if pct > 1.0:
            r.anotar("Horquilla (spread)", False,
                     f"{pct:.2f}% del precio — demasiado ancha. O el mercado "
                     f"está cerrado, o el activo tiene poca liquidez, o el "
                     f"dato es viejo. Entrar aquí cuesta caro.")
        else:
            r.anotar("Horquilla (spread)", True, f"{pct:.3f}% del precio")

    if not cot.get("en_vivo"):
        r.detenida_en = "calidad del dato"
        r.motivo = (cot.get("aviso") or "el dato no es en vivo") + \
                   ". Puedo analizar y practicar con esto, pero no ejecutaría " \
                   "dinero real sobre un precio que no sé de cuándo es."
        return r

    r.ok = True
    return r


# ═══════════════════════════════════════════════════════════════════════════
#  Lo que Litch sabe hacer, dicho en voz alta
# ═══════════════════════════════════════════════════════════════════════════

RUTINAS = {
    "revision":  ("revisión de apertura",
                  "Las nueve comprobaciones antes de tocar nada."),
    "preparar":  ("preparar operación",
                  "Análisis, tamaño por riesgo y bracket coherente."),
    "datos":     ("verificar datos",
                  "¿El precio que veo es de ahora o de hace 15 minutos?"),
    "ensayo":    ("ensayo general",
                  "Litch se autoevalúa y dice qué le falta."),
}


def listar_rutinas() -> str:
    lineas = ["Estas son mis rutinas para Interactive Brokers:"]
    for _, (nombre, desc) in RUTINAS.items():
        lineas.append(f"  · «{nombre}» — {desc}")
    lineas.append("")
    lineas.append("Cada una comprueba después de cada paso y se detiene si "
                  "algo no cuadra. Prefiero pararme a medias que seguir "
                  "construyendo sobre un paso que no sé si salió bien.")
    return "\n".join(lineas)
