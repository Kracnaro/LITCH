"""
escuela_ibkr.py — Todo lo que Litch sabe de Interactive Brokers, y cómo
te lo enseña poco a poco.

Este módulo es dos cosas a la vez:

  1. UNA BASE DE CONOCIMIENTO de las herramientas reales de TWS: qué hace
     cada una, para qué sirve de verdad, y —esto es lo importante— cuáles
     le convienen a alguien que empieza con poco capital y cuáles no.

  2. UNA ESCUELA POR LECCIONES. Litch lleva la cuenta de lo que usted ya
     ha visto y le propone lo siguiente. No suelta un manual de 300
     páginas: enseña una cosa, comprueba que se entendió, sigue.

POR QUÉ ESTÁ ESCRITO ASÍ
────────────────────────
Interactive Brokers es una plataforma profesional, y eso significa que
tiene decenas de funciones que un principiante no necesita y algunas que
le pueden hacer daño. Marcar cada herramienta con su nivel y su riesgo no
es paternalismo: es la diferencia entre una herramienta y una trampa.

Cuando una función es peligrosa, aquí se dice por qué, no solo que lo es.
"""

from __future__ import annotations

import json
import os
import time

_RUTA_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUTA_PROG = os.path.join(_RUTA_PROJ, "MEMORIA_AP", "escuela_ibkr.json")


# ═══════════════════════════════════════════════════════════════════════════
#  HERRAMIENTAS DE TWS
# ═══════════════════════════════════════════════════════════════════════════
# nivel: 1 = imprescindible al empezar · 2 = útil pronto · 3 = avanzado
# riesgo: bajo / medio / alto

