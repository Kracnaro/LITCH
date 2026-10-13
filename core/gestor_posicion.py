"""
gestor_posicion.py — Litch gestiona la operación mientras está viva.

Hasta ahora Litch entraba con un plan y esperaba a que saltara el stop o el
objetivo. Eso es correcto, pero es lo que hace un aficionado disciplinado.
Un profesional hace además una cosa: **mueve el stop a punto de equilibrio
cuando la operación ya le ha dado margen**.

QUÉ ES EL PUNTO DE EQUILIBRIO
─────────────────────────────
Si entró en 100 con stop en 96 (arriesgando 4, o sea 1R) y el precio llega
a 104 (+1R de ganancia), mover el stop de 96 a 100 convierte una operación
que todavía podía perder 4 en una que, como mucho, no gana nada.

Deja de ser una apuesta y pasa a ser una opción gratuita.

LA OTRA CARA, QUE CASI NADIE CUENTA
───────────────────────────────────
Mover el stop a equilibrio DEMASIADO PRONTO le saca de operaciones buenas.
El precio rara vez sube en línea recta: retrocede, respira, y vuelve. Si el
stop está justo en la entrada, cualquier retroceso normal le echa fuera de
una operación que habría ganado.

No existe el ajuste perfecto. Aquí se espera a +1R porque es el punto donde
la mayoría de sistemas encuentran el equilibrio entre proteger y dejar
respirar. Se puede cambiar, y conviene saber que se está eligiendo, no
acertando.

LA REGLA QUE NO SE PUEDE ROMPER
───────────────────────────────
El stop SOLO se mueve a favor. Nunca en contra. Jamás.

Ampliar un stop porque la operación va mal —«dale un poco más de margen,
seguro que rebota»— es el hábito que más cuentas ha destruido en la
historia de esto. Convierte una pérdida planificada de 1R en una pérdida
de 3R, de 5R, o en toda la cuenta.

Aquí es estructuralmente imposible: la función que mueve el stop comprueba
la dirección y se niega. No es una advertencia en un comentario, es código.
"""

from __future__ import annotations

import threading
import time

INTERVALO = 45            # revisar cada 45 segundos
R_EQUILIBRIO = 1.0        # a +1R se mueve el stop a la entrada
COLCHON = 0.0005          # 0.05% por encima de la entrada, para comisiones
R_TRAILING = 2.0          # a partir de +2R, el stop sigue al precio
FRACCION_TRAIL = 0.5      # deja correr la mitad del avance


