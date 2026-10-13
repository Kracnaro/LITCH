"""Memoria persistente de Litch.

Todo lo que el agente aprende (patrones, señales, estadísticas,
conversaciones, configuración, loterías, correos, investigaciones web)
se guarda en MEMORIA_AP/ — carpeta visible cuyo peso crece con cada sesión.
"""
import copy
import json
import os
import shutil
import threading

RUTA_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_DATA     = os.path.join(RUTA_PROYECTO, "MEMORIA_AP")
RUTA_MEMORIA  = os.path.join(RUTA_DATA, "memoria.json")

# Migración automática desde la carpeta antigua "data/" (una sola vez)
def _migrar_data_antigua():
    antigua = os.path.join(RUTA_PROYECTO, "data")
    if not os.path.isdir(antigua):
        return
    os.makedirs(RUTA_DATA, exist_ok=True)
    for nombre in os.listdir(antigua):
        src = os.path.join(antigua, nombre)
        dst = os.path.join(RUTA_DATA, nombre)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

_migrar_data_antigua()

_lock = threading.Lock()

ESTRUCTURA = {
    "config": {
        "region_grafico": None,       # [x1, y1, x2, y2] zona de velas (canal 1)
        "boton_verde": None,          # [x, y] botón Compra (canal 1)
        "boton_rojo": None,           # [x, y] botón Venta (canal 1)
        "region_grafico_2": None,     # [x1, y1, x2, y2] zona de velas (canal 2 — 2do grafico/activo)
        "boton_verde_2": None,        # [x, y] botón Compra (canal 2)
        "boton_rojo_2": None,         # [x, y] botón Venta (canal 2)
        "periodo_vela": 60,           # segundos por vela
        "longitud_patron": 3,         # "algoritmo del 3": patrones de 3 velas
        "min_observaciones": 8,       # mínimo de veces visto para confiar
        "umbral_probabilidad": 0.65,  # confianza mínima para emitir señal
        "avisar_resultados": True,
        "idioma": "es",               # idioma actual: "es" / "en"
        "monto_base": 10.0,           # monto por trade (manual o base para Kelly)
        "monto_modo_manual": False,   # True: usa monto_base fijo; False: Kelly/stats
        "montos_test": "",            # ej. "10,50,100,500" — Litch aprende cuál rinde más
    },
    "secuencia": [],        # historial de velas: "V" (verde) / "R" (roja) — canal 1
    "patrones": {},         # {"VVR": {"V": 12, "R": 4}, ...} — canal 1
    "senales": [],          # historial de señales emitidas — canal 1
    "estadisticas": {"senales_total": 0, "aciertos": 0, "fallos": 0},
    "secuencia_2": [],      # canal 2: gráfico/activo independiente (entrenamiento doble)
    "patrones_2": {},
    "senales_2": [],
    "estadisticas_2": {"senales_total": 0, "aciertos": 0, "fallos": 0},
    "secuencia_3": [],      # canal 3: tercer gráfico independiente
    "patrones_3": {},
    "senales_3": [],
    "estadisticas_3": {"senales_total": 0, "aciertos": 0, "fallos": 0},
    "secuencia_4": [],      # canal 4: cuarto gráfico independiente
    "patrones_4": {},
    "senales_4": [],
    "estadisticas_4": {"senales_total": 0, "aciertos": 0, "fallos": 0},
    "conversaciones": [],
    "loteria": {"historial": [], "ultimo_analisis": None},
}


def cargar():
    """Carga la memoria desde disco (o crea una nueva)."""
    os.makedirs(RUTA_DATA, exist_ok=True)
    mem = copy.deepcopy(ESTRUCTURA)
    if os.path.exists(RUTA_MEMORIA):
        try:
            with open(RUTA_MEMORIA, "r", encoding="utf-8") as f:
                datos = json.load(f)
            for clave, valor in datos.items():
                if clave == "config" and isinstance(valor, dict):
                    mem["config"].update(valor)
                else:
                    mem[clave] = valor
        except Exception as e:
            print(f"[Memoria] No se pudo leer la memoria previa: {e}")
    return mem


def _default_json(obj):
    """Encoder de respaldo: convierte dataclasses y objetos arbitrarios a dict/str."""
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses
        return dataclasses.asdict(obj)
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items()
                if not k.startswith("_") and isinstance(v, (str, int, float, bool, list, dict, type(None)))}
    return str(obj)


def guardar(mem):
    """Guarda la memoria a disco de forma segura."""
    with _lock:
        try:
            os.makedirs(RUTA_DATA, exist_ok=True)
            temporal = RUTA_MEMORIA + ".tmp"
            with open(temporal, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=1, default=_default_json)
            os.replace(temporal, RUTA_MEMORIA)
        except Exception as e:
            print(f"[Memoria] Error al guardar: {e}")


def registrar_conversacion(mem, origen, texto, respuesta):
    mem["conversaciones"].append(
        {"origen": origen, "usuario": texto, "litch": respuesta}
    )
    if len(mem["conversaciones"]) > 300:
        del mem["conversaciones"][:-300]


def peso_memoria() -> str:
    """Devuelve un resumen del tamaño de la carpeta MEMORIA_AP en KB/MB."""
    if not os.path.isdir(RUTA_DATA):
        return "MEMORIA_AP: vacía (aún no hay datos guardados)."
    total = 0
    archivos = []
    for nombre in os.listdir(RUTA_DATA):
        ruta = os.path.join(RUTA_DATA, nombre)
        if os.path.isfile(ruta):
            tam = os.path.getsize(ruta)
            total += tam
            archivos.append((nombre, tam))
    archivos.sort(key=lambda x: -x[1])
    if total < 1024:
        total_txt = f"{total} bytes"
    elif total < 1024 * 1024:
        total_txt = f"{total/1024:.1f} KB"
    else:
        total_txt = f"{total/1024/1024:.2f} MB"
    detalle = ", ".join(
        f"{n}={s/1024:.1f}KB" for n, s in archivos[:5]
    )
    return (f"MEMORIA_AP: {total_txt} totales · {len(archivos)} archivos. "
            f"Más grandes: {detalle}")


def ruta_memoria_ap() -> str:
    """Devuelve la ruta absoluta de la carpeta MEMORIA_AP."""
    return RUTA_DATA
