"""
lector_libros.py — Aprende de libros y documentos locales.

Flujo completo:
  1. El usuario pone sus PDF/TXT/DOCX/EPUB en la carpeta  LIBROS/
     (que queda en la raíz del proyecto, junto a litch.py)
  2. Dice "Litch, carga mis libros" o usa el botón en la interfaz
  3. Litch extrae el texto, lo fragmenta en chunks de ~600 caracteres
  4. Guarda el índice en MEMORIA_AP/libros_chunks.json
  5. Al preguntar "¿qué dicen tus libros sobre X?" busca con TF-IDF
     y devuelve los pasajes más relevantes

Dependencias (ya instaladas):
  pip install pypdf           ← PDF
  pip install python-docx     ← Word .docx
  (TXT y MD no necesitan nada)
"""

import json
import os
import re
import time

from . import memoria as mem_mod

# ── Rutas ──────────────────────────────────────────────────────────────────────
_BASE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_LIBROS  = os.path.join(_BASE, "LIBROS")
_RUTA_CHUNKS = os.path.join(mem_mod.ruta_memoria_ap(), "libros_chunks.json")

# ── Parámetros de chunking ─────────────────────────────────────────────────────
_CHARS_CHUNK  = 650    # tamaño de cada fragmento
_OVERLAP      = 120    # solapamiento entre chunks (contexto compartido)
_MAX_CHUNKS   = 8000   # tope para no saturar memoria

# ── Librerías opcionales ───────────────────────────────────────────────────────
try:
    import pypdf as _pypdf
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

try:
    import docx as _docx
    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False

# ── Estado en memoria (singleton) ─────────────────────────────────────────────
_chunks:  list = []         # [{libro, chunk_id, texto, palabras}]
_indice:  dict = {}         # palabra → [índices en _chunks]
_libros:  dict = {}         # nombre_archivo → {ts, chars, chunks, fecha_carga}
_cargado: bool = False


# ════════════════════════════════════════════════════════════════════════════════
# Extracción de texto por formato
# ════════════════════════════════════════════════════════════════════════════════

def _extraer_pdf(path: str) -> str:
    if not _PDF_OK:
        return ""
    try:
        reader = _pypdf.PdfReader(path)
        partes = []
        for page in reader.pages:
            try:
                partes.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(partes)
    except Exception:
        return ""


def _extraer_txt(path: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc, errors="ignore") as f:
                return f.read()
        except Exception:
            pass
    return ""


def _extraer_docx(path: str) -> str:
    if not _DOCX_OK:
        return ""
    try:
        doc = _docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""


