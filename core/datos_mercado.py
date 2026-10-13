"""
Calidad del dato de mercado y rótulos bilingües de TWS.

━━━ POR QUÉ EXISTE ESTE MÓDULO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dos problemas que solo aparecen cuando se opera de verdad, y que no se
ven en las pruebas:

 1) EL PRECIO PUEDE SER MENTIRA.
    TWS entrega cuatro clases de dato distintas y todas se leen igual
    en pantalla y en la API:
        1 = en vivo          (requiere suscripción pagada)
        2 = congelado        (último cierre; el mercado está cerrado)
        3 = retrasado        (15-20 minutos tarde)
        4 = retrasado y congelado (el cierre de ayer)
    Si Litch calcula un stop-loss con un precio de hace 20 minutos, el
    stop nace inválido y la operación arranca perdida. Peor: cuando NO
    hay suscripción, la API no devuelve un error — devuelve NaN. Y en
    Python `float('nan') or 0.0` NO da 0.0, da NaN, porque NaN es un
    valor verdadero. Un NaN se cuela silencioso hasta el tamaño de la
    posición.

 2) LOS RÓTULOS DE TWS CAMBIAN CON EL IDIOMA.
    La misma media móvil simple se llama "MA" si TWS está en español y
    "SMA" si está en inglés. Igual pasa con Portafolio/Portfolio,
    Comprar/Buy, Transmitir/Transmit. Litch lee la pantalla con OCR: si
    el diccionario está solo en un idioma, en la máquina de al lado no
    reconoce nada y se queda ciega sin saber que está ciega.

Este módulo resuelve las dos cosas y no toca nada de lo que ya funciona:
se importa y se usa, o se ignora y todo sigue igual.
"""

from __future__ import annotations

import math
import time
from typing import Any, Optional

# ── 1. Tipos de dato de mercado ──────────────────────────────────────────────

EN_VIVO             = 1
CONGELADO           = 2
RETRASADO           = 3
RETRASADO_CONGELADO = 4

NOMBRE_TIPO = {
    EN_VIVO:             "en vivo",
    CONGELADO:           "congelado (último cierre)",
    RETRASADO:           "retrasado ~15 min",
    RETRASADO_CONGELADO: "retrasado y congelado (cierre de ayer)",
}

# Solo el dato en vivo sirve para ejecutar. El congelado sirve para leer
# el cierre fuera de horario; el retrasado no sirve para nada operativo.
TIPOS_EJECUTABLES = (EN_VIVO,)

# Los "tick types" retrasados que IBKR devuelve cuando no hay suscripción.
# Si aparecen estos y no los normales, el dato es de hace 15 minutos.
TICKS_RETRASADOS = {
    66: "bid retrasado",
    67: "ask retrasado",
    68: "last retrasado",
    72: "máximo retrasado",
    73: "mínimo retrasado",
    74: "volumen retrasado",
    75: "cierre retrasado",
    76: "apertura retrasada",
}


def es_numero(v: Any) -> bool:
    """
    True solo si v es un número real y utilizable.

    Esto es el corazón del módulo. NaN e infinito son `float`, pasan
    `isinstance(v, float)`, son verdaderos en un `or`, y sobreviven a
    sumas y multiplicaciones contaminando todo lo que tocan. Aquí mueren.
    """
    if v is None or isinstance(v, bool):
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def limpio(v: Any, por_defecto: float = 0.0) -> float:
    """Convierte a float seguro. NaN, inf, None y basura → por_defecto."""
    return float(v) if es_numero(v) else float(por_defecto)


def primer_valido(*valores: Any) -> Optional[float]:
    """
    Devuelve el primer valor que sea un número real.

    Reemplaza el patrón peligroso `ticker.last or ticker.close or 0.0`,
    que devuelve NaN si last es NaN.
    """
    for v in valores:
        if es_numero(v):
            return float(v)
    return None


def leer_tipo(ib) -> int:
    """
    Averigua con qué clase de dato está trabajando la conexión.

    Devuelve 0 si no se pudo determinar. Nunca lanza excepción: si algo
    falla, Litch debe poder seguir leyendo, solo que sin certificar el
    dato — y no saber cuenta como no estar en vivo.
    """
    if ib is None:
        return 0
    for atributo in ("marketDataType", "_marketDataType", "marketDataTypeValue"):
        try:
            v = getattr(ib, atributo, None)
            if callable(v):
                v = v()
            if isinstance(v, int) and 1 <= v <= 4:
                return v
        except Exception:
            continue
    return 0


def pedir_tipo(ib, tipo: int = EN_VIVO) -> bool:
    """
    Pide a TWS una clase concreta de dato. True si la petición se cursó.

    Nota: que se curse NO garantiza que se reciba. TWS acepta la petición
    de dato en vivo aunque la cuenta no tenga suscripción, y luego manda
    NaN. Por eso siempre hay que verificar el resultado, no la petición.
    """
    if ib is None or tipo not in NOMBRE_TIPO:
        return False
    try:
        ib.reqMarketDataType(tipo)
        return True
    except Exception:
        return False


