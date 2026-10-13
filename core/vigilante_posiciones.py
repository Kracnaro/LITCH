"""
vigilante_posiciones.py — Litch cierra el círculo del aprendizaje.

EL PROBLEMA QUE RESUELVE
────────────────────────
Litch anotaba cada operación al abrirla y nunca anotaba el resultado. El
método `cerrar()` de la memoria existía, pero no lo llamaba nadie.

Eso rompe el aprendizaje de raíz: si ninguna operación se cierra, ningún
setup acumula historial, y `veredicto_setup` nunca puede decir «este ya me
salió mal tres veces». La memoria se llena de operaciones eternamente
abiertas y no aprende absolutamente nada.

Una IA que registra lo que hace pero no lo que le pasó después no está
aprendiendo: está llevando un diario que nadie lee.

QUÉ HACE
────────
Cada minuto compara lo que la memoria cree abierto con lo que IBKR dice que
está abierto de verdad. Cuando una posición desaparece de IBKR:

  1. Averigua a qué precio salió (por las ejecuciones reales de IBKR,
     que es la única fuente exacta).
  2. Calcula el resultado en R (múltiplos de riesgo), no en dólares.
  3. Lo anota como cerrada, con su motivo.
  4. Se lo cuenta al usuario.
  5. A partir de ahí ese setup ya cuenta para bien o para mal.

POR QUÉ EN R Y NO EN DÓLARES
────────────────────────────
Ganar 50 dólares no significa nada si no se sabe cuánto se arriesgó. Un R
es «lo que estaba dispuesto a perder». Ganar 2R con 20 dólares de riesgo y
ganar 2R con 200 son la misma decisión bien tomada. Medir en R es lo que
permite comparar operaciones de distinto tamaño y saber si el MÉTODO
funciona, independientemente de cuánto dinero había en juego.
"""

from __future__ import annotations

import threading
import time

INTERVALO = 60          # revisar cada minuto
MARGEN_PRECIO = 0.004   # 0.4% de tolerancia al identificar la salida