HERRAMIENTAS = {
    # ── Lo básico ───────────────────────────────────────────────────────────
    "watchlist": {
        "nombre": "Lista de vigilancia (Watchlist)",
        "nivel": 1, "riesgo": "bajo",
        "donde": "Panel izquierdo del Mosaico. Escriba un símbolo y Enter.",
        "que": "La lista de activos que sigue, con su precio en vivo.",
        "porque": ("Es su punto de partida. Antes de operar algo hay que "
                   "haberlo mirado durante días. Poner un activo aquí y "
                   "observarlo una semana enseña más que veinte vídeos."),
    },
    "grafico": {
        "nombre": "Gráfico (Chart)",
        "nivel": 1, "riesgo": "bajo",
        "donde": "Clic derecho sobre un símbolo → Charts → New Chart.",
        "que": "Las velas del precio, con indicadores si los añade.",
        "porque": ("Donde se lee la tendencia. Empiece con velas diarias: "
                   "los gráficos de un minuto son ruido y lo van a marear."),
    },
    "ticket_orden": {
        "nombre": "Entrada de órdenes (Order Ticket)",
        "nivel": 1, "riesgo": "medio",
        "donde": "Panel de Order Entry, o clic en el precio de compra/venta.",
        "que": "Donde se define qué comprar, cuánto y a qué precio.",
        "porque": ("El formulario que mueve el dinero. Cada campo importa. "
                   "Es el que le enseño campo por campo con la lección "
                   "guiada."),
    },
    "cartera": {
        "nombre": "Cartera (Portfolio)",
        "nivel": 1, "riesgo": "bajo",
        "donde": "Pestaña Portfolio, normalmente abajo.",
        "que": "Lo que tiene ahora mismo y cuánto gana o pierde cada cosa.",
        "porque": ("Mirarla demasiado es contraproducente: ver el número "
                   "rojo cada cinco minutos empuja a cerrar operaciones "
                   "buenas antes de tiempo. Revísela dos o tres veces al día."),
    },
    "ordenes": {
        "nombre": "Órdenes (Orders / Trades)",
        "nivel": 1, "riesgo": "bajo",
        "donde": "Pestaña Orders, junto a Portfolio.",
        "que": "Sus órdenes pendientes, ejecutadas y canceladas.",
        "porque": ("Aquí se comprueba que una orden entró de verdad. Dar por "
                   "hecho que entró sin mirarlo es un error caro."),
    },

    # ── Tipos de orden ──────────────────────────────────────────────────────
    "orden_limite": {
        "nombre": "Orden LMT (límite)",
        "nivel": 1, "riesgo": "bajo",
        "donde": "Campo TIPO del ticket → LMT.",
        "que": "Compra solo a su precio o mejor. Si no llega, no se ejecuta.",
        "porque": ("La orden que debería usar casi siempre. Usted decide el "
                   "precio, no el mercado. Puede quedarse sin entrar, y eso "
                   "está bien: no entrar nunca le ha arruinado a nadie."),
    },
    "orden_mercado": {
        "nombre": "Orden MKT (a mercado)",
        "nivel": 2, "riesgo": "alto",
        "donde": "Campo TIPO del ticket → MKT.",
        "que": "Compra ya, al precio que haya.",
        "porque": ("Parece la más simple y por eso engaña. En un momento de "
                   "poca liquidez puede ejecutarse muy lejos del precio que "
                   "vio. En la apertura y el cierre es donde más daño hace. "
                   "Úsela solo para SALIR de algo con urgencia."),
    },
    "stop_loss": {
        "nombre": "Stop de pérdidas (STP)",
        "nivel": 1, "riesgo": "bajo",
        "donde": "Campo TIPO → STP, o dentro de un bracket.",
        "que": "Vende automáticamente si el precio cae hasta su límite.",
        "porque": ("Lo que convierte una pérdida en un gasto conocido. Sin "
                   "stop, su pérdida máxima es todo. Entrar sin saber dónde "
                   "va a salir es la definición de apostar."),
    },
    "bracket": {
        "nombre": "Orden Bracket (entrada + stop + objetivo)",
        "nivel": 2, "riesgo": "bajo",
        "donde": ("Botón «avanzado +» del ticket → «Attach Stop Loss/Profit "
                  "Taker/Bracket» → marcar la casilla «Bracket». Profit "
                  "Taker y Stop Loss se marcan solos. Luego ponga el precio "
                  "límite del objetivo y, en STP PRC, el del stop. "
                  "(Documentación oficial de IBKR.)"),
        "que": "Tres órdenes atadas: entrada, stop de pérdida y toma de "
               "ganancia. Si salta una, la otra se cancela sola.",
        "porque": ("La forma profesional de entrar. Decide las tres cosas "
                   "estando tranquilo, antes de tener dinero en juego. "
                   "Cuando el precio se mueve en contra, uno no piensa bien: "
                   "el bracket piensa por usted de antemano. Es lo que "
                   "construye Litch cuando prepara una operación."),
    },
    "trailing_stop": {
        "nombre": "Stop dinámico (Trailing Stop)",
        "nivel": 3, "riesgo": "medio",
        "donde": "Campo TIPO → TRAIL.",
        "que": "Un stop que sube solo cuando el precio sube, pero no baja.",
        "porque": ("Sirve para dejar correr una ganancia sin devolverla "
                   "entera. Si lo pone muy pegado, el ruido normal del "
                   "mercado le saca de una operación que iba bien."),
    },

    # ── Herramientas de análisis ────────────────────────────────────────────
    "profundidad": {
        "nombre": "Profundidad de mercado (Level II)",
        "nivel": 3, "riesgo": "bajo",
        "donde": "Clic derecho en el símbolo → Market Depth.",
        "que": "Las órdenes de compra y venta esperando en cada precio.",
        "porque": ("Muy útil para quien opera en segundos, casi inútil para "
                   "quien opera en días. Además, en acciones se puede "
                   "manipular con órdenes falsas que se retiran. No se fíe "
                   "de ella como señal."),
    },
    "escaner": {
        "nombre": "Escáner de mercado (Market Scanner)",
        "nivel": 2, "riesgo": "medio",
        "donde": "Menú Analytical Tools → Market Scanner.",
        "que": "Filtra miles de acciones por criterios: las que más suben, "
               "más volumen, etc.",
        "porque": ("Buena herramienta con un peligro: la lista de 'las que "
                   "más suben hoy' es una lista de cosas que ya subieron. "
                   "Perseguirlas es comprar caro. Úselo para descubrir, "
                   "nunca para decidir."),
    },
    "calendario": {
        "nombre": "Calendario de resultados y eventos",
        "nivel": 2, "riesgo": "bajo",
        "donde": "Menú Analytical Tools, o pestaña de noticias del activo.",
        "que": "Cuándo publica resultados cada empresa y qué datos "
               "macroeconómicos salen.",
        "porque": ("Saber que mañana su acción publica resultados le evita "
                   "el susto de un salto del 10% de la noche a la mañana. "
                   "Un stop no protege contra un hueco de apertura: el "
                   "precio simplemente aparece más abajo."),
    },
    "riskNavigator": {
        "nombre": "Risk Navigator",
        "nivel": 3, "riesgo": "bajo",
        "donde": "Menú Analytical Tools → Risk Navigator.",
        "que": "Analiza el riesgo conjunto de toda su cartera.",
        "porque": ("Enseña algo que no se ve mirando posición por posición: "
                   "si tiene cinco tecnológicas, no tiene cinco apuestas, "
                   "tiene una apuesta cinco veces. Eso se llama correlación "
                   "y arruina a mucha gente que se creía diversificada."),
    },

    # ── Configuración ───────────────────────────────────────────────────────
    "api": {
        "nombre": "Configuración de la API",
        "nivel": 2, "riesgo": "medio",
        "donde": "File → Global Configuration → API → Settings.",
        "que": "Permite que un programa como Litch se conecte a TWS.",
        "porque": ("Necesaria para que yo lea datos exactos. El puerto 7497 "
                   "es la cuenta simulada y el 7496 la real: confundirlos es "
                   "el error que hay que evitar a toda costa. Deje "
                   "'Read-Only API' activado mientras aprende."),
    },
    "paper": {
        "nombre": "Cuenta simulada (Paper Trading)",
        "nivel": 1, "riesgo": "bajo",
        "donde": "Al iniciar sesión, o menú Account → Paper Trading.",
        "que": "Dinero ficticio con precios reales. Su cuenta DUR328203.",
        "porque": ("Donde debe estar hasta que tenga meses de resultados. "
                   "Tiene un límite que conviene conocer: sus órdenes no "
                   "afectan al mercado y siempre encuentran contrapartida, "
                   "así que en la simulación todo entra más fácil de lo que "
                   "entrará de verdad."),
    },
    # ── Añadidas tras mapear la serie oficial de tutoriales de IBKR ─────────
    "presets": {
        "nombre": "⚠ Presets (los valores por defecto de cada orden)",
        "nivel": 1, "riesgo": "alto",
        "donde": "Edit → Global Configuration → Presets, por tipo de activo.",
        "que": ("Lo que TWS rellena solo en cada orden nueva: cantidad, tipo "
                "de orden y tiempo en vigor."),
        "porque": ("La documentación oficial de IBKR lo dice textualmente: "
                   "por defecto un ticket de compra de acciones se rellena "
                   "con CIEN ACCIONES, orden límite, y el límite puesto en "
                   "el ask.\n\n"
                   "Con SPY cerca de 679 dólares, cien acciones son 67.900 "
                   "dólares: veintidós veces su cuenta entera. Cada ticket "
                   "que abra sin cambiar la cantidad le propone eso.\n\n"
                   "No es un fallo: ese valor está pensado para cuentas "
                   "mucho mayores que la suya, y nadie se lo va a ajustar. "
                   "Póngalo en 1, tipo LMT y vigencia DAY. Si se equivoca, "
                   "hay un botón «Revert to Defaults».\n\n"
                   "Y dos avisos: los presets se COMPARTEN entre IBKR "
                   "Desktop y TWS, así que cambiarlo en uno lo cambia en el "
                   "otro. Y la lección oficial enseña a ponerlo en 300 "
                   "acciones con orden a MERCADO — correcto para el público "
                   "al que va dirigida, demoledor para usted. Si sigue ese "
                   "vídeo al pie de la letra, se está configurando una "
                   "trampa."),
    },
    "orden_watchlist": {
        "nombre": "⚠ Un clic en el Bid o Ask abre un ticket de orden",
        "nivel": 1, "riesgo": "alto",
        "donde": "La columna de precios de su lista de vigilancia.",
        "que": ("Pulsar el precio de compra o de venta en la watchlist abre "
                "directamente el ticket de Rapid Order Entry."),
        "porque": ("Esto sorprende a todo el mundo la primera vez. Uno cree "
                   "que está pulsando un precio para ver detalles, y lo que "
                   "ha hecho es empezar a preparar una compra. El ticket "
                   "sale ya relleno con sus Presets — otra razón para "
                   "dejarlos en cantidad 1.\n\n"
                   "No es peligroso por sí solo, porque todavía hay que "
                   "enviar. Se vuelve peligroso si además tiene el estilo "
                   "Rapid Transmit, que no tiene botón de enviar."),
    },
    "atajos": {
        "nombre": "⚠ Atajos de teclado y ventana de orden rápida",
        "nivel": 3, "riesgo": "alto",
        "donde": "Configure → Hotkeys, y la ventana de orden rápida.",
        "que": "Enviar órdenes con una tecla, sin pasar por el ticket.",
        "porque": ("Existen para quien hace decenas de operaciones al día y "
                   "necesita velocidad. Usted hace tres a la semana. Para "
                   "usted la velocidad no es una ventaja: elimina justo los "
                   "segundos en los que uno se da cuenta de que se estaba "
                   "equivocando. Un atajo mal pulsado no pregunta. No los "
                   "configure mientras aprende."),
    },
    "orden_grafico": {
        "nombre": "⚠ Crear y mover órdenes desde el gráfico",
        "nivel": 2, "riesgo": "alto",
        "donde": ("Ratón al borde derecho del gráfico, dentro: aparece "
                  "«Place Order» con un +. Se pulsa y se elige Buy o Sell. "
                  "Las órdenes se ven como líneas: AZUL compra, ROJA venta. "
                  "La X a la derecha de la cantidad las cancela."),
        "que": ("Crear, ver y mover órdenes directamente sobre las velas."),
        "porque": ("Para VER dónde están sus órdenes respecto al precio es "
                   "excelente. El problema es moverlas, y aquí la "
                   "documentación de IBKR es escalofriante. Cita textual "
                   "sobre arrastrar una orden en el gráfico:\n\n"
                   "«La orden original se cancela y la nueva se transmite "
                   "INSTANTÁNEAMENTE, lo que significa que la vista previa "
                   "se actualiza al momento y EL USUARIO NO TIENE "
                   "OPORTUNIDAD DE HACER NINGÚN OTRO CAMBIO ANTES DE QUE LA "
                   "ORDEN SE ENVÍE.»\n\n"
                   "Sin confirmación. Sin rectificación. Un resbalón del "
                   "ratón sobre la línea de su stop y el stop se ha movido, "
                   "ya enviado. Si lo arrastra hacia abajo en una compra, "
                   "acaba de ampliar su pérdida máxima y nadie le ha "
                   "preguntado nada.\n\n"
                   "Yo tengo prohibido por código mover un stop en contra. "
                   "Usted a mano puede hacerlo en dos segundos. Use el "
                   "gráfico para mirar y el ticket para modificar: el "
                   "ticket sí pregunta."),
    },
    "paper_vs_real": {
        "nombre": "En qué se diferencia la simulada de la real",
        "nivel": 1, "riesgo": "bajo",
        "donde": "Documentación oficial de IBKR sobre paper trading.",
        "que": ("La cuenta simulada no ejecuta en ninguna bolsa ni liquida "
                "en cámara: es un simulador."),
        "porque": ("Sus ejecuciones se simulan «desde el tope del libro, sin "
                   "acceso al libro profundo» — palabras de IBKR. Traducido: "
                   "en la simulación siempre hay alguien al otro lado; en el "
                   "mercado real usted compite por esa contrapartida y "
                   "muchas veces la pierde. Además los stops están SIEMPRE "
                   "simulados y la propia IBKR avisa de que se comportan "
                   "distinto. Por eso un porcentaje de acierto alto en paper "
                   "es en parte un regalo del simulador, no habilidad. Sirve "
                   "para aprender el proceso; no sirve para estimar lo que "
                   "ganará."),
    },
    "opciones_futuros": {
        "nombre": "Opciones y futuros — todavía no",
        "nivel": 3, "riesgo": "alto",
        "donde": "Cadena de opciones, vista de rejilla, contratos de futuros.",
        "que": "Derivados: instrumentos que dependen de otro activo.",
        "porque": ("No son malos: son otro juego. Las opciones añaden dos "
                   "dimensiones que las acciones no tienen —el tiempo y la "
                   "volatilidad implícita—, y se puede acertar la dirección "
                   "y perder todo el dinero igualmente porque tardó en "
                   "moverse. Los futuros traen apalancamiento incorporado: "
                   "con capital pequeño no multiplican la ganancia, aceleran "
                   "el cero. Cuando lleve meses de acciones con resultados "
                   "anotados, hablamos."),
    },

    # ── Añadidas tras leer la documentación oficial de IBKR ─────────────────
    "modo_panel": {
        "nombre": "⚠ Modo del panel de órdenes (Rapid Transmit)",
        "nivel": 1, "riesgo": "alto",
        "donde": "Engranaje ⚙ del panel de órdenes → Settings → modo.",
        "que": ("Hay tres modos: Interactive (el normal), Simplified "
                "(reducido) y Rapid Transmit."),
        "porque": ("Esto es lo más peligroso de la plataforma para alguien "
                   "que empieza, y casi nadie lo advierte. La documentación "
                   "oficial dice del modo Rapid Transmit: «This version does "
                   "not include a Submit button». O sea: el clic en COMPRAR "
                   "ES el envío. No hay confirmación, no hay ENVIAR, no hay "
                   "vuelta atrás. Un clic accidental transmite una orden "
                   "real. Quédese en Interactive hasta llevar meses "
                   "operando: el segundo que ahorra no vale lo que arriesga."),
    },
    "check_margin": {
        "nombre": "Revisar la orden antes de enviarla",
        "nivel": 1, "riesgo": "bajo",
        "donde": ("Clic DERECHO sobre la línea de la orden → «Revisar "
                  "perfil de rendimiento / margen». También desde el botón "
                  "«avanzado +» → «Check Margin»."),
        "que": ("Enseña el coste real, los avisos de IBKR y el impacto "
                "sobre el margen, todo ANTES de transmitir."),
        "porque": ("Es el paso «d» de los cinco que marca la guía oficial "
                   "de operativa en TWS, y el que casi todo el mundo se "
                   "salta.\n\n"
                   "En esa ventana hay que mirar cuatro cosas: la "
                   "descripción de la orden (¿es lo que quería?), los "
                   "mensajes de aviso (IBKR le dice si los contratos son "
                   "más de lo normal o si el precio límite se aleja del "
                   "mercado), el coste de la operación, y el impacto sobre "
                   "el margen.\n\n"
                   "Esos avisos existen porque son los errores que la "
                   "gente comete de verdad. Cuesta un segundo leerlos."),
    },
    "cinco_pasos": {
        "nombre": "Los cinco pasos de toda operación",
        "nivel": 1, "riesgo": "bajo",
        "donde": "El orden que sigue cualquier operación en TWS.",
        "que": ("a) subyacente · b) instrumento · c) crear la orden · "
                "d) REVISAR · e) enviar"),
        "porque": ("La guía oficial de operativa en TWS insiste en que "
                   "estas cinco fases son SIEMPRE las mismas, sea lo que "
                   "sea que se opere.\n\n"
                   "El que importa es el (d). Los otros cuatro los hace "
                   "cualquiera por instinto; el de revisar hay que "
                   "acordarse. Y es justo el que le enseña el coste real y "
                   "si la orden le deja sin colchón.\n\n"
                   "Yo sigo esta secuencia entera en cada operación, y si "
                   "cualquiera de los cinco falla, me detengo."),
    },
    "clic_precio": {
        "nombre": "⚠ Clic en ASK compra, clic en BID vende",
        "nivel": 1, "riesgo": "alto",
        "donde": "Las columnas de precio de su ventana de negociación.",
        "que": ("Pulsar el precio ASK crea una orden de COMPRA. Pulsar el "
                "BID crea una de VENTA."),
        "porque": ("Esto sorprende a todo el mundo la primera vez, y sale "
                   "tanto en la guía de TWS clásica como en la de IBKR "
                   "Desktop: no es un clic para consultar, es un clic que "
                   "EMPIEZA UNA ORDEN.\n\n"
                   "La orden aparece con los parámetros por defecto — que "
                   "es otra razón para tener los presets en cantidad 1. "
                   "Todavía hay que enviarla, pero el camino ya está "
                   "andado a medias sin haberlo pretendido."),
    },
    "rolar": {
        "nombre": "Rolar una opción (renovar)",
        "nivel": 3, "riesgo": "alto",
        "donde": "Clic DERECHO sobre la opción → botón «RENOVAR».",
        "que": ("Cerrar la posición del vencimiento cercano y abrir otra "
                "en uno más lejano, en una sola orden de dos patas."),
        "porque": ("Lo importante es POR QUÉ se hace en una sola orden. "
                   "Cita de la guía: «se elimina el riesgo de inejecución "
                   "de alguna de las órdenes individuales».\n\n"
                   "Es el mismo principio del bracket: una orden combinada "
                   "no puede quedarse a medias; dos órdenes sueltas sí. Si "
                   "cierra la vieja y el mercado salta antes de abrir la "
                   "nueva, se queda fuera y a peor precio.\n\n"
                   "El precio combinado se pone a mano: bid = bid pata 1 − "
                   "ask pata 2. Suele salir negativo."),
    },
    "ejercer": {
        "nombre": "⚠ Ejercer una opción — inmediato e irreversible",
        "nivel": 3, "riesgo": "alto",
        "donde": ("Cuenta → Ejercicio de opciones → «Seleccionar» → "
                  "«Ejercicio temprano» → botón «T» de transmitir."),
        "que": "Convertir la opción en el subyacente al precio del strike.",
        "porque": ("Dos cosas, y ambas importan.\n\n"
                   "PRIMERA: la teoría dice que NO se debe ejercer antes "
                   "del vencimiento. Al ejercer solo se obtiene el valor "
                   "intrínseco y se REGALA el temporal. El ejemplo de la "
                   "guía: call strike 95, subyacente a 100, prima 6. "
                   "Ejerciendo gana 5; vendiendo la opción y comprando en "
                   "mercado gana 6. Ejercer siempre es peor, salvo con "
                   "dividendos de por medio o activos muy ilíquidos.\n\n"
                   "SEGUNDA, y más grave: la guía dice textualmente que "
                   "«el ejercicio de la opción se ejecuta de forma "
                   "inmediata». Sin confirmación y sin vuelta atrás. Su "
                   "posición pasa a cero y aparecen las acciones. Está en "
                   "mi lista de cosas que no haré nunca por mi cuenta."),
    },
    "adaptive": {
        "nombre": "Algoritmo Adaptive",
        "nivel": 2, "riesgo": "bajo",
        "donde": "Selector de algo del panel de órdenes → Adaptive.",
        "que": ("Combina el enrutado inteligente de IBKR con el nivel de "
                "urgencia que usted elija."),
        "porque": ("Intenta ejecutar DENTRO de la horquilla en lugar de "
                   "cruzarla. La propia IBKR dice que da mejores precios de "
                   "media que una orden límite o de mercado corriente. Con "
                   "poco capital, cada centavo de horquilla que se ahorra "
                   "cuenta de verdad."),
    },
    "tiempo_vigor": {
        "nombre": "Tiempo en vigor (DAY, GTC, IOC, FOK)",
        "nivel": 2, "riesgo": "medio",
        "donde": "Campo DAY del panel de órdenes.",
        "que": ("Cuánto tiempo sigue viva la orden. DAY vence al cierre; "
                "GTC sigue hasta ejecutarse o cancelarla."),
        "porque": ("Use DAY mientras aprende. El peligro de GTC es real: "
                   "una orden olvidada puede ejecutarse semanas después, en "
                   "un contexto que no tiene nada que ver con el que la "
                   "motivó. Si usa GTC, apúntela en algún sitio."),
    },
    "oca_parcial": {
        "nombre": "OCA y los llenados parciales",
        "nivel": 3, "riesgo": "medio",
        "donde": "Botón «avanzado +» → One Cancels Other → casilla «On Fill».",
        "que": ("Qué hacer con las demás órdenes del grupo cuando una se "
                "ejecuta solo en parte."),
        "porque": ("Elija siempre «Reduce other orders, overfill "
                   "protection». La documentación advierte que sin esa "
                   "protección se pueden mandar varias órdenes a la vez y "
                   "acabar comprando de más. Y un detalle que casi nadie "
                   "lee: si USTED cancela una del grupo, las demás se "
                   "cancelan; pero si el SISTEMA rechaza una, las demás NO. "
                   "Ahí puede quedarse con un stop huérfano sin saberlo."),
    },
    "alertas": {
        "nombre": "Alertas de precio",
        "nivel": 2, "riesgo": "bajo",
        "donde": "Clic derecho en el símbolo → Alerts → Create Alert.",
        "que": "Le avisa cuando un precio toca un nivel.",
        "porque": ("La mejor herramienta contra el peor hábito: mirar la "
                   "pantalla todo el día. Ponga la alerta y váyase a vivir. "
                   "Operar no debería ocuparle la vida entera."),
    },
}


