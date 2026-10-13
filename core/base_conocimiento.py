"""
Base de conocimiento persistente de Litch.

Litch almacena todo lo que aprende en una carpeta local (MEMORIA_AP/conocimiento/).
Cada tema es un fichero JSON independiente — fácil de respaldar, editar y migrar.

Estructura:
    MEMORIA_AP/
      conocimiento/
        brokers.json        — cómo funcionan Schwab, IBKR, IQ Option, etc.
        trading.json        — patrones, estrategias, lecciones aprendidas
        mercados.json       — análisis de activos, noticias importantes
        sesiones.json       — resumen de cada sesión de trading
        personal.json       — preferencias del usuario, metas, notas

La IA puede LEER este conocimiento para responder preguntas y ESCRIBIR
nuevas lecciones aprendidas durante el trading real.
"""

import json
import os
import threading
import time
from typing import Any, Optional

from . import memoria as mem_mod

_TOPICS_PREDEF = ("brokers", "trading", "mercados", "sesiones",
                  "personal", "estrategias", "errores", "logros")


class BaseConocimiento:
    """
    Base de conocimiento local, persistente y creciente de Litch.

    Litch aprende de cada sesión, cada error y cada éxito —
    y lo guarda aquí para recordarlo en conversaciones futuras.

    Uso:
        bc = BaseConocimiento(app)
        bc.guardar("brokers", "schwab_ventajas", "Sin comisiones en ETFs US.")
        bc.leer("brokers", "schwab_ventajas")
        bc.buscar("comisiones")
        bc.resumen_tema("brokers")
    """

    def __init__(self, app):
        self.app   = app
        self._lock = threading.Lock()
        self._ruta = os.path.join(mem_mod.ruta_memoria_ap(), "conocimiento")
        os.makedirs(self._ruta, exist_ok=True)
        self._cache: dict[str, dict] = {}
        self._inicializar_conocimiento_base()

    # ── CRUD ────────────────────────────────────────────────────────────────

    def guardar(self, tema: str, clave: str, contenido: Any,
                fuente: str = "litch") -> None:
        """
        Guarda un fragmento de conocimiento.

        tema     : categoría (brokers, trading, mercados, etc.)
        clave    : nombre del conocimiento (schwab_api, rsi_sobrecompra, etc.)
        contenido: texto, lista, dict — lo que Litch aprendió
        fuente   : "litch", "usuario", "mercado", "ia"
        """
        with self._lock:
            datos = self._cargar_tema(tema)
            datos[clave] = {
                "contenido": contenido,
                "fuente":    fuente,
                "ts":        time.strftime("%Y-%m-%d %H:%M:%S"),
                "revisiones": datos.get(clave, {}).get("revisiones", 0) + 1,
            }
            self._guardar_tema(tema, datos)
            self._cache[tema] = datos

    def leer(self, tema: str, clave: str) -> Optional[Any]:
        """Lee un fragmento de conocimiento. Devuelve None si no existe."""
        datos = self._cargar_tema(tema)
        entrada = datos.get(clave)
        return entrada["contenido"] if entrada else None

    def leer_completo(self, tema: str, clave: str) -> Optional[dict]:
        """Lee el fragmento con metadatos (fuente, timestamp, revisiones)."""
        datos = self._cargar_tema(tema)
        return datos.get(clave)

    def eliminar(self, tema: str, clave: str) -> bool:
        """Elimina un fragmento de conocimiento."""
        with self._lock:
            datos = self._cargar_tema(tema)
            if clave in datos:
                del datos[clave]
                self._guardar_tema(tema, datos)
                self._cache[tema] = datos
                return True
        return False

    def listar(self, tema: str) -> list[str]:
        """Lista las claves disponibles en un tema."""
        return list(self._cargar_tema(tema).keys())

    def temas(self) -> list[str]:
        """Lista todos los temas con conocimiento guardado."""
        try:
            return [f[:-5] for f in os.listdir(self._ruta)
                    if f.endswith(".json")]
        except Exception:
            return []

    # ── Búsqueda ────────────────────────────────────────────────────────────

    def buscar(self, termino: str) -> list[dict]:
        """
        Busca un término en TODOS los temas.
        Devuelve lista de matches con tema, clave y extracto del contenido.
        """
        termino_l = termino.lower()
        resultados = []
        for tema in self.temas():
            datos = self._cargar_tema(tema)
            for clave, entrada in datos.items():
                contenido_str = str(entrada.get("contenido", "")).lower()
                if (termino_l in clave.lower() or termino_l in contenido_str):
                    extracto = str(entrada.get("contenido", ""))[:150]
                    resultados.append({
                        "tema":    tema,
                        "clave":   clave,
                        "extracto":extracto,
                        "ts":      entrada.get("ts"),
                    })
        return resultados

    def responder(self, pregunta: str) -> Optional[str]:
        """
        Intenta responder una pregunta buscando en la base de conocimiento.
        Devuelve el mejor match o None si no sabe.
        """
        matches = self.buscar(pregunta.lower().replace("?", ""))
        if not matches:
            return None
        # Retorna el extracto más relevante
        mejor = matches[0]
        clave   = mejor["clave"]
        contenido = self.leer(mejor["tema"], clave)
        if isinstance(contenido, str) and len(contenido) > 20:
            return contenido[:600]
        return None

    # ── Resúmenes ───────────────────────────────────────────────────────────

    def resumen_tema(self, tema: str) -> str:
        """Resumen legible de todo lo que Litch sabe sobre un tema."""
        datos = self._cargar_tema(tema)
        if not datos:
            return f"No tengo conocimiento guardado sobre '{tema}' aún."
        lineas = [f"[{tema.upper()}] — {len(datos)} entradas de conocimiento:"]
        for clave, entrada in list(datos.items())[:15]:
            extracto = str(entrada.get("contenido", ""))[:100].replace("\n", " ")
            lineas.append(f"  • {clave}: {extracto}…" if len(str(entrada.get("contenido",""))) > 100
                          else f"  • {clave}: {extracto}")
        return "\n".join(lineas)

    def estadisticas(self) -> str:
        """Cuánto sabe Litch en total."""
        total_entradas = 0
        desglose = []
        for tema in self.temas():
            datos = self._cargar_tema(tema)
            n = len(datos)
            total_entradas += n
            if n > 0:
                desglose.append(f"{tema}={n}")
        return (f"Base de conocimiento: {total_entradas} entradas | "
                + " | ".join(desglose))

    # ── Registro automático de sesiones ─────────────────────────────────────

    def registrar_sesion(self, trades: int, wins: int, pnl: float,
                         activo: str, modo: str = "practica") -> None:
        """
        Registra un resumen de sesión automáticamente.
        Llamar al final de cada sesión de trading.
        """
        wr   = wins / trades * 100 if trades else 0
        clave = time.strftime("sesion_%Y%m%d_%H%M")
        self.guardar("sesiones", clave, {
            "fecha":  time.strftime("%Y-%m-%d"),
            "hora":   time.strftime("%H:%M"),
            "trades": trades,
            "wins":   wins,
            "losses": trades - wins,
            "wr_pct": round(wr, 1),
            "pnl":    round(pnl, 2),
            "activo": activo,
            "modo":   modo,
        }, fuente="auto")

    def registrar_leccion(self, leccion: str, categoria: str = "trading") -> None:
        """
        Guarda una lección aprendida durante el trading.
        Ejemplo: bc.registrar_leccion("El RSI en 80+ con vela bajista → señal de venta fuerte")
        """
        clave = f"leccion_{int(time.time())}"
        self.guardar(categoria, clave, leccion, fuente="experiencia")
        self.app.log(f"[Conocimiento] Lección guardada: {leccion[:60]}...")

    # ── Persistencia ────────────────────────────────────────────────────────

    def _cargar_tema(self, tema: str) -> dict:
        if tema in self._cache:
            return self._cache[tema]
        ruta = os.path.join(self._ruta, f"{tema}.json")
        if not os.path.exists(ruta):
            return {}
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            self._cache[tema] = datos
            return datos
        except Exception:
            return {}

    def _guardar_tema(self, tema: str, datos: dict) -> None:
        ruta = os.path.join(self._ruta, f"{tema}.json")
        try:
            tmp = ruta + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=1)
            os.replace(tmp, ruta)
        except Exception as e:
            self.app.log(f"[Conocimiento] Error guardando {tema}: {e}")

    # ── Conocimiento base (pre-cargado al crear) ─────────────────────────────

    def _inicializar_conocimiento_base(self) -> None:
        """
        Siembra el conocimiento inicial sobre brokers y trading
        si el fichero de brokers aún no existe.
        No sobreescribe conocimiento ya guardado.
        """
        ruta_brokers = os.path.join(self._ruta, "brokers.json")
        if os.path.exists(ruta_brokers):
            return   # ya inicializado

        from .broker_ibkr import BrokerIBKR
        from .broker_schwab import BrokerSchwab

        # ── Interactive Brokers ─────────────────────────────────────────
        for clave, texto in BrokerIBKR.CONOCIMIENTO.items():
            self.guardar("brokers", f"ibkr_{clave}", texto, fuente="sistema")

        # ── Charles Schwab ──────────────────────────────────────────────
        for clave, texto in BrokerSchwab.CONOCIMIENTO.items():
            self.guardar("brokers", f"schwab_{clave}", texto, fuente="sistema")

        # ── Conocimiento general de trading ─────────────────────────────
        conocimiento_trading = {
            "binario_vs_acciones": (
                "OPCIONES BINARIAS (IQ Option) vs ACCIONES REALES (Schwab/IBKR):\n"
                "Binarias: ganas/pierdes monto fijo. Duración 60s-5min. Alto riesgo.\n"
                "Acciones: ganas/pierdes según movimiento de precio. Puedes tener posición meses.\n"
                "La formación en IQ Option sirve: aprendes a leer velas, patrones y momentum.\n"
                "La diferencia es que en acciones el TIEMPO no te cierra la posición automáticamente."
            ),
            "velas_japonesas": (
                "Las velas japonesas son iguales en todos los mercados:\n"
                "• Doji: incertidumbre — posible reversión\n"
                "• Martillo: reversal alcista tras caída\n"
                "• Estrella fugaz: reversal bajista tras subida\n"
                "• Envolvente alcista: bullish engulfing — fuerte señal de compra\n"
                "• Envolvente bajista: bearish engulfing — fuerte señal de venta\n"
                "• Marubozu: vela sin sombras — precio dominado por un solo lado"
            ),
            "soportes_resistencias": (
                "SOPORTES Y RESISTENCIAS — claves en acciones reales:\n"
                "• Soporte: nivel donde el precio rebota hacia arriba (compradores aguantan)\n"
                "• Resistencia: nivel donde el precio rebota hacia abajo (vendedores dominan)\n"
                "• Breakout: cuando el precio rompe una resistencia con volumen → señal fuerte\n"
                "• Retest: precio vuelve a tocar nivel roto antes de continuar → entrada ideal"
            ),
            "indicadores_clave": (
                "INDICADORES más usados en acciones reales:\n"
                "• RSI (14): >70 sobrecompra (posible venta), <30 sobreventa (posible compra)\n"
                "• MACD: cruce de líneas → señal de cambio de tendencia\n"
                "• EMAs 20/50/200: precio sobre EMA200 = tendencia alcista\n"
                "• Volumen: confirma los movimientos de precio\n"
                "• VWAP: precio promedio ponderado por volumen — clave para intradía"
            ),
            "kelly_acciones": (
                "CRITERIO DE KELLY para acciones:\n"
                "f = (p * b - q) / b\n"
                "p = probabilidad de win, q = 1-p, b = ratio ganancia/pérdida\n"
                "Ejemplo: 60% WR, ratio 1:2 → f = (0.6*2 - 0.4)/2 = 0.4 = 40%\n"
                "NUNCA usar el Kelly completo — usa Kelly/4 como máximo.\n"
                "En la práctica: máximo 2-5% del capital por operación."
            ),
            "cuando_pasar_acciones": (
                "CUÁNDO PASAR DE IQ OPTION A ACCIONES REALES:\n"
                "1. Al menos 3 meses operando IQ Option con WR > 60% consistente.\n"
                "2. Entiendes por qué ganas y por qué pierdes (no es suerte).\n"
                "3. Has practicado en paper trading (Thinkorswim Paper) por 1 mes.\n"
                "4. Tienes capital suficiente: mínimo $500 (ideal $2,000+).\n"
                "5. Tu stop-loss es automático y nunca lo mueves 'para esperar'.\n"
                "6. Empiezas con acciones de alta capitalización: AAPL, MSFT, SPY."
            ),
        }
        for clave, texto in conocimiento_trading.items():
            self.guardar("trading", clave, texto, fuente="sistema")

        # ── Activos recomendados para principiantes ──────────────────────
        conocimiento_mercados = {
            "spy": (
                "SPY — SPDR S&P 500 ETF Trust\n"
                "Replica el rendimiento del S&P 500 (las 500 empresas más grandes de EEUU).\n"
                "Volumen diario: +60 millones de acciones — muy líquido.\n"
                "Precio aproximado: $500 USD.\n"
                "Ideal para: principiantes, inversión a largo plazo, opciones.\n"
                "El 'termómetro' del mercado US."
            ),
            "qqq": (
                "QQQ — Invesco QQQ Trust\n"
                "Replica el NASDAQ 100 (las 100 mayores empresas tecnológicas).\n"
                "Incluye: AAPL, MSFT, NVDA, META, AMZN, GOOGL, TSLA y más.\n"
                "Más volátil que SPY (+/-2% en días normales).\n"
                "Ideal para: traders que buscan más movimiento que SPY."
            ),
            "aapl": (
                "AAPL — Apple Inc.\n"
                "La empresa más valiosa del mundo (~$3T capitalización bursátil).\n"
                "Muy líquida, spreadsmínimos, comportamiento predecible.\n"
                "Sigue al mercado general pero con beta ~1.2.\n"
                "Reportes trimestrales en enero, abril, julio, octubre → alta volatilidad."
            ),
            "nvda": (
                "NVDA — NVIDIA Corporation\n"
                "Líder en chips GPU para IA. Una de las acciones más volátiles del S&P 500.\n"
                "Beta ~1.8 — mueve mucho más que el mercado.\n"
                "Para traders avanzados: rentable pero requiere stops ajustados.\n"
                "Splits frecuentes (10:1 en 2024) — accesible a todos los capitales."
            ),
            "sesion_ny": (
                "SESIÓN DE NUEVA YORK para acciones US:\n"
                "• 09:30–10:30 ET: apertura — mayor volatilidad, mejores oportunidades.\n"
                "• 10:30–11:30 ET: consolidación — menos señales claras.\n"
                "• 11:30–14:00 ET: lunch lull — mercado lateral, evitar.\n"
                "• 14:00–15:30 ET: re-activación de tarde — buenas señales.\n"
                "• 15:30–16:00 ET: cierre — alta volatilidad, posibles reversales.\n"
                "Mejor momento para intradía: 09:30–10:30 y 14:00–15:30 ET."
            ),
        }
        for clave, texto in conocimiento_mercados.items():
            self.guardar("mercados", clave, texto, fuente="sistema")

        self.app.log("[Conocimiento] Base inicializada con conocimiento de IBKR, Schwab y mercados.")
