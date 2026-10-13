"""
mapa_codigo.py — El código de Litch, documentado en la bóveda.

PARA QUÉ SIRVE ESTO (y para qué NO)
───────────────────────────────────
SIRVE para que cuando usted —o yo en otra sesión— quiera mejorar algo, no
haya que leerse 111 archivos para saber dónde tocar. Se abre la bóveda, se
mira el mapa, y se va directo.

NO SIRVE para que Litch opere mejor. Esto es documentación: se escribe
cuando usted lo pide y no interviene en ninguna decisión de trading. Que
quede claro, porque es fácil confundir «tengo un mapa bonito del código»
con «mi IA es más lista».

QUÉ GENERA
──────────
  · Una nota por módulo: qué hace, qué expone, de qué depende
  · Un mapa de dependencias — qué se rompe si toco esto
  · La separación IQ Option / IBKR / común, que es la que importa ahora
  · Un índice para llegar a cualquier parte sin buscar

CÓMO DECIDE A QUÉ BROKER PERTENECE CADA MÓDULO
──────────────────────────────────────────────
Por lo que el propio código menciona. No es infalible, y donde dude lo
dice en vez de inventarse una clasificación.
"""

from __future__ import annotations

import ast
import os
import time

from .boveda_obsidian import BOVEDA, _escribir, _limpiar, _preparar

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CARPETA = "Codigo"

# Pistas para clasificar cada módulo por broker
_PISTAS_IQ = ("iqoption", "iq_option", "iq option", "binaria", "payout",
              "vencimiento", "boton_verde", "boton_rojo", "broker_iq")
_PISTAS_IBKR = ("ibkr", "interactive", "tws", "ib_async", "ib_insync",
                "bracket", "7497", "7496", "paper trading")


def _clasificar(nombre: str, fuente: str) -> tuple:
    """¿Este módulo es de IQ Option, de IBKR, o de los dos?"""
    f = fuente.lower()
    n_iq = sum(f.count(p) for p in _PISTAS_IQ)
    n_ib = sum(f.count(p) for p in _PISTAS_IBKR)

    if n_iq == 0 and n_ib == 0:
        return "comun", "ninguno de los dos brokers se menciona"
    if n_ib > n_iq * 2:
        return "ibkr", f"{n_ib} menciones a IBKR frente a {n_iq} a IQ"
    if n_iq > n_ib * 2:
        return "iq", f"{n_iq} menciones a IQ frente a {n_ib} a IBKR"
    return "mixto", f"{n_iq} menciones a IQ y {n_ib} a IBKR"


