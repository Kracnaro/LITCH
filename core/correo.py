"""Gestor de correo electrónico autónomo de Litch.

Soporta Gmail, Outlook, Yahoo y servidores IMAP/SMTP personalizados.
Las credenciales se guardan en data/correos.json (codificación base64).

Para Gmail necesitas una "Contraseña de aplicación":
  Google Account → Seguridad → Verificación en 2 pasos → Contraseñas de app
  (Genera una contraseña de 16 caracteres para "Correo" + "Windows")

Para Outlook: usa tu contraseña normal o una App Password.
Para Yahoo:   Google Account → Seguridad → App Passwords.

Capacidades:
  • Leer bandeja de entrada (IMAP)
  • Buscar emails por asunto o remitente
  • Enviar emails (SMTP)
  • Multi-cuenta: tantas cuentas como quiera
  • Modo autónomo: puede redactar y enviar según instrucciones de voz
"""
import base64
import email
import imaplib
import json
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText

from . import memoria as _mem
from . import permisos

RUTA_CONF = os.path.join(_mem.RUTA_DATA, "correos.json")

# Configuraciones de proveedores conocidos
PROVEEDORES: dict = {
    "Gmail": {
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "imap_ssl":  True,
        "smtp_tls":  True,
        "ayuda":     (
            "Para Gmail crea una Contraseña de aplicación:\n"
            "Google Account → Seguridad → Verificación en 2 pasos → Contraseñas de app\n"
            "Selecciona «Correo» y «Windows», copia la clave de 16 letras."
        ),
    },
    "Outlook": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "imap_ssl":  True,
        "smtp_tls":  True,
        "ayuda":     "Para Outlook usa tu contraseña normal o una App Password de Microsoft.",
    },
    "Yahoo": {
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 587,
        "imap_ssl":  True,
        "smtp_tls":  True,
        "ayuda":     "Yahoo: Cuenta → Seguridad → Genera contraseña de app.",
    },
    "Personalizado": {
        "imap_host": "",
        "imap_port": 993,
        "smtp_host": "",
        "smtp_port": 587,
        "imap_ssl":  True,
        "smtp_tls":  True,
        "ayuda":     "Introduce los servidores IMAP y SMTP manualmente.",
    },
}


# ─── Persistencia de credenciales ─────────────────────────────────────────────

def _ofuscar(texto: str) -> str:
    """Codificación base64 simple — no es cifrado fuerte, evita texto plano."""
    return base64.b64encode(texto.encode()).decode()


def _desofuscar(texto: str) -> str:
    try:
        return base64.b64decode(texto.encode()).decode()
    except Exception:
        return texto


def cargar_cuentas() -> list:
    """Devuelve la lista de cuentas configuradas."""
    if not os.path.exists(RUTA_CONF):
        return []
    try:
        with open(RUTA_CONF, encoding="utf-8") as f:
            cuentas = json.load(f)
        for c in cuentas:
            if c.get("_pass_ofuscado") and not c.get("password"):
                c["password"] = _desofuscar(c["_pass_ofuscado"])
        return cuentas
    except Exception:
        return []


def guardar_cuentas(cuentas: list):
    """Guarda la lista de cuentas (ofuscando contraseñas)."""
    os.makedirs(_mem.RUTA_DATA, exist_ok=True)
    guardables = []
    for c in cuentas:
        g = {k: v for k, v in c.items() if k != "password"}
        if c.get("password"):
            g["_pass_ofuscado"] = _ofuscar(c["password"])
        guardables.append(g)
    with open(RUTA_CONF, "w", encoding="utf-8") as f:
        json.dump(guardables, f, ensure_ascii=False, indent=2)