# ═══════════════════════════════════════════════════════════════════════════
#  PLAN DE ESTUDIOS
# ═══════════════════════════════════════════════════════════════════════════

LECCIONES = [
    ("paper",         "Confirmar que estamos en la cuenta simulada"),
    ("modo_panel",    "⚠ Desactivar Rapid Transmit — lo primero de todo"),
    ("presets",       "⚠ Los presets: 100 acciones por defecto = 22× su cuenta"),
    ("orden_watchlist", "⚠ Un clic en el precio abre un ticket de orden"),
    ("clic_precio",   "⚠ ASK compra, BID vende: cuidado dónde pulsa"),
    ("cinco_pasos",   "Los cinco pasos de toda operación"),
    ("paper_vs_real", "Por qué la simulada da mejores números que la real"),
    ("watchlist",     "Poner activos en la lista de vigilancia"),
    ("grafico",       "Abrir y leer un gráfico"),
    ("ticket_orden",  "Conocer el ticket de órdenes campo por campo"),
    ("orden_limite",  "La orden límite: usted pone el precio"),
    ("stop_loss",     "El stop: saber por dónde se sale antes de entrar"),
    ("bracket",       "El bracket: decidir las tres cosas en frío"),
    ("check_margin",  "Comprobar el margen antes de enviar"),
    ("ordenes",       "Comprobar que una orden entró de verdad"),
    ("cartera",       "Leer la cartera sin obsesionarse"),
    ("tiempo_vigor",  "DAY, GTC y el peligro de la orden olvidada"),
    ("alertas",       "Alertas: dejar de mirar la pantalla"),
    ("orden_mercado", "La orden a mercado y por qué usarla poco"),
    ("adaptive",      "El algoritmo Adaptive: mejores precios de entrada"),
    ("calendario",    "Resultados y huecos de apertura"),
    ("escaner",       "El escáner y la trampa de perseguir lo que ya subió"),
    ("trailing_stop", "El stop dinámico"),
    ("oca_parcial",   "OCA: llenados parciales y stops huérfanos"),
    ("profundidad",   "Profundidad de mercado: para qué sirve y para qué no"),
    ("riskNavigator", "Riesgo de cartera y correlación"),
    ("orden_grafico", "Mover órdenes en el gráfico (y su peligro)"),
    ("atajos",        "⚠ Atajos y orden rápida: por qué no usarlos aún"),
    ("opciones_futuros", "Opciones y futuros: por qué todavía no"),
    ("rolar",         "Rolar una opción (para más adelante)"),
    ("ejercer",       "⚠ Ejercer: inmediato y sin vuelta atrás"),
    ("api",           "La API y los puertos 7497 / 7496"),
]


