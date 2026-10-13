"""
motor_acciones.py — El motor de Litch para operar ACCIONES en Wall Street.

Esto es la "macro inteligente" que faltaba: el flujo completo de una
operación en acciones, decidido por análisis (no por reglas ciegas) y
ejecutado con las protecciones del Manual 13.

POR QUÉ EXISTE: el motor original de Litch predice la próxima vela para
opciones binarias (vencimiento fijo, pérdida total al fallar). Wall Street
es otro juego: no hay vencimiento, la pérdida la define el STOP y la
ganancia puede correr. Este módulo traduce el análisis de Litch al lenguaje
de las acciones.

FLUJO DE UNA OPERACIÓN (los 7 pasos que ejecuta):
  1. Verificar que se puede operar (cuenta paper, horario, conexión).
  2. Traer velas reales del activo (Yahoo/IBKR).
  3. Analizar: tendencia, RSI, MACD, ATR, estructura.
  4. Decidir con consenso; si no hay claridad, ABSTENERSE.
  5. Dimensionar la posición por riesgo (ATR), nunca por capricho.
  6. Construir la orden BRACKET (entrada + stop + objetivo).
  7. Registrar todo para aprender del resultado.

SEGURIDAD: por defecto solo PREPARA la orden (modo dry-run) y te la muestra.
Ejecutar de verdad exige que el usuario active el modo autónomo con cuenta
paper verificada.
"""

from __future__ import annotations

import time

# Activos recomendados para empezar (líquidos, spread bajo)
ACTIVOS_RECOMENDADOS = [
    ("SPY",  "S&P 500 — las 500 mayores empresas de EEUU"),
    ("VOO",  "S&P 500 (Vanguard) — igual que SPY, comisión menor"),
    ("QQQ",  "Nasdaq 100 — tecnológicas"),
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
]

# Parámetros de riesgo (Manual 13)
RIESGO_PCT_DEFECTO   = 0.01   # 1% del capital por operación
ATR_MULT_STOP        = 2.0    # stop a 2× ATR (deja respirar el ruido)
RATIO_OBJETIVO       = 2.0    # take-profit a 2× la distancia del stop
VOTOS_MIN_ACCIONES   = 4      # en acciones se opera menos y mejor


# ── Utilidades ──────────────────────────────────────────────────────────────

def _redondear(precio: float) -> float:
    """Redondeo al tick de IBKR: 2 decimales ≥$1, 4 decimales <$1."""
    try:
        p = float(precio)
        return round(p, 2) if p >= 1.0 else round(p, 4)
    except Exception:
        return precio


# Festivos de Wall Street (NYSE/Nasdaq). Sin esto, Litch creería que el
# mercado está abierto un 4 de julio y analizaría datos congelados.
FESTIVOS_NYSE = {
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}

# Media sesión: cierra 13:00 ET
MEDIAS_SESIONES = {"2026-11-27", "2026-12-24", "2027-11-26"}


def _ahora_ny():
    """Hora actual en Nueva York, respetando el horario de verano.

    CRÍTICO: Colombia es UTC-5 todo el año; Nueva York alterna entre UTC-5
    (invierno) y UTC-4 (verano). Usar la hora local de Colombia como si
    fuera de Nueva York desfasa el mercado una hora media parte del año.
    """
    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        pass
    # Respaldo: calcular el horario de verano de EEUU a mano
    # (2º domingo de marzo → 1er domingo de noviembre)
    u = datetime.now(timezone.utc)
    año = u.year

    def _domingo(mes, n):
        d = datetime(año, mes, 1, tzinfo=timezone.utc)
        # días hasta el primer domingo
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)

    inicio = _domingo(3, 2).replace(hour=7)     # 2:00 ET = 07:00 UTC
    fin = _domingo(11, 1).replace(hour=6)
    verano = inicio <= u < fin
    return u + timedelta(hours=-4 if verano else -5)


