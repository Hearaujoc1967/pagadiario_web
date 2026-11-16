from flask import jsonify, request, session

def registrar(app, query):
    def _rango():
        return (request.args.get('start') or '2000-01-01',
                request.args.get('end') or '2100-01-01')

    @app.route('/api/prestamos_estados')
    def api_prestamos_estados():
        if not session.get('logueado'):
            return jsonify({}), 401
        r = query("SELECT id_estado_prestamo AS e, COUNT(*) AS n, COALESCE(SUM(monto_prestado),0) AS m, COALESCE(SUM(total_debe),0) AS d FROM t_prestamo WHERE fecha_prestamo BETWEEN %s AND %s GROUP BY id_estado_prestamo", _rango(), fetchall=True) or []
        return jsonify({str(x['e']): {'n': int(x['n']), 'm': float(x['m']), 'd': float(x['d'])} for x in r})

    @app.route('/api/prestamos_madre')
    def api_prestamos_madre():
        if not session.get('logueado'):
            return jsonify({}), 401
        p = _rango()
        from datetime import date as _d
        try:
            _n = (_d.fromisoformat(p[1][:10]) - _d.fromisoformat(p[0][:10])).days
        except Exception:
            _n = 99999
        FM = '%%Y-%%m-%%d' if _n <= 62 else '%%Y-%%m'
        cob = query("SELECT DATE_FORMAT(d.fecha_cobro,'" + FM + "') AS m, SUM(d.monto) AS t, SUM(d.monto*p.monto_prestado/NULLIF(p.total_prestado,0)) AS c FROM t_det_prestamo d JOIN t_prestamo p ON p.id=d.id_prestamo WHERE d.fecha_cobro BETWEEN %s AND %s GROUP BY m ORDER BY m", p, fetchall=True) or []
        des = query("SELECT DATE_FORMAT(fecha_prestamo,'" + FM + "') AS m, SUM(total_prestado) AS t FROM t_prestamo WHERE id_estado_prestamo IN (2,3) AND fecha_prestamo BETWEEN %s AND %s GROUP BY m ORDER BY m", p, fetchall=True) or []
        dn = query("SELECT COALESCE(SUM(monto_prestado),0) AS c, COALESCE(SUM(interes),0) AS i FROM t_prestamo WHERE id_estado_prestamo IN (2,3) AND fecha_prestamo BETWEEN %s AND %s", p, fetchone=True) or {}
        car = query("SELECT COALESCE(SUM(id_estado_prestamo=3),0) AS pag, COALESCE(SUM(id_estado_prestamo=2 AND dias_mora=0),0) AS dia, COALESCE(SUM(id_estado_prestamo=2 AND dias_mora BETWEEN 1 AND 15),0) AS tem, COALESCE(SUM(id_estado_prestamo=2 AND dias_mora>15),0) AS gra FROM t_prestamo WHERE fecha_prestamo BETWEEN %s AND %s", p, fetchone=True) or {}
        C = {x['m']: x for x in cob}
        D = {x['m']: float(x['t'] or 0) for x in des}
        meses = sorted(set(C) | set(D))
        tot = [float(C[m]['t'] or 0) if m in C else 0.0 for m in meses]
        cap = [float(C[m]['c'] or 0) if m in C else 0.0 for m in meses]
        return jsonify({'meses': meses, 'cobro': tot, 'capital': cap,
            'interes': [round(t - c) for t, c in zip(tot, cap)],
            'desembolso': [D.get(m, 0.0) for m in meses],
            'dona': {'capital': float(dn.get('c') or 0), 'interes': float(dn.get('i') or 0)},
            'cartera': {'pagados': int(car.get('pag') or 0), 'al_dia': int(car.get('dia') or 0), 'temprana': int(car.get('tem') or 0), 'grave': int(car.get('gra') or 0)}})

    @app.route('/api/clientes_salud')
    def api_clientes_salud():
        if not session.get('logueado'):
            return jsonify({}), 401
        p = _rango()
        est = query("SELECT COALESCE(e.descripcion,'Sin estado') AS d, COUNT(*) AS n FROM t_cliente c LEFT JOIN t_tipo_estado_cliente e ON c.id_tipo_estado_cliente=e.id GROUP BY d", fetchall=True) or []
        ag = query("SELECT COALESCE(SUM(dias_mora=0),0) AS a, COALESCE(SUM(dias_mora BETWEEN 1 AND 15),0) AS b, COALESCE(SUM(dias_mora BETWEEN 16 AND 30),0) AS c, COALESCE(SUM(dias_mora>30),0) AS d FROM t_prestamo WHERE id_estado_prestamo=2 AND fecha_prestamo BETWEEN %s AND %s", p, fetchone=True) or {}
        rep = query("SELECT COALESCE(r.descripcion,'Sin reputación') AS d, COUNT(*) AS n FROM t_cliente c LEFT JOIN t_reputacion r ON c.id_reputacion=r.id GROUP BY d ORDER BY n DESC", fetchall=True) or []
        cob = query("SELECT COALESCE(cb.nombre,'Sin cobrador') AS d, COUNT(*) AS n FROM t_cliente c LEFT JOIN t_cobrador cb ON c.id_cobrador=cb.id GROUP BY d ORDER BY n DESC", fetchall=True) or []
        return jsonify({'estado': [[x['d'], int(x['n'])] for x in est],
            'reputacion': [[x['d'], int(x['n'])] for x in rep],
            'cobrador': [[x['d'], int(x['n'])] for x in cob],
            'aging': [['Al día', int(ag.get('a') or 0)], ['1-15 días', int(ag.get('b') or 0)], ['16-30 días', int(ag.get('c') or 0)], ['Más de 30', int(ag.get('d') or 0)]]})