def _cargar() -> dict:
    try:
        with open(_RUTA_PROG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"vistas": [], "inicio": time.strftime("%Y-%m-%d")}


def _guardar(d: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_RUTA_PROG), exist_ok=True)
        tmp = _RUTA_PROG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _RUTA_PROG)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  LO QUE LITCH DICE
# ═══════════════════════════════════════════════════════════════════════════

# Cómo llama la gente a cada herramienta. Sin esto, "orden a mercado"
# acababa devolviendo la orden LÍMITE porque ambas contienen "orden" —
# y confundir esas dos es precisamente el error que más caro sale.
ALIAS = {
    "watchlist":     ("watchlist", "lista de vigilancia", "lista de activos",
                      "vigilancia"),
    "grafico":       ("grafico", "gráfico", "chart", "velas"),
    "ticket_orden":  ("ticket", "order ticket", "entrada de ordenes",
                      "entrada de órdenes", "formulario"),
    "cartera":       ("cartera", "portfolio", "posiciones", "mis posiciones"),
    "ordenes":       ("ordenes", "órdenes", "orders", "trades",
                      "mis ordenes", "mis órdenes"),
    "orden_limite":  ("limite", "límite", "lmt", "orden limite",
                      "orden límite", "orden lmt"),
    "orden_mercado": ("mercado", "mkt", "orden a mercado", "orden de mercado",
                      "market order", "a mercado"),
    "stop_loss":     ("stop", "stop loss", "stp", "stop de perdidas",
                      "stop de pérdidas", "corte de perdidas"),
    "bracket":       ("bracket", "orden bracket", "entrada stop objetivo",
                      "oca", "tres ordenes", "tres órdenes"),
    "trailing_stop": ("trailing", "trail", "stop dinamico", "stop dinámico",
                      "trailing stop"),
    "profundidad":   ("profundidad", "level ii", "level 2", "market depth",
                      "libro de ordenes", "libro de órdenes"),
    "escaner":       ("escaner", "escáner", "scanner", "market scanner",
                      "buscador"),
    "calendario":    ("calendario", "resultados", "earnings", "eventos",
                      "macro"),
    "riskNavigator": ("risk navigator", "riesgo de cartera", "correlacion",
                      "correlación", "navigator"),
    "api":           ("api", "puerto", "socket", "conexion", "conexión",
                      "7497", "7496"),
    "paper":         ("paper", "simulada", "demo", "cuenta simulada",
                      "paper trading", "ficticio"),
    "alertas":       ("alerta", "alertas", "aviso de precio", "alert"),
    "modo_panel":    ("rapid transmit", "modo del panel", "modo panel",
                      "sin boton enviar", "interactive", "simplified"),
    "check_margin":  ("check margin", "comprobar margen", "margen",
                      "revisar margen", "revisar la orden",
                      "perfil de rendimiento"),
    "cinco_pasos":   ("cinco pasos", "5 pasos", "secuencia de la operacion",
                      "pasos de una operacion", "como se opera"),
    "clic_precio":   ("clic en el ask", "clic en ask", "ask compra",
                      "bid vende", "pulsar el ask", "pulsar el bid"),
    "rolar":         ("rolar", "renovar", "roll out", "roll up",
                      "roll down", "cambiar de vencimiento"),
    "ejercer":       ("ejercer", "ejercicio", "ejercicio temprano",
                      "exercise", "convertir en acciones"),
    "adaptive":      ("adaptive", "adaptativo", "algoritmo adaptive",
                      "midprice", "mid price"),
    "tiempo_vigor":  ("tiempo en vigor", "time in force", "gtc", "day",
                      "ioc", "fok", "vigencia"),
    "oca_parcial":   ("oca parcial", "llenado parcial", "overfill",
                      "sobrellenado", "on fill", "stop huerfano"),
    "presets":       ("preset", "presets", "valores por defecto",
                      "cantidad por defecto", "configuracion por defecto",
                      "100 acciones", "cien acciones"),
    "orden_watchlist": ("clic en el precio", "clic en el bid",
                        "clic en el ask", "pulsar el precio",
                        "abrir ticket desde la lista"),
    "atajos":        ("atajo", "atajos", "hotkey", "hotkeys",
                      "teclas rapidas", "orden rapida", "ventana rapida"),
    "orden_grafico": ("orden en el grafico", "arrastrar el stop",
                      "mover el stop en el grafico", "lineas del grafico"),
    "paper_vs_real": ("paper vs real", "simulada vs real",
                      "diferencia entre simulada y real",
                      "por que gano en demo", "libro profundo"),
    "opciones_futuros": ("opciones", "futuros", "cadena de opciones",
                         "option chain", "derivados", "calls", "puts"),
}


