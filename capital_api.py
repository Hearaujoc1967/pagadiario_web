from flask import jsonify, request, session

def registrar(app, query):
    @app.route('/api/capital_evolucion')
    def api_capital_evolucion():
        if not session.get('logueado'):
            return jsonify([]), 401
        a = (request.args.get('start') or '2000-01-01')[:10]
        b = (request.args.get('end') or '2100-01-01')[:10]
        base = query("SELECT COALESCE(SUM(capital),0) AS t FROM t_det_capital WHERE DATE(fecha) < %s", (a,), fetchone=True)
        acum = float((base or {}).get('t') or 0)
        r = query("SELECT DATE_FORMAT(fecha,'%%Y-%%m') AS m, SUM(capital) AS t FROM t_det_capital WHERE DATE(fecha) BETWEEN %s AND %s GROUP BY m ORDER BY m", (a, b), fetchall=True) or []
        out = []
        for x in r:
            t = float(x['t'])
            acum += t
            out.append([x['m'], t, acum])
        return jsonify(out)
