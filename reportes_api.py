from datetime import datetime
from flask import jsonify, request, session

def registrar(app, query):
    @app.route('/api/reportes_graficos')
    def api_reportes_graficos():
        if not session.get('logueado'):
            return jsonify([]), 401
        a = (request.args.get('start') or '2000-01-01')[:10]
        b = (request.args.get('end') or '2100-01-01')[:10]
        v = request.args.get('v') or 'flujo'
        try:
            dias = (datetime.strptime(b, '%Y-%m-%d') - datetime.strptime(a, '%Y-%m-%d')).days
        except ValueError:
            dias = 9999
        fmt = '%%Y-%%m-%%d' if dias <= 62 else '%%Y-%%m'
        if v == 'tabla':
            from models.reporte import ReporteModel as RM
            from decimal import Decimal
            def ser(rows):
                out = []
                for r in rows or []:
                    o = {}
                    for k, x in r.items():
                        if hasattr(x, 'isoformat'):
                            x = x.isoformat()[:10]
                        elif isinstance(x, Decimal):
                            x = float(x)
                        o[k] = x
                    out.append(o)
                return out
            t = request.args.get('t') or 'pre'
            if t == 'pre':
                return jsonify(ser(RM.prestamos_por_fecha(a, b)))
            if t == 'cob':
                return jsonify(ser(RM.cobros_por_fecha(a, b)))
            if t == 'gas':
                return jsonify(ser(RM.gastos_por_fecha(a, b)))
            d = {}
            for x in RM.prestamos_por_cobrador(a, b) or []:
                d[x['cobrador']] = {'id_cobrador': x.get('id_cobrador'), 'cobrador': x['cobrador'], 'prestamos': int(x['total_prestamos'] or 0), 'colocado': float(x['total_monto'] or 0), 'por_cobrar': float(x['total_debe'] or 0), 'pagos': 0, 'cobrado': 0.0}
            for x in RM.cobros_por_cobrador(a, b) or []:
                e = d.setdefault(x['cobrador'], {'id_cobrador': x.get('id_cobrador'), 'cobrador': x['cobrador'], 'prestamos': 0, 'colocado': 0.0, 'por_cobrar': 0.0, 'pagos': 0, 'cobrado': 0.0})
                e['pagos'] = int(x['total_pagos'] or 0)
                e['cobrado'] = float(x['total_cobrado'] or 0)
            return jsonify(sorted(d.values(), key=lambda r: -(r['cobrado'] + r['colocado'])))
        if v == 'kpi':
            from models.caja import CajaModel
            cj = CajaModel.obtener_caja_principal()
            n = query("SELECT COUNT(*) AS n FROM t_cliente", fetchone=True) or {}
            return jsonify({'clientes': int(n.get('n') or 0), 'caja': float(cj['total_caja']) if cj else 0})
        if v == 'deudores':
            r = query("SELECT c.id AS id_cliente, c.nombre AS cliente, c.dni AS dni, COUNT(p.id) AS prestamos, SUM(p.total_debe) AS deuda FROM t_prestamo p LEFT JOIN t_cliente c ON p.id_cliente=c.id WHERE p.id_estado_prestamo = 2 AND p.total_debe > 0 GROUP BY c.id, c.nombre, c.dni ORDER BY deuda DESC LIMIT 50", fetchall=True) or []
            return jsonify([{'id_cliente': x['id_cliente'], 'cliente': x['cliente'] or 'Sin nombre', 'dni': x['dni'], 'prestamos': int(x['prestamos'] or 0), 'deuda': float(x['deuda'] or 0)} for x in r])
        if v == 'res':
            p = query("SELECT COUNT(*) n, COALESCE(SUM(monto_prestado),0) m, COALESCE(SUM(total_debe),0) d FROM t_prestamo WHERE DATE(fecha_prestamo) BETWEEN %s AND %s", (a, b), fetchone=True) or {}
            c = query("SELECT COUNT(*) n, COALESCE(SUM(monto),0) m FROM t_det_prestamo WHERE DATE(fecha_cobro) BETWEEN %s AND %s", (a, b), fetchone=True) or {}
            g = query("SELECT COUNT(*) n, COALESCE(SUM(total),0) m FROM t_gasto WHERE DATE(fecha) BETWEEN %s AND %s", (a, b), fetchone=True) or {}
            return jsonify({'prestamos': int(p.get('n') or 0), 'colocado': float(p.get('m') or 0), 'por_cobrar': float(p.get('d') or 0),
                            'pagos': int(c.get('n') or 0), 'cobrado': float(c.get('m') or 0),
                            'gastos_n': int(g.get('n') or 0), 'gastos': float(g.get('m') or 0)})
        if v == 'flujo':
            d = {}
            for x in query("SELECT DATE_FORMAT(fecha_prestamo,'" + fmt + "') n, SUM(monto_prestado) x FROM t_prestamo WHERE DATE(fecha_prestamo) BETWEEN %s AND %s GROUP BY n", (a, b), fetchall=True) or []:
                d.setdefault(x['n'], [0, 0])[0] = float(x['x'] or 0)
            for x in query("SELECT DATE_FORMAT(fecha_cobro,'" + fmt + "') n, SUM(monto) x FROM t_det_prestamo WHERE DATE(fecha_cobro) BETWEEN %s AND %s GROUP BY n", (a, b), fetchall=True) or []:
                d.setdefault(x['n'], [0, 0])[1] = float(x['x'] or 0)
            return jsonify([[k, d[k][0], d[k][1]] for k in sorted(d)])
        if v == 'cobrador':
            d = {}
            for x in query("SELECT COALESCE(cb.nombre,'Sin asignar') n, SUM(p.monto_prestado) x FROM t_prestamo p LEFT JOIN t_cobrador cb ON p.id_cobrador=cb.id WHERE DATE(p.fecha_prestamo) BETWEEN %s AND %s GROUP BY n", (a, b), fetchall=True) or []:
                d.setdefault(x['n'], [0, 0])[0] = float(x['x'] or 0)
            for x in query("SELECT COALESCE(cb.nombre,'Sin asignar') n, SUM(dp.monto) x FROM t_det_prestamo dp LEFT JOIN t_prestamo p ON dp.id_prestamo=p.id LEFT JOIN t_cobrador cb ON p.id_cobrador=cb.id WHERE DATE(dp.fecha_cobro) BETWEEN %s AND %s GROUP BY n", (a, b), fetchall=True) or []:
                d.setdefault(x['n'], [0, 0])[1] = float(x['x'] or 0)
            return jsonify(sorted([[k, d[k][0], d[k][1]] for k in d], key=lambda r: -(r[1] + r[2])))
        r = query("SELECT DATE_FORMAT(fecha,'" + fmt + "') n, SUM(total) x FROM t_gasto WHERE DATE(fecha) BETWEEN %s AND %s GROUP BY n ORDER BY n", (a, b), fetchall=True) or []
        return jsonify([[x['n'], float(x['x'] or 0)] for x in r])
