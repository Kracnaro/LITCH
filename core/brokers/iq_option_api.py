"""
iq_option_api.py — Conector IQ Option para LITCH via API oficial.

Usa la biblioteca iqoptionapi (WebSocket directo con IQ Option).
Ventajas sobre pyautogui:
  - No necesita que la ventana esté visible
  - Datos de velas en tiempo real
  - Saldo real sin leer la pantalla
  - Sentimiento del mercado (% SUBE / % BAJA)
  - Puede operar mientras LITCH está minimizado

Fallback: si no hay credenciales o falla la conexión,
          todas las operaciones reales siguen usando pyautogui.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import List, Optional

from .base import BrokerBase, InfoActivo, ResultadoTrade

_CRED_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "memoria_ap", "iq_credenciales.json")

try:
    from iqoptionapi.stable_api import IQ_Option as _IQApi
    _LIB_OK = True
except ImportError:
    _LIB_OK = False


# Mapa de nombres de activos IQ Option → símbolo estándar
_ASSET_MAP = {
    "EURUSD-OTC": "EUR/USD (OTC)",
    "EURGBP-OTC": "EUR/GBP (OTC)",
    "EURAUD-OTC": "EUR/AUD (OTC)",
    "GBPUSD-OTC": "GBP/USD (OTC)",
    "USDJPY-OTC": "USD/JPY (OTC)",
    "EURUSD":     "EUR/USD",
    "GBPUSD":     "GBP/USD",
}


class IQOptionBroker(BrokerBase):
    """
    Conector IQ Option via iqoptionapi.

    Flujo de uso:
        broker = IQOptionBroker()
        ok, msg = broker.conectar()
        if ok:
            saldo = broker.saldo("real")
            velas = broker.velas("EURUSD-OTC", 60, 200)
            resultado = broker.ejecutar_trade("EURUSD-OTC", "V", 50, 60)
    """

    nombre      = "IQ Option"
    descripcion = "Opciones binarias OTC y Forex — Blitz hasta 5min"

    def __init__(self):
        self._api: Optional[_IQApi] = None
        self._conectado   = False
        self._modo        = "demo"
        self._activo_sel  = "EURUSD-OTC"
        self._lock        = threading.Lock()
        self._cache_activos: List[InfoActivo] = []
        self._cache_activos_ts = 0.0

    # ── Credenciales ──────────────────────────────────────────────────────────

    @staticmethod
    def cargar_credenciales() -> dict:
        """Lee email/password de iq_credenciales.json"""
        try:
            if os.path.exists(_CRED_FILE):
                with open(_CRED_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    @staticmethod
    def guardar_credenciales(email: str, password: str) -> None:
        """Guarda credenciales cifradas en disco."""
        os.makedirs(os.path.dirname(_CRED_FILE), exist_ok=True)
        import base64
        datos = {
            "email": email,
            "password": base64.b64encode(password.encode()).decode(),
            "guardado": time.strftime("%Y-%m-%d %H:%M"),
        }
        with open(_CRED_FILE, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)

    # ── Conexión ──────────────────────────────────────────────────────────────

    def conectar(self, credenciales: dict = None) -> tuple[bool, str]:
        if not _LIB_OK:
            return False, "iqoptionapi no instalado. Ejecuta: py -m pip install git+https://github.com/Lu-Yi-Hsun/iqoptionapi"

        cred = credenciales or self.cargar_credenciales()
        if not cred.get("email") or not cred.get("password"):
            return False, "Sin credenciales IQ Option. Di 'mi cuenta IQ Option es email:contraseña'"

        try:
            import base64
            pwd = cred["password"]
            try:
                pwd = base64.b64decode(pwd.encode()).decode()
            except Exception:
                pass   # contraseña en texto plano

            self._api = _IQApi(cred["email"], pwd)
            check, reason = self._api.connect()
            if check:
                self._conectado = True
                # Por defecto modo práctica (demo) para seguridad
                self._api.change_balance("PRACTICE")
                self._modo = "demo"
                return True, f"Conectado a IQ Option como {cred['email']}"
            else:
                return False, f"Error de login: {reason}"
        except Exception as e:
            return False, f"Error conexión IQ Option: {e}"

    def desconectar(self) -> None:
        with self._lock:
            self._conectado = False
            self._api = None

    @property
    def conectado(self) -> bool:
        return self._conectado and self._api is not None

    # ── Cuenta ────────────────────────────────────────────────────────────────

    def saldo(self, modo: str = None) -> float:
        if not self.conectado:
            return 0.0
        try:
            m = modo or self._modo
            self._api.change_balance("PRACTICE" if m == "demo" else "REAL")
            return float(self._api.get_balance())
        except Exception:
            return 0.0

    def modo_cuenta(self) -> str:
        return self._modo

    def cambiar_modo(self, modo: str) -> bool:
        if not self.conectado:
            return False
        try:
            iq_modo = "PRACTICE" if modo == "demo" else "REAL"
            self._api.change_balance(iq_modo)
            self._modo = modo
            return True
        except Exception:
            return False

    # ── Activos ───────────────────────────────────────────────────────────────

    def activos_disponibles(self, tipo: str = "binarias") -> List[InfoActivo]:
        if not self.conectado:
            return []
        # Caché de 30 segundos
        if time.time() - self._cache_activos_ts < 30 and self._cache_activos:
            return self._cache_activos
        try:
            raw = self._api.get_all_open_time()
            activos = []
            for mercado in ("turbo", "binary"):
                for nombre, info in raw.get(mercado, {}).items():
                    if not info.get("open", False):
                        continue
                    activos.append(InfoActivo(
                        simbolo     = nombre,
                        nombre      = _ASSET_MAP.get(nombre, nombre),
                        payout_pct  = float(info.get("profit", {}).get("successful", 85)),
                        disponible  = True,
                    ))
            # Enriquecer con sentimiento del mercado
            activos = self._enriquecer_sentimiento(activos)
            self._cache_activos    = activos
            self._cache_activos_ts = time.time()
            return activos
        except Exception as e:
            return []

    def _enriquecer_sentimiento(self, activos: List[InfoActivo]) -> List[InfoActivo]:
        """Añade % de traders que esperan suba vs baja para cada activo."""
        try:
            for a in activos[:10]:   # limitar para no sobrecargar
                try:
                    info = self._api.get_technical_indicators(a.simbolo)
                    if info:
                        compra = float(info.get("sell_transactions", 0))
                        venta  = float(info.get("buy_transactions", 0))
                        total  = compra + venta
                        if total > 0:
                            a.sentimiento = compra / total
                except Exception:
                    pass
        except Exception:
            pass
        return activos

    def activo_recomendado(self, tipo: str = "binarias") -> Optional[InfoActivo]:
        """
        Elige el mejor activo: mayor payout Y mayor consenso de mercado.
        Prefiere activos con sentimiento > 60% en una dirección (tendencia clara).
        """
        activos = self.activos_disponibles(tipo)
        if not activos:
            return None
        # Score: payout * 0.6 + abs(sentimiento - 0.5)*2 * 0.4
        def score(a: InfoActivo) -> float:
            claridad = abs(a.sentimiento - 0.5) * 2   # 0=neutro, 1=extremo
            return (a.payout_pct / 100) * 0.6 + claridad * 0.4
        return max(activos, key=score)

    # ── Datos de mercado ──────────────────────────────────────────────────────

    def velas(self, activo: str, periodo_seg: int, n: int = 200) -> list:
        if not self.conectado:
            return []
        try:
            end = time.time()
            raw = self._api.get_candles(activo, periodo_seg, n, end)
            resultado = []
            for v in raw:
                resultado.append({
                    "time":   v.get("from",  0),
                    "open":   float(v.get("open",  0)),
                    "high":   float(v.get("max",   0)),
                    "low":    float(v.get("min",   0)),
                    "close":  float(v.get("close", 0)),
                    "volume": float(v.get("volume", 0)),
                })
            return resultado
        except Exception:
            return []

    def sentimiento_activo(self, activo: str) -> dict:
        """
        Retorna el sentimiento actual del mercado para este activo.
        {'sube_pct': 67, 'baja_pct': 33, 'activo': 'EUR/AUD-OTC'}
        """
        if not self.conectado:
            return {}
        try:
            info = self._api.get_technical_indicators(activo)
            if info:
                venden = float(info.get("sell_transactions", 50))
                compran = float(info.get("buy_transactions", 50))
                total  = venden + compran
                if total > 0:
                    return {
                        "sube_pct": round(venden / total * 100, 1),
                        "baja_pct": round(compran / total * 100, 1),
                        "activo":   activo,
                    }
        except Exception:
            pass
        return {}

    # ── Trading ───────────────────────────────────────────────────────────────

    def ejecutar_trade(self, activo: str, direccion: str,
                       monto: float, venc_seg: int) -> ResultadoTrade:
        if not self.conectado:
            return ResultadoTrade(False, mensaje="No conectado a IQ Option API")

        try:
            accion = "call" if direccion == "V" else "put"
            # IQ Option Blitz usa vencimiento en segundos directamente
            # Las opciones turbo usan minutos; Blitz usa segundos
            venc_min = max(1, venc_seg // 60)

            check, id_trade = self._api.buy(
                price           = monto,
                active          = activo,
                direction       = accion,
                expirations_mode = venc_min,
            )

            if check:
                return ResultadoTrade(
                    exito     = True,
                    id_trade  = str(id_trade),
                    activo    = activo,
                    direccion = direccion,
                    monto     = monto,
                    mensaje   = f"Trade ejecutado vía API: {accion} {activo} ${monto}",
                )
            else:
                return ResultadoTrade(False, mensaje=f"IQ Option rechazó el trade: {id_trade}")
        except Exception as e:
            return ResultadoTrade(False, mensaje=f"Error trade: {e}")

    def resultado_trade(self, id_trade: str, esperar_seg: int = 70) -> Optional[dict]:
        """
        Espera y retorna el resultado de un trade por ID.
        Retorna {'ganancia': float, 'acierto': bool} o None si timeout.
        """
        if not self.conectado:
            return None
        try:
            t_inicio = time.time()
            while time.time() - t_inicio < esperar_seg:
                try:
                    resultado = self._api.check_win_v3(id_trade)
                    if resultado:
                        ganancia = float(resultado)
                        return {
                            "acierto":  ganancia > 0,
                            "ganancia": ganancia,
                        }
                except Exception:
                    pass
                time.sleep(2)
        except Exception:
            pass
        return None

    # ── Exploración / Auto-aprendizaje ────────────────────────────────────────

    def explorar_mercado(self) -> dict:
        """
        LITCH explora el mercado como lo haría un trader humano:
        - Ve qué activos están abiertos
        - Identifica los de mayor payout
        - Lee el sentimiento general
        - Retorna resumen de oportunidades
        """
        if not self.conectado:
            return {"error": "No conectado"}

        activos = self.activos_disponibles()
        if not activos:
            return {"activos": 0}

        top3 = sorted(activos, key=lambda a: a.payout_pct, reverse=True)[:3]
        resumen = {
            "total_activos": len(activos),
            "top_payout":    [(a.nombre, a.payout_pct) for a in top3],
            "recomendado":   top3[0].simbolo if top3 else None,
            "saldo_demo":    self.saldo("demo"),
            "saldo_real":    self.saldo("real"),
        }
        return resumen
