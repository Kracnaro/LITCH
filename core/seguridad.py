"""Llave maestra de Litch — TOTP compatible con Google Authenticator.

La llave protege el MODO AUTÓNOMO (auto-click sin confirmación y
auto-mejora de parámetros). Registro: Litch genera un secreto y un QR;
lo escaneas con Google Authenticator y confirmas con el código de 6
dígitos. Activar el modo autónomo siempre exige un código vigente;
desactivarlo es libre (apagar la autonomía nunca debe tener barreras).
"""
import json
import os

from . import memoria

RUTA_LLAVE = os.path.join(memoria.RUTA_DATA, "llave_maestra.json")

try:
    import pyotp
    _OTP_OK = True
except Exception:
    _OTP_OK = False

try:
    import qrcode
    _QR_OK = True
except Exception:
    _QR_OK = False


def disponible():
    return _OTP_OK and _QR_OK


def _leer():
    if os.path.exists(RUTA_LLAVE):
        try:
            with open(RUTA_LLAVE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _guardar(datos):
    os.makedirs(memoria.RUTA_DATA, exist_ok=True)
    with open(RUTA_LLAVE, "w", encoding="utf-8") as f:
        json.dump(datos, f)


def llave_confirmada():
    datos = _leer()
    return bool(datos and datos.get("confirmada"))


def generar_llave(usuario="Giancarlo"):
    """Crea (o regenera) el secreto y devuelve la URI para el QR."""
    secreto = pyotp.random_base32()
    _guardar({"secreto": secreto, "confirmada": False})
    return pyotp.totp.TOTP(secreto).provisioning_uri(
        name=usuario, issuer_name="Litch IA")


def qr_imagen(uri):
    """Imagen PIL del QR para escanear con Google Authenticator."""
    return qrcode.make(uri).get_image()


def verificar(codigo):
    datos = _leer()
    if not datos or not _OTP_OK:
        return False
    try:
        return pyotp.TOTP(datos["secreto"]).verify(str(codigo).strip(),
                                                   valid_window=1)
    except Exception:
        return False


def confirmar(codigo):
    """Valida el primer código tras escanear el QR y sella el registro."""
    datos = _leer()
    if datos and verificar(codigo):
        datos["confirmada"] = True
        _guardar(datos)
        return True
    return False
