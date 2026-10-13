"""
vision_cam.py — Visión por cámara de Litch.

Capacidades:
  1. Reconocimiento facial del usuario (enrollment una sola vez con foto guardada)
  2. Saludo personalizado cuando detecta la cara registrada
  3. Detección de presencia para activar/desactivar modos automáticamente
  4. Vista de cámara en vivo en la UI (opcional)

Requiere: opencv-python (cv2)  — se instala con: pip install opencv-python
          numpy (ya instalado)

Si cv2 no está disponible, el módulo se carga en modo "sin cámara" y no hace nada.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path

import numpy as np

# ── Importación opcional de OpenCV ────────────────────────────────────────────
try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

RUTA_BASE     = Path("MEMORIA_AP")
RUTA_PERFIL   = RUTA_BASE / "cam_perfil.json"
RUTA_FOTO     = RUTA_BASE / "cam_cara_ref.npy"

# Cascade Haar para detección de rostros (incluido en cv2)
_HAARCASCADE  = "haarcascade_frontalface_default.xml"


# ─────────────────────────────────────────────────────────────────────────────

def disponible() -> bool:
    """True si cv2 está instalado."""
    return _CV2_OK


# ─────────────────────────────────────────────────────────────────────────────

class VisionCam:
    """
    Sistema de visión por cámara de Litch.

    Flujo:
      1. La primera vez: llama a enrollar(nombre) — toma una foto y la guarda.
      2. En run(): detecta caras en cada frame y las compara con la referencia.
      3. Cuando reconoce al usuario llama a app.decir() con el saludo.
      4. Proporciona frames JPEG (bytes) para mostrar en la UI vía get_frame().
    """

    SIMILARIDAD_UMBRAL = 0.72    # 0→1; más alto = más estricto
    COOLDOWN_SALUDO    = 120     # segundos entre saludos (evita repetir)
    ESCALA_DETECT      = 0.5     # escalar el frame para detección (más rápido)

    def __init__(self, app):
        self.app           = app
        self._activo       = False
        self._hilo: threading.Thread | None = None
        self._lock         = threading.Lock()
        self._frame_jpg: bytes | None = None   # último frame JPEG para UI
        self._perfil: dict = {}
        self._cara_ref: np.ndarray | None = None   # embedding de referencia
        self._t_ultimo_saludo = 0.0
        self._en_camara    = False    # True cuando el usuario está en cámara

        RUTA_BASE.mkdir(parents=True, exist_ok=True)
        self._cargar_perfil()

        if _CV2_OK:
            cascade_path = cv2.data.haarcascades + _HAARCASCADE
            self._cascade = cv2.CascadeClassifier(cascade_path)
        else:
            self._cascade = None

    # ── API pública ──────────────────────────────────────────────────────────

    def iniciar(self) -> bool:
        """Inicia el hilo de captura. Devuelve False si cv2 no está disponible."""
        if not _CV2_OK:
            self.app.log("[Cámara] cv2 no instalado. Ejecuta: pip install opencv-python")
            return False
        if self._activo:
            return True
        self._activo = True
        self._hilo = threading.Thread(target=self._loop, daemon=True, name="LitchCam")
        self._hilo.start()
        self.app.log("[Cámara] Iniciada.")
        return True

    def detener(self) -> None:
        self._activo = False

    def esta_activa(self) -> bool:
        return self._activo

    def get_frame(self) -> bytes | None:
        """Devuelve el último frame JPEG (bytes) para mostrar en tkinter."""
        with self._lock:
            return self._frame_jpg

    def usuario_presente(self) -> bool:
        """True si el usuario registrado está en cámara ahora mismo."""
        return self._en_camara

    def tiene_perfil(self) -> bool:
        return bool(self._perfil.get("nombre")) and self._cara_ref is not None

    def nombre_usuario(self) -> str:
        return self._perfil.get("nombre", "")

    # ── Enrolamiento ─────────────────────────────────────────────────────────

    def enrollar(self, nombre: str, n_fotos: int = 5,
                 callback=None) -> tuple[bool, str]:
        """
        Captura N fotos del usuario y promedia los embeddings para crear la
        referencia. callback(msg) se llama con mensajes de progreso.

        Devuelve (éxito: bool, mensaje: str).
        """
        if not _CV2_OK:
            return False, "cv2 no instalado. Ejecuta: pip install opencv-python"

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return False, "No se pudo abrir la cámara."

        if callback:
            callback("Sonriendo — quedándose quieto…")

        embeddings: list[np.ndarray] = []
        intentos = 0
        max_intentos = n_fotos * 30   # máximo 30 frames por foto

        while len(embeddings) < n_fotos and intentos < max_intentos:
            ret, frame = cap.read()
            if not ret:
                intentos += 1
                time.sleep(0.05)
                continue

            gris  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            caras = self._cascade.detectMultiScale(
                gris, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))

            if len(caras) == 1:
                x, y, w, h = caras[0]
                recorte = gris[y:y+h, x:x+w]
                emb = self._embedding(recorte)
                embeddings.append(emb)
                if callback:
                    callback(f"Foto {len(embeddings)}/{n_fotos} capturada…")
                time.sleep(0.3)
            intentos += 1
            time.sleep(0.05)

        cap.release()

        if not embeddings:
            return False, "No se detectó ninguna cara. Asegúrate de estar frente a la cámara."

        cara_ref = np.mean(embeddings, axis=0)
        np.save(str(RUTA_FOTO), cara_ref)

        self._cara_ref = cara_ref
        self._perfil   = {"nombre": nombre, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self._guardar_perfil()

        return True, f"Perfil de {nombre} guardado con {len(embeddings)} fotos."

    # ── Loop de captura ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.app.log("[Cámara] No se pudo abrir la cámara 0.")
            self._activo = False
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        while self._activo:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            # Codificar frame a JPEG para la UI (resolución completa)
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            with self._lock:
                self._frame_jpg = bytes(buf)

            # Detección y reconocimiento (frame reducido para velocidad)
            self._procesar_frame(frame)

            time.sleep(0.08)   # ~12 fps de procesamiento

        cap.release()
        self.app.log("[Cámara] Detenida.")

    def _procesar_frame(self, frame: np.ndarray) -> None:
        """Detecta caras y compara con el perfil registrado."""
        if self._cara_ref is None:
            return

        pequeño = cv2.resize(frame, (0, 0), fx=self.ESCALA_DETECT,
                              fy=self.ESCALA_DETECT)
        gris    = cv2.cvtColor(pequeño, cv2.COLOR_BGR2GRAY)
        caras   = self._cascade.detectMultiScale(
            gris, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))

        reconocido = False
        for (x, y, w, h) in caras:
            # Escalar coordenadas al frame original
            x2, y2, w2, h2 = (int(v / self.ESCALA_DETECT) for v in (x, y, w, h))
            gris_full = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            recorte   = gris_full[y2:y2+h2, x2:x2+w2]
            emb       = self._embedding(recorte)
            sim       = self._similitud_coseno(emb, self._cara_ref)

            if sim >= self.SIMILARIDAD_UMBRAL:
                reconocido = True
                break

        if reconocido and not self._en_camara:
            self._en_camara = True
            self._on_usuario_detectado()
        elif not reconocido:
            self._en_camara = False

    def _on_usuario_detectado(self) -> None:
        """Llamada cuando se detecta al usuario registrado por primera vez."""
        ahora = time.time()
        if ahora - self._t_ultimo_saludo < self.COOLDOWN_SALUDO:
            return
        self._t_ultimo_saludo = ahora

        nombre = self._perfil.get("nombre", "jefe")
        hora   = int(time.strftime("%H"))
        if   hora < 12: momento = "buenos días"
        elif hora < 19: momento = "buenas tardes"
        else:           momento = "buenas noches"

        app = self.app
        msg = app.txt(
            f"{momento.capitalize()}, {nombre}. Le detecto frente a la pantalla, señor.",
            f"Good {'morning' if hora < 12 else 'afternoon' if hora < 19 else 'evening'}, "
            f"{nombre}. I see you in front of the screen, sir.")
        app.log(f"[Cámara] Usuario reconocido: {nombre} (sim={self.SIMILARIDAD_UMBRAL:.2f}+)")

        # Saludo en el hilo de UI
        try:
            app.interfaz.root.after(0, lambda: app.decir(msg))
        except Exception:
            threading.Thread(target=lambda: app.decir(msg), daemon=True).start()

    # ── Embedding simple (LBP Histogram) ──────────────────────────────────────

    @staticmethod
    def _embedding(cara_gris: np.ndarray, size: tuple = (64, 64)) -> np.ndarray:
        """
        Crea un descriptor de la cara usando LBP (Local Binary Patterns).
        LBP es robusto a cambios de iluminación y funciona sin modelos DL.
        """
        if cara_gris.size == 0:
            return np.zeros(256, dtype=np.float32)
        cara = cv2.resize(cara_gris, size)
        cara = cv2.equalizeHist(cara)    # normalizar iluminación

        # LBP manual (8 vecinos, radio 1)
        h, w    = cara.shape
        lbp     = np.zeros((h - 2, w - 2), dtype=np.uint8)
        offsets = [(-1,-1),(-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1)]
        centro  = cara[1:-1, 1:-1]
        for bit, (dy, dx) in enumerate(offsets):
            lbp |= (cara[1+dy:h-1+dy, 1+dx:w-1+dx] >= centro).astype(np.uint8) << bit

        # Histograma LBP normalizado como embedding
        hist, _ = np.histogram(lbp.flatten(), bins=256, range=(0, 256))
        hist    = hist.astype(np.float32)
        norma   = np.linalg.norm(hist) + 1e-9
        return hist / norma

    @staticmethod
    def _similitud_coseno(a: np.ndarray, b: np.ndarray) -> float:
        na = np.linalg.norm(a) + 1e-9
        nb = np.linalg.norm(b) + 1e-9
        return float(np.dot(a, b) / (na * nb))

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _guardar_perfil(self) -> None:
        try:
            RUTA_PERFIL.write_text(
                json.dumps(self._perfil, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _cargar_perfil(self) -> None:
        try:
            if RUTA_PERFIL.exists():
                self._perfil = json.loads(RUTA_PERFIL.read_text(encoding="utf-8"))
            if RUTA_FOTO.exists():
                self._cara_ref = np.load(str(RUTA_FOTO))
        except Exception:
            self._perfil   = {}
            self._cara_ref = None


# ── Singleton ─────────────────────────────────────────────────────────────────

_instancia: VisionCam | None = None


def obtener(app=None) -> VisionCam | None:
    """Devuelve la instancia singleton de VisionCam."""
    global _instancia
    if _instancia is not None:
        return _instancia
    if app is None:
        return None
    _instancia = VisionCam(app)
    return _instancia
