"""
conocimiento_brokers.py — Manual de uso de los brokers, integrado en la
INTELIGENCIA de Litch (no solo como biblioteca).

A diferencia de LIBROS/ (texto que se consulta al preguntar), este módulo
codifica las funciones de IQ Option e Interactive Brokers en forma
ESTRUCTURADA y consultable por código: Litch lo usa al operar, al explorar
la pantalla del broker (UILearner / ExploradBroker) y al responder.

Cada función trae: qué es, cómo se usa, cuándo, y su regla de seguridad.
Fuente: documentación oficial de IQ Option e IBKR (Trader Workstation).
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════
#  IQ OPTION — funciones de la plataforma
# ═══════════════════════════════════════════════════════════════════════════

IQ_OPTION = {
    "boton_sube": {
        "que_es": "Botón verde SUPERIOR (Higher). Abre una opción a que el "
                  "precio SUBA al vencimiento.",
        "como_usar": "Fijar monto y vencimiento, y pulsar antes de la línea "
                     "de corte de compra.",
        "cuando": "Cuando el consenso de motores apunta a alza con votos "
                  "suficientes.",
        "seguridad": "Solo se pulsa en modo autónomo autorizado. Nunca con "
                     "menos del umbral de votos aprendido.",
    },
    "boton_baja": {
        "que_es": "Botón rojo INFERIOR (Lower). Abre una opción a que el "
                  "precio BAJE al vencimiento.",
        "como_usar": "Fijar monto y vencimiento, y pulsar antes de la línea "
                     "de corte de compra.",
        "cuando": "Cuando el consenso apunta a baja con votos suficientes.",
        "seguridad": "Igual que SUBE: solo autónomo autorizado y sobre el "
                     "umbral.",
    },
    "monto": {
        "que_es": "Inversión por operación (mín $1, máx $20.000). En binarias "
                  "es el riesgo total: se pierde completo al fallar.",
        "como_usar": "Escribir el valor en la casilla de inversión.",
        "cuando": "Siempre antes de operar.",
        "seguridad": "Nunca más del 1-2% del capital. Nunca doblar tras "
                     "perder (martingala).",
    },
    "vencimiento": {
        "que_es": "Tiempo hasta que la opción cierra (segundos a minutos). "
                  "Blitz = 5-30s (mucho ruido).",
        "como_usar": "Elegir en el panel de trading.",
        "cuando": "Vencimientos ≥1 min tienen menos ruido que Blitz.",
        "seguridad": "En Blitz el azar domina; exigir señales de altísima "
                     "confianza o evitarlo.",
    },
    "payout": {
        "que_es": "Porcentaje de ganancia si se acierta (ej. +85%). Cambia "
                  "durante el día y por activo.",
        "como_usar": "Leerlo antes de operar en el panel de trading.",
        "cuando": "Verificar que sea ≥80%.",
        "seguridad": "Con payout 85% se necesita >54% de acierto solo para no "
                     "perder. Payout bajo puede borrar la ventaja.",
    },
    "linea_corte_compra": {
        "que_es": "Línea vertical punteada que marca el corte para entrar en "
                  "una opción.",
        "como_usar": "Colocar la orden ANTES de que la línea alcance el "
                     "precio actual.",
        "cuando": "En cada opción binaria/digital.",
        "seguridad": "Entrar tarde invalida el trade: es un error a evitar.",
    },
    "selector_activo": {
        "que_es": "Menú (+) con 300+ instrumentos: binarias, forex, cripto, "
                  "acciones, materias primas, índices.",
        "como_usar": "Abrir el +, buscar el activo y seleccionarlo.",
        "cuando": "Al elegir dónde operar; verificar payout de cada uno.",
        "seguridad": "Registrar si es OTC (precio sintético del broker) y no "
                     "mezclar sus estadísticas con mercado real.",
    },
    "color_saldo": {
        "que_es": "El color del saldo indica la cuenta: NARANJA = demo, "
                  "VERDE = real.",
        "como_usar": "Leer el color antes de operar.",
        "cuando": "Siempre.",
        "seguridad": "Regla de honestidad: Litch debe decir en qué cuenta "
                     "está. Nunca decir 'dinero real' en demo.",
    },
    "historial": {
        "que_es": "Lista de operaciones cerradas con su resultado real.",
        "como_usar": "Leerla para verificar aciertos contra la verdad del "
                     "broker.",
        "cuando": "Tras cada trade.",
        "seguridad": "Registrar el resultado REAL leído, no el estimado.",
    },
    "multiventana": {
        "que_es": "Divide la pantalla en 1, 2, 4 o 9 gráficos.",
        "como_usar": "Botón de vista multiventana arriba a la izquierda.",
        "cuando": "Para vigilar activos correlacionados o varias "
                  "temporalidades.",
        "seguridad": "No sobrecargar la visión: más gráficos = más CPU.",
    },
}

# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIVE BROKERS (TWS) — tipos de orden y funciones
# ═══════════════════════════════════════════════════════════════════════════

IBKR = {
    "limit": {
        "que_es": "Orden LÍMITE: compra/venta a un precio específico o mejor.",
        "como_usar": "Elegir LMT en el Order Type y fijar el precio.",
        "cuando": "Para ENTRAR con control de precio (orden estándar).",
        "seguridad": "Preferida sobre Market en activos poco líquidos.",
    },
    "market": {
        "que_es": "Orden de MERCADO: al mejor precio disponible ahora, sin "
                  "garantía de precio.",
        "como_usar": "Elegir MKT en el Order Type.",
        "cuando": "Solo en activos MUY líquidos cuando urge entrar/salir.",
        "seguridad": "Riesgo de slippage: evitar en baja liquidez.",
    },
    "stop": {
        "que_es": "STOP: envía una orden de mercado al tocar el precio "
                  "disparador. Protege pérdida o ganancia.",
        "como_usar": "Sell Stop DEBAJO del precio (posición larga); Buy Stop "
                     "ARRIBA (posición corta).",
        "cuando": "Como stop-loss de toda posición.",
        "seguridad": "El stop va donde la idea queda invalidada, no a una "
                     "distancia arbitraria.",
    },
    "stop_limit": {
        "que_es": "STOP LIMIT: al tocar el disparador envía una orden límite "
                  "(no de mercado).",
        "como_usar": "Definir precio de stop y precio límite.",
        "cuando": "Cuando se quiere controlar el precio de salida.",
        "seguridad": "Riesgo: puede no ejecutarse si el precio salta el "
                     "límite (gaps).",
    },
    "bracket": {
        "que_es": "BRACKET: envuelve una orden con dos opuestas — take-profit "
                  "(límite) y stop-loss (stop). La forma correcta de operar "
                  "un plan completo.",
        "como_usar": "Compra = venta límite arriba + venta stop abajo. "
                     "Venta = compra stop arriba + compra límite abajo. "
                     "Se enlazan con OCA.",
        "cuando": "SIEMPRE que se entra en una posición.",
        "seguridad": "Stop y objetivo definidos ANTES de entrar. Es la "
                     "disciplina de riesgo hecha orden.",
    },
    "trailing_stop": {
        "que_es": "TRAILING STOP: stop dinámico a distancia fija del precio. "
                  "Si el precio va a favor, el stop lo sigue; si va en "
                  "contra, se queda quieto.",
        "como_usar": "Definir el Trailing Amount (distancia). Al tocarlo, "
                     "dispara una orden de mercado.",
        "cuando": "Para dejar correr la ganancia en una tendencia.",
        "seguridad": "Limita la pérdida máxima sin limitar la ganancia. "
                     "Ideal para asegurar ganancias en tendencia.",
    },
    "oca": {
        "que_es": "OCA/OCO (One-Cancels-All/Other): grupo de órdenes donde si "
                  "una se ejecuta, las demás se cancelan.",
        "como_usar": "Es el mecanismo detrás del bracket.",
        "cuando": "Para que take-profit y stop-loss no coexistan.",
        "seguridad": "Evita quedar con órdenes huérfanas tras un llenado.",
    },
    "fractional": {
        "que_es": "FRACTIONAL SHARES: construir el portafolio por monto en "
                  "dólares, comprando fracciones de acción desde $1.",
        "como_usar": "Indicar el monto en dólares en vez del número de "
                     "acciones.",
        "cuando": "Clave para empezar con poco capital y diversificar.",
        "seguridad": "Permite respetar el 1-2% aun con acciones caras.",
    },
    "tif": {
        "que_es": "Time in Force: cuánto vive la orden. DAY (solo hoy), GTC "
                  "(hasta cancelar), GTD (hasta fecha), IOC (inmediata o "
                  "cancela), FOK (completa o cancela).",
        "como_usar": "Elegir en el Order Ticket.",
        "cuando": "DAY para intradía; GTC para órdenes en reposo.",
        "seguridad": "En cuenta cash, recordar la liquidación T+1.",
    },
    "transmit": {
        "que_es": "Botón TRANSMIT: confirma y envía la orden. En TWS crear la "
                  "orden NO la envía hasta pulsar Transmit.",
        "como_usar": "Revisar la orden y pulsar Transmit.",
        "cuando": "Al final de cada orden.",
        "seguridad": "Esa doble confirmación es una protección, no un "
                     "estorbo.",
    },
    "puerto_paper": {
        "que_es": "Puerto 7497 = cuenta PAPER (dinero simulado). 7496 = real.",
        "como_usar": "Litch conecta SIEMPRE primero al 7497.",
        "cuando": "Para practicar y validar antes de arriesgar dinero.",
        "seguridad": "El real (7496) se pide explícitamente. Paper primero, "
                     "siempre.",
    },
    "pdt": {
        "que_es": "Regla PDT: con cuenta de margen <$25.000, máximo 3 "
                  "day-trades por 5 días hábiles.",
        "como_usar": "Contar los day-trades; usar cuenta cash o swing si "
                     "molesta.",
        "cuando": "En acciones de EEUU con cuenta pequeña.",
        "seguridad": "Violarla congela el day trading de la cuenta.",
    },
    "rth": {
        "que_es": "RTH (Regular Trading Hours): sesión principal de acciones "
                  "de EEUU, 09:30-16:00 ET.",
        "como_usar": "Operar dentro de RTH salvo estrategia específica.",
        "cuando": "Siempre que sea posible.",
        "seguridad": "Fuera de RTH la liquidez cae y los spreads se amplían.",
    },
}


# ── Mapa: nombre de elemento en pantalla → clave de conocimiento ────────────
# Lo usa el ExploradBroker/UILearner para saber qué hace lo que ve.
_ALIAS_UI = {
    "sube": ("iq", "boton_sube"), "higher": ("iq", "boton_sube"),
    "call": ("iq", "boton_sube"), "verde": ("iq", "boton_sube"),
    "baja": ("iq", "boton_baja"), "lower": ("iq", "boton_baja"),
    "put": ("iq", "boton_baja"), "rojo": ("iq", "boton_baja"),
    "monto": ("iq", "monto"), "inversion": ("iq", "monto"),
    "vencimiento": ("iq", "vencimiento"), "payout": ("iq", "payout"),
    "activo": ("iq", "selector_activo"), "saldo": ("iq", "color_saldo"),
    "historial": ("iq", "historial"),
    "bracket": ("ibkr", "bracket"), "trailing": ("ibkr", "trailing_stop"),
    "stop": ("ibkr", "stop"), "limit": ("ibkr", "limit"),
    "market": ("ibkr", "market"), "transmit": ("ibkr", "transmit"),
    "oca": ("ibkr", "oca"), "oco": ("ibkr", "oca"),
    "fraccion": ("ibkr", "fractional"), "fractional": ("ibkr", "fractional"),
}


def _fmt(clave: str, d: dict) -> str:
    return (f"• {clave.replace('_', ' ').upper()}\n"
            f"  Qué es: {d['que_es']}\n"
            f"  Cómo se usa: {d['como_usar']}\n"
            f"  Cuándo: {d['cuando']}\n"
            f"  Seguridad: {d['seguridad']}")


def explicar(broker: str, clave: str) -> str | None:
    """Devuelve la ficha de una función concreta. broker: 'iq' o 'ibkr'."""
    fuente = IQ_OPTION if broker == "iq" else IBKR
    d = fuente.get(clave)
    return _fmt(clave, d) if d else None


def funcion_de_elemento(nombre_ui: str) -> str | None:
    """Dado el nombre de un elemento visto en pantalla, dice qué hace.

    Usado por el explorador de broker: cuando detecta 'SUBE', 'bracket',
    etc., consulta aquí qué es y cómo se usa — así Litch no solo lo ve,
    entiende su función.
    """
    n = (nombre_ui or "").lower().strip()
    for alias, (br, clave) in _ALIAS_UI.items():
        if alias in n:
            return explicar(br, clave)
    return None


def buscar(pregunta: str, idioma: str = "es") -> str | None:
    """Búsqueda por palabras clave sobre el manual de los brokers.

    Se integra con el cerebro: preguntas como '¿cómo funciona el bracket?'
    o '¿qué es el trailing stop?' se responden desde aquí.
    """
    q = (pregunta or "").lower()
    resultados = []

    # ¿Menciona un broker específico?
    quiere_iq   = any(w in q for w in ("iq option", "iqoption", "binaria",
                                       "binarias", "opcion", "opción"))
    quiere_ibkr = any(w in q for w in ("ibkr", "interactive", "broker real",
                                       "tws", "acciones", "orden"))

    for broker, fuente in (("iq", IQ_OPTION), ("ibkr", IBKR)):
        for clave, d in fuente.items():
            texto = f"{clave} {d['que_es']} {d['como_usar']} {d['cuando']}".lower()
            # coincidencia por palabra clave de la pregunta
            palabras = [w for w in q.replace("¿", " ").replace("?", " ").split()
                        if len(w) > 3]
            if any(p in texto or p in clave for p in palabras):
                resultados.append((broker, clave, d))

    if not resultados:
        return None

    # Priorizar el broker mencionado
    if quiere_iq and not quiere_ibkr:
        resultados = [r for r in resultados if r[0] == "iq"] or resultados
    elif quiere_ibkr and not quiere_iq:
        resultados = [r for r in resultados if r[0] == "ibkr"] or resultados

    cab = "Del manual de funciones de los brokers, señor:\n\n"
    return cab + "\n\n".join(_fmt(c, d) for _, c, d in resultados[:4])


def resumen_capacidades(idioma: str = "es") -> str:
    """Lista lo que Litch sabe usar de cada broker (para '¿qué sabes hacer?')."""
    iq   = ", ".join(k.replace("_", " ") for k in IQ_OPTION)
    ibkr = ", ".join(k.replace("_", " ") for k in IBKR)
    return (f"Sé usar estas funciones de IQ Option: {iq}. "
            f"Y de Interactive Brokers: {ibkr}. "
            "Pregúnteme por cualquiera y le explico qué es, cómo se usa, "
            "cuándo y su regla de seguridad.")
