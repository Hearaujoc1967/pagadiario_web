from datetime import datetime
from flask import jsonify, request, session

def registrar(app, query):
    @app.route('/api/cierre_graficos')
    def api_cierre_graficos():
        if not session.get('logueado'):
            return jsonify([]), 401
        a = (request.args.get('start') or '2000-01-01')[:10]
        b = (request.args.get('end') or '2100-01-01')[:10]
        v = request.args.get('v') or 'cobrado'
        try:
            dias = (datetime.strptime(b, '%Y-%m-%d') - datetime.strptime(a, '%Y-%m-%d')).days
        except ValueError:
            dias = 9999
        fmt = '%%Y-%%m-%%d' if dias <= 62 else '%%Y-%%m'
        if v == 'cobrado':
            sql = "SELECT DATE_FORMAT(fecha_cobro,'" + fmt + "') AS n, SUM(monto) AS x FROM t_det_prestamo WHERE DATE(fecha_cobro) BETWEEN %s AND %s GROUP BY n ORDER BY n"
            r = query(sql, (a, b), fetchall=True) or []
            return jsonify([[x['n'], float(x['x'] or 0)] for x in r])
        sql = "SELECT DATE_FORMAT(fecha,'" + fmt + "') AS n, SUM(monto) AS e, SUM(monto_recibido) AS r FROM t_cierre WHERE DATE(fecha) BETWEEN %s AND %s GROUP BY n ORDER BY n"
        r = query(sql, (a, b), fetchall=True) or []
        if v == 'dif':
            return jsonify([[x['n'], float(x['r'] or 0) - float(x['e'] or 0)] for x in r])
        return jsonify([[x['n'], float(x['e'] or 0), float(x['r'] or 0)] for x in r])