def mercado_abierto() -> tuple[bool, str]:
    """¿Está abierto Wall Street? Calculado en hora real de Nueva York."""
    ny = _ahora_ny()
    fecha = ny.strftime("%Y-%m-%d")
    hhmm = ny.strftime("%H:%M")

    if ny.weekday() >= 5:
        return False, (f"Fin de semana (en Nueva York son las {hhmm}). "
                       f"Wall Street cierra sábado y domingo.")

    if fecha in FESTIVOS_NYSE:
        return False, (f"Hoy {fecha} es festivo en Wall Street: el mercado "
                       f"no abre. Los datos que vea estarán congelados.")

    minutos = ny.hour * 60 + ny.minute
    cierre = 780 if fecha in MEDIAS_SESIONES else 960     # 13:00 o 16:00

    if minutos < 570:                                     # antes de 9:30
        faltan = 570 - minutos
        if minutos >= 240:                                # desde 4:00 ET
            return False, (f"Pre-mercado (en Nueva York son las {hhmm}). "
                           f"Abre la sesión regular en {faltan // 60}h "
                           f"{faltan % 60}m. Ahora hay poca liquidez y los "
                           f"spreads son anchos.")
        return False, (f"Cerrado (en Nueva York son las {hhmm}). "
                       f"Abre a las 9:30 ET, en {faltan // 60}h "
                       f"{faltan % 60}m.")

    if minutos < cierre:
        restan = cierre - minutos
        aviso = ""
        if minutos < 600:      # primeros 30 minutos
            aviso = (" Estamos en los primeros 30 minutos: es el tramo más "
                     "volátil del día, el que más barre stops. Prudencia.")
        elif restan <= 30:
            aviso = (" Últimos 30 minutos: la volatilidad repunta al cierre.")
        media = " (media sesión, cierra 13:00 ET)" if cierre == 780 else ""
        return True, (f"Mercado ABIERTO{media} — en Nueva York son las "
                      f"{hhmm}, quedan {restan // 60}h {restan % 60}m." + aviso)

    if minutos < 1200:         # hasta 20:00 ET
        return False, (f"Post-mercado (en Nueva York son las {hhmm}). "
                       f"La sesión regular ya cerró; la liquidez es baja y "
                       f"los precios pueden saltar.")

    return False, (f"Cerrado (en Nueva York son las {hhmm}). "
                   f"La próxima sesión abre mañana a las 9:30 ET.")


# ── Datos del símbolo pedido ────────────────────────────────────────────────
#
# ESTO ARREGLA UN FALLO GRAVE: antes se pedían las velas a tv_feed, que sigue
# el activo configurado de IQ Option (normalmente EURUSD). Analizar "SPY"
# devolvía el análisis de EUR/USD con la etiqueta SPY encima. Un programa que
# se equivoca y avisa es molesto; uno que acierta la forma y falla el fondo
# es peligroso, porque nadie lo revisa.
#
# Ahora se descarga el símbolo que se pidió, y si no se puede, se dice.

_CACHE_VELAS: dict = {}
_CACHE_SEGS = 60          # un minuto: suficiente para no martillear Yahoo


def velas_de(app, simbolo: str, n: int = 150) -> tuple[list, str]:
    """Cierres del símbolo pedido. Devuelve (cierres, de dónde salieron).

    Orden de preferencia:
      1. El feed en vivo, PERO solo si está siguiendo este mismo símbolo.
      2. Descarga directa de Yahoo para este símbolo.
    """
    simbolo = (simbolo or "").upper().strip()
    if not simbolo:
        return [], "sin símbolo"

    ahora = time.time()
    ent = _CACHE_VELAS.get(simbolo)
    if ent and ahora - ent[0] < _CACHE_SEGS:
        return ent[1], ent[2] + " (caché)"

    # 1) El feed, solo si de verdad va de este símbolo
    try:
        feed = getattr(app, "tv_feed", None)
        if feed is not None:
            ticker = str(getattr(feed, "_ticker_yf", "") or "").upper()
            if ticker == simbolo:
                vs = feed.obtener_velas(n) or []
                c = [float(v.get("close", 0)) for v in vs if v.get("close")]
                if len(c) >= 30:
                    _CACHE_VELAS[simbolo] = (ahora, c, "feed en vivo")
                    return c, "feed en vivo"
    except Exception:
        pass

    # 2) Yahoo, directo y para el símbolo correcto
    try:
        import yfinance as yf
        import logging
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)

        hist = yf.Ticker(simbolo).history(period="1y", interval="1d",
                                          auto_adjust=True)
        if hist is None or len(hist) == 0:
            return [], f"Yahoo no devolvió datos de {simbolo}"
        c = [float(x) for x in hist["Close"].tolist()
             if x == x and x > 0]          # x == x descarta NaN
        c = c[-n:]
        if len(c) >= 30:
            _CACHE_VELAS[simbolo] = (ahora, c, "Yahoo (velas diarias)")
            return c, "Yahoo (velas diarias)"
        return c, f"Yahoo solo dio {len(c)} velas de {simbolo}"
    except ImportError:
        return [], ("falta yfinance — instálelo con: "
                    "py -m pip install yfinance")
    except Exception as e:
        return [], f"error descargando {simbolo}: {e}"


