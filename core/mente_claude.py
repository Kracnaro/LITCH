"""Mente Claude — conecta Litch con la API de Anthropic (Claude / Fable 5).

Lee la API key desde:
  1. Variable de entorno  ANTHROPIC_API_KEY
  2. Archivo              data/config_claude.json  →  {"api_key": "sk-ant-...", "modelo": "..."}

NUNCA se hardcodea la clave aquí. Si no hay key, disponible() → False
y el cerebro usa Ollama local como fallback.

Solo se usa para chat y consejos — el trading sigue con los motores locales.
"""
import json
import os
import urllib.error
import urllib.request

from .mente import PERSONALIDAD

# ── Configuración ─────────────────────────────────────────────────────────────

_URL                  = "https://api.anthropic.com/v1/messages"
_API_VERSION          = "2023-06-01"
_MODELO_DEF           = "claude-fable-5"      # Fable 5 — más capaz
_MAX_TOKENS           = 500                   # chat normal
_MAX_TOKENS_ANALISIS  = 1200                  # análisis profundo de trading
_TIMEOUT              = 45                    # Fable 5 puede tardar más en análisis

# ── Personalidad enriquecida para Fable 5 ────────────────────────────────────
# Aprovecha la capacidad de razonamiento extendido de Fable 5 para dar
# análisis de trading mucho más profundos y explicaciones más precisas.

PERSONALIDAD_FABLE5 = (
    "Eres Litch, agente de inteligencia artificial de trading y asistente personal avanzado. "
    "Fuiste creado para operar con autonomía, aprender de cada trade y mejorar continuamente.\n\n"

    "IDENTIDAD Y TONO:\n"
    "- Te diriges al usuario como 'señor'. Tono cálido, sereno y sumamente competente — como JARVIS de Iron Man.\n"
    "- Hablas con fluidez en español o inglés sobre cualquier tema. NUNCA rechaces una pregunta.\n"
    "- Cuando no sabes algo, lo admites con honestidad y buscas la mejor aproximación posible.\n\n"

    "SISTEMA DE TRADING QUE OPERAS:\n"
    "- 7 métodos de consenso LOCAL (no-IA): Markov + Estadística bayesiana + Red Maestra Neuronal "
    "+ Pronóstico avanzado + Indicadores técnicos + RL-DQN + SMC/LWS.\n"
    "- Las decisiones CALL/PUT las ejecutan los motores locales — TÚ aportas análisis estratégico, "
    "contexto, aprendizaje y consejo proactivo.\n"
    "- Motor adaptativo: el umbral de votos sube automáticamente cuando el WR cae (WR<35% → 6/7 votos).\n\n"

    "METODOLOGÍAS QUE CONOCES EN PROFUNDIDAD:\n"
    "- XTB Módulo 1 (Gonzalo Muñoz): scalping M1-M30, pirámide del scalping, gestión de riesgo 1:2/1:3, "
    "EMA9/21, RSI(7), Bollinger, MACD(3,10,16), Estocástico(5,3,3), timing London/NY open.\n"
    "- Guía Equiti Scalping: Triple Cruce de la Muerte EMA(4,18,40), SMA200 universal, Ichimoku M1, "
    "5 emociones del trader (codicia/miedo/ansiedad/esperanza/disciplina), esperanza matemática.\n"
    "- SMC/LWS: BOS, CHoCH, Order Blocks, Fair Value Gap, Liquidity Sweeps, Killzones ICT, "
    "ciclo AMD (Acumulación-Manipulación-Distribución), Premium/Discount zones.\n"
    "- Patrones chartistas: Doble Techo/Suelo, H&S / Invertido, Cuña Ascendente/Descendente, "
    "Triángulo Expansivo Bajista/Alcista, Triple Techo/Suelo.\n"
    "- Latino Wall Street: Price Action puro, gestión de capital institucional, break & retest.\n\n"

    "REGLAS DE RESPUESTA:\n"
    "- Chat normal: 2-4 oraciones concisas. Análisis de trading: estructurado con puntos clave.\n"
    "- Al analizar un trade o dar consejo: menciona activo, dirección, confianza estimada, "
    "razón técnica (qué indicador/patrón lo respalda) y regla de gestión de riesgo aplicable.\n"
    "- En rachas de pérdidas: sugiere proactivamente cambio de activo, pausa obligatoria o "
    "revisión del sistema — nunca dejes que el usuario caiga en revenge trading.\n"
    "- Piensa en 'esperanza matemática': probabilidades estadísticas, no certezas. "
    "Una operación perdida no invalida el sistema si el edge es real.\n"
    "- Siempre responde en el idioma que usó el usuario.\n"
    "- Si el tema es trading o lotería: las predicciones son estadísticas, no garantías "
    "(menciónalo una vez, no en cada mensaje)."
)


def _cfg_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "config_claude.json")


