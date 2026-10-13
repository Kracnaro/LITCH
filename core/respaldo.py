"""Respaldo de Litch en varias cuentas de nube TUYAS.

Cómo funciona, sin servidor ni hacks:
TeraBox, Google Drive, Dropbox y OneDrive tienen una APP DE ESCRITORIO que
crea una carpeta local sincronizada con tu cuenta. Tú instalas esa app,
inicias sesión con uno de tus correos y obtienes una carpeta (por ejemplo
C:/Users/G/TeraBox). Aquí registras esa carpeta junto al correo. Litch
copia su memoria a TODAS las carpetas registradas en cada respaldo, así
queda duplicada en todas tus cuentas. Cuando una carpeta/cuenta se acerca a
su límite, Litch la marca como llena y sigue usando las demás, avisándote
por voz que registres otra.

Esto es 100% legítimo: son TUS cuentas, abiertas por ti, sincronizadas por
las apps oficiales. Las credenciales no se piden ni se guardan: Litch solo
necesita la ruta de la carpeta que la app oficial ya mantiene sincronizada.
"""
import json
import os
import shutil
import time

from . import memoria

RUTA_CUENTAS = os.path.join(memoria.RUTA_DATA, "cuentas_nube.json")


def cargar_cuentas():
    if os.path.exists(RUTA_CUENTAS):
        try:
            with open(RUTA_CUENTAS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"cuentas": [], "activa": 0}


def guardar_cuentas(datos):
    os.makedirs(memoria.RUTA_DATA, exist_ok=True)
    with open(RUTA_CUENTAS, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)


def registrar_cuenta(correo, carpeta, proveedor="TeraBox", limite_gb=1024):
    """Registra una de tus cuentas de nube. 'carpeta' es la carpeta local
    sincronizada por la app oficial. limite_gb por defecto 1024 (1 TB)."""
    datos = cargar_cuentas()
    for c in datos["cuentas"]:
        if c["carpeta"].lower() == carpeta.lower():
            return False, "Esa carpeta ya estaba registrada, señor."
    datos["cuentas"].append({
        "correo": correo,
        "carpeta": carpeta,
        "proveedor": proveedor,
        "limite_gb": limite_gb,
        "llena": False,
        "registrada": time.strftime("%Y-%m-%d %H:%M"),
    })
    guardar_cuentas(datos)
    return True, f"Cuenta {correo} registrada en {proveedor}."


def eliminar_cuenta(indice):
    datos = cargar_cuentas()
    if 0 <= indice < len(datos["cuentas"]):
        c = datos["cuentas"].pop(indice)
        guardar_cuentas(datos)
        return c["correo"]
    return None


def _uso_gb(carpeta):
    """GB usados dentro de la subcarpeta de respaldo de Litch."""
    destino = os.path.join(carpeta, "Litch_Respaldo")
    total = 0
    if os.path.isdir(destino):
        for raiz, _dirs, archivos in os.walk(destino):
            for a in archivos:
                try:
                    total += os.path.getsize(os.path.join(raiz, a))
                except OSError:
                    pass
    return total / (1024 ** 3)


def respaldar(app=None):
    """Copia la memoria de Litch a todas las cuentas disponibles.
    Devuelve un texto-resumen para mostrar/hablar."""
    datos = cargar_cuentas()
    if not datos["cuentas"]:
        return "No hay cuentas de nube registradas todavía, señor."

    if not os.path.exists(memoria.RUTA_MEMORIA):
        return "Aún no tengo memoria que respaldar."

    marca = time.strftime("%Y%m%d_%H%M%S")
    copiadas, llenas = [], []
    for c in datos["cuentas"]:
        if c.get("llena"):
            continue
        carpeta = c["carpeta"]
        if not os.path.isdir(carpeta):
            continue  # la app de nube no está montada ahora
        usado = _uso_gb(carpeta)
        if usado >= c.get("limite_gb", 1024) * 0.98:
            c["llena"] = True
            llenas.append(c["correo"])
            continue
        destino = os.path.join(carpeta, "Litch_Respaldo")
        try:
            os.makedirs(destino, exist_ok=True)
            # copia con fecha (histórico) + copia "ultima" (rápida de hallar)
            shutil.copy2(memoria.RUTA_MEMORIA,
                         os.path.join(destino, f"memoria_{marca}.json"))
            shutil.copy2(memoria.RUTA_MEMORIA,
                         os.path.join(destino, "memoria_ultima.json"))
            copiadas.append(c["correo"])
        except Exception as e:
            print(f"[Respaldo] Error en {c['correo']}: {e}")

    guardar_cuentas(datos)

    partes = []
    if copiadas:
        partes.append("Memoria respaldada en: " + ", ".join(copiadas) + ".")
    if llenas and app is not None:
        emails = ", ".join(llenas)
        app.decir(f"Señor, las cuentas {emails} llegaron a su límite. "
                  f"Le recomiendo registrar otra cuenta de nube para seguir "
                  f"guardando mi conocimiento.")
    if not copiadas and not llenas:
        partes.append("Ninguna carpeta de nube está disponible ahora mismo. "
                      "¿Está abierta la app de sincronización, señor?")
    return " ".join(partes)


def estado_texto():
    datos = cargar_cuentas()
    if not datos["cuentas"]:
        return "Sin cuentas registradas."
    lineas = []
    for i, c in enumerate(datos["cuentas"]):
        usado = _uso_gb(c["carpeta"]) if os.path.isdir(c["carpeta"]) else 0
        estado = "LLENA" if c.get("llena") else "disponible"
        montada = "✔" if os.path.isdir(c["carpeta"]) else "✘ (app cerrada)"
        lineas.append(f"{i + 1}. {c['correo']} [{c['proveedor']}] — "
                      f"{usado:.2f}/{c['limite_gb']} GB — {estado} — {montada}")
    return "\n".join(lineas)
