"""
Módulo de notificaciones: WhatsApp, SMS y Email.
"""
import os
import smtplib
import subprocess
import json
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from telefono import para_whatsapp, para_sms


# ============================================
# CREDENCIALES
# ============================================
GMAIL_USER = os.environ.get('GMAIL_USER', '')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')

TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', '')
TWILIO_SMS_FROM = os.environ.get('TWILIO_SMS_FROM', '')


def _hay_credenciales_email():
    return bool(GMAIL_USER and GMAIL_APP_PASSWORD)

def _hay_credenciales_twilio():
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)


# ============================================
# EMAIL (Gmail SMTP)
# ============================================
def enviar_email(destino, asunto, cuerpo):
    if not _hay_credenciales_email():
        return False, 'sin_credenciales'

    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = destino
        msg['Subject'] = asunto
        msg.attach(MIMEText(cuerpo, 'plain'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        return True, 'enviado'
    except Exception as e:
        return False, f'error: {e}'


# ============================================
# SMS GRATIS (termux-sms-send)
# ============================================
def enviar_sms_termux(destino, cuerpo):
    """Envía SMS usando termux-sms-send (gratis, desde tu SIM)."""
    try:
        numero = para_sms(destino).lstrip('+')
        print(f"📱 Enviando SMS a {numero}...")

        proc = subprocess.Popen(
            ['termux-sms-send', '-n', numero, cuerpo],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True
        )

        try:
            stdout, stderr = proc.communicate(timeout=10)
            if proc.returncode == 0:
                print(f"✅ SMS enviado a {numero}")
                return True, 'enviado_termux'
            else:
                print(f"⚠️ SMS falló: {stderr}")
                return False, f'error_termux: {stderr}'
        except subprocess.TimeoutExpired:
            print(f"⏳ termux-sms-send tardando, pero seguirá en background")
            return True, 'enviado_termux_async'
    except FileNotFoundError:
        return False, 'sin_termux_api'
    except Exception as e:
        return False, f'error: {e}'


# ============================================
# TWILIO (WhatsApp o SMS pago)
# ============================================
def enviar_twilio(destino, cuerpo, canal='whatsapp'):
    if not _hay_credenciales_twilio():
        return False, 'sin_credenciales'

    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        if canal == 'whatsapp':
            if not TWILIO_WHATSAPP_FROM:
                return False, 'sin_numero_whatsapp'
            numero_destino = f'whatsapp:+{destino.lstrip("+")}'
            numero_origen = TWILIO_WHATSAPP_FROM
        else:
            if not TWILIO_SMS_FROM:
                return False, 'sin_numero_sms'
            numero_destino = f'+{destino.lstrip("+")}'
            numero_origen = TWILIO_SMS_FROM

        message = client.messages.create(
            body=cuerpo,
            from_=numero_origen,
            to=numero_destino
        )
        return True, message.sid
    except Exception as e:
        return False, f'error: {e}'


# ============================================
# ENVIAR OTP SEGÚN CANAL
# ============================================
def _token_bot():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_whatsapp', '.bot_token')) as f:
            return f.read().strip()
    except Exception:
        return ''


def enviar_whatsapp_bot(destino, cuerpo):
    """Envía WhatsApp vía bot local (whatsapp-web.js)."""
    try:
        data = json.dumps({'numero': str(destino), 'mensaje': cuerpo}).encode()
        req = urllib.request.Request(
            'http://127.0.0.1:3002/send',
            data=data,
            headers={'Content-Type': 'application/json', 'x-bot-token': _token_bot()}
        )
        with urllib.request.urlopen(req, timeout=15):
            return True, 'enviado_bot'
    except Exception as e:
        if getattr(e, 'code', None) == 404:  # el bot responde 404 si el número no tiene WhatsApp
            return False, 'sin_whatsapp'
        return False, f'error_bot: {e}'


def enviar_otp(canal, contacto, codigo):
    """Envía el código OTP por el canal elegido."""
    canal = (canal or '').lower()
    asunto = 'Tu codigo de verificacion - Pagadiario'
    cuerpo = f'Tu codigo de verificacion es: {codigo}\n\nNo lo compartas con nadie.'

    if canal == 'email':
        ok, detalle = enviar_email(contacto, asunto, cuerpo)
    elif canal == 'whatsapp':
        ok, detalle = enviar_whatsapp_bot(para_whatsapp(contacto), cuerpo)
        if not ok and detalle != 'sin_whatsapp':
            print(f"⚠️ Bot WA falló: {detalle}. Intentando Twilio...")
            ok, detalle = enviar_twilio(para_whatsapp(contacto), cuerpo, canal='whatsapp')
    elif canal == 'sms':
        # Intentar termux-sms-send primero (GRATIS)
        ok, detalle = enviar_sms_termux(para_sms(contacto), cuerpo)
        # Si falla, intentar con Twilio (pago)
        if not ok:
            print(f"⚠️ termux-sms-send falló: {detalle}. Intentando Twilio...")
            ok, detalle = enviar_twilio(para_sms(contacto), cuerpo, canal='sms')
    else:
        return {'ok': False, 'modo': 'error', 'detalle': 'canal_desconocido'}

    if ok:
        return {'ok': True, 'modo': 'real', 'detalle': detalle}

    if os.environ.get('PAGADIARIO_DEV') == '1' and (detalle == 'sin_credenciales' or detalle.startswith('sin_')):
        return {'ok': True, 'modo': 'dev', 'detalle': detalle}

    return {'ok': False, 'modo': 'error', 'detalle': detalle}
