"""Voz de Litch — síntesis natural bilingüe (español e inglés) con edge-tts.

Español: es-ES-AlvaroNeural | Inglés: en-GB-RyanNeural (británico, Jarvis).
La reproducción usa el motor de audio NATIVO de Windows (winmm/MCI), sin
dependencias que compilar. En otros sistemas intenta pygame si existe.
Requiere internet para sintetizar. Si el audio falla, imprime el texto.
"""
import asyncio
import os
import platform
import queue
import tempfile
import threading
import time

try:
    import edge_tts
    _TTS_OK = True
except Exception:
    _TTS_OK = False

_ES_WINDOWS = platform.system() == "Windows"

if _ES_WINDOWS:
    import ctypes
    _AUDIO_OK = True

    def _reproducir_bloqueante(ruta):
        """Reproduce un mp3 con el reproductor nativo de Windows (MCI)."""
        mci = ctypes.windll.winmm.mciSendStringW
        alias = "litchvoz"
        mci(f'close {alias}', None, 0, None)
        if mci(f'open "{ruta}" type mpegvideo alias {alias}', None, 0, None) != 0:
            return
        mci(f'play {alias} wait', None, 0, None)
        mci(f'close {alias}', None, 0, None)
else:
    try:
        import pygame
        pygame.mixer.init()
        _AUDIO_OK = True

        def _reproducir_bloqueante(ruta):
            pygame.mixer.music.load(ruta)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            pygame.mixer.music.unload()
    except Exception:
        _AUDIO_OK = False

        def _reproducir_bloqueante(ruta):
            pass

# Voz suave y amigable estilo Jarvis: ritmo sereno, tono cálido.
VOCES = {
    "es": ("es-ES-AlvaroNeural", "-5%", "-2Hz"),
    "en": ("en-GB-RyanNeural", "-5%", "-2Hz"),
}


_MAX_COLA = 5   # máximo de mensajes en cola — descarta los más viejos si se llena

