"""
broker_universal.py — Gestor multi-broker para LITCH.

LITCH puede operar en múltiples brokers simultáneamente.
Este módulo gestiona cuál está activo, cómo cambiar entre ellos,
y provee una interfaz unificada para trading.

Brokers soportados:
  - IQ Option   (opciones binarias OTC, Blitz)  ← principal actual
  - IBKR         (forex, acciones, opciones, futuros)
  - Schwab       (acciones, ETFs, $0 comisión en EEUU)

Uso:
    gestor = BrokerUniversal()
    gestor.activar("iq_option")
    broker = gestor.broker_activo()
    broker.conectar()
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional, Dict, List

from .brokers.base import BrokerBase, InfoActivo, ResultadoTrade
from .brokers.iq_option_api import IQOptionBroker
from .brokers.ibkr_broker    import IBKRBroker
from .brokers.schwab_broker  import SchwabBroker


_ESTADO_FILE = os.path.join(
    os.path.dirname(__file__), "..", "memoria_ap", "broker_universal.json")


class BrokerUniversal:
    """
    Gestor de brokers múltiples para LITCH.

    Permite conectar a diferentes brokers y cambiar entre ellos
    por voz o automáticamente.
    """

    _BROKERS_DISP = {
        "iq_option": IQOptionBroker,
        "ibkr":      IBKRBroker,
        "schwab":    SchwabBroker,
    }

    def __init__(self, app=None):
        self._app       = app
        self._lock      = threading.Lock()
        self._activo_id = "iq_option"
        self._instancias: Dict[str, BrokerBase] = {}
        self._cargar_estado()

    # ── API principal ─────────────────────────────────────────────────────────

    def broker_activo(self) -> Optional[BrokerBase]:
        """Retorna la instancia del broker actualmente seleccionado."""
        with self._lock:
            return self._instancias.get(self._activo_id)

    def activar(self, nombre: str) -> tuple[bool, str]:
        """
        Activa un broker como el principal.

        nombre: 'iq_option' | 'ibkr' | 'schwab'
        """
        nombre = nombre.lower().replace(" ", "_").replace("-", "_")
        alias = {
            "interactive": "ibkr",
            "interactive_brokers": "ibkr",
            "iq":          "iq_option",
            "charles":     "schwab",
            "charles_schwab": "schwab",
        }
        nombre = alias.get(nombre, nombre)

        if nombre not in self._BROKERS_DISP:
            return False, f"Broker '{nombre}' no reconocido. Disponibles: {list(self._BROKERS_DISP)}"

        with self._lock:
            if nombre not in self._instancias:
                self._instancias[nombre] = self._BROKERS_DISP[nombre]()
            self._activo_id = nombre
            self._guardar_estado()

        return True, f"Broker activado: {self._instancias[nombre].nombre}"

    def conectar(self, nombre: str = None,
                 credenciales: dict = None) -> tuple[bool, str]:
        """Conecta el broker activo (o el especificado)."""
        if nombre:
            ok, msg = self.activar(nombre)
            if not ok:
                return ok, msg

        broker = self.broker_activo()
        if broker is None:
            return False, "Sin broker activo"

        ok, msg = broker.conectar(credenciales)
        if ok:
            self._log(f"[{broker.nombre}] Conectado")
        else:
            self._log(f"[{broker.nombre}] Error: {msg}")
        return ok, msg

    def saldo(self, modo: str = None) -> float:
        """Saldo del broker activo."""
        broker = self.broker_activo()
        if broker and broker.conectado:
            return broker.saldo(modo)
        return 0.0

    def ejecutar_trade(self, activo: str, direccion: str,
                       monto: float, venc_seg: int) -> ResultadoTrade:
        """Ejecuta un trade en el broker activo."""
        broker = self.broker_activo()
        if broker is None:
            return ResultadoTrade(False, mensaje="Sin broker activo")
        if not broker.conectado:
            return ResultadoTrade(False, mensaje=f"{broker.nombre} no conectado")
        return broker.ejecutar_trade(activo, direccion, monto, venc_seg)

    def velas(self, activo: str, periodo_seg: int, n: int = 200) -> list:
        """Velas del broker activo."""
        broker = self.broker_activo()
        if broker and broker.conectado:
            return broker.velas(activo, periodo_seg, n)
        return []

    def activos_disponibles(self, tipo: str = "todos") -> List[InfoActivo]:
        """Activos del broker activo."""
        broker = self.broker_activo()
        if broker and broker.conectado:
            return broker.activos_disponibles(tipo)
        return []

    def activo_recomendado(self) -> Optional[InfoActivo]:
        """Mejor activo para operar ahora mismo."""
        broker = self.broker_activo()
        if broker and broker.conectado:
            return broker.activo_recomendado()
        return None

    # ── Estado ────────────────────────────────────────────────────────────────

    def resumen(self) -> str:
        """Estado textual del gestor."""
        lineas = [f"[BrokerUniversal] Activo: {self._activo_id}"]
        for nombre, inst in self._instancias.items():
            estado = "✓ conectado" if inst.conectado else "✗ desconectado"
            lineas.append(f"  {inst.nombre}: {estado}")
        if not self._instancias:
            lineas.append("  (ningún broker inicializado)")
        return "\n".join(lineas)

    def info_broker_texto(self) -> str:
        """Texto descriptivo para respuesta de voz."""
        broker = self.broker_activo()
        if broker is None:
            return "Ningún broker activado."
        estado = "conectado" if broker.conectado else "desconectado"
        saldo  = broker.saldo() if broker.conectado else 0.0
        return (
            f"Broker activo: {broker.nombre}. "
            f"Estado: {estado}. "
            + (f"Saldo: ${saldo:,.2f}." if saldo > 0 else "")
            + f" {broker.descripcion}"
        )

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _cargar_estado(self) -> None:
        try:
            if os.path.exists(_ESTADO_FILE):
                with open(_ESTADO_FILE) as f:
                    datos = json.load(f)
                self._activo_id = datos.get("activo", "iq_option")
        except Exception:
            pass

    def _guardar_estado(self) -> None:
        try:
            os.makedirs(os.path.dirname(_ESTADO_FILE), exist_ok=True)
            with open(_ESTADO_FILE, "w") as f:
                json.dump({"activo": self._activo_id}, f)
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        if self._app and hasattr(self._app, "log"):
            self._app.log(msg)
        else:
            print(msg)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instancia: Optional[BrokerUniversal] = None


def obtener(app=None) -> BrokerUniversal:
    global _instancia
    if _instancia is None:
        _instancia = BrokerUniversal(app=app)
    return _instancia
