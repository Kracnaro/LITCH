"""
base.py — Interfaz universal de broker para LITCH.

Todos los brokers (IQ Option, IBKR, Schwab) implementan esta clase.
LITCH habla con esta interfaz sin importar el broker concreto.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class InfoActivo:
    """Información de un activo de trading."""
    simbolo:     str
    nombre:      str
    payout_pct:  float = 85.0    # % de ganancia (IQ Option: 85%)
    tendencia:   str   = "neutra" # 'sube' | 'baja' | 'neutra'
    volatilidad: float = 0.5      # 0-1, mayor = más volátil
    sentimiento: float = 0.5      # 0-1, porcentaje de operadores que esperan suba
    disponible:  bool  = True
    precio:      float = 0.0


@dataclass
class ResultadoTrade:
    """Resultado de un trade ejecutado."""
    exito:       bool
    id_trade:    str   = ""
    activo:      str   = ""
    direccion:   str   = ""     # 'V' (call/sube) | 'R' (put/baja)
    monto:       float = 0.0
    ganancia:    float = 0.0    # positivo = ganó, negativo = perdió
    mensaje:     str   = ""
    precio_entrada: float = 0.0
    precio_salida:  float = 0.0


class BrokerBase(ABC):
    """
    Interfaz base que todos los brokers deben implementar.

    LITCH usa esta clase para operar sin importar el broker.
    """

    nombre: str = "Broker"
    descripcion: str = ""

    # ── Conexión ──────────────────────────────────────────────────────────────

    @abstractmethod
    def conectar(self, credenciales: dict = None) -> tuple[bool, str]:
        """
        Conecta con el broker.

        Retorna (éxito, mensaje).
        """
        ...

    @abstractmethod
    def desconectar(self) -> None:
        """Cierra la conexión limpiamente."""
        ...

    @property
    @abstractmethod
    def conectado(self) -> bool:
        """True si hay conexión activa."""
        ...

    # ── Cuenta ────────────────────────────────────────────────────────────────

    @abstractmethod
    def saldo(self, modo: str = "demo") -> float:
        """
        Retorna el saldo disponible.

        modo: 'demo' | 'real'
        """
        ...

    @abstractmethod
    def modo_cuenta(self) -> str:
        """Retorna 'demo' o 'real'."""
        ...

    @abstractmethod
    def cambiar_modo(self, modo: str) -> bool:
        """Cambia entre 'demo' y 'real'. Retorna éxito."""
        ...

    # ── Activos ───────────────────────────────────────────────────────────────

    @abstractmethod
    def activos_disponibles(self, tipo: str = "binarias") -> List[InfoActivo]:
        """
        Lista de activos disponibles para operar.

        tipo: 'binarias' | 'forex' | 'acciones' | 'cripto' | 'todos'
        """
        ...

    def activo_recomendado(self, tipo: str = "binarias") -> Optional[InfoActivo]:
        """
        Retorna el activo con mejor combinación de payout + tendencia.
        Por defecto, filtra los disponibles y ordena por payout.
        """
        activos = self.activos_disponibles(tipo)
        disponibles = [a for a in activos if a.disponible]
        if not disponibles:
            return None
        return max(disponibles, key=lambda a: a.payout_pct)

    # ── Datos de mercado ──────────────────────────────────────────────────────

    @abstractmethod
    def velas(self, activo: str, periodo_seg: int,
              n: int = 200) -> list:
        """
        Retorna lista de velas OHLCV.

        Cada vela: {'time': epoch, 'open': f, 'high': f, 'low': f, 'close': f, 'volume': f}
        """
        ...

    def precio_actual(self, activo: str) -> float:
        """Precio actual del activo (último close disponible)."""
        velas = self.velas(activo, 1, n=1)
        if velas:
            return float(velas[-1].get("close", 0))
        return 0.0

    # ── Trading ───────────────────────────────────────────────────────────────

    @abstractmethod
    def ejecutar_trade(self, activo: str, direccion: str,
                       monto: float, venc_seg: int) -> ResultadoTrade:
        """
        Ejecuta un trade.

        direccion: 'V' (call/sube) | 'R' (put/baja)
        venc_seg:  segundos hasta el vencimiento
        """
        ...

    # ── Info ──────────────────────────────────────────────────────────────────

    def resumen(self) -> str:
        """Texto de estado del broker para el log."""
        estado = "conectado" if self.conectado else "desconectado"
        return f"[{self.nombre}] {estado} | modo={self.modo_cuenta()}"
