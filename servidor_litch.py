"""
servidor_litch.py — Litch expuesto como API local, para hablarle desde Obsidian.

QUÉ ES
──────
Un servidor HTTP en su equipo que imita el formato de OpenAI. Los plugins de
Obsidian (Copilot, BMO, Smart Connections…) saben hablar ese formato, así que
se conectan sin escribir un plugin desde cero.

Resultado: en la barra lateral de Obsidian usted escribe una pregunta y
**responde Litch**, con su memoria, su bóveda y su conocimiento de IBKR.

    http://127.0.0.1:5000/v1

QUÉ SE CORRIGIÓ DEL CÓDIGO QUE LE PASARON
─────────────────────────────────────────
El enfoque era correcto. La implementación tenía siete problemas:

  1. `Flask(_name_)` — deben ser DOBLES guiones bajos: `__name__`. Falla en
     la primera línea. Es un error de copiado clásico.
  2. **Faltaba `/v1/models`.** Casi todos los clientes lo piden ANTES de
     chatear, para listar modelos. Sin él, el plugin ni se conecta.
  3. **Sin streaming.** Muchos plugins mandan `"stream": true` y esperan
     eventos SSE. Si reciben un JSON normal, se quedan colgados.
  4. **Respuesta incompleta.** Faltaban `id`, `object`, `created`, `model`,
     `finish_reason` y `usage`. Hay clientes estrictos que los exigen.
  5. **Sin manejo de errores.** Una excepción devolvía una página HTML de
     error y el plugin no sabía qué hacer.
  6. **Un solo hilo.** `app.run()` sin `threaded=True` bloquea con dos
     peticiones a la vez.
  7. **Sin Flask no arranca.** Aquí se usa la librería estándar de Python:
     una dependencia menos que instalar y que se rompa.

SEGURIDAD
─────────
Escucha SOLO en 127.0.0.1. No es accesible desde fuera de su equipo, ni
desde su red. Y no ejecuta operaciones: responde preguntas. Para operar
sigue haciendo falta la interfaz de Litch.

USO
    python servidor_litch.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

HOST = "127.0.0.1"      # solo local. NO cambiar a 0.0.0.0 sin pensarlo.
PUERTO = 5000
MODELO = "litch-trading"


# ═══════════════════════════════════════════════════════════════════════════
#  El cerebro: cómo responde Litch
# ═══════════════════════════════════════════════════════════════════════════

class CerebroLitch:
    """Enruta cada pregunta a la parte de Litch que sabe responderla."""

    def __init__(self):
        self.app = self._app_minima()
        self._listo = False
        self._error = ""
        self._preparar()

    @staticmethod
    def _app_minima():
        """Un 'app' suficiente para que los módulos de Litch funcionen
        sin necesidad de arrancar toda la interfaz gráfica."""
        class AppMinima:
            def __init__(self):
                self.mem = {"config": {}}
                self.broker_ibkr = None
                self.tv_feed = None
                self.autoclick_on = False
                self.modo_autonomo = False
                try:
                    from core import memoria
                    self.mem = memoria.cargar()
                except Exception:
                    pass

            def log(self, t):
                print(f"[Litch] {t}")

            def decir(self, t):
                pass      # el servidor no habla en voz alta
        return AppMinima()

    def _preparar(self):
        try:
            from core import consulta_boveda      # noqa: F401
            self._listo = True
        except Exception as e:
            self._error = str(e)

    # ── El enrutado ─────────────────────────────────────────────────────────

    def responder(self, pregunta: str) -> str:
        """Decide qué parte de Litch responde y devuelve su respuesta."""
        p = (pregunta or "").strip()
        if not p:
            return "No he recibido ninguna pregunta, señor."

        pl = p.lower()

        # 1. Preguntas sobre el código: el mapa
        if any(k in pl for k in ("código", "codigo", "módulo", "modulo",
                                 "arquitectura", "dónde está la función",
                                 "donde esta la funcion")):
            r = self._buscar_boveda(p, carpeta="Codigo")
            if r:
                return r

        # 2. Resultados y operaciones
        if any(k in pl for k in ("cómo van", "como van", "resultado",
                                 "rendimiento", "cuánto llevo",
                                 "cuanto llevo", "operaciones")):
            try:
                from core import vigilante_posiciones as vp
                return vp.resumen(self.app)
            except Exception:
                pass

        # 3. Herramientas de IBKR: la escuela
        try:
            from core import escuela_ibkr as ei
            clave = ei._buscar(p)
            if clave:
                return ei.explicar(clave)
        except Exception:
            pass

        # 4. Lo demás: la bóveda entera
        r = self._buscar_boveda(p)
        if r:
            return r

        return (
            f"No encuentro nada sobre «{p}» en mi memoria, señor.\n\n"
            f"Puedo responderle sobre:\n"
            f"  · herramientas de Interactive Brokers\n"
            f"  · sus operaciones y resultados\n"
            f"  · setups y qué tal han ido\n"
            f"  · el código de mi propio sistema\n\n"
            f"Y si no lo sé, se lo digo. Prefiero eso a inventármelo."
        )

    def _buscar_boveda(self, p: str, carpeta: str = "") -> str:
        try:
            from core import consulta_boveda as cb
            res = cb.buscar(p, limite=4)
            if carpeta:
                res = [r for r in res if r["carpeta"] == carpeta] or res
            if not res:
                return ""
            return cb.responder(self.app, p)
        except Exception:
            return ""


_cerebro: CerebroLitch | None = None


def cerebro() -> CerebroLitch:
    global _cerebro
    if _cerebro is None:
        _cerebro = CerebroLitch()
    return _cerebro


# ═══════════════════════════════════════════════════════════════════════════
#  El servidor HTTP
# ═══════════════════════════════════════════════════════════════════════════

class Manejador(BaseHTTPRequestHandler):

    # Silenciar el log por defecto (una línea por petición es demasiado)
    def log_message(self, formato, *args):
        pass

    # ── Cabeceras ───────────────────────────────────────────────────────────

    def _cors(self):
        """Sin esto, Obsidian bloquea la conexión por seguridad del navegador."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization")

    def _json(self, datos, codigo: int = 200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self._cors()
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ── GET ─────────────────────────────────────────────────────────────────

    def do_GET(self):
        ruta = self.path.split("?")[0].rstrip("/")

        # /v1/models — LO QUE FALTABA en el código original.
        # Casi todos los clientes lo piden antes de nada para listar
        # modelos. Sin esto, el plugin ni llega a intentar chatear.
        if ruta in ("/v1/models", "/models"):
            return self._json({
                "object": "list",
                "data": [{
                    "id": MODELO,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "litch-local",
                }],
            })

        if ruta in ("", "/", "/salud", "/health"):
            c = cerebro()
            return self._json({
                "estado": "en marcha",
                "modelo": MODELO,
                "boveda_lista": c._listo,
                "error": c._error,
                "endpoints": ["/v1/models", "/v1/chat/completions"],
            })

        return self._json({"error": {"message": f"Ruta no encontrada: {ruta}",
                                     "type": "not_found"}}, 404)

    # ── POST ────────────────────────────────────────────────────────────────

    def do_POST(self):
        ruta = self.path.split("?")[0].rstrip("/")
        if ruta not in ("/v1/chat/completions", "/chat/completions",
                        "/v1/completions"):
            return self._json({"error": {"message": "Ruta no encontrada",
                                         "type": "not_found"}}, 404)

        # Leer el cuerpo con tolerancia a errores. Una excepción aquí
        # devolvía HTML y rompía el plugin sin explicar nada.
        try:
            largo = int(self.headers.get("Content-Length", 0) or 0)
            crudo = self.rfile.read(largo) if largo else b"{}"
            datos = json.loads(crudo.decode("utf-8") or "{}")
        except Exception as e:
            return self._json({"error": {
                "message": f"No pude leer la petición: {e}",
                "type": "invalid_request_error"}}, 400)

        # Sacar el último mensaje del usuario
        try:
            mensajes = datos.get("messages") or []
            pregunta = ""
            for m in reversed(mensajes):
                if m.get("role") == "user":
                    c = m.get("content", "")
                    # El contenido puede venir como texto o como lista
                    if isinstance(c, list):
                        c = " ".join(t.get("text", "") for t in c
                                     if isinstance(t, dict))
                    pregunta = str(c)
                    break
            if not pregunta and mensajes:
                pregunta = str(mensajes[-1].get("content", ""))
        except Exception:
            pregunta = ""

        # Responder, capturando cualquier fallo del cerebro
        try:
            respuesta = cerebro().responder(pregunta)
        except Exception as e:
            respuesta = (f"Algo falló al responder, señor: {e}\n\n"
                         f"{traceback.format_exc()[-400:]}")

        # ¿Quiere el cliente streaming?
        if datos.get("stream"):
            return self._responder_stream(respuesta)

        ahora = int(time.time())
        return self._json({
            "id": f"chatcmpl-litch-{ahora}",
            "object": "chat.completion",
            "created": ahora,
            "model": datos.get("model") or MODELO,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": respuesta},
                "finish_reason": "stop",
            }],
            # Aproximado, pero algunos clientes lo exigen presente
            "usage": {
                "prompt_tokens": len(pregunta) // 4,
                "completion_tokens": len(respuesta) // 4,
                "total_tokens": (len(pregunta) + len(respuesta)) // 4,
            },
        })

    def _responder_stream(self, respuesta: str):
        """Streaming SSE — LO OTRO QUE FALTABA.

        Muchos plugins de Obsidian mandan `"stream": true` y se quedan
        esperando eventos. Si les llega un JSON de golpe, se cuelgan sin
        decir por qué.
        """
        ahora = int(time.time())
        cid = f"chatcmpl-litch-{ahora}"
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            # `Connection: close`, NO keep-alive.
            #
            # Con keep-alive la conexión queda abierta después del [DONE] y
            # el cliente se queda esperando más datos que nunca llegan. Lo
            # detecté probándolo: el cliente daba timeout. Habría colgado
            # el plugin de Obsidian exactamente igual que el código
            # original — solo que por otro motivo.
            self.send_header("Connection", "close")
            self._cors()
            self.end_headers()

            def envia(delta=None, fin=False):
                trozo = {
                    "id": cid, "object": "chat.completion.chunk",
                    "created": ahora, "model": MODELO,
                    "choices": [{
                        "index": 0,
                        "delta": ({} if fin else delta),
                        "finish_reason": ("stop" if fin else None),
                    }],
                }
                self.wfile.write(
                    f"data: {json.dumps(trozo, ensure_ascii=False)}\n\n"
                    .encode("utf-8"))
                self.wfile.flush()

            envia({"role": "assistant"})
            # En trozos, para que se vea escribir como en un chat normal
            paso = 40
            for i in range(0, len(respuesta), paso):
                envia({"content": respuesta[i:i + paso]})
                time.sleep(0.012)
            envia(fin=True)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            # Cerrar de verdad: es lo que le dice al cliente «ya está».
            self.close_connection = True
        except Exception:
            pass      # el cliente cerró la conexión: normal


