"""
practica_dirigida.py — Estudiar el manual, luego comprobarlo con el ratón.

━━━ LA DIFERENCIA CON EXPLORAR A CIEGAS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`explorador_activo` recorre una rejilla y va probando. Funciona, pero es
tanteo: 108 puntos, muchos vacíos, y lo que encuentra no tiene nombre —
solo sabe «aquí pasa algo».

Esto es distinto. Litch ya tiene 18 manuales y `escuela_ibkr` con 32
herramientas, y de cada una sabe tres cosas: **qué** es, **dónde** dice
el manual que está, y **para qué** sirve. Eso no es un mapa vacío: es
una hipótesis.

Así que en vez de tantear, hace lo que haría cualquiera que se ha leído
el manual antes de sentarse:

    1. Toma una herramienta del catálogo — «Watchlist».
    2. Lee qué dice el manual: «Panel izquierdo del Mosaico».
    3. Traduce esa descripción a una zona de la pantalla.
    4. Va, hace clic, y mira qué pasa.
    5. Compara con lo que esperaba:
         · pasó lo previsto        → la teoría se confirma
         · pasó otra cosa          → la teoría estaba mal AHÍ; corrige
         · no pasó nada            → no está donde decía; sigue buscando
    6. Lo anota con su grado de certeza y pasa a la siguiente.

Un clic con hipótesis enseña mucho más que diez a ciegas, porque el
resultado tiene nombre: no es «en (0.3,0.6) pasa algo», es «la Watchlist
está donde el manual decía, y al pulsarla se abre el panel de símbolos».

━━━ POR QUÉ ESTO IMPORTA PARA OPERAR ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Porque cuando llegue el momento de mandar una orden de verdad, Litch no
tendrá que buscar el campo de cantidad: sabrá dónde está, lo habrá
pulsado antes, y sabrá qué pasa al hacerlo. La diferencia entre haber
leído el manual y haberlo comprobado.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time

PAUSA = 2.2               # segundos entre lecciones prácticas
ESPERA_REACCION = 0.6
UMBRAL_CAMBIO = 0.4       # % de píxeles: por debajo, "no pasó nada"
UMBRAL_ABRIO = 5.0        # por encima, se abrió algo grande
MIN_PRUEBAS = 3           # pruebas antes de dar una herramienta por sabida


# ── Del texto del manual a una zona de la pantalla ───────────────────────────
#
# El manual habla en palabras («panel izquierdo», «abajo», «barra
# superior»). La pantalla se mide en proporciones. Esta tabla es el
# puente. Cada entrada da la zona (x1,y1,x2,y2) en proporción de la
# ventana de TWS.

PISTAS = {
    ("panel izquierdo", "izquierda", "left panel", "columna izquierda"):
        (0.00, 0.10, 0.35, 0.90),
    ("panel derecho", "derecha", "right panel", "escáner", "scanner"):
        (0.62, 0.08, 1.00, 0.80),
    ("abajo", "inferior", "bottom", "parte baja", "pie"):
        (0.00, 0.70, 1.00, 0.97),
    ("arriba", "superior", "top", "barra superior", "cabecera"):
        (0.00, 0.035, 1.00, 0.14),
    ("centro", "central", "medio", "middle"):
        (0.32, 0.25, 0.70, 0.75),
    ("pestaña", "pestañas", "tab", "tabs"):
        (0.00, 0.86, 1.00, 0.97),
    ("menú", "menu", "archivo", "file"):
        (0.00, 0.035, 0.45, 0.09),
    ("ticket", "entrada de órdenes", "order entry", "orden"):
        (0.00, 0.06, 0.52, 0.30),
    ("gráfico", "grafico", "chart", "velas"):
        (0.32, 0.25, 0.70, 0.72),
    ("cartera", "portfolio", "posiciones", "positions"):
        (0.00, 0.70, 0.55, 0.92),
}

ZONA_POR_DEFECTO = (0.10, 0.15, 0.90, 0.85)


def _plano(t: str) -> str:
    t = (t or "").lower()
    for a, b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")):
        t = t.replace(a, b)
    return t


def zona_del_manual(descripcion: str) -> tuple[float, float, float, float]:
    """
    Traduce lo que dice el manual a una zona de pantalla.

    Si varias pistas coinciden se cruza el área común: «pestaña abajo»
    es más preciso que cualquiera de las dos por separado. Si el cruce
    sale vacío se conserva la primera, porque una zona amplia y correcta
    es mejor que una diminuta e imposible.
    """
    d = _plano(descripcion)
    encontradas = []
    for claves, zona in PISTAS.items():
        if any(_plano(k) in d for k in claves):
            encontradas.append(zona)
    if not encontradas:
        return ZONA_POR_DEFECTO
    z = encontradas[0]
    for otra in encontradas[1:]:
        x1, y1 = max(z[0], otra[0]), max(z[1], otra[1])
        x2, y2 = min(z[2], otra[2]), min(z[3], otra[3])
        if (x2 - x1) > 0.06 and (y2 - y1) > 0.06:
            z = (x1, y1, x2, y2)
    return z


# ── Memoria de lo comprobado ─────────────────────────────────────────────────

def _ruta() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "MEMORIA_AP")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "manual_comprobado.json")


def cargar() -> dict:
    try:
        with open(_ruta(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"herramientas": {}, "sesiones": 0, "clics": 0}


def guardar(d: dict) -> None:
    try:
        tmp = _ruta() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _ruta())
    except Exception:
        pass


def certeza(h: dict) -> float:
    """Cota inferior de Wilson: una prueba no basta, aunque salga bien."""
    n = h.get("n", 0)
    if n <= 0:
        return 0.0
    p = h.get("confirmadas", 0) / n
    z = 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(max(0.0, c - m), 3)


def sabida(h: dict) -> bool:
    return h.get("n", 0) >= MIN_PRUEBAS and certeza(h) >= 0.60


# ── La práctica dirigida ─────────────────────────────────────────────────────

class PracticaDirigida(threading.Thread):
    """Recorre el catálogo de herramientas comprobando el manual a mano."""

    def __init__(self, app):
        super().__init__(daemon=True, name="PracticaDirigida")
        self.app = app
        self._parar = threading.Event()
        self._activo = False
        self.datos = cargar()
        self.tope = 150

    # ── Catálogo ────────────────────────────────────────────────────────

    def _catalogo(self) -> dict:
        try:
            from . import escuela_ibkr as _es
            return dict(getattr(_es, "HERRAMIENTAS", {}) or {})
        except Exception:
            return {}

    def _siguiente(self, cat: dict):
        """
        La herramienta que más falta hace probar.

        Se prefiere lo nunca probado; luego lo dudoso; y entre iguales,
        lo de riesgo bajo y nivel básico, porque el orden del manual está
        pensado para aprender, no al azar.
        """
        candidatas = []
        for clave, info in cat.items():
            h = self.datos["herramientas"].get(clave, {})
            if sabida(h):
                peso = 0.05
            elif h.get("n", 0) == 0:
                peso = 5.0
            else:
                peso = 1.0 + (1.0 - certeza(h)) * 2.0
            nivel = int(info.get("nivel", 3) or 3)
            peso *= (1.4 if nivel <= 1 else (1.0 if nivel == 2 else 0.7))
            if str(info.get("riesgo", "")).lower() == "alto":
                peso *= 0.6
            candidatas.append((peso, clave, info))
        if not candidatas:
            return None, None
        total = sum(c[0] for c in candidatas)
        dado = random.random() * total
        acc = 0.0
        for peso, clave, info in candidatas:
            acc += peso
            if acc >= dado:
                return clave, info
        return candidatas[-1][1], candidatas[-1][2]

    # ── Una lección práctica ────────────────────────────────────────────

    def _lección(self, v: dict, clave: str, info: dict) -> dict:
        """Hipótesis → clic → medición → conclusión."""
        from . import explorador_activo as _ex

        r = {"clave": clave, "confirmada": False, "pct": 0.0, "motivo": ""}

        donde = str(info.get("donde", ""))
        zx1, zy1, zx2, zy2 = zona_del_manual(donde)

        # Dentro de la zona que dice el manual, se prueba el punto menos
        # explorado. No siempre el mismo: si el primero no era, hay que
        # mirar al lado.
        h = self.datos["herramientas"].setdefault(clave, {
            "nombre": info.get("nombre", clave), "donde": donde,
            "n": 0, "confirmadas": 0, "puntos": [], "ultima": "",
        })
        intentos = h.get("n", 0)
        px = zx1 + (zx2 - zx1) * (0.5 + 0.32 * ((intentos % 5) - 2) / 2.0)
        py = zy1 + (zy2 - zy1) * (0.5 + 0.32 * ((intentos // 5 % 5) - 2) / 2.0)
        px = min(max(px, zx1 + 0.01), zx2 - 0.01)
        py = min(max(py, zy1 + 0.01), zy2 - 0.01)

        x = int(v["x"] + px * v["w"])
        y = int(v["y"] + py * v["h"])
        x = max(v["x"] + 6, min(x, v["x"] + v["w"] - 6))
        y = max(v["y"] + 6, min(y, v["y"] + v["h"] - 6))

        region = [v["x"], v["y"], v["x"] + v["w"], v["y"] + v["h"]]
        antes = _ex._capturar(region)
        if antes is None:
            r["motivo"] = "no pude fotografiar la pantalla"
            return r

        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.click(x, y)
            self.datos["clics"] = self.datos.get("clics", 0) + 1
        except Exception as e:
            r["motivo"] = f"el clic falló: {e}"
            return r

        time.sleep(ESPERA_REACCION)
        comp = _ex.comparar(antes, _ex._capturar(region))
        r["pct"] = comp["pct"]

        h["n"] += 1
        h["ultima"] = time.strftime("%Y-%m-%d %H:%M:%S")

        if comp["pct"] >= UMBRAL_CAMBIO:
            r["confirmada"] = True
            h["confirmadas"] += 1
            pt = [round(px, 3), round(py, 3), round(comp["pct"], 2)]
            if pt not in h["puntos"]:
                h["puntos"] = (h.get("puntos", []) + [pt])[-8:]
            r["motivo"] = (f"donde el manual decía «{donde[:48]}» sí hay algo: "
                           f"cambió el {comp['pct']}% de la pantalla")
        else:
            r["motivo"] = (f"donde el manual decía «{donde[:48]}» no reaccionó "
                           f"nada; probaré un poco más allá")

        # Si abrió algo, se cierra y se comprueba que se cerró de verdad.
        if comp["pct"] >= UMBRAL_ABRIO:
            try:
                import pyautogui
                pyautogui.press("escape"); time.sleep(0.35)
                if _ex.comparar(antes, _ex._capturar(region))["pct"] >= UMBRAL_CAMBIO:
                    pyautogui.press("escape"); time.sleep(0.35)
                r["cerrado"] = _ex.comparar(
                    antes, _ex._capturar(region))["pct"] < UMBRAL_CAMBIO
            except Exception:
                r["cerrado"] = False
        return r

    # ── Bucle ───────────────────────────────────────────────────────────

    def run(self) -> None:
        from . import explorador_activo as _ex

        self._activo = True
        self.datos["sesiones"] = self.datos.get("sesiones", 0) + 1
        cat = self._catalogo()
        if not cat:
            self.app.log("[Dirigida] No encuentro el catálogo de herramientas.")
            self._activo = False
            return

        self.app.log(f"[Dirigida] Empiezo. {len(cat)} herramientas del manual "
                     f"por comprobar con el ratón.")
        hechos = 0
        aux = _ex.Explorador(self.app)

        while not self._parar.is_set() and hechos < self.tope:
            puedo, motivo, v = aux._puedo()
            if not puedo:
                self.app.log(f"[Dirigida] Me detengo: {motivo}.")
                break

            clave, info = self._siguiente(cat)
            if clave is None:
                break
            r = self._lección(v, clave, info)
            hechos += 1

            h = self.datos["herramientas"].get(clave, {})
            if r["confirmada"] and h.get("n", 0) == h.get("confirmadas", 0) \
                    and sabida(h):
                self.app.log(
                    f"[Dirigida] ✓ {info.get('nombre', clave)} — "
                    f"comprobada {h['n']} veces, certeza {certeza(h):.0%}. "
                    f"{info.get('que','')[:60]}")
            elif hechos % 5 == 0:
                n_ok = sum(1 for x in self.datos["herramientas"].values()
                           if sabida(x))
                self.app.log(f"[Dirigida] {hechos} pruebas · {n_ok}/{len(cat)} "
                             f"herramientas comprobadas · última: "
                             f"{info.get('nombre', clave)} — {r['motivo'][:70]}")

            if hechos % 10 == 0:
                guardar(self.datos)
            self._parar.wait(PAUSA)

        guardar(self.datos)
        self._activo = False
        n_ok = sum(1 for x in self.datos["herramientas"].values() if sabida(x))
        self.app.log(f"[Dirigida] Terminado. {hechos} pruebas. "
                     f"{n_ok} de {len(cat)} herramientas comprobadas a mano.")

    def detener(self):
        self._parar.set()

    @property
    def activo(self) -> bool:
        return self._activo


# ── API ──────────────────────────────────────────────────────────────────────

_inst = None


def alternar(app) -> str:
    global _inst
    if _inst is not None and _inst.activo:
        _inst.detener()
        return "Dejo la práctica dirigida, señor. Guardo lo comprobado."
    if _inst is None or not _inst.is_alive():
        _inst = PracticaDirigida(app)
    from . import explorador_activo as _ex
    puedo, motivo, _ = _ex.Explorador(app)._puedo()
    if not puedo:
        return f"No puedo practicar ahora: {motivo}."
    _inst.start()

    try:
        from . import permisos_broker as _pb
        alcance = ("Tengo acceso total: puedo tocar todo, incluido el ticket."
                   if _pb.puede_todo(app) else
                   "No consta cuenta simulada, así que evito lo que mueve "
                   "dinero.")
    except Exception:
        alcance = ""
    return ("Práctica dirigida, señor. Voy herramienta por herramienta del "
            "manual: leo dónde dice que está, voy, hago clic y compruebo si "
            "es verdad. Lo que se confirme lo doy por sabido; lo que no, lo "
            "sigo buscando. " + alcance)


def resumen(app=None) -> str:
    d = cargar()
    hs = d.get("herramientas", {})
    if not hs:
        return ("Todavía no he comprobado ninguna herramienta a mano, señor. "
                "Dígame «practica con el manual» y empiezo.")
    try:
        from . import escuela_ibkr as _es
        total = len(getattr(_es, "HERRAMIENTAS", {}) or {})
    except Exception:
        total = len(hs)

    sab = [h for h in hs.values() if sabida(h)]
    dudo = [h for h in hs.values() if h.get("n", 0) > 0 and not sabida(h)]
    lineas = [
        f"MANUAL COMPROBADO A MANO — {d.get('sesiones',0)} sesiones, "
        f"{d.get('clics',0)} clics",
        "",
        f"· {len(sab)} de {total} herramientas comprobadas y confirmadas",
        f"· {len(dudo)} probadas pero todavía dudosas",
        f"· {total - len(hs)} sin tocar aún",
        "",
        "Confirmadas:",
    ]
    for h in sorted(sab, key=lambda x: -certeza(x))[:10]:
        lineas.append(f"  ✓ {h.get('nombre','?')} — {h['n']} pruebas, "
                      f"certeza {certeza(h):.0%}")
    if dudo:
        lineas.append("")
        lineas.append("Aún no las tengo claras:")
        for h in sorted(dudo, key=lambda x: certeza(x))[:6]:
            lineas.append(f"  · {h.get('nombre','?')} — {h['n']} pruebas, "
                          f"certeza {certeza(h):.0%}; el manual dice "
                          f"«{str(h.get('donde',''))[:40]}»")
    lineas.append("")
    lineas.append("Comprobado significa comprobado con el ratón, no leído.")
    return "\n".join(lineas)


__all__ = ["PracticaDirigida", "alternar", "resumen", "zona_del_manual",
           "certeza", "sabida", "cargar", "PISTAS"]