# ── Análisis de una acción ──────────────────────────────────────────────────

def analizar_accion(app, simbolo: str, velas: list | None = None) -> dict:
    """Analiza una acción y devuelve un veredicto con su razonamiento.

    Devuelve {"direccion": "COMPRA"|"VENTA"|"ESPERA", "votos": int,
              "confianza": float, "razones": [str], "atr": float,
              "precio": float}
    """
    from . import indicadores as ind

    resultado = {"simbolo": simbolo, "direccion": "ESPERA", "votos": 0,
                 "confianza": 0.0, "razones": [], "atr": 0.0, "precio": 0.0}

    # 1) Conseguir velas DEL SÍMBOLO PEDIDO
    cierres = []
    fuente = ""
    try:
        if velas:
            cierres = [float(v.get("close", v.get("Close", 0))) for v in velas]
            fuente = "velas recibidas"
        else:
            cierres, fuente = velas_de(app, simbolo)
    except Exception as e:
        resultado["razones"].append(f"No pude traer los datos: {e}")

    resultado["fuente"] = fuente

    if len(cierres) < 30:
        resultado["razones"].append(
            f"No tengo suficientes velas de {simbolo} "
            f"({len(cierres)} de 30 mínimo): no concluyo nada. Prefiero "
            f"callarme antes que opinar sobre cuatro datos.")
        return resultado

    resultado["precio"] = _redondear(cierres[-1])

    votos_alza = 0
    votos_baja = 0

    # 2) Tendencia por medias móviles
    try:
        import numpy as _np
        arr = _np.array(cierres, dtype=float)
        ema20 = ind.ema(arr, 20)[-1]
        ema50 = ind.ema(arr, 50)[-1] if len(arr) >= 50 else ema20
        if cierres[-1] > ema20 > ema50:
            votos_alza += 2
            resultado["razones"].append(
                "Tendencia alcista: precio sobre EMA20 y EMA20 sobre EMA50.")
        elif cierres[-1] < ema20 < ema50:
            votos_baja += 2
            resultado["razones"].append(
                "Tendencia bajista: precio bajo EMA20 y EMA20 bajo EMA50.")
        else:
            resultado["razones"].append("Tendencia mixta (medias entrelazadas).")
    except Exception:
        pass

    # 3) RSI
    try:
        r = ind.rsi(cierres, 14)
        if r is not None:
            if r < 35:
                votos_alza += 1
                resultado["razones"].append(f"RSI {r:.0f}: sobreventa, rebote posible.")
            elif r > 65:
                votos_baja += 1
                resultado["razones"].append(f"RSI {r:.0f}: sobrecompra, agotamiento.")
            else:
                resultado["razones"].append(f"RSI {r:.0f}: zona neutral.")
    except Exception:
        pass

    # 4) MACD
    try:
        m = ind.macd(cierres)
        if m and isinstance(m, (tuple, list)) and len(m) >= 2:
            linea, senal = float(m[0]), float(m[1])
            if linea > senal:
                votos_alza += 1
                resultado["razones"].append("MACD sobre su señal: impulso alcista.")
            else:
                votos_baja += 1
                resultado["razones"].append("MACD bajo su señal: impulso bajista.")
    except Exception:
        pass

    # 5) ATR (para dimensionar, no para dirección)
    try:
        a = ind.atr(cierres, 14)
        if a:
            resultado["atr"] = _redondear(a)
            resultado["razones"].append(
                f"ATR {resultado['atr']}: volatilidad para calcular el stop.")
    except Exception:
        pass

    # 6) Veredicto — en acciones exigimos consenso claro
    if votos_alza >= VOTOS_MIN_ACCIONES and votos_alza > votos_baja:
        resultado["direccion"] = "COMPRA"
        resultado["votos"] = votos_alza
    elif votos_baja >= VOTOS_MIN_ACCIONES and votos_baja > votos_alza:
        resultado["direccion"] = "VENTA"
        resultado["votos"] = votos_baja
    else:
        resultado["direccion"] = "ESPERA"
        resultado["votos"] = max(votos_alza, votos_baja)
        resultado["razones"].append(
            "Sin consenso suficiente: en acciones se opera menos y mejor. "
            "Abstenerse también es una decisión.")

    # ── Confianza honesta ───────────────────────────────────────────────────
    # La fórmula anterior era max(alza,baja)/(alza+baja). Con 3 votos a favor
    # y 0 en contra daba 100%: medía el ACUERDO pero ignoraba cuánta
    # evidencia había. Tres señales de acuerdo entre tres no es lo mismo que
    # tres entre ocho, y presentarlo como certeza total es engañoso.
    #
    # Ahora se divide por el máximo de votos que se PODÍAN emitir (4:
    # tendencia vale 2, RSI 1, MACD 1). Así la confianza baja cuando faltan
    # señales, que es exactamente lo que debe pasar.
    VOTOS_MAX = 4
    dominante = max(votos_alza, votos_baja)
    emitidos = votos_alza + votos_baja

    if resultado["direccion"] == "ESPERA":
        # Abstenerse no tiene "confianza en la dirección": no hay dirección.
        # Lo que se informa es lo cerca que estuvo de haber consenso.
        resultado["confianza"] = round(dominante / VOTOS_MAX, 2)
        resultado["confianza_es"] = "cercanía a un consenso"
    else:
        acuerdo = dominante / max(emitidos, 1)      # ¿discrepan las señales?
        cobertura = dominante / VOTOS_MAX           # ¿cuánta evidencia hay?
        resultado["confianza"] = round(acuerdo * cobertura, 2)
        resultado["confianza_es"] = "acuerdo × evidencia disponible"

    resultado["votos_max"] = VOTOS_MAX
    resultado["votos_contra"] = min(votos_alza, votos_baja)
    return resultado


