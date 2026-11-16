from flask import jsonify, request, session

def registrar(app, query):
    @app.route('/api/socios_aportes')
    def api_socios_aportes():
        if not session.get('logueado'):
            return jsonify([]), 401
        a = (request.args.get('start') or '2000-01-01')[:10]
        b = (request.args.get('end') or '2100-01-01')[:10]
        r = query("SELECT s.nombre AS n, COALESCE(SUM(d.capital),0) AS t FROM t_det_capital d JOIN t_socio s ON s.id=d.id_socio WHERE DATE(d.fecha) BETWEEN %s AND %s GROUP BY s.id, s.nombre HAVING t>0 ORDER BY t DESC", (a, b), fetchall=True) or []
        return jsonify([[x['n'], float(x['t'])] for x in r])