class GestorPosicion(threading.Thread):
    """Cuida las operaciones abiertas como lo haría un operador con oficio."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchGestorPos")
        self.app = app
        self._parar = threading.Event()
        self.activo = True
        self.mover_a_equilibrio = True
        self.usar_trailing = False      # apagado por defecto: es opcional
        self._ya_movidas: dict = {}     # op_id → nivel ya aplicado

    def parar(self):
        self._parar.set()

    def run(self):
        self._parar.wait(60)
        while not self._parar.is_set():
            if self.activo:
                try:
                    self.revisar()
                except Exception as e:
                    try:
                        self.app.log(f"[Gestor] {e}")
                    except Exception:
                        pass
            self._parar.wait(INTERVALO)

    # ── El trabajo ──────────────────────────────────────────────────────────

    def revisar(self) -> int:
        """Revisa cada posición abierta y ajusta lo que toque."""
        if not self.mover_a_equilibrio:
            return 0

        br = getattr(self.app, "broker_ibkr", None)
        if br is None or not getattr(br, "esta_conectado", False):
            return 0

        # Solo en cuenta simulada verificada
        if getattr(br, "_es_paper", None) is not True:
            return 0

        try:
            from . import memoria_acciones as mem_mod
            abiertas = [o for o in mem_mod.obtener()._ops if o.get("abierta")]
        except Exception:
            return 0

        ajustes = 0
        for op in abiertas:
            try:
                if self._gestionar(br, op):
                    ajustes += 1
            except Exception as e:
                self.app.log(f"[Gestor] {op.get('simbolo')}: {e}")
        return ajustes

    def _gestionar(self, br, op) -> bool:
        simbolo = op.get("simbolo")
        entrada = float(op.get("entrada") or 0)
        stop = float(op.get("stop") or 0)
        direccion = op.get("direccion", "COMPRA")
        op_id = op.get("id")

        if entrada <= 0 or stop <= 0:
            return False

        riesgo = abs(entrada - stop)
        if riesgo <= 0:
            return False

        precio = self._precio(br, simbolo)
        if precio <= 0:
            return False

        # ¿Cuánto llevamos ganado, medido en R?
        if direccion == "COMPRA":
            avance_r = (precio - entrada) / riesgo
        else:
            avance_r = (entrada - precio) / riesgo

        nivel_previo = self._ya_movidas.get(op_id, 0.0)

        # ── Punto de equilibrio a +1R ───────────────────────────────────────
        if avance_r >= R_EQUILIBRIO and nivel_previo < R_EQUILIBRIO:
            if direccion == "COMPRA":
                nuevo = entrada * (1 + COLCHON)
            else:
                nuevo = entrada * (1 - COLCHON)
            if self._mover_stop(br, op, nuevo, "punto de equilibrio"):
                self._ya_movidas[op_id] = R_EQUILIBRIO
                self.app.log(
                    f"[Gestor] {simbolo}: +{avance_r:.1f}R. Stop movido a "
                    f"{nuevo:.2f} (entrada). Esta operación ya no puede "
                    f"perder dinero.")
                try:
                    self.app.decir(
                        f"{simbolo} lleva {avance_r:.1f} erres a favor. He "
                        f"movido el stop al punto de entrada: a partir de "
                        f"ahora esta operación no puede perder.")
                except Exception:
                    pass
                return True

        # ── Trailing a partir de +2R (opcional) ─────────────────────────────
        if (self.usar_trailing and avance_r >= R_TRAILING
                and avance_r > nivel_previo + 0.5):
            avance = abs(precio - entrada)
            if direccion == "COMPRA":
                nuevo = entrada + avance * FRACCION_TRAIL
            else:
                nuevo = entrada - avance * FRACCION_TRAIL
            if self._mover_stop(br, op, nuevo, "seguimiento"):
                self._ya_movidas[op_id] = avance_r
                self.app.log(f"[Gestor] {simbolo}: +{avance_r:.1f}R. Stop "
                             f"sube a {nuevo:.2f}, asegurando parte de la "
                             f"ganancia.")
                return True

        return False

    # ── Mover el stop, con la regla innegociable ────────────────────────────

    def _mover_stop(self, br, op, nuevo: float, motivo: str) -> bool:
        """Mueve el stop SOLO si es a favor. Nunca en contra.

        Esta comprobación es el corazón del módulo. Ampliar un stop porque
        la operación va mal es lo que convierte una pérdida planificada en
        un desastre. Aquí no se puede hacer, ni por error ni a propósito.
        """
        actual = float(op.get("stop") or 0)
        direccion = op.get("direccion", "COMPRA")
        simbolo = op.get("simbolo")

        if direccion == "COMPRA":
            # En una compra, el stop está debajo: solo puede SUBIR
            if nuevo <= actual:
                return False
        else:
            # En una venta, el stop está encima: solo puede BAJAR
            if nuevo >= actual:
                return False

        # Redondeo al tick que acepta IBKR
        try:
            nuevo = round(nuevo, 2) if nuevo >= 1 else round(nuevo, 4)
        except Exception:
            return False

        # Modificar la orden de stop en IBKR
        ok = self._modificar_en_ibkr(br, op, nuevo)
        if not ok:
            self.app.log(f"[Gestor] No pude mover el stop de {simbolo} en "
                         f"IBKR. Lo dejo como estaba: prefiero un stop "
                         f"viejo pero real a uno nuevo que solo existe en "
                         f"mi memoria.")
            return False

        # Solo se actualiza la memoria si IBKR lo aceptó de verdad
        try:
            from . import memoria_acciones as mem_mod
            mem = mem_mod.obtener()
            with mem._lock:
                for o in mem._ops:
                    if o.get("id") == op.get("id"):
                        o["stop_original"] = o.get("stop_original", actual)
                        o["stop"] = nuevo
                        o.setdefault("ajustes", []).append(
                            {"ts": time.strftime("%H:%M:%S"),
                             "de": actual, "a": nuevo, "motivo": motivo})
            mem._guardar()
        except Exception:
            pass

        op["stop"] = nuevo
        return True

    def _modificar_en_ibkr(self, br, op, nuevo: float) -> bool:
        """Cambia el precio de la orden de stop que ya está puesta.

        Busca entre las órdenes abiertas la de tipo STP del símbolo y la
        modifica. Si no la encuentra, NO inventa una nueva: podría acabar
        con dos stops o con uno huérfano.
        """
        simbolo = op.get("simbolo")
        try:
            ib = getattr(br, "_ib", None)
            if ib is None:
                return False
            for trade in (ib.openTrades() or []):
                c = getattr(trade, "contract", None)
                o = getattr(trade, "order", None)
                if c is None or o is None:
                    continue
                if getattr(c, "symbol", "") != simbolo:
                    continue
                if str(getattr(o, "orderType", "")).upper() not in ("STP",
                                                                   "STP LMT"):
                    continue
                o.auxPrice = nuevo
                ib.placeOrder(c, o)      # reenviar = modificar
                ib.sleep(0.5)
                estado = str(trade.orderStatus.status or "")
                if estado in ("Cancelled", "ApiCancelled", "Inactive"):
                    return False
                return True
            return False
        except Exception:
            return False

    # ── Utilidades ──────────────────────────────────────────────────────────

    @staticmethod
    def _precio(br, simbolo) -> float:
        try:
            cot = br.cotizacion(simbolo) or {}
            p = float(cot.get("precio") or 0)
            if p > 0:
                return p
            bid = float(cot.get("bid") or 0)
            ask = float(cot.get("ask") or 0)
            return (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
        except Exception:
            return 0.0

    # ── Informe ─────────────────────────────────────────────────────────────

    def estado(self) -> str:
        try:
            from . import memoria_acciones as mem_mod
            abiertas = [o for o in mem_mod.obtener()._ops if o.get("abierta")]
        except Exception:
            return "No pude leer las posiciones, señor."

        if not abiertas:
            return ("No tengo ninguna posición abierta que gestionar, "
                    "señor.")

        br = getattr(self.app, "broker_ibkr", None)
        lineas = [f"GESTIÓN DE POSICIONES — {len(abiertas)} abierta(s)"]

        for o in abiertas:
            sim = o.get("simbolo")
            ent = float(o.get("entrada") or 0)
            stp = float(o.get("stop") or 0)
            orig = float(o.get("stop_original") or stp)
            riesgo = abs(ent - orig) or 1e-9
            precio = self._precio(br, sim) if br else 0.0

            if precio > 0:
                r = ((precio - ent) if o.get("direccion") == "COMPRA"
                     else (ent - precio)) / riesgo
                estado_r = f"{r:+.2f}R"
            else:
                estado_r = "sin precio"

            protegida = (stp >= ent if o.get("direccion") == "COMPRA"
                         else stp <= ent)
            lineas.append(
                f"  {sim}: entrada {ent:.2f} | stop {stp:.2f} | {estado_r}"
                + ("  ✓ ya no puede perder" if protegida else ""))
            for aj in (o.get("ajustes") or [])[-2:]:
                lineas.append(f"      {aj['ts']} stop {aj['de']:.2f} → "
                              f"{aj['a']:.2f} ({aj['motivo']})")

        lineas.append("")
        lineas.append(f"  Muevo el stop a equilibrio en cuanto la operación "
                      f"llega a +{R_EQUILIBRIO:.0f}R.")
        lineas.append("  El stop nunca se mueve en contra. Eso no es una "
                      "norma que sigo: es algo que el código no me deja "
                      "hacer.")
        return "\n".join(lineas)


# ── Instancia única ─────────────────────────────────────────────────────────

_gestor: GestorPosicion | None = None


def obtener(app) -> GestorPosicion:
    global _gestor
    if _gestor is None:
        _gestor = GestorPosicion(app)
        if not _gestor.is_alive():
            _gestor.start()
    return _gestor


def estado(app) -> str:
    return obtener(app).estado()


def revisar_ahora(app) -> str:
    g = obtener(app)
    n = g.revisar()
    if n:
        return f"Ajusté {n} stop(s), señor.\n\n" + g.estado()
    return g.estado()
