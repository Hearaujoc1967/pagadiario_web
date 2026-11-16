// ===================================================================
//  Tanishi Finance — Script de landing pública
//  (versión para Flask: redirige al login, no usa API interna)
// ===================================================================

document.getElementById('year') && (document.getElementById('year').textContent = new Date().getFullYear());

// -------------------------------------------------------------------
//  Abrir login/registro
// -------------------------------------------------------------------
function irALogin() {
  window.location.href = '/login';
}
function irARegistro() {
  window.location.href = '/login#registro';
}

// Sobrescribir abrirSolicitud para que mande al login
function abrirSolicitud(tipo) {
  window.location.href = '/login';
}

// -------------------------------------------------------------------
//  Acordeón FAQs
// -------------------------------------------------------------------
document.querySelectorAll('.faq-q').forEach(q => q.addEventListener('click', () => {
  const item = q.parentElement;
  item.classList.toggle('open');
  const icono = q.querySelector('i');
  if (icono) {
    icono.className = item.classList.contains('open') ? 'fas fa-minus' : 'fas fa-plus';
  }
}));

// -------------------------------------------------------------------
//  Navegación móvil
// -------------------------------------------------------------------
function alternarNavMovil() {
  const x = document.getElementById('mobileNav');
  if (x) x.style.display = x.style.display === 'none' ? 'block' : 'none';
}
function cerrarNavMovil() {
  const x = document.getElementById('mobileNav');
  if (x) x.style.display = 'none';
}

// -------------------------------------------------------------------
//  Calificación del cliente (solo visual)
// -------------------------------------------------------------------
(function() {
  const estrellas = document.querySelectorAll('.rating-stars button');
  const nota = document.getElementById('ratingNote');
  if (!estrellas.length || !nota) return;
  estrellas.forEach(star => {
    star.addEventListener('click', function() {
      const valor = Number(this.dataset.rating);
      estrellas.forEach(s => s.classList.toggle('active', Number(s.dataset.rating) <= valor));
      nota.textContent = valor === 1
        ? '¡Gracias por su calificación de 1 estrella!'
        : 'Calificación de ' + valor + ' estrellas seleccionada. ¡Gracias por su opinión!';
    });
  });
})();