class VigilantePosiciones(threading.Thread):
    """Detecta cierres, calcula el resultado y hace que Litch aprenda."""

    def __init__(self, app):
        super().__init__(daemon=True, name="LitchVigilantePos")
        self.app = app
        self._parar = threading.Event()
        self.activo = True
        self._vistas: set = set()      # símbolos que IBKR reportó abiertos
        # Bandera aparte, NO "¿está vacío el conjunto?".
        # Un set() vacío es falso en Python, así que usar el propio
        # conjunto como marca de «ya arranqué» hacía que la lógica de
        # primera vuelta se re-disparara cada vez que no había ninguna
        # posición abierta — y entonces no cerraba nunca la última.
        self._arrancado = False
        self._cierres = 0

    def parar(self):
        self._parar.set()

    # ── Bucle ───────────────────────────────────────────────────────────────

    def run(self):
        self._parar.wait(45)
        while not self._parar.is_set():
            if self.activo:
                try:
                    self.revisar()
                except Exception as e:
                    try:
                        self.app.log(f"[Vigilante] {e}")
                    except Exception:
                        pass
            self._parar.wait(INTERVALO)

    # ── El trabajo ──────────────────────────────────────────────────────────

    def revisar(self) -> int:
        """Compara memoria con IBKR y cierra lo que ya no está. Devuelve
        cuántas operaciones cerró."""
        br = getattr(self.app, "broker_ibkr", None)
        if br is None or not getattr(br, "esta_conectado", False):
            return 0

        from . import memoria_acciones as mem_mod
        mem = mem_mod.obtener()

        # Lo que la memoria cree que sigue abierto
        try:
            abiertas = [o for o in mem._ops if o.get("abierta")]
        except Exception:
            return 0
        if not abiertas:
            return 0

        # Lo que IBKR dice de verdad
        try:
            posiciones = br.posiciones() or []
        except Exception:
            return 0
        vivos = {p.get("simbolo") for p in posiciones
                 if p.get("cantidad")}

        # Primera vuelta: solo aprender el estado, sin concluir nada.
        # Si Litch arranca con posiciones ya abiertas, no debe creer que
        # acaban de cerrarse.
        if not self._arrancado:
            self._arrancado = True
            self._vistas = vivos | {o["simbolo"] for o in abiertas}
            return 0

        cerradas = 0
        for op in list(abiertas):
            simbolo = op.get("simbolo")
            if simbolo in vivos:
                continue      # sigue abierta, nada que hacer

            # Estaba abierta y ya no está: se cerró.
            precio, motivo = self._precio_de_salida(br, op)
            if precio is None:
                continue      # sin precio fiable, mejor esperar otra vuelta

            res = mem.cerrar(op["id"], precio, motivo)
            if res:
                cerradas += 1
                self._cierres += 1
                self._contar(res)

        self._vistas = vivos

        # Tras cada cierre hay que recontar los day trades: una operación
        # abierta y cerrada el mismo día cuenta para la regla PDT, aunque
        # nadie pretendiera hacer day trading.
        if cerradas:
            try:
                from . import guardia_pdt as pdt
                pdt.revisar_cierres(self.app)
            except Exception:
                pass

        return cerradas

    # ── ¿A qué precio salió? ────────────────────────────────────────────────

    def _precio_de_salida(self, br, op) -> tuple:
        """El precio real de salida, por orden de fiabilidad.

        1. Las ejecuciones (fills) de IBKR — es el dato exacto.
        2. Si no hay, se deduce por cuál de los dos precios está más cerca
           del último precio de mercado: el stop o el objetivo.

        Si ninguna de las dos da algo creíble, devuelve None y se espera.
        Inventar un precio de salida corrompería la memoria para siempre,
        y una memoria corrompida es peor que no tener memoria.
        """
        simbolo = op.get("simbolo")

        # 1) Ejecuciones reales
        try:
            ib = getattr(br, "_ib", None)
            if ib is not None:
                fills = [f for f in (ib.fills() or [])
                         if getattr(f.contract, "symbol", "") == simbolo]
                if fills:
                    ult = fills[-1]
                    px = float(getattr(ult.execution, "price", 0) or 0)
                    if px > 0:
                        return px, "ejecución real de IBKR"
        except Exception:
            pass

        # 2) Deducir por cercanía al último precio
        try:
            # La clave es "precio" (comprobado en broker_ibkr.cotizacion).
            # Si falta, se prueba el punto medio entre compra y venta.
            cot = br.cotizacion(simbolo) or {}
            ultimo = float(cot.get("precio") or 0)
            if ultimo <= 0:
                bid = float(cot.get("bid") or 0)
                ask = float(cot.get("ask") or 0)
                if bid > 0 and ask > 0:
                    ultimo = (bid + ask) / 2
        except Exception:
            ultimo = 0.0

        if ultimo <= 0:
            return None, ""

        stop = float(op.get("stop") or 0)
        objetivo = float(op.get("objetivo") or 0)
        if stop <= 0 or objetivo <= 0:
            return None, ""

        d_stop = abs(ultimo - stop) / max(stop, 1e-9)
        d_obj = abs(ultimo - objetivo) / max(objetivo, 1e-9)

        if d_stop <= MARGEN_PRECIO and d_stop < d_obj:
            return stop, "saltó el stop (deducido por el precio)"
        if d_obj <= MARGEN_PRECIO and d_obj < d_stop:
            return objetivo, "llegó al objetivo (deducido por el precio)"

        # Ni cerca del stop ni del objetivo: se cerró por otra vía
        # (a mano, o el mercado saltó). Se usa el último precio, y se
        # dice claramente que es una aproximación.
        return ultimo, "cierre fuera del bracket (precio aproximado)"

    # ── Contarlo bien ───────────────────────────────────────────────────────

    def _contar(self, op: dict):
        """Cuenta el resultado sin dramatizar ni celebrar de más."""
        r = float(op.get("r_multiplo", 0))
        simbolo = op.get("simbolo", "?")
        gano = r > 0

        if gano:
            texto = (f"Cerrada {simbolo} en ganancia: +{r:.2f}R "
                     f"({op.get('motivo_cierre','')}).")
        else:
            texto = (f"Cerrada {simbolo} en pérdida: {r:.2f}R "
                     f"({op.get('motivo_cierre','')}).")

        # Lo que de verdad importa: qué aprende de esto
        try:
            from . import memoria_acciones as mem_mod
            ver = mem_mod.obtener().veredicto_setup(
                simbolo, op.get("direccion", ""), op.get("contexto", {}))
            n = ver.get("n", 0)
            if n >= 6:
                texto += (f" Este tipo de entrada lleva {n} operaciones "
                          f"con {ver.get('wr', 0):.0f}% de acierto y "
                          f"{ver.get('r_medio', 0):+.2f}R de media.")
            else:
                texto += (f" Llevo {n} operaciones de este tipo: todavía "
                          f"muy pocas para sacar conclusiones.")
        except Exception:
            pass

        self.app.log("[Vigilante] " + texto)
        try:
            if gano:
                self.app.decir(f"Cerró {simbolo} con ganancia, "
                               f"{r:.1f} erres.")
            else:
                # Una pérdida con stop es el sistema funcionando, no un
                # fracaso. Conviene decirlo así, sin dramatizar.
                self.app.decir(f"Cerró {simbolo} con pérdida de "
                               f"{abs(r):.1f} erres. El stop hizo su "
                               f"trabajo: la pérdida quedó donde debía.")
        except Exception:
            pass

    # ── Informe ─────────────────────────────────────────────────────────────

    def resumen(self) -> str:
        try:
            from . import memoria_acciones as mem_mod
            mem = mem_mod.obtener()
            ops = list(mem._ops)
        except Exception:
            return "No pude leer la memoria de operaciones, señor."

        cerradas = [o for o in ops if not o.get("abierta")]
        abiertas = [o for o in ops if o.get("abierta")]

        if not cerradas:
            return (f"Todavía no se ha cerrado ninguna operación de acciones, "
                    f"señor. Tengo {len(abiertas)} abierta(s) y las vigilo "
                    f"cada minuto. Cuando se cierren aprenderé de ellas.")

        wins = [o for o in cerradas if o.get("resultado") == "WIN"]
        rs = [float(o.get("r_multiplo", 0)) for o in cerradas]
        total_r = sum(rs)
        n = len(cerradas)
        wr = 100.0 * len(wins) / n

        lineas = [
            f"OPERACIONES DE ACCIONES — {n} cerradas, "
            f"{len(abiertas)} abiertas",
            f"  Acierto: {wr:.0f}% ({len(wins)} de {n})",
            f"  Resultado acumulado: {total_r:+.2f}R",
            f"  Media por operación: {total_r / n:+.2f}R",
        ]

        # La honestidad estadística importa más que el número bonito
        if n < 30:
            lineas.append(f"  ⚠ Con {n} operaciones esto todavía no "
                          f"significa gran cosa. Hacen falta unas 30 para "
                          f"empezar a distinguir método de suerte.")
        elif total_r > 0:
            lineas.append("  Con esta muestra el método va en positivo. "
                          "Sigue sin ser garantía de nada futuro.")
        else:
            lineas.append("  Con esta muestra el método va en negativo. "
                          "Merece la pena revisar qué setups fallan antes "
                          "de seguir.")

        ult = cerradas[-3:]
        if ult:
            lineas.append("  Últimas:")
            for o in ult:
                lineas.append(f"    {o.get('simbolo')} "
                              f"{o.get('r_multiplo', 0):+.2f}R "
                              f"— {o.get('motivo_cierre', '')}")
        return "\n".join(lineas)


# ── Instancia única ─────────────────────────────────────────────────────────

_vig: VigilantePosiciones | None = None


def obtener(app) -> VigilantePosiciones:
    global _vig
    if _vig is None:
        _vig = VigilantePosiciones(app)
        if not _vig.is_alive():
            _vig.start()
    return _vig


def resumen(app) -> str:
    return obtener(app).resumen()


def revisar_ahora(app) -> str:
    v = obtener(app)
    n = v.revisar()
    if n:
        return f"Cerré {n} operación(es) y aprendí de ellas, señor."
    return ("Nada nuevo que cerrar, señor. " + v.resumen())
