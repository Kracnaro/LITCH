"""
conocimiento_trading.py — Base de conocimiento profesional de trading para Litch.

Cubre: scalping, price action, velas japonesas, sesiones NYSE/Forex, bulls/bears,
       stops, gestión de riesgo, TradingView, estrategias reales.

Este módulo NO ejecuta trades — es el "cerebro académico" de Litch.
Se consulta desde cerebro.py para responder preguntas de trading con profundidad
profesional, igual que un trader institucional con años de experiencia.
"""

# ── SESIONES DEL MERCADO ───────────────────────────────────────────────────────

SESIONES = {
    "tokyo": {
        "nombre": "Sesión Asiática / Tokio",
        "horario_utc": "00:00 – 09:00",
        "horario_et":  "19:00 – 04:00",
        "caracteristicas": [
            "Baja volatilidad — ideal para rangos y acumulación.",
            "Pares AUD/JPY, USD/JPY y NZD/USD son los más activos.",
            "Muchos traders usan esta sesión para colocar órdenes pendientes.",
            "Evitar scalping agresivo; los spreads suelen ser más amplios.",
        ],
        "mejor_para": "Rangos, acumulación, preparar órdenes para Londres.",
    },
    "london": {
        "nombre": "Sesión Londres / Europa",
        "horario_utc": "08:00 – 17:00",
        "horario_et":  "03:00 – 12:00",
        "caracteristicas": [
            "Mayor volumen del mundo — 35% del mercado Forex.",
            "Rompe los rangos formados en Asia con fuerza.",
            "Tendencias claras: ideal para seguimiento de tendencia.",
            "Pares EUR/USD, GBP/USD, EUR/GBP dominan.",
            "Las primeras 2 horas (08:00-10:00 UTC) son las más explosivas.",
        ],
        "mejor_para": "Breakouts, tendencias, scalping con momentum.",
    },
    "nueva_york": {
        "nombre": "Sesión Nueva York / NYSE",
        "horario_utc": "13:00 – 22:00",
        "horario_et":  "09:30 – 17:00",
        "apertura":     "09:30 ET — alta volatilidad, momentum plays",
        "primera_hora": "09:30–10:30 ET — 'Power Hour', mayor oportunidad del día",
        "almuerzo":     "12:00–14:00 ET — baja liquidez, EVITAR scalping",
        "cierre":       "15:00–16:00 ET — reposicionamiento institucional, fuertes movimientos",
        "caracteristicas": [
            "Superpone con Londres 13:00-17:00 UTC — MEJOR MOMENTO para scalping.",
            "Noticias económicas USA mueven el mercado bruscamente.",
            "NYSE: acciones, ETFs, índices (SPY, QQQ, AAPL, TSLA).",
            "La apertura (09:30 ET) tiene el mayor volumen del día.",
            "Los primeros 30 min son de 'descubrimiento de precio' — alto riesgo.",
        ],
        "mejor_para": "Scalping de acciones, seguimiento de noticias, momentum.",
    },
    "solapamiento_ldn_ny": {
        "nombre": "Solapamiento Londres – Nueva York",
        "horario_utc": "13:00 – 17:00",
        "horario_et":  "09:00 – 13:00",
        "descripcion":  (
            "La ventana más poderosa del día. Ambas sesiones activas = máxima liquidez. "
            "Los movimientos más grandes del Forex ocurren aquí. "
            "Ideal para scalping con confirmación, breakouts y reversals."
        ),
    },
}

# ── TERMINOLOGÍA BULLS & BEARS ─────────────────────────────────────────────────

TOROS_Y_OSOS = {
    "bull_market": (
        "Mercado alcista sostenido. Precio sube >20% desde un mínimo. "
        "Confianza alta, economía fuerte. Ideal para compras (LONG)."
    ),
    "bear_market": (
        "Mercado bajista sostenido. Precio cae >20% desde un máximo. "
        "Miedo, incertidumbre. Ideal para ventas (SHORT) o esperar al piso."
    ),
    "bull_trap": (
        "Trampa alcista. El precio rompe una resistencia al alza, atrayendo compradores, "
        "pero inmediatamente regresa. Los osos venden la falsa ruptura."
    ),
    "bear_trap": (
        "Trampa bajista. El precio rompe un soporte a la baja, forzando stop-loss, "
        "pero rebota inmediatamente. Los toros compran el fakeout."
    ),
    "dead_cat_bounce": (
        "Rebote del gato muerto. Recuperación temporal en un mercado bajista. "
        "No indica reversión — el precio continúa bajando después."
    ),
    "bull_run": "Rally sostenido y acelerado al alza. Máximo momentum comprador.",
    "short_squeeze": (
        "Vendedores en corto se ven forzados a cerrar posiciones porque el precio sube, "
        "lo que acelera aún más la subida. Muy violento (ej: GME 2021)."
    ),
    "capitulation": (
        "Capitulación. Pánico masivo de vendedores al final de un bear market. "
        "Velas largas bajistas con volumen extremo. Señal de posible fondo."
    ),
    "rally": "Movimiento alcista fuerte y rápido desde un soporte o mínimo.",
    "correction": (
        "Corrección. Caída del 10-20% dentro de un bull market. "
        "Normal y sana. No confundir con cambio de tendencia."
    ),
    "consolidation": (
        "Consolidación. El precio se mueve lateralmente después de una tendencia. "
        "Los institucionales acumulan o distribuyen posiciones."
    ),
    "fomo": (
        "Fear Of Missing Out. Comprar por miedo a perderse el movimiento, "
        "generalmente en máximos. Error común de novatos."
    ),
    "fud": (
        "Fear, Uncertainty, Doubt. Noticias negativas que crean pánico vendedor. "
        "Los institucionales suelen comprar durante el FUD."
    ),
    "long": "Posición compradora. Apuestas a que el precio sube.",
    "short": "Posición vendedora. Apuestas a que el precio baja.",
    "margin": (
        "Margen. Capital prestado por el broker para operar con apalancamiento. "
        "Amplifica ganancias y pérdidas. Usar con disciplina estricta."
    ),
    "margin_call": (
        "Llamada de margen. El broker exige más fondos porque las pérdidas "
        "consumen el margen disponible. Si no depositas, cierra tu posición."
    ),
    "liquidity": (
        "Liquidez. Facilidad para comprar/vender sin mover el precio. "
        "Alta liquidez = spreads bajos, ejecución rápida. Los institucionales "
        "buscan zonas de liquidez para entrar y salir."
    ),
    "smart_money": (
        "Dinero inteligente. Instituciones, bancos, fondos de cobertura. "
        "Mueven el mercado. El objetivo del trader minorista es seguirlos, "
        "no ir en contra."
    ),
    "dumb_money": (
        "Dinero tonto (retail). Traders minoristas que generalmente pierden "
        "porque operan con emociones y tarde en las tendencias."
    ),
    "stop_hunt": (
        "Caza de stops. Los institucionales mueven el precio brevemente "
        "para activar los stop-loss de los minoristas, luego revierten. "
        "Reconocerlos evita pérdidas innecesarias."
    ),
}

# ── VELAS JAPONESAS — PATRONES Y SIGNIFICADOS ──────────────────────────────────

VELAS = {
    # ── SIMPLES ────────────────────────────────────────────────────────────────
    "doji": {
        "tipo": "simple",
        "señal": "indecision",
        "descripcion": (
            "Apertura y cierre casi iguales. Cuerpo diminuto. "
            "Indica equilibrio entre compradores y vendedores. "
            "En tendencia = posible reversión. En rango = sin relevancia."
        ),
        "accion": "Esperar confirmación de la siguiente vela antes de entrar.",
    },
    "doji_libelula": {
        "tipo": "simple", "señal": "bullish",
        "descripcion": (
            "Sombra inferior muy larga, sin sombra superior, cuerpo en el tope. "
            "Compradores rechazaron fuertemente los mínimos. "
            "Señal alcista en soporte o fondo de tendencia bajista."
        ),
        "accion": "Compra si aparece en soporte con confirmación alcista.",
    },
    "doji_lapida": {
        "tipo": "simple", "señal": "bearish",
        "descripcion": (
            "Sombra superior muy larga, sin sombra inferior, cuerpo en la base. "
            "Vendedores rechazaron fuertemente los máximos. "
            "Señal bajista en resistencia o techo de tendencia alcista."
        ),
        "accion": "Venta si aparece en resistencia con confirmación bajista.",
    },
    "martillo": {
        "tipo": "simple", "señal": "bullish",
        "descripcion": (
            "Cuerpo pequeño en el tope, sombra inferior larga (≥2x el cuerpo). "
            "Los vendedores empujaron el precio abajo pero los compradores "
            "recuperaron el control. Señal alcista en fondo de tendencia."
        ),
        "accion": "Compra sobre el máximo del martillo con volumen confirmatorio.",
    },
    "martillo_invertido": {
        "tipo": "simple", "señal": "bullish_potential",
        "descripcion": (
            "Cuerpo pequeño en la base, sombra superior larga. En fondo de tendencia. "
            "Los compradores intentaron subir pero fueron controlados; "
            "sin embargo la presión compradora es visible."
        ),
        "accion": "Requiere confirmación alcista en la siguiente vela.",
    },
    "hombre_colgado": {
        "tipo": "simple", "señal": "bearish",
        "descripcion": (
            "Igual que el martillo pero aparece en un máximo de tendencia alcista. "
            "Los vendedores entraron con fuerza intradiaria. "
            "Señal de posible reversión bajista."
        ),
        "accion": "Venta si la siguiente vela confirma dirección bajista.",
    },
    "estrella_fugaz": {
        "tipo": "simple", "señal": "bearish",
        "descripcion": (
            "Cuerpo pequeño en la base, sombra superior larga. Aparece en máximos. "
            "Los compradores perdieron el control. "
            "Los vendedores empujaron el precio hacia abajo desde máximos."
        ),
        "accion": "Venta bajo el mínimo de la estrella fugaz.",
    },
    "marubozu_alcista": {
        "tipo": "simple", "señal": "bullish_strong",
        "descripcion": (
            "Vela verde con cuerpo grande, sin sombras o casi sin ellas. "
            "Dominio absoluto de compradores desde apertura hasta cierre. "
            "Señal de momentum alcista fuerte."
        ),
        "accion": "Compra en retroceso o breakout confirmado.",
    },
    "marubozu_bajista": {
        "tipo": "simple", "señal": "bearish_strong",
        "descripcion": (
            "Vela roja con cuerpo grande, sin sombras. "
            "Dominio absoluto de vendedores. "
            "Señal de momentum bajista fuerte."
        ),
        "accion": "Venta en rebote o breakdown confirmado.",
    },
    "spinning_top": {
        "tipo": "simple", "señal": "indecision",
        "descripcion": (
            "Cuerpo pequeño con sombras largas en ambos lados. "
            "Igual que el Doji pero con algo de movimiento. "
            "Indecisión — ni toros ni osos ganan."
        ),
        "accion": "Esperar. No operar en indecisión.",
    },

    # ── DOBLES ─────────────────────────────────────────────────────────────────
    "engulfing_alcista": {
        "tipo": "doble", "señal": "bullish_strong",
        "descripcion": (
            "Vela roja seguida de una vela verde que la envuelve completamente. "
            "Los compradores tomaron el control total. "
            "Señal de reversión alcista muy fiable en soportes."
        ),
        "accion": "Compra sobre el máximo de la segunda vela. Stop bajo el mínimo.",
    },
    "engulfing_bajista": {
        "tipo": "doble", "señal": "bearish_strong",
        "descripcion": (
            "Vela verde seguida de una vela roja que la envuelve completamente. "
            "Los vendedores tomaron el control total. "
            "Señal de reversión bajista muy fiable en resistencias."
        ),
        "accion": "Venta bajo el mínimo de la segunda vela. Stop sobre el máximo.",
    },
    "harami_alcista": {
        "tipo": "doble", "señal": "bullish",
        "descripcion": (
            "Vela roja grande seguida de vela pequeña contenida en el cuerpo anterior. "
            "La momentum bajista se está agotando. "
            "Menos poderosa que el Engulfing."
        ),
        "accion": "Compra con confirmación de tercera vela alcista.",
    },
    "harami_bajista": {
        "tipo": "doble", "señal": "bearish",
        "descripcion": (
            "Vela verde grande seguida de vela pequeña contenida en el cuerpo anterior. "
            "El momentum alcista se está agotando."
        ),
        "accion": "Venta con confirmación de tercera vela bajista.",
    },
    "nube_oscura": {
        "tipo": "doble", "señal": "bearish",
        "descripcion": (
            "Vela verde seguida de vela roja que abre sobre el máximo y cierra "
            "por encima del 50% del cuerpo verde anterior. "
            "Los vendedores están ganando terreno."
        ),
        "accion": "Venta si la tercera vela confirma la debilidad.",
    },
    "piercing": {
        "tipo": "doble", "señal": "bullish",
        "descripcion": (
            "Vela roja seguida de vela verde que abre bajo el mínimo y cierra "
            "sobre el 50% del cuerpo rojo anterior. "
            "Los compradores están recuperando terreno."
        ),
        "accion": "Compra si la tercera vela confirma la fortaleza.",
    },

    # ── TRIPLES ────────────────────────────────────────────────────────────────
    "estrella_de_la_manana": {
        "tipo": "triple", "señal": "bullish_strong",
        "descripcion": (
            "1) Vela roja grande. 2) Doji o vela pequeña con gap abajo. "
            "3) Vela verde grande que recupera >50% de la primera. "
            "Uno de los patrones de reversión alcista más fiables."
        ),
        "accion": "Compra al cierre de la tercera vela. Stop bajo el mínimo del Doji.",
    },
    "estrella_de_la_tarde": {
        "tipo": "triple", "señal": "bearish_strong",
        "descripcion": (
            "1) Vela verde grande. 2) Doji o vela pequeña con gap arriba. "
            "3) Vela roja grande que cae >50% de la primera. "
            "Patrón de reversión bajista muy fiable."
        ),
        "accion": "Venta al cierre de la tercera vela. Stop sobre el máximo del Doji.",
    },
    "tres_soldados_blancos": {
        "tipo": "triple", "señal": "bullish_strong",
        "descripcion": (
            "Tres velas verdes consecutivas, cada una abriendo dentro del cuerpo "
            "anterior y cerrando más alto. Momentum alcista fuerte y sostenido."
        ),
        "accion": "Compra en retroceso o seguir la tendencia.",
    },
    "tres_cuervos_negros": {
        "tipo": "triple", "señal": "bearish_strong",
        "descripcion": (
            "Tres velas rojas consecutivas, cada una abriendo dentro del cuerpo "
            "anterior y cerrando más bajo. Momentum bajista fuerte y sostenido."
        ),
        "accion": "Venta en rebote o seguir la tendencia.",
    },
    "tres_inside_up": {
        "tipo": "triple", "señal": "bullish",
        "descripcion": (
            "1) Vela roja grande. 2) Vela pequeña contenida (Harami). "
            "3) Vela verde que cierra sobre el máximo de la primera. "
            "Reversión alcista confirmada."
        ),
        "accion": "Compra al cierre de la tercera vela.",
    },
    "tres_inside_down": {
        "tipo": "triple", "señal": "bearish",
        "descripcion": (
            "1) Vela verde grande. 2) Vela pequeña contenida (Harami). "
            "3) Vela roja que cierra bajo el mínimo de la primera. "
            "Reversión bajista confirmada."
        ),
        "accion": "Venta al cierre de la tercera vela.",
    },
}

# ── PRICE ACTION — CONCEPTOS AVANZADOS ────────────────────────────────────────

PRICE_ACTION = {
    "soporte": (
        "Nivel de precio donde la demanda es suficientemente fuerte para "
        "detener o revertir una caída. Los compradores defienden este nivel. "
        "Cuanto más veces fue testeado sin romperse, más fuerte es."
    ),
    "resistencia": (
        "Nivel de precio donde la oferta es suficientemente fuerte para "
        "detener o revertir una subida. Los vendedores defienden este nivel. "
        "Un soporte roto se convierte en resistencia y viceversa."
    ),
    "tendencia_alcista": (
        "Sucesión de máximos más altos (HH: Higher Highs) y mínimos más altos "
        "(HL: Higher Lows). Operar LONG en cada retroceso al HL es la estrategia."
    ),
    "tendencia_bajista": (
        "Sucesión de máximos más bajos (LH: Lower Highs) y mínimos más bajos "
        "(LL: Lower Lows). Operar SHORT en cada rebote al LH es la estrategia."
    ),
    "bos": (
        "Break of Structure (Ruptura de estructura). El precio rompe el último "
        "máximo relevante (alcista) o el último mínimo relevante (bajista). "
        "Confirma que la tendencia continúa."
    ),
    "choch": (
        "Change of Character (Cambio de carácter). El precio rompe en dirección "
        "OPUESTA a la tendencia actual. Primera señal de posible reversión. "
        "No confirma el cambio solo — requiere estructura adicional."
    ),
    "order_block": (
        "Order Block (Bloque de órdenes). Última vela (o grupo) antes de un "
        "movimiento impulsivo grande. Zona donde los institucionales dejaron "
        "órdenes pendientes. Precio suele regresar para 'llenarlas' antes de continuar."
    ),
    "fair_value_gap": (
        "Fair Value Gap / Imbalance. Gap de 3 velas donde la segunda sube o baja "
        "tan rápido que deja un vacío de liquidez. El precio tiende a regresar "
        "para llenar ese vacío (Fill the gap). Muy usado en SMC / ICT."
    ),
    "supply_zone": (
        "Zona de oferta. Área de precio donde los institucionales tienen "
        "órdenes de venta masivas. El precio rebota repetidamente desde arriba. "
        "Equivale a la resistencia en terminología clásica."
    ),
    "demand_zone": (
        "Zona de demanda. Área donde los institucionales tienen órdenes de compra "
        "masivas. El precio rebota repetidamente desde abajo. "
        "Equivale al soporte en terminología clásica."
    ),
    "liquidity_grab": (
        "Captura de liquidez. El precio barre brevemente los stop-loss de los "
        "traders minoristas (por debajo del soporte o sobre la resistencia) "
        "y regresa. Los institucionales usan esta liquidez para llenar sus órdenes."
    ),
    "fibonacci": (
        "Retrocesos de Fibonacci. Niveles clave: 23.6%, 38.2%, 50%, 61.8% (golden), 78.6%. "
        "El 61.8% es el retroceso más respetado — zona de entrada en tendencia. "
        "Trazar desde el swing low hasta el swing high (o viceversa)."
    ),
    "confluencia": (
        "Confluencia. Dos o más señales técnicas apuntan al mismo nivel de precio. "
        "Ejemplo: Fibonacci 61.8% + Order Block + Soporte horizontal = entrada de alta probabilidad. "
        "Más confluencias = mayor probabilidad de éxito."
    ),
    "estructura_mercado": (
        "Estructura del mercado. La lectura de HH/HL (alcista) y LH/LL (bajista) "
        "en múltiples marcos temporales (multi-timeframe analysis). "
        "Siempre operar EN LÍNEA con la estructura del timeframe mayor."
    ),
}

# ── ESCALPING — ESTRATEGIAS COMPLETAS ─────────────────────────────────────────

