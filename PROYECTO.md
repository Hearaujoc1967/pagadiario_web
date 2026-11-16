# 📖 Contexto del Proyecto — Tanishi Finance + Pagadiario

> Pegar este bloque al inicio de un chat nuevo para retomar el hilo.

## 🎯 Objetivo
Integrar Tanishi Finance como **cara frontal** (landing + login) de `pagadiario_local`,
sin tocar el backend Flask existente ni la BD `bd_prestamo`.

## 🗂️ Estructura
- `~/pagadiario_local/`      → Proyecto Flask principal (producción)
- `~/Tanishifinance-main/`   → Landing traducida (fuente)
- `~/backups/`               → Respaldos con fecha

## 🎨 Paleta Tanishi
- Navy:          #07111f
- Navy 2:        #0d1b2a
- Dorado:        #f5c542
- Dorado oscuro: #d4a017
- Dorado claro:  #ffd966

## ✅ Hecho
- [x] Landing Tanishi 100% traducida (index.html, app.js, estilos.css)
- [x] Separación de CSS y JS desde el HTML monolítico original
- [x] Backend `pagadiario_local` intacto y funcionando
- [x] Login rediseñado a colores Tanishi (navy/dorado)
- [x] Botones, panel lateral, inputs y títulos del login en estilo Tanishi
- [x] Archivos copiados:
      - `templates/tanishi/index.html` (344 líneas, con url_for)
      - `static/tanishi/estilos.css` (27 KB)
      - `static/tanishi/tanishi.js` (63 líneas, limpio)
      - `static/tanishi/img/logo.png` (2.6 MB, pendiente optimizar)
- [x] **Ruta `/` modificada**: sirve la landing Tanishi si no hay sesión
- [x] **Landing funcionando** en `http://192.168.1.38:5000/`
- [x] Flujo completo: landing → login → dashboard (admin) o portal (cliente)

## ⏳ Pendiente
### Fase B — Detalles de la landing
- [ ] Traducir el lema "AAPKA VISHWAS, HAMARI ZIMMEDARI"
- [ ] Traducir `<title>` y `<meta>` (aún en inglés)
- [ ] Optimizar `logo.png` (2.6 MB → ~50 KB)

### Fase C — Portal cliente
- [ ] Rediseñar `templates/portal.html` con estética Tanishi
- [ ] Rediseñar `templates/base_cliente.html` (menú lateral, header)
- [ ] Ajustar `partials_cliente/_header.html` y `_sidebar.html`

### Fase D — Personalizaciones del usuario
- [ ] Cambios específicos por definir (el usuario los indicará)

## 📋 Reglas de trabajo
1. **Backup antes de cada cambio** (`cp archivo archivo.antes_X`)
2. **Un cambio a la vez**, verificar antes de continuar
3. **Leer el archivo completo** antes de modificarlo (no adivinar)
4. **Usar comandos verificables** (`grep`, `sed`, `perl`, `cat`)
5. **No romper animaciones** ni `z-index`/`transform` sin revisar el contexto
6. **Idioma:** todo en español (variables, comentarios, textos visibles)
7. **Backend intacto:** no tocar `app.py` salvo la ruta `/`
8. **BD intacta:** `bd_prestamo` no se modifica sin avisar

## 🔑 Datos clave
- Servidor Flask: `http://0.0.0.0:5000` (Waitress)
- BD:            `bd_prestamo` (MariaDB por socket Unix)
- Hash de claves: SHA-1 (compatible con CodeIgniter)
- Login:         `/login` (form `txt_nombre_ususario` + `txt_pass`)
- Portal:        `/portal` (solo `id_nivel == 4`)
- Landing:       `/` (solo si NO hay sesión)

## 📅 Bitácora
- 2026-10-14: Login rediseñado a colores Tanishi ✅
- 2026-10-14: Creación de este PROYECTO.md
- 2026-10-14: Ruta `/` modificada para servir landing Tanishi ✅
- 2026-10-14: Landing verificada y funcionando en producción ✅
- Próximo:    Traducir lema, meta tags y optimizar logo

## 📅 Bitácora extendida (14/10/2026)
- Login rediseñado a colores Tanishi ✅
- Ruta `/` modificada → landing Tanishi ✅
- Landing verificada ✅
- PROYECTO.md creado ✅
- Lema hindi → español ✅
- Meta description → español ✅
- Logo optimizado (2.6 MB → 100 KB) ✅
- Header: "Tanishi Finance" → "Pagadiario Web" ✅
- Badge hero: "Financial assistance..." → "Asistencia financiera y soporte digital" ✅
- Header compactado, lema sin cortar ✅

## 📌 Estado actual
- **Landing**: `http://192.168.1.38:5000/` ✅ funcionando
- **Login**: `/login` ✅ rediseñado Tanishi (dorado/navy)
- **Dashboard**: `/dashboard` ✅ funciona (admin/staff)
- **Portal cliente**: `/portal` ✅ funciona (pendiente rediseño)
- **Servidor**: `python app.py` en Termux, puerto 5000

## 🚧 Pendiente
### Fase C — Rediseñar portal cliente
- [ ] `templates/portal.html` con estética Tanishi
- [ ] `templates/base_cliente.html` (menú lateral, header)
- [ ] `partials_cliente/_header.html` y `_sidebar.html`

### Fase D — Personalizaciones del usuario
- [ ] Por definir
