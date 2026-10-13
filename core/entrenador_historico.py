"""
Entrenador Histórico — Litch se entrena solo con datos REALES del mercado.

Descarga velas OHLCV reales (Yahoo Finance, gratuito) de varios activos y
timeframes, las convierte a secuencias de colores 'V'/'R' y pre-entrena la
Red Maestra (CNN + LSTM + MLP) sin necesidad de mirar la pantalla ni de
esperar velas en vivo. Miles de velas de experiencia en minutos.

Uso:
  · Por voz/chat:  «Litch, entrena con historial»
  · Por código:    entrenar_en_fondo(app)

Honestidad técnica: entrenar con EUR/USD real mejora la intuición general
de secuencias del mercado, pero los activos OTC del broker son sintéticos:
el ajuste fino en vivo (velas de pantalla) sigue siendo necesario.
"""

from __future__ import annotations

import threading
import time

try:
    import logging as _logging
    import yfinance as _yf
    _logging.getLogger("yfinance").setLevel(_logging.CRITICAL)
    _YF_OK = True
except Exception:
    _YF_OK = False

# Activos reales líquidos para el pre-entrenamiento.
# PRIORIDAD: acciones y ETFs de Wall Street — es lo que Litch va a operar
# en IBKR. Antes solo entrenaba con divisas/oro, que se comportan distinto.
SIMBOLOS_DEFECTO = [
    ("SPY",   "S&P 500 ETF"),
    ("QQQ",   "Nasdaq 100 ETF"),
    ("VOO",   "S&P 500 (Vanguard)"),
    ("AAPL",  "Apple"),
    ("MSFT",  "Microsoft"),
    ("NVDA",  "Nvidia"),
    ("AMZN",  "Amazon"),
    ("GOOGL", "Alphabet"),
]

# Divisas y materias primas (contexto adicional, menor prioridad)
SIMBOLOS_EXTRA = [
    ("EURUSD=X", "EUR/USD"),
    ("GC=F",     "Oro"),
    ("BTC-USD",  "Bitcoin"),
]

# (intervalo yfinance, período máximo permitido por Yahoo)
INTERVALOS = [
    ("1m",  "5d"),    # ~1900 velas por símbolo
    ("5m",  "1mo"),   # ~1700 velas
    ("15m", "1mo"),
]

_entrenando = False


def disponible() -> bool:
    return _YF_OK


def descargar_colores(simbolo: str, intervalo: str, periodo: str) -> list:
    """Descarga OHLCV y devuelve la secuencia de colores 'V'/'R'."""
    if not _YF_OK:
        return []
    try:
        df = _yf.download(simbolo, interval=intervalo, period=periodo,
                          progress=False, auto_adjust=True)
        if df is None or df.empty:
            return []
        colores = []
        cierres  = df["Close"].values.flatten()
        aperturas = df["Open"].values.flatten()
        for o, c in zip(aperturas, cierres):
            try:
                o = float(o); c = float(c)
            except Exception:
                continue
            if c > o:
                colores.append("V")
            elif c < o:
                colores.append("R")
            # dojis exactos se omiten (no aportan dirección)
        return colores
    except Exception:
        return []


def _esperar_red_libre(red, timeout: float = 240.0) -> bool:
    """Espera a que la Red Maestra termine su entrenamiento en curso."""
    t0 = time.time()
    while getattr(red, "_entrenando", False):
        if time.time() - t0 > timeout:
            return False
        time.sleep(2)
    return True


