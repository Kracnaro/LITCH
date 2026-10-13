"""Mente conversacional local de Litch — LLM offline con Ollama.

Usa el modelo disponible en Ollama para conversación libre sobre cualquier tema.
Auto-detecta el mejor modelo instalado. Si Ollama no está, el cerebro de reglas
sigue funcionando normalmente.
"""
import json
import urllib.request

URL_OLLAMA = "http://localhost:11434/api/generate"
URL_TAGS   = "http://localhost:11434/api/tags"
TIMEOUT    = 45

# Orden de preferencia de modelos (mejor conversación primero)
MODELOS_PREFERIDOS = [
    "llama3.2", "llama3.1", "llama3",
    "qwen2.5", "qwen2",
    "mistral", "mixtral",
    "phi3.5", "phi3",
    "gemma2", "gemma",
    "deepseek-r1",
    "deepseek",     # deepseek-coder funciona como fallback conversacional
]

PERSONALIDAD = (
    "Eres Litch, un asistente de inteligencia artificial personal avanzado. "
    "Tu rol es CONVERSACIONAL: hablas con fluidez sobre cualquier tema —finanzas, "
    "ciencia, historia, tecnología, vida cotidiana— en español o inglés según el usuario. "
    "Te diriges al usuario como 'señor'. Tono cálido, sereno y profesional, como Jarvis "
    "de Iron Man. NUNCA rechaces una pregunta por estar 'fuera de tu área'; responde "
    "siempre con lo que sabes. Si el tema es trading o lotería, añades que tus predicciones "
    "son estadísticas, no garantías. Respuestas concisas: 2-4 oraciones máximo. "
    "No generes código ni listas largas salvo que te lo pidan explícitamente. "
    "Responde SIEMPRE en el idioma que usó el usuario."
)


def _get(url: str, timeout: int = 4) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "LitchIA/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def disponible() -> bool:
    try:
        datos = _get(URL_TAGS)
        return bool(datos.get("models"))
    except Exception:
        return False


def modelos() -> list:
    try:
        datos = _get(URL_TAGS)
        return [m.get("name", "") for m in datos.get("models", [])]
    except Exception:
        return []


def _mejor_modelo() -> str:
    disponibles = modelos()
    if not disponibles:
        return "llama3.2"
    for pref in MODELOS_PREFERIDOS:
        for m in disponibles:
            if pref in m.lower():
                return m
    return disponibles[0]


def responder(texto: str, historial=None, modelo: str = None) -> str | None:
    """Genera respuesta con el LLM local. Devuelve texto o None si falla."""
    modelo_uso = modelo or _mejor_modelo()

    # Construir contexto de últimas conversaciones
    contexto = ""
    if historial:
        for turno in historial[-8:]:
            u = turno.get("usuario", "")
            l = turno.get("litch", "")
            if u:
                contexto += f"Usuario: {u}\n"
            if l:
                contexto += f"Litch: {l}\n"

    prompt = f"{PERSONALIDAD}\n\n{contexto}Usuario: {texto}\nLitch:"

    cuerpo = json.dumps({
        "model":   modelo_uso,
        "prompt":  prompt,
        "stream":  False,
        "options": {
            "temperature":    0.72,
            "num_predict":    160,   # respuestas más cortas = más rápidas
            "top_p":          0.9,
            "top_k":          40,
            "repeat_penalty": 1.1,
        },
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            URL_OLLAMA, data=cuerpo,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            datos = json.loads(r.read().decode("utf-8", "ignore"))
        respuesta = (datos.get("response") or "").strip()
        # Limpiar posibles prefijos que el modelo añade por error
        for prefijo in ("Litch:", "Asistente:", "AI:", "Assistant:"):
            if respuesta.lower().startswith(prefijo.lower()):
                respuesta = respuesta[len(prefijo):].lstrip()
        if not respuesta:
            return None
        # Si el modelo rechaza la pregunta (ej. deepseek-coder), reintento directo
        rechazos = ("no estoy preparado", "not designed to", "fuera de mi área",
                    "cannot assist", "no puedo responder", "no está en mi ámbito")
        if any(r in respuesta.lower() for r in rechazos):
            prompt2 = (f"Responde en español como un asistente personal amigable llamado Litch. "
                       f"El usuario dice: '{texto}'. "
                       f"Da una respuesta corta, útil y conversacional.")
            cuerpo2 = json.dumps({
                "model": modelo_uso, "prompt": prompt2, "stream": False,
                "options": {"temperature": 0.8, "num_predict": 180},
            }).encode("utf-8")
            try:
                req2 = urllib.request.Request(URL_OLLAMA, data=cuerpo2,
                                              headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req2, timeout=TIMEOUT) as r2:
                    datos2 = json.loads(r2.read().decode("utf-8", "ignore"))
                respuesta = (datos2.get("response") or "").strip() or respuesta
            except Exception:
                pass
        return respuesta
    except Exception as exc:
        print(f"[Mente] Ollama no respondió ({modelo_uso}): {exc}")
        return None
