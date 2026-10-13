"""
Watchdog — guardián anti-crash de Litch.

Monitorea los hilos críticos cada 30 segundos y los reinicia
si mueren inesperadamente. También detecta fugas de memoria,
atrancamiento del loop principal y bloqueos de UI.

Anti-crash garantizado (v2):
  • Si un hilo muere      → lo reinicia automáticamente (máx. 10 intentos/hora)
  • Si el loop principal se atasca > 120s → alerta por log y voz
  • Si RAM > 1 GB         → alerta; libera caché de litch si es posible
  • Si thread count > 60  → alerta de posible fuga de threads
  • Si hay excepción no capturada → la registra en crash_log.json
  • Heartbeat detallado con métricas de sistema en el log periódico
"""

import gc
import json
import os
import platform
import sys
import threading
import time
import traceback
from typing import Callable, Optional

from . import memoria as mem_mod

# ── psutil — opcional: no crashear si no está instalado ─────────────────────
try:
    import psutil
    _PSUTIL = True
    _PROC   = psutil.Process(os.getpid())
except ImportError:
    _PSUTIL = False
    _PROC   = None

_ES_WINDOWS = platform.system() == "Windows"


_MAX_REINICIOS_HORA = 10    # máximo de reinicios por hilo por hora
_INTERVALO_CHECK    = 30    # segundos entre checks
_TIMEOUT_LOOP       = 120   # segundos antes de considerar loop colgado
_LIMITE_RAM_MB      = 1024  # MB — alerta de fuga de memoria
_LIMITE_THREADS     = 60    # alerta si hay demasiados threads vivos
_RUTA_CRASH_LOG     = None  # se asigna en __init__


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class EntradaHilo:
    """Registro de un hilo monitoreado."""
    def __init__(self, nombre: str, fabrica: Callable,
                 critico: bool = False):
        self.nombre    = nombre
        self.fabrica   = fabrica   # función que crea y arranca el hilo de nuevo
        self.critico   = critico   # si muere, alertar por voz
        self.reinicios : list[float] = []  # timestamps de reinicios recientes
        self.ultimo_ok : float = time.time()


