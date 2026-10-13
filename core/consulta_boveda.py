"""
consulta_boveda.py — Litch responde con SU conocimiento, no con teoría.

LA MITAD QUE FALTABA
────────────────────
`boveda_obsidian.py` escribe: Litch vuelca lo que aprende a notas.
Este módulo LEE: Litch busca en esas notas antes de responder.

Sin esta mitad, la bóveda es un archivo muerto — bonito de mirar y sin
efecto sobre lo que Litch hace. Con las dos, el ciclo se cierra:

    Litch aprende  →  lo escribe en la bóveda
                          ↓
                   USTED lo lee y lo corrige
                          ↓
    Litch lo relee  →  responde con lo corregido

Ese tercer paso es el que convierte la bóveda en un cerebro y no en un
diario. Y el segundo es el que hace que sus correcciones importen: si
usted escribe «este setup solo funciona con volumen alto», Litch lo
encontrará la próxima vez que le pregunten por ese setup.

POR QUÉ LAS NOTAS DEL USUARIO PESAN MÁS
───────────────────────────────────────
Cuando una nota tiene texto suyo bajo «Mis notas», ese texto se muestra
PRIMERO y marcado. Usted ha visto el mercado con sus ojos; Litch solo ha
visto números. Ante un desacuerdo, lo que usted anotó merece leerse antes.
"""

from __future__ import annotations

import os
import re
import unicodedata

from .boveda_obsidian import BOVEDA, FIN

MAX_RESULTADOS = 5
MAX_TROZO = 900


# ═══════════════════════════════════════════════════════════════════════════
#  Utilidades de texto
# ═══════════════════════════════════════════════════════════════════════════

def _plano(t: str) -> str:
    """Minúsculas y sin tildes, para que «gráfico» encuentre «grafico»."""
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                   if unicodedata.category(c) != "Mn")


_VACIAS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "que", "y", "o", "a", "en", "con", "por", "para", "es", "son", "su",
    "sus", "al", "lo", "me", "te", "se", "mi", "tu", "como", "cual",
    "cuales", "donde", "cuando", "sobre", "litch", "dime", "dame", "sabes",
    "puedes", "quiero", "necesito", "hay", "esta", "este", "esa", "ese",
}


def _palabras(consulta: str) -> list[str]:
    """Las palabras con contenido de una pregunta."""
    t = _plano(consulta)
    t = re.sub(r"[^\w\s]", " ", t)
    return [p for p in t.split() if len(p) > 2 and p not in _VACIAS]


# ═══════════════════════════════════════════════════════════════════════════
#  Lectura de la bóveda
# ═══════════════════════════════════════════════════════════════════════════

def _notas() -> list[tuple]:
    """Todas las notas: (ruta, carpeta, título, texto de Litch, texto suyo)."""
    salida = []
    if not os.path.isdir(BOVEDA):
        return salida
    for raiz, _dirs, ficheros in os.walk(BOVEDA):
        for f in ficheros:
            if not f.endswith(".md"):
                continue
            ruta = os.path.join(raiz, f)
            try:
                texto = open(ruta, encoding="utf-8").read()
            except Exception:
                continue
            carpeta = os.path.basename(raiz)
            if carpeta == os.path.basename(BOVEDA):
                carpeta = "raíz"
            # Separar lo que escribió Litch de lo que escribió el usuario
            if FIN in texto:
                de_litch, del_usuario = texto.split(FIN, 1)
            else:
                de_litch, del_usuario = texto, ""
            # Limpiar la parte del usuario del texto de relleno
            if "*(Escriba aquí" in del_usuario:
                del_usuario = ""
            salida.append((ruta, carpeta, f[:-3], de_litch, del_usuario))
    return salida


def buscar(consulta: str, limite: int = MAX_RESULTADOS) -> list[dict]:
    """Busca en la bóveda y ordena por relevancia.

    Las notas con texto del usuario suben posiciones: si usted se molestó
    en escribir algo sobre un tema, es porque tenía algo que decir.
    """
    claves = _palabras(consulta)
    if not claves:
        return []

    resultados = []
    for ruta, carpeta, titulo, de_litch, del_usuario in _notas():
        p_titulo = _plano(titulo)
        p_litch = _plano(de_litch)
        p_usuario = _plano(del_usuario)

        punt = 0
        for k in claves:
            if k in p_titulo:
                punt += 10          # el título pesa mucho
            punt += min(p_litch.count(k), 4) * 2
            punt += min(p_usuario.count(k), 4) * 5   # lo suyo pesa más

        if del_usuario.strip():
            punt += 6               # tener nota suya ya es señal

        if punt > 0:
            resultados.append({
                "ruta": ruta, "carpeta": carpeta, "titulo": titulo,
                "punt": punt, "litch": de_litch, "usuario": del_usuario,
            })

    resultados.sort(key=lambda r: -r["punt"])
    return resultados[:limite]