def _buscar(texto: str) -> str | None:
    """Encuentra la herramienta que mejor encaja. Gana el alias más largo.

    Puntuar por longitud evita el fallo clásico: "orden a mercado" contiene
    tanto "orden" (genérico) como "a mercado" (específico). El específico
    debe ganar siempre.
    """
    t = (texto or "").lower().strip()
    if not t:
        return None
    if t in HERRAMIENTAS:
        return t

    mejor, punt = None, 0
    for clave, alias in ALIAS.items():
        for a in alias:
            if a in t and len(a) > punt:
                mejor, punt = clave, len(a)
    return mejor


def explicar(clave_o_texto: str) -> str:
    """Explica una herramienta de TWS. Acepta el nombre suelto."""
    clave = _buscar(clave_o_texto)
    h = HERRAMIENTAS.get(clave) if clave else None
    if h is None:
        return ("No tengo ficha de esa herramienta, señor. Dígame "
                "'qué herramientas tiene IBKR' y le listo las que conozco.")

    nivel = {1: "imprescindible desde el primer día",
             2: "útil cuando lleve unas semanas",
             3: "avanzada, no la necesita todavía"}[h["nivel"]]
    riesgo = {"bajo": "Riesgo bajo.",
              "medio": "Riesgo medio: conviene entenderla antes de usarla.",
              "alto": "⚠ Riesgo alto."}[h["riesgo"]]

    return (f"{h['nombre']} — {nivel}. {riesgo}\n\n"
            f"Dónde está: {h['donde']}\n\n"
            f"Qué hace: {h['que']}\n\n"
            f"Por qué le importa: {h['porque']}")