SCALPING = {
    "ema_scalping": {
        "nombre": "EMA Scalping (Cruce de medias rápidas)",
        "timeframe": "M1, M5",
        "indicadores": ["EMA 9", "EMA 21", "EMA 50", "Volumen"],
        "reglas_entrada_long": [
            "EMA 9 cruza sobre EMA 21 (cruce dorado).",
            "Precio por encima de EMA 50 (filtro de tendencia).",
            "Volumen superior al promedio de 20 períodos.",
            "Entrar en el primer retroceso a la EMA 9 después del cruce.",
        ],
        "reglas_entrada_short": [
            "EMA 9 cruza bajo EMA 21 (cruce muerto).",
            "Precio por debajo de EMA 50.",
            "Volumen superior al promedio.",
            "Entrar en rebote a la EMA 9.",
        ],
        "stop_loss": "3-5 pips / 0.3% bajo el último swing low (long) o sobre el swing high (short).",
        "take_profit": "1:1.5 a 1:2 ratio riesgo-beneficio.",
        "notas": "Mejor en sesión Londres o solapamiento NY. Evitar en rangos laterales.",
    },
    "rsi_scalping": {
        "nombre": "RSI Scalping (Sobrecompra/Sobreventa)",
        "timeframe": "M5, M15",
        "indicadores": ["RSI 14", "EMA 200 (tendencia)"],
        "reglas_entrada_long": [
            "RSI cae bajo 30 (sobreventa).",
            "Precio por encima de EMA 200 (tendencia alcista mayor).",
            "RSI regresa sobre 30 — señal de entrada.",
            "Confirmación con vela verde de reversión (martillo/engulfing).",
        ],
        "reglas_entrada_short": [
            "RSI sube sobre 70 (sobrecompra).",
            "Precio por debajo de EMA 200.",
            "RSI regresa bajo 70 — señal de entrada.",
            "Confirmación con vela roja de reversión.",
        ],
        "stop_loss": "Bajo el mínimo del swing de sobreventa (long) o sobre el máximo (short).",
        "take_profit": "Al siguiente nivel de resistencia/soporte o cuando RSI llega a 50.",
        "notas": "Funciona mejor en mercados con rangos definidos.",
    },
    "bollinger_scalping": {
        "nombre": "Bollinger Bands Scalping",
        "timeframe": "M5, M15",
        "indicadores": ["Bollinger Bands (20, 2)", "RSI 14", "Volumen"],
        "estrategias": {
            "squeeze": (
                "Cuando las bandas se comprimen mucho (volatilidad baja), "
                "se prepara un movimiento explosivo. Esperar la ruptura + "
                "confirmar con volumen para entrar en la dirección."
            ),
            "bounce": (
                "En rango: comprar en banda inferior + RSI <35. "
                "Vender en banda superior + RSI >65. "
                "Stop: fuera de la banda."
            ),
            "riding_the_band": (
                "En tendencia fuerte: el precio 'camina' por la banda exterior. "
                "Mantener la posición mientras el precio no cierre dentro."
            ),
        },
        "notas": "El 'squeeze' es la señal de Bollinger más poderosa para scalping.",
    },
    "macd_scalping": {
        "nombre": "MACD Scalping",
        "timeframe": "M5, M15",
        "indicadores": ["MACD (12, 26, 9)", "EMA 50"],
        "reglas": [
            "MACD cruza sobre la línea de señal (alcista) → LONG.",
            "MACD cruza bajo la línea de señal (bajista) → SHORT.",
            "Filtro: solo operar en la dirección de la EMA 50.",
            "El histograma aumentando en la dirección del trade = confirmación extra.",
        ],
        "notas": "Combinar con niveles de soporte/resistencia para mayor fiabilidad.",
    },
    "scalping_apertura_ny": {
        "nombre": "Scalping Apertura NYSE (09:30-10:30 ET)",
        "timeframe": "M1, M5",
        "descripcion": (
            "La apertura de NYSE es el momento de mayor volatilidad. "
            "En los primeros 15 minutos el precio 'descubre' su dirección. "
            "Estrategia: esperar los primeros 15 min, identificar el rango, "
            "operar el breakout de ese rango con volumen."
        ),
        "reglas": [
            "09:30-09:45 ET: OBSERVAR, no entrar. Dejar que el mercado muestre la dirección.",
            "09:45-10:30 ET: Operar el breakout del rango de los primeros 15 min.",
            "Confirmar con volumen superior al promedio del día anterior.",
            "Stop bajo el mínimo del rango (long) o sobre el máximo (short).",
            "Target: el rango proyectado en la dirección del breakout.",
        ],
        "notas": "Altísima probabilidad si se respetan los 15 min de espera.",
    },
    "scalping_vwap": {
        "nombre": "VWAP Scalping",
        "timeframe": "M1, M5, M15",
        "indicadores": ["VWAP (Volume Weighted Average Price)", "Volumen"],
        "descripcion": (
            "El VWAP es el precio promedio ponderado por volumen del día. "
            "Es la referencia que usan los institucionales. "
            "El precio tiende a regresar al VWAP como imán."
        ),
        "reglas": [
            "LONG: Precio cae al VWAP desde arriba + rebota + volumen comprador → Compra.",
            "SHORT: Precio sube al VWAP desde abajo + rechaza + volumen vendedor → Venta.",
            "En tendencia fuerte alcista: comprar cada pullback al VWAP.",
            "Si el precio está lejos del VWAP → alta probabilidad de regreso (mean reversion).",
        ],
        "notas": "El VWAP se resetea cada día. Muy usado en acciones NYSE/NASDAQ.",
    },
    "liquidity_sweep_scalping": {
        "nombre": "Scalping de Captura de Liquidez (SMC/ICT)",
        "timeframe": "M1, M5, M15",
        "descripcion": (
            "Los institucionales mueven el precio para capturar la liquidez "
            "(stop-loss) de los minoristas antes de ir en la dirección real. "
            "Identificar este sweep y operar la reversión."
        ),
        "reglas": [
            "Identificar máximos/mínimos previos donde están los stops (liquidez).",
            "Cuando el precio barre brevemente esos niveles con una vela de pico (wick larga).",
            "Entrar en la dirección opuesta cuando el precio regresa al rango.",
            "Stop: justo más allá del sweep (1-3 pips/ticks).",
            "Target: el siguiente nivel significativo de la estructura.",
        ],
        "notas": (
            "Estrategia de Smart Money Concepts (SMC). Alta probabilidad. "
            "Latino Wall Street y ICT la enseñan extensamente."
        ),
    },
}

# ── MÉTODOS DE STOP LOSS ───────────────────────────────────────────────────────

STOP_METHODS = {
    "fijo_porcentaje": {
        "nombre": "Stop Fijo por Porcentaje",
        "descripcion": "Stop colocado a X% del precio de entrada. Nunca arriesgar más del 1-2% de la cuenta por trade.",
        "formula": "Stop = Precio_entrada × (1 - riesgo_pct)  [para LONG]",
        "ventaja": "Simple, consistente, fácil de calcular.",
        "desventaja": "No respeta la estructura del mercado.",
    },
    "estructura": {
        "nombre": "Stop por Estructura de Mercado",
        "descripcion": (
            "Stop colocado bajo el último mínimo relevante (LONG) "
            "o sobre el último máximo relevante (SHORT). "
            "El más profesional — respeta la lógica del mercado."
        ),
        "regla": "Si el precio invalida la estructura, la tesis de trade es incorrecta → salir.",
        "ventaja": "Lógicamente justificado. Reduce whipsaws.",
        "desventaja": "Puede ser amplio en mercados volátiles.",
    },
    "atr": {
        "nombre": "Stop por ATR (Average True Range)",
        "descripcion": (
            "Stop = Precio_entrada - (ATR × multiplicador). "
            "Multiplicador típico: 1.5x a 2.5x. "
            "Se adapta automáticamente a la volatilidad del mercado."
        ),
        "formula": "Stop_LONG = Entrada - (ATR14 × 1.5)",
        "ventaja": "Dinámico, se ajusta a la volatilidad real.",
        "desventaja": "Requiere cálculo o indicador.",
    },
    "trailing": {
        "nombre": "Trailing Stop (Stop Seguidor)",
        "descripcion": (
            "El stop sigue al precio en la dirección del trade a una distancia fija. "
            "Permite dejar correr las ganancias ilimitadamente "
            "mientras protege lo ganado."
        ),
        "tipos": [
            "Trailing fijo: distancia fija en pips/puntos.",
            "Trailing ATR: distancia = ATR × multiplicador, se recalcula.",
            "Trailing por swing: se mueve al siguiente mínimo/máximo confirmado.",
        ],
        "ventaja": "Protege ganancias, elimina decisiones emocionales de salida.",
        "desventaja": "Puede salirte antes en correcciones normales.",
    },
    "breakeven": {
        "nombre": "Break-even Stop",
        "descripcion": (
            "Cuando el trade llega a +1R de ganancia, mover el stop al precio de entrada (0 pérdida). "
            "Convierte el trade en 'gratis' — solo puede ganar desde ahí."
        ),
        "regla": "Al alcanzar +1R, mover stop a breakeven. Al alcanzar +2R, mover a +1R.",
        "ventaja": "Elimina el riesgo de pérdida una vez ejecutado.",
    },
    "tiempo": {
        "nombre": "Stop por Tiempo",
        "descripcion": (
            "Salir del trade si no se mueve en X tiempo, independientemente del P&L. "
            "Si el precio no responde como esperabas en el tiempo previsto, la tesis era incorrecta."
        ),
        "uso": "Scalping: si en 5-15 min el trade no se mueve, cerrar.",
        "ventaja": "Evita trades 'dormidos' que consumen capital mental.",
    },
}

# ── GESTIÓN DE RIESGO ─────────────────────────────────────────────────────────

GESTION_RIESGO = {
    "regla_1_pct": (
        "Regla del 1%. Nunca arriesgar más del 1% de la cuenta en un trade. "
        "Con 1000 USD → máximo riesgo 10 USD por trade. "
        "Esto permite sobrevivir 100 pérdidas consecutivas."
    ),
    "regla_2_pct": (
        "Regla del 2%. Máximo 2% de la cuenta por trade. "
        "Estándar para traders con experiencia media. "
        "Con 10,000 USD → máximo riesgo 200 USD por trade."
    ),
    "rr_minimo": (
        "Ratio Riesgo/Beneficio mínimo 1:2. "
        "Si arriesgas $100, solo entrar si el target es ≥ $200. "
        "Con 50% de aciertos y 1:2 RR → sistema rentable."
    ),
    "perdida_diaria": (
        "Límite de pérdida diaria (Daily Max Loss). "
        "Si pierdes 3-5% de la cuenta en un día, PARAR. "
        "Protege de revenge trading y días destructivos."
    ),
    "revenge_trading": (
        "Revenge trading. Operar para recuperar pérdidas de forma impulsiva. "
        "La causa #1 de cuentas destruidas. "
        "Regla: si pierdes 2 trades seguidos, descansar 1 hora mínimo."
    ),
    "tamanio_posicion": (
        "Cálculo de tamaño de posición: "
        "Unidades = (Capital × Riesgo_pct) / (Stop_pips × Valor_pip). "
        "Siempre calcular ANTES de entrar al trade."
    ),
    "diversificacion": (
        "No concentrar más del 20% del capital en correlaciones similares. "
        "EUR/USD y GBP/USD se mueven similar — tener ambos no diversifica."
    ),
    "winrate_minimo": (
        "Con RR 1:2, necesitas solo 34% de win rate para ser rentable. "
        "Con RR 1:3, solo el 26%. "
        "Un sistema con 40-50% win rate y RR 1:2 es un sistema EXCELENTE."
    ),
}

# ── INDICADORES TÉCNICOS CLAVE ─────────────────────────────────────────────────

INDICADORES = {
    "ema": (
        "Exponential Moving Average (Media Móvil Exponencial). "
        "Da más peso a los precios recientes. "
        "EMA 9/21: scalping. EMA 50: tendencia media. EMA 200: tendencia mayor. "
        "Precio sobre EMA 200 → tendencia alcista de largo plazo."
    ),
    "rsi": (
        "Relative Strength Index (0-100). "
        "<30 = sobreventa (potencial compra). >70 = sobrecompra (potencial venta). "
        "Divergencia RSI vs precio = señal poderosa de reversión."
    ),
    "macd": (
        "Moving Average Convergence Divergence. "
        "Cruce de líneas: señal de momentum. Histograma: fuerza del momentum. "
        "Divergencia MACD vs precio = reversión probable."
    ),
    "bollinger_bands": (
        "Bandas de Bollinger (20 períodos, 2 desviaciones estándar). "
        "Precio en banda superior = sobrecompra. Banda inferior = sobreventa. "
        "Squeeze (bandas juntas) = próximo movimiento explosivo."
    ),
    "vwap": (
        "Volume Weighted Average Price. El precio justo del día según volumen. "
        "Referencia institucional. Precio sobre VWAP = sesgo alcista del día. "
        "Se resetea cada día a las 00:00."
    ),
    "atr": (
        "Average True Range. Mide la volatilidad media del período. "
        "ATR alto = mercado volátil, stops más amplios. "
        "ATR bajo = mercado tranquilo, stops más ajustados."
    ),
    "volumen": (
        "El volumen confirma los movimientos de precio. "
        "Ruptura de nivel + volumen alto = movimiento real. "
        "Ruptura sin volumen = probable trampa (fakeout)."
    ),
    "stochastic": (
        "Stochastic Oscillator (0-100). Similar al RSI. "
        "<20 = sobreventa. >80 = sobrecompra. "
        "Cruce de K y D en zona extrema = señal de entrada."
    ),
    "ichimoku": (
        "Ichimoku Cloud. Muestra soporte, resistencia, tendencia y momentum en un indicador. "
        "Precio sobre la nube = alcista. Precio bajo la nube = bajista. "
        "La nube verde = soporte. La nube roja = resistencia."
    ),
}

# ── TRADINGVIEW — GUÍA PRÁCTICA ────────────────────────────────────────────────

TRADINGVIEW = {
    "descripcion": (
        "TradingView (tradingview.com) es la plataforma de análisis técnico "
        "más usada del mundo. Permite graficar cualquier activo (acciones, forex, "
        "crypto, futuros) con todos los indicadores técnicos disponibles. "
        "Tiene una versión gratuita muy completa y versiones Pro."
    ),
    "caracteristicas_clave": [
        "Gráficos en tiempo real de cualquier mercado global.",
        "Pine Script: lenguaje propio para crear indicadores y estrategias personalizadas.",
        "Alertas automáticas por precio, indicador o patrón.",
        "Ideas de trading de millones de traders (análisis compartidos).",
        "Screener de acciones/crypto/forex con filtros técnicos.",
        "Replay de mercado para practicar estrategias en histórico.",
        "Integración con brokers (Interactive Brokers, Alpaca, Coinbase, etc.).",
    ],
    "configuracion_recomendada": {
        "indicadores_basicos": ["EMA 9", "EMA 21", "EMA 50", "EMA 200", "VWAP", "Volumen"],
        "indicadores_avanzados": ["RSI 14", "MACD (12,26,9)", "Bollinger Bands (20,2)", "ATR 14"],
        "timeframes": "Analizar en H4/H1 para dirección, entrar en M15/M5.",
        "alertas": "Configurar alertas en niveles clave para no estar pegado a la pantalla.",
    },
    "atajos_teclado": {
        "Alt+1 a Alt+9": "Cambiar timeframe rápido.",
        "Alt+H": "Ver historial de alertas.",
        "Ctrl+Z": "Deshacer última acción en gráfico.",
        "/": "Buscar símbolo.",
        "Alt+S": "Snapshot (captura del gráfico).",
    },
    "screener_uso": (
        "El screener de TradingView permite filtrar activos por criterios técnicos. "
        "Ejemplo: 'Mostrar todas las acciones del NYSE donde RSI < 30 y precio sobre EMA 200'. "
        "Herramienta poderosa para encontrar oportunidades sin buscar manualmente."
    ),
}

# ── ESTRATEGIAS DE APERTURA Y CIERRE ──────────────────────────────────────────

PLANES_MERCADO = {
    "plan_diario": {
        "descripcion": "Rutina de preparación antes de operar cada día.",
        "pasos": [
            "1. Revisar el calendario económico (noticias del día).",
            "2. Analizar el mercado en H4/H1: ¿tendencia o rango?",
            "3. Identificar los niveles clave del día (soportes, resistencias, highs/lows previos).",
            "4. Definir: ¿en qué zona compraría? ¿en qué zona vendería?",
            "5. Calcular el tamaño de posición para no arriesgar más del 1-2%.",
            "6. Establecer las reglas de entrada con anticipación (no improvisar).",
            "7. Definir la pérdida máxima del día. Si se alcanza, parar.",
        ],
    },
    "estrategia_apertura_ny": {
        "descripcion": "Protocolo de apertura NYSE (09:30-10:30 ET).",
        "pasos": [
            "09:00-09:30 ET: Revisar pre-market. ¿Hay gaps? ¿En qué dirección abre?",
            "09:30-09:45 ET: SOLO OBSERVAR. No entrar. Identificar el rango de apertura.",
            "09:45 ET: Si hay breakout del rango con volumen → entrar en esa dirección.",
            "Target inicial: 1-2x el tamaño del rango de apertura.",
            "Stop: bajo el mínimo del rango (long) o sobre el máximo (short).",
        ],
    },
    "estrategia_cierre_ny": {
        "descripcion": "Protocolo de cierre NYSE (15:00-16:00 ET).",
        "pasos": [
            "15:00-15:30 ET: Los institucionales reposicionan. Alta volatilidad.",
            "Observar si el precio rompe máximos/mínimos del día en la última hora.",
            "MOC (Market On Close): las órdenes institucionales se ejecutan al cierre.",
            "15:45-16:00 ET: Reducir tamaño o cerrar posiciones abiertas del día.",
            "Evitar mantener posiciones volátiles durante el fin de semana.",
        ],
    },
    "swing_trading": {
        "descripcion": "Trades de 1-5 días, aprovechando movimientos de tendencia.",
        "entrada": "Retroceso al 50-61.8% Fibonacci en tendencia establecida.",
        "stop": "Bajo el swing low anterior (long) o sobre el swing high (short).",
        "target": "161.8% Fibonacci o siguiente zona de resistencia/soporte mayor.",
        "timeframe_analisis": "H4, Daily.",
        "timeframe_entrada": "H1, M30.",
    },
}

# ── LATINO WALL STREET — METODOLOGÍA ─────────────────────────────────────────

LATINO_WALL_STREET = {
    "quienes_son": (
        "Latino Wall Street es una PLATAFORMA EDUCATIVA de trading (no un broker). "
        "Fundada por Gabriela Berrospi y Tony Delgado. "
        "Aliado estratégico: Alan Burak, hedge fund manager en Manhattan (Never Alone Capital). "
        "Misión: democratizar los mercados financieros para hispanoparlantes."
    ),
    "cursos": {
        "Universidad de Wall Street": "$1,999 — Intro + avanzado, opciones, estrategias.",
        "Secretos de Day Trading": "$1,999 — Price action PURO sin indicadores.",
        "Secretos del Dinero Inteligente": "$1,999 — Scalping + day trading + SMC institucional.",
        "Secretos del Trading Profesional": "$1,999 — Opciones financieras, swing, spreads.",
        "Scalping Bootcamp": "Scalping exclusivo — metodología acelerada.",
        "Programa Platino": "Alto ticket — acceso total + mentoring personalizado.",
        "Universidad LWS 12 meses": "$1,999+ — Programa guiado con clases en vivo diarias.",
    },
    "metodologias": [
        "Price Action PURO sin indicadores — entender la naturaleza del movimiento.",
        "Smart Money Concepts (SMC) — seguir el dinero institucional.",
        "Day Trading intradía.",
        "Scalping de corta duración.",
        "Swing Trading de días a semanas.",
        "Spreads con opciones financieras para ingreso consistente.",
        "El Gallo Mañanero — análisis pre-mercado diario (noticias + sesgo del día).",
    ],
    "herramientas": [
        "TradingView — plataforma principal de gráficos.",
        "Clases en vivo diarias.",
        "Comunidad privada de miembros.",
        "Análisis macro + técnico combinado.",
    ],
    "filosofia": (
        "Reducir la curva de aprendizaje. Evitar errores típicos del principiante. "
        "Combinar análisis técnico con contexto macroeconómico. "
        "Ingreso real y consistente — no especulación ciega."
    ),
    "gabriela_berrospi": (
        "Cofundadora. Más de 10 años en bolsa. Especialista en NYSE y opciones. "
        "Filosofía: 'El mercado no te da dinero, te lo cobra si no estás preparado.'"
    ),
    "alan_burak": (
        "Socio estratégico. Propietario de hedge fund en Manhattan (Never Alone Capital). "
        "Trader institucional. Enseña los secretos del Smart Money."
    ),
}

# ── BROKERS POPULARES EN LATAM ────────────────────────────────────────────────

