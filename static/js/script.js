document.addEventListener('DOMContentLoaded', () => {
    const cardContainer = document.getElementById('cardContainer');
    const toggleFront = document.getElementById('toggleFront');
    const toggleBack = document.getElementById('toggleBack');

    let currentRotation = 0;
    let isRegisterView = false;

    function flipCard() {
        // Alternar el estado
        isRegisterView = !isRegisterView;
        
        // Gira la tarjeta 180 grados (siempre acumulativo a la derecha)
        currentRotation += 180;
        cardContainer.style.transform = `rotateY(${currentRotation}deg)`;

        // Sincroniza el estado visual de ambos botones (frontal y trasero)
        const state = isRegisterView ? "true" : "false";
        const text = isRegisterView ? "LOG IN" : "SIGN UP";

        toggleFront.setAttribute('aria-checked', state);
        toggleFront.querySelector('.vswitch__label').textContent = text;

        toggleBack.setAttribute('aria-checked', state);
        toggleBack.querySelector('.vswitch__label').textContent = text;
    }

    // Asignar el evento a ambos botones
    if (toggleFront && toggleBack) {
        toggleFront.addEventListener('click', flipCard);
        toggleBack.addEventListener('click', flipCard);
    }
});