# ── Construcción de la operación (bracket) ──────────────────────────────────

def preparar_operacion(app, simbolo: str, capital: float = None) -> dict:
    """Prepara una operación completa con bracket. NO la envía.

    Devuelve un plan legible: entrada, stop, objetivo, cantidad y razones.
    """
    an = analizar_accion(app, simbolo)
    plan = {"simbolo": simbolo, "accion": an["direccion"], "listo": False,
            "analisis": an, "mensaje": ""}

    if an["direccion"] == "ESPERA":
        plan["mensaje"] = (f"{simbolo}: sin señal clara. "
                           + " ".join(an["razones"][-2:]))
        return plan

    precio = an["precio"]
    atr    = an["atr"] or (precio * 0.01)   # 1% si no hay ATR

    # Capital: el del usuario o el saldo conocido
    if capital is None:
        try:
            capital = float(app.mem["config"].get("capital_ibkr", 0)) or 1000.0
        except Exception:
            capital = 1000.0

    riesgo_dolares = capital * RIESGO_PCT_DEFECTO
    dist_stop      = ATR_MULT_STOP * atr
    if dist_stop <= 0:
        plan["mensaje"] = "No pude calcular el stop (ATR inválido)."
        return plan

    cantidad = max(1, int(riesgo_dolares / dist_stop))

    if an["direccion"] == "COMPRA":
        entrada  = _redondear(precio)
        stop     = _redondear(precio - dist_stop)
        objetivo = _redondear(precio + dist_stop * RATIO_OBJETIVO)
    else:
        entrada  = _redondear(precio)
        stop     = _redondear(precio + dist_stop)
        objetivo = _redondear(precio - dist_stop * RATIO_OBJETIVO)

    # ── MEMORIA: ¿este setup me ha ganado o perdido antes? ──────────────
    # Litch consulta su experiencia previa ANTES de operar. Si el setup es
    # peligroso, se abstiene aunque los indicadores digan que sí.
    veredicto = {"tipo": "neutral", "mensaje": ""}
    try:
        from . import memoria_acciones as _mem_acc
        ctx_setup = {
            "tendencia": ("alcista" if an["direccion"] == "COMPRA"
                          else "bajista"),
            "rsi": next((r for r in an["razones"] if "RSI" in r), None),
            "sesion": "ny",
        }
        # Extraer el número del RSI del texto de razones
        try:
            import re as _re_r
            for _r in an["razones"]:
                _m = _re_r.search(r"RSI (\d+)", _r)
                if _m:
                    ctx_setup["rsi"] = float(_m.group(1))
                    break
        except Exception:
            pass
        plan["contexto_setup"] = ctx_setup
        veredicto = _mem_acc.obtener().veredicto_setup(
            simbolo, an["direccion"], ctx_setup)
        plan["memoria"] = veredicto
        if veredicto["tipo"] == "peligroso":
            plan["listo"] = False
            plan["mensaje"] = (
                f"{simbolo}: me abstengo. {veredicto['mensaje']} "
                f"Mi experiencia pesa más que los indicadores de hoy.")
            return plan
    except Exception:
        pass

    plan.update({
        "listo": True, "entrada": entrada, "stop": stop,
        "objetivo": objetivo, "cantidad": cantidad,
        "riesgo_dolares": round(riesgo_dolares, 2),
        "ratio": RATIO_OBJETIVO,
    })
    plan["mensaje"] = (
        f"Plan para {simbolo} ({an['direccion']}):\n"
        f"· Entrada LÍMITE: {entrada}\n"
        f"· Stop-loss: {stop}  (riesgo ${riesgo_dolares:.2f}, "
        f"{ATR_MULT_STOP}× ATR)\n"
        f"· Objetivo: {objetivo}  (ratio {RATIO_OBJETIVO}:1)\n"
        f"· Cantidad: {cantidad} acciones\n"
        f"· Votos: {an['votos']} | Confianza: {int(an['confianza']*100)}%\n"
        f"Razones: " + " ".join(an["razones"][:3])
    )
    if veredicto.get("mensaje"):
        plan["mensaje"] += f"\nMemoria: {veredicto['mensaje']}"
    return plan