def listar(nivel: int | None = None) -> str:
    """Todas las herramientas, o las de un nivel."""
    items = [(k, v) for k, v in HERRAMIENTAS.items()
             if nivel is None or v["nivel"] == nivel]
    if not items:
        return "No tengo herramientas de ese nivel, señor."
    items.sort(key=lambda kv: (kv[1]["nivel"], kv[1]["nombre"]))
    lineas = []
    nivel_actual = None
    titulos = {1: "── Para empezar ──", 2: "── Para después ──",
               3: "── Avanzadas ──"}
    for k, v in items:
        if v["nivel"] != nivel_actual:
            nivel_actual = v["nivel"]
            lineas.append("")
            lineas.append(titulos[nivel_actual])
        marca = " ⚠" if v["riesgo"] == "alto" else ""
        lineas.append(f"  · {v['nombre']}{marca} — {v['que']}")
    return ("Conozco estas herramientas de Interactive Brokers:\n"
            + "\n".join(lineas)
            + "\n\nPregúnteme por cualquiera: 'Litch, explícame el bracket'.")


def siguiente_leccion(app=None) -> str:
    """La próxima lección del plan, según lo que ya se ha visto."""
    prog = _cargar()
    vistas = set(prog.get("vistas", []))
    for clave, titulo in LECCIONES:
        if clave not in vistas:
            n = len(vistas) + 1
            h = HERRAMIENTAS[clave]
            return (f"Lección {n} de {len(LECCIONES)}: {titulo}.\n\n"
                    + explicar(clave)
                    + f"\n\nCuando lo tenga claro dígame 'lección aprendida' "
                      f"y pasamos a la siguiente.")
    return ("Ha completado las diecisiete lecciones, señor. Ahora lo que "
            "queda no se aprende leyendo: es repetir en la cuenta simulada "
            "hasta que el proceso le salga sin pensar. Le sugiero llevar un "
            "diario de cada operación con el motivo de entrada y el "
            "resultado. Revisarlo al mes enseña más que cualquier manual.")