def _extraer(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _extraer_pdf(path)
    if ext in (".txt", ".md"):
        return _extraer_txt(path)
    if ext == ".docx":
        return _extraer_docx(path)
    return ""


# ════════════════════════════════════════════════════════════════════════════════
# Fragmentación (chunking)
# ════════════════════════════════════════════════════════════════════════════════

def _limpiar(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto)
    # Quitar caracteres no imprimibles conservando español
    texto = re.sub(
        r"[^\w\s\.,;:¿?¡!\"'\(\)\-áéíóúüñÁÉÍÓÚÜÑ]", " ", texto)
    return texto.strip()


def _fragmentar(texto: str, libro: str) -> list:
    texto = _limpiar(texto)
    if len(texto) < 60:
        return []

    resultado = []
    inicio    = 0
    idx       = 0
    n         = len(texto)

    while inicio < n and len(resultado) < _MAX_CHUNKS:
        fin = min(inicio + _CHARS_CHUNK, n)

        # Extender al punto más cercano para no cortar medio de oración
        if fin < n:
            p = texto.rfind(".", inicio, fin + 100)
            if p > inicio + 200:
                fin = p + 1

        fragmento = texto[inicio:fin].strip()
        if len(fragmento) > 50:
            palabras = set(re.findall(r"[a-záéíóúüñ]{3,}", fragmento.lower()))
            resultado.append({
                "libro":    libro,
                "chunk_id": idx,
                "texto":    fragmento,
                "palabras": list(palabras),
            })
            idx += 1

        inicio = max(fin - _OVERLAP, inicio + 1)

    return resultado


# ════════════════════════════════════════════════════════════════════════════════
# Índice de búsqueda (TF-IDF simplificado)
# ════════════════════════════════════════════════════════════════════════════════

def _construir_indice(todos: list) -> dict:
    """Índice invertido: palabra → lista de posiciones en todos_chunks."""
    idx: dict = {}
    for i, ch in enumerate(todos):
        for pal in ch.get("palabras", []):
            idx.setdefault(pal, []).append(i)
    return idx


# ════════════════════════════════════════════════════════════════════════════════
# Persistencia
# ════════════════════════════════════════════════════════════════════════════════

def _guardar():
    os.makedirs(os.path.dirname(_RUTA_CHUNKS), exist_ok=True)
    try:
        with open(_RUTA_CHUNKS, "w", encoding="utf-8") as f:
            json.dump({"chunks": _chunks, "libros": _libros,
                       "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
                      f, ensure_ascii=False)
    except Exception:
        pass


def _cargar_persistido() -> bool:
    global _chunks, _libros, _indice, _cargado
    if not os.path.exists(_RUTA_CHUNKS):
        return False
    try:
        with open(_RUTA_CHUNKS, "r", encoding="utf-8") as f:
            data = json.load(f)
        _chunks  = data.get("chunks", [])
        _libros  = data.get("libros", {})
        _indice  = _construir_indice(_chunks)
        _cargado = True
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════════════════
# API pública
# ════════════════════════════════════════════════════════════════════════════════

def inicializar():
    """Llama al arrancar Litch para recuperar el índice persistido."""
    global _cargado
    if not _cargado:
        _cargar_persistido()


def cargar_libros(callback=None) -> dict:
    """
    Escanea LIBROS/ y procesa todos los archivos nuevos o modificados.

    callback(str) — función para informar progreso (p.ej. app.log)

    Retorna:
        nuevos   — cuántos libros se procesaron ahora
        total    — cuántos libros hay en total en el índice
        chunks   — total de fragmentos en el índice
        libros   — lista de nombres de archivos cargados
        errores  — lista de errores (archivos vacíos, ilegibles, etc.)
    """
    global _chunks, _libros, _indice, _cargado

    def log(msg):
        if callback:
            callback(msg)

    os.makedirs(RUTA_LIBROS, exist_ok=True)

    exts    = {".pdf", ".txt", ".md", ".docx"}
    try:
        archivos = [f for f in os.listdir(RUTA_LIBROS)
                    if os.path.splitext(f)[1].lower() in exts]
    except Exception as e:
        return {"nuevos": 0, "total": 0, "chunks": 0, "libros": [],
                "errores": [f"Error leyendo LIBROS/: {e}"]}

    if not archivos:
        return {"nuevos": 0, "total": len(_libros), "chunks": len(_chunks),
                "libros": list(_libros.keys()),
                "errores": ["La carpeta LIBROS/ está vacía — copia tus PDF o TXT allí"]}

    nuevos  = []
    errores = []

    for nombre in sorted(archivos):
        path = os.path.join(RUTA_LIBROS, nombre)
        ts   = str(os.path.getmtime(path))

        # Saltar si ya está cargado y no cambió
        if nombre in _libros and _libros[nombre].get("ts") == ts:
            log(f"  ↺ '{nombre}' sin cambios — omitido.")
            continue

        log(f"  📖 Leyendo '{nombre}'…")
        texto = _extraer(path)

        if not texto or len(texto) < 100:
            msg = (f"'{nombre}': sin texto extraíble. "
                   "PDF escaneado (imágenes)? Prueba con un PDF con texto seleccionable.")
            errores.append(msg)
            log(f"  ⚠ {msg}")
            continue

        # Reemplazar chunks anteriores del mismo libro
        _chunks = [c for c in _chunks if c["libro"] != nombre]

        nuevos_chunks = _fragmentar(texto, nombre)
        if not nuevos_chunks:
            errores.append(f"'{nombre}': sin fragmentos útiles")
            continue

        _chunks.extend(nuevos_chunks)
        _libros[nombre] = {
            "ts":          ts,
            "chars":       len(texto),
            "chunks":      len(nuevos_chunks),
            "fecha_carga": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        nuevos.append(nombre)
        log(f"  ✓ '{nombre}' → {len(nuevos_chunks)} fragmentos.")

    _indice  = _construir_indice(_chunks)
    _cargado = True
    _guardar()

    return {
        "nuevos":  len(nuevos),
        "total":   len(_libros),
        "chunks":  len(_chunks),
        "libros":  list(_libros.keys()),
        "errores": errores,
    }


def buscar(pregunta: str, top_n: int = 3, libro_filtro: str = None) -> list:
    """
    Busca pasajes relevantes para la pregunta usando índice invertido.

    pregunta     — consulta en lenguaje natural
    top_n        — cuántos resultados devolver
    libro_filtro — restringir a un libro específico (None = todos)

    Retorna lista de dicts: {libro, texto, score}
    """
    global _cargado
    if not _cargado:
        _cargar_persistido()
    if not _chunks:
        return []

    palabras = set(re.findall(r"[a-záéíóúüñ]{3,}", pregunta.lower()))

    # Stop words comunes (no aportan en búsqueda)
    stops = {"que", "una", "con", "del", "los", "las", "son", "por", "para",
             "como", "este", "ese", "ser", "más", "mas", "hay", "tiene",
             "pero", "cuando", "todo", "cada"}
    palabras -= stops

    if not palabras:
        return []

    # Puntuar chunks
    puntajes: dict = {}
    for pal in palabras:
        for i in _indice.get(pal, []):
            if libro_filtro and _chunks[i]["libro"] != libro_filtro:
                continue
            puntajes[i] = puntajes.get(i, 0) + 1

    if not puntajes:
        return []

    top = sorted(puntajes.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        {"libro": _chunks[i]["libro"],
         "texto": _chunks[i]["texto"],
         "score": sc}
        for i, sc in top
        if 0 <= i < len(_chunks)
    ]


def listar_libros() -> list:
    """Devuelve los libros cargados con estadísticas."""
    global _cargado
    if not _cargado:
        _cargar_persistido()
    return [
        {"nombre": n,
         "chunks": info.get("chunks", 0),
         "fecha":  info.get("fecha_carga", "?")}
        for n, info in _libros.items()
    ]


def total_chunks() -> int:
    global _cargado
    if not _cargado:
        _cargar_persistido()
    return len(_chunks)


def disponible() -> bool:
    global _cargado
    if not _cargado:
        _cargar_persistido()
    return bool(_chunks)


def info_dependencias() -> dict:
    return {
        "pdf":       _PDF_OK,
        "docx":      _DOCX_OK,
        "txt":       True,
        "ruta_libros": RUTA_LIBROS,
        "pip_pdf":   "pip install pypdf",
        "pip_docx":  "pip install python-docx",
    }