# ═══════════════════════════════════════════════════════════════════════════
#  Arranque
# ═══════════════════════════════════════════════════════════════════════════

_servidor = None
_hilo = None


def arrancar(puerto: int = PUERTO, en_hilo: bool = True) -> str:
    """Levanta el servidor. Devuelve un mensaje para el usuario."""
    global _servidor, _hilo
    if _servidor is not None:
        return f"El servidor ya estaba en marcha en http://{HOST}:{puerto}/v1"
    try:
        # ThreadingHTTPServer: atiende varias peticiones a la vez.
        # El app.run() del ejemplo original era de un solo hilo y se
        # bloqueaba con dos consultas simultáneas.
        _servidor = ThreadingHTTPServer((HOST, puerto), Manejador)
    except OSError as e:
        return (f"No pude abrir el puerto {puerto}: {e}\n"
                f"Puede que ya haya algo escuchando ahí.")

    if en_hilo:
        _hilo = threading.Thread(target=_servidor.serve_forever, daemon=True,
                                 name="ServidorLitch")
        _hilo.start()
    return f"Servidor de Litch en marcha: http://{HOST}:{puerto}/v1"


def parar() -> str:
    global _servidor
    if _servidor is None:
        return "El servidor no estaba en marcha."
    try:
        _servidor.shutdown()
        _servidor.server_close()
    except Exception:
        pass
    _servidor = None
    return "Servidor detenido."


