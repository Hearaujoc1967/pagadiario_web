from flask import jsonify, request, session
from datetime import date, datetime, timedelta

def registrar(app, query):
    @app.route('/api/cobradores_graficos')
    def api_cobradores_graficos():
        if not session.get('logueado'):
            return jsonify({}), 401
        a = (request.args.get('start') or '2000-01-01')[:10]
        b = (request.args.get('end') or '2100-01-01')[:10]
        d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
        diario = (d1 - d0).days <= 62
        fmt = '%Y-%m-%d' if diario else '%Y-%m'
        cobs = query("SELECT id, nombre FROM t_cobrador ORDER BY id", fetchall=True) or []
        res = {c['id']: {'nombre': c['nombre'], 'real': 0.0, 'proy': 0.0,
                         'mora': 0.0, 'cartera': 0.0, 'n_mora': 0} for c in cobs}
        sr, sp = {}, {}
        pr = query("SELECT p.id_cobrador cid, p.total_prestado tp, p.numero_cuotas n, "
                   "p.fecha_prestamo f, p.total_debe td, p.dias_mora dm, t.descripcion tipo "
                   "FROM t_prestamo p LEFT JOIN t_tipo_prestamo t ON t.id=p.id_tipo_prestamo "
                   "LEFT JOIN t_estado_prestamo e ON e.id=p.id_estado_prestamo "
                   "WHERE e.descripcion NOT LIKE 'Por Aprobar%%' AND e.descripcion NOT LIKE 'Rechaz%%'",
                   fetchall=True) or []
        for x in pr:
            r = res.get(x['cid'])
            if not r:
                continue
            td = float(x['td'] or 0)
            r['cartera'] += td
            if (x['dm'] or 0) > 0:
                r['mora'] += td
                r['n_mora'] += 1
            n = int(x['n'] or 0)
            if n and x['f']:
                dias = {'Semanal': 7, 'Quincenal': 15, 'Mensual': 30}.get(x['tipo'] or 'Diario', 1)
                cuota = float(x['tp'] or 0) / n
                f0 = datetime.strptime(str(x['f'])[:10], '%Y-%m-%d').date()
                for i in range(1, n + 1):
                    fe = f0 + timedelta(days=dias * i)
                    if d0 <= fe <= d1:
                        r['proy'] += cuota
                        k = fe.strftime(fmt)
                        sp[k] = sp.get(k, 0) + cuota
        pg = query("SELECT p.id_cobrador cid, d.monto m, d.fecha_cobro f FROM t_det_prestamo d "
                   "JOIN t_prestamo p ON p.id=d.id_prestamo WHERE d.fecha_cobro BETWEEN %s AND %s",
                   (a, b), fetchall=True) or []
        for x in pg:
            m = float(x['m'] or 0)
            if x['cid'] in res:
                res[x['cid']]['real'] += m
            k = x['f'].strftime(fmt)
            sr[k] = sr.get(k, 0) + m
        ps = sorted(set(sr) | set(sp))
        return jsonify({'cobradores': list(res.values()), 'periodos': ps, 'diario': diario,
                        'real': [round(sr.get(p, 0)) for p in ps],
                        'proy': [round(sp.get(p, 0)) for p in ps]})
