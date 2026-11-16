/* =====================================================================
   Pagadiario Web · auth.js
   Un solo archivo (reemplaza los 3 <script> inline). Módulos:
   1 Utilidades · 2 Apariencia · 3 Clima · 4 Vistas · 5 Contraseñas
   6 Login · 7 Registro · 8 Recuperar contraseña · 9 Avisos
   Los endpoints son los mismos del código original.
   ===================================================================== */
(() => {
  'use strict';

  /* ---------- 1. UTILIDADES ---------- */
  const API = {
    loginUser: '/api/validar_login_usuario',
    field: '/api/validar_campo',
    otp: '/api/enviar_otp',
    register: '/api/registro_cliente',
    recover: '/api/recuperar_password',
  };
  const OTP_COOLDOWN = 45; // segundos
  const NO_DB = '⚠ Sin conexión a la base'; // el servidor respondió que la base de datos no está disponible
  const root = document.documentElement;
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* modo privado */ } },
  };

  /** POST con FormData, tiempo límite y JSON seguro. Lanza error si falla la red. */
  async function post(url, data, timeout = 10000) {
    const fd = new FormData();
    Object.entries(data).forEach(([k, v]) => fd.append(k, v));
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(url, { method: 'POST', body: fd, signal: ctrl.signal, credentials: 'same-origin' });
      let json = null;
      try { json = await res.json(); } catch { /* respuesta sin JSON */ }
      if (!json) throw new Error(`HTTP ${res.status}`);
      return json;
    } finally { clearTimeout(timer); }
  }

  /* ---------- 9. AVISOS (toasts y mensajes de Flask) ---------- */
  function toast(msg, type = 'info', ms = 3800) {
    const el = document.createElement('div');
    el.className = 'toast'; el.dataset.type = type; el.textContent = msg;
    $('#toasts').append(el);
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 450); }, ms);
  }
  $$('.alert').forEach(el => setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 550); }, 4000));

  function feedback(id, msg = '', state = '') {
    const el = $(`#feedback-${id}`);
    if (!el) return;
    el.textContent = msg;
    if (state) el.dataset.s = state; else delete el.dataset.s;
  }

  /* ---------- 2. APARIENCIA: layout, fondo y tema ---------- */
  const LAYOUTS = ['a', 'b', 'c'];
  const BG_COUNT = 4;

  function setLayout(l) { if (!LAYOUTS.includes(l)) l = 'a'; root.dataset.layout = l; store.set('auth.layout', l); }
  function setBg(i) {
    const n = ((+i % BG_COUNT) + BG_COUNT) % BG_COUNT;
    root.dataset.bg = n; root.dataset.theme = n === 0 ? 'light' : 'dark'; // los fondos 1-3 son oscuros
    store.set('auth.bg', n);
  }

  root.dataset.layout = 'x'; root.dataset.bg = '1'; root.dataset.theme = 'dark'; // base fija: cilindro oscuro

  /* ---------- 3. CLIMA Y RELOJ (Bogotá) ---------- */
  const TZ = 'America/Bogota';
  const fmtDate = new Intl.DateTimeFormat('es-CO', { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ });
  const fmtTime = new Intl.DateTimeFormat('es-CO', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
  const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'];
  const fmtDow = new Intl.DateTimeFormat('es-CO', { weekday: 'short', timeZone: TZ });
  const fmtDay = new Intl.DateTimeFormat('es-CO', { day: 'numeric', timeZone: TZ });

  function tick() {
    const now = new Date();
    $('#wx-date').textContent = fmtDate.format(now).replace(/\./g, '');
    $('#wx-time').textContent = fmtTime.format(now);
  }
  function weatherIcon(code, isDay) {
    if (code === 0) return isDay ? ['sun', 'Despejado'] : ['moon', 'Despejado'];
    if (code <= 2) return ['partly', 'Parcialmente nublado'];
    if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return ['rain', 'Lluvia'];
    if (code >= 95) return ['storm', 'Tormenta'];
    return ['cloud', 'Nublado'];
  }
  async function loadWeather() {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    try {
      const res = await fetch('https://api.open-meteo.com/v1/forecast?latitude=4.6097&longitude=-74.0817&current_weather=true&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=America%2FBogota&forecast_days=7', { signal: ctrl.signal });
      const { current_weather: w, daily } = await res.json();
      renderWeek(daily);
      const [icon, desc] = weatherIcon(w.weathercode, w.is_day === 1);
      $('#wx-temp').textContent = `${Math.round(w.temperature)}°`;
      $('#wx-desc').textContent = desc;
      $('#wx-icon').setAttribute('href', `#w-${icon}`);
      $('#wx-wind').textContent = `${Math.round(w.windspeed)} km/h ${COMPASS[Math.round(w.winddirection / 45) % 8]}`;
    } catch { $('#wx-desc').textContent = 'Sin datos del clima'; $('#wxw-list').textContent = 'Sin datos'; }
    finally { clearTimeout(timer); }
  }
  /* Widget semanal (solo registro): se crea aquí, no hace falta tocar la plantilla */
  const wxWeek = document.createElement('aside');
  wxWeek.id = 'wx-week'; wxWeek.className = 'wxw glass m';
  wxWeek.innerHTML = '<div class="wxw__list" id="wxw-list">…</div>';
  $('#wx').after(wxWeek);

  function renderWeek(d) {
    if (!d || !d.time) return;
    $('#wxw-list').innerHTML = d.time.map((t, i) => {
      const day = new Date(`${t}T12:00:00-05:00`), [icon] = weatherIcon(d.weathercode[i], true);
      return `<div class="wxd"><b>${fmtDow.format(day).replace('.', '')} ${fmtDay.format(day)}</b>` +
        `<svg class="wic" aria-hidden="true"><use href="#w-${icon}"/></svg>` +
        `<span>${Math.round(d.temperature_2m_max[i])}°<i>/${Math.round(d.temperature_2m_min[i])}°</i></span></div>`;
    }).join('');
  }

  /* En el registro el clima alterna entre pastilla y semana con un toque */
  function setRegWx(mode) { root.dataset.regwx = mode; store.set('auth.regwx', mode); }
  function tapButton(el, label, fn) {
    el.setAttribute('tabindex', '0'); el.setAttribute('role', 'button'); el.setAttribute('aria-label', label);
    el.addEventListener('click', fn);
    el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); } });
  }
  setRegWx(store.get('auth.regwx', 'week'));
  tapButton(wxWeek, 'Pronóstico semanal. Toca para ver solo la temperatura', () => setRegWx('chip'));
  const wxEl = $('#wx');
  const wxShowWeek = () => { if (root.dataset.view === 'register') setRegWx('week'); };
  wxEl.addEventListener('click', wxShowWeek);
  wxEl.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && root.dataset.view === 'register') { e.preventDefault(); wxShowWeek(); } });
  function syncWxRole(reg) { // la tarjeta solo es "botón" en el registro
    if (reg) { wxEl.setAttribute('tabindex', '0'); wxEl.setAttribute('role', 'button'); wxEl.setAttribute('aria-label', 'Clima. Toca para ver el pronóstico semanal'); }
    else { ['tabindex', 'role'].forEach(a => wxEl.removeAttribute(a)); wxEl.setAttribute('aria-label', 'Clima en Bogotá'); }
  }

  tick(); setInterval(tick, 15000);
  loadWeather(); setInterval(loadWeather, 10 * 60 * 1000);

  /* ---------- 4. VISTAS: login <-> registro ---------- */
  const SWS = [$('#view-switch'), $('#view-switch-2')], LBL = [$('#sw-label'), $('#sw-label-2')], drum = $('#drum');
  const FACE = { login: $('#login-view'), register: $('#register-view') };
  let current = 'login', ang = 0, swBusy = false;
  /* La perilla cambia y, tras 150 ms, gira el cilindro 180° hacia la otra cara (la oculta queda inert). */
  function setView(name, delay = 0) {
    const reg = name === 'register';
    SWS.forEach(s => s.setAttribute('aria-checked', String(reg)));
    LBL.forEach(l => { l.textContent = reg ? 'LOG IN' : 'SIGN UP'; });
    if (name === current) return; current = name;
    setTimeout(() => { FACE.login.inert = reg; FACE.register.inert = !reg; ang += 180; drum.style.transform = `rotateY(${ang}deg)`; }, delay);
  }
  FACE.register.inert = true; setView('login');
  SWS.forEach(s => s.addEventListener('click', () => {
    if (swBusy) return; swBusy = true;
    setView(current === 'login' ? 'register' : 'login', 150);
    setTimeout(() => { swBusy = false; }, 1900);
  }));

  /* Formas animadas del fondo (capa .bgfx, fija y sin eventos) */
  const bgfx = $('.bgfx');
  if (bgfx) ['s1', 's2', 's3'].forEach(c => { const i = document.createElement('i'); i.className = 'bgshape ' + c; bgfx.appendChild(i); });

  /* ---------- 5. CONTRASEÑAS ---------- */
  $$('[data-toggle]').forEach(btn => btn.addEventListener('click', () => {
    const input = document.getElementById(btn.dataset.toggle);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.setAttribute('aria-pressed', String(show));
    btn.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
    btn.querySelector('use').setAttribute('href', show ? '#i-eye' : '#i-eyeoff');
  }));

  /* Reglas de clave nueva (el servidor es la autoridad; mantener alineado con claves.py) */
  const MIN_PASS = 10;
  const COMUNES = new Set(['admin', 'administrador', 'administrator', 'root', 'user', 'usuario', 'test', 'prueba', 'demo', 'password', 'pass', 'passw0rd',
    'contrasena', 'clave', 'secret', 'secreto', 'login', 'letmein', 'welcome', 'bienvenido', 'qwerty', 'qwertyuiop', 'asdfgh', 'asdfghjkl', 'zxcvbn',
    'zxcvbnm', 'abc', 'abcdef', 'abcdefgh', 'iloveyou', 'teamo', 'tequiero', 'amor', 'dios', 'jesus', 'hola', 'master', 'shadow', 'dragon', 'monkey',
    'superman', 'batman', 'futbol', 'colombia', 'bogota', 'medellin', 'cali', 'millonarios', 'nacional', 'america', 'santafe', 'pagadiario', 'tanishi',
    'prestamo', 'prestamos', 'cobrador', 'cliente']);
  const SECUENCIAS = ['12345', '23456', '34567', '45678', '56789', '09876', 'abcde', 'qwert', 'asdfg', 'zxcvb', 'qazwsx'];
  const plain = t => t.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  function passProblem(v) {
    if (v.length < MIN_PASS) return '⚠ Muy corta';
    if (!(/[A-Za-z]/.test(v) && /\d/.test(v))) return '⚠ Usa letras y números';
    const n = plain(v), base = n.replace(/[^a-z]/g, '');
    if (COMUNES.has(base) || COMUNES.has(n) || [...COMUNES].some(c => c.length >= 4 && base.startsWith(c) && base.length - c.length <= 3)) return '⚠ Demasiado común';
    if (new Set(n).size < 5 || SECUENCIAS.some(s => n.includes(s))) return '⚠ Evita secuencias';
    return '';
  }
  const strength = v => (v.length >= MIN_PASS) + (/[a-z]/.test(v) && /[A-Z]/.test(v)) + /\d/.test(v) + /[^A-Za-z0-9]/.test(v);

  /* ---------- 6. LOGIN: existencia de usuario + avatar ---------- */
  const loginUser = $('#login_user');
  const avatarBox = $('#login_avatar_container');
  const showAvatar = on => avatarBox.classList.toggle('is-visible', on);
  let loginSeq = 0;

  const safeUrl = u => { try { const x = new URL(u, location.origin); return /^https?:$/.test(x.protocol) ? x.href : ''; } catch { return ''; } };

  const lookupUser = debounce(async (val, seq) => {
    try {
      const d = await post(API.loginUser, { valor: val });
      if (seq !== loginSeq) return; // respuesta vieja: se ignora
      if (d.error) { feedback('login-user', NO_DB, 'err'); showAvatar(false); return; }
      const avatar = d.existe ? safeUrl(d.avatar) : '';
      if (d.existe) {
        feedback('login-user', '✓ Usuario encontrado', 'ok');
        if (avatar) { $('#login_avatar_img').src = avatar; showAvatar(true); }
      } else { feedback('login-user', '⚠ El usuario no existe', 'err'); showAvatar(false); }
    } catch { if (seq === loginSeq) feedback('login-user', 'Error de conexión', 'err'); }
  }, 500);

  loginUser.addEventListener('input', () => {
    const val = loginUser.value.trim(), seq = ++loginSeq;
    showAvatar(false);
    if (val.length < 3) { feedback('login-user'); return; }
    feedback('login-user', '…', 'wait');
    lookupUser(val, seq);
  });

  /* Login con campos vacios: se avisa aqui y no se envia al servidor */
  $('#login-view form').addEventListener('submit', e => {
    const u = loginUser.value.trim(), p = $('#login_password').value;
    if (u && p) return;
    e.preventDefault();
    if (!u) feedback('login-user', '⚠ Escribe tu usuario o cédula', 'err');
    if (!p) feedback('login-password', '⚠ Escribe tu contraseña', 'err');
    (u ? $('#login_password') : loginUser).focus();
  });
  $('#login_password').addEventListener('input', () => feedback('login-password'));

  /* ---------- 7. REGISTRO ---------- */
  const reg = { cedula: false, nombre: false, telefono: false, email: false, otp: false, password: false, password2: false, terms: false };
  const submitBtn = $('#btn-registrar');
  const refreshSubmit = () => { submitBtn.disabled = !Object.values(reg).every(Boolean); };
  const mark = (key, ok) => { reg[key] = ok; refreshSubmit(); };

  const el = {
    cedula: $('#signup_cedula'), nombre: $('#signup_nombre'), tel: $('#signup_telefono'), pais: $('#signup_pais'),
    email: $('#signup_email'), otp: $('#signup_otp'), pass: $('#signup_password'), pass2: $('#signup_password2'), terms: $('#confirm-terms'),
  };

  /** Teléfono unificado: código de país + dígitos nacionales sin ceros a la izquierda (misma regla para validar, OTP y registro). */
  const nationalDigits = () => {
    let d = el.tel.value.replace(/\D/g, '').replace(/^0+/, '');
    if (el.pais.value === '57' && d.length === 12 && d.startsWith('57')) d = d.slice(2); // pegaron +57 3xx...
    return d;
  };
  const fullPhone = () => { const n = nationalDigits(); return n ? el.pais.value + n : ''; };

  /* Entradas limpias: solo caracteres válidos (al escribir y al pegar) */
  const limpiar = (input, fn) => input.addEventListener('input', () => { const c = fn(input.value); if (c !== input.value) input.value = c; });
  limpiar(el.cedula, v => v.replace(/\D/g, '').slice(0, 12)); // "7.869.774." -> 7869774
  limpiar(el.nombre, v => v.replace(/[^\p{L}\s'.-]/gu, '').replace(/\s{2,}/g, ' ').replace(/([.'-])\1+/g, '$1').slice(0, 80));
  limpiar(el.tel, v => v.replace(/[^\d ]/g, '').slice(0, 14));
  el.email.maxLength = 120;


  /** Campo con validación local + consulta remota (con anti-respuestas-viejas). */
  function remoteField({ key, input, campo, prepare, local }) {
    let seq = 0;
    const run = debounce(async (value, my) => {
      try {
        const d = await post(API.field, { campo, valor: value });
        if (my !== seq) return;
        if (d.error) { feedback(key, NO_DB, 'err'); mark(key, false); return; }
        feedback(key, d.existe ? '⚠ Ya registrado' : '✓ Disponible', d.existe ? 'err' : 'ok');
        mark(key, !d.existe);
      } catch { if (my === seq) { feedback(key, '⚠ Error de red', 'err'); mark(key, false); } }
    }, 500);
    const check = () => {
      const my = ++seq, value = prepare(), bad = local(value);
      mark(key, false);
      if (bad) { feedback(key, bad.msg, bad.msg ? 'err' : ''); return; }
      feedback(key, '…', 'wait');
      run(value, my);
    };
    input.addEventListener('input', check);
    return check;
  }

  remoteField({ key: 'cedula', input: el.cedula, campo: 'cedula', prepare: () => el.cedula.value.trim(), local: v => v.length < 5 ? { msg: '' } : null });
  remoteField({ key: 'nombre', input: el.nombre, campo: 'nombre', prepare: () => el.nombre.value.trim(),
    local: v => v.length < 5 ? { msg: '' } : (v.split(/\s+/).filter(w => w.length > 1).length < 2 ? { msg: '⚠ Nombre y apellido' } : null) });
  remoteField({
    key: 'email', input: el.email, campo: 'email', prepare: () => el.email.value.trim(),
    local: v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? null : { msg: v ? '⚠ Email inválido' : '' },
  });
  const checkPhone = remoteField({
    key: 'telefono', input: el.tel, campo: 'telefono', prepare: fullPhone,
    local: () => nationalDigits().length < 7 ? { msg: '' } : null,
  });

  el.otp.addEventListener('input', () => mark('otp', el.otp.value.trim().length >= 4));
  el.terms.addEventListener('change', () => mark('terms', el.terms.checked));

  /* Contraseña: medidor, mensaje y confirmación */
  const meter = $('#meter-password'), hint = $('#password-hint');
  const HINTS = ['Usa 10 o más caracteres con letras, números y símbolos.', '⚠ Contraseña débil. Agrega mayúsculas y números.',
    'Aceptable. Agrega números o símbolos para mejorar.', '✓ Contraseña fuerte.', '✓ Contraseña muy fuerte.'];
  const checkConfirm = () => {
    const a = el.pass.value, b = el.pass2.value;
    if (!a || !b) { feedback('password2'); mark('password2', false); return; }
    const ok = a === b;
    feedback('password2', ok ? '✓ Coinciden' : '⚠ No coinciden', ok ? 'ok' : 'err');
    mark('password2', ok);
  };
  const WEAK_HINT = '⚠ Clave débil: combina palabras, números y símbolos.';
  el.pass.addEventListener('input', () => {
    const v = el.pass.value, bad = v ? passProblem(v) : '';
    const s = bad ? Math.min(strength(v), 1) : strength(v); // una clave rechazada nunca se ve "aceptable"
    meter.dataset.s = v ? s : 0;
    hint.textContent = !v ? HINTS[0] : bad ? (v.length < MIN_PASS ? HINTS[0] : WEAK_HINT) : HINTS[s];
    hint.dataset.s = bad ? 'weak' : s >= 3 ? 'strong' : '';
    if (!v) feedback('password');
    else if (bad) feedback('password', bad, 'err');
    else feedback('password', '✓ Válida', 'ok');
    mark('password', v.length > 0 && !bad);
    if (el.pass2.value) checkConfirm();
  });
  el.pass2.addEventListener('input', checkConfirm);

  /* Campos vacios: al salir de un campo obligatorio sin valor se avisa.
     No avisa si el foco pasa a un boton del mismo campo (ojo, enviar codigo, pais). */
  const OBLIG = 'Campo obligatorio';
  [['cedula', el.cedula], ['nombre', el.nombre], ['telefono', el.tel], ['otp', el.otp], ['email', el.email], ['password', el.pass], ['password2', el.pass2]]
    .forEach(([key, input]) => {
      input.addEventListener('blur', e => {
        if (input.value.trim() || input.closest('.fld')?.contains(e.relatedTarget)) return;
        feedback(key, OBLIG, 'err');
      });
      input.addEventListener('input', () => { if ($(`#feedback-${key}`)?.textContent === OBLIG) feedback(key); });
    });

  /* Selector de país (accesible: teclado, Esc y clic fuera) */
  const trigger = $('#countryTrigger'), menu = $('#countryMenu'), telField = $('#tel-field');
  const toggleMenu = open => {
    menu.hidden = !open; trigger.setAttribute('aria-expanded', String(open)); telField.classList.toggle('is-open', open);
  };
  trigger.addEventListener('click', e => { e.stopPropagation(); toggleMenu(menu.hidden); });
  $$('.country__opt', menu).forEach(opt => opt.addEventListener('click', e => {
    e.stopPropagation();
    el.pais.value = opt.dataset.val;
    $('#selectedFlag').textContent = opt.dataset.flag;
    $('#selectedCode').textContent = `+${opt.dataset.val}`;
    toggleMenu(false);
    if (el.tel.value) checkPhone(); // revalida el teléfono con el nuevo código
  }));
  document.addEventListener('click', () => toggleMenu(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { toggleMenu(false); closeModal(); } });

  /* Envío del código por WhatsApp (con cuenta regresiva visible) */
  const otpBtn = $('#btn-enviar-otp');
  const smsBtn = document.createElement('button'), smsBox = document.createElement('div'), smsTxt = document.createElement('div'), smsX = document.createElement('button'); let smsT;
