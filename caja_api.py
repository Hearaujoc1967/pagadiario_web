from flask import jsonify, request, session
from datetime import date

def registrar(app, query):
    @app.route('/api/caja_graficos')
    def api_caja_graficos():
        if not session.get('logueado'):
            return jsonify({}), 401
        a = (request.args.get('start') or '2000-01-01')[:10]
        b = (request.args.get('end') or '2100-01-01')[:10]
        diario = (date.fromisoformat(b) - date.fromisoformat(a)).days <= 62
        fm = '%%Y-%%m-%%d' if diario else '%%Y-%%m'
        s = query("SELECT DATE_FORMAT(fecha,'" + fm + "') p, SUM(IF(id_tipo_ingreso IN (1,2),monto,0)) i, SUM(IF(id_tipo_ingreso IN (3,4),monto,0)) e FROM t_det_caja WHERE fecha BETWEEN %s AND %s GROUP BY p ORDER BY p", (a, b), fetchall=True) or []
        t = query("SELECT t.descripcion n, SUM(d.monto) m FROM t_det_caja d JOIN t_tipo_caja t ON t.id=d.id_tipo_ingreso WHERE d.id_tipo_ingreso IN (1,2,3,4) AND d.fecha BETWEEN %s AND %s GROUP BY t.id, t.descripcion ORDER BY t.id", (a, b), fetchall=True) or []
        c = query("SELECT c.fecha_apertura f, SUM(IF(d.id_tipo_ingreso=5,d.monto,0)) ap, SUM(IF(d.id_tipo_ingreso IN (1,2),d.monto,0)) i, SUM(IF(d.id_tipo_ingreso IN (3,4),d.monto,0)) e, SUM(IF(d.id_tipo_ingreso=6,d.monto,0)) ci FROM t_caja c LEFT JOIN t_det_caja d ON d.id_caja=c.id WHERE c.fecha_apertura BETWEEN %s AND %s GROUP BY c.id, c.fecha_apertura ORDER BY c.fecha_apertura", (a, b), fetchall=True) or []
        cu = [[str(x['f']), float(x['ci'] - (x['ap'] + x['i'] - x['e']))] for x in c if x['ci'] and x['ci'] > 0]
        return jsonify({'diario': diario, 'periodos': [x['p'] for x in s], 'ing': [float(x['i']) for x in s], 'egr': [float(x['e']) for x in s], 'tipos': [[x['n'], float(x['m'])] for x in t], 'cuadre': cu})
