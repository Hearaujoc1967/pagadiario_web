from flask import jsonify, request, session

def registrar(app, query):
    @app.route('/api/gastos_graficos')
    def api_gastos_graficos():
        if not session.get('logueado'):
            return jsonify([]), 401
        a = (request.args.get('start') or '2000-01-01')[:10]
        b = (request.args.get('end') or '2100-01-01')[:10]
        v = request.args.get('v') or 'tipo'
        if v == 'res':
            x = query("SELECT COALESCE(SUM(total),0) AS t, COUNT(*) AS n FROM t_gasto WHERE DATE(fecha) BETWEEN %s AND %s", (a, b), fetchone=True) or {}
            return jsonify([float(x.get('t') or 0), int(x.get('n') or 0)])
        if v == 'mes':
            sql = "SELECT DATE_FORMAT(g.fecha,'%%Y-%%m') AS n, SUM(g.total) AS v FROM t_gasto g WHERE DATE(g.fecha) BETWEEN %s AND %s GROUP BY n ORDER BY n"
        elif v == 'cob':
            sql = "SELECT COALESCE(c.nombre,'Sin asignar') AS n, SUM(g.total) AS v FROM t_gasto g LEFT JOIN t_cobrador c ON c.id=g.id_cobrador WHERE DATE(g.fecha) BETWEEN %s AND %s GROUP BY c.id, c.nombre ORDER BY v DESC"
        else:
            sql = "SELECT COALESCE(t.descripcion,'Sin tipo') AS n, SUM(d.monto) AS v FROM t_det_gasto d JOIN t_gasto g ON g.id=d.id_gasto LEFT JOIN t_tipo_gasto t ON t.id=d.id_tipo_gasto WHERE DATE(g.fecha) BETWEEN %s AND %s GROUP BY t.id, t.descripcion ORDER BY v DESC"
        r = query(sql, (a, b), fetchall=True) or []
        return jsonify([[x['n'], float(x['v'] or 0)] for x in r])
