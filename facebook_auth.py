import os, secrets, requests
from urllib.parse import quote
from flask import redirect, request, session, flash, url_for

REDIR = 'https://localhost:5001/auth/facebook/callback'
GV = 'https://graph.facebook.com/v19.0'

def _cfg():
    d = {}
    try:
        for l in open(os.path.expanduser('~/pagadiario_web/.oauth_facebook')):
            if '=' in l:
                k, v = l.strip().split('=', 1)
                d[k] = v
    except OSError:
        pass
    return d

def registrar(app, query):
    @app.route('/auth/facebook')
    def auth_facebook():
        c = _cfg()
        if not c.get('FACEBOOK_ID'):
            flash('Facebook no está configurado', 'danger')
            return redirect(url_for('login'))
        st = secrets.token_urlsafe(16)
        session['fb_state'] = st
        return redirect('https://www.facebook.com/v19.0/dialog/oauth?client_id=' + c['FACEBOOK_ID'] + '&redirect_uri=' + quote(REDIR, safe='') + '&scope=email,public_profile&auth_type=rerequest&state=' + st)

    @app.route('/auth/facebook/callback')
    def auth_facebook_cb():
        c = _cfg()
        if not request.args.get('code') or request.args.get('state') != session.pop('fb_state', None):
            flash('No se pudo validar el acceso con Facebook', 'danger')
            return redirect(url_for('login'))
        try:
            r = requests.get(GV + '/oauth/access_token', params={'client_id': c['FACEBOOK_ID'], 'client_secret': c['FACEBOOK_SECRET'], 'redirect_uri': REDIR, 'code': request.args['code']}, timeout=15)
            tok = r.json().get('access_token')
            if not tok:
                raise ValueError('sin token')
            me = requests.get(GV + '/me', params={'fields': 'id,name,email', 'access_token': tok}, timeout=15).json()
        except Exception:
            flash('Facebook no respondió o rechazó el acceso', 'danger')
            return redirect(url_for('login'))
        correos = [me['email'].lower()] if me.get('email') else []
        user = None
        try:
            vin = query("SELECT id_usuario FROM t_oauth_vinculo WHERE proveedor = 'facebook' AND proveedor_id = %s LIMIT 1", (str(me.get('id')),), fetchone=True)
        except Exception:
            vin = None
        if vin:
            user = query("SELECT * FROM t_usuario WHERE id = %s LIMIT 1", (vin['id_usuario'],), fetchone=True)
        for m in ([] if user else correos):
            user = query("SELECT * FROM t_usuario WHERE LOWER(email) = %s LIMIT 1", (m,), fetchone=True)
            if not user:
                cl = query("SELECT dni FROM t_cliente WHERE LOWER(email) = %s LIMIT 1", (m,), fetchone=True)
                if cl:
                    user = query("SELECT * FROM t_usuario WHERE login = %s LIMIT 1", (cl['dni'],), fetchone=True)
            if user:
                break
        if not user:
            import oauth_registro
            return oauth_registro.pendiente('facebook', me.get('id'), me.get('name'), correos[0] if correos else '')
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