BROKERS_LATAM = {
    "iq_option": {
        "tipo": "Opciones binarias / CFDs",
        "regulacion": "CySEC",
        "nota": "El más popular para opciones binarias en LATAM. Alta liquidez.",
        "payout": "Hasta 92% en demo, 80-85% en real.",
    },
    "exness": {
        "tipo": "Forex / CFDs",
        "regulacion": "FCA (UK), CySEC (EU)",
        "nota": "Muy popular en LATAM. Spreads bajos, retiros rápidos.",
    },
    "xm": {
        "tipo": "Forex / CFDs",
        "regulacion": "ASIC, CySEC",
        "nota": "Bono sin depósito. Popular para principiantes LATAM.",
    },
    "etoro": {
        "tipo": "Acciones reales / Crypto / CFDs",
        "regulacion": "FCA, CySEC, ASIC",
        "nota": "Copy trading — copia traders exitosos automáticamente.",
    },
    "interactive_brokers": {
        "tipo": "Acciones reales / Opciones financieras",
        "regulacion": "SEC, FINRA (USA)",
        "nota": "Para acciones reales en bolsa USA. El más regulado.",
    },
    "pepperstone": {
        "tipo": "Forex / CFDs",
        "regulacion": "ASIC, FCA",
        "nota": "Spreads muy bajos. Favorito de scalpers profesionales.",
    },
    "broker_express": {
        "tipo": "Sin categoría verificada",
        "regulacion": "No encontrado en registros internacionales (FCA, CySEC, ASIC).",
        "nota": "Verificar directamente su regulación antes de depositar.",
    },
}

# ── SMC / ICT — SMART MONEY CONCEPTS COMPLETO ────────────────────────────────

SMC_ICT = {
    "ciclo_amd": {
        "nombre": "Ciclo AMD — Accumulation, Manipulation, Distribution",
        "descripcion": (
            "El modelo institucional que explica cómo se mueven los mercados "
            "cada día. Creado por ICT (Inner Circle Trader)."
        ),
        "acumulacion": (
            "Sesión asiática. Rango estrecho. Los institucionales acumulan "
            "posiciones en silencio sin mostrar dirección."
        ),
        "manipulacion": (
            "Apertura Londres. Barre los extremos de Asia para activar stops retail. "
            "El precio parece ir en la dirección 'incorrecta' — es la trampa."
        ),
        "distribucion": (
            "Apertura Nueva York. Los institucionales ejecutan el movimiento real "
            "en la dirección opuesta a la manipulación. Ahí se opera."
        ),
        "uso": (
            "NO operar en acumulación (Asia). "
            "Identificar el sweep de manipulación en Londres. "
            "Entrar en la distribución (NY open) en la dirección real."
        ),
    },
    "market_maker_model": {
        "nombre": "Market Maker Model (MMM)",
        "patron": [
            "1. Consolidación en rango asiático.",
            "2. Sweep: barre liquidez del lado OPUESTO al movimiento real.",
            "3. CHoCH en M5/M15 — primer cambio de carácter.",
            "4. Retroceso a FVG u OB para entrada.",
            "5. BOS — confirmación de nueva tendencia.",
            "6. Extensión hacia pools de liquidez del lado contrario.",
        ],
    },
    "ote": {
        "nombre": "OTE — Optimal Trade Entry (ICT)",
        "descripcion": (
            "Zona de Fibonacci entre 61.8% y 78.6% de un retroceso. "
            "La zona de MAYOR PROBABILIDAD para entrar en pullback "
            "después de un BOS o CHoCH confirmado."
        ),
        "niveles": {
            "0.500": "Equilibrium — precio justo, punto medio del rango.",
            "0.618": "Golden Ratio — inicio de zona OTE.",
            "0.705": "Nivel ICT específico — centro de la zona OTE.",
            "0.786": "Final de zona OTE — retroceso profundo máximo válido.",
            "1.272": "Extensión 1 — primer objetivo de beneficio.",
            "1.618": "Extensión 2 — objetivo extendido.",
        },
        "uso": (
            "Después de BOS: medir el impulso desde el swing point hasta el BOS. "
            "Orden límite en zona 61.8%-78.6%. "
            "Stop bajo el 100% del retroceso. "
            "Target: extensión 1.272 o 1.618."
        ),
    },
    "premium_discount": {
        "nombre": "Premium vs Descuento",
        "descripcion": "El rango entre swing high y swing low dividido en 50%.",
        "discount": "Precio BAJO el 50% = zona de COMPRA (precio barato).",
        "premium": "Precio SOBRE el 50% = zona de VENTA (precio caro).",
        "equilibrium": "El 50% exacto = precio justo / indecisión.",
        "regla": (
            "Comprar en descuento. Vender en premium. "
            "Siempre alineado con el bias del timeframe mayor."
        ),
    },
    "breaker_block": {
        "nombre": "Breaker Block",
        "descripcion": (
            "Order Block invalidado que ahora actúa en dirección OPUESTA. "
            "OB bajista roto → actúa como soporte. "
            "OB alcista roto → actúa como resistencia."
        ),
        "uso": "Misma operativa que OB pero dirección invertida. Alta probabilidad en retesteos.",
    },
    "displacement": {
        "nombre": "Displacement (Desplazamiento Impulsivo)",
        "descripcion": (
            "Movimiento impulsivo fuerte que rompe estructura y crea FVGs. "
            "Señal de orden institucional grande. "
            "Después de displacement: buscar retroceso al FVG para entrada en la misma dirección."
        ),
    },
    "inducement": {
        "nombre": "Inducement (Inducción)",
        "descripcion": (
            "Movimiento falso que atrae a retail antes del movimiento real. "
            "El mercado 'induce' a entrar en la dirección equivocada. "
            "Esperar el sweep del inducement antes de entrar en la dirección correcta."
        ),
    },
    "killzones_latam": {
        "descripcion": "ICT Killzones — ventanas de mayor probabilidad institucional con horarios LATAM.",
        "asia_range": {
            "utc": "00:00-07:00",
            "colombia_mexico": "19:00-02:00",
            "argentina": "21:00-04:00",
            "accion": "Marcar high/low. NO operar. Son niveles de liquidez objetivo.",
        },
        "london_open": {
            "utc": "07:00-10:00",
            "colombia_mexico": "02:00-05:00",
            "argentina": "04:00-07:00",
            "tasa": "65-70%",
            "accion": "Buscar sweep del rango asiático + CHoCH para entrar.",
        },
        "ny_open": {
            "utc": "13:30-16:00",
            "colombia_mexico": "08:30-11:00",
            "argentina": "10:30-13:00",
            "tasa": "70-75%",
            "accion": "MEJOR MOMENTO. Scalping, day trading, todos los setups SMC.",
        },
        "london_close": {
            "utc": "15:00-17:00",
            "colombia_mexico": "10:00-12:00",
            "argentina": "12:00-14:00",
            "tasa": "60-65%",
            "accion": "Precaución: reversiones frecuentes. Reducir tamaño.",
        },
    },
    "london_sweep": {
        "nombre": "London Sweep + Reversal",
        "descripcion": "Londres barre extremos del rango asiático y luego revierte.",
        "pasos": [
            "1. Marcar high/low de sesión asiática.",
            "2. Esperar que Londres barre uno de los extremos.",
            "3. Si barre mínimo asiático y revierte → LONG.",
            "4. Si barre máximo asiático y revierte → SHORT.",
            "5. Entrada en FVG de la reversal.",
        ],
        "stop": "Detrás del extremo barrido.",
        "target": "Extremo opuesto del rango asiático.",
        "nota": "Uno de los setups más enseñados en Latino Wall Street.",
    },
    "fvg_entry": {
        "nombre": "FVG Entry (Entrada en Fair Value Gap)",
        "pasos": [
            "1. Identificar bias del día en H1/H4.",
            "2. Localizar FVG en M5/M15 alineado con bias.",
            "3. Orden límite al 50% del FVG.",
            "4. Stop bajo el FVG completo + 2 pips.",
            "5. Target: siguiente pool de liquidez.",
        ],
        "validacion": [
            "FVG formado durante killzone (no en Asia).",
            "FVG no mitigado previamente.",
            "Alineado con OB de H4 o Daily.",
        ],
        "ratio": "Mínimo 1:2, ideal 1:3.",
    },
}

# ── RESUMEN DE ESTRATEGIAS PARA RESPUESTA RÁPIDA ─────────────────────────────

ESTRATEGIAS_RESUMEN = """
ESTRATEGIAS DE TRADING PROFESIONAL — RESUMEN RITCH:

SCALPING (M1-M15):
• EMA 9/21 crossover + Volumen + EMA 50 como filtro
• VWAP bounce (comprar pullback al VWAP en tendencia)
• Liquidity sweep + reversión (captura de stops institucionales)
• Bollinger Bands squeeze breakout
• Apertura NYSE 09:45 ET breakout del rango de los primeros 15 min

PRICE ACTION AVANZADO:
• BOS (Break of Structure) = tendencia continúa
• ChoCH (Change of Character) = posible reversión
• Order Blocks = zonas de entrada de alta probabilidad
• FVG (Fair Value Gap) = imbalances que el precio llena
• Liquidity grab = caza de stops, operar la reversión

GESTIÓN DE RIESGO (OBLIGATORIO):
• Máximo 1-2% de cuenta por trade
• RR mínimo 1:2 (por cada $1 arriesgado, ganar $2)
• Límite diario de pérdida: 3-5% de la cuenta
• Stop siempre colocado ANTES de entrar

VELAS MÁS IMPORTANTES:
• Engulfing alcista/bajista = reversión fuerte
• Doji en extremos = indecisión, esperar confirmación
• Marubozu = momentum puro
• Estrella de la mañana/tarde = reversión de 3 velas

SESIONES ÓPTIMAS PARA SCALPING:
• Londres 08:00-10:00 UTC (primeras 2 horas)
• Solapamiento Londres-NY 13:00-17:00 UTC (MEJOR)
• Apertura NYSE 09:30-10:30 ET
• EVITAR: almuerzo NY (12:00-14:00 ET)
"""


# ── FUNCIÓN PRINCIPAL DE CONSULTA ─────────────────────────────────────────────

