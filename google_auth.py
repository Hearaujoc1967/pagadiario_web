import os, secrets, requests
from urllib.parse import quote
from flask import redirect, request, session, flash, url_for

REDIR = 'https://localhost:5001/auth/google/callback'

def _cfg():
    d = {}
    try:
        for l in open(os.path.expanduser('~/pagadiario_web/.oauth_google')):
            if '=' in l:
                k, v = l.strip().split('=', 1)
                d[k] = v
    except OSError:
        pass
    return d

def registrar(app, query):
    @app.route('/auth/google')
    def auth_google():
        c = _cfg()
        if not c.get('GOOGLE_ID'):
            flash('Google no está configurado', 'danger')
            return redirect(url_for('login'))
        st = secrets.token_urlsafe(16)
        session['gg_state'] = st
        return redirect('https://accounts.google.com/o/oauth2/v2/auth?client_id=' + c['GOOGLE_ID'] + '&redirect_uri=' + quote(REDIR, safe='') + '&response_type=code&scope=openid%20email&prompt=select_account&state=' + st)

    @app.route('/auth/google/callback')
    def auth_google_cb():
        c = _cfg()
        if not request.args.get('code') or request.args.get('state') != session.pop('gg_state', None):
            flash('No se pudo validar el acceso con Google', 'danger')
            return redirect(url_for('login'))
        try:
            r = requests.post('https://oauth2.googleapis.com/token',
                data={'client_id': c['GOOGLE_ID'], 'client_secret': c['GOOGLE_SECRET'], 'code': request.args['code'], 'redirect_uri': REDIR, 'grant_type': 'authorization_code'}, timeout=15)
            tok = r.json().get('access_token')
            if not tok:
                raise ValueError('sin token')
            info = requests.get('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization': 'Bearer ' + tok}, timeout=15).json()
        except Exception:
            flash('Google no respondió o rechazó el acceso', 'danger')
            return redirect(url_for('login'))
        m = (info.get('email') or '').lower()
        if not m or not info.get('email_verified'):
            flash('Google no entregó un correo verificado', 'danger')
            return redirect(url_for('login'))
        user = query("SELECT * FROM t_usuario WHERE LOWER(email) = %s LIMIT 1", (m,), fetchone=True)
        if not user:
            cl = query("SELECT dni FROM t_cliente WHERE LOWER(email) = %s LIMIT 1", (m,), fetchone=True)
            if cl:
                user = query("SELECT * FROM t_usuario WHERE login = %s LIMIT 1", (cl['dni'],), fetchone=True)
        if not user:
            import oauth_registro
            return oauth_registro.pendiente('google', info.get('sub'), info.get('name'), m)
        if user['id_estado_usuario'] != 1:
            flash('Usuario Inactivo', 'danger')
            return redirect(url_for('login'))
        session['logueado'] = True
        session['id'] = user['id']
        session['id_estado_usuario'] = user['id_estado_usuario']
        session['id_nivel'] = user['id_nivel']
        session['nombre'] = user['nombre']
        session['login'] = user['login']
        session['email'] = user.get('email') or ''
        if user['id_nivel'] == 4:
            cl = query("SELECT id, nombre, dni, email FROM t_cliente WHERE dni = %s LIMIT 1", (user['login'],), fetchone=True)
            if not cl:
                flash('No se encontró el cliente asociado a este usuario', 'danger')
                return redirect(url_for('login'))
            session['cliente_id'] = cl['id']
            session['cliente_nombre'] = cl['nombre']
            session['cliente_dni'] = cl['dni']
            session['email'] = cl.get('email') or ''
            return redirect(url_for('portal'))
        return redirect(url_for('dashboard'))