def resumen_analisis(app, simbolo: str = "SPY") -> str:
    """Texto para «Litch, analiza SPY»."""
    simbolo = (simbolo or "SPY").upper().strip()
    ok, motivo = mercado_abierto()
    an = analizar_accion(app, simbolo)

    cab = f"Análisis de {simbolo} — {motivo}\n"

    # Decir SIEMPRE de dónde salieron los datos. Un análisis sin procedencia
    # no se puede comprobar, y lo que no se puede comprobar no se debería
    # usar para arriesgar dinero.
    fuente = an.get("fuente") or "sin determinar"
    cab += f"Datos: {fuente}\n"

    if not an["razones"] and an["direccion"] == "ESPERA":
        return cab + "No pude analizar nada, señor."

    if an["precio"] == 0:
        return (cab + "· " + "\n· ".join(an["razones"]) +
                "\n\nSin datos no hay análisis. No me invento un veredicto.")

    contra = an.get("votos_contra", 0)
    vmax = an.get("votos_max", 4)
    cuerpo = (f"Dirección: {an['direccion']} | "
              f"votos {an['votos']} de {vmax}"
              + (f" ({contra} en contra)" if contra else "")
              + f" | confianza {int(an['confianza']*100)}%"
              + (f" ({an['confianza_es']})" if an.get("confianza_es") else "")
              + f"\nPrecio: {an['precio']} | ATR: {an['atr']}\n")
    razones = "\n".join(f"· {r}" for r in an["razones"])

    cierre = ""
    if an["direccion"] == "ESPERA":
        cierre = ("\n\nMe abstengo: no hay acuerdo suficiente entre las "
                  "señales. No operar también es una decisión, y suele ser "
                  "la buena cuando el cuadro no está claro.")
    elif not ok:
        cierre = ("\n\nOJO: el mercado está cerrado, así que estos datos "
                  "están congelados. Sirven para estudiar, no para decidir "
                  "una entrada ahora.")

    return cab + cuerpo + razones + cierre


def activos_sugeridos() -> str:
    lineas = [f"· {s} — {d}" for s, d in ACTIVOS_RECOMENDADOS]
    return ("Para empezar en Wall Street le recomiendo activos líquidos "
            "y estables:\n" + "\n".join(lineas) +
            "\nLos ETF (SPY, VOO, QQQ) son canastas de muchas empresas: "
            "menos sustos que una acción individual.")