def buscar(pregunta: str, idioma: str = "es") -> str:
    """
    Responde preguntas de trading usando la base de conocimiento.
    Llamada desde cerebro.py cuando se detecta una pregunta de trading.
    """
    q = pregunta.lower()
    respuestas = []

    # Velas japonesas (excluir patrones chartistas que coinciden con "patron"/"patrón")
    _vela_excl = ("doble techo", "doble suelo", "triple techo", "triple suelo",
                  "cabeza y hombros", "cuña", "wedge", "broadening", "chartism")
    if any(x in q for x in ["vela", "candlestick", "doji", "martillo", "hammer",
                              "engulfing", "estrella", "marubozu", "harami",
                              "patrón", "patron"]) and not any(x in q for x in _vela_excl):
        for nombre, info in VELAS.items():
            if nombre.replace("_", " ") in q or nombre in q:
                señal_txt = {"bullish": "ALCISTA", "bearish": "BAJISTA",
                             "bullish_strong": "ALCISTA FUERTE",
                             "bearish_strong": "BAJISTA FUERTE",
                             "indecision": "INDECISIÓN"}.get(info["señal"], info["señal"])
                return (f"**{nombre.replace('_',' ').upper()}** ({señal_txt})\n"
                        f"{info['descripcion']}\n"
                        f"Acción: {info['accion']}")
        # Si pregunta genérica sobre velas
        tipos = [n.replace("_"," ") for n, i in VELAS.items() if i["tipo"]=="simple"]
        return (f"Conozco {len(VELAS)} patrones de velas japonesas. "
                f"Patrones simples clave: {', '.join(tipos[:6])}. "
                f"Pregúntame por uno específico para la descripción completa.")

    # Scalping (excluir queries XTB y Equiti — tienen sus propios bloques abajo)
    _xbt_excl = ("xtb", "gonzalo", "piramide", "pirámide", "natgas", "us100",
                  "activos para", "mejor activo",
                  "equiti", "ichimoku scalping", "ichimoku m1", "triple cruce")
    if any(x in q for x in ["scalp", "scalping", "entrada rápida", "m1", "m5"]) and not any(x in q for x in _xbt_excl):
        for nombre, info in SCALPING.items():
            if nombre.replace("_"," ") in q:
                return (f"**{info['nombre']}** ({info['timeframe']})\n"
                        f"Indicadores: {', '.join(info.get('indicadores',[]))}\n"
                        f"Notas: {info.get('notas','')}")
        estrategias = [v["nombre"] for v in SCALPING.values()]
        return ("Estrategias de scalping que manejo: " +
                " | ".join(estrategias) + ". "
                "Pregúntame por una específica para las reglas completas.")

    # Price action (excluir queries SMA 200 de Equiti que tienen "soporte"/"resistencia")
    _pa_excl = ("sma 200 universal", "sma 200 soporte", "sma 200 resistencia",
                "sma200 scalping", "media 200 universal")
    if any(x in q for x in ["price action", "acción de precio", "soporte", "resistencia",
                              "bos", "choch", "order block", "fvg", "estructura",
                              "tendencia", "fibonacci", "confluencia", "liquidez"]) and not any(x in q for x in _pa_excl):
        for clave, desc in PRICE_ACTION.items():
            if clave.replace("_"," ") in q or clave in q:
                return f"**{clave.replace('_',' ').upper()}**: {desc}"
        return ESTRATEGIAS_RESUMEN

    # Sesiones
    _sesion_excl = ("acciones wall street", "bolsa wall street", "trading acciones wall",
                    "derivados wall")
    if any(x in q for x in ["sesión", "sesion", "horario", "nueva york", "new york",
                              "nyse", "wall street", "london", "tokio", "tokyo", "apertura",
                              "cierre", "solapamiento", "overlap"]) and not any(x in q for x in _sesion_excl):
        for s in SESIONES.values():
            if any(x in q for x in [s["nombre"].lower(),
                                     s["horario_et"].split("–")[0].strip().lower()]):
                return (f"**{s['nombre']}** | UTC: {s['horario_utc']} | ET: {s['horario_et']}\n"
                        f"Mejor para: {s.get('mejor_para','')}\n"
                        f"{chr(10).join(s.get('caracteristicas',[]))}")
        return ("Sesiones del mercado Forex/NYSE:\n"
                "• Tokio: 00:00-09:00 UTC (baja volatilidad)\n"
                "• Londres: 08:00-17:00 UTC (mayor volumen Forex)\n"
                "• Nueva York/NYSE: 09:30-16:00 ET / 13:00-22:00 UTC\n"
                "• Solapamiento Londres-NY: 13:00-17:00 UTC — EL MEJOR MOMENTO\n"
                "• Apertura NYSE: 09:30-10:30 ET — máxima volatilidad")

    # Toros y osos / terminología
    if any(x in q for x in ["toro", "oso", "bull", "bear", "alcista", "bajista",
                              "smart money", "fomo", "short squeeze", "trampa"]):
        for clave, desc in TOROS_Y_OSOS.items():
            if clave.replace("_"," ") in q or clave in q:
                return f"**{clave.replace('_',' ').upper()}**: {desc}"
        terms = list(TOROS_Y_OSOS.keys())[:8]
        return ("Terminología Wall Street que conozco: " +
                ", ".join(t.replace("_"," ") for t in terms) +
                "... y más. Pregúntame por el término específico.")

    # Stops (excluir "patron"/"patrón" que contienen "atr" como subpalabra)
    _stop_excl = ("patron", "patrón", "patronal")
    if any(x in q for x in ["stop", "stop loss", "trailing", "breakeven", "atr"]) and not any(x in q for x in _stop_excl):
        for clave, info in STOP_METHODS.items():
            if clave.replace("_"," ") in q or clave in q:
                return (f"**{info['nombre']}**: {info['descripcion']}\n"
                        f"Ventaja: {info.get('ventaja','')}\n"
                        f"Desventaja: {info.get('desventaja','')}")
        return ("Métodos de stop loss profesionales: " +
                " | ".join(v["nombre"] for v in STOP_METHODS.values()))

    # Gestión de riesgo
    if any(x in q for x in ["riesgo", "risk", "gestión", "gestion", "posición",
                              "position", "1%", "2%", "rr", "ratio"]):
        for clave, desc in GESTION_RIESGO.items():
            if clave.replace("_"," ") in q:
                return f"**{clave.replace('_',' ').upper()}**: {desc}"
        return " | ".join(list(GESTION_RIESGO.values())[:3])

    # TradingView
    if any(x in q for x in ["tradingview", "trading view", "grafico", "gráfico",
                              "screener", "alerta", "pine script"]):
        return (f"**TRADINGVIEW**: {TRADINGVIEW['descripcion']}\n"
                f"Indicadores recomendados: {', '.join(TRADINGVIEW['configuracion_recomendada']['indicadores_basicos'])}.\n"
                f"Uso de screener: {TRADINGVIEW['screener_uso']}")

    # Estocástico XTB (handler dedicado — más detallado que el genérico)
    if any(x in q for x in ["estocástico", "estocastico", "oscilador estocástico",
                              "indicador so", "%k", "%d cruce"]):
        so = XTB_SCALPING_M1["indicadores_clave"]["estocastico"]
        return (
            f"**Indicador Estocástico (SO) — Scalping:**\n{so}\n"
            f"Configuración recomendada para scalping: (5,3,3) o (14,3,3).\n"
            f"Regla de oro: combinar con RSI para doble confirmación de sobrecompra/sobreventa."
        )

    # Triple Cruce de la Muerte EMA(4,18,40) — Equiti
    if any(x in q for x in ["triple cruce", "cruce de la muerte", "ema 4 18",
                              "ema 4-18", "triple death", "medias 4 18 40",
                              "tres emas scalp"]):
        tc = EQUITI_SCALPING["triple_cruce_muerte"]
        return (
            f"**{tc['nombre']}:**\n{tc['descripcion']}\n\n"
            f"Señal ALCISTA: {tc['señal_alcista']}\n"
            f"Señal BAJISTA: {tc['señal_bajista']}\n"
            f"Timeframe: {tc['timeframe']} | Par referencia: {tc['par_referencia']}\n"
            f"Confirmación: {tc['confirmacion']}\n"
            f"Fiabilidad: {tc['fiabilidad']}"
        )

    # Ichimoku dedicado para scalping M1 — Equiti (más específico que INDICADORES genérico)
    if any(x in q for x in ["ichimoku scalping", "ichimoku m1", "nube ichimoku scalp",
                              "kumo scalping", "ichimoku corto plazo", "nube scalping"]):
        ic = EQUITI_SCALPING["ichimoku_scalping"]
        reglas = "\n".join(f"  • {r}" for r in ic["reglas"])
        return (
            f"**{ic['nombre']}:**\n{ic['descripcion']}\n\n"
            f"Reglas operativas:\n{reglas}\n\n"
            f"Mejor timeframe: {ic['mejor_timeframe']}\n"
            f"Nota de Equiti: {ic['nota']}"
        )

    # SMA 200 como soporte/resistencia universal — Equiti
    if any(x in q for x in ["sma 200 universal", "sma 200 soporte", "sma 200 resistencia",
                              "sma200 scalping", "media 200 universal"]):
        s200 = EQUITI_SCALPING["sma_200_universal"]
        return (
            f"**{s200['nombre']}:**\n{s200['descripcion']}\n\n"
            f"Uso en scalping: {s200['uso_scalping']}\n\n"
            f"Combinación ideal: {s200['combinacion']}"
        )

    # Indicadores (excluir palabras que contienen "ema" como subpalabra no deseada)
    _ind_excl = ("esperanza", "matematica", "matemática", "academia", "problema",
                 "sistema de", "tema de", "patron", "patrón")
    if any(x in q for x in ["ema", "rsi", "macd", "bollinger", "vwap", "atr",
                              "volumen", "stochastic", "ichimoku", "indicador"]) and not any(x in q for x in _ind_excl):
        for ind, desc in INDICADORES.items():
            if ind in q:
                return f"**{ind.upper()}**: {desc}"
        return ("Indicadores técnicos que manejo: " +
                ", ".join(INDICADORES.keys()).upper() +
                ". Pregúntame por uno específico.")

    # SMC / ICT
    if any(x in q for x in ["smc", "ict", "smart money", "inner circle", "ciclo amd",
                              "accumulation", "manipulation", "distribution",
                              "market maker model", "mmm", "ote", "optimal trade entry",
                              "premium", "descuento", "discount", "equilibrium",
                              "breaker block", "displacement", "inducement", "induccion",
                              "killzone", "kill zone", "london sweep",
                              "dinero institucional", "dinero inteligente"]):
        # Buscar en SMC_ICT primero
        for clave, info in SMC_ICT.items():
            if clave.replace("_", " ") in q or clave in q:
                if isinstance(info, dict):
                    nombre = info.get("nombre", clave.replace("_", " ").upper())
                    desc   = info.get("descripcion", info.get("uso", str(info)))
                    return f"**{nombre}**: {desc}"
                return f"**{clave.replace('_',' ').upper()}**: {info}"
        # Killzones con horarios LATAM
        if any(x in q for x in ["killzone", "kill zone", "horario latam", "colombia",
                                  "argentina", "mexico"]):
            kz = SMC_ICT["killzones_latam"]
            ny = kz["ny_open"]
            lon = kz["london_open"]
            return (
                f"ICT Killzones (horarios Colombia/México):\n"
                f"• Asia range: {kz['asia_range']['colombia_mexico']} — Marcar niveles, NO operar.\n"
                f"• London open: {lon['colombia_mexico']} — Sweep asiático + entrada. ({lon['tasa']})\n"
                f"• NY open: {ny['colombia_mexico']} — MEJOR MOMENTO. ({ny['tasa']})\n"
                f"• London close: {kz['london_close']['colombia_mexico']} — Precaución, reversiones."
            )
        # Descripción general SMC
        ciclo = SMC_ICT["ciclo_amd"]
        return (
            f"**SMC/ICT — Smart Money Concepts**: {ciclo['descripcion']}\n"
            f"Fases: Acumulación (Asia) → Manipulación (Londres) → Distribución (NY).\n"
            f"OTE: Zona Fibonacci 61.8%-78.6% — la entrada de mayor probabilidad.\n"
            f"Conceptos clave: Order Blocks, FVG, BOS, CHoCH, Liquidity, Killzones."
        )

    # Latino Wall Street
    if any(x in q for x in ["latino wall street", "latinowallstreet", "lws",
                              "gabriela berrospi", "alan burak", "never alone capital",
                              "cursos de trading", "academia de trading",
                              "secretos de day trading", "gallo mañanero"]):
        lws = LATINO_WALL_STREET
        return (
            f"**Latino Wall Street**: {lws['quienes_son']}\n"
            f"Cursos: {', '.join(list(lws['cursos'].keys())[:4])} (y más).\n"
            f"Metodologías: {', '.join(lws['metodologias'][:3])}.\n"
            f"Herramientas: {', '.join(lws['herramientas'][:2])}."
        )

    # Brokers LATAM
    if any(x in q for x in ["broker express", "exness", "xm broker", "etoro",
                              "interactive brokers", "pepperstone", "roboforex",
                              "qué broker", "que broker", "mejor broker",
                              "broker para latam", "broker recomendado"]):
        for nombre, info in BROKERS_LATAM.items():
            if nombre.replace("_", " ") in q or nombre in q:
                return (f"**{nombre.replace('_',' ').upper()}** ({info.get('tipo','')})\n"
                        f"Regulación: {info.get('regulacion','')}\n"
                        f"{info.get('nota','')}")
        return ("Brokers populares en LATAM: " +
                " | ".join(f"{k.replace('_',' ')} ({v.get('tipo','')})"
                           for k, v in BROKERS_LATAM.items() if k != "broker_express"))

    # Estrategias generales
    if any(x in q for x in ["estrategia", "strategy", "plan", "sistema", "método",
                              "metodo", "cómo operar", "como operar", "cuando entrar",
                              "dame un plan", "cómo hago trading", "como hago trading"]):
        return ESTRATEGIAS_RESUMEN

    # ── Maestría en Scalping LWS (video 1) ───────────────────────────────────
    if any(x in q for x in ["maestria scalping", "maestría scalping", "scalping lws",
                              "clase 1", "bos choch", "order block válido",
                              "order block valido", "liquidity sweep", "sweep",
                              "multi timeframe", "breaker block", "inducement",
                              "regla 3 perdidas", "regla tres perdidas"]):
        scl = SCALPING_LWS
        return (
            f"**{scl['introduccion']}\n\n"
            f"Pilares LWS:\n" +
            "\n".join(f"  {p}" for p in scl["pilares"]) +
            f"\n\nOrder Block válido: {scl['order_blocks_validos']['definicion']}\n" +
            "Criterios: " + " ".join(scl["order_blocks_validos"]["criterios"][:3]) +
            f"\n\nLiquidity Sweep: {scl['liquidity_sweeps']['como_usarlo']}\n" +
            f"Gestión: {scl['gestion_scalping_lws']['regla_3']}"
        )

    if any(x in q for x in ["bos", "break of structure", "choch", "change of character",
                              "estructura de mercado", "estructura mercado"]):
        em = SCALPING_LWS["estructura_mercado"]
        return (
            f"**Estructura de Mercado (LWS):**\n"
            f"BOS: {em['bos']}\n"
            f"CHoCH: {em['choch']}\n"
            f"Regla: {em['regla']}"
        )

    if any(x in q for x in ["fvg", "fair value gap", "brecha de valor"]):
        return f"**FVG (Fair Value Gap):** {SCALPING_LWS['patrones_scalping_lws']['fvg_entry']}"

    # ── Bolsa desde cero (video 2) ────────────────────────────────────────────
    _bolsa_excl = ("acciones wall street", "trading acciones wall", "bolsa wall street")
    if any(x in q for x in ["bolsa desde cero", "invertir desde cero", "principiante",
                              "empezar a invertir", "qué es la bolsa", "que es la bolsa",
                              "cómo empezar", "como empezar", "primeros pasos trading",
                              "etf", "spy", "qqq", "accion", "acción"]) and not any(x in q for x in _bolsa_excl):
        bp = BOLSA_PRINCIPIANTES
        return (
            f"**Bolsa desde cero:**\n{bp['que_es_la_bolsa']}\n\n"
            f"Instrumentos: acciones ({bp['instrumentos']['acciones'][:80]}...) | "
            f"ETFs ({bp['instrumentos']['etf'][:60]}...)\n\n"
            f"Gestión: {bp['gestion_capital_principiantes']['regla_1_porciento']}\n"
            f"Pasos: {' → '.join(bp['pasos_principiante'][:4])}"
        )

    if any(x in q for x in ["analisis fundamental", "análisis fundamental",
                              "pe ratio", "p/e", "eps", "valor empresa"]):
        return f"**Análisis Fundamental:** {BOLSA_PRINCIPIANTES['analisis']['fundamental']}"

    if any(x in q for x in ["errores comunes", "errores trader", "errores trading",
                              "fomo", "revenge trading"]):
        return (
            "**Errores más comunes en trading:**\n" +
            "\n".join(f"  ❌ {e}" for e in BOLSA_PRINCIPIANTES["errores_comunes"])
        )

    if any(x in q for x in ["video", "clase", "youtube", "curso lws",
                              "que aprendiste", "qué aprendiste", "resumen videos"]):
        return (
            f"**Maestría en Scalping (LWS):** {VIDEOS_RESUMEN['maestria_scalping_lws']}\n\n"
            f"**Bolsa desde cero:** {VIDEOS_RESUMEN['bolsa_desde_cero']}"
        )

    # ── XTB Módulo 1 — Scalping (Gonzalo Muñoz) ──────────────────────────────
    if any(x in q for x in ["xtb", "gonzalo muñoz", "gonzalo munoz",
                              "módulo 1", "modulo 1", "módulo scalping xtb",
                              "pirámide del scalping", "piramide del scalping",
                              "cortar pérdidas", "cortar perdidas rapidamente",
                              "gestión del tiempo scalping", "gestion del tiempo scalping",
                              "activos para scalping", "mejor activo scalping",
                              "us100 scalping", "natgas"]):
        xtb = XTB_SCALPING_M1
        if any(x in q for x in ["activos", "us100", "natgas", "qué activo", "que activo"]):
            ar = xtb["activos_recomendados"]
            return (
                f"**Activos para Scalping (XTB):**\n"
                f"✓ Recomendados: {' | '.join(ar['buenos'][:3])}\n"
                f"✗ Evitar: {' | '.join(ar['evitar'][:2])}\n"
                f"Criterios de selección: {' | '.join(ar['criterios'])}"
            )
        if any(x in q for x in ["pirámide", "piramide", "cortar pérdida", "cortar perdida"]):
            pir = xtb["control_emocional"]["piramide"]
            return (
                "**Pirámide del Scalping Exitoso (XTB)** — base a cima:\n" +
                "\n".join(f"  {p}" for p in pir)
            )
        if any(x in q for x in ["timing", "momento", "cuándo entrar", "cuando entrar"]):
            t = xtb["timing"]
            return (
                f"**Timing en Scalping (XTB):**\n"
                f"Alta volatilidad: {t['alta_volatilidad']}\n"
                f"Confirmaciones: {t['confirmaciones']}\n"
                f"Evitar: {t['evitar_consolidacion']}\n"
                f"Mejores momentos: {' | '.join(t['mejores_momentos'])}"
            )
        # Respuesta general del módulo XTB
        gr = xtb["gestion_riesgo"]
        return (
            f"**XTB — Módulo 1 Scalping (Gonzalo Muñoz):**\n"
            f"{xtb['definicion'][:220]}...\n\n"
            f"Gestión de riesgo: R:R mínimo {gr['rr_minimo']} | "
            f"Exposición: {gr['exposicion']} | SL: {gr['stop_loss']}\n"
            f"Emociones: {xtb['control_emocional']['overtrading']}\n"
            f"Tiempo: {xtb['gestion_tiempo']['limite_sesion']}"
        )

    # ── Chartismo / Patrones de precio (XTB) ─────────────────────────────────
    if any(x in q for x in ["chartismo", "patrón chartista", "patron chartista",
                              "formación de precio", "formacion de precio",
                              "doble techo", "doble suelo", "cabeza y hombros",
                              "head and shoulders", "cuña", "wedge", "cuña ascendente",
                              "cuña descendente", "falling wedge", "rising wedge",
                              "triángulo expansivo", "triangulo expansivo",
                              "expanding triangle", "triple techo", "triple suelo",
                              "double top", "double bottom"]):
        # Buscar patrón específico
        alias = {
            # Las variantes específicas deben ir ANTES que las genéricas
            "cabeza y hombros invertido": "cabeza_y_hombros_invertido",
            "cabeza hombros invertido": "cabeza_y_hombros_invertido",
            "inverted head and shoulders": "cabeza_y_hombros_invertido",
            "h&s invertido": "cabeza_y_hombros_invertido",
            "triángulo expansivo bajista": "triangulo_expansion_bajista",
            "triángulo expansivo alcista": "triangulo_expansion_alcista",
            "triangulo expansion bajista": "triangulo_expansion_bajista",
            "triangulo expansion alcista": "triangulo_expansion_alcista",
            "broadening top": "triangulo_expansion_bajista",
            "broadening bottom": "triangulo_expansion_alcista",
            # Genéricas después
            "doble techo": "doble_techo", "double top": "doble_techo",
            "doble suelo": "doble_suelo", "double bottom": "doble_suelo",
            "cabeza y hombros": "cabeza_y_hombros", "head and shoulders": "cabeza_y_hombros",
            "cuña ascendente": "cuña_ascendente", "rising wedge": "cuña_ascendente",
            "cuña descendente": "cuña_descendente", "falling wedge": "cuña_descendente",
            "expanding triangle": "triangulo_expansion_bajista",
            "triple techo": "triple_techo", "triple suelo": "triple_suelo",
        }
        clave_patron = None
        for term, clave in alias.items():
            if term in q:
                clave_patron = clave
                break
        if clave_patron and clave_patron in PATRONES_CHARTISTAS:
            p = PATRONES_CHARTISTAS[clave_patron]
            señal_txt = {
                "bullish_reversal": "REVERSIÓN ALCISTA",
                "bearish_reversal": "REVERSIÓN BAJISTA",
                "bullish": "ALCISTA",
                "bearish": "BAJISTA",
            }.get(p["señal"], p["señal"])
            return (
                f"**{p['nombre']}** ({señal_txt})\n"
                f"{p['descripcion']}\n"
                f"Acción: {p['accion']}\n"
                f"Fiabilidad: {p['fiabilidad']}"
            )
        # Resumen general de patrones
        bajistas = [v["nombre"] for v in PATRONES_CHARTISTAS.values()
                    if "bearish" in v["señal"]]
        alcistas = [v["nombre"] for v in PATRONES_CHARTISTAS.values()
                    if "bullish" in v["señal"]]
        return (
            f"**Patrones Chartistas (XTB Módulo 1):**\n"
            f"Bajistas: {', '.join(bajistas)}\n"
            f"Alcistas: {', '.join(alcistas)}\n"
            f"Pregúntame por uno específico para descripción, acción y target completos."
        )

    # ── Estocástico ───────────────────────────────────────────────────────────
    if any(x in q for x in ["estocástico", "estocastico", "stochastic", "indicador so",
                              "oscilador estocástico", "%k", "%d cruce"]):
        so = XTB_SCALPING_M1["indicadores_clave"]["estocastico"]
        return (
            f"**Indicador Estocástico (SO) — Scalping:**\n{so}\n"
            f"Configuración recomendada para scalping: (5,3,3) o (14,3,3).\n"
            f"Regla de oro: combinar con RSI para doble confirmación de sobrecompra/sobreventa."
        )

    # ── EQUITI Scalping Guide — Psicología, Acciones, Esperanza Matemática ──────
    if any(x in q for x in ["equiti", "guia equiti", "guía equiti",
                              "codicia", "miedo trading", "ansiedad trading",
                              "ansiedad mercado", "esperanza matemática",
                              "esperanza matematica", "disciplina trading",
                              "disciplina horarios", "incertidumbre trading",
                              "incertidumbre mercado", "5 emociones", "cinco emociones",
                              "emociones del trader", "emociones trading",
                              "psicologia equiti", "psicología equiti",
                              "acciones wall street", "derivados acciones",
                              "bolsa valores scalping", "probabilidad trading",
                              "oferta y demanda bolsa", "derivados bolsa"]):
        eq = EQUITI_SCALPING

        if "codicia" in q:
            return (
                f"**La Codicia en Trading (Equiti):**\n"
                f"{eq['psicologia_5_emociones']['codicia']}"
            )

        if any(x in q for x in ["miedo trading", "miedo en trading"]):
            return (
                f"**El Miedo en Trading (Equiti):**\n"
                f"{eq['psicologia_5_emociones']['miedo']}"
            )

        if any(x in q for x in ["ansiedad trading", "ansiedad mercado"]):
            return (
                f"**La Ansiedad en Trading (Equiti):**\n"
                f"{eq['psicologia_5_emociones']['ansiedad']}"
            )

        if any(x in q for x in ["esperanza trading", "no esperanza trading"]):
            return (
                f"**La Esperanza en Trading (Equiti):**\n"
                f"{eq['psicologia_5_emociones']['esperanza']}"
            )

        if any(x in q for x in ["disciplina trading", "disciplina horarios"]):
            return (
                f"**La Disciplina en Trading (Equiti):**\n"
                f"{eq['psicologia_5_emociones']['disciplina']}"
            )

        if any(x in q for x in ["5 emociones", "cinco emociones", "emociones del trader",
                                  "emociones trading", "psicologia equiti", "psicología equiti"]):
            emo = eq["psicologia_5_emociones"]
            return (
                f"**Las 5 Emociones del Trader (Equiti):**\n"
                f"1. CODICIA: {emo['codicia'][:120]}...\n\n"
                f"2. MIEDO: {emo['miedo'][:120]}...\n\n"
                f"3. ANSIEDAD: {emo['ansiedad'][:120]}...\n\n"
                f"4. ESPERANZA: {emo['esperanza'][:120]}...\n\n"
                f"5. DISCIPLINA: {emo['disciplina'][:120]}...\n\n"
                f"Orden de peligrosidad: {' > '.join(emo['orden_peligrosidad'])}"
            )

        if any(x in q for x in ["esperanza matemática", "esperanza matematica",
                                  "incertidumbre trading", "incertidumbre mercado",
                                  "probabilidad trading"]):
            em = eq["esperanza_matematica"]
            return (
                f"**Esperanza Matemática — Control de Incertidumbre (Equiti):**\n\n"
                f"{em['concepto']}\n\n"
                f"Ejemplo práctico: {em['formula_mental']}\n\n"
                f"Regla clave: {em['regla_clave']}\n\n"
                f"Mentalidad profesional: {em['incertidumbre_como_aliada']}"
            )

        if any(x in q for x in ["acciones wall street", "derivados acciones",
                                  "bolsa valores scalping", "oferta y demanda bolsa",
                                  "derivados bolsa"]):
            acc = eq["trading_acciones"]
            der = acc["derivados_vs_directas"]
            return (
                f"**Trading con Acciones (Equiti):**\n"
                f"Bolsas: {', '.join(acc['bolsas_principales'])}\n"
                f"Precio determinado por: {acc['determinacion_precio']}\n\n"
                f"Derivados (CFDs): {der['derivados_cfds']}\n\n"
                f"Acciones directas: {der['acciones_directas']}\n\n"
                f"Para scalping: {acc['recomendacion_scalping']}"
            )

        # Respuesta general Equiti
        tc = eq["triple_cruce_muerte"]
        return (
            f"**Guía Scalping Equiti — Resumen:**\n"
            f"• {eq['definicion'][:130]}...\n"
            f"• Triple Cruce de la Muerte EMA(4,18,40): {tc['señal_alcista'][:70]}...\n"
            f"• SMA 200: soporte/resistencia universal en TODOS los timeframes\n"
            f"• Ichimoku M1: más popular para scalping de 1 minuto — precio sobre nube=alcista\n"
            f"• 5 emociones clave: codicia (enemiga#1), miedo, ansiedad, esperanza (trampa), disciplina\n"
            f"• Esperanza matemática: pensar en probabilidades, no en certezas — así opera el profesional"
        )

    # ── DINAMITA GRIZZLY — Volume Profile / VWAP ─────────────────────────────
    _dg_excl = ("scalping crypto", "cinco pasos", "5 pasos", "semillero")
    _dg_trigs = ("vpoc", "vah", "val", "volume profile", "vwap", "dinamita grizzly",
                 "grizzly", "nivel 2", "nivel2", "desequilibrio precio", "equilibrio mercado",
                 "zona de valor", "area de valor", "microestructura")
    if any(t in q for t in _dg_trigs) and not any(e in q for e in _dg_excl):
        dg = DINAMITA_GRIZZLY
        if any(t in q for t in ("vpoc", "vah", "val", "volume profile", "zona de valor", "area de valor")):
            vp = dg["volume_profile"]
            return (
                f"VOLUME PROFILE (DINAMITA GRIZZLY / J.M. Martín Núñez):\n"
                f"• VPOC: {vp['vpoc']}\n"
                f"• VAH (límite superior): {vp['vah']}\n"
                f"• VAL (límite inferior): {vp['val']}\n"
                f"• En equilibrio (VAH-VAL): {vp['equilibrio']}\n"
                f"• En desequilibrio: {vp['desequilibrio']}"
            )
        if any(t in q for t in ("vwap", "precio justo", "desviacion estandar vwap")):
            vw = dg["vwap_operativa"]
            return (
                f"VWAP OPERATIVA (DINAMITA GRIZZLY):\n"
                f"• {vw['definicion']}\n"
                f"• Sesgo alcista: {vw['sesgo_alcista']}\n"
                f"• Sesgo bajista: {vw['sesgo_bajista']}\n"
                f"• Desviaciones: {vw['desviaciones']}"
            )
        if "microestructura" in q:
            return dg["microestructuras"]
        return (
            f"SCALPING MOMENTUM — DINAMITA GRIZZLY:\n"
            f"• Filosofía: {dg['filosofia']}\n\n"
            f"PROCESO: " + "\n".join(dg["proceso_operativo"]) + "\n\n"
            f"REGLA DE ORO: {dg['regla_de_oro']}"
        )

    # ── MANUAL AVANZADO — Dow Theory / Elliott / Fibonacci ────────────────────
    _ma_excl = ("volumen", "vwap", "scalping crypto")
    _ma_trigs = ("teoria dow", "teoría dow", "dow theory", "ondas elliott", "ondas de elliott",
                 "onda 2", "onda 3", "onda 4", "onda 5", "onda a", "onda b", "onda c",
                 "fibonacci avanzado", "throw back", "pull back", "retroceso fibonacci",
                 "golden ratio", "61.8", "38.2", "fases tendencia", "acumulacion distribucion",
                 "etapas trader", "analisis fundamental avanzado", "per ratio", "dcf valoracion",
                 "ev ebitda", "price to book", "pib trading", "inflacion trading")
    if any(t in q for t in _ma_trigs) and not any(e in q for e in _ma_excl):
        ma = MANUAL_AVANZADO
        if any(t in q for t in ("teoria dow", "teoría dow", "dow theory", "fases tendencia")):
            td = ma["teoria_dow"]
            return (
                f"TEORÍA DE DOW — 6 Principios:\n"
                + "\n".join(f"  {p}" for p in td["principios"]) + "\n\n"
                f"FASES DE TENDENCIA ALCISTA:\n"
                f"  Acumulación: {td['fases_alcista']['acumulacion']}\n"
                f"  Expansión: {td['fases_alcista']['expansion']}\n"
                f"  Agotamiento: {td['fases_alcista']['agotamiento']}\n"
                f"  Distribución: {td['fases_alcista']['distribucion']}\n\n"
                f"Para scalping: {td['aplicacion_scalping']}"
            )
        if any(t in q for t in ("ondas elliott", "ondas de elliott", "onda 2", "onda 3",
                                 "onda 4", "onda 5", "onda a", "onda b", "onda c")):
            oe = ma["ondas_elliott"]
            return (
                f"ONDAS DE ELLIOTT:\n"
                f"Estructura: {oe['estructura']}\n\n"
                f"REGLAS INQUEBRANTABLES:\n"
                + "\n".join(f"  • {r}" for r in oe["reglas_inquebrantables"]) + "\n\n"
                f"Fibonacci + Elliott: {oe['fibonacci_elliot']}\n\n"
                f"Uso práctico: {oe['uso_practico']}\n\n"
                f"Para scalping: {oe['aplicacion_scalping']}"
            )
        if any(t in q for t in ("fibonacci avanzado", "throw back", "pull back",
                                 "retroceso fibonacci", "golden ratio", "61.8", "38.2")):
            fib = ma["fibonacci"]
            return (
                f"FIBONACCI AVANZADO:\n"
                f"Niveles clave: {fib['niveles_clave']}\n\n"
                f"Como soporte: {fib['uso_soporte']}\n\n"
                f"Como resistencia (extensiones): {fib['uso_resistencia']}\n\n"
                f"Throw Back / Pull Back: {fib['throw_back_pull_back']}\n\n"
                f"Regla de oro: {fib['regla_oro']}"
            )
        if any(t in q for t in ("etapas trader", "etapas del trader")):
            gm = ma["gestion_monetaria_profesional"]
            return "ETAPAS DEL TRADER:\n" + "\n".join(f"  {e}" for e in gm["etapas_trader"])
        if any(t in q for t in ("per ratio", "dcf valoracion", "ev ebitda",
                                 "price to book", "analisis fundamental avanzado")):
            af = ma["analisis_fundamental_conceptos"]
            return (
                f"ANÁLISIS FUNDAMENTAL — Conceptos clave:\n"
                f"• DCF: {af['dcf']}\n"
                f"• PER: {af['per']}\n"
                f"• EV/EBITDA: {af['ev_ebitda']}\n"
                f"• Price-to-Book: {af['price_to_book']}\n\n"
                f"Datos macro que mueven el mercado:\n"
                + "\n".join(f"  • {m}" for m in af["catalogo_macro"])
            )
        # Default manual avanzado
        return (
            f"MANUAL AVANZADO DE TRADING (Admiral Markets — Juan E. Cadiñanos):\n"
            f"Cubre: Teoría de Dow • Ondas de Elliott • Fibonacci • Análisis Fundamental. "
            f"Pregunta por cualquiera de estos temas para obtener detalle completo."
        )

    # ── FRANCISCA SERRANO — Psicología y disciplina operativa ────────────────
    _fs_excl = ("esperanza matematica", "equiti", "codicia equiti")
    _fs_trigs = ("francisca serrano", "livermore regla", "jesse livermore regla",
                 "cortar perdidas raiz", "blue chips liquidez", "objetivo diario",
                 "psicotrading", "revenge trading evitar", "dos horas trading",
                 "27 de 10000", "estudio barber", "actitud trader")
    if any(t in q for t in _fs_trigs) and not any(e in q for e in _fs_excl):
        fs = FRANCISCA_SERRANO
        if any(t in q for t in ("livermore", "cortar perdidas", "cortar pérdidas")):
            return (
                f"REGLAS DE JESSE LIVERMORE (via Francisca Serrano):\n"
                + "\n".join(f"• {r}" for r in fs["reglas_livermore"])
            )
        if any(t in q for t in ("blue chips", "liquidez", "chicharro")):
            liq = fs["liquidez_importancia"]
            return (
                f"LIQUIDEZ EN TRADING:\n"
                f"• {liq['concepto']}\n"
                f"• Blue chips: {liq['blue_chips']}\n"
                f"• Chicharros: {liq['chicharros_peligro']}\n"
                f"• Regla: {liq['regla_liquidez']}"
            )
        if any(t in q for t in ("psicotrading", "revenge trading evitar", "objetivo diario",
                                 "miedo trading", "codicia trading simple")):
            pt = fs["psicotrading"]
            return (
                f"PSICOTRADING (Francisca Serrano):\n"
                f"• Enemigo principal: {pt['enemigo_principal']}\n"
                f"• Miedo: {pt['miedo']}\n"
                f"• Codicia: {pt['codicia']}\n"
                f"• Objetivo diario: {pt['objetivo_diario']}\n"
                f"• Revenge trading: {pt['revenge_trading']}\n"
                f"• Disciplina: {pt['dos_horas_disciplina']}"
            )
        return (
            f"FRANCISCA SERRANO — Escuela de Bolsa:\n"
            f"• {fs['filosofia_base']}\n\n"
            f"Temas: Reglas Livermore • Liquidez/Blue chips • Psicotrading • Revenge trading"
        )

    # ── 151 ESTRATEGIAS CUANTITATIVAS — Kakushadze & Serur ────────────────────
    _eq_excl = ("scalping 5 pasos", "cinco pasos scalping")
    _eq_trigs = ("151 estrategias", "kakushadze", "estrategia momentum cuant",
                 "arbitraje estadistico", "machine learning trading", "regimen mercado cuant",
                 "eficiencia mercado", "overfitting trading", "kelly formula",
                 "esperanza matematica trading", "ev trading", "diversificacion estadistica",
                 "drawdown maximo", "estrategia mean reversion", "filtro vwap estrategia")
    if any(t in q for t in _eq_trigs) and not any(e in q for e in _eq_excl):
        ec = ESTRATEGIAS_CUANTITATIVAS
        if any(t in q for t in ("momentum cuant", "estrategia momentum")):
            return f"MOMENTUM (Kakushadze & Serur):\n{ec['tipos_estrategia']['momentum']}"
        if any(t in q for t in ("mean reversion", "reversión media", "reversion media")):
            return f"MEAN REVERSION (Kakushadze & Serur):\n{ec['tipos_estrategia']['mean_reversion']}"
        if any(t in q for t in ("arbitraje estadistico", "arbitraje estadístico")):
            return f"ARBITRAJE ESTADÍSTICO:\n{ec['tipos_estrategia']['arbitraje_estadistico']}"
        if any(t in q for t in ("kelly formula", "kelly criterio")):
            return f"KELLY + DRAWDOWN:\n{ec['principios_matematicos_clave']['drawdown_y_kelly']}"
        if any(t in q for t in ("esperanza matematica trading", "ev trading", "valor esperado")):
            return f"ESPERANZA MATEMÁTICA DE TRADING:\n{ec['principios_matematicos_clave']['esperanza_matematica_trading']}"
        if any(t in q for t in ("regimen mercado cuant", "trending formal", "ranging formal", "chaotic formal")):
            rm = ec["regimenes_mercado_cuantitativos"]
            return (
                f"REGÍMENES DE MERCADO (Kakushadze & Serur):\n"
                f"• TRENDING: {rm['trending_formal']}\n"
                f"• RANGING: {rm['ranging_formal']}\n"
                f"• CHAOTIC: {rm['chaotic_formal']}\n"
                f"• TRANSICIÓN: {rm['transicion']}"
            )
        return (
            f"151 ESTRATEGIAS DE TRADING (Kakushadze & Serur, 2019):\n"
            f"Libro académico con +550 fórmulas. Cubre todas las clases de activos.\n\n"
            f"Conceptos clave para Litch:\n"
            f"• Regímenes: trending (ADX>25, Hurst>0.55) / ranging (ADX<20) / chaotic (entropia>0.90)\n"
            f"• Diversificación estadística: 7 métodos no correlacionados > 1 método perfecto\n"
            f"• Overfitting: {ec['principios_matematicos_clave']['overfitting_warning'][:100]}...\n"
            f"• Kelly + Drawdown: {ec['principios_matematicos_clave']['drawdown_y_kelly'][:100]}..."
        )

    # ── 5 PASOS SCALPING CRIPTOMONEDAS — Semillero de Ingresos ──────────────
    _sp_excl = ("equiti", "grizzly", "francisca")
    _sp_trigs = ("5 pasos scalping", "cinco pasos scalping", "semillero de ingresos",
                 "scalping criptomonedas paso", "zonas de trabajo scalping",
                 "micro tendencia scalping", "objetivo scalping paso", "dominio plataforma")
    if any(t in q for t in _sp_trigs) and not any(e in q for e in _sp_excl):
        sp = SCALPING_5_PASOS
        if any(t in q for t in ("zonas de trabajo", "zonas trabajo scalping")):
            return f"PASO 1 — ZONAS DE TRABAJO:\n{sp['pasos_operativos']['paso1_zonas']}"
        if any(t in q for t in ("micro tendencia", "microtendencia")):
            return f"PASO 2 — MICRO-TENDENCIA:\n{sp['pasos_operativos']['paso2_micro_tendencia']}"
        if any(t in q for t in ("objetivo scalping", "target scalping")):
            return f"PASO 3 — OBJETIVO:\n{sp['pasos_operativos']['paso3_objetivo']}"
        if "herramientas scalping" in q:
            return "PASO 4 — HERRAMIENTAS:\n" + "\n".join(f"• {h}" for h in sp["pasos_operativos"]["paso4_herramientas"])
        if any(t in q for t in ("dominio plataforma", "dominar plataforma")):
            return sp["dominio_plataforma"]
        return (
            f"5 PASOS PARA SCALPING (Semillero de Ingresos):\n"
            f"• {sp['concepto_scalping']}\n\n"
            f"PASOS:\n"
            f"1. {sp['pasos_operativos']['paso1_zonas'][:80]}...\n"
            f"2. {sp['pasos_operativos']['paso2_micro_tendencia'][:80]}...\n"
            f"3. {sp['pasos_operativos']['paso3_objetivo'][:80]}...\n"
            f"4. Herramientas: escáner volumen, patrones velas, nivel 2, Volume Profile\n"
            f"5. {sp['pasos_operativos']['paso5_gestion'][:80]}..."
        )

    return ""  # Sin respuesta específica → usar IA