def auditar_ticker(ticker, tipo: int = 0) -> dict:
    """
    Examina un ticker de IBKR y dictamina si su precio es de fiar.

    Devuelve:
        precio, bid, ask, volumen : floats limpios (0.0 si no hay dato)
        hay_precio  : bool  — llegó algún número real
        spread      : float — ask-bid, o 0.0 si falta alguno
        tipo        : int   — clase de dato (1..4, 0 desconocido)
        ejecutable  : bool  — ¿se puede mandar una orden con esto?
        motivo      : str   — por qué no, si no
    """
    r = {
        "precio": 0.0, "bid": 0.0, "ask": 0.0, "volumen": 0.0,
        "hay_precio": False, "spread": 0.0,
        "tipo": int(tipo or 0), "ejecutable": False, "motivo": "",
    }
    if ticker is None:
        r["motivo"] = "sin ticker: TWS no devolvió nada"
        return r

    g = lambda n: getattr(ticker, n, None)

    bid = primer_valido(g("bid"))
    ask = primer_valido(g("ask"))
    # Orden de preferencia: última operación, punto medio, marca, cierre.
    medio = (bid + ask) / 2.0 if (bid is not None and ask is not None) else None
    precio = primer_valido(g("last"), medio, g("markPrice"), g("close"))

    r["bid"]     = limpio(bid)
    r["ask"]     = limpio(ask)
    r["precio"]  = limpio(precio)
    r["volumen"] = limpio(g("volume"))
    r["hay_precio"] = precio is not None and precio > 0

    if bid is not None and ask is not None and ask >= bid:
        r["spread"] = round(ask - bid, 6)

    if not r["hay_precio"]:
        r["motivo"] = ("sin precio válido — casi siempre significa que la "
                       "cuenta no tiene suscripción de datos para ese mercado")
        return r

    t = r["tipo"]
    if t == 0:
        r["motivo"] = "no se pudo confirmar que el dato sea en vivo"
    elif t not in TIPOS_EJECUTABLES:
        r["motivo"] = f"dato {NOMBRE_TIPO.get(t, t)}: no sirve para ejecutar"
    else:
        r["ejecutable"] = True
    return r


def puede_ejecutar(ib, ticker=None) -> tuple[bool, str]:
    """
    Portero. Se llama justo antes de mandar una orden real.

    Regla dura: si no consta que el dato es en vivo, NO se ejecuta. El
    desconocimiento nunca cuenta como permiso — es el mismo criterio que
    usa broker_ibkr con la verificación de cuenta paper.
    """
    tipo = leer_tipo(ib)
    if tipo == 0:
        return False, ("No consta que TWS esté dando datos en vivo. "
                       "Sin certeza no se ejecuta.")
    if tipo not in TIPOS_EJECUTABLES:
        return False, (f"TWS está dando datos {NOMBRE_TIPO[tipo]}. "
                       f"Un stop calculado con ese precio nace inválido.")
    if ticker is not None:
        a = auditar_ticker(ticker, tipo)
        if not a["ejecutable"]:
            return False, a["motivo"]
    return True, "dato en vivo confirmado"


# ── 2. Rótulos bilingües de TWS ──────────────────────────────────────────────
#
# Clave interna → todas las formas en que TWS puede escribirlo. Litch
# compara siempre contra la lista entera, así el idioma de la instalación
# deja de importar.
#
# El caso MA/SMA está documentado por un espectador del tutorial de
# OPCIÓN SIGMA (minuto 38:56): en español el indicador se llama "MA" y en
# inglés "SMA". Es el mismo indicador. Quien programe contra un solo
# nombre pierde el indicador en la mitad de las máquinas del mundo.

