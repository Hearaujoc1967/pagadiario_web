# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_session import Session
from config import Config
from database import query
from telefono import normalizar
import hashlib
import os
import socket
import threading
import webbrowser
from datetime import date, timedelta

import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# ============================================
# SILENCIAR WARNING DE WERKZEUG (solo desarrollo)
# ============================================
import sys
class _FiltroStderr:
    def write(self, msg):
        if 'WARNING: This is a development server' in msg:
            return
        if 'Use a production WSGI server instead' in msg:
            return
        sys.__stderr__.write(msg)
    def flush(self):
        sys.__stderr__.flush()
sys.stderr = _FiltroStderr()

app = Flask(__name__)
app.config.from_object(Config)

# Inicializar Flask-Session
Session(app)

# Crear carpeta de sesiones si no existe
os.makedirs(Config.SESSION_FILE_DIR, exist_ok=True)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================
def sha1_hash(texto):
    """Genera el hash SHA1, igual que la función do_hash() de CodeIgniter."""
    return hashlib.sha1(texto.encode('utf-8')).hexdigest()


import random
from datetime import datetime

def generar_codigo_otp():
    """Genera un código OTP de 6 dígitos."""
    import secrets
    return str(100000 + secrets.randbelow(900000))


def validar_campos_unicos():
    """Valida si un campo (dni, email, telf) ya existe en t_cliente."""
    campo = request.form.get('campo', '').strip()
    valor = request.form.get('valor', '').strip()

    # Mapear campo a columna real
    mapa = {'dni': 'dni', 'cedula': 'dni', 'nombre': 'nombre', 'email': 'email', 'telefono': 'telf'}
    if campo not in mapa or not valor:
        return jsonify({'existe': False})

    columna = mapa[campo]
    try:
        existe = query_estricto(
            f"SELECT id, nombre, dni FROM t_cliente WHERE {columna} = %s LIMIT 1",
            (valor,)
        )
        if existe:
            return jsonify({'existe': True, 'nombre': existe['nombre']})
        return jsonify({'existe': False})
    except BaseDatosNoDisponible:
        raise
    except Exception as e:
        print(f"Error validando {campo}: {e}", flush=True)
        return jsonify({'existe': False, 'error': 'interno'}), 500