def marcar_aprendida(app=None) -> str:
    """Registra la lección actual como vista."""
    prog = _cargar()
    vistas = list(prog.get("vistas", []))
    for clave, titulo in LECCIONES:
        if clave not in vistas:
            vistas.append(clave)
            prog["vistas"] = vistas
            prog["ultima"] = time.strftime("%Y-%m-%d %H:%M")
            _guardar(prog)
            faltan = len(LECCIONES) - len(vistas)
            if faltan:
                sig = next(t for c, t in LECCIONES if c not in vistas)
                return (f"Anotado: «{titulo}» aprendida. Van {len(vistas)} "
                        f"de {len(LECCIONES)}. La siguiente será: {sig}. "
                        f"Dígame 'siguiente lección' cuando quiera.")
            return (f"«{titulo}» aprendida. Con esa completa las "
                    f"{len(LECCIONES)} lecciones, señor. Enhorabuena.")
    return "Ya tenía todas las lecciones marcadas, señor."


def progreso(app=None) -> str:
    """Cuánto lleva aprendido."""
    prog = _cargar()
    vistas = prog.get("vistas", [])
    n, total = len(vistas), len(LECCIONES)
    if not n:
        return ("Aún no hemos empezado la escuela de Interactive Brokers. "
                "Dígame 'siguiente lección' y arrancamos por lo básico.")
    barra = "█" * n + "·" * (total - n)
    txt = f"Escuela de IBKR: {n} de {total} lecciones.\n[{barra}]\n"
    nombres = [dict(LECCIONES)[c] for c in vistas if c in dict(LECCIONES)]
    if nombres:
        txt += "Ya vio: " + "; ".join(nombres[-4:]) + ".\n"
    if n < total:
        sig = next(t for c, t in LECCIONES if c not in vistas)
        txt += f"Le toca: {sig}."
    if prog.get("ultima"):
        txt += f"\nÚltima lección: {prog['ultima']}."
    return txt