ROTULOS = {
    # Indicadores
    "media_simple":     ["SMA", "MA", "Simple Moving Average", "Media Móvil",
                         "Media Movil", "Media Móvil Simple"],
    "media_exponencial":["EMA", "MME", "Exponential Moving Average",
                         "Media Móvil Exponencial"],
    "bandas":           ["Bollinger Bands", "Bandas de Bollinger", "BB"],
    "rsi":              ["RSI", "Relative Strength Index",
                         "Índice de Fuerza Relativa"],
    "macd":             ["MACD"],
    "volumen":          ["Volume", "Volumen", "Vol"],

    # Ventanas y paneles
    "portafolio":       ["Portfolio", "Portafolio", "Cartera",
                         "Account Window", "Ventana de Cuenta"],
    "ordenes":          ["Orders", "Órdenes", "Ordenes",
                         "Order Management", "Gestión de Órdenes"],
    "transacciones":    ["Trades", "Transacciones", "Operaciones",
                         "Executions", "Ejecuciones"],
    "lista":            ["Watchlist", "Lista de Seguimiento",
                         "Monitor", "Quote Monitor"],
    "mosaico":          ["Mosaic", "Mosaico"],
    "clasico":          ["Classic TWS", "TWS Clásico", "Classic"],
    "cadena_opciones":  ["Option Chain", "Cadena de Opciones", "OptionTrader"],

    # Ticket de orden
    "comprar":          ["BUY", "Buy", "Comprar", "COMPRA", "Compra"],
    "vender":           ["SELL", "Sell", "Vender", "VENTA", "Venta"],
    "cantidad":         ["Quantity", "Cantidad", "Qty", "Ctd"],
    "tipo_orden":       ["Order Type", "Tipo de Orden", "Type", "Tipo"],
    "precio_limite":    ["Limit Price", "Precio Límite", "Lmt Price", "LMT"],
    "precio_stop":      ["Stop Price", "Precio Stop", "Stp Price", "STP"],
    "vigencia":         ["Time in Force", "Vigencia", "TIF",
                         "Validez", "Duración"],
    "transmitir":       ["Transmit", "Transmitir", "Enviar", "Submit"],
    "cancelar":         ["Cancel", "Cancelar"],
    "modificar":        ["Modify", "Modificar", "Edit", "Editar"],
    "cerrar_posicion":  ["Close Position", "Cerrar Posición", "Flatten",
                         "Liquidar"],

    # Cifras de cuenta que Litch tiene que vigilar
    "liquidez_excedente":["Excess Liquidity", "Liquidez Excedente",
                          "Liquidez en Exceso"],
    "poder_compra":     ["Buying Power", "Poder de Compra",
                         "Capacidad de Compra"],
    "margen_inicial":   ["Initial Margin", "Margen Inicial", "Init Margin"],
    "margen_mantenim":  ["Maintenance Margin", "Margen de Mantenimiento",
                         "Maint Margin"],
    "valor_liquidacion":["Net Liquidation", "Valor de Liquidación",
                         "Liquidación Neta"],

    # Avisos de dato retrasado tal como los pinta TWS
    "aviso_retrasado":  ["Delayed", "Retrasado", "Datos Retrasados",
                         "Delayed Data", "Frozen", "Congelado",
                         "Delayed Frozen"],
}


def _plano(t: str) -> str:
    """Normaliza para comparar: sin tildes, sin espacios, en minúscula."""
    t = (t or "").lower().strip()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")):
        t = t.replace(a, b)
    return "".join(c for c in t if c.isalnum())


_INDICE = {}
for _clave, _formas in ROTULOS.items():
    for _f in _formas:
        _INDICE.setdefault(_plano(_f), _clave)


def que_es(texto: str) -> Optional[str]:
    """
    Dado un texto leído de la pantalla, dice qué elemento de TWS es.

    >>> que_es("SMA")            -> "media_simple"
    >>> que_es("Media Móvil")    -> "media_simple"
    >>> que_es("Transmitir")     -> "transmitir"
    """
    p = _plano(texto)
    if not p:
        return None
    if p in _INDICE:
        return _INDICE[p]
    # Coincidencia por contención: el OCR suele traer texto pegado
    # ("PrecioLímite:" en vez de "Precio Límite"). Se prefiere siempre la
    # forma más larga para no confundir "MA" dentro de "MACD".
    mejor, largo = None, 0
    for forma, clave in _INDICE.items():
        if len(forma) >= 3 and forma in p and len(forma) > largo:
            mejor, largo = clave, len(forma)
    return mejor


def formas_de(clave: str) -> list[str]:
    """Todas las formas en que TWS puede escribir ese elemento."""
    return list(ROTULOS.get(clave, []))


def dice_retrasado(texto: str) -> bool:
    """
    True si el texto de pantalla delata dato retrasado o congelado.

    TWS lo avisa con una etiqueta pequeña junto al precio. Es fácil de
    pasar por alto mirando, y trivial de detectar leyendo.
    """
    p = _plano(texto)
    return any(_plano(f) in p for f in ROTULOS["aviso_retrasado"])


# ── 3. Diagnóstico legible ───────────────────────────────────────────────────

def diagnostico(ib, ticker=None) -> str:
    """Una línea para el registro de actividad de Litch."""
    tipo = leer_tipo(ib)
    nombre = NOMBRE_TIPO.get(tipo, "desconocido")
    ok, motivo = puede_ejecutar(ib, ticker)
    marca = "OK" if ok else "BLOQUEADO"
    return f"[DATO] {marca} · tipo={tipo} ({nombre}) · {motivo}"


__all__ = [
    "EN_VIVO", "CONGELADO", "RETRASADO", "RETRASADO_CONGELADO",
    "NOMBRE_TIPO", "TIPOS_EJECUTABLES", "TICKS_RETRASADOS",
    "es_numero", "limpio", "primer_valido",
    "leer_tipo", "pedir_tipo", "auditar_ticker", "puede_ejecutar",
    "ROTULOS", "que_es", "formas_de", "dice_retrasado", "diagnostico",
]
