"""
diagnostico_entorno.py — Revisa qué impide que Litch funcione al máximo.

Ejecutar:  doble clic en diagnostico_entorno.bat
       o:  "C:\\Users\\G\\AppData\\Local\\Python\\bin\\python.exe" diagnostico_entorno.py

Revisa: versión de Python, dependencias, memoria/CPU, latencia a IBKR y a
Yahoo, tamaño de los archivos de memoria, y la configuración crítica.
Al final da un veredicto y qué corregir.
"""

import json
import os
import socket
import sys
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
OK, WARN, BAD = "  [OK]  ", "  [!]   ", "  [X]   "
problemas = []


def titulo(t):
    print("\n" + "=" * 62)
    print(f"  {t}")
    print("=" * 62)


# ── 1. Python ───────────────────────────────────────────────────────────────
titulo("1. PYTHON")
v = sys.version_info
print(f"       Versión: {v.major}.{v.minor}.{v.micro}")
if v.major == 3 and v.minor >= 12:
    print(WARN + "Python 3.12+ : algunas librerías de trading (ib_insync) "
          "no son 100% compatibles. Litch ya está blindado para eso.")
elif v.major == 3 and 9 <= v.minor <= 11:
    print(OK + "Versión ideal para librerías de trading.")
else:
    print(BAD + "Versión no recomendada.")
    problemas.append("Actualiza a Python 3.11 o 3.12.")

# ── 2. Dependencias ─────────────────────────────────────────────────────────
titulo("2. DEPENDENCIAS")
CRITICAS = ["numpy", "mss", "PIL", "pyautogui", "requests"]
OPCIONALES = {
    "ibapi":      "conexión con Interactive Brokers",
    "yfinance":   "entrenamiento con velas reales",
    "pypdf":      "leer manuales en PDF",
    "speech_recognition": "micrófono",
}
for m in CRITICAS:
    try:
        __import__(m)
        print(OK + f"{m}")
    except Exception:
        print(BAD + f"{m} FALTA — Litch no funcionará bien")
        problemas.append(f"pip install {m}")
for m, para in OPCIONALES.items():
    try:
        __import__(m)
        print(OK + f"{m}  ({para})")
    except Exception:
        print(WARN + f"{m} falta — sin esto: {para}")
        problemas.append(f"pip install {m}   (opcional: {para})")

# ── 3. Conectividad y latencia ──────────────────────────────────────────────
titulo("3. CONEXIÓN Y LATENCIA")


def probar(host, puerto, nombre, critico=False):
    t0 = time.time()
    try:
        with socket.create_connection((host, puerto), timeout=3):
            ms = (time.time() - t0) * 1000
            if ms < 100:
                print(OK + f"{nombre}: {ms:.0f} ms (excelente)")
            elif ms < 400:
                print(OK + f"{nombre}: {ms:.0f} ms (aceptable)")
            else:
                print(WARN + f"{nombre}: {ms:.0f} ms (lento)")
            return True
    except Exception:
        msg = BAD if critico else WARN
        print(msg + f"{nombre}: sin respuesta")
        return False


tws_paper = probar("127.0.0.1", 7497, "TWS puerto PAPER (7497)")
tws_real = probar("127.0.0.1", 7496, "TWS puerto REAL (7496)")
if not tws_paper:
    problemas.append("Abre TWS en modo Paper y habilita la API "
                     "(Archivo→Configuración global→API→Configuración).")
if tws_real and not tws_paper:
    problemas.append("¡CUIDADO! Solo responde el puerto REAL. Cambia TWS a "
                     "modo Paper antes de practicar.")
probar("query1.finance.yahoo.com", 443, "Yahoo Finance (datos)")

# ── 4. Archivos de memoria ──────────────────────────────────────────────────
titulo("4. MEMORIA DE LITCH")
ARCHIVOS = {
    "data/memoria.json":                 "memoria principal",
    "MEMORIA_AP/fallo_db.json":          "base de fallos (binarias)",
    "MEMORIA_AP/memoria_acciones.json":  "memoria de acciones (Wall Street)",
    "MEMORIA_AP/autoaprendizaje.json":   "progreso de aprendizaje",
    "MEMORIA_AP/red_pesos.npz":          "pesos de la red neuronal",
}
for rel, desc in ARCHIVOS.items():
    ruta = os.path.join(RAIZ, rel)
    if os.path.exists(ruta):
        mb = os.path.getsize(ruta) / (1024 * 1024)
        estado = OK if mb < 50 else WARN
        print(estado + f"{rel}  ({mb:.1f} MB) — {desc}")
        if mb > 50:
            problemas.append(f"{rel} muy grande ({mb:.0f} MB): puede ralentizar.")
    else:
        print(WARN + f"{rel} aún no existe — {desc}")

# ── 5. Configuración crítica ────────────────────────────────────────────────
titulo("5. CONFIGURACIÓN CRÍTICA")
try:
    with open(os.path.join(RAIZ, "data", "memoria.json"), encoding="utf-8") as f:
        cfg = json.load(f).get("config", {})
    revisiones = [
        ("tipo_cuenta", cfg.get("tipo_cuenta", "demo"),
         "demo = seguro | real = dinero verdadero"),
        ("monto_base", cfg.get("monto_base", "?"),
         "monto por operación"),
        ("region_grafico", "calibrado" if cfg.get("region_grafico") else "SIN CALIBRAR",
         "visión del gráfico"),
        ("flash_crash_racha", cfg.get("flash_crash_racha", 6),
         "velas iguales para alertar"),
    ]
    for k, val, desc in revisiones:
        estado = OK
        if k == "tipo_cuenta" and val == "real":
            estado = WARN
        if k == "region_grafico" and val == "SIN CALIBRAR":
            estado = WARN
            problemas.append("Calibra el gráfico con el botón 📐 de Litch.")
        print(estado + f"{k} = {val}   ({desc})")
except Exception as e:
    print(BAD + f"No pude leer la configuración: {e}")

# ── 6. Horario de mercado ───────────────────────────────────────────────────
titulo("6. HORARIO DE WALL STREET")
t = time.localtime()
dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
print(f"       Ahora: {dias[t.tm_wday]} {t.tm_hour:02d}:{t.tm_min:02d}")
if t.tm_wday >= 5:
    print(WARN + "Fin de semana — mercado CERRADO.")
else:
    mins = t.tm_hour * 60 + t.tm_min
    if 570 <= mins < 960:
        print(OK + "Mercado ABIERTO (9:30-16:00 ET).")
    else:
        print(WARN + "Fuera del horario regular (9:30-16:00 ET).")

# ── VEREDICTO ───────────────────────────────────────────────────────────────
titulo("VEREDICTO")
if not problemas:
    print("  Todo en orden. Litch puede funcionar a su máximo rendimiento.")
else:
    print(f"  {len(problemas)} punto(s) por corregir:\n")
    for i, p in enumerate(problemas, 1):
        print(f"   {i}. {p}")
print()