if __name__ == "__main__":
    print()
    print("=" * 64)
    print("  SERVIDOR DE LITCH — para conectar Obsidian")
    print("=" * 64)
    print()

    c = cerebro()
    if not c._listo:
        print(f"  Aviso: la bóveda no está lista ({c._error})")
        print("  El servidor arranca igual, pero responderá poco.")
        print()

    print(arrancar(en_hilo=False))
    print()
    print("  CONFIGURACIÓN EN OBSIDIAN")
    print("  ─────────────────────────")
    print("  1. Instale el plugin «Copilot» (Ajustes → Plugins de la")
    print("     comunidad → Buscar «Copilot»)")
    print("  2. En sus ajustes, añada un modelo personalizado:")
    print(f"       Base URL : http://{HOST}:{PUERTO}/v1")
    print(f"       Modelo   : {MODELO}")
    print("       API key  : cualquier cosa (no se comprueba)")
    print("       Proveedor: OpenAI compatible / Custom")
    print()
    print("  Después pregúntele desde la barra lateral de Obsidian.")
    print("  Responde Litch con SU memoria, no con teoría de internet.")
    print()
    print("  Ctrl+C para detenerlo.")
    print()

    try:
        _servidor.serve_forever()
    except KeyboardInterrupt:
        print()
        print("  " + parar())
        print()
