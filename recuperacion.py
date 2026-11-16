"""Recuperación de contraseña por enlace de un solo uso.

Reemplaza la ruta anterior, que cambiaba la clave al instante y la enviaba en texto plano.
Flujo:
  1. POST /api/recuperar_password  -> guarda un token (solo su hash) y envía un enlace por correo.
  2. GET/POST /restablecer/<token> -> el usuario escribe su nueva contraseña (el enlace dura 30 min y se usa una vez).
La respuesta de (1) es siempre la misma exista o no la cuenta, y la base se consulta con límite de 3 solicitudes por hora.
Requiere la tabla t_recuperacion (ver sql_recuperacion.sql).
"""
import hashlib
import os
import re
import secrets
import threading

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from claves import validar_clave
from database import get_connection

recuperacion_bp = Blueprint('recuperacion', __name__)

VIGENCIA_MIN = 30
MAX_SOLICITUDES_HORA = 3
MENSAJE_GENERICO = 'Si los datos coinciden con una cuenta con correo registrado, te enviamos un enlace de recuperación.'


class BaseDatosNoDisponible(Exception):
    """La base de datos no respondió o la consulta falló."""


def _ejecutar(sql, params=(), uno=False, escribir=False):
    """Ejecuta una consulta. Si la base no responde lanza BaseDatosNoDisponible (no devuelve datos falsos)."""
    conn = get_connection()
    if conn is None:
        raise BaseDatosNoDisponible('sin conexión')
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if escribir:
                conn.commit()
                return cur.rowcount
            return cur.fetchone() if uno else cur.fetchall()
    except Exception as e:
        print(f'Recuperación: error de base de datos: {e}', flush=True)
        raise BaseDatosNoDisponible(str(e))
    finally:
        conn.close()


def _hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _enviar(email, nombre, enlace):
    """Envía el correo en segundo plano para que la respuesta tarde igual exista o no la cuenta."""
    try:
        from notificaciones import enviar_email
        cuerpo = (f'Hola {nombre},\n\n'
                  'Recibimos una solicitud para restablecer tu contraseña de Pagadiario Web.\n\n'
                  f'Entra a este enlace (válido por {VIGENCIA_MIN} minutos y de un solo uso):\n{enlace}\n\n'
                  'Si no fuiste tú, ignora este mensaje: tu contraseña no ha cambiado.\n\n'
                  'Atentamente,\nEl equipo de Pagadiario.')
        ok, detalle = enviar_email(email, 'Recuperación de contraseña - Pagadiario Web', cuerpo)
        if not ok:
            print(f'Recuperación: no se pudo enviar el correo ({detalle})', flush=True)
    except Exception as e:
        print(f'Recuperación: error al enviar el correo: {e}', flush=True)


def _validar_clave(p1, p2, contexto=()):
    if p1 != p2:
        return 'Las contraseñas no coinciden.'
    return validar_clave(p1, contexto)


@recuperacion_bp.route('/api/recuperar_password', methods=['POST'])
def solicitar():
    dato = request.form.get('dato', '').strip()
    if not dato:
        return jsonify({'success': False, 'message': 'Ingresa un correo o cédula válida.'})
    try:
        usuario = _ejecutar(
            'SELECT id, nombre, email FROM t_usuario WHERE email = %s OR login = %s LIMIT 1',
            (dato, dato), uno=True)
        if usuario and usuario.get('email'):
            recientes = _ejecutar(
                'SELECT COUNT(*) AS n FROM t_recuperacion WHERE usuario_id = %s AND creado > (NOW() - INTERVAL 1 HOUR)',
                (usuario['id'],), uno=True)['n']
            if recientes < MAX_SOLICITUDES_HORA:
                token = secrets.token_urlsafe(32)
                _ejecutar('UPDATE t_recuperacion SET usado = 1 WHERE usuario_id = %s AND usado = 0',
                          (usuario['id'],), escribir=True)
                _ejecutar('INSERT INTO t_recuperacion (usuario_id, token_hash, expira, ip) '
                          'VALUES (%s, %s, NOW() + INTERVAL %s MINUTE, %s)',
                          (usuario['id'], _hash(token), VIGENCIA_MIN, request.remote_addr), escribir=True)
                # En producción define PUBLIC_BASE_URL (p. ej. https://tudominio.com): así nadie puede fabricar
                # enlaces con un encabezado Host falso.
                base = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
                ruta = url_for('recuperacion.restablecer', token=token)
                enlace = (base + ruta) if base else url_for('recuperacion.restablecer', token=token, _external=True)
                threading.Thread(target=_enviar, args=(usuario['email'], usuario['nombre'], enlace), daemon=True).start()
    except BaseDatosNoDisponible:
        return jsonify({'success': False, 'message': 'Servicio no disponible. Intenta de nuevo en unos minutos.'}), 503
    return jsonify({'success': True, 'message': MENSAJE_GENERICO})


@recuperacion_bp.route('/restablecer/<token>', methods=['GET', 'POST'])
def restablecer(token):
    try:
        fila = _ejecutar(
            'SELECT id, usuario_id FROM t_recuperacion WHERE token_hash = %s AND usado = 0 AND expira > NOW() LIMIT 1',
            (_hash(token),), uno=True)
        if not fila:
            return render_template('restablecer.html', invalido=True), 400
        if request.method == 'POST':
            # .strip() igual que el login, para que la clave guardada sea la misma que se escribe al entrar
            p1, p2 = request.form.get('password', '').strip(), request.form.get('password2', '').strip()
            persona = _ejecutar('SELECT login, nombre, email FROM t_usuario WHERE id = %s', (fila['usuario_id'],), uno=True) or {}
            error = _validar_clave(p1, p2, [persona.get('login'), persona.get('nombre'), persona.get('email')])
            if error:
                return render_template('restablecer.html', error=error), 400
            clave = hashlib.sha1(p1.encode('utf-8')).hexdigest()  # mismo esquema que usa hoy el login
            _ejecutar('UPDATE t_usuario SET clave = %s, clave_v2 = NULL WHERE id = %s', (clave, fila['usuario_id']), escribir=True)
            _ejecutar('UPDATE t_recuperacion SET usado = 1 WHERE usuario_id = %s AND usado = 0',
                      (fila['usuario_id'],), escribir=True)
            flash('Contraseña actualizada. Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
    except BaseDatosNoDisponible:
        return render_template('restablecer.html', error='Servicio no disponible. Intenta de nuevo en unos minutos.'), 503
    return render_template('restablecer.html')
