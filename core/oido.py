"""Oído de Litch — reconocimiento de voz bilingüe, Python 3.14 compatible.

Arquitectura:
  1. Captura de audio con sounddevice (tasa nativa del dispositivo: 44100 Hz)
  2. Detección de voz por umbral de RMS con calibración ambiental
  3. STT primario:  Google Speech API v2 via 'requests' + WAV/PCM (sin flac.exe)
  4. STT fallback:  Windows System.Speech offline (sin internet)

Por qué se usa 'requests' en vez de 'urllib':
  urllib en Windows Python 3.14 provoca WinError 50 (ERROR_NOT_SUPPORTED) al
  hacer POST a la API de Google. El paquete 'requests' maneja el SSL de Windows
  correctamente y no presenta ese problema.

Por qué se envía WAV en lugar de FLAC:
  speech_recognition.recognize_google() ejecuta flac-win32.exe como subprocess
  para convertir el audio. En algunas configuraciones de Windows 11 ese proceso
  también puede fallar. Enviando audio/l16 (PCM raw) se evita por completo.
"""
import io
import json
import os
import subprocess
import tempfile
import threading
import time
import wave

import numpy as np

try:
    import sounddevice as sd
    _SD_OK = True
except ImportError:
    _SD_OK = False

try:
    import requests as _requests
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

try:
    import speech_recognition as sr
    _SR_OK = True
except ImportError:
    _SR_OK = False

# ── Constantes de captura ────────────────────────────────────────────────────
UMBRAL_MINIMO   = 280      # RMS mínimo para considerar voz
FACTOR_RUIDO    = 1.9      # umbral = max(MINIMO, ruido_ambiente × FACTOR)
CHUNKS_SILENCIO = 16       # chunks consecutivos de silencio para cerrar frase
MAX_SEGUNDOS    = 14       # máximo de grabación por frase
CALENTAMIENTO   = 15       # chunks de calibración ambiental al arrancar
T_REINICIO      = 180      # reiniciar stream cada 3 minutos
MAX_ERR_CONSEC  = 8        # errores seguidos antes de reiniciar

CODIGOS = {"es": "es-ES", "en": "en-US"}

# ── Key pública de Google Speech API v2 (predeterminada de speech_recognition)
_GOOGLE_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"


# ─── Utilidades de audio ─────────────────────────────────────────────────────

def _rms(data: np.ndarray) -> float:
    return float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))


def _resamplear(audio: np.ndarray, rate_from: int, rate_to: int = 16000) -> np.ndarray:
    """Resamplea audio usando interpolación numpy. No requiere audioop."""
    if rate_from == rate_to:
        return audio
    n = int(len(audio) * rate_to / rate_from)
    return np.interp(
        np.linspace(0, len(audio) - 1, n),
        np.arange(len(audio)),
        audio.astype(np.float64)
    ).astype(np.int16)


def _detectar_dispositivo() -> tuple:
    """Devuelve (device_idx, sample_rate) compatibles con el micrófono.

    Prioriza la tasa nativa para evitar incompatibilidades con WASAPI.
    """
    if not _SD_OK:
        return None, 16000
    try:
        dev_in = sd.default.device[0]
        if dev_in is None or (isinstance(dev_in, (int, float)) and dev_in < 0):
            dev_in = None
        try:
            info   = sd.query_devices(dev_in if dev_in is not None
                                       else sd.default.device[0], 'input')
            native = int(info.get('default_samplerate', 44100))
        except Exception:
            native = 44100

        for rate in (native, 44100, 48000, 22050, 16000, 32000):
            try:
                block = max(512, int(rate * 0.05))
                with sd.InputStream(device=dev_in, samplerate=rate,
                                    channels=1, dtype='int16', blocksize=block):
                    pass
                return dev_in, rate
            except Exception:
                continue
        return dev_in, native
    except Exception:
        return None, 16000


# ─── Motores STT ─────────────────────────────────────────────────────────────