# ── MAESTRÍA EN SCALPING — Latino Wall Street Clase 1 ─────────────────────────
# Basado en la metodología del curso "Maestría en Scalping" de Latino Wall Street
# (Live class serie). Integra Price Action + SMC + gestión de capital.

SCALPING_LWS = {
    "introduccion": (
        "La Maestría en Scalping de Latino Wall Street enseña a operar en marcos "
        "temporales cortos (M1–M15) usando estructura de mercado y Smart Money "
        "Concepts sin depender de indicadores lagging. "
        "Filosofía: 'El precio habla — aprende a escucharlo.'"
    ),
    "pilares": [
        "1. Estructura de mercado (BOS / CHoCH): identificar quién controla.",
        "2. Order Blocks válidos: zona donde el precio debe regresar.",
        "3. Liquidity sweeps: el precio busca stops antes de moverse.",
        "4. Multi-timeframe: bias en M15/H1, entrada en M1/M5.",
        "5. Gestión: mínimo R:R 1:1.5, máximo 2% riesgo por trade.",
    ],
    "estructura_mercado": {
        "bos": (
            "Break of Structure (BOS): el precio rompe un máximo/mínimo previo "
            "confirmando la continuación de la tendencia actual."
        ),
        "choch": (
            "Change of Character (CHoCH): el precio rompe en dirección CONTRARIA "
            "a la tendencia — primer indicio de reversión. "
            "En scalping: entrar en el primer pullback tras el CHoCH."
        ),
        "regla": (
            "Mínimo = bajista si precio hace LL (Lower Low) y LH (Lower High). "
            "Máximo = alcista si precio hace HH (Higher High) y HL (Higher Low)."
        ),
    },
    "order_blocks_validos": {
        "definicion": (
            "Un Order Block (OB) VÁLIDO es la última vela contraria antes del "
            "movimiento impulsivo que rompió estructura. No cualquier vela grande."
        ),
        "criterios": [
            "a) Causó un BOS o CHoCH — tuvo consecuencia real en el precio.",
            "b) No ha sido completamente mitigado — precio no regresó al 100%.",
            "c) En zona Premium (>50% Fibonacci del rango) para ventas.",
            "d) En zona Discount (<50% Fibonacci del rango) para compras.",
            "e) Confirmado en HTF (H1/H4) → entrada en LTF (M5/M1).",
        ],
        "error_comun": (
            "Error frecuente: marcar cualquier vela bajista/alcista grande como OB. "
            "Solo es OB si causó una ruptura de estructura."
        ),
    },
    "liquidity_sweeps": {
        "definicion": (
            "El precio barre stops acumulados antes de moverse en la dirección real. "
            "Los stops están en: máximos/mínimos previos, equal highs/lows, "
            "extremos de sesiones anteriores."
        ),
        "como_usarlo": (
            "1. Identificar zona de liquidez (iguales máximos o mínimos). "
            "2. Esperar que el precio la barra (falsa ruptura). "
            "3. Confirmar CHoCH en LTF tras el sweep. "
            "4. Entrar en el OB más cercano con SL por debajo del sweep."
        ),
        "ejemplo": (
            "Equal highs en M15 → precio sube, rompe los máximos (sweep), "
            "vela bajista engulfing → CHoCH en M1 → short desde OB bajista."
        ),
    },
    "multi_timeframe": {
        "regla": "Siempre operar a FAVOR del bias del HTF.",
        "proceso": [
            "H4/H1: determinar tendencia principal y zona Premium/Discount.",
            "M15: identificar OBs relevantes y zonas de liquidez.",
            "M5/M1: buscar entrada precisa con CHoCH + FVG.",
        ],
        "sesiones_scalping": {
            "london_open": "07:00-10:00 UTC — mayor movimiento, primer sweep + tendencia.",
            "ny_open":     "13:30-16:00 UTC — volatilidad alta, reversiones y continuaciones.",
            "evitar":      "Asia y lunch time NY (12:00-13:30 UTC) — spreads amplios.",
        },
    },
    "gestion_scalping_lws": {
        "riesgo_por_trade": "1-2% máximo del capital total.",
        "rr_minimo": "1:1.5 — si no hay espacio para este R:R, no entrar.",
        "stop_loss": "Por debajo/encima del Order Block o del sweep (estructura).",
        "take_profit": [
            "TP1: siguiente zona de liquidez (50% de la posición).",
            "TP2: extremo del rango o FVG de HTF (50% restante).",
        ],
        "regla_3": (
            "Regla 3 de LWS: máximo 3 trades perdedores seguidos → PARAR el día. "
            "El mercado no te debe nada. La disciplina es el edge."
        ),
        "psicologia": [
            "No operar si estás emocional (enojado, ansioso, eufórico).",
            "Llevar un diario de trades — registrar entrada, razón, resultado.",
            "El objetivo diario es consistencia, no un número específico.",
        ],
    },
    "patrones_scalping_lws": {
        "fvg_entry": (
            "Fair Value Gap (FVG): tres velas donde la segunda es muy grande. "
            "El gap entre vela 1 y vela 3 es la zona de valor justo. "
            "Precio regresa a llenar el gap → entrada con SL al otro lado."
        ),
        "inducement": (
            "Trampa antes del OB: el precio crea un falso BOS en LTF "
            "para tomar los stops de traders que entraron demasiado pronto. "
            "Señal: ver sweep de inducement → CHoCH → entrada real."
        ),
        "breaker_block": (
            "OB que falló → se convierte en Breaker Block de la dirección opuesta. "
            "Alta probabilidad porque muchos traders quedan atrapados."
        ),
    },
}

# ── BOLSA DESDE CERO — Clase para principiantes ───────────────────────────────
# Conceptos cubiertos en 'Cómo invertir en la Bolsa desde cero'
# (video educativo para principiantes)

BOLSA_PRINCIPIANTES = {
    "que_es_la_bolsa": (
        "La Bolsa de Valores es un mercado organizado donde se compran y venden "
        "instrumentos financieros (acciones, ETFs, bonos, futuros). "
        "NYSE (New York Stock Exchange) y NASDAQ son los más grandes del mundo. "
        "Horario NYSE: 9:30-16:00 ET de lunes a viernes."
    ),
    "instrumentos": {
        "acciones": (
            "Una acción es una fracción de propiedad de una empresa. "
            "Si AAPL sube 10%, tu inversión sube 10%. "
            "Riesgo: la empresa puede quebrar o el precio bajar indefinidamente."
        ),
        "etf": (
            "ETF (Exchange Traded Fund): cesta de activos que cotiza como una acción. "
            "SPY = S&P 500 (las 500 empresas más grandes de USA). "
            "QQQ = NASDAQ 100 (tecnológicas). "
            "Ventaja: diversificación instantánea, bajo costo."
        ),
        "opciones_binarias": (
            "Las opciones binarias (IQ Option, Quotex) son MUY distintas a la bolsa. "
            "Son apuestas de 'sube o baja' en tiempo fijo (30s, 1min, 5min). "
            "Payout máximo ~85-92%. No son instrumentos regulados en la mayoría de países. "
            "SOLO practicar en DEMO hasta tener >60% precisión consistente."
        ),
    },
    "analisis": {
        "tecnico": (
            "Análisis Técnico: estudia el comportamiento del precio en el gráfico. "
            "Herramientas: velas japonesas, soportes/resistencias, tendencias, "
            "indicadores (RSI, MACD, Medias Móviles). "
            "Filosofía: 'el precio descuenta todo'."
        ),
        "fundamental": (
            "Análisis Fundamental: evalúa el valor real de una empresa. "
            "Métricas clave: P/E ratio, EPS, revenue growth, deuda/patrimonio. "
            "Para largo plazo: busca empresas con ventaja competitiva (moat). "
            "Ejemplo: Buffett compra empresas con P/E razonable + moat fuerte."
        ),
        "combinacion": (
            "Mejor enfoque: Fundamental para seleccionar QUÉ comprar, "
            "Técnico para decidir CUÁNDO entrar y salir."
        ),
    },
    "gestion_capital_principiantes": {
        "regla_base": "Nunca invertir dinero que no puedas perder.",
        "diversificacion": "No pongas todos los huevos en una canasta — mínimo 5 activos.",
        "stop_loss": (
            "Stop Loss: precio al que vendes automáticamente para limitar la pérdida. "
            "Ejemplo: compras en $100, pones stop en $95 (-5%). "
            "SIN stop loss → puedes perder todo en una sola operación."
        ),
        "take_profit": (
            "Take Profit: precio objetivo donde realizas la ganancia. "
            "R:R mínimo 1:2 — si arriesgas $100, el objetivo es ganar $200."
        ),
        "regla_1_porciento": (
            "Nunca arriesgues más del 1-2% del capital total en un solo trade. "
            "Con $1,000 en cuenta: máximo en riesgo = $10-20 por operación."
        ),
        "psicologia": [
            "FOMO (Fear of Missing Out): entrar tarde por miedo a perderse el movimiento.",
            "Revenge trading: entrar de nuevo tras una pérdida para 'recuperar'.",
            "Solución: plan de trading escrito ANTES de abrir el gráfico.",
        ],
    },
    "pasos_principiante": [
        "1. Aprender análisis técnico básico (velas, soportes, tendencias).",
        "2. Abrir cuenta DEMO y practicar 3-6 meses sin dinero real.",
        "3. Llevar diario de trades: entrada, razón, resultado, lección.",
        "4. Alcanzar >55% de tasa de acierto y R:R positivo en demo.",
        "5. Empezar con capital MÍNIMO en real (lo que puedas perder todo).",
        "6. Escalar gradualmente según los resultados.",
    ],
    "errores_comunes": [
        "Operar sin stop loss.",
        "Usar todo el capital en un solo trade.",
        "Cambiar la estrategia después de 3 pérdidas.",
        "Operar sin un plan escrito.",
        "Ignorar el análisis fundamental en acciones a largo plazo.",
        "Confundir opciones binarias con inversión real en bolsa.",
    ],
}

