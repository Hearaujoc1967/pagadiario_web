/* ====================================================== *
 * PROYECTO COBROS - CONTROL INTERACTIVO Y VALIDACIÓN AJAX*
 * ====================================================== */
$(document).ready(function(){
  // --- ANIMACIÓN DE PANELES (SlideBox) ---
  $('#goRight').on('click', function(){
    $('#slideBox').animate({ 'marginLeft' : '0' });
    $('.topLayer').animate({ 'marginLeft' : '100%' });
  });

  $('#goLeft').on('click', function(){
    if (window.innerWidth > 769){
      $('#slideBox').animate({ 'marginLeft' : '50%' });
    } else {
      $('#slideBox').animate({ 'marginLeft' : '20%' });
    }
    $('.topLayer').animate({ 'marginLeft': '0' });
  });

  // --- VISIBILIDAD DE CONTRASEÑAS ---
  $('#show-password-login').on('change', function() {
    $('#login_password').attr('type', $(this).is(':checked') ? 'text' : 'password');
  });

  $('#show-password-signup').on('change', function() {
    let type = $(this).is(':checked') ? 'text' : 'password';
    $('#signup_password').attr('type', type);
    $('#signup_password2').attr('type', type);
  });
});

/* ====================================================== *
 * LÓGICA DE PAPER.JS (Fondo Animado)                    *
 * ====================================================== */
paper.install(window);
paper.setup(document.getElementById("canvas"));
var canvasWidth, canvasHeight, canvasMiddleX, canvasMiddleY;
var shapeGroup = new Group();
var positionArray = [];

function getCanvasBounds() {
  canvasWidth = view.size.width;
  canvasHeight = view.size.height;
  canvasMiddleX = canvasWidth / 2;
  canvasMiddleY = canvasHeight / 2;
  positionArray = [
    { x: canvasMiddleX + 200, y: 150 }, { x: 200, y: canvasMiddleY },
    { x: canvasWidth - 130, y: canvasHeight - 75 }, { x: 0, y: canvasMiddleY + 100 },
    { x: canvasMiddleX / 2 + 100, y: 100 }, { x: canvasMiddleX + 80, y: canvasHeight - 50 },
    { x: canvasWidth + 60, y: canvasMiddleY - 50 }, { x: canvasMiddleX + 100, y: canvasMiddleY + 100 }
  ];
}

function initializeShapes() {
  getCanvasBounds();
  var shapePathData = [
    'M231,352l445-156L600,0L452,54L331,3L0,48L231,352', 
    'M0,0l64,219L29,343l535,30L478,37l-133,4L0,0z', 
    'M0,65l16,138l96,107l270-2L470,0L337,4L0,65z',
    'M333,0L0,94l64,219L29,437l570-151l-196-42L333,0',
    'M331.9,3.6l-331,45l231,304l445-156l-76-196l-148,54L331.9,3.6z',
    'M389,352l92-113l195-43l0,0l0,0L445,48l-80,1L122.7,0L0,275.2L162,297L389,352',
    'M 50 100 L 300 150 L 550 50 L 750 300 L 500 250 L 300 450 L 50 100',
    'M 700 350 L 500 350 L 700 500 L 400 400 L 200 450 L 250 350 L 100 300 L 150 50 L 350 100 L 250 150 L 450 150 L 400 50 L 550 150 L 350 250 L 650 150 L 650 50 L 700 150 L 600 250 L 750 250 L 650 300 L 700 350 '
  ];
  for (var i = 0; i < shapePathData.length; i++) {
    var headerShape = new Path({
      strokeColor: 'rgba(255, 255, 255, 0.5)',
      strokeWidth: 2,
      parent: shapeGroup,
    });
    headerShape.pathData = shapePathData[i];
    headerShape.scale(2);
    headerShape.position = positionArray[i];
  }
}
initializeShapes();
view.onFrame = function(event) {
  if (event.count % 4 === 0) {
    for (var i = 0; i < shapeGroup.children.length; i++) {
      shapeGroup.children[i].rotate(i % 2 === 0 ? -0.1 : 0.1);
    }
  }
};

/* ====================================================== *
 * VALIDACIONES EN TIEMPO REAL Y CONTROL DE BOTÓN         *
 * ====================================================== */