def agregar_cuenta(email_addr: str, password: str, proveedor: str = "Gmail",
                   imap_host: str = "", smtp_host: str = "") -> bool:
    """Añade o actualiza una cuenta. Devuelve True si se guardó."""
    cuentas = cargar_cuentas()
    cfg_prov = PROVEEDORES.get(proveedor, PROVEEDORES["Personalizado"])

    nueva = {
        "email":     email_addr.strip().lower(),
        "proveedor": proveedor,
        "imap_host": imap_host or cfg_prov["imap_host"],
        "imap_port": cfg_prov["imap_port"],
        "imap_ssl":  cfg_prov["imap_ssl"],
        "smtp_host": smtp_host or cfg_prov["smtp_host"],
        "smtp_port": cfg_prov["smtp_port"],
        "smtp_tls":  cfg_prov["smtp_tls"],
        "password":  password,
        "activa":    True,
    }

    # Reemplazar si ya existe
    for i, c in enumerate(cuentas):
        if c.get("email") == nueva["email"]:
            cuentas[i] = nueva
            guardar_cuentas(cuentas)
            return True
    cuentas.append(nueva)
    guardar_cuentas(cuentas)
    return True


def eliminar_cuenta(email_addr: str):
    cuentas = [c for c in cargar_cuentas()
               if c.get("email") != email_addr.lower()]
    guardar_cuentas(cuentas)


def cuenta_principal() -> dict | None:
    """Devuelve la primera cuenta activa configurada."""
    for c in cargar_cuentas():
        if c.get("activa"):
            return c
    return None


# ─── IMAP — Lectura ──────────────────────────────────────────────────────────

def _conectar_imap(cuenta: dict):
    if cuenta.get("imap_ssl", True):
        imap = imaplib.IMAP4_SSL(cuenta["imap_host"], cuenta["imap_port"])
    else:
        imap = imaplib.IMAP4(cuenta["imap_host"], cuenta["imap_port"])
    imap.login(cuenta["email"], cuenta["password"])
    return imap


def _parsear_email(data_bytes: bytes) -> dict:
    """Parsea los bytes de un email y devuelve dict con campos clave."""
    msg = email.message_from_bytes(data_bytes)

    asunto = email.header.decode_header(msg.get("Subject", ""))
    asunto_txt = ""
    for part, enc in asunto:
        if isinstance(part, bytes):
            asunto_txt += part.decode(enc or "utf-8", errors="replace")
        else:
            asunto_txt += str(part)

    remitente = email.header.decode_header(msg.get("From", ""))
    rem_txt   = remitente[0][0]
    if isinstance(rem_txt, bytes):
        rem_txt = rem_txt.decode(remitente[0][1] or "utf-8", errors="replace")

    cuerpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                try:
                    cuerpo = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")[:2000]
                except Exception:
                    pass
                break
    else:
        try:
            cuerpo = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace")[:2000]
        except Exception:
            pass

    return {
        "asunto":    asunto_txt.strip(),
        "de":        str(rem_txt).strip(),
        "fecha":     msg.get("Date", ""),
        "cuerpo":    cuerpo.strip()[:500],
    }


def leer_inbox(n: int = 10, cuenta: dict = None) -> tuple:
    """Lee los últimos N emails de la bandeja de entrada.

    Devuelve (lista_de_emails, mensaje_estado).
    """
    if not permisos.tiene("correo_leer"):
        return [], "Permiso correo_leer no concedido. Actívalo en el panel de permisos."

    if cuenta is None:
        cuenta = cuenta_principal()
    if cuenta is None:
        return [], "No hay cuentas de correo configuradas. Añade una en el panel de correo."

    try:
        imap = _conectar_imap(cuenta)
        imap.select("INBOX")
        _, datos = imap.search(None, "ALL")
        ids = datos[0].split()[-n:]   # los N más recientes
        emails = []
        for uid in reversed(ids):
            _, msg_data = imap.fetch(uid, "(RFC822)")
            for response in msg_data:
                if isinstance(response, tuple):
                    emails.append(_parsear_email(response[1]))
        imap.logout()
        return emails, f"✓ {len(emails)} emails leídos de {cuenta['email']}."
    except imaplib.IMAP4.error as e:
        return [], f"Error IMAP: {e}. Verifica la contraseña de aplicación."
    except Exception as e:
        return [], f"Error al leer correo: {e}"