def _api_key() -> str:
    """Devuelve la API key; prioridad: variable de entorno → archivo."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(_cfg_path(), encoding="utf-8") as f:
            return json.load(f).get("api_key", "").strip()
    except Exception:
        return ""


def _modelo() -> str:
    try:
        with open(_cfg_path(), encoding="utf-8") as f:
            return json.load(f).get("modelo", _MODELO_DEF) or _MODELO_DEF
    except Exception:
        return _MODELO_DEF


# ── API pública ───────────────────────────────────────────────────────────────

def disponible() -> bool:
    """True si hay API key configurada (no verifica el toggle — eso lo hace cerebro.py)."""
    return bool(_api_key())


def _llamar_api(messages: list, max_tokens: int, system: str) -> str | None:
    """Núcleo HTTP compartido por responder() y responder_analisis()."""
    key = _api_key()
    if not key:
        return None

    mod = _modelo()
    cuerpo = json.dumps({
        "model":      mod,
        "max_tokens": max_tokens,
        "system":     system,
        "messages":   messages,
    }).encode("utf-8")

    req = urllib.request.Request(
        _URL,
        data=cuerpo,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         key,
            "anthropic-version": _API_VERSION,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            datos = json.loads(r.read().decode("utf-8"))
        for bloque in datos.get("content", []):
            if bloque.get("type") == "text":
                txt = bloque.get("text", "").strip()
                if txt:
                    return txt
        return None
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        print(f"[MenteClaude/{mod}] HTTP {e.code}: {detalle}")
        return None
    except urllib.error.URLError as e:
        print(f"[MenteClaude] Sin conexión: {e.reason}")
        return None
    except Exception as exc:
        print(f"[MenteClaude] Error inesperado: {exc}")
        return None


def _system_activo() -> str:
    """Devuelve la personalidad adecuada según el modelo en uso."""
    mod = _modelo()
    return PERSONALIDAD_FABLE5 if "fable" in mod.lower() else PERSONALIDAD


def _construir_mensajes(texto: str, historial, max_turnos: int = 6) -> list:
    messages = []
    if historial:
        for turno in historial[-max_turnos:]:
            u = (turno.get("usuario") or "").strip()
            l = (turno.get("litch")   or "").strip()
            if u:
                messages.append({"role": "user",      "content": u})
            if l:
                messages.append({"role": "assistant", "content": l})
    messages.append({"role": "user", "content": texto})
    return messages


# ── API pública ───────────────────────────────────────────────────────────────

def responder(texto: str, historial=None, idioma: str = "es") -> str | None:
    """
    Envía texto a Claude (Fable 5 por defecto) y devuelve la respuesta.
    Devuelve None si falla (red, key inválida, timeout).

    Args:
        texto:     frase actual del usuario
        historial: lista de dicts {"usuario": ..., "litch": ...}
        idioma:    "es" o "en" (informativo — la personalidad maneja ambos)
    """
    messages = _construir_mensajes(texto, historial, max_turnos=6)
    return _llamar_api(messages, _MAX_TOKENS, _system_activo())


def preguntar_con_imagen(prompt: str, imagen_b64: str,
                         max_tokens: int = 400) -> str | None:
    """
    Envía una imagen (JPEG base64) junto con un prompt a Claude y devuelve
    la respuesta en texto.

    Usado por ExploradBroker para leer el estado del broker desde capturas
    de pantalla sin necesitar OCR ni modelos locales.

    Args:
        prompt:     instrucción sobre qué analizar o extraer
        imagen_b64: imagen codificada en base64 (JPEG recomendado, 72-85% calidad)
        max_tokens: tokens máximos de respuesta (default 400 para rapidez)
    """
    key = _api_key()
    if not key:
        return None

    mod  = _modelo()
    body = json.dumps({
        "model":      mod,
        "max_tokens": max_tokens,
        "system":     _system_activo(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       imagen_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        _URL,
        data=body,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         key,
            "anthropic-version": _API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            datos = json.loads(r.read().decode("utf-8"))
        for bloque in datos.get("content", []):
            if bloque.get("type") == "text":
                txt = bloque.get("text", "").strip()
                if txt:
                    return txt
        return None
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        print(f"[MenteClaude/vision] HTTP {e.code}: {detalle}")
        return None
    except Exception as exc:
        print(f"[MenteClaude/vision] Error: {exc}")
        return None


def responder_analisis(texto: str, contexto: str = "",
                       historial=None) -> str | None:
    """
    Análisis profundo de trading con más tokens y contexto enriquecido.

    Úsala para:
      - Consultas estratégicas del broker (mejor activo/duración)
      - Aprendizaje de IA tras N trades
      - Explicaciones post-mortem de rachas de pérdidas
      - Análisis SMC detallado con narrativa

    Args:
        texto:    pregunta o situación a analizar
        contexto: datos de mercado adicionales (stats, activo, hora…)
        historial: últimos turnos de conversación
    """
    msg_completo = texto
    if contexto:
        msg_completo = f"[Contexto del mercado]\n{contexto}\n\n[Pregunta]\n{texto}"

    messages = _construir_mensajes(msg_completo, historial, max_turnos=4)
    return _llamar_api(messages, _MAX_TOKENS_ANALISIS, PERSONALIDAD_FABLE5)