$(document).ready(function(){
  // Mapeo de IDs REALES de tu auth.html
  const cedulaF = document.getElementById('signup_cedula');
  const nombreF = document.getElementById('signup_nombre');
  const telefonoF = document.getElementById('signup_telefono');
  const emailF = document.getElementById('signup_email');
  const p1 = document.getElementById('signup_password');
  const p2 = document.getElementById('signup_password2');
  const terms = document.getElementById('confirm-terms');
  const btn = document.getElementById('signUp');

  // Variables de estado para validación
  let cedulaOk = false;
  let emailOk = false;
  let passOk = false;
  let matchOk = false;

  // Función para habilitar/deshabilitar el botón
  function validarEstadoBoton() {
    const termsOk = terms ? terms.checked : false;
    if (cedulaOk && emailOk && passOk && matchOk && termsOk) {
      $(btn).prop('disabled', false).css({'opacity': '1', 'cursor': 'pointer'});
    } else {
      $(btn).prop('disabled', true).css({'opacity': '0.5', 'cursor': 'not-allowed'});
    }
  }

  // Función para crear/actualizar los mensajes debajo de los inputs
  function emitirAlerta(input, id, msj, error) {
    if (!input) return;
    let a = document.getElementById(id);
    if (!a) {
      a = document.createElement('div');
      a.id = id;
      a.style = "font-size: 0.75em; margin-top: 5px; font-weight: bold; display: block;";
      input.parentNode.appendChild(a);
    }
    a.innerHTML = msj;
    a.style.color = error ? "#ff4d4d" : "#2ecc71";
    // Actualizamos los estados según el tipo de campo
    if (id === 'msg-cedula') cedulaOk = !error;
    if (id === 'msg-email') emailOk = !error;
    if (id === 'msg-p1') passOk = !error;
    if (id === 'msg-p2') matchOk = !error;
    
    validarEstadoBoton();
  }

  // --- VALIDACIÓN DE CÉDULA (Contra la BD) ---
  if (cedulaF) {
    $(cedulaF).on('input', function() {
      let val = this.value.trim();
      if (val.length < 6) {
        emitirAlerta(cedulaF, 'msg-cedula', '❌ Mínimo 6 dígitos', true);
      } else {
        // AJAX para validar si la cédula ya existe en tcliente
        $.ajax({
          url: '/validar_cedula', // NOTA: Esta ruta debe existir en tu app.py
          data: { 'cedula': val },
          success: (d) => {
            // Asumimos que d.is_taken devuelve true o false desde Flask
            emitirAlerta(cedulaF, 'msg-cedula', d.is_taken ? '❌ Cédula ya registrada' : '✅ Cédula disponible', d.is_taken);
          },
          error: () => {
            // Si la ruta no existe, al menos validamos que no esté vacío
            emitirAlerta(cedulaF, 'msg-cedula', '✅ Cédula válida', false);
          }
        });
      }
    });
  }

  // --- VALIDACIÓN DE EMAIL (Contra la BD) ---
  if (emailF) {
    $(emailF).on('input', function() {
      let val = this.value.trim();
      const emailReg = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailReg.test(val)) {
        emitirAlerta(emailF, 'msg-email', '❌ Email inválido', true);
      } else {
        $.ajax({
          url: '/validar_email', // NOTA: Esta ruta debe existir en tu app.py
          data: { 'email': val },
          success: (d) => {
            emitirAlerta(emailF, 'msg-email', d.is_taken ? '❌ Email ya registrado' : '✅ Email disponible', d.is_taken);
          },
          error: () => {
            emitirAlerta(emailF, 'msg-email', '✅ Email válido', false);
          }
        });
      }
    });
  }

  // --- VALIDACIÓN DE CONTRASEÑAS ---
  const vc = () => {
    if (!p1 || !p2) return;
    if (p1.value.length < 6) {
      emitirAlerta(p1, 'msg-p1', '⚠️ Mínimo 6 caracteres', true);
    } else {
      emitirAlerta(p1, 'msg-p1', '✅ Longitud segura', false);
    }
    
    if (p2.value.length > 0) {
      if (p1.value !== p2.value) {
        emitirAlerta(p2, 'msg-p2', '❌ Las contraseñas no coinciden', true);
      } else {
        emitirAlerta(p2, 'msg-p2', '✅ Coinciden', false);
      }
    }
  };

  if (p1) $(p1).on('input', vc);
  if (p2) $(p2).on('input', vc);
  if (terms) $(terms).on('change', validarEstadoBoton);

  // Validar al cargar por si el navegador autocompletó
  validarEstadoBoton();
});