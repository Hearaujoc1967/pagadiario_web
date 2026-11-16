import os, secrets, requests
from urllib.parse import quote
from flask import redirect, request, session, flash, url_for

REDIR = 'https://localhost:5001/auth/github/callback'

def _cfg():
    d = {}
    try:
        for l in open(os.path.expanduser('~/pagadiario_web/.oauth_github')):
            if '=' in l:
                k, v = l.strip().split('=', 1)
                d[k] = v
    except OSError:
        pass
    return d

def registrar(app, query):
    @app.route('/auth/github')
    def auth_github():
        c = _cfg()
        if not c.get('GITHUB_ID'):
            flash('GitHub no está configurado', 'danger')
            return redirect(url_for('login'))
        st = secrets.token_urlsafe(16)
        session['gh_state'] = st
        return redirect('https://github.com/login/oauth/authorize?client_id=' + c['GITHUB_ID'] + '&redirect_uri=' + quote(REDIR, safe='') + '&scope=user:email&state=' + st)

    @app.route('/auth/github/callback')
    def auth_github_cb():
        c = _cfg()
        if not request.args.get('code') or request.args.get('state') != session.pop('gh_state', None):
            flash('No se pudo validar el acceso con GitHub', 'danger')
            return redirect(url_for('login'))
        try:
            r = requests.post('https://github.com/login/oauth/access_token',
                data={'client_id': c['GITHUB_ID'], 'client_secret': c['GITHUB_SECRET'], 'code': request.args['code'], 'redirect_uri': REDIR},
                headers={'Accept': 'application/json'}, timeout=15)
            tok = r.json().get('access_token')
            if not tok:
                raise ValueError('sin token')
            h = {'Authorization': 'Bearer ' + tok, 'Accept': 'application/vnd.github+json'}
            em = requests.get('https://api.github.com/user/emails', headers=h, timeout=15).json()
            gu = requests.get('https://api.github.com/user', headers=h, timeout=15).json()
        except Exception:
            flash('GitHub no respondió o rechazó el acceso', 'danger')
            return redirect(url_for('login'))
        correos = [e['email'].lower() for e in em if isinstance(e, dict) and e.get('verified')]
        user = None
        for m in correos:
            user = query("SELECT * FROM t_usuario WHERE LOWER(email) = %s LIMIT 1", (m,), fetchone=True)
            if not user:
                cl = query("SELECT dni FROM t_cliente WHERE LOWER(email) = %s LIMIT 1", (m,), fetchone=True)
                if cl:
                    user = query("SELECT * FROM t_usuario WHERE login = %s LIMIT 1", (cl['dni'],), fetchone=True)
            if user:
                break
        if not user:
            if not correos:
                flash('GitHub no entregó un correo verificado', 'danger')
                return redirect(url_for('login'))
            import oauth_registro
            return oauth_registro.pendiente('github', gu.get('id'), gu.get('name') or gu.get('login'), correos[0])
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
