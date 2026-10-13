"""
tws_operacion.py — Litch aprende a USAR Trader Workstation (IBKR).

Este módulo le da a Litch el conocimiento operativo de TWS: qué hay en cada
zona de la pantalla, cómo se arma una orden de acciones, y —lo más
importante— la DIFERENCIA fundamental entre operar binarias (IQ Option) y
operar acciones (Wall Street).

Dos caminos de operación, y Litch usa el mejor de cada momento:
  A) VISIÓN  → lee el gráfico de TWS en pantalla para ANALIZAR (igual que
     hace con IQ Option). Sirve para detectar tendencia, velas, estructura.
  B) API     → ejecuta las órdenes por ibapi (puerto 7497 paper). Es el
     camino profesional: preciso, sin clics a ciegas, con bracket orders.

Regla de oro: analizar con los ojos, ejecutar con la API. Hacer clics a
ciegas en TWS es peligroso porque el botón "Transmit" envía dinero.
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════════
#  MAPA DE PANTALLA DE TWS (para que Litch entienda lo que ve)
# ═══════════════════════════════════════════════════════════════════════════

ZONAS_TWS = {
    "entrada_ordenes": {
        "donde": "Panel superior izquierdo, título 'ENTRADA DE ÓRDENES'.",
        "que_tiene": "Casilla del símbolo (ej. AMZN), botones COMPRAR/VENDER, "
                     "CANT. (cantidad), tipo de orden (LMT/MKT), PRECIO LÍM., "
                     "vigencia (DAY/GTC) y el botón ENVIAR.",
        "cuidado": "El botón ENVIAR ejecuta de verdad. Litch NO hace clic ahí "
                   "a ciegas: ejecuta por API con parámetros verificados.",
    },
    "grafico": {
        "donde": "Centro-izquierda, panel con velas y el selector "
                 "'10 min Velas'.",
        "que_tiene": "Velas japonesas del activo, escala de precio a la "
                     "derecha, eje temporal abajo, precio actual resaltado.",
        "uso_litch": "ESTA es la zona que Litch calibra con 📐 para analizar. "
                     "Lee las velas igual que en IQ Option.",
    },
    "watchlist": {
        "donde": "Columna derecha, pestañas SEGUIMIENTO / Cartera / Favoritos.",
        "que_tiene": "Lista de símbolos con ÚLTIMO precio y VARIACIÓN diaria "
                     "(verde sube, rojo baja).",
        "uso_litch": "Fuente rápida de precios y sentimiento del día.",
    },
    "detalle_activo": {
        "donde": "Panel izquierdo bajo la entrada de órdenes.",
        "que_tiene": "Precio actual, Bid/Ask, volumen, rango 52 semanas, "
                     "EPS, PER, capitalización.",
        "uso_litch": "Contexto fundamental del activo (PER alto = caro).",
    },
    "actividad": {
        "donde": "Panel inferior, pestañas ACTIVIDAD / Órdenes / Operaciones.",
        "que_tiene": "Órdenes enviadas, ejecutadas y su estado.",
        "uso_litch": "Verificar que una orden se llenó de verdad.",
    },
    "cuenta": {
        "donde": "Arriba a la derecha: 'DATOS DU...' o 'U...'.",
        "que_tiene": "El número de cuenta activa.",
        "uso_litch": "REGLA DE SEGURIDAD: si empieza con DU es PAPER "
                     "(simulada). Si empieza con U es REAL. Litch verifica "
                     "esto antes de cualquier operación.",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
#  LA DIFERENCIA CLAVE: binarias vs acciones
# ═══════════════════════════════════════════════════════════════════════════

DIFERENCIA_BINARIAS_ACCIONES = """
Litch nació operando OPCIONES BINARIAS en IQ Option. Wall Street es otro
juego, y confundirlos es el error más caro posible:

BINARIAS (IQ Option)          | ACCIONES (IBKR / Wall Street)
------------------------------|--------------------------------------------
Vencimiento fijo (30s-5min)   | Sin vencimiento: se mantiene lo que quieras
Pierdes el 100% al fallar     | Pierdes solo hasta tu stop-loss
Ganas payout fijo (85%)       | Ganancia ilimitada si la tendencia sigue
Solo importa la dirección     | Importa la GESTIÓN después de entrar
Predecir la próxima vela      | Seguir tendencias de días/semanas
Necesitas >54% de acierto     | Rentable con 40% si el ratio es 2:1

