import os
from flask import session, request, redirect, url_for, flash, render_template

def registrar(app, query, sha1_hash):
    def ok():
        return session.get('logueado') and session.get('id_nivel') != 4

    @app.route('/perfil', methods=['GET', 'POST'])
    def perfil_admin():
        if not ok():
            return redirect(url_for('login'))
        uid = session.get('id')
        if request.method == 'POST':
            nombre = (request.form.get('nombre') or '').strip()
            email = (request.form.get('email') or '').strip()
            if not nombre:
                flash('El nombre es obligatorio', 'danger')
                return redirect(url_for('perfil_admin'))
            query("UPDATE t_usuario SET nombre=%s, email=%s WHERE id=%s", (nombre, email, uid), commit=True)
            session['nombre'] = nombre
            session['email'] = email
            f = request.files.get('foto')
            if f and f.filename:
                data = f.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    flash('La foto supera 2 MB', 'warning')
                elif data[:3] == b'\xff\xd8\xff' or data[:4] == b'\x89PNG':
                    d = os.path.join(app.static_folder, 'avatars')
                    os.makedirs(d, exist_ok=True)
                    with open(os.path.join(d, '%s.jpg' % uid), 'wb') as fh:
                        fh.write(data)
                else:
                    flash('La foto debe ser JPG o PNG', 'warning')
            flash('Perfil actualizado', 'success')
            return redirect(url_for('perfil_admin'))
        u = query("SELECT id, nombre, login, email, fecha_registro FROM t_usuario WHERE id=%s", (uid,), fetchone=True) or {}
        return render_template('perfil_pw.html', u=u)

    @app.route('/api/notificaciones', methods=['GET', 'POST'])
    def api_notificaciones():
        from flask import jsonify
        if not session.get('logueado'):
            return jsonify({'ok': False}), 401
        uid = session.get('id')
        if request.method == 'POST':
            v = 1 if request.form.get('activo') == '1' else 0
            query("UPDATE t_usuario SET notificaciones=%s WHERE id=%s", (v, uid), commit=True)
            return jsonify({'ok': True, 'activo': v})
        r = query("SELECT notificaciones FROM t_usuario WHERE id=%s", (uid,), fetchone=True)
        return jsonify({'ok': True, 'activo': int(r['notificaciones']) if r else 1})

    @app.route('/api/verificar_actual', methods=['POST'])
    def api_verificar_actual():
        from flask import jsonify
        import time
        if not ok():
            return jsonify({'ok': False}), 401
        ahora = time.time()
        intentos = [t for t in session.get('chk_actual', []) if ahora - t < 300]
        if len(intentos) >= 10:
            return jsonify({'ok': False, 'limite': True}), 429
        intentos.append(ahora)
        session['chk_actual'] = intentos
        a = (request.form.get('actual') or '').strip()
        if not a:
            return jsonify({'ok': True, 'valida': None})
        fila = query("SELECT id FROM t_usuario WHERE id=%s AND clave=%s",
                     (session.get('id'), sha1_hash(a)), fetchone=True)
        return jsonify({'ok': True, 'valida': bool(fila)})

    @app.route('/cuenta', methods=['GET', 'POST'])
    def cuenta_admin():
        if not ok():
            return redirect(url_for('login'))
        if request.method == 'POST':
            a = (request.form.get('actual') or '').strip()
            n = (request.form.get('nueva') or '').strip()
            c = (request.form.get('confirmar') or '').strip()
            uid = session.get('id')
            if not (a and n and c):
                flash('Todos los campos son obligatorios', 'danger')
            elif n != c:
                flash('Las contraseñas no coinciden', 'danger')
            elif len(n) < 10:
                flash('La contraseña debe tener al menos 10 caracteres', 'danger')
            elif not query("SELECT id FROM t_usuario WHERE id=%s AND clave=%s", (uid, sha1_hash(a)), fetchone=True):
                flash('La contraseña actual es incorrecta', 'danger')
            else:
                query("UPDATE t_usuario SET clave=%s, clave_v2=NULL WHERE id=%s", (sha1_hash(n), uid), commit=True)
                flash('Contraseña cambiada correctamente', 'success')
                return redirect(url_for('cuenta_admin'))
            return render_template('cuenta_pw.html', v_actual=a, v_nueva=n, v_conf=c)
        return render_template('cuenta_pw.html')