def buscar_emails(query: str, n: int = 20, cuenta: dict = None) -> tuple:
    """Busca emails que coincidan con el asunto o remitente."""
    if not permisos.tiene("correo_leer"):
        return [], "Permiso correo_leer no concedido."

    if cuenta is None:
        cuenta = cuenta_principal()
    if cuenta is None:
        return [], "No hay cuentas configuradas."

    try:
        imap = _conectar_imap(cuenta)
        imap.select("INBOX")
        criterio = f'(SUBJECT "{query}")'
        _, datos = imap.search(None, criterio)
        ids = datos[0].split()[-n:]
        emails = []
        for uid in reversed(ids):
            _, msg_data = imap.fetch(uid, "(RFC822)")
            for response in msg_data:
                if isinstance(response, tuple):
                    emails.append(_parsear_email(response[1]))
        imap.logout()
        return emails, f"✓ {len(emails)} resultados para «{query}»."
    except Exception as e:
        return [], f"Error buscando: {e}"


# ─── SMTP — Envío ─────────────────────────────────────────────────────────────

def enviar(destinatario: str, asunto: str, cuerpo: str,
           cuenta: dict = None) -> tuple:
    """Envía un email. Devuelve (bool_exito, mensaje_estado)."""
    if not permisos.tiene("correo_enviar"):
        return False, "Permiso correo_enviar no concedido. Actívalo en el panel de permisos."

    if cuenta is None:
        cuenta = cuenta_principal()
    if cuenta is None:
        return False, "No hay cuentas configuradas para enviar."

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = cuenta["email"]
        msg["To"]      = destinatario
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        if cuenta.get("smtp_tls", True):
            with smtplib.SMTP(cuenta["smtp_host"], cuenta["smtp_port"]) as s:
                s.ehlo()
                s.starttls()
                s.login(cuenta["email"], cuenta["password"])
                s.sendmail(cuenta["email"], [destinatario], msg.as_string())
        else:
            with smtplib.SMTP_SSL(cuenta["smtp_host"], cuenta["smtp_port"]) as s:
                s.login(cuenta["email"], cuenta["password"])
                s.sendmail(cuenta["email"], [destinatario], msg.as_string())

        return True, f"✓ Email enviado a {destinatario}."
    except smtplib.SMTPAuthenticationError:
        return False, "Error de autenticación. Verifica la contraseña de aplicación."
    except Exception as e:
        return False, f"Error al enviar: {e}"


def probar_conexion(cuenta: dict) -> tuple:
    """Prueba las conexiones IMAP y SMTP. Devuelve (imap_ok, smtp_ok, msg)."""
    msgs = []
    imap_ok = False
    smtp_ok = False

    # Test IMAP
    try:
        imap = _conectar_imap(cuenta)
        imap.logout()
        imap_ok = True
        msgs.append("✓ IMAP: conexión exitosa")
    except Exception as e:
        msgs.append(f"✗ IMAP: {e}")

    # Test SMTP
    try:
        if cuenta.get("smtp_tls", True):
            with smtplib.SMTP(cuenta["smtp_host"], cuenta["smtp_port"], timeout=10) as s:
                s.ehlo()
                s.starttls()
                s.login(cuenta["email"], cuenta["password"])
        else:
            with smtplib.SMTP_SSL(cuenta["smtp_host"], cuenta["smtp_port"], timeout=10) as s:
                s.login(cuenta["email"], cuenta["password"])
        smtp_ok = True
        msgs.append("✓ SMTP: conexión exitosa")
    except Exception as e:
        msgs.append(f"✗ SMTP: {e}")

    return imap_ok, smtp_ok, "\n".join(msgs)


# ─── Resumen de emails para Litch ─────────────────────────────────────────────

def resumen_inbox(n: int = 5, idioma: str = "es") -> str:
    """Devuelve un resumen hablado de los últimos emails."""
    emails, msg_estado = leer_inbox(n)
    if not emails:
        return msg_estado

    if idioma == "en":
        lineas = [f"You have {len(emails)} recent emails, sir:"]
        for e in emails[:5]:
            lineas.append(f"• From {e['de'][:30]}: {e['asunto'][:50]}")
        return " ".join(lineas)

    lineas = [f"Tiene {len(emails)} correos recientes, señor:"]
    for em in emails[:5]:
        lineas.append(f"• De {em['de'][:30]}: {em['asunto'][:50]}")
    return " ".join(lineas)
