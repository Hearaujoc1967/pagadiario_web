import hashlib, secrets
from flask import redirect, request, session, flash, url_for, render_template_string
from telefono import normalizar

def pendiente(prov, pid, nombre, email):
    session['oauth_pend'] = {'prov': prov, 'pid': str(pid), 'nombre': nombre or '', 'email': (email or '').lower()}
    return redirect(url_for('oauth_completar'))

def _entrar(query, uid):
    u = query("SELECT * FROM t_usuario WHERE id = %s LIMIT 1", (uid,), fetchone=True)
    cl = query("SELECT id, nombre, dni, email FROM t_cliente WHERE dni = %s LIMIT 1", (u['login'],), fetchone=True)
    session['logueado'] = True
    session['id'] = u['id']
    session['id_estado_usuario'] = u['id_estado_usuario']
    session['id_nivel'] = u['id_nivel']
    session['nombre'] = u['nombre']
    session['login'] = u['login']
    session['cliente_id'] = cl['id']
    session['cliente_nombre'] = cl['nombre']
    session['cliente_dni'] = cl['dni']
    session['email'] = cl.get('email') or ''
    return redirect(url_for('portal'))

FORM = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Completa tu registro</title>
<link href="{{ url_for('static', filename='metronic/css/style.bundle.css') }}" rel="stylesheet"></head>
<body class="bg-light"><div class="container py-10" style="max-width:480px">
<div class="card"><div class="card-body p-8">
<h3 class="mb-2">Completa tu registro</h3>
<p class="text-muted">Entras con {{ p.prov|capitalize }}. Faltan unos datos para crear tu cuenta de Cliente.</p>
{% for c, m in get_flashed_messages(with_categories=true) %}<div class="alert alert-{{ c }}">{{ m }}</div>{% endfor %}
<form method="post">
<label class="form-label">Nombre</label><input class="form-control mb-4" name="nombre" value="{{ p.nombre }}" required>
<label class="form-label">Cédula</label><input class="form-control mb-4" name="dni" inputmode="numeric" required>
<label class="form-label">Teléfono (celular)</label><input class="form-control mb-4" name="telf" inputmode="tel" required>
<label class="form-label">Correo</label><input class="form-control mb-6" type="email" name="email" value="{{ p.email }}" required>
<button class="btn btn-primary w-100">Crear mi cuenta</button>
<a class="btn btn-light w-100 mt-3" href="{{ url_for('login') }}">Cancelar</a>
</form></div></div></div></body></html>"""

def registrar(app, query):
    @app.route('/auth/completar', methods=['GET', 'POST'])
    def oauth_completar():
        p = session.get('oauth_pend')
        if not p:
            return redirect(url_for('login'))
        if request.method == 'GET':
            return render_template_string(FORM, p=p)
        nombre = request.form.get('nombre', '').strip()
        dni = ''.join(c for c in request.form.get('dni', '') if c.isdigit())
        telf = normalizar(request.form.get('telf', ''))
        email = request.form.get('email', '').strip().lower()
        if not nombre or len(dni) < 6 or not telf or '@' not in email:
            flash('Revisa cédula, teléfono y correo', 'danger')
            return render_template_string(FORM, p=p)
        for col, val, txt in (('dni', dni, 'cédula'), ('telf', telf, 'teléfono'), ('email', email, 'correo')):
            if query("SELECT id FROM t_cliente WHERE " + col + " = %s", (val,), fetchone=True):
                flash('Ya existe un cliente con ese ' + txt, 'danger')
                return render_template_string(FORM, p=p)
        if query("SELECT id FROM t_usuario WHERE login = %s", (dni,), fetchone=True):
            flash('Ya existe un usuario con esa cédula', 'danger')
            return render_template_string(FORM, p=p)
        ver = 0 if p['prov'] == 'facebook' else 1
        query("INSERT INTO t_cliente (id_tipo_estado_cliente, id_reputacion, dni, nombre, telf, email, email_verificado, telefono_verificado, fecha_registro) VALUES (1, 1, %s, %s, %s, %s, %s, 0, CURDATE())", (dni, nombre, telf, email, ver), commit=True)
        clave = hashlib.sha1(secrets.token_hex(16).encode()).hexdigest()
        query("INSERT INTO t_usuario (id_estado_usuario, id_nivel, nombre, login, clave, email) VALUES (1, 4, %s, %s, %s, %s)", (nombre, dni, clave, email), commit=True)
        u = query("SELECT id FROM t_usuario WHERE login = %s LIMIT 1", (dni,), fetchone=True)
        query("INSERT INTO t_oauth_vinculo (proveedor, proveedor_id, id_usuario) VALUES (%s, %s, %s)", (p['prov'], p['pid'], u['id']), commit=True)
        session.pop('oauth_pend', None)
        return _entrar(query, u['id'])