smsBox.style.cssText = 'position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:60;padding:16px 18px;border-radius:18px;background:rgba(255,255,255,.9);backdrop-filter:blur(10px);box-shadow:0 8px 26px rgba(0,0,0,.3);font-size:14px;color:#10223f;text-align:center;max-width:78%';
smsBtn.style.cssText = 'display:block;margin:10px auto 0;padding:9px 16px;border:0;border-radius:12px;background:#1d4ed8;color:#fff;font-size:14px';
smsX.style.cssText = 'position:absolute;top:2px;right:8px;border:0;background:none;font-size:20px;color:#10223f';
smsBtn.type = 'button'; smsX.type = 'button'; smsBtn.textContent = 'Enviar por SMS'; smsX.textContent = '×'; smsBtn.disabled = true; smsBtn.style.opacity = '.45'; smsBox.hidden = true;
smsBox.append(smsX, smsTxt, smsBtn); document.body.appendChild(smsBox);
function showSmsBox() {
  clearInterval(smsT); let s = 46; smsBtn.disabled = true; smsBtn.style.opacity = '.45'; smsBox.hidden = false;
  smsTxt.textContent = `¿No te llegó? Podrás pedirlo por SMS en ${s}s`;
  smsT = setInterval(() => { s--; if (s <= 0) { clearInterval(smsT); smsTxt.textContent = '¿No te llegó el código?'; smsBtn.disabled = false; smsBtn.style.opacity = '1'; } else smsTxt.textContent = `¿No te llegó? Podrás pedirlo por SMS en ${s}s`; }, 1000);
}
smsX.addEventListener('click', () => { clearInterval(smsT); smsBox.hidden = true; });
smsBtn.addEventListener('click', () => { smsBox.hidden = true; });

  function cooldown(seconds) {
    let left = seconds;
    otpBtn.disabled = true; otpBtn.textContent = `Reenviar en ${left}s`;
    const id = setInterval(() => {
      left -= 1;
      if (left <= 0) { clearInterval(id); otpBtn.disabled = false; otpBtn.textContent = 'Enviar código'; }
      else otpBtn.textContent = `Reenviar en ${left}s`;
    }, 1000);
  }
  otpBtn.addEventListener('click', async () => {
    const dni = el.cedula.value.trim(), contacto = fullPhone();
    if (!dni || contacto.length < 9) { feedback('otp', 'Falta cédula o teléfono', 'err'); return; }
    if ($('#feedback-telefono')?.dataset.s === 'err' || $('#feedback-cedula')?.dataset.s === 'err') {
      feedback('otp', 'Corrige la cédula y el teléfono antes de pedir el código', 'err'); return;
    }
    otpBtn.disabled = true;
    try {
      const d = await post(API.otp, { dni, canal: 'whatsapp', contacto });
      if (d.success) { feedback('otp', '✓ Código enviado', 'ok'); cooldown(OTP_COOLDOWN); }
      else { feedback('otp', d.error || 'No se pudo enviar el código', 'err'); otpBtn.disabled = false; if (/WhatsApp/i.test(d.error || '')) showSmsBox(); }
    } catch { feedback('otp', 'Error de red', 'err'); otpBtn.disabled = false; }
  });

  smsBtn.addEventListener("click", async () => { const dni = el.cedula.value.trim(), contacto = fullPhone(); if (!dni || contacto.length < 9) { feedback("otp", "Falta cédula o teléfono", "err"); return; } smsBtn.disabled = true; try { const d = await post(API.otp, { dni, canal: "sms", contacto }); if (d.success) feedback("otp", "✓ Código enviado por SMS", "ok"); else feedback("otp", d.error || "No se pudo enviar el SMS", "err"); } catch { feedback("otp", "Error de red", "err"); } smsBtn.disabled = false; });
  /* Envío del registro */
  $('#form-signup').addEventListener('submit', async e => {
    e.preventDefault();
    submitBtn.disabled = true;
    try {
      const d = await post(API.register, {
        dni: el.cedula.value.trim(), nombre: el.nombre.value.trim(), telefono: fullPhone(), email: el.email.value.trim(),
        password: el.pass.value, password2: el.pass2.value, codigo_otp: el.otp.value.trim(),
      }, 15000);
      if (d.success) { toast('Registro exitoso. Ya puedes iniciar sesión.', 'ok'); setView('login'); }
      else { feedback('otp', d.error || 'No se pudo registrar', 'err'); toast(d.error || 'No se pudo registrar', 'err'); refreshSubmit(); }
    } catch { feedback('otp', 'Error de red', 'err'); toast('Error de conexión con el servidor', 'err'); refreshSubmit(); }
  });

  /* ---------- 8. RECUPERAR CONTRASEÑA ---------- */
  const modal = $('#forgotModal'), recoverInput = $('#recover_input'), sendBtn = $('#btn-send-recover');
  let lastFocus = null;
  function openModal() { lastFocus = document.activeElement; modal.hidden = false; recoverInput.focus(); }
  function closeModal() { if (modal.hidden) return; modal.hidden = true; lastFocus?.focus(); }
  $('#btn-forgot-pwd').addEventListener('click', openModal);
  $('#btn-cancel-recover').addEventListener('click', closeModal);
  modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });

  sendBtn.addEventListener('click', async () => {
    const dato = recoverInput.value.trim();
    if (!dato) { toast('Ingresa tu correo o cédula.', 'err'); recoverInput.focus(); return; }
    const label = sendBtn.textContent;
    sendBtn.textContent = 'Enviando…'; sendBtn.disabled = true;
    try {
      const d = await post(API.recover, { dato });
      if (d.success) { toast(`${d.message} Revisa tu bandeja de entrada o Spam.`, 'ok', 6000); recoverInput.value = ''; closeModal(); }
      else toast(d.message || 'No se pudo enviar el enlace.', 'err');
    } catch { toast('Error de conexión con el servidor.', 'err'); }
    finally { sendBtn.textContent = label; sendBtn.disabled = false; }
  });
})();