def enviar_otp():
    """Envía un código OTP al canal elegido (whatsapp/sms/email)."""
    dni = request.form.get('dni', '').strip()
    canal = request.form.get('canal', 'whatsapp').strip().lower()
    contacto = request.form.get('contacto', '').strip()

    if not dni:
        return jsonify({'success': False, 'error': 'DNI es obligatorio'})

    if canal not in ('whatsapp', 'sms', 'email'):
        return jsonify({'success': False, 'error': 'Canal no válido'})

    # Si no viene contacto, buscarlo en t_cliente
    if not contacto:
        cliente = query(
            "SELECT telf, email FROM t_cliente WHERE dni = %s LIMIT 1",
            (dni,),
            fetchone=True
        )
        if cliente:
            if canal == 'email':
                contacto = cliente.get('email') or ''
            else:
                contacto = cliente.get('telf') or ''

    if not contacto:
        return jsonify({'success': False, 'error': 'No hay ' + ('email' if canal == 'email' else 'teléfono') + ' registrado'})

    codigo = generar_codigo_otp()

    try:
        # Invalidar códigos anteriores del mismo DNI
        query(
            "UPDATE t_otp SET usado = 1 WHERE dni = %s AND usado = 0",
            (dni,),
            commit=True
        )

        # Crear nuevo código con expiración de 10 minutos
        query(
            """INSERT INTO t_otp (dni, telefono, codigo, tipo, fecha_expiracion)
               VALUES (%s, %s, %s, %s, DATE_ADD(NOW(), INTERVAL 10 MINUTE))""",
            (dni, contacto, codigo, 'canal_' + canal),
            commit=True
        )

        # Modo desarrollo: devolvemos el código en la respuesta
        resultado = enviar_otp_real(canal, contacto, codigo)

        if not resultado['ok']:
            print(f"❌ Error enviando OTP: {resultado['detalle']}")
            return jsonify({
                'success': False,
                'error': f"No se pudo enviar por {canal}. Detalle: {resultado['detalle']}"
            })

        if resultado['modo'] == 'dev':
            print(f"\n🔐 [MODO DEV] OTP [{canal.upper()}] para {dni} ({contacto}): {codigo}\n")
            return jsonify({
                'success': True,
                'modo': 'dev',
                'codigo_dev': codigo,
                'canal': canal,
                'contacto': contacto,
                'mensaje': f'[Modo dev] Código: {codigo}'
            })
        else:
            print(f"✅ OTP [{canal.upper()}] enviado a {contacto} ({dni})")
            return jsonify({
                'success': True,
                'modo': 'real',
                'canal': canal,
                'contacto': contacto,
                'mensaje': f'Código enviado por {canal}'
            })
    except Exception as e:
        print(f"Error enviando OTP: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/register')
def register():
    return render_template('register.html')  # O el nombre exacto de tu archivo HTML de registro

def verificar_otp():
    """Verifica un código OTP ingresado por el usuario."""
    dni = request.form.get('dni', '').strip()
    codigo = request.form.get('codigo', '').strip()

    if not dni or not codigo:
        return jsonify({'success': False, 'error': 'DNI y código son obligatorios'})

    try:
        otp = query(
            """SELECT * FROM t_otp
               WHERE dni = %s AND codigo = %s AND usado = 0
                 AND fecha_expiracion > NOW()
               ORDER BY id DESC LIMIT 1""",
            (dni, codigo),
            fetchone=True
        )

        if otp:
            query("UPDATE t_otp SET usado = 1 WHERE id = %s", (otp['id'],), commit=True)
            return jsonify({'success': True, 'mensaje': 'Código verificado'})
        return jsonify({'success': False, 'error': 'Código inválido o expirado'})
    except Exception as e:
        print(f"Error verificando OTP: {e}")
        return jsonify({'success': False, 'error': str(e)})


def registro_cliente():
    """Registra un nuevo cliente desde el formulario público.
    Todo ocurre en UNA transacción: o se crean cliente + usuario y se consume el OTP, o no cambia nada."""
    import pymysql
    from claves import validar_clave
    from database import get_connection

    dni = request.form.get('dni', '').strip()
    nombre = request.form.get('nombre', '').strip()
    telf = normalizar(request.form.get('telefono', '').strip())
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    password2 = request.form.get('password2', '').strip()
    codigo_otp = request.form.get('codigo_otp', '').strip()

    # Validaciones que no necesitan la base
    if not all([dni, nombre, telf, email, password, password2, codigo_otp]):
        return jsonify({'success': False, 'error': 'Todos los campos son obligatorios'})
    if password != password2:
        return jsonify({'success': False, 'error': 'Las contraseñas no coinciden'})
    error_clave = validar_clave(password, [dni, nombre, telf, email.split('@')[0]])
    if error_clave:
        return jsonify({'success': False, 'error': error_clave})

    conn = get_connection()
    if conn is None:
        return jsonify({'success': False, 'error': 'Servicio no disponible. Intenta en unos minutos.'}), 503

    try:
        with conn.cursor() as cur:
            conn.begin()

            # 1) OTP vigente de esa cédula; FOR UPDATE evita que dos registros lo usen a la vez
            cur.execute(
                """SELECT id, telefono FROM t_otp
                   WHERE dni = %s AND codigo = %s AND usado = 0
                     AND fecha_expiracion > NOW()
                   ORDER BY id DESC LIMIT 1 FOR UPDATE""",
                (dni, codigo_otp))
            otp = cur.fetchone()
            if not otp:
                conn.rollback()
                return jsonify({'success': False, 'error': 'Código OTP inválido o expirado'})

            # 2) El código solo vale para el teléfono al que se envió
            if normalizar(otp['telefono']) != telf:
                conn.rollback()
                return jsonify({'success': False, 'error': 'El código no fue enviado a este teléfono'})

            # 3) Duplicados
            for col, val, msg in (('dni', dni, 'Ya existe un cliente con esa cédula'),
                                  ('email', email, 'Ya existe un cliente con ese email'),
                                  ('telf', telf, 'Ya existe un cliente con ese teléfono')):
                cur.execute(f"SELECT id FROM t_cliente WHERE {col} = %s LIMIT 1", (val,))
                if cur.fetchone():
                    conn.rollback()
                    return jsonify({'success': False, 'error': msg})
            cur.execute("SELECT id FROM t_usuario WHERE login = %s LIMIT 1", (dni,))
            if cur.fetchone():
                conn.rollback()
                return jsonify({'success': False, 'error': 'Ya existe un usuario con esa cédula'})

            # 4) Cliente + usuario (login = cédula) + OTP consumido
            cur.execute(
                """INSERT INTO t_cliente
                   (id_tipo_estado_cliente, id_reputacion, dni, nombre, telf, email,
                    email_verificado, telefono_verificado, fecha_registro)
                   VALUES (1, 1, %s, %s, %s, %s, 0, 1, CURDATE())""",
                (dni, nombre, telf, email))
            cur.execute(
                """INSERT INTO t_usuario
                   (id_estado_usuario, id_nivel, nombre, login, clave)
                   VALUES (1, 4, %s, %s, %s)""",
                (nombre, dni, sha1_hash(password)))
            cur.execute("UPDATE t_otp SET usado = 1 WHERE id = %s", (otp['id'],))

        conn.commit()
        return jsonify({'success': True, 'mensaje': 'Registro exitoso'})
    except pymysql.err.IntegrityError as e:
        conn.rollback()
        print(f"Registro revertido (dato repetido): {e}", flush=True)
        return jsonify({'success': False, 'error': 'Ya existe un registro con esos datos'})
    except Exception as e:
        conn.rollback()
        print(f"Error en registro (se revirtió todo): {e}", flush=True)
        return jsonify({'success': False, 'error': 'No se pudo completar el registro. Intenta de nuevo.'}), 500
    finally:
        conn.close()


def obtener_ip_local():
    """Obtiene la IP local del dispositivo en la red WiFi."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def abrir_navegador(ip):
    """Abre el navegador con la URL del servidor."""
    url = f"http://{ip}:5000"
    print(f"\n>>> Abriendo navegador en: {url}\n")
    webbrowser.open(url)


# ============================================================
# RUTAS
# ============================================================
@app.route('/')
def index():
    """Landing pública de Tanishi Finance.
    Si ya hay sesión, va directo al panel correspondiente."""
    if session.get('logueado'):
        if session.get('id_nivel') == 4:
            return redirect(url_for('portal'))
        return redirect(url_for('dashboard'))
    return render_template('tanishi/index.html')


class BaseDatosNoDisponible(Exception):
    """La base de datos no respondió (apagada o sin conexión)."""


def query_estricto(sql, params=None):
    """Como query(..., fetchone=True), pero distingue 'no hay fila' de 'la base no responde'."""
    from database import get_connection
    conn = get_connection()
    if conn is None:
        raise BaseDatosNoDisponible('sin conexión')
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()
    except Exception as e:
        raise BaseDatosNoDisponible(str(e))
    finally:
        conn.close()


@app.errorhandler(BaseDatosNoDisponible)
def _base_datos_no_disponible(e):
    print(f"Base de datos no disponible: {e}", flush=True)
    return jsonify({'existe': False, 'error': 'db_no_disponible'}), 503


# ---------------------------------------------------------------------
# LÍMITES DE OTP (patch_08). En memoria: se reinician al reiniciar Flask.
# ---------------------------------------------------------------------
import time as _time

_LIM_LOCK = threading.Lock()
_LIM_EVENTOS = {}  # clave -> [marcas de tiempo]


def _lim_purgar(clave, ventana, ahora):
    ev = [t for t in _LIM_EVENTOS.get(clave, []) if ahora - t < ventana]
    if ev:
        _LIM_EVENTOS[clave] = ev
    else:
        _LIM_EVENTOS.pop(clave, None)
    return ev


def _lim_excedido(clave, maximo, ventana):
    ahora = _time.time()
    with _LIM_LOCK:
        return len(_lim_purgar(clave, ventana, ahora)) >= maximo


def _lim_anotar(clave, ventana):
    ahora = _time.time()
    with _LIM_LOCK:
        ev = _lim_purgar(clave, ventana, ahora)
        ev.append(ahora)
        _LIM_EVENTOS[clave] = ev
        if len(_LIM_EVENTOS) > 5000:  # evita crecer sin límite
            for k in list(_LIM_EVENTOS)[:1000]:
                _LIM_EVENTOS.pop(k, None)


def _lim_limpiar(clave):
    with _LIM_LOCK:
        _LIM_EVENTOS.pop(clave, None)


def _json_limite(msg, seg=None):
    r = jsonify({'success': False, 'error': msg})
    r.status_code = 429
    if seg:
        r.headers['Retry-After'] = str(seg)
    return r


def _otp_guardia_envio():
    """None si el código puede enviarse; si no, la respuesta de rechazo."""
    ip = request.remote_addr or '?'
    dni = request.form.get('dni', '').strip()
    contacto = request.form.get('contacto', '').strip()
    canal = request.form.get('canal', 'whatsapp').strip().lower()
    tel = normalizar(contacto) if (contacto and canal != 'email') else ''
    if contacto and canal != 'email':
        import re as _re
        if not _re.fullmatch(r'[0-9]{5,12}', dni):
            return jsonify({'success': False, 'error': 'Cédula inválida: solo números (5 a 12 dígitos)'})

    # Un teléfono que ya pertenece a OTRO cliente no recibe códigos
    if tel and dni:
        otro = query("SELECT dni FROM t_cliente WHERE telf = %s AND dni <> %s LIMIT 1", (tel, dni), fetchone=True)
        if otro:
            return jsonify({'success': False, 'error': 'Ese teléfono ya está registrado'})

    limites = [('otp_ip:' + ip, 20, 3600), ('otp_dni:' + dni, 5, 3600),
               ('otp_gap:' + (tel or dni), 1, 45)]
    if tel:
        limites.append(('otp_tel:' + tel, 3, 900))
    for clave, maximo, ventana in limites:
        if _lim_excedido(clave, maximo, ventana):
            return _json_limite('Demasiados códigos solicitados. Intenta de nuevo en unos minutos.', ventana)
    for clave, _maximo, ventana in limites:
        _lim_anotar(clave, ventana)
    return None


def _validar_registro_form():
    """None si los datos del registro son válidos; si no, la respuesta de rechazo (patch_09)."""
    import re as _re
    f = request.form
    dni = f.get('dni', '').strip()
    nombre = ' '.join(f.get('nombre', '').split())
    email = f.get('email', '').strip()
    if not _re.fullmatch(r'[0-9]{5,12}', dni):
        return jsonify({'success': False, 'error': 'Cédula inválida: solo números (5 a 12 dígitos)'})
    palabras = [w for w in nombre.split(' ') if len(w) > 1]
    if not (5 <= len(nombre) <= 80) or len(palabras) < 2 or not all(c.isalpha() or c in " '.-" for c in nombre):
        return jsonify({'success': False, 'error': 'Nombre inválido: escribe nombre y apellido, solo letras'})
    if len(email) > 120 or not _re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        return jsonify({'success': False, 'error': 'Email inválido'})
    if not normalizar(f.get('telefono', '').strip()):
        return jsonify({'success': False, 'error': 'Teléfono inválido'})
    return None


def _otp_sin_detalles(resp):
    """El detalle interno de un envío fallido queda en el log; al navegador va un mensaje genérico."""
    r = resp[0] if isinstance(resp, tuple) else resp
    datos = r.get_json(silent=True) if hasattr(r, 'get_json') else None
    if datos is not None and not datos.get('success') and 'sin_whatsapp' in str(datos.get('error', '')):
        print(f"OTP no enviado: {datos.get('error')}", flush=True)
        return jsonify({'success': False, 'error': 'Ese número no tiene WhatsApp. Revisa el teléfono.'})
    if datos is not None and not datos.get('success') and str(datos.get('error', '')).startswith('No se pudo enviar'):
        print(f"OTP no enviado: {datos.get('error')}", flush=True)
        return jsonify({'success': False, 'error': 'No se pudo enviar el código. Intenta de nuevo en unos minutos.'})
    return resp


def _otp_con_intentos(fn):
    """Ejecuta fn() y cuenta los códigos OTP fallidos por cédula e IP (bloqueo tras 5 / 20 en 15 min)."""
    dni = request.form.get('dni', '').strip()
    ip = request.remote_addr or '?'
    if _lim_excedido('otp_fallos:' + dni, 5, 900) or _lim_excedido('otp_fallos_ip:' + ip, 20, 900):
        return _json_limite('Demasiados intentos con el código. Espera unos minutos.', 900)
    resp = fn()
    r = resp[0] if isinstance(resp, tuple) else resp
    datos = r.get_json(silent=True) if hasattr(r, 'get_json') else None
    if datos is not None:
        if datos.get('success'):
            _lim_limpiar('otp_fallos:' + dni)
        elif 'código' in str(datos.get('error', '')).lower():
            _lim_anotar('otp_fallos:' + dni, 900)
            _lim_anotar('otp_fallos_ip:' + ip, 900)
    return resp


@app.route('/api/validar_campo', methods=['POST'])
def route_validar_campo():
    """Endpoint: valida si un campo ya existe."""
    return validar_campos_unicos()


@app.route('/api/enviar_otp', methods=['POST'])
def route_enviar_otp():
    """Endpoint: envía un código OTP."""
    rechazo = _otp_guardia_envio()
    if rechazo is not None:
        return rechazo
    return _otp_sin_detalles(enviar_otp())


@app.route('/api/verificar_otp', methods=['POST'])
def route_verificar_otp():
    """Endpoint: verifica un código OTP."""
    return _otp_con_intentos(verificar_otp)


@app.route('/api/registro_cliente', methods=['POST'])
def route_registro_cliente():
    """Endpoint: registra un cliente nuevo."""
    rechazo = _validar_registro_form()
    if rechazo is not None:
        return rechazo
    return _otp_con_intentos(registro_cliente)


@app.route('/registro', methods=['GET'])
def registro_view():
    """Vista: formulario de registro."""
    return redirect(url_for('login'))


@app.route('/verificar', methods=['GET'])
def verificar_view():
    """Vista: verificación OTP."""
    return render_template('verificar.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Formulario de login y validación."""
    if request.method == 'POST':
        usuario = request.form.get('txt_nombre_ususario', '').strip()
        password = request.form.get('txt_pass', '').strip()
        usuario = usuario[:60]
        if not usuario or not password:
            flash('Escribe tu usuario y contraseña', 'danger')
            return redirect(url_for('login'))
        ip = request.remote_addr or '?'
        k_ui = f'login_fallos_ui:{usuario.lower()}|{ip}'
        k_ip = f'login_fallos_ip:{ip}'
        k_u = f'login_fallos_u:{usuario.lower()}'
        if _lim_excedido(k_ui, 5, 900) or _lim_excedido(k_ip, 20, 900) or _lim_excedido(k_u, 15, 900):
            flash('Demasiados intentos. Espera unos minutos e inténtalo de nuevo.', 'danger')
            return redirect(url_for('login'))

        # Buscar usuario en la BD
        try:
            user = query_estricto(
                "SELECT * FROM t_usuario WHERE login = %s",
                (usuario,)
            )
        except BaseDatosNoDisponible:
            flash('Servicio no disponible. Intenta de nuevo en unos minutos.', 'danger')
            return redirect(url_for('login'))

        if user:
            import hash_clave as _hc
            _ok, _mig = _hc.verificar(password, user.get('clave'), user.get('clave_v2'))
            if not _ok:
                user = None
            elif _mig:
                try:
                    query('UPDATE t_usuario SET clave_v2 = %s WHERE id = %s', (_hc.hash_fuerte(password), user['id']), commit=True)
                except Exception:
                    pass
        if user:
            # Bloquear usuarios inactivos ANTES de crear la sesión
            if user['id_estado_usuario'] != 1:
                flash('Usuario Inactivo', 'danger')
                return redirect(url_for('login'))
            _lim_limpiar(k_ui)
            _lim_limpiar(k_u)
            session.clear()  # evita fijación de sesión
            # Guardar datos en sesión
            session['logueado'] = True
            session['id'] = user['id']
            session['id_estado_usuario'] = user['id_estado_usuario']
            session['id_nivel'] = user['id_nivel']
            session['nombre'] = user['nombre']
            session['login'] = user['login']
            session['email'] = user.get('email') or ''


            # Si es CLIENTE (nivel 4) -> buscar en t_cliente y redirigir al portal
            if user['id_nivel'] == 4:
                cliente = query(
                    "SELECT id, nombre, dni, telf, email FROM t_cliente WHERE dni = %s LIMIT 1",
                    (user['login'],),
                    fetchone=True
                )
                if cliente:
                    session['cliente_id'] = cliente['id']
                    session['cliente_nombre'] = cliente['nombre']
                    session['cliente_dni'] = cliente['dni']
                    session['email'] = cliente.get('email') or ''
                    return redirect(url_for('portal'))
                else:
                    session.clear()
                    flash('No se encontró el cliente asociado a este usuario', 'danger')
                    return redirect(url_for('login'))

            # Admin, Cobrador, Socio -> dashboard
            return redirect(url_for('dashboard'))
        else:
            for _k in (k_ui, k_ip, k_u):
                _lim_anotar(_k, 900)
            flash('Usuario o Clave Invalidos', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')



# Ruta antigua DESACTIVADA (cambiaba la clave al instante). Ahora: recuperacion.py
def api_recuperar_password():
    dato = request.form.get('dato', '').strip()
    if not dato:
        return jsonify({"success": False, "message": "Ingresa un correo o cédula válida."})

    user = query("SELECT id, nombre, email, login FROM t_usuario WHERE email = %s OR login = %s LIMIT 1", (dato, dato), fetchone=True)
    
    if not user:
        return jsonify({"success": False, "message": "No se encontró un usuario con ese correo o cédula."})
    
    if not user.get('email'):
        return jsonify({"success": False, "message": "El usuario no tiene un correo registrado."})

    import secrets
    import string
    import hashlib
    
    alphabet = string.ascii_letters + string.digits
    nueva_pass = ''.join(secrets.choice(alphabet) for i in range(8))
    hash_pass = hashlib.sha1(nueva_pass.encode('utf-8')).hexdigest()
    
    query("UPDATE t_usuario SET clave = %s, clave_v2 = NULL WHERE id = %s", (hash_pass, user['id']), commit=True)

    try:
        from notificaciones import enviar_email
        asunto = "Recuperación de Contraseña - Pagadiario Web"
        
        # Usamos triples comillas para evitar errores de saltos de línea
        cuerpo = f"""Hola {user['nombre']},

Has solicitado recuperar tu contraseña.

Tu nueva contraseña temporal es: {nueva_pass}

Por seguridad, te recomendamos cambiarla al iniciar sesión.

Atentamente,
El equipo de Pagadiario."""
        
        exito, mensaje = enviar_email(user['email'], asunto, cuerpo)

        if exito:
            return jsonify({"success": True, "message": f"Contraseña enviada al correo: {user['email']}"})
        else:
            return jsonify({"success": False, "message": f"Error al enviar correo: {mensaje}"})
            
    except Exception as e:
        return jsonify({"success": False, "message": f"Error interno del servidor: {str(e)}"})









@app.route('/api/validar_login_usuario', methods=['POST'])
def api_validar_login_usuario():
    ip = request.remote_addr or '?'
    if _lim_excedido('chk_ip_m:' + ip, 60, 60) or _lim_excedido('chk_ip_h:' + ip, 600, 3600):
        return jsonify({"existe": False, "limitado": True}), 429
    _lim_anotar('chk_ip_m:' + ip, 60)
    _lim_anotar('chk_ip_h:' + ip, 3600)

    dni = request.form.get('valor', '').strip()[:60]
    if not dni:
        return jsonify({"existe": False})

    user = query_estricto("SELECT id, nombre FROM t_usuario WHERE login = %s LIMIT 1", (dni,))

    if user:
        # Foto real en static/avatars; si no hay, el navegador dibuja las iniciales (el nombre no sale del servidor)
        avatar_filename = f"avatars/{user['id']}.jpg"
        if os.path.exists(os.path.join(app.static_folder, avatar_filename)):
            return jsonify({"existe": True, "avatar": f"/static/{avatar_filename}"})
        palabras = (user['nombre'] or '').split()
        elegidas = palabras[:1] + palabras[-1:] if len(palabras) > 1 else palabras[:1]
        iniciales = ''.join(w[0] for w in elegidas).upper()
        return jsonify({"existe": True, "iniciales": iniciales[:2] or '?'})

    return jsonify({"existe": False})

@app.route('/dashboard')
def dashboard():
    """Panel principal con tema oscuro estilo Premium."""
    if not session.get('logueado'):
        flash('Debe Iniciar Sesion', 'warning')
        return redirect(url_for('login'))
    
    from datetime import date
    hoy = date.today()
    hoy_str = hoy.strftime('%Y-%m-%d')
    
    # --- Filtros de fecha ---
    mes_ini = int(request.args.get('mes_ini', hoy.month))
    anio_ini = int(request.args.get('anio_ini', hoy.year))
    mes_fin = int(request.args.get('mes_fin', hoy.month))
    anio_fin = int(request.args.get('anio_fin', hoy.year))
    
    # --- KPIs ---
    from models.cliente import ClienteModel
    total_clientes = ClienteModel.contar()
    
    from models.caja import CajaModel
    caja_principal = CajaModel.obtener_caja_principal()
    total_caja = float(caja_principal['total_caja']) if caja_principal else 0
    
    # Cobrado del mes actual
    resultado = query("""
        SELECT COALESCE(SUM(monto), 0) AS total
        FROM t_det_prestamo
        WHERE MONTH(fecha_cobro) = %s AND YEAR(fecha_cobro) = %s
    """, (hoy.month, hoy.year), fetchone=True)
    cobrado_mes = float(resultado['total']) if resultado else 0
    
    # Total por cobrar
    resultado = query("""
        SELECT COALESCE(SUM(total_debe), 0) AS total
        FROM t_prestamo
        WHERE id_estado_prestamo = 2
    """, fetchone=True)
    total_por_cobrar = float(resultado['total']) if resultado else 0
    
    # --- Gráfico 1: Cobros por mes (últimos 12 meses) ---
    grafico_cobros = []
    for i in range(11, -1, -1):
        fecha = hoy.replace(day=1) - timedelta(days=i*30)
        mes = fecha.month
        anio = fecha.year
        r = query("""
            SELECT COALESCE(SUM(monto), 0) AS total
            FROM t_det_prestamo
            WHERE MONTH(fecha_cobro) = %s AND YEAR(fecha_cobro) = %s
        """, (mes, anio), fetchone=True)
        valor = float(r['total']) if r else 0
        grafico_cobros.append({
            'etiqueta': f"{['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'][mes-1]} {str(anio)[2:]}",
            'valor': valor
        })
    
    # --- Gráfico 2: Préstamos por mes (últimos 12 meses) ---
    grafico_prestamos = []
    for i in range(11, -1, -1):
        fecha = hoy.replace(day=1) - timedelta(days=i*30)
        mes = fecha.month
        anio = fecha.year
        r = query("""
            SELECT COALESCE(SUM(monto_prestado), 0) AS total
            FROM t_prestamo
            WHERE MONTH(fecha_prestamo) = %s AND YEAR(fecha_prestamo) = %s
        """, (mes, anio), fetchone=True)
        valor = float(r['total']) if r else 0
        grafico_prestamos.append({
            'etiqueta': f"{['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'][mes-1]} {str(anio)[2:]}",
            'valor': valor
        })
    
    # --- Ranking Cobradores ---
    ranking_cobradores = query("""
        SELECT 
            COALESCE(cb.nombre, 'Sin asignar') AS cobrador,
            COUNT(dp.id) AS total_pagos,
            COALESCE(SUM(dp.monto), 0) AS total_cobrado
        FROM t_det_prestamo dp
        LEFT JOIN t_prestamo p ON dp.id_prestamo = p.id
        LEFT JOIN t_cobrador cb ON p.id_cobrador = cb.id
        WHERE MONTH(dp.fecha_cobro) = %s AND YEAR(dp.fecha_cobro) = %s
        GROUP BY cb.nombre
        ORDER BY total_cobrado DESC
        LIMIT 10
    """, (hoy.month, hoy.year), fetchall=True) or []
    
    # --- Top Deudores ---
    top_deudores_raw = query("""
        SELECT 
            c.nombre AS cliente,
            c.dni AS cliente_dni,
            SUM(p.total_debe) AS deuda
        FROM t_prestamo p
        LEFT JOIN t_cliente c ON p.id_cliente = c.id
        WHERE p.id_estado_prestamo = 2 AND p.total_debe > 0
        GROUP BY c.id, c.nombre, c.dni
        ORDER BY deuda DESC
        LIMIT 10
    """, fetchall=True) or []
    
    max_deuda = top_deudores_raw[0]['deuda'] if top_deudores_raw else 1
    top_deudores = []
    for d in top_deudores_raw:
        porcentaje = (float(d['deuda']) / float(max_deuda) * 100) if max_deuda else 0
        top_deudores.append({
            'cliente': d['cliente'] or 'Sin nombre',
            'deuda': float(d['deuda']),
            'porcentaje': porcentaje
        })
    
    # --- Período (selector de fechas) + datos del gráfico 3D ---
    from datetime import datetime as _dt
    def _f(v):
        try:
            return _dt.strptime(v, '%Y-%m-%d').date()
        except Exception:
            return None
    p_ini = _f(request.args.get('start', ''))
    p_fin = _f(request.args.get('end', ''))
    p_label = request.args.get('label') or 'Reset (All)'
    if not (p_ini and p_fin):
        p_ini, p_fin, p_label = date(2000, 1, 1), hoy, 'Reset (All)'
    top_clientes = query("""
        SELECT c.nombre AS cliente, COALESCE(SUM(p.monto_prestado), 0) AS total
        FROM t_prestamo p LEFT JOIN t_cliente c ON p.id_cliente = c.id
        WHERE DATE(p.fecha_prestamo) BETWEEN %s AND %s
        GROUP BY c.id, c.nombre ORDER BY total DESC LIMIT 10
    """, (p_ini, p_fin), fetchall=True) or []
    est = query("SELECT id_tipo_estado_cliente AS e, COUNT(*) AS n FROM t_cliente GROUP BY id_tipo_estado_cliente", fetchall=True) or []
    conteo = {r['e']: int(r['n']) for r in est}
    periodo = {
        'inicio': p_ini.strftime('%Y-%m-%d'), 'fin': p_fin.strftime('%Y-%m-%d'), 'label': p_label,
        'top_clientes': [{'nombre': r['cliente'] or 'Sin nombre', 'total': float(r['total'])} for r in top_clientes],
        'activos': conteo.get(1, 0), 'inactivos': conteo.get(2, 0), 'lista_negra': conteo.get(3, 0),
    }

    # --- Datos para el template ---
    meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                     'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    anios_disponibles = list(range(hoy.year - 3, hoy.year + 1))
    
    data_usuario = {
        'id_usuario': session.get('id'),
        'nombre_usuario': session.get('nombre'),
        'id_nivel': session.get('id_nivel')
    }
    
    data_panel = {
        'cliente_registrados': total_clientes,
        'dinero_capital': total_caja,
        'dinero_recogido': cobrado_mes,
        'total_por_cobrar': total_por_cobrar,
        'ranking_cobradores': ranking_cobradores,
        'top_deudores': top_deudores,
        'grafico_cobros': grafico_cobros,
        'grafico_prestamos': grafico_prestamos,
    }
    
    return render_template('dashboard.html',
                           usuario=data_usuario,
                           panel=data_panel,
                           ahora=hoy.strftime('%d/%m/%Y %H:%M'),
                           mes_actual=hoy.month,
                           meses_nombres=meses_nombres,
                           anios_disponibles=anios_disponibles,
                           periodo=periodo)


# ============================================================
# RUTAS PLACEHOLDER (por ahora, se implementarán después)
# ============================================================
# ============================================================
# MÓDULO DE CLIENTES (REAL)
# ============================================================
from models.cliente import ClienteModel

@app.route('/clientes')
def clientes():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    lista_clientes = ClienteModel.listar_todos()
    def _v(sql):
        r = query(sql, fetchone=True)
        return float(r['v']) if r and r['v'] is not None else 0
    stats = {
        'prestado': _v("SELECT COALESCE(SUM(monto_prestado),0) AS v FROM t_prestamo"),
        'cobros_mes': _v("SELECT COALESCE(SUM(monto),0) AS v FROM t_det_prestamo WHERE MONTH(fecha_cobro)=MONTH(CURDATE()) AND YEAR(fecha_cobro)=YEAR(CURDATE())"),
        'por_cobrar': _v("SELECT COALESCE(SUM(total_debe),0) AS v FROM t_prestamo WHERE id_estado_prestamo = 2"),
        'con_deuda': _v("SELECT COUNT(DISTINCT id_cliente) AS v FROM t_prestamo WHERE id_estado_prestamo = 2 AND total_debe > 0"),
    }
    top = query("SELECT c.nombre AS n, SUM(p.monto_prestado) AS m, SUM(CASE WHEN p.id_estado_prestamo = 2 THEN p.total_debe ELSE 0 END) AS d FROM t_prestamo p JOIN t_cliente c ON c.id = p.id_cliente GROUP BY c.id, c.nombre ORDER BY m DESC LIMIT 10", fetchall=True) or []
    top = [{'n': t['n'], 'm': float(t['m'] or 0), 'd': float(t['d'] or 0)} for t in top]
    ex = {}
    for r in (query("SELECT id, email_verificado AS ev, telefono_verificado AS tv FROM t_cliente", fetchall=True) or []):
        ex[r['id']] = {'ev': int(r['ev'] or 0), 'tv': int(r['tv'] or 0), 'deu': 0}
    for r in (query("SELECT DISTINCT id_cliente AS i FROM t_prestamo WHERE id_estado_prestamo = 2 AND total_debe > 0", fetchall=True) or []):
        if r['i'] in ex:
            ex[r['i']]['deu'] = 1
    for r in (query("SELECT s.id_cliente AS i, s.estado AS e FROM t_solicitud_prestamo s JOIN (SELECT id_cliente, MAX(id) AS m FROM t_solicitud_prestamo GROUP BY id_cliente) x ON s.id = x.m", fetchall=True) or []):
        if r['i'] in ex:
            ex[r['i']]['sol'] = r['e']
    return render_template('clientes.html', clientes=lista_clientes, stats=stats, top=top, ex=ex)


@app.route('/api/clientes_top')
def api_clientes_top():
    if not session.get('logueado'):
        return jsonify([]), 401
    d = request.args.get('start') or '2000-01-01'
    h = request.args.get('end') or '2100-01-01'
    r = query("SELECT c.nombre AS n, SUM(p.monto_prestado) AS m, SUM(CASE WHEN p.id_estado_prestamo = 2 THEN p.total_debe ELSE 0 END) AS d FROM t_prestamo p JOIN t_cliente c ON c.id = p.id_cliente WHERE p.fecha_prestamo BETWEEN %s AND %s GROUP BY c.id, c.nombre ORDER BY m DESC LIMIT 10", (d, h), fetchall=True) or []
    return jsonify([{'n': t['n'], 'm': float(t['m'] or 0), 'd': float(t['d'] or 0)} for t in r])

@app.route('/api/clientes_stats')
def api_clientes_stats():
    if not session.get('logueado'):
        return jsonify({}), 401
    p = (request.args.get('start') or '2000-01-01', request.args.get('end') or '2100-01-01')
    def _v(sql):
        r = query(sql, p, fetchone=True)
        return float(r['v']) if r and r['v'] is not None else 0
    return jsonify({
        'total': _v("SELECT COUNT(*) AS v FROM t_cliente WHERE fecha_registro BETWEEN %s AND %s"),
        'activos': _v("SELECT COUNT(DISTINCT id_cliente) AS v FROM t_prestamo WHERE fecha_prestamo BETWEEN %s AND %s"),
        'cobros': _v("SELECT COALESCE(SUM(monto),0) AS v FROM t_det_prestamo WHERE fecha_cobro BETWEEN %s AND %s"),
        'prestado': _v("SELECT COALESCE(SUM(monto_prestado),0) AS v FROM t_prestamo WHERE fecha_prestamo BETWEEN %s AND %s"),
        'por_cobrar': _v("SELECT COALESCE(SUM(total_debe),0) AS v FROM t_prestamo WHERE id_estado_prestamo = 2 AND fecha_prestamo BETWEEN %s AND %s"),
        'con_deuda': _v("SELECT COUNT(DISTINCT id_cliente) AS v FROM t_prestamo WHERE id_estado_prestamo = 2 AND total_debe > 0 AND fecha_prestamo BETWEEN %s AND %s")
    })

@app.route('/api/clientes_series')
def api_clientes_series():
    import datetime as _dt
    if not session.get('logueado'):
        return jsonify({}), 401
    N = 8
    hoy = _dt.date.today()
    try:
        e = _dt.date.fromisoformat(request.args.get('end') or str(hoy))
        s = _dt.date.fromisoformat(request.args.get('start') or '2000-01-01')
    except ValueError:
        return jsonify({}), 400
    e = min(e, hoy)
    if s.year <= 2000:
        r = query("SELECT LEAST((SELECT MIN(fecha_prestamo) FROM t_prestamo),(SELECT MIN(fecha_registro) FROM t_cliente),(SELECT MIN(fecha_cobro) FROM t_det_prestamo)) AS v", fetchone=True)
        if r and r['v']:
            s = r['v'].date() if hasattr(r['v'], 'date') else r['v']
    ancho = max(1, -(-((e - s).days + 1) // N))
    def _serie(sql):
        v = [0.0] * N
        for r in (query(sql, (s, e), fetchall=True) or []):
            d = r['d'].date() if hasattr(r['d'], 'date') else r['d']
            i = min(N - 1, max(0, (d - s).days // ancho))
            v[i] += float(r['v'] or 0)
        return v
    return jsonify({
        'total': _serie("SELECT fecha_registro AS d, COUNT(*) AS v FROM t_cliente WHERE fecha_registro BETWEEN %s AND %s GROUP BY fecha_registro"),
        'activos': _serie("SELECT fecha_prestamo AS d, COUNT(DISTINCT id_cliente) AS v FROM t_prestamo WHERE fecha_prestamo BETWEEN %s AND %s GROUP BY fecha_prestamo"),
        'cobros': _serie("SELECT fecha_cobro AS d, SUM(monto) AS v FROM t_det_prestamo WHERE fecha_cobro BETWEEN %s AND %s GROUP BY fecha_cobro"),
        'prestado': _serie("SELECT fecha_prestamo AS d, SUM(monto_prestado) AS v FROM t_prestamo WHERE fecha_prestamo BETWEEN %s AND %s GROUP BY fecha_prestamo"),
        'por_cobrar': _serie("SELECT fecha_prestamo AS d, SUM(total_debe) AS v FROM t_prestamo WHERE id_estado_prestamo = 2 AND fecha_prestamo BETWEEN %s AND %s GROUP BY fecha_prestamo"),
        'con_deuda': _serie("SELECT fecha_prestamo AS d, COUNT(DISTINCT id_cliente) AS v FROM t_prestamo WHERE id_estado_prestamo = 2 AND total_debe > 0 AND fecha_prestamo BETWEEN %s AND %s GROUP BY fecha_prestamo")
    })
@app.route('/cliente/nuevo', methods=['GET', 'POST'])
def cliente_nuevo():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        datos = {
            'dni': request.form.get('dni', ''),
            'nombre': request.form.get('nombre', ''),
            'nombre_negocio': request.form.get('nombre_negocio', ''),
            'telf': normalizar(request.form.get('telf', '')),
            'email': request.form.get('email', ''),
            'direccion': request.form.get('direccion', ''),
            'direccion_cobro': request.form.get('direccion_cobro', ''),
            'referencia_1': request.form.get('referencia_1', ''),
            'referencia_2': request.form.get('referencia_2', ''),
            'id_tipo_estado_cliente': 1,
            'id_reputacion': 1,
            'id_documentacion': 1
        }
        ClienteModel.crear(datos)
        flash('Cliente creado correctamente', 'success')
        return redirect(url_for('clientes'))
    
    return render_template('cliente_form.html', cliente=None, titulo='Nuevo Cliente')

@app.route('/cliente/ver/<int:id_cliente>')
def cliente_ver(id_cliente):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    cliente = ClienteModel.obtener_por_id(id_cliente)
    if not cliente:
        flash('Cliente no encontrado', 'danger')
        return redirect(url_for('clientes'))
    prestamos = PrestamoModel.listar_por_cliente(id_cliente) or []
    activos = [p for p in prestamos if p['estado_prestamo'] == 'Activo']
    stats = {
        'total': len(prestamos),
        'activos': len(activos),
        'capital': sum(float(p['monto_prestado'] or 0) for p in prestamos if p['estado_prestamo'] != 'Por Aprobar'),
        'debe': sum(float(p['total_debe'] or 0) for p in activos),
    }
    return render_template('cliente_ver.html', cliente=cliente, prestamos=prestamos, stats=stats)

@app.route('/cliente/editar/<int:id_cliente>', methods=['GET', 'POST'])
def cliente_editar(id_cliente):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    cliente = ClienteModel.obtener_por_id(id_cliente)
    if not cliente:
        flash('Cliente no encontrado', 'danger')
        return redirect(url_for('clientes'))
    
    if request.method == 'POST':
        datos = {
            'dni': request.form.get('dni', ''),
            'nombre': request.form.get('nombre', ''),
            'nombre_negocio': request.form.get('nombre_negocio', ''),
            'telf': normalizar(request.form.get('telf', '')),
            'email': request.form.get('email', ''),
            'direccion': request.form.get('direccion', ''),
            'direccion_cobro': request.form.get('direccion_cobro', ''),
            'referencia_1': request.form.get('referencia_1', ''),
            'referencia_2': request.form.get('referencia_2', ''),
        }
        ClienteModel.actualizar(id_cliente, datos)
        flash('Cliente actualizado correctamente', 'success')
        return redirect(url_for('clientes'))
    
    return render_template('cliente_form.html', cliente=cliente, titulo='Editar Cliente')

@app.route('/cliente/eliminar/<int:id_cliente>')
def cliente_eliminar(id_cliente):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    ClienteModel.eliminar(id_cliente)
    flash('Cliente eliminado correctamente', 'success')
    return redirect(url_for('clientes'))

@app.route('/codeudores')
def codeudores():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    return render_template('placeholder.html', titulo='Codeudores', icono='fa-file-signature')

# ============================================================
# MÓDULO DE IMPORTACIÓN DE CONTACTOS (VCF)
# ============================================================
from models.vcf_import import VCFImportModel

UPLOAD_VCF = os.path.join(os.path.dirname(__file__), 'static', 'vcf_uploads')
os.makedirs(UPLOAD_VCF, exist_ok=True)

# Variable global temporal para guardar los contactos analizados
_contactos_temp = {}

@app.route('/importar_contactos/<tipo>', methods=['GET', 'POST'])
def importar_contactos(tipo):
    """Importar contactos desde VCF para Clientes, Usuarios, Cobradores o Socios."""
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if tipo not in ['clientes', 'usuarios', 'cobradores', 'socios']:
        flash('Tipo de importación no válido', 'danger')
        return redirect(url_for('dashboard'))
    
    contactos = None
    stats = None
    
    if request.method == 'POST':
        archivo = request.files.get('archivo_vcf')
        if not archivo or not archivo.filename:
            flash('Debes seleccionar un archivo VCF', 'warning')
            return redirect(url_for('importar_contactos', tipo=tipo))
        
        if not archivo.filename.lower().endswith('.vcf'):
            flash('El archivo debe ser .vcf', 'danger')
            return redirect(url_for('importar_contactos', tipo=tipo))
        
        # Guardar archivo
        import time
        nombre_archivo = f"vcf_{int(time.time())}.vcf"
        ruta = os.path.join(UPLOAD_VCF, nombre_archivo)
        archivo.save(ruta)
        
        # Parsear
        contactos = VCFImportModel.leer_archivo_vcf(ruta)
        
        if not contactos:
            flash('No se encontraron contactos en el archivo', 'warning')
            return redirect(url_for('importar_contactos', tipo=tipo))
        
        # Guardar temporalmente
        session_id = session.get('id')
        _contactos_temp[session_id] = {
            'tipo': tipo,
            'contactos': contactos
        }
        
        stats = VCFImportModel.estadisticas(contactos)
        flash(f'Se encontraron {len(contactos)} contactos', 'success')
    
    return render_template('importar_contactos.html',
                           tipo=tipo,
                           contactos=contactos,
                           stats=stats,
                           titulo=f'Importar Contactos - {tipo.capitalize()}')


@app.route('/importar_contactos/<tipo>/confirmar', methods=['POST'])
def importar_contactos_confirmar(tipo):
    """Confirma e inserta los contactos seleccionados."""
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    session_id = session.get('id')
    if session_id not in _contactos_temp:
        flash('Sesión de importación expirada', 'warning')
        return redirect(url_for('importar_contactos', tipo=tipo))
    
    datos = _contactos_temp[session_id]
    contactos = datos['contactos']
    
    seleccionados = request.form.getlist('seleccionados')
    insertados = 0
    
    for idx_str in seleccionados:
        idx = int(idx_str)
        if idx >= len(contactos):
            continue
        
        contacto = contactos[idx]
        
        # Obtener datos editados del formulario
        nombre = request.form.get(f'nombre_{idx}', '').strip()
        telefono = normalizar(request.form.get(f'telefono_{idx}', '').strip())
        email = request.form.get(f'email_{idx}', '').strip()
        direccion = request.form.get(f'direccion_{idx}', '').strip()
        
        if not nombre:
            continue
        
        # Insertar según el tipo
        if tipo == 'clientes':
            query("""
                INSERT INTO t_cliente 
                (id_tipo_estado_cliente, id_reputacion, dni, nombre, telf, email, direccion, direccion_cobro)
                VALUES (1, 1, %s, %s, %s, %s, %s, %s)
            """, ('', nombre, telefono, email, direccion, direccion), commit=True)
            insertados += 1
        
        elif tipo == 'cobradores':
            query("""
                INSERT INTO t_cobrador (nombre)
                VALUES (%s)
            """, (nombre,), commit=True)
            insertados += 1
        
        elif tipo == 'socios':
            query("""
                INSERT INTO t_socio (nombre)
                VALUES (%s)
            """, (nombre,), commit=True)
            insertados += 1
        
        elif tipo == 'usuarios':
            # Generar login automático
            login = nombre.lower().replace(' ', '_')[:20]
            import hashlib
            clave = hashlib.sha1(__import__('secrets').token_hex(16).encode('utf-8')).hexdigest()  # clave aleatoria: la cuenta nace inactiva
            query("""
                INSERT INTO t_usuario (id_estado_usuario, id_nivel, nombre, login, clave)
                VALUES (2, 2, %s, %s, %s)
            """, (nombre, login, clave), commit=True)
            insertados += 1
    
    # Limpiar temporal
    del _contactos_temp[session_id]
    
    flash(f'Se importaron {insertados} contactos como {tipo}', 'success')
    return redirect(url_for(tipo))
# ============================================================
# MÓDULO DE PRÉSTAMOS (REAL)
# ============================================================
from notificaciones import enviar_otp as enviar_otp_real
from models.prestamo import PrestamoModel
from models.cliente import ClienteModel

@app.route('/portal')
def portal():
    """Portal del cliente: solo ve SUS préstamos."""
    if not session.get('logueado') or session.get('id_nivel') != 4:
        return redirect(url_for('login'))

    cliente_id = session.get('cliente_id')
    if not cliente_id:
        flash('No se encontró información del cliente', 'danger')
        return redirect(url_for('login'))

    # Préstamos del cliente
    prestamos = query(
        """SELECT p.*,
                  e.descripcion AS estado_prestamo
           FROM t_prestamo p
           LEFT JOIN t_estado_prestamo e ON p.id_estado_prestamo = e.id
           WHERE p.id_cliente = %s
           ORDER BY p.id DESC""",
        (cliente_id,),
        fetchall=True
    ) or []

    # Para cada préstamo, calcular el total pagado
    for p in prestamos:
        pagado = query(
            "SELECT COALESCE(SUM(monto), 0) AS total_pagado FROM t_det_prestamo WHERE id_prestamo = %s",
            (p['id'],),
            fetchone=True
        )
        total_pagado = float(pagado['total_pagado']) if pagado else 0
        total_prestamo = float(p['total_prestado'] or 0)
        p['pagado'] = total_pagado
        p['saldo'] = total_prestamo - total_pagado
        p['porcentaje'] = (total_pagado / total_prestamo * 100) if total_prestamo > 0 else 0

    # Validar crédito vigente o mora
    tiene_prestamo_activo = False
    prestamo_activo_info = None
    esta_en_mora = False
    dias_mora = 0

    activo = query(
        """SELECT p.*,
                  COALESCE((SELECT SUM(monto) FROM t_det_prestamo WHERE id_prestamo = p.id), 0) AS total_pagado
           FROM t_prestamo p
           WHERE p.id_cliente = %s AND p.id_estado_prestamo = 2
           ORDER BY p.id DESC LIMIT 1""",
        (cliente_id,),
        fetchone=True
    )

    if activo:
        tiene_prestamo_activo = True
        saldo = float(activo['total_prestado'] or 0) - float(activo['total_pagado'] or 0)
        prestamo_activo_info = {
            'id': activo['id'],
            'valor': float(activo['monto_prestado'] or 0),
            'saldo': saldo,
            'fecha_inicio': activo['fecha_prestamo'],
            'fecha_final': activo['fecha_prox_cobro'],
        }
        dias_mora = int(activo['dias_mora'] or 0)
        if dias_mora > 0:
            esta_en_mora = True

    # Notificaciones no leídas
    notif = query(
        "SELECT COUNT(*) AS total FROM t_notificacion WHERE id_cliente = %s AND leida = 0",
        (cliente_id,),
        fetchone=True
    )
    notif_no_leidas = notif['total'] if notif else 0

    # Obtener datos completos del cliente
    cliente_datos = query(
        """SELECT id, dni, nombre, telf, email, ingreso_mensual,
                  direccion, nombre_negocio, referencia_1, referencia_2
           FROM t_cliente WHERE id = %s LIMIT 1""",
        (cliente_id,),
        fetchone=True
    ) or {}

    return render_template('portal.html',
                           cliente_nombre=session.get('cliente_nombre'),
                           cliente_dni=session.get('cliente_dni'),
                           cliente_datos=cliente_datos,
                           prestamos=prestamos,
                           tiene_prestamo_activo=tiene_prestamo_activo,
                           prestamo_activo_info=prestamo_activo_info,
                           esta_en_mora=esta_en_mora,
                           dias_mora=dias_mora,
                           notif_no_leidas=notif_no_leidas)


@app.route('/mi_perfil')
def mi_perfil():
    """Perfil del cliente."""
    if not session.get('logueado') or session.get('id_nivel') != 4:
        return redirect(url_for('login'))

    cliente_id = session.get('cliente_id')
    cliente = query(
        "SELECT c.*, e.descripcion AS estado FROM t_cliente c LEFT JOIN t_tipo_estado_cliente e ON c.id_tipo_estado_cliente = e.id WHERE c.id = %s",
        (cliente_id,),
        fetchone=True
    ) or {}

    notif = query(
        "SELECT COUNT(*) AS total FROM t_notificacion WHERE id_cliente = %s AND leida = 0",
        (cliente_id,),
        fetchone=True
    )
    notif_no_leidas = notif['total'] if notif else 0

    return render_template('mi_perfil.html',
                           cliente=cliente,
                           cliente_nombre=session.get('cliente_nombre'),
                           cliente_dni=session.get('cliente_dni'),
                           notif_no_leidas=notif_no_leidas)


@app.route('/cambiar_password', methods=['GET', 'POST'])
def cambiar_password():
    """Cambiar la contraseña del cliente."""
    if not session.get('logueado') or session.get('id_nivel') != 4:
        return redirect(url_for('login'))

    if request.method == 'POST':
        actual = request.form.get('password_actual', '').strip()
        nueva = request.form.get('password_nueva', '').strip()
        confirmar = request.form.get('password_confirmar', '').strip()

        user_id = session.get('id')

        if not all([actual, nueva, confirmar]):
            flash('Todos los campos son obligatorios', 'danger')
            return redirect(url_for('cambiar_password'))

        if nueva != confirmar:
            flash('Las contraseñas no coinciden', 'danger')
            return redirect(url_for('cambiar_password'))

        if len(nueva) < 10:
            flash('La contraseña debe tener al menos 10 caracteres', 'danger')
            return redirect(url_for('cambiar_password'))

        user = query(
            "SELECT * FROM t_usuario WHERE id = %s",
            (user_id,),
            fetchone=True
        )
        import hash_clave as _hc
        if not user or not _hc.verificar(actual, user.get('clave'), user.get('clave_v2'))[0]:
            flash('La contraseña actual es incorrecta', 'danger')
            return redirect(url_for('cambiar_password'))

        query(
            "UPDATE t_usuario SET clave = %s, clave_v2 = %s WHERE id = %s",
            (sha1_hash(nueva), _hc.hash_fuerte(nueva) if _hc.v2_activo() else None, user_id),
            commit=True
        )

        flash('Contraseña cambiada exitosamente', 'success')
        return redirect(url_for('portal'))

    cliente_id = session.get('cliente_id')
    notif = query(
        "SELECT COUNT(*) AS total FROM t_notificacion WHERE id_cliente = %s AND leida = 0",
        (cliente_id,),
        fetchone=True
    )
    notif_no_leidas = notif['total'] if notif else 0

    return render_template('cambiar_password.html',
                           cliente_nombre=session.get('cliente_nombre'),
                           cliente_dni=session.get('cliente_dni'),
                           notif_no_leidas=notif_no_leidas)


@app.route('/eliminar_cuenta')
def eliminar_cuenta():
    """Página para eliminar la cuenta del cliente."""
    if not session.get('logueado') or session.get('id_nivel') != 4:
        return redirect(url_for('login'))

    cliente_id = session.get('cliente_id')
    notif = query(
        "SELECT COUNT(*) AS total FROM t_notificacion WHERE id_cliente = %s AND leida = 0",
        (cliente_id,),
        fetchone=True
    )
    notif_no_leidas = notif['total'] if notif else 0

    return render_template('eliminar_cuenta.html',
                           cliente_nombre=session.get('cliente_nombre'),
                           cliente_dni=session.get('cliente_dni'),
                           notif_no_leidas=notif_no_leidas)


@app.route('/notificaciones_cliente')
def notificaciones_cliente():
    """Notificaciones del cliente."""
    if not session.get('logueado') or session.get('id_nivel') != 4:
        return redirect(url_for('login'))

    cliente_id = session.get('cliente_id')
    notificaciones = query(
        "SELECT * FROM t_notificacion WHERE id_cliente = %s ORDER BY fecha_creacion DESC LIMIT 50",
        (cliente_id,),
        fetchall=True
    ) or []

    notif = query(
        "SELECT COUNT(*) AS total FROM t_notificacion WHERE id_cliente = %s AND leida = 0",
        (cliente_id,),
        fetchone=True
    )
    notif_no_leidas = notif['total'] if notif else 0

    query("UPDATE t_notificacion SET leida = 1 WHERE id_cliente = %s AND leida = 0",
          (cliente_id,), commit=True)

    return render_template('notificaciones_cliente.html',
                           cliente_nombre=session.get('cliente_nombre'),
                           cliente_dni=session.get('cliente_dni'),
                           notificaciones=notificaciones,
                           notif_no_leidas=notif_no_leidas)


@app.route('/solicitar_prestamo', methods=['POST'])
def solicitar_prestamo():
    """El cliente envía una solicitud de nuevo préstamo."""
    if not session.get('logueado') or session.get('id_nivel') != 4:
        return redirect(url_for('login'))

    cliente_id = session.get('cliente_id')
    monto = float(request.form.get('monto', 0))
    plazo = int(request.form.get('plazo', 0))

    if monto < 50000 or monto > 20000000:
        flash('El monto debe estar entre $50.000 y $20.000.000', 'danger')
        return redirect(url_for('portal'))

    if plazo not in [7, 14, 21, 30, 45, 60]:
        flash('Plazo no válido', 'danger')
        return redirect(url_for('portal'))

    # Detectar crédito vigente o mora
    activo = query(
        """SELECT p.*, p.dias_mora
           FROM t_prestamo p
           WHERE p.id_cliente = %s AND p.id_estado_prestamo = 2
           ORDER BY p.id DESC LIMIT 1""",
        (cliente_id,),
        fetchone=True
    )

    estado = 'pendiente'
    comentario = f"Solicitud creada desde el portal del cliente. Monto: ${monto:,.0f}, Plazo: {plazo} días."

    if activo:
        if int(activo['dias_mora'] or 0) > 0:
            estado = 'rechazada'
            comentario = f"RECHAZADA POR SISTEMA: Cliente en mora ({activo['dias_mora']} días). " + comentario
        else:
            estado = 'rechazada'
            comentario = "RECHAZADA POR SISTEMA: Cliente con crédito vigente. " + comentario

    query(
        """INSERT INTO t_solicitud_prestamo
           (id_cliente, monto, plazo_dias, estado, comentario_admin)
           VALUES (%s, %s, %s, %s, %s)""",
        (cliente_id, monto, plazo, estado, comentario),
        commit=True
    )

    if estado == 'rechazada':
        flash('Tu solicitud fue registrada, pero no puede ser aprobada porque tienes un crédito vigente. El administrador la revisará.', 'warning')
    else:
        flash('Solicitud enviada correctamente. El administrador la revisará.', 'success')

    return redirect(url_for('portal'))


@app.route('/solicitudes')
def solicitudes():
    if not session.get('logueado') or session.get('id_nivel') == 4:
        return redirect(url_for('login'))
    lista = query(
        "SELECT s.*, c.nombre FROM t_solicitud_prestamo s LEFT JOIN t_cliente c ON c.id = s.id_cliente "
        "ORDER BY (s.fecha_respuesta IS NULL) DESC, s.id DESC LIMIT 100", fetchall=True) or []
    return render_template('solicitudes_pw.html', solicitudes=lista)


@app.route('/solicitudes/<int:id_sol>/<accion>', methods=['POST'])
def solicitud_resolver(id_sol, accion):
    if not session.get('logueado') or session.get('id_nivel') == 4:
        return redirect(url_for('login'))
    sol = query("SELECT * FROM t_solicitud_prestamo WHERE id = %s", (id_sol,), fetchone=True)
    if accion not in ('aprobar', 'rechazar') or not sol or sol['fecha_respuesta']:
        flash('Solicitud no válida o ya resuelta.', 'warning')
        return redirect(url_for('solicitudes'))
    estado = 'aprobada' if accion == 'aprobar' else 'rechazada'
    query("UPDATE t_solicitud_prestamo SET estado = %s, fecha_respuesta = NOW(), "
          "comentario_admin = CONCAT(COALESCE(comentario_admin, ''), %s) WHERE id = %s",
          (estado, ' | Resuelta por el administrador: ' + estado, id_sol), commit=True)
    crear_notificacion(sol['id_cliente'], 'solicitud', 'Solicitud ' + estado,
                       'El administrador {} tu solicitud de ${:,.0f}.'.format(estado, sol['monto']))
    flash('Solicitud ' + estado + '.', 'success')
    return redirect(url_for('solicitudes'))


def _extra_avisos():
    try:
        r = query("SELECT notificaciones FROM t_usuario WHERE id=%s", (session.get('id'),), fetchone=True)
        if r and int(r['notificaciones']) == 0:
            return {'avisos_on': False}
        venc = query("SELECT p.id, c.nombre, p.dias_mora, p.total_debe FROM t_prestamo p LEFT JOIN t_cliente c ON c.id=p.id_cliente WHERE p.id_estado_prestamo=2 AND p.dias_mora>0 ORDER BY p.dias_mora DESC LIMIT 5", fetchall=True) or []
        nv = query("SELECT COUNT(*) AS total FROM t_prestamo WHERE id_estado_prestamo=2 AND dias_mora>0", fetchone=True)
        pagos = query("SELECT d.id, d.id_prestamo, c.nombre, d.monto, d.fecha_cobro FROM t_det_prestamo d JOIN t_prestamo p ON p.id=d.id_prestamo LEFT JOIN t_cliente c ON c.id=p.id_cliente ORDER BY d.fecha_cobro DESC, d.id DESC LIMIT 5", fetchall=True) or []
        return {'avisos_on': True, 'av_venc': venc, 'av_venc_total': (nv or {}).get('total', 0), 'av_pagos': pagos}
    except Exception as e:
        print('avisos:', e)
        return {'avisos_on': False}


@app.context_processor
def inyectar_solicitudes_admin():
    """Campana del admin: solicitudes sin resolver por el administrador."""
    if not session.get('logueado'):
        return {}
    if session.get('id_nivel') == 4:
        cid = session.get('cliente_id')
        if not cid:
            return {}
        base = "SELECT s.id, s.id_cliente, c.nombre, s.monto, s.plazo_dias, s.estado, s.fecha_solicitud, s.fecha_respuesta FROM t_solicitud_prestamo s LEFT JOIN t_cliente c ON c.id = s.id_cliente WHERE s.id_cliente = %s AND "
        pend = query(base + "s.fecha_respuesta IS NULL ORDER BY s.id DESC LIMIT 5", (cid,), fetchall=True) or []
        res = query(base + "s.fecha_respuesta IS NOT NULL ORDER BY s.fecha_respuesta DESC LIMIT 5", (cid,), fetchall=True) or []
        logs = query("SELECT id, id_cliente, tipo, titulo, fecha_creacion FROM t_notificacion WHERE id_cliente = %s ORDER BY id DESC LIMIT 8", (cid,), fetchall=True) or []
        return {'sol_total': len(pend), 'sol_ultimas': pend, 'sol_resueltas': res, 'notif_logs': logs, 'sol_link': '/notificaciones_cliente'}
    fila = query("SELECT COUNT(*) AS total FROM t_solicitud_prestamo WHERE fecha_respuesta IS NULL", fetchone=True)
    ultimas = query(
        "SELECT s.id, s.id_cliente, c.nombre, s.monto, s.plazo_dias, s.estado, s.fecha_solicitud FROM t_solicitud_prestamo s LEFT JOIN t_cliente c ON c.id = s.id_cliente "
        "WHERE s.fecha_respuesta IS NULL ORDER BY s.id DESC LIMIT 5", fetchall=True)
    resueltas = query(
        "SELECT s.id, c.nombre, s.id_cliente, s.monto, s.estado, s.fecha_respuesta FROM t_solicitud_prestamo s "
        "LEFT JOIN t_cliente c ON c.id = s.id_cliente WHERE s.fecha_respuesta IS NOT NULL "
        "ORDER BY s.fecha_respuesta DESC LIMIT 5", fetchall=True)
    logs = query("SELECT id, id_cliente, tipo, titulo, fecha_creacion FROM t_notificacion ORDER BY id DESC LIMIT 8", fetchall=True)
    return {'sol_total': (fila or {}).get('total', 0), 'sol_ultimas': ultimas or [],
            'sol_resueltas': resueltas or [], 'notif_logs': logs or [], **_extra_avisos()}


def crear_notificacion(id_cliente, tipo, titulo, mensaje, id_prestamo=None):
    """Inserta una notificacion para el cliente en t_notificacion."""
    try:
        query(
            "INSERT INTO t_notificacion (id_cliente, tipo, titulo, mensaje, id_prestamo) VALUES (%s, %s, %s, %s, %s)",
            (id_cliente, tipo, titulo, mensaje, id_prestamo), commit=True
        )
    except Exception as e:
        print("Error creando notificacion:", e)


@app.route('/solicitar_prestamo_paso', methods=['POST'])
def solicitar_prestamo_paso():
    """Endpoint JSON para el portal del cliente."""
    if not session.get('logueado') or session.get('id_nivel') != 4:
        return jsonify({'success': False, 'error': 'Sesión no válida'}), 401

    cliente_id = session.get('cliente_id')
    if not cliente_id:
        return jsonify({'success': False, 'error': 'Cliente no identificado'}), 400

    try:
        monto = float(request.form.get('monto', 0))
        plazo = int(request.form.get('plazo', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Monto o plazo inválidos'}), 400

    if monto < 50000 or monto > 20000000:
        return jsonify({'success': False, 'error': 'El monto debe estar entre $50.000 y $20.000.000'}), 400

    if plazo not in [7, 14, 21, 30, 45, 60]:
        return jsonify({'success': False, 'error': 'Plazo no válido'}), 400

    activo = query(
        """SELECT p.*, p.dias_mora FROM t_prestamo p
           WHERE p.id_cliente = %s AND p.id_estado_prestamo = 2
           ORDER BY p.id DESC LIMIT 1""",
        (cliente_id,), fetchone=True
    )

    estado = 'pendiente'
    advertencia = None
    comentario = "Solicitud creada desde el portal. Monto: ${:,.0f}, Plazo: {} días.".format(monto, plazo)

    if activo:
        if int(activo.get('dias_mora') or 0) > 0:
            estado = 'rechazada'
            advertencia = "Tienes un crédito en mora ({} días).".format(activo['dias_mora'])
            comentario = "RECHAZADA POR SISTEMA: Cliente en mora. " + comentario
        else:
            estado = 'rechazada'
            advertencia = "Tienes un crédito vigente."
            comentario = "RECHAZADA POR SISTEMA: Cliente con crédito vigente. " + comentario

    try:
        query(
            """INSERT INTO t_solicitud_prestamo
               (id_cliente, monto, plazo_dias, estado, comentario_admin)
               VALUES (%s, %s, %s, %s, %s)""",
            (cliente_id, monto, plazo, estado, comentario),
            commit=True
        )
    except Exception as e:
        return jsonify({'success': False, 'error': 'Error al guardar: ' + str(e)}), 500

    if estado == 'pendiente':
        crear_notificacion(cliente_id, 'solicitud', 'Solicitud enviada',
                           'Tu solicitud de ${:,.0f} a {} días fue enviada y está en revisión.'.format(monto, plazo))
    else:
        crear_notificacion(cliente_id, 'solicitud', 'Solicitud en revisión', 'El administrador revisará tu solicitud. ' + (advertencia or ''))

    resp = {'success': True}
    if advertencia:
        resp['advertencia'] = advertencia
    return jsonify(resp)


@app.route('/prestamos')
def prestamos():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    lista = PrestamoModel.listar_todos() or []  # ← Asegurar lista vacía si es None
    return render_template('prestamos.html', prestamos=lista)

@app.route('/prestamos/estado/<int:id_estado>')
def prestamos_por_estado(id_estado):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    lista = PrestamoModel.listar_por_estado(id_estado)
    return render_template('prestamos.html', prestamos=lista)

@app.route('/prestamo/nuevo', methods=['GET', 'POST'])
def prestamo_nuevo():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        monto = float(request.form.get('monto_prestado', 0) or 0)
        porcentaje = float(request.form.get('porcentaje', 0) or 0)
        num_cuotas = int(request.form.get('numero_cuotas', 1) or 1)
        
        interes = monto * (porcentaje / 100)
        total = monto + interes
        monto_cuota = total / num_cuotas if num_cuotas > 0 else 0
        
        datos = {
            'id_cliente': request.form.get('id_cliente'),
            'id_cobrador': request.form.get('id_cobrador') or None,
            'id_tipo_prestamo': request.form.get('id_tipo_prestamo', 1),
            'id_metodo_pago': request.form.get('id_metodo_pago', 1),
            'porcentaje': porcentaje,
            'monto_prestado': monto,
            'interes': interes,
            'total_prestado': total,
            'numero_cuotas': num_cuotas,
            'monto_x_cuotas': monto_cuota,
            'total_debe': total,
            'fecha_prestamo': request.form.get('fecha_prestamo'),
            'id_estado_prestamo': 1  # Por Aprobar
        }
        
        PrestamoModel.crear(datos)
        flash('Préstamo creado correctamente (pendiente de aprobación)', 'success')
        return redirect(url_for('prestamos'))
    
    from datetime import date
    clientes = ClienteModel.listar_todos() or []
    cobradores = query("SELECT id, nombre FROM t_cobrador", fetchall=True) or []
    tipos = PrestamoModel.listar_tipos() or []
    metodos = PrestamoModel.listar_metodos_pago() or []
    
    return render_template('prestamo_form.html',
                           titulo='Nuevo Préstamo',
                           clientes=clientes,
                           cobradores=cobradores,
                           tipos=tipos,
                           metodos=metodos,
                           fecha_hoy=date.today().strftime('%Y-%m-%d'))
@app.route('/prestamo/editar/<int:id_prestamo>', methods=['GET', 'POST'])
def prestamo_editar(id_prestamo):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    prestamo = PrestamoModel.obtener_por_id(id_prestamo)
    if not prestamo:
        flash('Préstamo no encontrado', 'danger')
        return redirect(url_for('prestamos'))
    
    if request.method == 'POST':
        # Solo permitimos editar cobrador, tipo de préstamo, método de pago y observación
        # (No monto, ni cuotas, ni porcentaje, porque ya está creado)
        nuevo_cobrador = request.form.get('id_cobrador') or None
        
        query("""
            UPDATE t_prestamo SET
                id_cobrador = %s,
                id_tipo_prestamo = %s,
                id_metodo_pago = %s
            WHERE id = %s
        """, (
            nuevo_cobrador,
            request.form.get('id_tipo_prestamo', 1),
            request.form.get('id_metodo_pago', 1),
            id_prestamo
        ), commit=True)
        
        flash('Préstamo actualizado correctamente', 'success')
        return redirect(url_for('prestamos'))
    
    from datetime import date
    clientes = ClienteModel.listar_todos() or []
    cobradores = query("SELECT id, nombre FROM t_cobrador", fetchall=True) or []
    tipos = PrestamoModel.listar_tipos() or []
    metodos = PrestamoModel.listar_metodos_pago() or []
    
    return render_template('prestamo_editar.html',
                           titulo=f'Editar Préstamo #{id_prestamo}',
                           prestamo=prestamo,
                           clientes=clientes,
                           cobradores=cobradores,
                           tipos=tipos,
                           metodos=metodos,
                           fecha_hoy=date.today().strftime('%Y-%m-%d'))
@app.route('/prestamo/ver/<int:id_prestamo>')
def prestamo_ver(id_prestamo):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    prestamo = PrestamoModel.obtener_por_id(id_prestamo)
    pagos = PrestamoModel.listar_pagos(id_prestamo)
    if not prestamo:
        flash('Préstamo no encontrado', 'danger')
        return redirect(url_for('prestamos'))
    from datetime import date, timedelta, datetime
    n = int(prestamo['numero_cuotas'] or 0)
    dias = {'Semanal': 7, 'Quincenal': 15, 'Mensual': 30}.get(prestamo.get('tipo_prestamo') or 'Diario', 1)
    tot = float(prestamo['total_prestado'] or 0)
    cuota = tot / n if n else 0
    cap = float(prestamo['monto_prestado'] or 0) / n if n else 0
    pagadas = max(n - int(prestamo['cuotas_debe'] or 0), 0)
    hoy = date.today()
    cron = []
    if n and prestamo['fecha_prestamo']:
        f0 = datetime.strptime(str(prestamo['fecha_prestamo'])[:10], '%Y-%m-%d').date()
        for i in range(1, n + 1):
            fe = f0 + timedelta(days=dias * i)
            est = 'Pagada' if i <= pagadas else ('Vencida' if fe < hoy else 'Pendiente')
            cron.append({'n': i, 'fecha': fe.strftime('%Y-%m-%d'), 'cuota': cuota, 'capital': cap, 'interes': cuota - cap, 'saldo': max(tot - cuota * i, 0), 'estado': est})
    return render_template('prestamo_ver.html', prestamo=prestamo, pagos=pagos, cronograma=cron, dias_cuota=dias)

@app.route('/prestamo/aprobar/<int:id_prestamo>')
def prestamo_aprobar(id_prestamo):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    prestamo = PrestamoModel.obtener_por_id(id_prestamo)
    if not prestamo:
        flash('Préstamo no encontrado', 'danger')
        return redirect(url_for('prestamos'))
    
    if prestamo['estado_prestamo'] != 'Por Aprobar':
        flash('Este préstamo ya fue procesado', 'warning')
        return redirect(url_for('prestamo_ver', id_prestamo=id_prestamo))
    
    # Calcular datos de aprobación
    from datetime import date, timedelta
    num_cuotas = prestamo['numero_cuotas'] or 1
    monto = float(prestamo['monto_prestado'] or 0)
    porcentaje = float(prestamo['porcentaje'] or 0)
    interes = monto * (porcentaje / 100)
    total = monto + interes
    monto_cuota = total / num_cuotas
    
    # Calcular la fecha del próximo cobro (según tipo de préstamo)
    tipo = prestamo.get('tipo_prestamo', 'Diario')
    dias_por_cuota = 1  # Diario por defecto
    if tipo == 'Semanal':
        dias_por_cuota = 7
    elif tipo == 'Quincenal':
        dias_por_cuota = 15
    elif tipo == 'Mensual':
        dias_por_cuota = 30
    
    fecha_prox_cobro = date.today() + timedelta(days=dias_por_cuota)
    
    # Actualizar el préstamo
    PrestamoModel.aprobar(id_prestamo, {
        'monto_aprobado': monto,
        'porcentaje_aprobado': porcentaje,
        'interes': interes,
        'total_prestado': total,
        'total_debe': total,
        'numero_cuotas_aprobadas': num_cuotas,
        'monto_x_cuotas': monto_cuota,
        'fecha_prox_cobro': fecha_prox_cobro.strftime('%Y-%m-%d'),
        'observacion': 'Préstamo aprobado automáticamente'
    })
    
    flash('¡Préstamo aprobado correctamente! Ya está activo.', 'success')
    return redirect(url_for('prestamo_ver', id_prestamo=id_prestamo))


@app.route('/prestamo/pago/<int:id_prestamo>', methods=['GET', 'POST'])
def prestamo_pago(id_prestamo):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    prestamo = PrestamoModel.obtener_por_id(id_prestamo)
    if not prestamo:
        flash('Préstamo no encontrado', 'danger')
        return redirect(url_for('prestamos'))
    
    if request.method == 'POST':
        monto_pago = float(request.form.get('monto', 0) or 0)
        
        if monto_pago <= 0:
            flash('El monto debe ser mayor que cero', 'danger')
            return redirect(url_for('prestamo_pago', id_prestamo=id_prestamo))
        
        # Calcular la fecha del próximo cobro (mantener el ciclo)
        from datetime import date, timedelta
        tipo = prestamo.get('tipo_prestamo', 'Diario')
        dias_por_cuota = 1
        if tipo == 'Semanal':
            dias_por_cuota = 7
        elif tipo == 'Quincenal':
            dias_por_cuota = 15
        elif tipo == 'Mensual':
            dias_por_cuota = 30
        
        fecha_prox_cobro = date.today() + timedelta(days=dias_por_cuota)
        
        # Registrar el pago
        PrestamoModel.registrar_pago(id_prestamo, {
            'id_tipo_prestamo_2': 2,  # Pago de Cuota
            'cuota': (prestamo['cuotas_amortizadas'] or 0) + 1,
            'descripcion': request.form.get('descripcion', 'Pago Efectuado'),
            'monto': monto_pago,
            'fecha_cobro': date.today().strftime('%Y-%m-%d'),
            'fecha_prox_cobro': fecha_prox_cobro.strftime('%Y-%m-%d')
        })
        
        flash(f'Pago de {monto_pago:.2f} registrado correctamente.', 'success')
        return redirect(url_for('prestamo_ver', id_prestamo=id_prestamo))
    
    from datetime import date
    return render_template('prestamo_pago.html', 
                           prestamo=prestamo, 
                           fecha_hoy=date.today().strftime('%Y-%m-%d'))
@app.route('/prestamo/eliminar/<int:id_prestamo>')
def prestamo_eliminar(id_prestamo):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    PrestamoModel.eliminar(id_prestamo)
    flash('Préstamo eliminado correctamente', 'success')
    return redirect(url_for('prestamos'))

# ============================================================
# MÓDULO DE ESCANEO DE COMPROBANTES
# ============================================================
from models.comprobante import ComprobanteModel

UPLOAD_COMPROBANTES = os.path.join(os.path.dirname(__file__), 'static', 'comprobantes')
os.makedirs(UPLOAD_COMPROBANTES, exist_ok=True)

@app.route('/prestamo/escanear/<int:id_prestamo>', methods=['GET', 'POST'])
def prestamo_escanear(id_prestamo):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    prestamo = PrestamoModel.obtener_por_id(id_prestamo)
    if not prestamo:
        flash('Préstamo no encontrado', 'danger')
        return redirect(url_for('prestamos'))
    
    datos_extraidos = None
    
    if request.method == 'POST':
        tipo = request.form.get('tipo', 'envio')
        archivo = request.files.get('comprobante')
        
        if not archivo or not archivo.filename:
            flash('Debes seleccionar una imagen', 'warning')
            return redirect(url_for('prestamo_escanear', id_prestamo=id_prestamo))
        
        # Validar extensión
        ext = archivo.filename.rsplit('.', 1)[-1].lower()
        if ext not in ['png', 'jpg', 'jpeg']:
            flash('Formato no permitido. Usa PNG, JPG o JPEG.', 'danger')
            return redirect(url_for('prestamo_escanear', id_prestamo=id_prestamo))
        
        # Guardar la imagen
        import time
        nombre_archivo = f"comprobante_{id_prestamo}_{int(time.time())}.{ext}"
        ruta = os.path.join(UPLOAD_COMPROBANTES, nombre_archivo)
        archivo.save(ruta)
        
        # Procesar con OCR y QR (pasando el tipo)
        datos_extraidos = ComprobanteModel.procesar_comprobante(ruta, tipo=tipo)
        datos_extraidos['ruta_imagen'] = f"/static/comprobantes/{nombre_archivo}"
        
        if datos_extraidos['exito']:
            tipo_texto = 'Envío' if tipo == 'envio' else 'Pago'
            flash(f"Comprobante de {tipo_texto} procesado. Monto: ${datos_extraidos['monto']:,.0f}", 'success')
        else:
            flash('Comprobante procesado pero no se detectó el monto. Verifica manualmente.', 'warning')
    
    from datetime import date
    return render_template('prestamo_escanear.html',
                           prestamo=prestamo,
                           datos=datos_extraidos,
                           fecha_hoy=date.today().strftime('%Y-%m-%d'))

# ============================================================
# MÓDULO DE COBRADORES (REAL)
# ============================================================
from models.cobrador import CobradorModel

@app.route('/cobradores')
def cobradores():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    lista = CobradorModel.listar_todos()
    return render_template('cobradores.html', cobradores=lista)

@app.route('/cobrador/nuevo', methods=['GET', 'POST'])
def cobrador_nuevo():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        datos = {
            'id_usuario': request.form.get('id_usuario') or None,
            'nombre': request.form.get('nombre', '')
        }
        CobradorModel.crear(datos)
        flash('Cobrador creado correctamente', 'success')
        return redirect(url_for('cobradores'))
    
    usuarios = CobradorModel.listar_usuarios_disponibles() or []
    return render_template('cobrador_form.html',
                           cobrador=None,
                           usuarios=usuarios,
                           titulo='Nuevo Cobrador')

@app.route('/cobrador/editar/<int:id_cobrador>', methods=['GET', 'POST'])
def cobrador_editar(id_cobrador):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    cobrador = CobradorModel.obtener_por_id(id_cobrador)
    if not cobrador:
        flash('Cobrador no encontrado', 'danger')
        return redirect(url_for('cobradores'))
    
    if request.method == 'POST':
        datos = {
            'id_usuario': request.form.get('id_usuario') or None,
            'nombre': request.form.get('nombre', '')
        }
        CobradorModel.actualizar(id_cobrador, datos)
        flash('Cobrador actualizado correctamente', 'success')
        return redirect(url_for('cobradores'))
    
    usuarios = CobradorModel.listar_usuarios_disponibles() or []
    return render_template('cobrador_form.html',
                           cobrador=cobrador,
                           usuarios=usuarios,
                           titulo=f'Editar Cobrador #{id_cobrador}')

@app.route('/cobrador/eliminar/<int:id_cobrador>')
def cobrador_eliminar(id_cobrador):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    CobradorModel.eliminar(id_cobrador)
    flash('Cobrador eliminado correctamente', 'success')
    return redirect(url_for('cobradores'))

# ============================================================
# MÓDULO DE SOCIOS (REAL)
# ============================================================
from models.socio import SocioModel

@app.route('/socios')
def socios():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    lista = SocioModel.listar_todos() or []
    ap = query("SELECT id_socio, COALESCE(SUM(capital),0) AS t, COUNT(*) AS n FROM t_det_capital GROUP BY id_socio", fetchall=True) or []
    am = {r['id_socio']: float(r['t'] or 0) for r in ap}
    cn = {r['id_socio']: int(r['n'] or 0) for r in ap}
    tot = sum(am.values())
    filas = [{'id': x['id'], 'nombre': x['nombre'], 'usuario_nombre': x['usuario_nombre'], 'usuario_login': x['usuario_login'], 'aporte': am.get(x['id'], 0.0), 'n': cn.get(x['id'], 0), 'pct': (am.get(x['id'], 0.0) * 100 / tot) if tot else 0.0} for x in lista]
    top = max(filas, key=lambda z: z['aporte']) if filas else None
    datos = [[f['nombre'], f['aporte']] for f in sorted(filas, key=lambda z: -z['aporte']) if f['aporte'] > 0]
    return render_template('socios.html', socios=filas, total=tot, top=top, datos=datos)

@app.route('/socio/nuevo', methods=['GET', 'POST'])
def socio_nuevo():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        datos = {
            'id_usuario': request.form.get('id_usuario') or None,
            'nombre': request.form.get('nombre', '')
        }
        SocioModel.crear(datos)
        flash('Socio creado correctamente', 'success')
        return redirect(url_for('socios'))
    
    usuarios = SocioModel.listar_usuarios_disponibles() or []
    return render_template('socio_form.html',
                           socio=None,
                           usuarios=usuarios,
                           titulo='Nuevo Socio')

@app.route('/socio/editar/<int:id_socio>', methods=['GET', 'POST'])
def socio_editar(id_socio):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    socio = SocioModel.obtener_por_id(id_socio)
    if not socio:
        flash('Socio no encontrado', 'danger')
        return redirect(url_for('socios'))
    
    if request.method == 'POST':
        datos = {
            'id_usuario': request.form.get('id_usuario') or None,
            'nombre': request.form.get('nombre', '')
        }
        SocioModel.actualizar(id_socio, datos)
        flash('Socio actualizado correctamente', 'success')
        return redirect(url_for('socios'))
    
    usuarios = SocioModel.listar_usuarios_disponibles() or []
    return render_template('socio_form.html',
                           socio=socio,
                           usuarios=usuarios,
                           titulo=f'Editar Socio #{id_socio}')

@app.route('/socio/eliminar/<int:id_socio>')
def socio_eliminar(id_socio):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    SocioModel.eliminar(id_socio)
    flash('Socio eliminado correctamente', 'success')
    return redirect(url_for('socios'))

# ============================================================
# MÓDULO DE ZONAS (REAL)
# ============================================================
from models.zona import ZonaModel, ZonaCobradorModel

@app.route('/zonas')
def zonas():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    lista = ZonaModel.listar_todas() or []
    asignaciones = ZonaCobradorModel.listar_todas() or []
    total_asignaciones = ZonaCobradorModel.contar()
    return render_template('zonas.html',
                           zonas=lista,
                           asignaciones=asignaciones,
                           total_asignaciones=total_asignaciones)

@app.route('/zona/nueva', methods=['GET', 'POST'])
def zona_nueva():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        datos = {
            'zona': request.form.get('zona', ''),
            'direccion': request.form.get('direccion', '')
        }
        ZonaModel.crear(datos)
        flash('Zona creada correctamente', 'success')
        return redirect(url_for('zonas'))
    
    return render_template('zona_form.html', zona=None, titulo='Nueva Zona')

@app.route('/zona/editar/<int:id_zona>', methods=['GET', 'POST'])
def zona_editar(id_zona):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    zona = ZonaModel.obtener_por_id(id_zona)
    if not zona:
        flash('Zona no encontrada', 'danger')
        return redirect(url_for('zonas'))
    
    if request.method == 'POST':
        datos = {
            'zona': request.form.get('zona', ''),
            'direccion': request.form.get('direccion', '')
        }
        ZonaModel.actualizar(id_zona, datos)
        flash('Zona actualizada correctamente', 'success')
        return redirect(url_for('zonas'))
    
    return render_template('zona_form.html', zona=zona, titulo=f'Editar Zona #{id_zona}')

@app.route('/zona/eliminar/<int:id_zona>')
def zona_eliminar(id_zona):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    ZonaModel.eliminar(id_zona)
    flash('Zona eliminada correctamente', 'success')
    return redirect(url_for('zonas'))

# --- Asignaciones Zona-Cobrador ---

@app.route('/zona/asignacion/nueva', methods=['GET', 'POST'])
def asignacion_nueva():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        datos = {
            'id_zona': request.form.get('id_zona'),
            'id_cobrador': request.form.get('id_cobrador'),
            'id_sucursal': request.form.get('id_sucursal')
        }
        ZonaCobradorModel.crear(datos)
        flash('Asignación creada correctamente', 'success')
        return redirect(url_for('zonas'))
    
    zonas_lista = ZonaModel.listar_todas() or []
    cobradores_lista = query("SELECT id, nombre FROM t_cobrador ORDER BY nombre", fetchall=True) or []
    sucursales_lista = query("SELECT id, descripcion FROM t_sucursal ORDER BY descripcion", fetchall=True) or []
    
    return render_template('asignacion_form.html',
                           asignacion=None,
                           zonas=zonas_lista,
                           cobradores=cobradores_lista,
                           sucursales=sucursales_lista,
                           titulo='Nueva Asignación')

@app.route('/zona/asignacion/editar/<int:id_asignacion>', methods=['GET', 'POST'])
def asignacion_editar(id_asignacion):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    asignacion = ZonaCobradorModel.obtener_por_id(id_asignacion)
    if not asignacion:
        flash('Asignación no encontrada', 'danger')
        return redirect(url_for('zonas'))
    
    if request.method == 'POST':
        datos = {
            'id_zona': request.form.get('id_zona'),
            'id_cobrador': request.form.get('id_cobrador'),
            'id_sucursal': request.form.get('id_sucursal')
        }
        ZonaCobradorModel.actualizar(id_asignacion, datos)
        flash('Asignación actualizada correctamente', 'success')
        return redirect(url_for('zonas'))
    
    zonas_lista = ZonaModel.listar_todas() or []
    cobradores_lista = query("SELECT id, nombre FROM t_cobrador ORDER BY nombre", fetchall=True) or []
    sucursales_lista = query("SELECT id, descripcion FROM t_sucursal ORDER BY descripcion", fetchall=True) or []
    
    return render_template('asignacion_form.html',
                           asignacion=asignacion,
                           zonas=zonas_lista,
                           cobradores=cobradores_lista,
                           sucursales=sucursales_lista,
                           titulo=f'Editar Asignación #{id_asignacion}')

@app.route('/zona/asignacion/eliminar/<int:id_asignacion>')
def asignacion_eliminar(id_asignacion):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    ZonaCobradorModel.eliminar(id_asignacion)
    flash('Asignación eliminada correctamente', 'success')
    return redirect(url_for('zonas'))

# ============================================================
# MÓDULO DE CAJA (REAL)
# ============================================================
from models.caja import CajaModel

@app.route('/caja')
def caja():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    caja_principal = CajaModel.obtener_caja_principal()
    if not caja_principal:
        flash('No hay cajas configuradas. Contacta al administrador.', 'warning')
        return redirect(url_for('dashboard'))
    
    movimientos = CajaModel.listar_movimientos(caja_principal['id_caja']) or []
    total_ingresos = CajaModel.sumar_ingresos()
    total_egresos = CajaModel.sumar_egresos()
    
    return render_template('caja.html',
                           caja=caja_principal,
                           movimientos=movimientos,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos)

@app.route('/caja/nuevo', methods=['GET', 'POST'])
def caja_nuevo_movimiento():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    caja_principal = CajaModel.obtener_caja_principal()
    if not caja_principal:
        flash('No hay cajas configuradas.', 'warning')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        id_tipo_ingreso = request.form.get('id_tipo_ingreso')
        monto = float(request.form.get('monto', 0) or 0)
        fecha = request.form.get('fecha')
        
        if monto <= 0:
            flash('El monto debe ser mayor que cero', 'danger')
            return redirect(url_for('caja_nuevo_movimiento'))
        
        CajaModel.registrar_movimiento(
            caja_principal['id_caja'],
            id_tipo_ingreso,
            monto,
            fecha
        )
        
        flash('Movimiento registrado correctamente', 'success')
        return redirect(url_for('caja'))
    
    from datetime import date
    tipos = CajaModel.listar_tipos_movimiento() or []
    return render_template('caja_movimiento.html',
                           caja=caja_principal,
                           tipos=tipos,
                           fecha_hoy=date.today().strftime('%Y-%m-%d'))

@app.route('/caja/editar/<int:id_movimiento>', methods=['GET', 'POST'])
def caja_editar_movimiento(id_movimiento):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    caja_principal = CajaModel.obtener_caja_principal()
    if not caja_principal:
        flash('No hay cajas configuradas.', 'warning')
        return redirect(url_for('dashboard'))
    
    movimiento = CajaModel.obtener_movimiento_por_id(id_movimiento)
    if not movimiento:
        flash('Movimiento no encontrado', 'danger')
        return redirect(url_for('caja'))
    
    if request.method == 'POST':
        id_tipo_ingreso = request.form.get('id_tipo_ingreso')
        monto = float(request.form.get('monto', 0) or 0)
        fecha = request.form.get('fecha')
        
        if monto <= 0:
            flash('El monto debe ser mayor que cero', 'danger')
            return redirect(url_for('caja_editar_movimiento', id_movimiento=id_movimiento))
        
        CajaModel.actualizar_movimiento(id_movimiento, caja_principal['id_caja'], {
            'id_tipo_ingreso': id_tipo_ingreso,
            'monto': monto,
            'fecha': fecha
        })
        
        flash('Movimiento actualizado correctamente', 'success')
        return redirect(url_for('caja'))
    
    tipos = CajaModel.listar_tipos_movimiento() or []
    return render_template('caja_editar_movimiento.html',
                           caja=caja_principal,
                           movimiento=movimiento,
                           tipos=tipos)

@app.route('/caja/eliminar/<int:id_movimiento>')
def caja_eliminar_movimiento(id_movimiento):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    caja_principal = CajaModel.obtener_caja_principal()
    if not caja_principal:
        flash('No hay cajas configuradas.', 'warning')
        return redirect(url_for('dashboard'))
    
    CajaModel.eliminar_movimiento(id_movimiento, caja_principal['id_caja'])
    flash('Movimiento eliminado correctamente', 'success')
    return redirect(url_for('caja'))

# ============================================================
# MÓDULO DE CAPITAL (REAL)
# ============================================================
from models.capital import CapitalModel

@app.route('/capital')
def capital():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    # Asegurar que exista el registro de capital
    cap = CapitalModel.obtener_capital()
    if not cap:
        CapitalModel.inicializar_capital()
        cap = CapitalModel.obtener_capital()
    
    aportes = CapitalModel.listar_aportes() or []
    
    return render_template('capital.html',
                           capital=cap,
                           aportes=aportes)

@app.route('/capital/nuevo', methods=['GET', 'POST'])
def capital_nuevo_aporte():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    cap = CapitalModel.obtener_capital()
    if not cap:
        CapitalModel.inicializar_capital()
        cap = CapitalModel.obtener_capital()
    
    if request.method == 'POST':
        id_socio = request.form.get('id_socio')
        monto = float(request.form.get('monto', 0) or 0)
        descripcion = request.form.get('descripcion', '')
        
        if monto <= 0:
            flash('El monto debe ser mayor que cero', 'danger')
            return redirect(url_for('capital_nuevo_aporte'))
        
        CapitalModel.registrar_aporte(cap['id'], id_socio, descripcion, monto)
        flash('Aporte registrado correctamente', 'success')
        return redirect(url_for('capital'))
    
    socios = CapitalModel.listar_socios() or []
    return render_template('capital_aporte.html',
                           capital=cap,
                           aporte=None,
                           socios=socios,
                           titulo='Nuevo Aporte de Capital')

@app.route('/capital/editar/<int:id_aporte>', methods=['GET', 'POST'])
def capital_editar_aporte(id_aporte):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    cap = CapitalModel.obtener_capital()
    aporte = CapitalModel.obtener_aporte_por_id(id_aporte)
    
    if not aporte:
        flash('Aporte no encontrado', 'danger')
        return redirect(url_for('capital'))
    
    if request.method == 'POST':
        id_socio = request.form.get('id_socio')
        monto = float(request.form.get('monto', 0) or 0)
        descripcion = request.form.get('descripcion', '')
        
        if monto <= 0:
            flash('El monto debe ser mayor que cero', 'danger')
            return redirect(url_for('capital_editar_aporte', id_aporte=id_aporte))
        
        CapitalModel.actualizar_aporte(id_aporte, monto, descripcion, id_socio)
        flash('Aporte actualizado correctamente', 'success')
        return redirect(url_for('capital'))
    
    socios = CapitalModel.listar_socios() or []
    return render_template('capital_aporte.html',
                           capital=cap,
                           aporte=aporte,
                           socios=socios,
                           titulo=f'Editar Aporte #{id_aporte}')

@app.route('/capital/eliminar/<int:id_aporte>')
def capital_eliminar_aporte(id_aporte):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    CapitalModel.eliminar_aporte(id_aporte)
    flash('Aporte eliminado correctamente', 'success')
    return redirect(url_for('capital'))

# ============================================================
# MÓDULO DE GASTOS (REAL)
# ============================================================
from models.gasto import GastoModel

@app.route('/gastos')
def gastos():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    lista = GastoModel.listar_todos()
    total_gastos = GastoModel.sumar_total()
    total_registros = GastoModel.contar()
    return render_template('gastos.html',
                           gastos=lista,
                           total_gastos=total_gastos,
                           total_registros=total_registros)

@app.route('/gasto/nuevo', methods=['GET', 'POST'])
def gasto_nuevo():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        id_cobrador = request.form.get('id_cobrador') or None
        fecha = request.form.get('fecha')
        
        tipos = request.form.getlist('tipo_gasto[]')
        descripciones = request.form.getlist('descripcion[]')
        cantidades = request.form.getlist('cantidad[]')
        montos = request.form.getlist('monto[]')
        
        detalles = []
        for i in range(len(tipos)):
            if tipos[i]:
                detalles.append({
                    'id_tipo_gasto': tipos[i],
                    'descripcion': descripciones[i] if i < len(descripciones) else '',
                    'cantidad': int(cantidades[i]) if i < len(cantidades) and cantidades[i] else 1,
                    'monto': float(montos[i]) if i < len(montos) and montos[i] else 0
                })
        
        if not detalles:
            flash('Debe agregar al menos un ítem al gasto', 'danger')
            return redirect(url_for('gasto_nuevo'))
        
        GastoModel.crear(id_cobrador, fecha, detalles)
        flash('Gasto registrado correctamente', 'success')
        return redirect(url_for('gastos'))
    
    from datetime import date
    tipos = GastoModel.listar_tipos_gasto() or []
    cobradores = GastoModel.listar_cobradores() or []
    return render_template('gasto_form.html',
                           titulo='Nuevo Gasto',
                           gasto=None,
                           tipos=tipos,
                           cobradores=cobradores,
                           fecha_hoy=date.today().strftime('%Y-%m-%d'))

@app.route('/gasto/ver/<int:id_gasto>')
def gasto_ver(id_gasto):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    gasto = GastoModel.obtener_por_id(id_gasto)
    if not gasto:
        flash('Gasto no encontrado', 'danger')
        return redirect(url_for('gastos'))
    return render_template('gasto_ver.html', gasto=gasto)

@app.route('/gasto/editar/<int:id_gasto>', methods=['GET', 'POST'])
def gasto_editar(id_gasto):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    gasto = GastoModel.obtener_por_id(id_gasto)
    if not gasto:
        flash('Gasto no encontrado', 'danger')
        return redirect(url_for('gastos'))
    
    if request.method == 'POST':
        id_cobrador = request.form.get('id_cobrador') or None
        fecha = request.form.get('fecha')
        
        tipos = request.form.getlist('tipo_gasto[]')
        descripciones = request.form.getlist('descripcion[]')
        cantidades = request.form.getlist('cantidad[]')
        montos = request.form.getlist('monto[]')
        
        detalles = []
        for i in range(len(tipos)):
            if tipos[i]:
                detalles.append({
                    'id_tipo_gasto': tipos[i],
                    'descripcion': descripciones[i] if i < len(descripciones) else '',
                    'cantidad': int(cantidades[i]) if i < len(cantidades) and cantidades[i] else 1,
                    'monto': float(montos[i]) if i < len(montos) and montos[i] else 0
                })
        
        if not detalles:
            flash('Debe agregar al menos un ítem al gasto', 'danger')
            return redirect(url_for('gasto_editar', id_gasto=id_gasto))
        
        GastoModel.actualizar(id_gasto, id_cobrador, fecha, detalles)
        flash('Gasto actualizado correctamente', 'success')
        return redirect(url_for('gastos'))
    
    tipos = GastoModel.listar_tipos_gasto() or []
    cobradores = GastoModel.listar_cobradores() or []
    return render_template('gasto_form.html',
                           titulo=f'Editar Gasto #{id_gasto}',
                           gasto=gasto,
                           tipos=tipos,
                           cobradores=cobradores,
                           fecha_hoy=gasto['fecha'])

@app.route('/gasto/eliminar/<int:id_gasto>')
def gasto_eliminar(id_gasto):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    GastoModel.eliminar(id_gasto)
    flash('Gasto eliminado correctamente', 'success')
    return redirect(url_for('gastos'))

# ============================================================
# MÓDULO DE CIERRE POR DÍA (REAL)
# ============================================================
from models.cierre import CierreModel

@app.route('/cierre', methods=['GET', 'POST'])
def cierre():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    # Fecha seleccionada (por defecto hoy)
    fecha = request.args.get('fecha') or request.form.get('fecha')
    if not fecha:
        from datetime import date
        fecha = date.today().strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        monto = float(request.form.get('monto', 0) or 0)
        monto_recibido = float(request.form.get('monto_recibido', 0) or 0)
        total = float(request.form.get('total', 0) or 0)
        observaciones = request.form.get('observaciones', '')
        
        CierreModel.crear({
            'monto': monto,
            'monto_recibido': monto_recibido,
            'total': total,
            'observaciones': observaciones,
            'fecha': fecha
        })
        
        flash(f'Cierre del {fecha} registrado correctamente', 'success')
        return redirect(url_for('cierre', fecha=fecha))
    
    # Calcular datos del día
    total_cobrado = CierreModel.total_cobrado_dia(fecha)
    total_gastos = CierreModel.total_gastos_dia(fecha)
    pagos_dia = CierreModel.contar_pagos_dia(fecha)
    prestamos_dia = CierreModel.contar_prestamos_dia(fecha)
    neto_dia = total_cobrado - total_gastos
    ya_cerrado = CierreModel.existe_cierre(fecha)
    
    cierres = CierreModel.listar_todos() or []
    
    return render_template('cierre.html',
                           fecha=fecha,
                           total_cobrado=total_cobrado,
                           total_gastos=total_gastos,
                           pagos_dia=pagos_dia,
                           prestamos_dia=prestamos_dia,
                           neto_dia=neto_dia,
                           ya_cerrado=ya_cerrado,
                           cierres=cierres)

@app.route('/cierre/eliminar/<int:id_cierre>')
def cierre_eliminar(id_cierre):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    CierreModel.eliminar(id_cierre)
    flash('Cierre eliminado correctamente', 'success')
    return redirect(url_for('cierre'))
# ============================================================
# MÓDULO DE EMPRESA (REAL con subida de logo)
# ============================================================
from models.empresa import EmpresaModel
from werkzeug.utils import secure_filename

# Configuración de subida de archivos
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'img')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/empresa', methods=['GET', 'POST'])
def empresa():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    emp = EmpresaModel.inicializar()
    
    if request.method == 'POST':
        datos = {
            'nombre': request.form.get('nombre', ''),
            'nit': request.form.get('nit', ''),
            'direccion': request.form.get('direccion', ''),
            'telefono': request.form.get('telefono', ''),
            'email': request.form.get('email', ''),
            'logo': emp['logo'] if emp else ''
        }
        
        # Procesar la subida del logo
        archivo = request.files.get('logo_archivo')
        if archivo and archivo.filename:
            if allowed_file(archivo.filename):
                # Generar nombre único para evitar colisiones
                import time
                ext = archivo.filename.rsplit('.', 1)[1].lower()
                nombre_archivo = f"logo_empresa_{int(time.time())}.{ext}"
                ruta_completa = os.path.join(UPLOAD_FOLDER, nombre_archivo)
                archivo.save(ruta_completa)
                
                # Guardar la ruta relativa para mostrarla en el template
                datos['logo'] = f"/static/img/{nombre_archivo}"
                flash('Logo subido correctamente', 'success')
            else:
                flash('Formato de imagen no permitido. Usa PNG, JPG, JPEG o GIF.', 'danger')
                return redirect(url_for('empresa'))
        
        EmpresaModel.actualizar(emp['id'], datos)
        flash('Datos de la empresa actualizados correctamente', 'success')
        return redirect(url_for('empresa'))
    
    return render_template('empresa.html', empresa=emp)

# ============================================================
# MÓDULO DE USUARIOS (REAL)
# ============================================================
from models.usuario import UsuarioModel
import hashlib

@app.route('/usuarios')
def usuarios():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    lista = UsuarioModel.listar_todos()
    return render_template('usuarios.html', usuarios=lista)

@app.route('/usuario/nuevo', methods=['GET', 'POST'])
def usuario_nuevo():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '')
        login = request.form.get('login', '').strip()
        clave = request.form.get('clave', '')
        id_nivel = request.form.get('id_nivel', 1)
        id_estado_usuario = request.form.get('id_estado_usuario', 1)
        
        if not nombre or not login or not clave:
            flash('Nombre, login y contraseña son obligatorios', 'danger')
            return redirect(url_for('usuario_nuevo'))
        
        if UsuarioModel.existe_login(login):
            flash('Ese login ya está en uso', 'danger')
            return redirect(url_for('usuario_nuevo'))
        
        # Hash SHA-1
        clave_hash = hashlib.sha1(clave.encode('utf-8')).hexdigest()
        
        datos = {
            'nombre': nombre,
            'login': login,
            'clave': clave_hash,
            'id_nivel': id_nivel,
            'id_estado_usuario': id_estado_usuario
        }
        
        UsuarioModel.crear(datos)
        flash('Usuario creado correctamente', 'success')
        return redirect(url_for('usuarios'))
    
    niveles = UsuarioModel.listar_niveles() or []
    estados = UsuarioModel.listar_estados() or []
    return render_template('usuario_form.html',
                           usuario=None,
                           niveles=niveles,
                           estados=estados,
                           titulo='Nuevo Usuario')

@app.route('/usuario/editar/<int:id_usuario>', methods=['GET', 'POST'])
def usuario_editar(id_usuario):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    usuario = UsuarioModel.obtener_por_id(id_usuario)
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('usuarios'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '')
        login = request.form.get('login', '').strip()
        clave = request.form.get('clave', '')
        id_nivel = request.form.get('id_nivel', 1)
        id_estado_usuario = request.form.get('id_estado_usuario', 1)
        
        if not nombre or not login:
            flash('Nombre y login son obligatorios', 'danger')
            return redirect(url_for('usuario_editar', id_usuario=id_usuario))
        
        if UsuarioModel.existe_login(login, excluir_id=id_usuario):
            flash('Ese login ya está en uso por otro usuario', 'danger')
            return redirect(url_for('usuario_editar', id_usuario=id_usuario))
        
        # Si no se cambió la contraseña, mantener la actual
        if clave:
            clave_hash = hashlib.sha1(clave.encode('utf-8')).hexdigest()
        else:
            clave_hash = usuario['clave']
        
        datos = {
            'nombre': nombre,
            'login': login,
            'clave': clave_hash,
            'id_nivel': id_nivel,
            'id_estado_usuario': id_estado_usuario
        }
        
        UsuarioModel.actualizar(id_usuario, datos)
        flash('Usuario actualizado correctamente', 'success')
        return redirect(url_for('usuarios'))
    
    niveles = UsuarioModel.listar_niveles() or []
    estados = UsuarioModel.listar_estados() or []
    return render_template('usuario_form.html',
                           usuario=usuario,
                           niveles=niveles,
                           estados=estados,
                           titulo=f'Editar Usuario #{id_usuario}')

@app.route('/usuario/eliminar/<int:id_usuario>')
def usuario_eliminar(id_usuario):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    if id_usuario == session.get('id'):
        flash('No puedes eliminar tu propio usuario', 'danger')
        return redirect(url_for('usuarios'))
    
    UsuarioModel.eliminar(id_usuario)
    flash('Usuario eliminado correctamente', 'success')
    return redirect(url_for('usuarios'))

# ============================================================
# MÓDULO DE REPORTES (REAL)
# ============================================================
from models.reporte import ReporteModel
from datetime import date, timedelta

@app.route('/reportes')
def reportes():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    
    # Fechas por defecto: último mes
    hoy = date.today()
    hace_un_mes = hoy - timedelta(days=30)
    
    fecha_i = request.args.get('fecha_i', hace_un_mes.strftime('%Y-%m-%d'))
    fecha_f = request.args.get('fecha_f', hoy.strftime('%Y-%m-%d'))
    
    prestamos = ReporteModel.prestamos_por_fecha(fecha_i, fecha_f) or []
    cobros = ReporteModel.cobros_por_fecha(fecha_i, fecha_f) or []
    gastos = ReporteModel.gastos_por_fecha(fecha_i, fecha_f) or []
    
    resumen_prestamos = ReporteModel.resumen_prestamos(fecha_i, fecha_f) or {}
    resumen_cobros = ReporteModel.resumen_cobros(fecha_i, fecha_f) or {}
    resumen_gastos = ReporteModel.resumen_gastos(fecha_i, fecha_f) or {}
    
    prestamos_cobrador = ReporteModel.prestamos_por_cobrador(fecha_i, fecha_f) or []
    cobros_cobrador = ReporteModel.cobros_por_cobrador(fecha_i, fecha_f) or []
    
    return render_template('reportes.html',
                           fecha_i=fecha_i,
                           fecha_f=fecha_f,
                           prestamos=prestamos,
                           cobros=cobros,
                           gastos=gastos,
                           resumen_prestamos=resumen_prestamos,
                           resumen_cobros=resumen_cobros,
                           resumen_gastos=resumen_gastos,
                           prestamos_cobrador=prestamos_cobrador,
                           cobros_cobrador=cobros_cobrador)

@app.route('/logout')
def logout():
    """Cerrar sesión."""
    session.clear()
    return redirect(url_for('login'))


# ============================================================
# INICIAR SERVIDOR AUTOMÁTICAMENTE
# ============================================================

# --- Idioma del menu de usuario (solo guarda la eleccion y la bandera) ---
IDIOMAS = {'en':'united-states.svg','es':'spain.svg','de':'germany.svg','ja':'japan.svg','fr':'france.svg'}

@app.context_processor
def inyectar_cop():
    return {"cop": lambda v: "$" + f"{float(v or 0):,.0f}".replace(",", ".")}

@app.context_processor
def inyectar_ver():
    def ver(ruta):
        try:
            return int(os.path.getmtime(os.path.join(app.static_folder, ruta)))
        except OSError:
            return 0
    return {"ver": ver}

@app.context_processor
def inyectar_idioma():
    l = session.get('lang', 'es')
    return {'lang': l, 'flag': IDIOMAS.get(l, 'spain.svg')}

@app.route('/set_lang/<lang>')
def set_lang(lang):
    if lang in IDIOMAS:
        session['lang'] = lang
    return redirect(request.referrer or url_for('dashboard'))

import prestamos_api; prestamos_api.registrar(app, query)
import cobradores_api; cobradores_api.registrar(app, query)
import socios_api; socios_api.registrar(app, query)
import capital_api; capital_api.registrar(app, query)
import gastos_api; gastos_api.registrar(app, query)
import cierre_api; cierre_api.registrar(app, query)
import reportes_api; reportes_api.registrar(app, query)
import perfil_admin; perfil_admin.registrar(app, query, sha1_hash)
import caja_api; caja_api.registrar(app, query)
import github_auth; github_auth.registrar(app, query)
import google_auth; google_auth.registrar(app, query)
import facebook_auth; facebook_auth.registrar(app, query)
import oauth_registro; oauth_registro.registrar(app, query)

# --- Recuperación de contraseña por enlace (módulo recuperacion.py) ---
from recuperacion import recuperacion_bp
app.register_blueprint(recuperacion_bp)


if __name__ == '__main__':
    # Abrir navegador
    import threading
    import webbrowser
    def abrir_navegador():
        webbrowser.open("http://127.0.0.1:5000")
    threading.Timer(1.5, abrir_navegador).start()

    # Servidor de producción Waitress (sin WARNING)
    from waitress import serve
    print("=" * 60)
    print("  SISTEMA PAGADIARIO - VERSIÓN PYTHON (Waitress)")
    print("=" * 60)
    print(f"  Servidor corriendo en:  http://127.0.0.1:5000")
    print("=" * 60)
    serve(app, host='127.0.0.1', port=5000, threads=4)
  