def entrenar_todo(app, simbolos: list | None = None) -> str:
    """Entrena la Red Maestra con historial real. BLOQUEANTE — usar en hilo."""
    global _entrenando
    if _entrenando:
        return "Ya hay un entrenamiento histórico en curso, señor."
    if not _YF_OK:
        return ("No tengo yfinance instalado. Ejecute: "
                "pip install yfinance — y podré entrenarme solo.")

    red = getattr(app, "red", None)
    if red is None:
        return "Red Maestra no disponible."

    _entrenando = True
    t_inicio    = time.time()
    total_velas = 0
    sesiones    = 0
    try:
        pares = simbolos or SIMBOLOS_DEFECTO
        # Sonda rápida: si el PRIMER símbolo no devuelve velas, yfinance no
        # está funcionando (sin internet, sin instalar, o Yahoo bloqueado).
        # Abortamos temprano en vez de gastar 20 minutos descargando nada.
        _sonda = descargar_colores(pares[0][0], INTERVALOS[0][0],
                                   INTERVALOS[0][1])
        if len(_sonda) < 60:
            _entrenando = False
            msg = ("No pude descargar velas reales (yfinance no responde o no "
                   "está instalado). Ejecute 'pip install yfinance' y revise "
                   "su internet. Omito el entrenamiento histórico por ahora.")
            app.log(f"[EntrenadorHist] ⚠ {msg}")
            # Desactivar el auto-reintento de esta sesión para no gastar CPU
            try:
                app.mem["config"]["entrenamiento_auto"] = False
            except Exception:
                pass
            return msg

        for ticker, nombre in pares:
            for intervalo, periodo in INTERVALOS:
                colores = descargar_colores(ticker, intervalo, periodo)
                if len(colores) < 60:
                    continue
                app.log(f"[EntrenadorHist] {nombre} {intervalo}: "
                        f"{len(colores)} velas reales descargadas.")
                if not _esperar_red_libre(red):
                    app.log("[EntrenadorHist] ⚠ Red ocupada demasiado tiempo — "
                            "continúo con el siguiente lote.")
                    continue
                try:
                    red.entrenar(colores)
                    sesiones    += 1
                    total_velas += len(colores)
                except Exception as e:
                    app.log(f"[EntrenadorHist] Error entrenando: {e}")
                # Ceder CPU entre lotes para no trabar el equipo
                time.sleep(3)

        # Esperar el último entrenamiento y guardar pesos
        _esperar_red_libre(red)
        try:
            if hasattr(red, "_guardar_todo"):
                red._guardar_todo()
            if hasattr(red, "_guardar_stats"):
                red._guardar_stats()
        except Exception:
            pass

        # Registrar en el coordinador de autoaprendizaje
        try:
            aa = getattr(app, "autoaprendizaje", None)
            if aa:
                aa.registrar("entrenador_historico", True,
                             f"{total_velas} velas")
        except Exception:
            pass

        mins = (time.time() - t_inicio) / 60
        msg = (f"Entrenamiento histórico completo, señor: {total_velas} velas "
               f"reales de {len(pares)} activos en {sesiones} sesiones "
               f"({mins:.1f} min). Pesos guardados.")
        app.log(f"[EntrenadorHist] ✓ {msg}")
        return msg
    finally:
        _entrenando = False


def entrenar_en_fondo(app, simbolos: list | None = None) -> None:
    """Lanza el entrenamiento histórico en un hilo daemon."""
    def _run():
        try:
            resultado = entrenar_todo(app, simbolos)
            try:
                app.decir(resultado)
            except Exception:
                pass
        except Exception as e:
            app.log(f"[EntrenadorHist] Error: {e}")
    threading.Thread(target=_run, daemon=True,
                     name="LitchEntrenadorHist").start()


def en_curso() -> bool:
    return _entrenando


# ═══════════════════════════════════════════════════════════════════════════
# MODO NOCTURNO — ciclos de entrenamiento automáticos durante toda la noche
# ═══════════════════════════════════════════════════════════════════════════

_nocturno_stop = threading.Event()
_nocturno_activo = False


def modo_nocturno_activo() -> bool:
    return _nocturno_activo


def iniciar_modo_nocturno(app, cada_min: int = 90) -> str:
    """Entrena con datos reales frescos cada `cada_min` minutos, sin parar.

    Pensado para dejar a Litch aprendiendo toda la noche: cada ciclo
    descarga las velas más recientes del mercado real, reentrena la Red
    Maestra y guarda TODO. Combínalo con el modo Práctica en IQ Option
    para que además aprenda de las velas del broker en vivo.
    """
    global _nocturno_activo
    if _nocturno_activo:
        return "El modo nocturno ya está activo, señor."
    if not _YF_OK:
        return ("Necesito yfinance para el modo nocturno: "
                "pip install yfinance")

    _nocturno_stop.clear()
    _nocturno_activo = True

    def _loop():
        global _nocturno_activo
        ciclo = 0
        app.log(f"[Nocturno] ✓ Modo nocturno iniciado — ciclo cada {cada_min} min.")
        while not _nocturno_stop.is_set():
            ciclo += 1
            try:
                app.log(f"[Nocturno] Ciclo {ciclo}: descargando velas frescas…")
                entrenar_todo(app)
                # Guardado total tras cada ciclo (por si hay un corte de luz)
                aa = getattr(app, "autoaprendizaje", None)
                if aa:
                    aa.guardar_todo()
                app.log(f"[Nocturno] Ciclo {ciclo} completo. "
                        f"Próximo en {cada_min} min.")
            except Exception as e:
                app.log(f"[Nocturno] Error en ciclo {ciclo}: {e}")
            _nocturno_stop.wait(cada_min * 60)
        _nocturno_activo = False
        app.log("[Nocturno] Modo nocturno detenido.")

    threading.Thread(target=_loop, daemon=True,
                     name="LitchNocturno").start()
    return (f"Modo nocturno activado, señor. Entrenaré con velas reales "
            f"frescas cada {cada_min} minutos y guardaré todo tras cada "
            f"ciclo. Puede irse a dormir tranquilo.")


def detener_modo_nocturno() -> str:
    if not _nocturno_activo:
        return "El modo nocturno no estaba activo, señor."
    _nocturno_stop.set()
    return "Modo nocturno detenido. Todo lo aprendido quedó guardado."
