"""
knowledge_feeder.py — Alimentador de conocimiento de trading para LITCH.

LITCH aprende de fuentes reales de internet:
  - Conceptos de análisis técnico
  - Noticias económicas relevantes
  - Indicadores macro (tasas de interés, índices)
  - Patrones y estrategias de trading documentadas
  - Calendarios económicos (eventos que mueven el mercado)

Fuentes gratuitas utilizadas:
  - RSS de noticias financieras (Yahoo Finance, Reuters)
  - Wikipedia API (conceptos de trading)
  - ExchangeRate API (tasas actuales)
  - Open Meteo (no, eso es clima — esto es trading)

Todo el conocimiento se almacena en memoria_ap/conocimiento_trading_web.json
y LITCH lo consulta para enriquecer sus respuestas y análisis.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

try:
    import requests as _req
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

_BASE = os.path.join(
    os.path.dirname(__file__), "..", "memoria_ap")
_CONOCIMIENTO_FILE = os.path.join(_BASE, "conocimiento_trading_web.json")
_NOTICIAS_FILE     = os.path.join(_BASE, "noticias_economicas.json")
_CALENDAR_FILE     = os.path.join(_BASE, "calendario_economico.json")

# Intervalo de actualización (4 horas)
_UPDATE_INTERVAL = 4 * 3600


class KnowledgeFeeder:
    """
    Alimentador periódico de conocimiento de trading para LITCH.

    Descarga y almacena:
    1. Conceptos de análisis técnico (Wikipedia)
    2. Noticias económicas recientes (RSS)
    3. Tasas de cambio actuales
    4. Sentimiento del mercado global
    5. Calendario de eventos económicos

    LITCH consulta esta base para responder preguntas sobre el mercado
    y enriquecer su análisis con contexto macroeconómico.
    """

    def __init__(self, app=None):
        self._app         = app
        self._lock        = threading.Lock()
        self._conocimiento = self._cargar_conocimiento()
        self._noticias    = self._cargar_noticias()
        self._ultimo_update = float(self._conocimiento.get("_timestamp", 0))
        self._hilo        = None

    # ── API principal ─────────────────────────────────────────────────────────

    def iniciar(self) -> None:
        """Inicia la actualización periódica en background."""
        if not _REQ_OK:
            return
        self._hilo = threading.Thread(
            target=self._loop_actualizacion,
            daemon=True,
            name="KnowledgeFeeder",
        )
        self._hilo.start()
        self._log("[KnowledgeFeed] Iniciado — actualizando cada 4 horas")

    def actualizar_ahora(self) -> dict:
        """Actualiza inmediatamente y retorna resumen."""
        resultados = {}
        try:
            resultados["conceptos"]  = self._actualizar_conceptos()
            resultados["noticias"]   = self._actualizar_noticias()
            resultados["tasas"]      = self._actualizar_tasas()
            resultados["calendario"] = self._actualizar_calendario()
            with self._lock:
                self._conocimiento["_timestamp"] = time.time()
                self._ultimo_update = time.time()
            self._guardar_conocimiento()
            self._log(f"[KnowledgeFeed] Actualización completa: {resultados}")
        except Exception as e:
            self._log(f"[KnowledgeFeed] Error: {e}")
        return resultados

    def buscar(self, consulta: str) -> str:
        """
        Busca en el conocimiento almacenado.
        Retorna el texto más relevante encontrado.
        """
        consulta = consulta.lower()
        resultados = []

        with self._lock:
            # Buscar en conceptos
            for termino, datos in self._conocimiento.get("conceptos", {}).items():
                if any(p in termino.lower() or p in str(datos).lower()
                       for p in consulta.split()):
                    texto = str(datos)[:300]
                    resultados.append(("concepto", termino, texto))

            # Buscar en noticias
            for noticia in self._noticias.get("items", [])[:20]:
                titulo = noticia.get("titulo", "").lower()
                if any(p in titulo for p in consulta.split()):
                    resultados.append(("noticia", noticia.get("titulo", ""),
                                       noticia.get("resumen", "")[:200]))

        if not resultados:
            return ""

        # Retornar el más relevante
        mejor = resultados[0]
        return f"[{mejor[0].upper()}] {mejor[1]}: {mejor[2]}"

    def noticias_recientes(self, n: int = 5) -> list:
        """Retorna las N noticias más recientes."""
        with self._lock:
            return self._noticias.get("items", [])[:n]

    def tasas_actuales(self) -> dict:
        """Tasas de cambio actuales."""
        with self._lock:
            return self._conocimiento.get("tasas", {})

    def contexto_macro(self) -> str:
        """
        Texto de contexto macroeconómico para el análisis de LITCH.
        Incluye noticias relevantes y tasas actuales.
        """
        lineas = []
        tasas = self.tasas_actuales()
        if tasas:
            eur_usd = tasas.get("EUR", {})
            if eur_usd:
                lineas.append(f"EUR/USD: {eur_usd}")

        noticias = self.noticias_recientes(3)
        for n in noticias:
            lineas.append(f"📰 {n.get('titulo', '')[:80]}")

        if not lineas:
            return ""
        return "[Macro] " + " | ".join(lineas)

    # ── Actualizaciones periódicas ────────────────────────────────────────────

    def _loop_actualizacion(self) -> None:
        """Loop en background que actualiza el conocimiento cada 4 horas."""
        while True:
            try:
                ahora = time.time()
                if ahora - self._ultimo_update > _UPDATE_INTERVAL:
                    self.actualizar_ahora()
            except Exception as e:
                self._log(f"[KnowledgeFeed] Error en loop: {e}")
            time.sleep(3600)   # revisar cada hora

    def _actualizar_conceptos(self) -> int:
        """
        Descarga definiciones de conceptos clave de trading desde Wikipedia.
        """
        if not _REQ_OK:
            return 0

        conceptos_clave = [
            "Análisis técnico", "Vela japonesa", "RSI", "MACD",
            "Bollinger Bands", "Soporte y resistencia", "Tendencia de mercado",
            "Gestión de riesgo", "Order block", "Estructura de mercado",
            "Break of structure", "Liquidity sweep", "Fibonacci retroceso",
            "Sesión de Londres", "Sesión de Nueva York", "Opciones binarias",
        ]

        actualizados = 0
        with self._lock:
            if "conceptos" not in self._conocimiento:
                self._conocimiento["conceptos"] = {}

        for concepto in conceptos_clave:
            # Evitar re-descargar si ya tenemos datos recientes (< 7 días)
            existente = self._conocimiento.get("conceptos", {}).get(concepto, {})
            if (isinstance(existente, dict) and
                    existente.get("ts", 0) > time.time() - 7 * 86400):
                continue

            try:
                # Wikipedia API en español
                resp = _req.get(
                    "https://es.wikipedia.org/api/rest_v1/page/summary/" +
                    concepto.replace(" ", "_"),
                    timeout=5,
                    headers={"User-Agent": "LITCH-TradingAI/3.0"},
                )
                if resp.status_code == 200:
                    datos = resp.json()
                    extracto = datos.get("extract", "")[:500]
                    with self._lock:
                        self._conocimiento["conceptos"][concepto] = {
                            "texto": extracto,
                            "ts":    time.time(),
                        }
                    actualizados += 1
                    time.sleep(0.3)   # respetar rate limit
            except Exception:
                pass

        return actualizados

    def _actualizar_noticias(self) -> int:
        """
        Descarga noticias económicas recientes via RSS de Yahoo Finance.
        """
        if not _REQ_OK:
            return 0

        feeds = [
            ("Yahoo Finance", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=eurusd=x&region=US&lang=en-US"),
            ("Forex Factory", "https://www.forexfactory.com/ff_calendar_thisweek.xml"),
        ]

        items = []
        for fuente, url in feeds:
            try:
                resp = _req.get(url, timeout=8,
                                headers={"User-Agent": "LITCH-TradingAI/3.0"})
                if resp.status_code == 200:
                    # Parseo simple de RSS sin librerías externas
                    contenido = resp.text
                    items_raw = contenido.split("<item>")[1:]
                    for item_raw in items_raw[:10]:
                        titulo  = self._extraer_xml(item_raw, "title")
                        resumen = self._extraer_xml(item_raw, "description")
                        fecha   = self._extraer_xml(item_raw, "pubDate")
                        if titulo:
                            items.append({
                                "titulo":  titulo[:120],
                                "resumen": resumen[:300] if resumen else "",
                                "fecha":   fecha,
                                "fuente":  fuente,
                            })
            except Exception:
                pass

        if items:
            with self._lock:
                self._noticias = {
                    "items":    items,
                    "timestamp": time.time(),
                }
            self._guardar_noticias()

        return len(items)

    def _actualizar_tasas(self) -> int:
        """Tasas de cambio actuales usando Open Exchange Rates (gratis)."""
        if not _REQ_OK:
            return 0
        try:
            # Usando exchangerate-api.com (gratuito, sin clave)
            resp = _req.get(
                "https://open.er-api.com/v6/latest/USD",
                timeout=5,
                headers={"User-Agent": "LITCH-TradingAI/3.0"},
            )
            if resp.status_code == 200:
                datos = resp.json()
                tasas = datos.get("rates", {})
                # Guardar pares relevantes (invertidos: USD→EUR = 1/EUR)
                pares = {}
                for moneda in ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]:
                    if moneda in tasas:
                        pares[f"USD/{moneda}"] = round(tasas[moneda], 5)
                        if tasas[moneda] != 0:
                            pares[f"{moneda}/USD"] = round(1 / tasas[moneda], 5)

                with self._lock:
                    self._conocimiento["tasas"] = pares
                    self._conocimiento["tasas_ts"] = time.time()
                return len(pares)
        except Exception:
            pass
        return 0

    def _actualizar_calendario(self) -> int:
        """
        Eventos económicos importantes de la semana.
        Usa una lista conocida de eventos clave que mueven el mercado.
        """
        # Eventos de alto impacto que LITCH debe conocer
        eventos_altos = [
            "NFP (Non-Farm Payrolls) — primer viernes de cada mes — USD",
            "FOMC (Decisión de tasas Fed) — 8 veces al año — USD",
            "BCE (Decisión de tasas) — cada 6 semanas — EUR",
            "CPI (Inflación EEUU) — mensual — USD",
            "GDP (PIB EEUU) — trimestral — USD",
            "Reportes de ganancias empresariales — trimestral",
        ]
        with self._lock:
            self._conocimiento["eventos_clave"] = eventos_altos
        return len(eventos_altos)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extraer_xml(texto: str, tag: str) -> str:
        """Extrae contenido de una etiqueta XML simple."""
        inicio = texto.find(f"<{tag}>")
        fin    = texto.find(f"</{tag}>")
        if inicio >= 0 and fin > inicio:
            contenido = texto[inicio + len(tag) + 2:fin]
            # Limpiar CDATA
            contenido = contenido.replace("<![CDATA[", "").replace("]]>", "")
            # Limpiar HTML básico
            import re
            contenido = re.sub(r"<[^>]+>", "", contenido).strip()
            return contenido[:300]
        return ""

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _cargar_conocimiento(self) -> dict:
        try:
            if os.path.exists(_CONOCIMIENTO_FILE):
                with open(_CONOCIMIENTO_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _cargar_noticias(self) -> dict:
        try:
            if os.path.exists(_NOTICIAS_FILE):
                with open(_NOTICIAS_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"items": []}

    def _guardar_conocimiento(self) -> None:
        try:
            os.makedirs(_BASE, exist_ok=True)
            with self._lock:
                snap = dict(self._conocimiento)
            with open(_CONOCIMIENTO_FILE, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"[KnowledgeFeed] Error guardando: {e}")

    def _guardar_noticias(self) -> None:
        try:
            with self._lock:
                snap = dict(self._noticias)
            with open(_NOTICIAS_FILE, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        if self._app and hasattr(self._app, "log"):
            self._app.log(msg)
        else:
            print(msg)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instancia: Optional[KnowledgeFeeder] = None


def obtener(app=None) -> KnowledgeFeeder:
    global _instancia
    if _instancia is None:
        _instancia = KnowledgeFeeder(app=app)
    return _instancia