class Watchdog(threading.Thread):
    """
    Daemon vigilante de Litch.

    Se arranca una vez desde litch.py y corre para siempre,
    mirando que todos los hilos vitales estén vivos.
    """

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchWatchdog")
        self.app    = app
        self._hilos : dict[str, EntradaHilo] = {}
        self._lock  = threading.Lock()
        self._ultimo_heartbeat: float = time.time()

        # ── Métricas de sistema ──────────────────────────────────────────────
        self._ram_pico_mb: float = 0.0
        self._thread_pico: int   = 0
        self._ultima_alerta_ram: float = 0.0
        self._alertas_thread: int = 0

        # ── Flash-crash detector ─────────────────────────────────────────────
        # Monitorea la secuencia de velas para detectar flash crashes:
        # si en menos de 30s llegan 4+ velas del mismo color → alerta
        self._fc_ultimo_ts: float   = 0.0   # timestamp de la última alerta
        self._fc_racha_cache: int   = 0     # racha de velas guardada en última check
        self._fc_color_cache: str   = ""    # color de la racha anterior
        self._fc_alerta_hasta: float= 0.0   # no repetir alerta por 90s

        global _RUTA_CRASH_LOG
        _RUTA_CRASH_LOG = os.path.join(
            mem_mod.ruta_memoria_ap(), "crash_log.json")
        self._instalar_manejador_global()

    # ── API pública ──────────────────────────────────────────────────────────

    def registrar(self, nombre: str, fabrica: Callable,
                  critico: bool = False) -> None:
        """
        Registra un hilo para ser vigilado.

        nombre  : mismo nombre del thread (threading.Thread.name)
        fabrica : función sin args que crea y arranca el hilo de nuevo
        critico : si True, Litch habla cuando muere y se reinicia
        """
        with self._lock:
            self._hilos[nombre] = EntradaHilo(nombre, fabrica, critico)

    def heartbeat(self) -> None:
        """Llamar desde el loop principal para indicar que sigue vivo."""
        self._ultimo_heartbeat = time.time()

    def estado(self) -> dict:
        """Resumen del estado de todos los hilos monitoreados más métricas."""
        activos = {t.name for t in threading.enumerate()}
        hilos = {
            nombre: {
                "vivo":       nombre in activos,
                "reinicios":  len(e.reinicios),
                "ultimo_ok":  time.strftime("%H:%M:%S", time.localtime(e.ultimo_ok)),
            }
            for nombre, e in self._hilos.items()
        }
        sys_info = self._metricas_sistema()
        return {"hilos": hilos, "sistema": sys_info}

    def _metricas_sistema(self) -> dict:
        """Devuelve RAM, CPU, threads totales del proceso."""
        info: dict = {
            "threads_total": threading.active_count(),
            "ram_mb":        None,
            "cpu_pct":       None,
        }
        if _PSUTIL and _PROC:
            try:
                info["ram_mb"]  = round(_PROC.memory_info().rss / 1_048_576, 1)
                info["cpu_pct"] = round(_PROC.cpu_percent(interval=None), 1)
            except Exception:
                pass
        return info

    def resumen(self) -> str:
        """Texto legible del estado para el log."""
        est = self.estado()
        partes = []
        for nombre, info in est.get("hilos", {}).items():
            estado_str = "✓" if info["vivo"] else f"✗(×{info['reinicios']})"
            partes.append(f"{nombre}:{estado_str}")
        sys = est.get("sistema", {})
        ram_str = f"RAM={sys.get('ram_mb', '?')}MB" if sys.get("ram_mb") else ""
        t_str   = f"Threads={sys.get('threads_total', '?')}"
        extras  = " | ".join(x for x in [ram_str, t_str] if x)
        base    = "Watchdog | " + " | ".join(partes) if partes else "Watchdog | sin hilos"
        return base + (f" | {extras}" if extras else "")

    # ── Loop principal ────────────────────────────────────────────────────────

    def run(self) -> None:
        time.sleep(8)   # esperar a que Litch arranque por completo
        _tick = 0
        while True:
            time.sleep(_INTERVALO_CHECK)
            _tick += 1
            try:
                self._verificar_hilos()
                self._verificar_heartbeat()
                self._verificar_sistema()
                self._verificar_flash_crash()
                self._verificar_alerta_sesion()
                # Log de estado completo cada 5 ciclos (2.5 min)
                if _tick % 5 == 0:
                    self.app.log(self.resumen())
            except Exception as e:
                self._registrar_crash("watchdog_interno", e)

    # ── Verificación ─────────────────────────────────────────────────────────

    def _verificar_hilos(self) -> None:
        activos = {t.name for t in threading.enumerate()}
        with self._lock:
            entradas = list(self._hilos.items())

        for nombre, entrada in entradas:
            if nombre in activos:
                entrada.ultimo_ok = time.time()
                continue

            # El hilo murió — intentar reiniciar
            ahora = time.time()
            # Limpiar reinicios de hace más de 1 hora
            entrada.reinicios = [t for t in entrada.reinicios
                                 if ahora - t < 3600]

            if len(entrada.reinicios) >= _MAX_REINICIOS_HORA:
                self.app.log(
                    f"[Watchdog] ⛔ {nombre} ha muerto {len(entrada.reinicios)} veces "
                    f"en la última hora — no se reinicia más. Revisar manualmente.")
                continue

            self.app.log(f"[Watchdog] ⚠ Hilo '{nombre}' muerto — reiniciando "
                         f"(intento {len(entrada.reinicios)+1}/{_MAX_REINICIOS_HORA})...")
            try:
                entrada.fabrica()
                entrada.reinicios.append(ahora)
                self.app.log(f"[Watchdog] ✓ '{nombre}' reiniciado.")
                if entrada.critico:
                    self.app.decir(f"Atención: el módulo {nombre} se reinició "
                                   "automáticamente. Funcionamiento restaurado.")
            except Exception as e:
                self.app.log(f"[Watchdog] Error al reiniciar '{nombre}': {e}")
                self._registrar_crash(f"reinicio_{nombre}", e)

    def _verificar_heartbeat(self) -> None:
        """Detecta si el loop principal lleva más de 120s sin latir."""
        elapsed = time.time() - self._ultimo_heartbeat
        if elapsed > _TIMEOUT_LOOP:
            self.app.log(
                f"[Watchdog] ⚠ Loop principal sin heartbeat por "
                f"{int(elapsed)}s. Posible bloqueo.")
            try:
                self.app.decir(
                    "Atención: el motor de análisis lleva más de dos "
                    "minutos sin responder. Puede haber un bloqueo interno.")
            except Exception:
                pass
            self._ultimo_heartbeat = time.time()

    def _verificar_sistema(self) -> None:
        """Comprueba RAM, thread count y activa alertas o GC si es necesario."""
        met = self._metricas_sistema()
        ahora = time.time()

        # ── Control de RAM ────────────────────────────────────────────────────
        ram_mb = met.get("ram_mb")
        if ram_mb is not None:
            if ram_mb > self._ram_pico_mb:
                self._ram_pico_mb = ram_mb
            if ram_mb > _LIMITE_RAM_MB and ahora - self._ultima_alerta_ram > 300:
                self._ultima_alerta_ram = ahora
                self.app.log(
                    f"[Watchdog] ⚠ RAM alta: {ram_mb:.0f} MB "
                    f"(pico={self._ram_pico_mb:.0f} MB). "
                    "Ejecutando recolección de basura...")
                gc.collect()
                # Intentar comprimir caché de secuencias si existe
                try:
                    mem = self.app.mem
                    sec = mem.get("secuencia", [])
                    if len(sec) > 5000:
                        mem["secuencia"] = sec[-5000:]
                        self.app.log(
                            f"[Watchdog] Secuencia recortada de "
                            f"{len(sec)} a 5000 velas.")
                except Exception:
                    pass
                # Segunda medición tras GC
                try:
                    if _PSUTIL and _PROC:
                        ram_post = _PROC.memory_info().rss / 1_048_576
                        self.app.log(
                            f"[Watchdog] RAM post-GC: {ram_post:.0f} MB "
                            f"(liberado {ram_mb - ram_post:.0f} MB)")
                except Exception:
                    pass

        # ── Control de thread count ───────────────────────────────────────────
        n_threads = met.get("threads_total", 0)
        if n_threads > self._thread_pico:
            self._thread_pico = n_threads
        if n_threads > _LIMITE_THREADS:
            self._alertas_thread += 1
            if self._alertas_thread <= 3:
                nombres = [t.name for t in threading.enumerate()]
                self.app.log(
                    f"[Watchdog] ⚠ Thread count alto: {n_threads} "
                    f"(pico={self._thread_pico}). "
                    f"Hilos: {nombres[:20]}..."
                    if len(nombres) > 20 else str(nombres))
        else:
            self._alertas_thread = 0   # reset cuando vuelve a lo normal

    # ── Flash-crash detector ─────────────────────────────────────────────────

    def _verificar_flash_crash(self) -> None:
        """
        Detecta flash crashes: ≥4 velas del mismo color en los últimos 30s.
        Si ocurre, avisa por log + voz y marca alerta para que trading.py
        pueda consultarla antes de ejecutar el siguiente trade.
        """
        ahora = time.time()
        if ahora < self._fc_alerta_hasta:
            return   # ya alertamos recientemente
        try:
            # Umbral corregido: 4 velas iguales ocurren ~12% del tiempo por
            # puro azar (falsa alarma constante que bloqueaba rachas buenas).
            # 6+ velas iguales ocurren ~3% del tiempo: alerta con sentido.
            # Configurable con config «flash_crash_racha».
            _RACHA_MIN = int(self.app.mem.get("config", {})
                             .get("flash_crash_racha", 6))
            sec = self.app.mem.get("secuencia", [])
            if len(sec) < _RACHA_MIN:
                return
            ultimas = sec[-10:]  # últimas 10 velas
            # Racha final del mismo color
            color_fin = ultimas[-1]
            racha = 0
            for c in reversed(ultimas):
                if c == color_fin:
                    racha += 1
                else:
                    break
            if racha >= _RACHA_MIN:
                # Solo alertar si cambió la situación (evitar spam)
                if racha == self._fc_racha_cache and color_fin == self._fc_color_cache:
                    return
                self._fc_racha_cache = racha
                self._fc_color_cache = color_fin
                self._fc_alerta_hasta = ahora + 90   # silencio 90s
                color_txt = "VERDES" if color_fin in ("V", "verde", "g") else "ROJAS"
                self.app.log(
                    f"[Watchdog] FLASH-CRASH detectado: "
                    f"{racha} velas {color_txt} consecutivas. "
                    "Litch suspende el próximo trade automáticamente.")
                try:
                    self.app.decir(
                        f"Alerta, señor. Detecté {racha} velas {color_txt.lower()} "
                        "consecutivas. Posible flash crash. "
                        "Suspendiendo el próximo trade por precaución.")
                except Exception:
                    pass
                # Marcar señal de flash crash en el agente
                try:
                    self.app.agente._flash_crash_hasta = ahora + 60
                except Exception:
                    pass
                # Recentrar el gráfico tras flash crash
                try:
                    _gc = getattr(self.app, "gestor_grafico", None)
                    if _gc is not None:
                        _gc.forzar_centrado()
                except Exception:
                    pass
            else:
                self._fc_racha_cache = 0
                self._fc_color_cache = ""
        except Exception:
            pass

    def _verificar_alerta_sesion(self) -> None:
        """Revisa si hay alertas proactivas de sesión y las comunica al usuario."""
        ahora = time.time()
        # No alertar más de una vez cada 15 minutos
        if ahora < getattr(self, "_sesion_alerta_hasta", 0.0):
            return
        try:
            st = getattr(self.app.agente, "_session_tracker", None)
            if st is None:
                return
            mensaje = st.alerta_sesion()
            if mensaje:
                # Dedup: no repetir el MISMO aviso (la condición de sesión
                # persiste horas; antes se re-anunciaba cada 15 min). Solo se
                # dice de nuevo si cambió el mensaje, o tras 2h del mismo.
                _clave = mensaje[:50]
                if (_clave == getattr(self, "_sesion_ult_clave", "")
                        and ahora < getattr(self, "_sesion_ult_repetir", 0.0)):
                    self._sesion_alerta_hasta = ahora + 900
                    return
                self._sesion_ult_clave   = _clave
                self._sesion_ult_repetir = ahora + 7200   # mismo aviso: 2h
                self.app.log(f"[Sesión] {mensaje}")
                try:
                    self.app.decir(mensaje)
                except Exception:
                    pass
                self._sesion_alerta_hasta = ahora + 900   # 15 min de silencio
        except Exception:
            pass

    # ── Crash logger global ───────────────────────────────────────────────────

    def _instalar_manejador_global(self) -> None:
        """
        Captura excepciones NO manejadas en hilos secundarios.
        Python 3.8+ permite threading.excepthook.
        """
        if hasattr(threading, "excepthook"):
            _original_hook = threading.excepthook

            def _hook(args):
                if args.exc_type is SystemExit:
                    return
                # Python 3.14 renombró exc_tb → exc_traceback
                _tb_obj = (getattr(args, "exc_traceback", None)
                           or getattr(args, "exc_tb", None))
                self._registrar_crash(
                    getattr(args.thread, "name", "desconocido"),
                    args.exc_value,
                    tb="".join(traceback.format_exception(
                        args.exc_type, args.exc_value, _tb_obj)))
                if _original_hook:
                    try:
                        _original_hook(args)
                    except Exception:
                        pass

            threading.excepthook = _hook

        # También capturar excepciones en el hilo principal
        _sys_except = sys.excepthook

        def _sys_hook(tipo, valor, tb):
            if tipo is KeyboardInterrupt:
                _sys_except(tipo, valor, tb)
                return
            self._registrar_crash("hilo_principal", valor,
                                  tb="".join(traceback.format_tb(tb)))
            _sys_except(tipo, valor, tb)

        sys.excepthook = _sys_hook

    def _registrar_crash(self, nombre_hilo: str,
                         error: Exception,
                         tb: str = "") -> None:
        """Escribe el crash en crash_log.json para diagnóstico posterior."""
        entrada = {
            "ts":    _ts(),
            "hilo":  nombre_hilo,
            "error": str(error),
            "tipo":  type(error).__name__,
            "tb":    tb or traceback.format_exc(),
        }
        try:
            historial = []
            if os.path.exists(_RUTA_CRASH_LOG):
                with open(_RUTA_CRASH_LOG, "r", encoding="utf-8") as f:
                    historial = json.load(f)
            historial.append(entrada)
            historial = historial[-200:]   # máximo 200 entradas
            with open(_RUTA_CRASH_LOG, "w", encoding="utf-8") as f:
                json.dump(historial, f, ensure_ascii=False, indent=1)
        except Exception:
            pass   # no crashear al guardar el crash

        try:
            self.app.log(
                f"[Watchdog] 💥 CRASH en '{nombre_hilo}': "
                f"{type(error).__name__}: {str(error)[:120]}")
        except Exception:
            pass


def leer_crash_log(n: int = 10) -> list[dict]:
    """Lee los últimos N crashes registrados. Útil para diagnóstico."""
    if not _RUTA_CRASH_LOG or not os.path.exists(_RUTA_CRASH_LOG):
        return []
    try:
        with open(_RUTA_CRASH_LOG, "r", encoding="utf-8") as f:
            historial = json.load(f)
        return historial[-n:]
    except Exception:
        return []