def _stt_google(audio_np: np.ndarray, rate: int, idioma: str) -> str | None:
    """STT primario: Google Speech API v2 via WAV/PCM + requests.

    - No usa flac.exe (evita WinError 50 del subprocess)
    - No usa urllib (evita WinError 50 del SSL de Windows)
    - Resamplea a 16 kHz con numpy (sin audioop)
    """
    if not _REQ_OK:
        return None

    audio_16k = _resamplear(audio_np, rate)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_16k.tobytes())
    wav_data = buf.getvalue()

    url = (f"http://www.google.com/speech-api/v2/recognize"
           f"?client=chromium&lang={idioma}&maxresults=1&pfilter=0&key={_GOOGLE_KEY}")
    try:
        resp = _requests.post(
            url, data=wav_data,
            headers={
                "Content-Type": "audio/l16; rate=16000",
                "User-Agent":   "Mozilla/5.0 (compatible; LitchIA/2.0)",
            },
            verify=False, timeout=10
        )
        if resp.status_code != 200:
            return None
        for linea in resp.text.strip().split("\n"):
            try:
                obj  = json.loads(linea)
                alts = (obj.get("result") or [{}])[0].get("alternative") or []
                txt  = alts[0].get("transcript", "").strip() if alts else ""
                if txt:
                    return txt
            except Exception:
                continue
    except Exception as exc:
        print(f"[Oído] Google STT: {exc}")
    return None


def _stt_sr_google(audio_np: np.ndarray, rate: int, idioma: str) -> str | None:
    """STT alternativo: speech_recognition.recognize_google (usa urllib + FLAC).

    Solo se intenta si requests no está disponible.
    """
    if not _SR_OK:
        return None
    try:
        audio_sr = sr.AudioData(audio_np.tobytes(), rate, 2)
        return sr.Recognizer().recognize_google(audio_sr, language=idioma)
    except sr.UnknownValueError:
        return None   # silencio — no es error
    except Exception as exc:
        print(f"[Oído] sr.recognize_google: {exc}")
        return None


def _stt_windows_sapi(audio_np: np.ndarray, rate: int, idioma: str) -> str | None:
    """STT offline: Windows System.Speech.Recognition (sin internet).

    Usa el motor de reconocimiento de voz integrado en Windows 10/11.
    Requiere que el idioma esté instalado en Configuración → Voz.
    """
    ruta = os.path.join(tempfile.gettempdir(), "litch_sapi.wav")
    audio_16k = _resamplear(audio_np, rate)
    try:
        with wave.open(ruta, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_16k.tobytes())

        locale   = "es-ES" if idioma.startswith("es") else "en-US"
        ruta_ps  = ruta.replace("\\", "\\\\")
        ps_cmd   = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Add-Type -AssemblyName System.Speech; "
            f"$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine('{locale}'); "
            "$r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar)); "
            f"$r.SetInputToWaveFile('{ruta_ps}'); "
            "$res = $r.Recognize(); "
            "if ($res) { Write-Output $res.Text } else { Write-Output '' }; "
            "$r.Dispose()"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        texto = proc.stdout.strip()
        return texto if texto else None
    except Exception as exc:
        print(f"[Oído] SAPI offline: {exc}")
        return None
    finally:
        try:
            os.remove(ruta)
        except Exception:
            pass


# ─── Clase principal ─────────────────────────────────────────────────────────