/* Íconos Diseño (🎨) y Color (🔮) + clima mini del registro */
(() => {
  const root = document.documentElement, $$ = s => [...document.querySelectorAll(s)], $ = id => document.getElementById(id);
  const get = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } }, set = (k, v) => { try { localStorage.setItem(k, v); } catch { /* privado */ } };
  root.dataset.hue = get('auth.hue', '0'); root.dataset.card = get('auth.card', '0');
  const cyc = (k, a, n) => { const v = (+root.dataset[a] + 1) % n; root.dataset[a] = v; set(k, v); };
  $$('#mfl [data-act="bg"],#mfr [data-act="bg"]').forEach(b => b.addEventListener('click', () => cyc('auth.hue', 'hue', 4)));
  $$('#mfl [data-act="layout"],#mfr [data-act="layout"]').forEach(b => b.addEventListener('click', () => cyc('auth.card', 'card', 4)));
  const t = $('wx-temp'), ic = $('wx-icon'), mt = $('wxm-temp'), mi = $('wxm-icon');
  const cp = () => { mt.textContent = t.textContent; mi.setAttribute('href', ic.getAttribute('href')); };
  new MutationObserver(cp).observe(t, { childList: true, characterData: true, subtree: true });
  new MutationObserver(cp).observe(ic, { attributes: true }); cp();
})();

/* Juegos de diseño: cabezal + base + fondo según data-card */
(() => {
  const root = document.documentElement;
  const N = 4;
  const cab = document.querySelector('img.ly.cab'), bas = document.querySelector('img.ly.bas');
  if (!cab || !bas) return;
  const dir = cab.getAttribute('src').replace(/[^/]*$/, '');
  const nm = (b, i) => i ? `${b}_${i + 1}.png` : `${b}.png`;
  const pick = (f, d) => new Promise(r => { const m = new Image(); m.onload = () => r(f); m.onerror = () => r(d); m.src = dir + f; });
  let tk = 0;
  const apply = async () => {
    const t = ++tk, i = (+root.dataset.card || 0) % N;
    const [c, b, f] = await Promise.all([
      pick(nm('cabezal', i), 'cabezal.png'),
      pick(nm('base', i), 'base.png'),
      pick(nm('fondo', i), 'fondo.png')
    ]);
    if (t !== tk) return;
    cab.src = dir + c; bas.src = dir + b;
    root.style.setProperty('--fondo', `url(${dir}${f})`);
  };
  new MutationObserver(apply).observe(root, { attributes: true, attributeFilter: ['data-card'] });
  apply();
})();