# Resumen de ambos videos para búsquedas
VIDEOS_RESUMEN = {
    "maestria_scalping_lws": (
        "Maestría en Scalping Clase 1 — Latino Wall Street. "
        "Pilares: estructura de mercado (BOS/CHoCH), Order Blocks válidos, "
        "Liquidity Sweeps, multi-timeframe (H1→M5→M1), R:R mínimo 1:1.5, "
        "máximo 2% riesgo. Sesiones: London Open y NY Open. "
        "Regla 3 pérdidas → parar el día."
    ),
    "bolsa_desde_cero": (
        "Bolsa desde cero para principiantes. "
        "Instrumentos: acciones, ETFs (SPY, QQQ), opciones binarias (DEMO). "
        "Análisis técnico + fundamental. Stop loss obligatorio. "
        "1-2% riesgo por trade. Diario de trades. Demo 3-6 meses antes de real."
    ),
}


# ── XTB — MÓDULO 1: INTRODUCCIÓN AL SCALPING (Gonzalo Muñoz) ─────────────────
# Fuente: PDF oficial XTB "Módulo 1: Introducción al Scalping y al Trading
# de corto plazo". Integrado permanentemente como conocimiento estructurado.

XTB_SCALPING_M1 = {
    "definicion": (
        "El scalping es una disciplina de trading de altísima frecuencia que busca "
        "obtener pequeñas ganancias de manera rápida a lo largo del día. "
        "Cada operación dura segundos o pocos minutos. El resultado se logra por "
        "acumulación de muchas operaciones pequeñas con alta precisión. "
        "Requiere extrema disciplina emocional, un plan escrito, y R:R mínimo 1:2."
    ),
    "identificar_tendencia": {
        "alcista": (
            "Máximos más altos (Higher Highs, HH) y mínimos más altos (Higher Lows, HL). "
            "El precio rompe resistencias anteriores y cada retroceso se detiene más arriba. "
            "Operar SOLO en dirección alcista en esta condición — compras en pullbacks."
        ),
        "bajista": (
            "Máximos más bajos (Lower Highs, LH) y mínimos más bajos (Lower Lows, LL). "
            "El precio rompe soportes anteriores. "
            "Operar SOLO en dirección bajista — ventas en rebotes."
        ),
        "lateral": (
            "El precio oscila entre soporte y resistencia sin dirección clara. "
            "En scalping: EVITAR operar en el medio del rango. "
            "Oportunidades: rebotes en los extremos del rango con confirmación de vela."
        ),
        "multi_temporalidad": (
            "Analizar siempre en múltiples timeframes: HTF (H1 o H4) para estructura general, "
            "MTF (M15 o M5) para la tendencia de trading, LTF (M1 o M2) para la entrada. "
            "Nunca operar contra la tendencia del HTF."
        ),
    },
    "timing": {
        "alta_volatilidad": (
            "Los mejores momentos son las aperturas de mercados: "
            "London Open (8:00-10:00 UTC) y NY Open (13:30-15:30 UTC). "
            "La volatilidad es máxima y hay grandes movimientos direccionales."
        ),
        "confirmaciones": (
            "En M1 o M2: esperar rompimiento de estructura (BOS) + pullback + nueva vela de confirmación. "
            "No entrar en medio de un movimiento — esperar el retroceso al OB o nivel clave."
        ),
        "evitar_consolidacion": (
            "Evitar entrar durante consolidaciones (velas pequeñas, rango estrecho). "
            "Esperar la ruptura del rango o la expansión de volatilidad antes de entrar."
        ),
        "mejores_momentos": [
            "London Open 08:00-10:00 UTC",
            "Solapamiento Londres-NY 13:30-16:00 UTC",
            "Primeros 30 minutos de apertura NYSE (13:30 UTC)",
        ],
    },
    "gestion_riesgo": {
        "rr_minimo": "1:2 (por cada $1 en riesgo, objetivo mínimo $2 en ganancia)",
        "rr_objetivo": "1:3 para operaciones de alta confianza (muy buena setup)",
        "exposicion": "1-2% del capital total por operación",
        "stop_loss": (
            "Stop Loss obligatorio en cada operación. "
            "Colocarlo al otro lado del Order Block o nivel clave más cercano. "
            "NUNCA mover el SL para ampliar la pérdida — error fatal en scalping."
        ),
        "take_profit": (
            "TP en el siguiente nivel clave de liquidez (máximo/mínimo previo). "
            "En R:R 1:2: si SL = 10 pips, TP = 20 pips. "
            "Considerar cerrar 50% en R:R 1:1 y mover SL a BE para proteger."
        ),
        "regla_3_perdidas": (
            "Si pierdes 3 operaciones seguidas en el mismo día: STOP. "
            "Cerrar la plataforma y analizar qué salió mal. "
            "Retomar al día siguiente con mente fresca."
        ),
    },
    "control_emocional": {
        "overtrading": (
            "El overtrading es el mayor enemigo del scalper. "
            "Operar por aburrimiento, FOMO o por 'recuperar pérdidas' destruye la cuenta. "
            "Plan de trading escrito ANTES de abrir la plataforma — seguirlo sin excepciones."
        ),
        "revenge_trading": (
            "Después de una pérdida: NO entrar inmediatamente a 'recuperar'. "
            "Esperar 10-15 minutos, revisar si la condición del mercado sigue siendo válida. "
            "La mayoría de pérdidas dobles ocurren por revenge trading."
        ),
        "sesgo_confirmacion": (
            "No buscar señales que 'confirmen' la dirección que ya decidiste. "
            "El mercado no sabe lo que tú quieres. Analizar objetivamente."
        ),
        "piramide": [
            "1 (base): Cortar las pérdidas rápido — SL siempre, nunca moverlo",
            "2: Gestionar el capital — 1-2% max por operación",
            "3: Auto-disciplina — seguir el plan aunque no quieras",
            "4: Gestionar las emociones — no operar en estado emocional",
            "5: Evitar la sobre-exposición — no estar en demasiadas posiciones",
            "6 (cima): Planificar a fondo — analizar antes de entrar",
        ],
    },
    "activos_recomendados": {
        "buenos": [
            "US100/NAS100 (Nasdaq 100) — alta liquidez, movimientos limpios",
            "EUR/USD — el par más líquido del mundo, spreads mínimos",
            "GBP/USD — buena volatilidad en sesión de Londres",
            "Gold (XAU/USD) — respeta soportes/resistencias muy bien",
            "S&P 500 (US500) — tendencias fuertes y predecibles",
        ],
        "evitar": [
            "Natural Gas (Natgas) — extremadamente caótico, movimientos erráticos",
            "Crypto en alta volatilidad — spreads amplios, gaps impredecibles",
            "Acciones individuales en pre-market o post-market",
            "Pares exóticos (USD/TRY, USD/ZAR) — spreads muy altos",
        ],
        "criterios": [
            "Alta liquidez (spread bajo, muchos participantes)",
            "Tendencia clara y sostenida durante la sesión",
            "Respeto de soportes, resistencias y Order Blocks",
            "Sin noticias de alto impacto activas (revisar calendario económico)",
        ],
    },
    "indicadores_clave": {
        "ema": (
            "EMA (Exponential Moving Average): más sensible que la SMA, reacciona más rápido. "
            "EMA 9 y EMA 21 para scalping M1-M5. "
            "Precio sobre EMA = sesgo alcista. Precio bajo EMA = sesgo bajista. "
            "Cruce EMA9 > EMA21 = señal de compra. Cruce EMA9 < EMA21 = señal de venta."
        ),
        "rsi": (
            "RSI (Relative Strength Index) — 14 periodos estándar. "
            "< 30: sobrevendido → posible rebote alcista. "
            "> 70: sobrecomprado → posible corrección bajista. "
            "En scalping: usar RSI (7) para más sensibilidad en M1."
        ),
        "bollinger": (
            "Bandas de Bollinger: miden volatilidad del precio. "
            "Precio toca banda superior → resistencia dinámica, posible venta. "
            "Precio toca banda inferior → soporte dinámico, posible compra. "
            "Bandas muy estrechas (squeeze) → expansión de volatilidad inminente."
        ),
        "macd": (
            "MACD (Moving Average Convergence Divergence). "
            "Cruce MACD > señal con histograma positivo → momentum alcista. "
            "Cruce MACD < señal con histograma negativo → momentum bajista. "
            "En scalping M1: configuración (3,10,16) más sensible que el estándar (12,26,9)."
        ),
        "volumen": (
            "Volumen confirma la fuerza de un movimiento. "
            "Ruptura con volumen alto = real (institucionales participando). "
            "Ruptura con volumen bajo = posible fakeout — esperar confirmación."
        ),
        "estocastico": (
            "Oscilador Estocástico (%K y %D): mide posición del precio vs rango reciente. "
            "< 20: zona de sobreventa → %K cruzando hacia arriba %D = señal de COMPRA. "
            "> 80: zona de sobrecompra → %K cruzando hacia abajo %D = señal de VENTA. "
            "Config. para scalping: (5,3,3) rápido o (14,3,3) moderado. "
            "Combinar con RSI para doble confirmación: ambos en sobreventa = entrada fuerte."
        ),
        "sma": (
            "SMA 20: tendencia de corto plazo. "
            "SMA 50: tendencia de mediano plazo. "
            "SMA 200: tendencia de largo plazo (la más respetada por instituciones). "
            "Golden Cross: SMA50 cruza sobre SMA200 = señal alcista mayor. "
            "Death Cross: SMA50 cruza bajo SMA200 = señal bajista mayor."
        ),
    },
    "gestion_tiempo": {
        "concentracion": (
            "El scalping requiere concentración total. "
            "Sin distracciones: cerrar redes sociales, TV, conversaciones. "
            "Una distracción de 30 segundos puede significar una pérdida."
        ),
        "horarios_definidos": (
            "Definir y respetar horarios de trading: "
            "no 'por si acaso' ni 'solo un rato más'. "
            "El mejor scalping es en alta liquidez — no forzar operaciones fuera de ventana."
        ),
        "limite_sesion": (
            "Limitar sesiones de trading a 2-3 horas máximo. "
            "La fatiga mental aumenta drásticamente los errores después de 2 horas. "
            "Si ya alcanzaste el objetivo diario: CERRAR y no operar más ese día."
        ),
        "descansos": (
            "Tomar descansos de 5-10 minutos cada hora. "
            "Si hay 2 pérdidas seguidas: pausar 15 minutos, revisar el sesgo del mercado."
        ),
    },
}

# ── PATRONES CHARTISTAS (XTB Módulo 1 — Gonzalo Muñoz) ───────────────────────
# Los 10 patrones de chartismo de inversión cubiertos en el módulo.
# 5 bajistas + 5 alcistas, cada uno con nombre, señal, descripción, acción y
# fiabilidad según el material XTB.

PATRONES_CHARTISTAS = {
    # ─── BAJISTAS ─────────────────────────────────────────────────────────────
    "doble_techo": {
        "nombre":     "Doble Techo (Double Top)",
        "señal":      "bearish_reversal",
        "descripcion": (
            "El precio alcanza un máximo (techo 1), retrocede al soporte (neckline), "
            "sube de nuevo al mismo nivel pero NO lo supera (techo 2), "
            "y luego rompe el neckline hacia abajo. "
            "Forma visual de 'M'. Los dos techos deben estar al mismo nivel ± 0.5%."
        ),
        "accion": (
            "VENDER en el cierre de la primera vela bajista que rompa el neckline. "
            "SL: ligeramente encima del segundo techo. "
            "TP: distancia entre techo y neckline proyectada hacia abajo (1:1 mínimo)."
        ),
        "target": "Altura del patrón proyectada por debajo del neckline",
        "fiabilidad": "Alta (65-70%) cuando el volumen disminuye en el segundo techo",
    },
    "cabeza_y_hombros": {
        "nombre":     "Cabeza y Hombros (Head & Shoulders)",
        "señal":      "bearish_reversal",
        "descripcion": (
            "Tres picos: hombro izquierdo, cabeza (el más alto), hombro derecho. "
            "Los dos hombros están al mismo nivel. La neckline une los dos valles. "
            "Es uno de los patrones de reversión más fiables del análisis técnico."
        ),
        "accion": (
            "VENDER en la ruptura del neckline con vela de confirmación. "
            "SL: encima del hombro derecho. "
            "TP: distancia cabeza-neckline proyectada desde el punto de ruptura."
        ),
        "target": "Distancia cabeza-neckline proyectada hacia abajo",
        "fiabilidad": "Muy alta (70-75%) — el más fiable de los patrones de reversión bajista",
    },
    "cuña_ascendente": {
        "nombre":     "Cuña Ascendente (Rising Wedge)",
        "señal":      "bearish_reversal",
        "descripcion": (
            "El precio sube pero cada vez con menos fuerza. "
            "Tanto los máximos como los mínimos suben, pero las líneas de tendencia "
            "convergen hacia un punto (cuña). "
            "La presión compradora se agota — los vendedores toman control."
        ),
        "accion": (
            "VENDER en la ruptura de la línea de soporte inferior de la cuña. "
            "SL: encima del último máximo de la cuña. "
            "TP: inicio de la cuña (parte más ancha, proyectada hacia abajo)."
        ),
        "target": "Ancho máximo de la cuña proyectado desde el punto de ruptura",
        "fiabilidad": "Alta (62-68%) — confirmar con volumen decreciente dentro de la cuña",
    },
    "triangulo_expansion_bajista": {
        "nombre":     "Triángulo de Expansión Bajista (Broadening Top)",
        "señal":      "bearish_reversal",
        "descripcion": (
            "El precio hace máximos más altos y mínimos más bajos — ampliando el rango. "
            "Las líneas de tendencia se separan (opuesto al triángulo simétrico). "
            "Indica indecisión y caos. Generalmente resuelve a la baja en tendencia previa alcista."
        ),
        "accion": (
            "VENDER en el rebote hacia la línea de resistencia superior con rechazo. "
            "SL: encima del último máximo. "
            "TP: mínimo inferior del patrón."
        ),
        "target": "Soporte inferior del patrón o el mínimo más bajo registrado",
        "fiabilidad": "Media (55-60%) — menos fiable, requiere confirmación adicional",
    },
    "triple_techo": {
        "nombre":     "Triple Techo (Triple Top)",
        "señal":      "bearish_reversal",
        "descripcion": (
            "Variante reforzada del doble techo. El precio intenta romper la resistencia "
            "3 veces sin lograrlo. Cada intento fallido aumenta la presión vendedora. "
            "Cuando el neckline cede, la caída suele ser más agresiva que en el doble techo."
        ),
        "accion": (
            "VENDER en ruptura del neckline con cierre bajo el mismo. "
            "SL: encima del último techo (tercer techo). "
            "TP: altura del patrón × 1.5 proyectada hacia abajo (R:R favorable)."
        ),
        "target": "Distancia entre techos y neckline × 1.5 proyectada",
        "fiabilidad": "Muy alta (72-78%) — tres rechazos consecutivos = resistencia muy fuerte",
    },
    # ─── ALCISTAS ─────────────────────────────────────────────────────────────
    "doble_suelo": {
        "nombre":     "Doble Suelo (Double Bottom)",
        "señal":      "bullish_reversal",
        "descripcion": (
            "El precio cae a un mínimo (suelo 1), rebota al neckline, "
            "vuelve a caer al mismo nivel sin romperlo (suelo 2), "
            "y luego sube rompiendo el neckline hacia arriba. "
            "Forma visual de 'W'. Espejo del doble techo."
        ),
        "accion": (
            "COMPRAR en el cierre de la primera vela alcista que rompa el neckline. "
            "SL: ligeramente debajo del segundo suelo. "
            "TP: distancia suelo-neckline proyectada hacia arriba."
        ),
        "target": "Altura del patrón proyectada por encima del neckline",
        "fiabilidad": "Alta (65-70%) — confirmar con volumen creciente en la segunda subida",
    },
    "cabeza_y_hombros_invertido": {
        "nombre":     "Cabeza y Hombros Invertido (Inverted H&S)",
        "señal":      "bullish_reversal",
        "descripcion": (
            "Tres valles: hombro izquierdo, cabeza (el más bajo), hombro derecho. "
            "Los dos hombros están al mismo nivel. Señal de que los vendedores se agotan. "
            "La ruptura del neckline hacia arriba confirma la reversión alcista."
        ),
        "accion": (
            "COMPRAR en la ruptura del neckline con cierre sobre el mismo. "
            "SL: debajo del hombro derecho. "
            "TP: distancia cabeza-neckline proyectada hacia arriba desde el punto de ruptura."
        ),
        "target": "Distancia cabeza-neckline proyectada hacia arriba",
        "fiabilidad": "Muy alta (70-75%) — espejo del H&S bajista, igualmente fiable",
    },
    "cuña_descendente": {
        "nombre":     "Cuña Descendente (Falling Wedge)",
        "señal":      "bullish_reversal",
        "descripcion": (
            "El precio baja pero con menos fuerza progresivamente. "
            "Máximos y mínimos descienden, pero las líneas convergen. "
            "La presión vendedora se agota — los compradores toman control gradualmente. "
            "Puede ser patrón de continuación en tendencia alcista o reversión en bajista."
        ),
        "accion": (
            "COMPRAR en la ruptura de la línea de resistencia superior de la cuña. "
            "SL: debajo del último mínimo de la cuña. "
            "TP: inicio de la cuña (parte más ancha, proyectada hacia arriba)."
        ),
        "target": "Ancho máximo de la cuña proyectado desde el punto de ruptura",
        "fiabilidad": "Alta (63-68%) — muy efectiva en correcciones de tendencia alcista",
    },
    "triangulo_expansion_alcista": {
        "nombre":     "Triángulo de Expansión Alcista (Broadening Bottom)",
        "señal":      "bullish_reversal",
        "descripcion": (
            "Máximos más altos y mínimos más bajos ampliando el rango, pero en tendencia "
            "previa bajista. Las líneas se separan hacia abajo. "
            "Indica acumulación institucional. Resuelve alcista al escapar por arriba."
        ),
        "accion": (
            "COMPRAR en el rebote desde la línea de soporte inferior con vela alcista. "
            "SL: debajo del último mínimo. "
            "TP: resistencia superior del patrón."
        ),
        "target": "Resistencia superior del patrón o el máximo más alto registrado",
        "fiabilidad": "Media (55-60%) — confirmar con divergencia alcista en RSI",
    },
    "triple_suelo": {
        "nombre":     "Triple Suelo (Triple Bottom)",
        "señal":      "bullish_reversal",
        "descripcion": (
            "El precio intenta romper el soporte 3 veces sin lograrlo. "
            "Cada rechazo del soporte es más explosivo. "
            "Cuando el neckline se rompe al alza, la subida suele ser fuerte y sostenida."
        ),
        "accion": (
            "COMPRAR en ruptura del neckline con cierre sobre el mismo. "
            "SL: debajo del último suelo (tercer suelo). "
            "TP: altura del patrón × 1.5 proyectada hacia arriba."
        ),
        "target": "Distancia entre suelos y neckline × 1.5 proyectada",
        "fiabilidad": "Muy alta (72-78%) — tres rechazos del soporte = soporte muy fuerte",
    },
}


