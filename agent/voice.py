"""
Motor de voz LITCH usando edge-tts (Microsoft Neural TTS) + WinMM nativo para reproducción.
No requiere pygame ni instalaciones adicionales — usa la API multimedia de Windows.
"""

import asyncio
import ctypes
import logging
import os
import queue
import tempfile
import threading
import time
from typing import Optional

try:
    import edge_tts
    EDGE_TTS_OK = True
except ImportError:
    EDGE_TTS_OK = False

log = logging.getLogger("LITCH.Voice")

# Voces españolas disponibles en edge-tts (de mayor a menor preferencia para LITCH)
SPANISH_VOICES = [
    "es-MX-JorgeNeural",    # Hombre mexicano — profundo, Jarvis-like
    "es-ES-AlvaroNeural",   # Hombre España
    "es-MX-DaliaNeural",    # Mujer mexicana
    "es-ES-ElviraNeural",   # Mujer España
]

DEFAULT_VOICE = "es-MX-JorgeNeural"

# API multimedia de Windows (siempre disponible, reproduce MP3 sin instalar nada)
_mci = ctypes.windll.winmm.mciSendStringW


def _play_mp3_blocking(filepath: str) -> bool:
    """Reproduce un MP3 bloqueando el hilo hasta que termine."""
    alias = "litch_snd"
    try:
        _mci(f'open "{filepath}" type mpegvideo alias {alias}', None, 0, None)
        _mci(f'play {alias} wait', None, 0, None)
        _mci(f'close {alias}', None, 0, None)
        return True
    except Exception as exc:
        log.error(f"Error WinMM reproduciendo audio: {exc}")
        return False
    finally:
        try:
            _mci(f'close {alias}', None, 0, None)
        except Exception:
            pass


async def _generate_mp3(text: str, voice: str, output_path: str):
    """Genera el archivo MP3 con edge-tts."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


class VoiceEngine:
    PREFIXES = {
        "COMPRAR": "Señal positiva. ",
        "VENDER":  "Señal negativa. ",
        "ESPERAR": "",
        "INFO":    "",
        "ALERTA":  "Atención. ",
        "INICIO":  "",
    }

    def __init__(self, cfg: dict = None):
        self.cfg = cfg or {}
        self.enabled = self.cfg.get("enabled", True)
        self.voice = DEFAULT_VOICE
        self._queue: queue.Queue = queue.Queue(maxsize=5)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._ready = False
        self._tmpdir = tempfile.mkdtemp(prefix="litch_voice_")

        if not EDGE_TTS_OK:
            log.warning("edge-tts no instalado. Voz deshabilitada.")
            self.enabled = False
            return

        if self.enabled:
            self._running = True
            self._thread = threading.Thread(
                target=self._voice_loop, daemon=True, name="LITCH-Voice"
            )
            self._thread.start()

    # ─── Loop de voz ─────────────────────────────────────────────────────────

    def _voice_loop(self):
        self._ready = True
        log.info(f"Motor de voz listo. Voz: {self.voice}")

        while self._running:
            try:
                item = self._queue.get(timeout=0.5)
                if item is None:
                    break
                text, category = item
                self._speak_now(text, category)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                log.error(f"Error en VoiceLoop: {exc}")
                time.sleep(0.5)

        # Limpiar archivos temporales
        self._cleanup_tmp()

    def _speak_now(self, text: str, category: str):
        tmp_mp3 = os.path.join(self._tmpdir, f"litch_{int(time.time()*1000)}.mp3")
        try:
            asyncio.run(_generate_mp3(text, self.voice, tmp_mp3))
            _play_mp3_blocking(tmp_mp3)
        except Exception as exc:
            log.error(f"Error generando/reproduciendo audio: {exc}")
        finally:
            try:
                os.unlink(tmp_mp3)
            except Exception:
                pass

    def _cleanup_tmp(self):
        try:
            import shutil
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        except Exception:
            pass

    # ─── API pública ──────────────────────────────────────────────────────────

    def speak(self, text: str, category: str = "INFO", priority: bool = False):
        if not self.enabled or not text:
            return
        prefix = self.PREFIXES.get(category, "")
        full_text = prefix + text

        if priority:
            # Vaciar cola para mensajes urgentes
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break

        try:
            self._queue.put_nowait((full_text, category))
        except queue.Full:
            # Si la cola está llena, descartamos (no bloquear la UI)
            pass

    def announce_signal(self, signal: str, confidence: float, pair: str = ""):
        pair_str = f"en {pair} " if pair else ""
        conf_str = f"Confianza: {confidence:.0f} por ciento."
        if signal == "COMPRAR":
            self.speak(f"Recomiendo COMPRAR {pair_str}. {conf_str}", "COMPRAR", priority=True)
        elif signal == "VENDER":
            self.speak(f"Recomiendo VENDER {pair_str}. {conf_str}", "VENDER", priority=True)
        else:
            self.speak(f"Señal de espera. {conf_str}", "ESPERAR")

    def announce_start(self):
        self.speak(
            "Sistemas en línea. LITCH activado. Listo para analizar el mercado.",
            "INICIO"
        )

    def announce_learning(self, pattern_count: int):
        self.speak(f"Patrón aprendido. Total memorizado: {pattern_count}.", "INFO")

    def stop(self):
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass

    @property
    def is_ready(self) -> bool:
        return self._ready and EDGE_TTS_OK