class Oido:
    def __init__(self, callback, idioma="es", al_grabar=None):
        self.callback   = callback
        self.al_grabar  = al_grabar  # callback(bool) — True mientras graba audio
        self.idioma     = CODIGOS.get(idioma, "es-ES")
        self.escuchando = False
        self.grabando   = False
        self._detener   = False
        self._hilo      = None
        self._device    = None
        self._rate      = 16000
        self._ult_err_txt = ""
        self._ult_err_t   = 0.0
        self._err_consec  = 0

        # Mostrar qué motores STT están disponibles
        motores = []
        if _REQ_OK:
            motores.append("Google-WAV(requests)")
        if _SR_OK:
            motores.append("Google-FLAC(sr)")
        motores.append("Windows-SAPI(offline)")
        print(f"[Oído] Motores STT disponibles: {', '.join(motores)}")

    def disponible(self) -> bool:
        return _SD_OK

    def set_idioma(self, idioma: str):
        self.idioma = CODIGOS.get(idioma, "es-ES")

    def iniciar(self) -> bool:
        if not self.disponible() or self.escuchando:
            return self.escuchando
        self.escuchando = True
        self._detener   = False
        self._hilo = threading.Thread(
            target=self._bucle, daemon=True, name="LitchOido")
        self._hilo.start()
        return True

    def detener(self):
        self._detener   = True
        self.escuchando = False
        self.grabando   = False

    # ─── Feedback visual ─────────────────────────────────────────────────────

    def _set_grabando(self, valor: bool):
        self.grabando = valor
        if self.al_grabar:
            try:
                self.al_grabar(valor)
            except Exception:
                pass

    # ─── Log sin spam ────────────────────────────────────────────────────────

    def _log_err(self, texto: str):
        msg   = str(texto)[:120]
        ahora = time.time()
        if msg != self._ult_err_txt or ahora - self._ult_err_t > 30:
            print(f"[Oído] {msg}")
            self._ult_err_txt = msg
            self._ult_err_t   = ahora
        self._err_consec += 1

    # ─── Bucle principal ─────────────────────────────────────────────────────

    def _bucle(self):
        self._device, self._rate = _detectar_dispositivo()

        while not self._detener:
            self._err_consec = 0
            try:
                chunk = max(512, int(self._rate * 0.08))
                with sd.InputStream(
                        device=self._device, samplerate=self._rate,
                        channels=1, dtype='int16', blocksize=chunk) as stream:

                    # Calibración ambiental
                    muestras = [_rms(stream.read(chunk)[0].flatten())
                                for _ in range(CALENTAMIENTO)]
                    nivel_ruido = float(np.mean(muestras))
                    umbral = max(UMBRAL_MINIMO, nivel_ruido * FACTOR_RUIDO)
                    print(f"[Oído] Listo. rate={self._rate} Hz | "
                          f"Ruido:{nivel_ruido:.0f} | Umbral:{umbral:.0f}")

                    t_inicio = time.time()
                    while not self._detener:
                        if time.time() - t_inicio > T_REINICIO:
                            break
                        if self._err_consec >= MAX_ERR_CONSEC:
                            print("[Oído] Demasiados errores — reiniciando stream.")
                            break
                        try:
                            self._escuchar_frase(stream, umbral, chunk)
                        except OSError as exc:
                            self._log_err(f"Stream error: {exc}")
                            time.sleep(0.4)
                        except Exception as exc:
                            self._log_err(f"Loop error: {exc}")
                            time.sleep(0.5)

            except Exception as exc:
                self._log_err(f"No se pudo abrir micrófono: {exc}")
                if self._err_consec > 5:
                    self._device, self._rate = _detectar_dispositivo()
                wait = min(30, 2 ** min(self._err_consec, 4))
                time.sleep(wait)

            if not self._detener:
                time.sleep(1.0)

        self.escuchando = False

    # ─── Grabación y STT ─────────────────────────────────────────────────────

    def _escuchar_frase(self, stream, umbral: float, chunk: int):
        """Captura hasta detectar silencio y lanza STT en capas."""
        max_chunks  = int(MAX_SEGUNDOS * self._rate / chunk)
        chunks: list = []
        silencio    = 0
        tiene_voz   = False

        while len(chunks) < max_chunks:
            if self._detener:
                return
            data, _ = stream.read(chunk)
            plano   = data.flatten()
            nivel   = _rms(plano)

            if nivel >= umbral:
                tiene_voz = True
                silencio  = 0
                chunks.append(plano)
            elif tiene_voz:
                chunks.append(plano)
                silencio += 1
                if silencio >= CHUNKS_SILENCIO:
                    break

        if not tiene_voz or len(chunks) < 3:
            return

        audio_np = np.concatenate(chunks).astype(np.int16)
        self._set_grabando(True)

        try:
            texto = self._transcribir(audio_np)
            if texto and not self._detener:
                self._err_consec = max(0, self._err_consec - 1)
                print(f"[Oído] Reconocido: «{texto}»")
                self.callback(texto)
            elif not texto:
                pass  # silencio reconocido o sin respuesta — no es error
        finally:
            self._set_grabando(False)

    def _transcribir(self, audio_np: np.ndarray) -> str | None:
        """Multi-capa STT: Google(requests) → Google(sr) → Windows SAPI."""
        # Capa 1: Google Speech API via requests + WAV (más fiable en Windows 3.14)
        texto = _stt_google(audio_np, self._rate, self.idioma)
        if texto:
            return texto

        # Capa 2: speech_recognition + recognize_google (FLAC, urllib)
        if _SR_OK and not _REQ_OK:
            texto = _stt_sr_google(audio_np, self._rate, self.idioma)
            if texto:
                return texto

        # Capa 3: Windows SAPI offline (sin internet)
        texto = _stt_windows_sapi(audio_np, self._rate, self.idioma)
        return texto