# ── EQUITI SCALPING GUIDE ──────────────────────────────────────────────────────
# Fuente: "Ebook de Scalping Trading con Ejemplos — Equiti Distrito Financiero"
# Cubre: definición, trading acciones, indicadores, gestión R:R, psicología
# (5 emociones: codicia/miedo/ansiedad/esperanza/disciplina), esperanza matemática

EQUITI_SCALPING = {
    "definicion": (
        "El scalping (Equiti): método de operación para tomar beneficios rápidos en marcos M1-M30. "
        "La ventaja principal es la velocidad: entrar y salir en segundos (no más de pocos minutos). "
        "Variación del day-trading que opera con gran volumen de operaciones ejecutadas. "
        "Requiere: disciplina extrema, concentración total en el gráfico, conexión rápida a internet. "
        "Una gran pérdida puede eliminar muchas horas o días de pequeñas ganancias — gestión de riesgo CRÍTICA. "
        "El scalping ofrece grandes rentabilidades a corto plazo, pero también elevados riesgos."
    ),
    "triple_cruce_muerte": {
        "nombre": "Triple Cruce de la Muerte (EMA 4-18-40)",
        "descripcion": (
            "Configuración clásica usada por scalpers profesionales (Equiti). "
            "Tres EMAs al precio de cierre: período 4 (rápida), 18 (media), 40 (lenta). "
            "Cuando las tres se cruzan en el mismo punto = inicio de nueva tendencia fuerte."
        ),
        "señal_alcista": (
            "EMA4 cruza sobre EMA18 y ambas sobre EMA40 = inicio de tendencia alcista. "
            "Acción: COMPRAR en cierre de vela confirmatorio."
        ),
        "señal_bajista": (
            "EMA4 cruza bajo EMA18 y ambas bajo EMA40 = inicio de tendencia bajista. "
            "Acción: VENDER en cierre de vela confirmatorio."
        ),
        "timeframe": "M5 principalmente; válido también en M1 y M15",
        "par_referencia": "GBP/USD, EUR/USD (alta liquidez)",
        "confirmacion": (
            "Esperar cierre de vela SOBRE/BAJO el cruce antes de entrar. "
            "Usar RSI como filtro adicional: RSI > 50 confirma compra, < 50 confirma venta. "
            "Combinar con SMA200: si el cruce ocurre sobre SMA200 = señal alcista más fuerte."
        ),
        "fiabilidad": (
            "Alta cuando los tres períodos coinciden en la misma dirección. "
            "Fallos frecuentes en mercado lateral — solo operar en tendencia clara."
        ),
    },
    "sma_200_universal": {
        "nombre": "SMA 200 — Soporte y Resistencia Universal",
        "descripcion": (
            "La SMA de 200 períodos es soporte y resistencia independientemente del timeframe: "
            "M1, M5, H1, H4, Diario, Semanal. Es el indicador más respetado globalmente por "
            "institucionales y minoristas. Cuando el precio toca la SMA200, hay REACCIÓN."
        ),
        "uso_scalping": (
            "Precio SOBRE SMA200 = entrar SOLO en compras (no ir contra la tendencia mayor). "
            "Precio BAJO SMA200 = entrar SOLO en ventas. "
            "Toque de SMA200 desde arriba = zona de soporte → oportunidad de compra. "
            "Toque de SMA200 desde abajo = zona de resistencia → oportunidad de venta. "
            "Nunca abrir operación en contra de la SMA200 sin confirmación fuerte."
        ),
        "combinacion": (
            "Ideal con EMA(4,18,40): si el triple cruce confirma la dirección de SMA200 = "
            "señal muy fuerte. Añadir RSI para filtrar sobrecompra/sobreventa."
        ),
    },
    "ichimoku_scalping": {
        "nombre": "Ichimoku Cloud para Scalping M1 (Equiti)",
        "descripcion": (
            "Indicador complejo que muestra soporte, resistencia, tendencia y momentum en uno solo. "
            "Es el indicador más popular entre scalpers profesionales en M1 (según Equiti). "
            "No hay respuesta universal — el trading es personal; úsalo si encaja contigo."
        ),
        "reglas": [
            "Precio SOBRE la nube (Kumo) = tendencia alcista → SOLO entrar en COMPRA",
            "Precio BAJO la nube = tendencia bajista → SOLO entrar en VENTA",
            "Precio DENTRO de la nube = zona de indecisión → EVITAR entrar",
            "Nube VERDE (Senkou A > Senkou B) = soporte fuerte debajo del precio",
            "Nube ROJA (Senkou B > Senkou A) = resistencia fuerte sobre el precio",
            "TK Cross: Tenkan-sen cruza sobre Kijun-sen = señal de compra (en tendencia alcista)",
            "TK Cross: Tenkan-sen cruza bajo Kijun-sen = señal de venta (en tendencia bajista)",
        ],
        "mejor_timeframe": "M1 y M5 para scalping; H1 para contexto macro",
        "nota": (
            "La mayoría de traders profesionales lo usan en M1. "
            "Otros ni lo consideran. El trading es personal — encuentra lo que funciona para ti."
        ),
    },
    "psicologia_5_emociones": {
        "codicia": (
            "ENEMIGA #1 del trading. Si empiezas a apartarte del plan para ganar más → STOP INMEDIATO. "
            "La codicia hace que traders con ganancias terminen con pérdidas totales en una sesión. "
            "Señal de alerta: pensar 'dejo correr un poco más' sin razón técnica. "
            "Solución: objetivo de profit diario definido ANTES de operar. Al llegar, CERRAR Y SALIR."
        ),
        "miedo": (
            "Papel opuesto a la codicia — previene pérdidas catastróficas. "
            "Normal perder dinero y sentir miedo. Pero el exceso paraliza: no ejecutas el plan. "
            "Solución: tamaño de posición pequeño para que las pérdidas no duelan emocionalmente. "
            "Si el miedo persiste, reduce el tamaño hasta que te sientas cómodo con la pérdida máxima."
        ),
        "ansiedad": (
            "Mezcla de codicia y miedo amplificados. El scalping/intraday es especialmente sensible. "
            "Síntomas: revisar el precio cada 10 segundos, cerrar posiciones sin señal técnica, "
            "abrir operaciones por impulso. "
            "Solución: PAUSA obligatoria. 5-10 min de descanso, cabeza despejada antes de continuar. "
            "Regla: 2 pérdidas seguidas → pausa de 15 min mínimo."
        ),
        "esperanza": (
            "La esperanza NO sirve en trading. 'Esperar a que se recupere' es la trampa más peligrosa. "
            "Lo que necesitas es CONFIANZA EN EL SISTEMA, no esperanza emocional. "
            "Ser realista: si el trade va contra ti y tocó el Stop Loss → CERRAR. Sin excusas. "
            "La esperanza elimina el Stop Loss mentalmente → pérdidas ilimitadas."
        ),
        "disciplina": (
            "La emoción más valiosa (la única positiva). "
            "Operar siempre en las mismas ventanas horarias de alta liquidez. "
            "Abrir y cerrar posiciones EXACTAMENTE según lo que indica el sistema, no las emociones. "
            "Los profesionales usan métodos rigurosos: mismo horario, mismas reglas, siempre. "
            "Construir disciplina = construir consistencia = construir rentabilidad a largo plazo."
        ),
        "orden_peligrosidad": [
            "codicia (enemiga #1)",
            "esperanza (trampa #2)",
            "ansiedad",
            "miedo (preventivo pero paralizante)",
            "disciplina (positiva — la única que quieres)",
        ],
    },
    "esperanza_matematica": {
        "concepto": (
            "Cómo controlar la incertidumbre del mercado: pensar en PROBABILIDADES ESTADÍSTICAS. "
            "El mercado es incierto — ningún análisis garantiza certeza en una operación. "
            "La solución profesional: construir un sistema con edge estadístico (ventaja matemática) "
            "y respetarlo rigurosamente en TODAS las operaciones, sin excepción."
        ),
        "formula_mental": (
            "Ejemplo: winrate 60%, R:R 1:2. "
            "En 10 trades: 6 ganas × 2 unidades = +12 | 4 pierdes × 1 = -4. "
            "Resultado neto: +8 unidades. Esa es tu ESPERANZA MATEMÁTICA POSITIVA. "
            "Una operación perdida NO invalida el sistema — las estadísticas necesitan volumen."
        ),
        "regla_clave": (
            "Mantente disciplinado y respeta las reglas del sistema en TODAS las operaciones. "
            "Con el tiempo, las estadísticas se cumplen y la esperanza matemática funciona. "
            "El error fatal: cambiar el sistema después de 2-3 pérdidas seguidas por emociones. "
            "Los sistemas con edge positivo necesitan 50-100 trades para demostrar su ventaja."
        ),
        "incertidumbre_como_aliada": (
            "Los principiantes buscan certeza — no existe en el mercado. "
            "Los profesionales ABRAZAN la incertidumbre y la convierten en ventaja estadística. "
            "Saben que no saben cuál será el próximo trade, pero su sistema tiene probabilidad a su favor. "
            "Abrazar la incertidumbre = panorama más amplio del comportamiento del mercado."
        ),
        "aplicacion_litch": (
            "Para Litch: cada señal del consenso 7-métodos no es certeza, es probabilidad. "
            "Si el sistema dice CALL con 5/7 votos, la probabilidad favorece CALL — no garantiza. "
            "La esperanza matemática funciona con volumen de operaciones, no con una sola."
        ),
    },
    "trading_acciones": {
        "bolsas_principales": ["Wall Street (NYSE/NASDAQ)", "Tokio (TSE)", "Londres (LSE)", "Hong Kong (HKEX)"],
        "determinacion_precio": (
            "Ley de oferta y demanda. Factores que mueven precios: "
            "psicológicos (expectativas), económicos (PIB, inflación), "
            "decisiones estatales (tasas interés), fundamentales de la empresa."
        ),
        "derivados_vs_directas": {
            "derivados_cfds": (
                "Ventajas para scalping: "
                "• Poco apalancamiento vs corredores profesionales. "
                "• Costos bajos — solo pagar el spread del bróker. "
                "• Comprar/vender con un clic en cualquier momento. "
                "• Solo importa la DIRECCIÓN del precio, no los fundamentales de la empresa. "
                "• Posible abrir SHORT (apostar a la baja) fácilmente."
            ),
            "acciones_directas": (
                "Desventajas para scalping: "
                "• Necesitas comprador/vendedor del otro lado (liquidez limitada). "
                "• Las ganancias/pérdidas dependen del desempeño REAL de la compañía. "
                "• Mayor apalancamiento requerido. "
                "• Costos operativos más altos."
            ),
        },
        "volatilidad_acciones": (
            "Las acciones son instrumentos muy volátiles — alto nivel de riesgo. "
            "Para scalping: usar DERIVADOS (CFDs) en vez de acciones directas. "
            "Ventaja: el trader solo está pendiente de la dirección del mercado y "
            "factores fundamentales que afecten el precio — no del desempeño de la empresa."
        ),
        "recomendacion_scalping": (
            "Mejores activos para scalping con derivados: "
            "índices (SPX500, US100/NAS100), forex (GBP/USD, EUR/USD), "
            "materias primas (Gold). Alta liquidez = spreads bajos = mejor para scalping."
        ),
    },
    "indicadores_equiti_resumen": {
        "ichimoku": "M1 — el más popular según Equiti. Precio sobre nube=alcista, bajo nube=bajista.",
        "bollinger": (
            "Expansión de bandas + precio entre banda media y superior = tendencia alcista → COMPRAR. "
            "Precio entre banda inferior y media = tendencia bajista → VENDER. "
            "Contracción de bandas = mercado lateral, esperar expansión antes de entrar."
        ),
        "rsi": (
            "RSI < 30 = sobreventa → esperar confirmación en VELAS para COMPRAR. "
            "RSI > 70 = sobrecompra → esperar confirmación en VELAS para VENDER. "
            "CRÍTICO: el RSI puede quedarse en zona extrema largo tiempo — siempre confirmar con vela."
        ),
        "medias_moviles": (
            "SMA 200: soporte/resistencia universal en todos los timeframes (M1 a semanal). "
            "EMA (4, 18, 40): 'Triple Cruce de la Muerte' — detecta inicio de tendencia. "
            "EMA combos adicionales: 4, 5, 9, 10, 20 según estrategia personal del trader."
        ),
        "macd": (
            "Cruce de línea MACD sobre señal = señal de COMPRA. "
            "Cruce de línea MACD bajo señal = señal de VENTA. "
            "Histograma creciendo = momentum acelerando. "
            "Histograma decreciendo = momentum perdiendo fuerza → posible reversión."
        ),
        "confluencia_ideal": (
            "La señal más fuerte combina: precio sobre SMA200 + triple cruce EMA alcista + "
            "RSI saliendo de sobreventa + MACD cruzando al alza. Cuantos más coincidan, "
            "mayor la probabilidad de éxito del trade."
        ),
    },
    "gestion_riesgo_equiti": {
        "rr_ejemplo": "Perder 10 USD para ganar 20 USD = R:R 1:2",
        "stop_loss": (
            "Stop Loss OBLIGATORIO en cada posición. "
            "Sin SL: riesgo de no poder cerrar manualmente en pérdidas — estas se amplifican dramáticamente. "
            "Es recomendable SL automático, no manual — las emociones impiden cerrarlo a tiempo."
        ),
        "nivel_aceptacion": (
            "Definir ANTES de operar el nivel máximo de pérdida aceptable para la sesión. "
            "Si se alcanza ese nivel → CERRAR TODO y no operar hasta el día siguiente."
        ),
        "objetivo_ganancia": (
            "Definir objetivo de ganancia diaria ANTES de operar. "
            "Al alcanzarlo → SALIR aunque el mercado siga moviendo. "
            "La codicia destruye las ganancias del día cuando no hay objetivo definido."
        ),
    },
}


# ── DINAMITA GRIZZLY — Scalping de Momentum con Volume Profile ───────────────
# Basado en: José María Martín Núñez — Traders Magazine 11/12.2020
# Metodología: Volume Profile, VWAP, microestructuras de mercado
# "Los datos se calculan de forma aritmética, no geométrica" — anti-chartismo cuantitativo

DINAMITA_GRIZZLY = {
    "filosofia": (
        "La operativa de DINAMITA GRIZZLY se basa en datos de mercado en tiempo real "
        "(nivel 1 y nivel 2), interpretados de forma aritmética — NO en geometría ni chartismo. "
        "El chartismo es 'deprecated' (obsoleto). El mercado de 2020+ no funciona como antes."
    ),
    "proceso_operativo": [
        "1. CONTEXTO DIARIO: ver el gráfico diario para identificar la tendencia dominante. "
        "   'Desde lo alto de una montaña' — nunca operar sin conocer la tendencia mayor.",
        "2. TIMEFRAME M60: identificar zonas de valor (VAH, VPOC, VAL) de la semana actual.",
        "3. VWAP: precio más justo del activo. Precio arriba=caro(distribución), abajo=barato(acumulación).",
        "4. DESVIACIONES ESTÁNDAR del VWAP para determinar desequilibrio del precio.",
        "5. VOLUMEN: sin participación institucional = sin señal operable.",
        "6. SOLO APERTURA DE SESIÓN: concentrar operativa en los primeros 30-60 minutos de NY/London.",
    ],
    "volume_profile": {
        "vpoc": "Volume Point of Control — precio con mayor negociación del período. "
                "Actúa como imán de precio. Si el precio está lejos del VPOC, tenderá a volver.",
        "vah":  "Value Area High — límite superior del 70% de la negociación. "
                "Por encima del VAH: mercado CARO (desequilibrio alcista). Esperar distribución.",
        "val":  "Value Area Low — límite inferior del 70% de la negociación. "
                "Por debajo del VAL: mercado BARATO (desequilibrio bajista). Esperar acumulación.",
        "equilibrio": "Precio dentro del VAH-VAL = mercado en EQUILIBRIO. "
                      "En equilibrio el mercado no da señales operables claras. ESPERAR.",
        "desequilibrio": "Precio fuera del VAH-VAL = mercado en DESEQUILIBRIO. "
                         "Los desequilibrios se resuelven: el precio tiende a volver al VPOC.",
    },
    "vwap_operativa": {
        "definicion": "VWAP = precio ponderado por volumen. El precio más justo del activo en el período.",
        "sesgo_alcista": "Precio persistentemente sobre el VWAP = compradores dominantes. "
                         "Solo entrar en largo (SUBE) al tocar el VWAP desde arriba.",
        "sesgo_bajista": "Precio persistentemente bajo el VWAP = vendedores dominantes. "
                         "Solo entrar en corto (BAJA) al tocar el VWAP desde abajo.",
        "desviaciones": "Desviación +1σ y +2σ sobre VWAP = zonas de distribución (probable BAJA). "
                        "Desviación -1σ y -2σ bajo VWAP = zonas de acumulación (probable SUBE).",
    },
    "microestructuras": (
        "El mercado tiene estructura fractal: la tendencia diaria se desglosa en estructuras de M60, "
        "M60 en M15, M15 en M5. Un scalper necesita ver al menos dos timeframes: "
        "el mayor para contexto y el menor para la entrada puntual."
    ),
    "filtros_entrada": [
        "Siempre operar a FAVOR de la tendencia del gráfico diario.",
        "Volumen alto confirma participación institucional — sin volumen, no hay señal.",
        "VPOC como objetivo de precio: si el precio está en VAH, objetivo = VPOC (medio).",
        "VWAP + desviación estándar como zona de entrada de alta probabilidad.",
        "Apertura de sesión NY (15:30 España / 09:30 ET) = mayor volumen y oportunidades.",
    ],
    "activos_recomendados": "Futuros de índices: MiniSP500 (ES), DAX, EUROSTOXX. "
                            "Divisas: EUR/USD, GBP/USD. Alta liquidez = spreads justos.",
    "regla_de_oro": (
        "En tendencia alcista diaria: SOLO COMPRAR (SUBE) cuando el precio retrocede al VPOC o VWAP. "
        "En tendencia bajista diaria: SOLO VENDER (BAJA) cuando el precio sube al VPOC o VWAP. "
        "Contra la tendencia mayor = revenge trading institucional."
    ),
}


# ── MANUAL AVANZADO DE TRADING — Admiral Markets (Juan Enrique Cadiñanos) ────
# Teoría de Dow, Ondas de Elliott, Fibonacci, Análisis Fundamental avanzado
# Gestión monetaria profesional, psicología operativa