def _analizar(ruta: str) -> dict | None:
    """Lee un archivo y saca su estructura."""
    try:
        fuente = open(ruta, encoding="utf-8", errors="replace").read()
        arbol = ast.parse(fuente)
    except Exception:
        return None

    nombre = os.path.basename(ruta)[:-3]
    doc = (ast.get_docstring(arbol) or "").strip()

    funciones, clases, importa = [], [], set()

    for n in arbol.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not n.name.startswith("_"):
                funciones.append((n.name,
                                  (ast.get_docstring(n) or "").split("\n")[0]))
        elif isinstance(n, ast.ClassDef):
            metodos = [m.name for m in n.body
                       if isinstance(m, ast.FunctionDef)
                       and not m.name.startswith("_")]
            clases.append((n.name,
                           (ast.get_docstring(n) or "").split("\n")[0],
                           metodos))

    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.level:      # from . import X
            for a in n.names:
                importa.add(a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                b = a.name.split(".")[-1]
                if b not in ("os", "sys", "time", "json", "re", "math",
                             "threading", "random", "typing", "ast"):
                    importa.add(b)

    broker, motivo = _clasificar(nombre, fuente)

    return {
        "nombre": nombre, "ruta": ruta, "doc": doc,
        "lineas": fuente.count("\n") + 1,
        "funciones": funciones, "clases": clases,
        "importa": sorted(importa),
        "broker": broker, "motivo_broker": motivo,
    }


def _archivos() -> list:
    """Todos los .py del proyecto, sin entrar en carpetas de terceros."""
    salida = []
    for f in ("litch.py", "verificar.py", "probar_ibkr.py",
              "conexion_ibkr.py", "bandeja.py"):
        p = os.path.join(_RAIZ, f)
        if os.path.exists(p):
            salida.append(p)
    core = os.path.join(_RAIZ, "core")
    if os.path.isdir(core):
        for f in sorted(os.listdir(core)):
            if f.endswith(".py") and f != "__init__.py":
                salida.append(os.path.join(core, f))
    return salida


# ═══════════════════════════════════════════════════════════════════════════
#  Generación
# ═══════════════════════════════════════════════════════════════════════════

_ETIQ = {"iq": "broker-iq", "ibkr": "broker-ibkr",
         "mixto": "broker-mixto", "comun": "comun"}

_TITULO = {"iq": "IQ Option (opciones binarias)",
           "ibkr": "Interactive Brokers (acciones)",
           "mixto": "Los dos brokers",
           "comun": "Común (no depende del broker)"}


def generar(app=None) -> str:
    """Escribe el mapa del código completo en la bóveda."""
    _preparar()
    try:
        os.makedirs(os.path.join(BOVEDA, CARPETA), exist_ok=True)
    except Exception:
        pass

    modulos = []
    for ruta in _archivos():
        d = _analizar(ruta)
        if d:
            modulos.append(d)

    if not modulos:
        return "No pude leer ningún archivo de código, señor."

    # Quién usa a quién (para saber qué se rompe al tocar algo)
    usado_por: dict = {}
    for m in modulos:
        for dep in m["importa"]:
            usado_por.setdefault(dep, []).append(m["nombre"])

    # ── Una nota por módulo ─────────────────────────────────────────────────
    for m in modulos:
        cuerpo = []
        etiq_broker = _ETIQ[m["broker"]]

        cuerpo.append(f"> **{_TITULO[m['broker']]}** · {m['lineas']} líneas")
        cuerpo.append("")
        cuerpo.append(f"`{os.path.relpath(m['ruta'], _RAIZ)}`")
        cuerpo.append("")

        if m["doc"]:
            cuerpo.append("## Qué hace")
            cuerpo.append("")
            # Solo el primer bloque del docstring: lo demás es detalle
            primero = m["doc"].split("\n\n")[0]
            cuerpo.append(primero)
            cuerpo.append("")

        if m["clases"]:
            cuerpo.append("## Clases")
            cuerpo.append("")
            for nom, doc, met in m["clases"]:
                cuerpo.append(f"**`{nom}`** — {doc or 'sin descripción'}")
                if met:
                    cuerpo.append(f"  · métodos: {', '.join(met[:10])}")
                cuerpo.append("")

        if m["funciones"]:
            cuerpo.append("## Funciones públicas")
            cuerpo.append("")
            for nom, doc in m["funciones"][:25]:
                cuerpo.append(f"- **`{nom}()`** — {doc or '—'}")
            if len(m["funciones"]) > 25:
                cuerpo.append(f"- *(y {len(m['funciones']) - 25} más)*")
            cuerpo.append("")

        # Dependencias, en las dos direcciones
        cuerpo.append("## De qué depende")
        cuerpo.append("")
        propios = [d for d in m["importa"]
                   if any(x["nombre"] == d for x in modulos)]
        externos = [d for d in m["importa"] if d not in propios]
        if propios:
            cuerpo.append("Módulos de Litch: "
                          + ", ".join(f"[[cod-{d}|{d}]]" for d in propios))
        if externos:
            cuerpo.append(f"Librerías externas: {', '.join(externos)}")
        if not m["importa"]:
            cuerpo.append("No depende de nada. Es una pieza suelta.")
        cuerpo.append("")

        quien = usado_por.get(m["nombre"], [])
        cuerpo.append("## Quién lo usa")
        cuerpo.append("")
        if quien:
            cuerpo.append(f"**{len(quien)} módulo(s)**: "
                          + ", ".join(f"[[cod-{q}|{q}]]" for q in sorted(quien)))
            cuerpo.append("")
            if len(quien) >= 5:
                cuerpo.append(f"> ⚠ Lo usan {len(quien)} módulos. Un cambio "
                              f"aquí se propaga lejos: pruebe bien antes de "
                              f"tocarlo.")
        else:
            cuerpo.append("Nadie lo importa. O es un punto de entrada, o "
                          "quedó sin usar.")
        cuerpo.append("")
        cuerpo.append("---")
        cuerpo.append("")
        cuerpo.append(f"Clasificación de broker: *{m['motivo_broker']}*")
        cuerpo.append("")
        cuerpo.append("Ver [[Mapa del código]] · [[00 Índice]]")

        _escribir(CARPETA, f"cod-{m['nombre']}", "\n".join(cuerpo),
                  ["codigo", etiq_broker])

    # ── El mapa general ─────────────────────────────────────────────────────
    por_broker: dict = {"ibkr": [], "iq": [], "mixto": [], "comun": []}
    for m in modulos:
        por_broker[m["broker"]].append(m)

    total_lineas = sum(m["lineas"] for m in modulos)

    mapa = [
        f"> {len(modulos)} módulos · {total_lineas:,} líneas",
        "",
        "Esto es el plano del código de Litch. Sirve para saber **dónde "
        "tocar** cuando queramos mejorar algo, sin tener que leerlo todo.",
        "",
        "## La transición que estamos haciendo",
        "",
        "Litch nació para IQ Option (opciones binarias) y ahora opera "
        "Interactive Brokers (acciones). Son juegos distintos, así que "
        "conviene ver qué parte del código pertenece a cada uno:",
        "",
        "| Grupo | Módulos | Líneas |",
        "|---|---|---|",
    ]
    for k in ("ibkr", "iq", "mixto", "comun"):
        ms = por_broker[k]
        if ms:
            mapa.append(f"| {_TITULO[k]} | {len(ms)} | "
                        f"{sum(x['lineas'] for x in ms):,} |")

    mapa.append("")
    mapa.append("> El conocimiento de IQ Option **no se borra**. Lo que "
                "Litch aprendió de leer velas, reconocer estructura y "
                "gestionar rachas sigue sirviendo: lo que cambia es cómo se "
                "ejecuta y cómo se sale, no cómo se lee un gráfico.")
    mapa.append("")

    for k in ("ibkr", "iq", "mixto", "comun"):
        ms = sorted(por_broker[k], key=lambda x: -x["lineas"])
        if not ms:
            continue
        mapa.append(f"## {_TITULO[k]}")
        mapa.append("")
        for m in ms:
            n_usa = len(usado_por.get(m["nombre"], []))
            aviso = " ⚠" if n_usa >= 5 else ""
            resumen = (m["doc"].split("\n")[0][:70] if m["doc"] else "—")
            mapa.append(f"- [[cod-{m['nombre']}|{m['nombre']}]]{aviso} "
                        f"({m['lineas']} L) — {resumen}")
        mapa.append("")

    # Los más críticos
    criticos = sorted(usado_por.items(), key=lambda kv: -len(kv[1]))[:8]
    mapa.append("## Los que más se usan (cuidado al tocarlos)")
    mapa.append("")
    for nom, quien in criticos:
        if any(m["nombre"] == nom for m in modulos):
            mapa.append(f"- [[cod-{nom}|{nom}]] — lo usan {len(quien)} módulos")
    mapa.append("")
    mapa.append("---")
    mapa.append("")
    mapa.append(f"*Generado el {time.strftime('%Y-%m-%d %H:%M')}. "
                f"«Litch, mapea el código» para actualizarlo.*")

    _escribir(CARPETA, "Mapa del código", "\n".join(mapa),
              ["codigo", "indice", "arquitectura"])

    n_ib = len(por_broker["ibkr"])
    n_iq = len(por_broker["iq"])
    return (
        f"Código mapeado en la bóveda, señor.\n\n"
        f"  {len(modulos)} módulos · {total_lineas:,} líneas\n"
        f"  {n_ib} de Interactive Brokers\n"
        f"  {n_iq} de IQ Option\n"
        f"  {len(por_broker['mixto'])} que tocan los dos\n"
        f"  {len(por_broker['comun'])} independientes del broker\n\n"
        f"Está en la carpeta Codigo. Empiece por «Mapa del código».\n\n"
        f"Le sirve para saber dónde tocar cuando quiera mejorar algo. Los "
        f"módulos marcados con ⚠ los usan cinco o más: un cambio ahí se "
        f"propaga lejos.\n\n"
        f"Aviso honesto: esto NO hace a Litch más rápido ni más listo. Es "
        f"documentación, y solo se lee cuando usted o yo la abrimos."
    )
