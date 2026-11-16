/* Pagadiario Web · restablecer.js
   Página "Crea tu nueva contraseña": mismas reglas en vivo que el registro (medidor, avisos, confirmación),
   ver/ocultar contraseña y fondo animado. El servidor sigue siendo la autoridad (claves.py). */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);

  /* Fondo animado (capa .bgfx, igual que auth.js) */
  const bgfx = $('.bgfx');
  if (bgfx) ['s1', 's2', 's3'].forEach(c => { const i = document.createElement('i'); i.className = 'bgshape ' + c; bgfx.appendChild(i); });

  /* Ver / ocultar contraseña */
  document.querySelectorAll('[data-toggle]').forEach(btn => btn.addEventListener('click', () => {
    const input = document.getElementById(btn.dataset.toggle);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.setAttribute('aria-pressed', String(show));
    btn.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
    btn.querySelector('use').setAttribute('href', show ? '#i-eye' : '#i-eyeoff');
  }));

  const form = $('form.form');
  if (!form) return; // página "Enlace no válido": no hay formulario

  /* ---- Reglas de clave nueva: mantener alineado con auth.js y claves.py ---- */
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

  const pass = $('#password'), pass2 = $('#password2'), btn = $('#btn-guardar');
  const meter = $('#meter-password'), hint = $('#password-hint');
  const HINTS = ['Usa 10 o más caracteres con letras, números y símbolos.', '⚠ Contraseña débil. Agrega mayúsculas y números.',
    'Aceptable. Agrega números o símbolos para mejorar.', '✓ Contraseña fuerte.', '✓ Contraseña muy fuerte.'];
  const WEAK_HINT = '⚠ Clave débil: combina palabras, números y símbolos.';

  function feedback(id, msg = '', state = '') {
    const el = document.getElementById('feedback-' + id);
    if (!el) return;
    el.textContent = msg;
    if (state) el.dataset.s = state; else delete el.dataset.s;
  }

  const ok = { password: false, password2: false };
  const refresh = () => { btn.disabled = !(ok.password && ok.password2); };

  const checkConfirm = () => {
    const a = pass.value, b = pass2.value;
    if (!a || !b) { feedback('password2'); ok.password2 = false; refresh(); return; }
    const igual = a === b;
    feedback('password2', igual ? '✓ Coinciden' : '⚠ No coinciden', igual ? 'ok' : 'err');
    ok.password2 = igual; refresh();
  };

  const checkPass = () => {
    const v = pass.value, bad = v ? passProblem(v) : '';
    const s = bad ? Math.min(strength(v), 1) : strength(v); // una clave rechazada nunca se ve "aceptable"
    meter.dataset.s = v ? s : 0;
    hint.textContent = !v ? HINTS[0] : bad ? (v.length < MIN_PASS ? HINTS[0] : WEAK_HINT) : HINTS[s];
    hint.dataset.s = bad ? 'weak' : s >= 3 ? 'strong' : '';
    if (!v) feedback('password');
    else if (bad) feedback('password', bad, 'err');
    else feedback('password', '✓ Válida', 'ok');
    ok.password = v.length > 0 && !bad;
    refresh();
    if (pass2.value) checkConfirm();
  };

  pass.addEventListener('input', checkPass);
  pass2.addEventListener('input', checkConfirm);
  form.addEventListener('submit', e => { if (btn.disabled) e.preventDefault(); });

  btn.disabled = true; // sin JS el botón queda activo y el servidor valida igual
  if (pass.value) checkPass(); // por si el navegador autocompleta al cargar
})();