def _extracto(texto: str, claves: list, maximo: int = MAX_TROZO) -> str:
    """El trozo del texto donde de verdad se habla del tema."""
    lineas = [l for l in texto.split("\n")
              if l.strip() and not l.strip().startswith(("---", "<!--",
                                                        "actualizado:",
                                                        "generado-por:"))]
    buenas = []
    for i, l in enumerate(lineas):
        pl = _plano(l)
        if any(k in pl for k in claves):
            ini = max(0, i - 1)
            buenas.extend(lineas[ini:i + 3])
    if not buenas:
        buenas = lineas[:12]

    # Quitar repetidos conservando el orden
    vistas, limpio = set(), []
    for l in buenas:
        if l not in vistas:
            vistas.add(l)
            limpio.append(l)

    txt = "\n".join(limpio)
    return txt[:maximo] + ("…" if len(txt) > maximo else "")


# ═══════════════════════════════════════════════════════════════════════════
#  La respuesta
# ═══════════════════════════════════════════════════════════════════════════

def responder(app, consulta: str) -> str:
    """Responde usando la bóveda. Si no hay nada, lo dice."""
    if not os.path.isdir(BOVEDA):
        return ("Todavía no tengo bóveda, señor. Dígame «actualiza la "
                "bóveda» y la creo con todo lo que sé.")

    res = buscar(consulta)
    if not res:
        return (f"He buscado «{consulta}» en mi bóveda y no encuentro nada, "
                f"señor.\n\n"
                f"Eso puede significar dos cosas: que no lo he aprendido "
                f"todavía, o que lo tengo guardado con otras palabras. "
                f"Pruebe con otro término, o pregúnteme directamente y le "
                f"respondo con lo que sé aunque no esté en las notas.")

    claves = _palabras(consulta)
    partes = [f"Esto es lo que tengo en mi bóveda sobre «{consulta}»:"]

    for r in res:
        partes.append("")
        partes.append(f"━━ {r['titulo']}  ({r['carpeta']})")

        # PRIMERO lo del usuario, y bien marcado
        if r["usuario"].strip():
            nota = r["usuario"].replace("## Mis notas", "").strip()
            if nota:
                partes.append("")
                partes.append("  ✍ NOTA SUYA — la leo antes que lo mío:")
                for l in nota.split("\n"):
                    if l.strip():
                        partes.append(f"     {l.strip()}")

        ext = _extracto(r["litch"], claves)
        if ext:
            partes.append("")
            for l in ext.split("\n"):
                if l.strip():
                    partes.append(f"  {l.strip()}")

    partes.append("")
    partes.append("─" * 50)
    con_nota = sum(1 for r in res if r["usuario"].strip())
    if con_nota:
        partes.append(
            f"Ojo: {con_nota} de estas notas tiene texto suyo. Cuando usted "
            f"y yo no coincidimos, gana usted: yo he visto números, usted ha "
            f"visto el mercado.")
    partes.append("Esto sale de MI memoria, no de teoría general. Si algo "
                  "está mal, corríjalo en Obsidian y lo aprenderé.")
    return "\n".join(partes)


def estado(app=None) -> str:
    """Qué hay en la bóveda ahora mismo."""
    if not os.path.isdir(BOVEDA):
        return ("No tengo bóveda todavía, señor. «actualiza la bóveda» y la "
                "creo.")
    notas = _notas()
    if not notas:
        return "La bóveda existe pero está vacía, señor."

    por_carpeta: dict = {}
    con_nota = []
    for _ruta, carpeta, titulo, _l, usuario in notas:
        por_carpeta[carpeta] = por_carpeta.get(carpeta, 0) + 1
        if usuario.strip():
            con_nota.append(titulo)

    lineas = [f"MI BÓVEDA — {len(notas)} notas"]
    for c, n in sorted(por_carpeta.items(), key=lambda x: -x[1]):
        lineas.append(f"  {c}: {n}")
    lineas.append("")
    if con_nota:
        lineas.append(f"Usted ha escrito en {len(con_nota)} nota(s):")
        for t in con_nota[:8]:
            lineas.append(f"  ✍ {t}")
        lineas.append("")
        lineas.append("Esas las leo con prioridad cuando me pregunta algo "
                      "relacionado.")
    else:
        lineas.append("Todavía no ha escrito ninguna nota suya. Cuando vea "
                      "algo que he aprendido mal, corríjalo bajo «Mis "
                      "notas» y lo tendré en cuenta a partir de entonces.")
    lineas.append("")
    lineas.append("Pregúnteme «según tus notas, ...» y busco aquí antes de "
                  "responder.")
    return "\n".join(lineas)
