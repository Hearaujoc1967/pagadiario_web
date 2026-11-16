/* escena3d.js v2 · Three.js (tarjeta de vidrio) + copias curvas de los formularios reales (#mfl/#mfr).
   auth.js manda: setView() escribe rotateY en #drum (oculto) y aquí se lee como señal. */
(() => {
  'use strict';
  if (!window.THREE) return;
  const root = document.documentElement, $ = id => document.getElementById(id);
  const drum = $('drum'), cab = document.querySelector('.ly.cab'), bas = document.querySelector('.ly.bas');
  if (!drum || !$('mfl') || !$('mfr') || !cab || !bas) return;
  const mk = id => { const e = document.createElement('div'); e.id = id; return e; };
  const sw = mk('scenew'), cont = mk('canvas-container'), wrap = mk('cardwrap'), spin = mk('cardspin');
  wrap.appendChild(spin); sw.append(cont, wrap); cab.before(sw);

  const R = 3.2, ARC = 1.42, ARCD = ARC * 180 / Math.PI, HG = 7.3, CY = 1.22, CAM = 10, FOV = 45, N = 16;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, innerWidth / innerHeight, .1, 100); camera.position.set(0, 1.2, CAM);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); cont.appendChild(renderer.domElement);
  scene.add(new THREE.AmbientLight(0xffffff, .5));
  const dl = new THREE.DirectionalLight(0xffffff, 2); dl.position.set(3, 10, 6); scene.add(dl);
  const geo = new THREE.CylinderGeometry(R, R, HG, 40, 1, true, -ARC / 2, ARC);
  const mat = new THREE.MeshPhysicalMaterial({ color: 0xbfe6ff, transparent: true, opacity: .16, roughness: .05, metalness: .1, side: THREE.DoubleSide, depthWrite: false });
  const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: 0x9fd8ff, transparent: true, opacity: .8 }));
  const card = new THREE.Group();
  [0, Math.PI].forEach(r => { const m = new THREE.Mesh(geo, mat), e = edge.clone(); m.rotation.y = e.rotation.y = r; card.add(m, e); });
  card.position.set(0, CY, -R); scene.add(card);

  /* ---- copias curvas: 16 rebanadas por cara sobre la superficie del cilindro ---- */
  const list = m => [m, ...m.querySelectorAll('*')];
  let active = 0, Rpx = 300, W = 0, Hf = 0, rot = 0, tgt = 0;
  const faces = [{ m: $('mfl'), off: 0 }, { m: $('mfr'), off: 180 }].map((f, n) => ({ ...f, n, els: [], slices: [] }));
  const SKIP = new Set(['id', 'for', 'name', 'data-i']);
  function fix(b) {
    if (b.tagName === 'INPUT') { b.readOnly = true; b.tabIndex = -1; b.setAttribute('inputmode', 'none'); }
    else if (b.tagName === 'BUTTON') { b.type = 'button'; b.tabIndex = -1; }
    else if (b.tagName === 'A') b.tabIndex = -1;
  }
  const hid = me => me.map(a => (a.hidden ? 1 : 0)).join('');
  function build(f) {
    const w = W / N;
    f.slices.forEach(x => x.sl.remove()); f.slices = []; f.els = list(f.m); f.hid = hid(f.els);
    for (let i = 0; i < N; i++) {
      const a = f.off - ARCD / 2 + (i + .5) * ARCD / N, sl = document.createElement('div'), cw = document.createElement('div'), c = f.m.cloneNode(true);
      list(c).forEach((e, k) => { ['id', 'for', 'name'].forEach(x => e.removeAttribute(x)); e.dataset.i = k; });
      c.querySelectorAll('[hidden]').forEach(e => e.remove());
      const ce = []; list(c).forEach(e => { ce[+e.dataset.i] = e; fix(e); });
      sl.className = 'sl'; sl.style.cssText = `left:${-w / 2}px;width:${w}px;transform:rotateY(${a}deg) translateZ(${Rpx.toFixed(1)}px)`;
      cw.className = 'cw'; cw.dataset.f = f.n; cw.style.left = (-i * w) + 'px';
      cw.appendChild(c); sl.appendChild(cw); spin.appendChild(sl); f.slices.push({ sl, ce });
      if (f.n !== active) sl.style.visibility = 'hidden';
    }
    sync(f);
  }
  function sync(f) {
    const cur = list(f.m);
    if (cur.length !== f.els.length || hid(cur) !== f.hid) return build(f);
    const sig = cur.map(a => [...a.attributes].filter(x => !SKIP.has(x.name)).map(x => x.name + '=' + x.value).join('\u0001'));
    const leaf = cur.map(a => a.children.length ? null : a.textContent);
    const fi = cur.indexOf(document.activeElement), fw = fi >= 0 ? cur.indexOf(cur[fi].closest('.fld')) : -1;
    f.slices.forEach(s => s.ce.forEach((b, k) => {
      const a = cur[k];
      if (b._s !== sig[k]) {
        [...b.attributes].forEach(x => { if (x.name !== 'data-i') b.removeAttribute(x.name); });
        [...a.attributes].forEach(x => { if (!SKIP.has(x.name)) b.setAttribute(x.name, x.value); });
        b._s = sig[k]; fix(b);
      }
      if (leaf[k] !== null && b.textContent !== leaf[k]) b.textContent = leaf[k];
      if (a.tagName === 'INPUT') { if (b.value !== a.value) b.value = a.value; b.checked = a.checked; }
      if (k === fi || b.classList.contains('foc')) b.classList.toggle('foc', k === fi);
      if (k === fw || b.classList.contains('foc-w')) b.classList.toggle('foc-w', k === fw);
    }));
  }
  let raf = 0;
  const schedule = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; sync(faces[active]); }); };
  faces.forEach(f => {
    new MutationObserver(schedule).observe(f.m, { subtree: true, attributes: true, childList: true, characterData: true });
    ['input', 'change', 'focusin', 'focusout'].forEach(t => f.m.addEventListener(t, schedule));
  });
  /* tocar una copia = actuar sobre el elemento real (teclado, botones, selector de país...) */
  ['pointerdown', 'mousedown'].forEach(t => spin.addEventListener(t, e => { if (e.target.closest('.cw')) e.preventDefault(); }));
  spin.addEventListener('click', e => {
    const cw = e.target.closest('.cw'); if (!cw) return;
    e.stopPropagation();
    const f = faces[+cw.dataset.f], t = e.target.closest('[data-i]'); if (!t) return;
    const act = t.closest('button,a,label,input'), fl = t.closest('.fld');
    const idx = act ? +act.dataset.i : fl && fl.querySelector('input') ? +fl.querySelector('input').dataset.i : -1;
    const m = f.els[idx]; if (!m || m.disabled) return;
    if (m.tagName === 'INPUT' && m.type !== 'checkbox') m.focus(); else { if (m.type === 'submit' && document.activeElement && document.activeElement.blur) document.activeElement.blur(); m.click(); }
  });

  /* ---- escena y ajuste a la pantalla ---- */
  function apply() {
    card.rotation.y = rot;
    spin.style.transform = `translateZ(${(-Rpx).toFixed(1)}px) rotateY(${rot}rad)`;
    renderer.render(scene, camera);
  }
  function fit() {
    const w = innerWidth, h = innerHeight;
    camera.aspect = w / h; camera.updateProjectionMatrix(); camera.updateMatrixWorld(); renderer.setSize(w, h);
    const ppu = h / (2 * CAM * Math.tan(FOV / 2 * Math.PI / 180)); Rpx = R * ppu;
    const P = (x, y, z) => { const v = new THREE.Vector3(x, y, z).project(camera); return { x: (v.x + 1) / 2 * w, y: (1 - v.y) / 2 * h }; };
    const hx = R * Math.sin(ARC / 2), zE = -R + R * Math.cos(ARC / 2);
    const L = P(-hx, CY, zE).x, Rt = P(hx, CY, zE).x;
    let T = P(0, CY + HG / 2, 0).y, B = P(0, CY - HG / 2, 0).y;
    T = Math.max(T, cab.getBoundingClientRect().height * .66 + 6);
    B = Math.min(B, h - bas.getBoundingClientRect().height * .5 - 6) + 12;
    const H = Math.round(B - T), nW = Math.round(Rpx * ARC);
    wrap.style.cssText = `left:${Math.round(L)}px;top:${Math.round(T)}px;width:${Math.round(Rt - L)}px;height:${H}px;perspective:${Math.round(CAM * ppu)}px;perspective-origin:${Math.round(w / 2 - L)}px ${Math.round(h / 2 - T)}px`;
    root.style.setProperty('--W', nW + 'px'); root.style.setProperty('--Hf', H + 'px');
    if (nW !== W || H !== Hf) { W = nW; Hf = H; faces.forEach(build); }
    apply();
  }
  addEventListener('resize', fit); addEventListener('load', fit); cab.addEventListener('load', fit); bas.addEventListener('load', fit); fit();

  /* ---- ángulo: auth.js escribe rotateY(deg) en #drum; Three lo sigue con suavidad ---- */
  const setVis = (f, on) => f.slices.forEach(x => { x.sl.style.visibility = on ? '' : 'hidden'; });
  new MutationObserver(() => {
    const m = /rotateY\((-?[\d.]+)deg\)/.exec(drum.style.transform); if (!m) return;
    const deg = parseFloat(m[1]); tgt = -deg * Math.PI / 180;
    const a = Math.abs(Math.round(deg / 180)) % 2; if (a === active) return;
    active = a; setVis(faces[a], true); sync(faces[a]);
  }).observe(drum, { attributes: true, attributeFilter: ['style'] });
  (function loop() {
    requestAnimationFrame(loop); const d = tgt - rot; if (!d) return;
    if (Math.abs(d) < 1e-4) { rot = tgt; faces.forEach((f, i) => setVis(f, i === active)); } else rot += d * .08;
    apply();
  })();

  /* ---- sube la escena si el teclado tapa el campo activo ---- */
  const vv = window.visualViewport;
  function lift() {
    const a = document.activeElement, f = faces.find(x => x.m.contains(a)); let ky = 0;
    if (vv && f && a.tagName === 'INPUT') {
      const el = (f.slices[N >> 1] && f.slices[N >> 1].ce[f.els.indexOf(a)]) || a, cy = parseFloat(sw.dataset.ky) || 0;
      const over = (el.getBoundingClientRect().bottom - cy) - (vv.offsetTop + vv.height - 16);
      if (over > 0) ky = -over;
    }
    sw.dataset.ky = ky; sw.style.transform = `translateY(${ky}px)`;
  }
  if (vv) vv.addEventListener('resize', lift);
  document.addEventListener('focusin', () => setTimeout(lift, 350));
  document.addEventListener('focusout', () => setTimeout(lift, 60));
  /* sincroniza el scroll del menú de países en todas las rebanadas */
  spin.addEventListener('scroll', e => {
    const m = e.target; if (!m.classList || !m.classList.contains('country__menu')) return;
    spin.querySelectorAll('.country__menu').forEach(x => { if (x !== m) x.scrollTop = m.scrollTop; });
    const r = document.getElementById('countryMenu'); if (r) r.scrollTop = m.scrollTop;
  }, true);
})();