MANUAL_AVANZADO = {
    "teoria_dow": {
        "principios": [
            "1. LAS MEDIAS LO DESCUENTAN TODO: el precio ya refleja toda la información disponible.",
            "2. TRES TENDENCIAS: primaria (>1 año), secundaria (3 semanas–3 meses), terciaria (<3 semanas).",
            "3. TRES FASES DE TENDENCIA ALCISTA: Acumulación → Expansión → Agotamiento/Distribución.",
            "4. LAS MEDIAS DEBEN CONFIRMARSE ENTRE SÍ: una sola media no confirma tendencia.",
            "5. VOLUMEN CONFIRMA LA TENDENCIA: en alcista el volumen crece en subidas.",
            "6. TENDENCIA VIGENTE HASTA SEÑAL DE CAMBIO CONFIRMADA: no anticipar giros.",
        ],
        "fases_alcista": {
            "acumulacion": "Informes negativos, pesimismo. Los informados compran en silencio.",
            "expansion":   "Economía mejora, empresas ganan. El público empieza a comprar.",
            "agotamiento": "Euforia máxima, noticias positivas. Los informados VENDEN.",
            "distribucion": "Precios altos pero los 'smart money' ya vendieron. Reversión inminente.",
            "panico":       "Más vendedores que compradores. Bajada acelerada con volumen alto.",
        },
        "aplicacion_scalping": (
            "Para scalping: la tendencia secundaria (M15-H1) es la más relevante. "
            "Identificar en qué fase está para no comprar en 'Agotamiento' ni vender en 'Acumulación'."
        ),
    },
    "ondas_elliott": {
        "estructura": "5 ondas impulsivas (1-2-3-4-5) en dirección de la tendencia + 3 correctivas (A-B-C).",
        "reglas_inquebrantables": [
            "La onda 2 NUNCA retrocede más allá del inicio de la onda 1.",
            "La onda 3 NUNCA es la más corta (generalmente la más larga y fuerte).",
            "La onda 4 NO se solapa con la onda 1 (excepto en cuñas diagonales).",
        ],
        "fibonacci_elliot": (
            "La onda 3 suele extenderse al 161.8% de la onda 1. "
            "La onda 5 suele igualar a la onda 1 si la 3 es la más extendida. "
            "Correcciones A-B-C suelen terminar en retroceso del 61.8% de la onda impulso."
        ),
        "uso_practico": (
            "Cuando la onda 3 falla en el recuento → salir de posición inmediatamente. "
            "El fallo de recuento ES la señal de stop loss — nunca ignorarla. "
            "Elliott permite gestionar el riesgo ANTES de la operación."
        ),
        "aplicacion_scalping": (
            "En scalping: identificar si estamos en onda 3 (la más poderosa) para operar con el impulso, "
            "o en onda 4-5 / corrección A-B-C para operar reversión o quedarse fuera."
        ),
    },
    "fibonacci": {
        "niveles_clave": "23.6% — 38.2% — 50% — 61.8% (Golden Ratio) — 76.4% — 100%",
        "uso_soporte": (
            "En tendencia alcista: los retrocesos al 38.2%, 50% o 61.8% son zonas de compra (SUBE). "
            "El 61.8% es el 'Golden Ratio' — si el precio lo perfora a la baja, la tendencia alcista termina."
        ),
        "uso_resistencia": (
            "Extensiones Fibonacci: 127.2%, 161.8%, 200%, 261.8%. "
            "Son objetivos de precio para operaciones con tendencia (take profit)."
        ),
        "throw_back_pull_back": (
            "Throw Back: precio rompe resistencia, sube, vuelve a la zona de rotura y rebota (confirmación). "
            "Pull Back: precio rompe soporte, baja, vuelve a la zona de rotura y cae (confirmación). "
            "Son las entradas con mejor relación riesgo/recompensa en el análisis técnico clásico."
        ),
        "regla_oro": (
            "Si un retroceso perfora el 61.8% con fuerza y cierra debajo: "
            "el movimiento previo ha terminado — buscar el lado contrario."
        ),
    },
    "analisis_fundamental_conceptos": {
        "dcf": "Discounted Cash Flow — valor actual de flujos futuros. Base de la valoración de empresas.",
        "per": "Price to Earnings Ratio. PER alto = cara, PER bajo = barata (relativo al sector).",
        "ev_ebitda": "Enterprise Value / EBITDA. Comparación entre empresas con diferentes estructuras de deuda.",
        "price_to_book": "P/BV < 1 → posible infravaloración. Útil en bancos y empresas con activos tangibles.",
        "catalogo_macro": [
            "PIB (GDP): crecimiento económico — positivo para acciones del país.",
            "Inflación CPI: alta inflación → bancos centrales suben tasas → presión sobre acciones.",
            "Desempleo NFP: baja tasa = economía fuerte. NFP americano mueve el mercado el primer viernes del mes.",
            "Tasas de interés FED/BCE: subidas de tasas = fortaleza moneda, presión acciones tecnológicas.",
            "PMI manufacturero/servicios: >50 expansión, <50 contracción.",
        ],
    },
    "gestion_monetaria_profesional": {
        "regla_1_pct": (
            "Nunca arriesgar más del 1-2% del capital total en un solo trade. "
            "Con $1000 de capital: máximo $10-20 de riesgo por operación."
        ),
        "relacion_rr": (
            "Mínimo 1:2 de riesgo/recompensa. Si arriesgas 10, el objetivo debe ser ganar 20+. "
            "Con winrate del 40% y RR 1:2 ya eres rentable a largo plazo."
        ),
        "formula_posicion": (
            "Tamaño de posición = (Capital × %_riesgo) / (precio_entrada - stop_loss). "
            "Ejemplo: $10.000 × 1% / $50 de stop = 2 lotes."
        ),
        "etapas_trader": [
            "1. NOVATO: opera por intuición, sin sistema. Pierde dinero.",
            "2. CONSCIENTE INCOMPETENTE: sabe que no sabe — empieza a estudiar.",
            "3. CONSCIENTE COMPETENTE: aplica reglas pero con esfuerzo consciente.",
            "4. EXPERTO INCONSCIENTE: las reglas son automáticas. Consistentemente rentable.",
        ],
        "errores_comunes": [
            "Operar sin stop loss definido ANTES de entrar.",
            "Mover el stop loss en contra (dejar correr pérdidas).",
            "Cerrar ganancias demasiado pronto por miedo.",
            "Aumentar el tamaño de posición después de pérdidas (revenge trading).",
            "Operar en mercados sin liquidez suficiente.",
            "Ignorar el contexto macroeconómico (noticias, earnings).",
        ],
    },
}


# ── FRANCISCA SERRANO — Escuela de Bolsa: Manual de Trading ──────────────────
# Libro: "Como ganar 2000 dólares al mes en dos horas de trabajo al día" (2013)
# Enfoque: Day trading disciplinado, psicología, liquidez, Jesse Livermore

FRANCISCA_SERRANO = {
    "filosofia_base": (
        "Según el estudio Barber-Lee-Liu (2011, bolsa de Taiwan 1992-2006): "
        "solo 27 de cada 10.000 traders logran rentabilidad consistente. "
        "El éxito NO depende de los conocimientos técnicos — depende de la ACTITUD: "
        "cómo el trader enfrenta el beneficio, la pérdida, el miedo y la codicia. "
        "La disciplina en el control del riesgo es la única ventaja real."
    ),
    "reglas_livermore": [
        "CORTAR PÉRDIDAS DE RAÍZ: 'Los beneficios debemos conservarlos, las pérdidas evitarlas y cortarlas desde el comienzo' — Jesse Livermore.",
        "AUMENTAR EN GANANCIAS: Añadir posición cuando la operación va a favor. Reducir cuando va en contra.",
        "NO OPERAR CHICHARROS: Solo activos con alta liquidez — los 'blue chips' del mercado.",
        "HORARIO DEFINIDO: La bolsa de Madrid opera de 09:00 a 17:30. NYSEdel abre 15:30-22:00 ET. Respetar horarios.",
        "PATRONES SE REPITEN: El mercado tiene comportamientos cíclicos. La historia no se repite igual pero sí rima.",
        "LOS PRECIOS LO DESCUENTAN TODO: No hay secretos — la información ya está en el precio.",
    ],
    "liquidez_importancia": {
        "concepto": "Liquidez = capacidad de comprar/vender sin mover el precio y a spreads justos.",
        "blue_chips": (
            "Blue chips = empresas de mayor capitalización y liquidez. "
            "Forex equivalente: EUR/USD, GBP/USD, USD/JPY. "
            "En opciones binarias: los pares de mayor liquidez dan señales más confiables."
        ),
        "chicharros_peligro": (
            "Chicharros = activos con poca liquidez. Cuando suben o bajan lo hacen extremo. "
            "El spread es amplio y cuesta más entrar/salir. EVITAR para scalping."
        ),
        "regla_liquidez": (
            "Para scalping: solo operar en el top 5 de activos más líquidos del broker. "
            "Más liquidez = más predecible = más señales con edge real."
        ),
    },
    "psicotrading": {
        "enemigo_principal": "TÚ MISMO. El mayor problema del trader es su propia mente.",
        "miedo": (
            "El miedo cierra las operaciones ganadoras demasiado pronto. "
            "Solución: definir el take profit ANTES de entrar y no moverlo por miedo."
        ),
        "codicia": (
            "La codicia mantiene operaciones ganadoras abiertas hasta que se vuelven perdedoras. "
            "Solución: respetar el objetivo de ganancia definido. Una vez cumplido, CERRAR."
        ),
        "objetivo_diario": (
            "Definir objetivo de ganancia DIARIO antes de operar. "
            "Al alcanzarlo: PARAR aunque el mercado siga. "
            "Ejemplo: si el objetivo es $200/día, al llegar → cerrar el ordenador."
        ),
        "revenge_trading": (
            "Después de una pérdida: PARAR. No operar nunca con el objetivo de 'recuperar'. "
            "El revenge trading es la causa #1 de destrucción de cuentas."
        ),
        "dos_horas_disciplina": (
            "Es posible ganar $2000/mes con solo 2 horas de trabajo diario. "
            "La clave no es operar más tiempo sino operar con DISCIPLINA. "
            "Más tiempo frente a la pantalla sin sistema = más pérdidas, no más ganancias."
        ),
    },
    "mercado_primario_secundario": {
        "primario": "Donde se emiten acciones (IPO, ampliaciones de capital). Empresas captan dinero.",
        "secundario": "Donde se compran/venden títulos ya emitidos. El precio lo fija la oferta y demanda.",
        "bolsas_mundiales": {
            "europa":  "FTSE 100 (UK), DAX 30 (Alemania), CAC 40 (Francia), IBEX 35 (España)",
            "america": "Dow Jones, S&P 500, NASDAQ (EE.UU.), Bovespa (Brasil), IPC (México)",
            "asia":    "Nikkei 225 (Japón), Hang Seng (Hong Kong), Shanghai Composite (China)",
        },
    },
}


# ── 151 ESTRATEGIAS DE TRADING — Kakushadze & Serur (2018/2019) ───────────────
# 398 páginas, +550 fórmulas matemáticas, todas las clases de activos
# Enfoque: estrategias cuantitativas, machine learning, arbitraje estadístico

ESTRATEGIAS_CUANTITATIVAS = {
    "definicion_estrategia": (
        "Una estrategia de trading = conjunto de instrucciones para lograr ciertas tenencias "
        "de activos en momentos determinados t1, t2... El objetivo: retornos positivos. "
        "Pero también existen estrategias de cobertura que son parte de un plan mayor."
    ),
    "tipos_estrategia": {
        "momentum": (
            "Comprar lo que ha subido, vender lo que ha bajado. "
            "Se basa en la persistencia de tendencias (Hurst > 0.55). "
            "Funciona mejor en mercados trending con ADX > 25. "
            "En scalping: seguir la dirección de la EMA rápida (4-9 períodos)."
        ),
        "mean_reversion": (
            "Comprar lo que ha bajado mucho, vender lo que ha subido mucho. "
            "Se basa en la anti-persistencia (Hurst < 0.45). "
            "Funciona mejor en mercados ranging (ADX < 20). "
            "En scalping: usar Bollinger Bands, RSI extremo, Stochastic."
        ),
        "arbitraje_estadistico": (
            "Explotar desviaciones temporales de precios que históricamente están correlacionados. "
            "Ejemplo: EUR/USD y GBP/USD suelen moverse juntos. "
            "Cuando divergen más de lo normal → esperar convergencia."
        ),
        "machine_learning": (
            "Redes neuronales (CNN, LSTM, MLP), Bayes, K-vecinos más cercanos. "
            "Identifican señales débiles que individualmente no son operables. "
            "La combinación de miles de señales débiles amplifica la señal operable. "
            "El modelo de Litch (7 métodos de consenso) sigue este principio."
        ),
    },
    "principios_matematicos_clave": {
        "eficiencia_mercado": (
            "Los mercados son 'casi eficientes' — no perfectamente. "
            "Las ineficiencias existen pero son fugaces. "
            "Las estrategias que funcionan hoy pueden dejar de funcionar mañana. "
            "Por eso Litch usa aprendizaje continuo (RL-DQN, Red Maestra)."
        ),
        "diversificacion_estadistica": (
            "Combinar múltiples señales no correlacionadas reduce el error de predicción. "
            "Por eso el consenso de 7 métodos es más robusto que cualquier método solo. "
            "Correlación entre métodos <0.3 = máxima diversificación estadística."
        ),
        "overfitting_warning": (
            "Riesgo de sobre-ajuste: un modelo que funciona perfectamente en datos históricos "
            "pero falla en datos nuevos. Solución: validación out-of-sample y regularización. "
            "La Red Maestra de Litch usa dropout y L2 para evitar overfitting."
        ),
        "drawdown_y_kelly": (
            "Drawdown máximo aceptable = 20% del capital. Si superas el 20%, PARAR y revisar el sistema. "
            "Criterio de Kelly: f* = p - (1-p)/payout. Con payout 0.85: necesitas >54% winrate para ser rentable. "
            "Apostar más que Kelly × 2 duplica el riesgo de ruina sin aumentar retornos esperados."
        ),
        "esperanza_matematica_trading": (
            "EV = (prob_ganancia × ganancia) - (prob_pérdida × pérdida). "
            "Ejemplo: WR=60%, ganancia $85 (85% payout), pérdida $100: "
            "EV = 0.60×85 - 0.40×100 = 51 - 40 = +$11 por operación. "
            "Si EV < 0 → el sistema es perdedor aunque ganes operaciones individuales."
        ),
    },
    "regimenes_mercado_cuantitativos": {
        "trending_formal": (
            "ADX > 25, Hurst > 0.55, baja entropía de permutación (<0.70). "
            "Usar: MACD, EMA crossovers, momentum, OBV, seguimiento de tendencia."
        ),
        "ranging_formal": (
            "ADX < 20, Hurst < 0.50, entropía moderada (0.65-0.85). "
            "Usar: RSI extremos, Bollinger Bands, Stochastic, reversión a la media."
        ),
        "chaotic_formal": (
            "Entropía de permutación > 0.90 (casi aleatoria). "
            "NINGUNA estrategia tiene edge estadístico. PARAR. "
            "Esperar a que el mercado vuelva a trending o ranging."
        ),
        "transicion": (
            "Cuando el ADX pasa de <20 a >25 = inicio de tendencia. "
            "Las primeras velas de la tendencia tienen el mejor ratio riesgo/recompensa. "
            "El momento exacto de la transición es cuando el sistema gana más."
        ),
    },
    "estrategias_aplicables_binarias": {
        "momentum_scalping": (
            "Operar en dirección del momentum cuando ADX > 25 y EMA(4) > EMA(18) > EMA(40). "
            "Entrada: tras un retroceso al EMA18 en tendencia alcista. "
            "Stop: cierre bajo EMA40. Target: extensión 1.618 del impulso previo."
        ),
        "reversión_rsi_bb": (
            "Operar reversión cuando RSI < 25 Y precio toca banda inferior Bollinger. "
            "Confirmar con Stochastic %K < 18 y %D < 25. "
            "No usar en trending fuerte (ADX > 35) — las reversiones fallas en tendencia fuerte."
        ),
        "filtro_vwap": (
            "Solo entrar en LARGO cuando el precio está SOBRE el VWAP y retrocede hacia él. "
            "Solo entrar en CORTO cuando el precio está BAJO el VWAP y sube hacia él. "
            "Operar contra el VWAP sin confirmación = peor ratio entrada/salida."
        ),
    },
}


# ── 5 PASOS SCALPING CRIPTOMONEDAS — Semillero de Ingresos ───────────────────
# Aplicable a cualquier activo con alta volatilidad: crypto, forex, índices

SCALPING_5_PASOS = {
    "concepto_scalping": (
        "Scalping = operaciones en segundos a pocos minutos buscando movimientos pequeños. "
        "NO significa duplicar la cuenta rápido — significa GESTIONAR el capital con precisión. "
        "La ventaja del scalping: sin overnight risk, resultados inmediatos, pérdidas pequeñas."
    ),
    "ventajas": [
        "Resultados inmediatos (ganancias o pérdidas se ven al instante).",
        "Sin riesgo de mercado nocturno (overnight) — cierre diario total.",
        "Pérdidas por operación muy pequeñas (objetivos pequeños = stops pequeños).",
        "Alta liquidez: fácil entrar y salir en cualquier momento.",
    ],
    "desventajas_y_soluciones": {
        "comisiones": "Las comisiones erosionan ganancias. Solución: broker con spreads bajos, pocos trades de alta calidad.",
        "estres": "El scalping es mentalmente agotador. Solución: máximo 2 horas de operativa diaria.",
        "precision": "Requiere mayor precisión que swing trading. Solución: zonas de trabajo predefinidas.",
        "recuperacion_emocional": "No hay tiempo para procesar pérdidas. Solución: stop automático tras 2 pérdidas seguidas.",
    },
    "pasos_operativos": {
        "paso1_zonas": (
            "DEFINIR ZONAS DE TRABAJO antes de abrir el mercado. "
            "Ir de mayor a menor temporalidad: D1 (tendencia) → H1 (zonas clave) → M5 (entrada). "
            "Trazar soportes y resistencias relevantes en H1/H4, luego micro-tendencias en M5."
        ),
        "paso2_micro_tendencia": (
            "Identificar micro-tendencias o formaciones claras en M15 o M5. "
            "Solo operar cuando hay dirección clara — no en mercado lateral sin volumen."
        ),
        "paso3_objetivo": (
            "Proyectar objetivo alcanzable de 1-2% del precio (o equivalente en pips/puntos). "
            "No apuntar a movimientos enormes — el scalping se construye con acumulación de pequeñas ganancias."
        ),
        "paso4_herramientas": [
            "Escáner de volumen: confirmar que hay participación real en el movimiento.",
            "Patrones de velas japonesas: confirmar reversión o continuación antes de entrar.",
            "Profundidad de mercado (Nivel 2): ver dónde están las órdenes institucionales.",
            "Volume Profile: VPOC como zona de confluencia (DINAMITA GRIZZLY).",
        ],
        "paso5_gestion": (
            "Stop Loss SIEMPRE definido antes de entrar. "
            "Ratio R:R mínimo 1:1.5 en scalping (para superar el costo de la opción binaria con payout 85%). "
            "Objetivo diario definido. Al cumplirlo: PARAR. No intentar más."
        ),
    },
    "por_que_criptomonedas_y_forex": (
        "Alta volatilidad = movimientos erráticos en temporalidades largas pero PREDECIBLES en corto. "
        "El scalping en volatilidad alta permite objetivos alcanzables en minutos "
        "que serían imposibles en activos de baja volatilidad."
    ),
    "dominio_plataforma": (
        "El dominio de la plataforma marca la diferencia entre un scalping exitoso y un fracaso. "
        "Practicar en demo hasta que la ejecución sea automática — sin dudar en los clicks. "
        "Un segundo de duda en scalping puede significar la diferencia entre ganar y perder."
    ),
}


def resumen_sesion_actual() -> str:
    """Devuelve qué sesión está activa ahora y recomendación."""
    import time as _t
    hora_utc = int(_t.strftime("%H"))

    if 0 <= hora_utc < 8:
        s = SESIONES["tokyo"]
        rec = "Baja volatilidad. Bueno para preparar órdenes, no para scalping agresivo."
    elif 8 <= hora_utc < 13:
        s = SESIONES["london"]
        rec = "Muy bueno para scalping. Londres abrió — busca breakouts."
    elif 13 <= hora_utc < 17:
        s = SESIONES["solapamiento_ldn_ny"]
        rec = "MEJOR MOMENTO DEL DÍA. Máxima liquidez. Scalping y seguimiento de tendencia."
    elif 17 <= hora_utc < 22:
        s = SESIONES["nueva_york"]
        rec = "NYSE activo. Bueno para acciones. 15:00-16:00 ET cuidado con volatilidad de cierre."
    else:
        rec = "Mercado tranquilo. Pre-sesión asiática. Preparar análisis para mañana."
        return rec

    return f"Sesión activa: {s['nombre']}. {rec}"
