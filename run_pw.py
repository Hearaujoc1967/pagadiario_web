import os
import app as A

A.app.config['SESSION_COOKIE_NAME'] = 'pagadiario_web_session'
A.app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session_pw')
os.makedirs(A.app.config['SESSION_FILE_DIR'], exist_ok=True)

_orig = A.render_template
_map = {'dashboard.html': 'dashboard_pw.html'}
A.render_template = lambda t, *a, **k: _orig(_map.get(t, t), *a, **k)

if __name__ == '__main__':
    if os.environ.get('PW_SSL', '1') == '1':
        d = os.path.expanduser('~/pagadiario_web/ssl_pw')
        print('PW test en https://localhost:5001')
        A.app.run(host='127.0.0.1', port=5001, ssl_context=(d + '/cert.pem', d + '/key.pem'), threaded=True)
        raise SystemExit
    from waitress import serve
    print('PW test en http://127.0.0.1:5001')
    serve(A.app, host='127.0.0.1', port=5001, threads=2)