def consejo_del_dia() -> str:
    """Un principio de los que de verdad importan, rotando cada día."""
    consejos = [
        ("Antes de entrar, escriba dónde va a salir si se equivoca. Si no "
         "sabe responder eso, no es una operación: es una apuesta."),
        ("Arriesgar el 1% por operación suena poco. Es exactamente por eso "
         "que funciona: veinte errores seguidos le dejan el 82% del capital, "
         "y veinte errores seguidos le van a pasar alguna vez."),
        ("La orden a mercado en la apertura es donde más dinero pierde la "
         "gente sin enterarse. Use órdenes límite."),
        ("Un stop no le protege de un hueco de apertura. Si la empresa "
         "publica resultados esta noche, el precio de mañana puede "
         "aparecer directamente por debajo de su stop."),
        ("Si mira la cartera cada cinco minutos, va a cerrar operaciones "
         "buenas por nervios. Ponga alertas y váyase."),
        ("Tener cinco tecnológicas no es diversificar. Es la misma apuesta "
         "cinco veces, y cuando caiga el sector caerán las cinco."),
        ("En la cuenta simulada todo entra fácil porque no hay nadie al "
         "otro lado. En la real habrá días que no le llenen la orden. "
         "Cuente con eso antes de que pase."),
        ("Una racha ganadora no prueba que su método sirva, igual que una "
         "perdedora no prueba que no. Con menos de treinta operaciones no "
         "hay conclusión posible, solo ruido."),
        ("El mejor día de trading es a menudo aquel en el que no operó "
         "porque no había nada claro. Eso no es pereza, es criterio."),
        ("Escriba por qué entra en cada operación ANTES de entrar. Al mes, "
         "releerlo le va a enseñar más sobre usted que sobre el mercado."),
    ]
    return consejos[int(time.time() // 86400) % len(consejos)]