CONSECUENCIA para Litch: su motor de "próxima vela sube/baja" NO se traduce
directo a acciones. En acciones la señal sirve para ELEGIR EL MOMENTO de
entrar, pero lo que define el resultado es el stop, el objetivo y la
paciencia. Por eso toda entrada va con BRACKET (entrada + stop + objetivo).
"""


# ═══════════════════════════════════════════════════════════════════════════
#  PROTOCOLO DE OPERACIÓN EN ACCIONES (lo que Litch debe seguir)
# ═══════════════════════════════════════════════════════════════════════════

PROTOCOLO_ACCIONES = [
    "1. VERIFICAR CUENTA: confirmar que es paper (DU). Nunca operar real sin "
    "confirmación explícita del usuario.",
    "2. VERIFICAR HORARIO: mercado abierto 9:30-16:00 ET, lunes a viernes. "
    "Fuera de eso, no operar (spreads amplios, poca liquidez).",
    "3. ELEGIR ACTIVO LÍQUIDO: SPY, VOO, QQQ, AAPL, MSFT. Evitar ilíquidos.",
    "4. ANALIZAR: leer el gráfico (visión) + indicadores + estructura. "
    "Exigir consenso alto — en acciones se opera menos y mejor.",
    "5. DIMENSIONAR: riesgo máximo 1-2% del capital. Cantidad = "
    "riesgo_dólares / distancia_al_stop (ATR).",
    "6. ENTRAR con orden LÍMITE (nunca market en poco líquido), precio "
    "redondeado a 2 decimales (≥$1) o 4 (<$1).",
    "7. BRACKET OBLIGATORIO: stop-loss donde la idea queda invalidada + "
    "take-profit con ratio mínimo 1.5:1. Enlazados OCA.",
    "8. GESTIONAR: si va a favor, mover el stop (trailing). No cerrar por "
    "nervios; no promediar a la baja.",
    "9. REGISTRAR: cada orden enviada, llenada o rechazada con su motivo.",
    "10. RESPETAR PDT: con cuenta de margen <$25.000, máximo 3 day-trades "
    "en 5 días hábiles.",
]


# ═══════════════════════════════════════════════════════════════════════════
#  CALIBRACIÓN DE LA VISIÓN PARA TWS
# ═══════════════════════════════════════════════════════════════════════════

GUIA_CALIBRACION = """
Para que Litch ANALICE el gráfico de TWS con su visión (igual que hace con
IQ Option):

1. Deja TWS abierto y visible, con el gráfico del activo que quieres seguir
   (ej. escribe SPY en la casilla del símbolo).
2. Amplía el panel del gráfico lo más posible (doble clic en su barra de
   título lo maximiza dentro de TWS).
3. En Litch, pulsa el botón 📐 (Calibrar) y dibuja un rectángulo SOLO sobre
   el área de las velas — sin incluir la escala de precios ni los menús.
4. Litch guardará esa región y leerá las velas de TWS en tiempo real.

IMPORTANTE: la calibración de IQ Option y la de TWS son distintas. Si
cambias de plataforma, recalibra. Litch avisa si no ve el gráfico.

VENTAJA DEL FONDO OSCURO: TWS usa velas verdes/rojas sobre fondo negro,
igual que IQ Option — la visión de Litch funciona bien con ese contraste.
"""


def mapa_pantalla(idioma: str = "es") -> str:
    """Explica a Litch (y al usuario) qué hay en cada zona de TWS."""
    lineas = ["Mapa de la pantalla de Trader Workstation:"]
    for clave, z in ZONAS_TWS.items():
        lineas.append(f"\n• {clave.replace('_', ' ').upper()}")
        lineas.append(f"  Dónde: {z['donde']}")
        lineas.append(f"  Qué tiene: {z['que_tiene']}")
        extra = z.get("uso_litch") or z.get("cuidado")
        if extra:
            lineas.append(f"  Nota: {extra}")
    return "\n".join(lineas)


def protocolo(idioma: str = "es") -> str:
    """Protocolo paso a paso para operar acciones."""
    return ("Protocolo de operación en acciones (Wall Street):\n"
            + "\n".join(PROTOCOLO_ACCIONES))


def diferencia(idioma: str = "es") -> str:
    return DIFERENCIA_BINARIAS_ACCIONES.strip()


def guia_calibracion(idioma: str = "es") -> str:
    return GUIA_CALIBRACION.strip()


def checklist_listo(app) -> str:
    """Revisa si todo está listo para operar en TWS y dice qué falta."""
    import time
    pasos = []

    # 1. ibapi
    try:
        import ibapi  # noqa: F401
        pasos.append("✓ Librería ibapi instalada.")
    except Exception:
        pasos.append("✗ Falta ibapi (pip install ibapi).")

    # 2. Puerto paper
    try:
        from . import ibkr_diagnostico as _d
        e = _d.diagnosticar()
        if e.get("tws_paper"):
            pasos.append("✓ TWS abierto en PAPER (puerto 7497 responde).")
        elif e.get("tws_real"):
            pasos.append("⚠ TWS abierto pero en REAL. Cambie a Paper.")
        else:
            pasos.append("✗ TWS no detectado. Ábralo en modo Paper y "
                         "habilite la API.")
    except Exception:
        pasos.append("✗ No pude revisar el puerto de TWS.")

    # 3. Horario de mercado — hora REAL de Nueva York, no la del equipo.
    #    (Colombia es UTC-5 fijo; NY cambia a UTC-4 en verano.)
    try:
        from . import motor_acciones as _ma
        abierto, detalle = _ma.mercado_abierto()
        pasos.append(("✓ " if abierto else "⏰ ") + detalle)
    except Exception:
        pasos.append("⚠ No pude verificar el horario de Wall Street.")

    # 4. Región del gráfico calibrada
    try:
        if app.mem.get("config", {}).get("region_grafico"):
            pasos.append("✓ Región de gráfico calibrada (recalibre sobre TWS "
                         "si venía de IQ Option).")
        else:
            pasos.append("✗ Falta calibrar el gráfico (botón 📐).")
    except Exception:
        pass

    return "Estado para operar en Wall Street:\n" + "\n".join(pasos)