class Voz:
    """Cola de voz: las frases se pronuncian en orden, sin bloquear la app.

    Mejora v2: protección contra overflow de cola.
    Si la cola tiene ≥ _MAX_COLA mensajes acumulados (señales muy rápidas o
    TTS lento), descarta los más antiguos y solo mantiene los N más recientes.
    Esto evita que Litch hable sobre una señal de hace 30 segundos cuando
    el mercado ya cambió completamente.
    """

    def __init__(self, al_hablar=None):
        self.activa    = True
        self.al_hablar = al_hablar
        self._cola     = queue.Queue()
        self._hilo     = threading.Thread(target=self._trabajador, daemon=True)
        self._hilo.start()

    def decir(self, texto, idioma="es"):
        print(f"[Litch] {texto}")
        if not self.activa or not texto or not _TTS_OK:
            return
        # Si la cola está llena, descartar el mensaje más antiguo para hacer espacio
        # Esto mantiene el audio relevante y evita hablar con retraso acumulado
        while self._cola.qsize() >= _MAX_COLA:
            try:
                self._cola.get_nowait()
            except queue.Empty:
                break
        self._cola.put((texto, idioma if idioma in VOCES else "es"))

    def _trabajador(self):
        contador  = 0
        _fallos   = 0        # fallos consecutivos online
        _offline  = False    # True cuando cambiamos a SAPI
        _retry_t  = 0.0      # timestamp del próximo intento de reconexión online
        while True:
            texto, idioma = self._cola.get()
            contador += 1

            if _offline:
                # Modo offline: SAPI sin red — reintentar online cada 120 s
                if time.time() > _retry_t:
                    _offline = False
                    _fallos  = 0
                else:
                    self._hablar_sapi(texto)
                    continue

            try:
                self._hablar(texto, idioma, contador)
                _fallos = 0
            except Exception as e:
                _fallos += 1
                if _fallos <= 2:
                    print(f"[Voz] Error TTS online: {e}")
                elif _fallos == 3:
                    print("[Voz] Sin conexion a internet — cambiando a voz SAPI offline.")
                    _offline = True
                    _retry_t = time.time() + 120  # reintentar en 2 min
                # Hablar offline de todas formas
                self._hablar_sapi(texto)

    def _hablar_sapi(self, texto: str) -> None:
        """
        Voz offline con Windows SAPI — no requiere internet.

        ━━━ POR QUÉ NO SE OÍA NADA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Esta función tenía dos defectos que juntos producían silencio
        absoluto sin un solo mensaje de error:

         1. `Popen` LANZA Y SE VA. No esperaba a que terminara de hablar.
            Como el bucle de voz sigue tomando frases de la cola, se
            lanzaban varios PowerShell a la vez y se pisaban unos a otros.
            Con dos o tres frases seguidas no se entendía ninguna; con más,
            no se oía nada.

         2. `except Exception: pass` SE TRAGABA TODO. Si PowerShell no
            estaba, si la política de ejecución lo bloqueaba, si no había
            voz instalada — nada de eso se decía. Silencio y ningún
            indicio de por qué.

        Un fallo silencioso en la voz es especialmente malo: el señor no
        puede distinguir «Litch no tiene nada que decir» de «Litch está
        rota». Ahora espera a terminar y, si falla, lo dice por escrito.
        """
        import subprocess
        safe = (texto or "").replace("'", "''").replace("`", "")[:400]
        if not safe.strip():
            return

        cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate = 1; "
            # Voz en español si la hay; si no, la que haya
            "try { $s.SelectVoiceByHints('NotSet','NotSet',0,"
            "(New-Object System.Globalization.CultureInfo 'es-ES')) } "
            "catch { } ; "
            f"$s.Speak('{safe}')"
        )
        try:
            # `run` espera a que termine de hablar. Así las frases salen
            # una detrás de otra en vez de solaparse.
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                 "-Command", cmd],
                creationflags=0x08000000,          # CREATE_NO_WINDOW
                capture_output=True, timeout=45)
            if r.returncode != 0:
                err = (r.stderr or b"").decode("utf-8", "ignore").strip()[:200]
                self._avisar_mudo(f"SAPI devolvió {r.returncode}: {err}")
        except FileNotFoundError:
            self._avisar_mudo("no encuentro PowerShell en este equipo")
        except subprocess.TimeoutExpired:
            self._avisar_mudo("SAPI tardó demasiado y lo corté")
        except Exception as e:
            self._avisar_mudo(f"SAPI falló: {e}")

    def _avisar_mudo(self, motivo: str) -> None:
        """
        Dice POR ESCRITO que no puede hablar. Una vez cada 5 minutos.

        Sin esto, quedarse mudo es indistinguible de no tener nada que
        decir — y el señor pierde el tiempo buscando el problema donde
        no está.
        """
        import time as _t
        ahora = _t.time()
        if (ahora - getattr(self, "_t_aviso_mudo", 0)) < 300:
            return
        self._t_aviso_mudo = ahora
        print(f"[Voz] ⚠ No consigo hablar: {motivo}. "
              f"El texto sigue saliendo en el registro.")

    # ── Diagnóstico ────────────────────────────────────────────────────

    def probar(self) -> str:
        """
        Comprueba las dos vías de voz y dice cuál funciona.

        Devuelve un informe legible. Es lo que hay que mirar cuando no se
        oye nada, en vez de adivinar.
        """
        import subprocess
        l = ["PRUEBA DE VOZ", ""]

        # 1. Vía online (Edge TTS)
        try:
            self._hablar("Prueba de voz en línea.", "es", 0)
            l.append("✓ Voz en línea (Edge TTS): funciona")
        except Exception as e:
            l.append(f"✗ Voz en línea (Edge TTS): {str(e)[:120]}")
            l.append("   Suele ser un 503 del servidor de Microsoft. "
                     "Es temporal y no depende de nosotros.")

        # 2. Vía offline (SAPI)
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command",
                 "Add-Type -AssemblyName System.Speech; "
                 "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 "$s.Speak('Prueba de voz sin internet.'); "
                 "$s.GetInstalledVoices() | "
                 "ForEach-Object { $_.VoiceInfo.Name }"],
                creationflags=0x08000000, capture_output=True, timeout=45)
            if r.returncode == 0:
                voces = (r.stdout or b"").decode("utf-8", "ignore").strip()
                l.append("✓ Voz sin internet (Windows SAPI): funciona")
                if voces:
                    l.append("   Voces instaladas:")
                    for v in voces.splitlines()[:6]:
                        l.append(f"     · {v.strip()}")
            else:
                err = (r.stderr or b"").decode("utf-8", "ignore").strip()[:200]
                l.append(f"✗ Voz sin internet (SAPI): {err or 'error ' + str(r.returncode)}")
        except FileNotFoundError:
            l.append("✗ Voz sin internet: no encuentro PowerShell")
        except Exception as e:
            l.append(f"✗ Voz sin internet: {str(e)[:120]}")

        l.append("")
        l.append("Si oyó las dos frases, la voz está bien. Si no oyó "
                 "ninguna pero aquí sale ✓, revise el volumen de Windows "
                 "y que el altavoz correcto esté seleccionado.")
        return "\n".join(l)

    def _hablar(self, texto, idioma, n):
        ruta = os.path.join(tempfile.gettempdir(), f"litch_voz_{n % 2}.mp3")
        self._sintetizar_seguro(texto, idioma, ruta)
        if _AUDIO_OK:
            if self.al_hablar:
                try:
                    self.al_hablar(True)
                except Exception:
                    pass
            try:
                _reproducir_bloqueante(ruta)
            finally:
                if self.al_hablar:
                    try:
                        self.al_hablar(False)
                    except Exception:
                        pass

    def _sintetizar_seguro(self, texto, idioma, ruta):
        """Sintetiza en un bucle de eventos PROPIO y limpio.

        Antes usaba asyncio.run() directamente. El problema: si otra parte
        del programa parchea asyncio —ib_async lo hacía con startLoop/
        nest_asyncio— asyncio.run() empieza a fallar con «Timeout should be
        used inside a task» y la voz se cae entera.

        Se vio en el registro del usuario: el mismo error aparecía en la
        conexión a IBKR y en el TTS. La causa era el parche global.
        Ya no se llama a startLoop, pero la voz no debería depender de que
        nadie más se porte bien: aquí se crea un bucle nuevo, se usa y se
        cierra. Aislado de lo que haga el resto.
        """
        bucle = None
        try:
            bucle = asyncio.new_event_loop()
            bucle.run_until_complete(self._sintetizar(texto, idioma, ruta))
        finally:
            if bucle is not None:
                try:
                    bucle.close()
                except Exception:
                    pass

    async def _sintetizar(self, texto, idioma, ruta):
        voz, velocidad, tono = VOCES[idioma]
        com = edge_tts.Communicate(texto, voz, rate=velocidad, pitch=tono)
        await com.save(ruta)
