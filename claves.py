"""Reglas de contraseña compartidas (registro, recuperación y cambio de clave).

Solo valida claves NUEVAS: las claves que ya existen siguen funcionando igual.
validar_clave() devuelve None si la clave es aceptable, o un mensaje listo para mostrar al usuario.
"""
import re
import unicodedata

MIN_LARGO = 10

# Palabras muy usadas. Se comparan sin tildes, en minúsculas y quitando números y símbolos
# (así 'Admin2026' y 'admin#1' cuentan como 'admin'). Mantén esta lista alineada con la de auth.js.
_COMUNES = {
    'admin', 'administrador', 'administrator', 'root', 'user', 'usuario', 'test', 'prueba', 'demo',
    'password', 'pass', 'passw0rd', 'contrasena', 'clave', 'secret', 'secreto', 'login', 'letmein', 'welcome',
    'bienvenido', 'qwerty', 'qwertyuiop', 'asdfgh', 'asdfghjkl', 'zxcvbn', 'zxcvbnm', 'abc', 'abcdef', 'abcdefgh',
    'iloveyou', 'teamo', 'tequiero', 'amor', 'dios', 'jesus', 'hola', 'master', 'shadow', 'dragon', 'monkey',
    'superman', 'batman', 'futbol', 'colombia', 'bogota', 'medellin', 'cali', 'millonarios', 'nacional', 'america',
    'santafe', 'pagadiario', 'tanishi', 'prestamo', 'prestamos', 'cobrador', 'cliente',
}
_SECUENCIAS = ('12345', '23456', '34567', '45678', '56789', '09876', 'abcde', 'qwert', 'asdfg', 'zxcvb', 'qazwsx')


def _plano(texto):
    """Minúsculas y sin tildes (ñ -> n)."""
    return unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower()


def validar_clave(clave, contexto=()):
    """contexto: datos de la persona (cédula, nombre, correo, teléfono) que la clave no debe contener."""
    if len(clave) < MIN_LARGO:
        return f'La contraseña debe tener al menos {MIN_LARGO} caracteres.'
    if not (re.search(r'[A-Za-z]', clave) and re.search(r'\d', clave)):
        return 'Usa letras y números en la contraseña.'
    n = _plano(clave)
    base = re.sub(r'[^a-z]', '', n)
    if base in _COMUNES or n in _COMUNES or any(len(c) >= 4 and base.startswith(c) and len(base) - len(c) <= 3 for c in _COMUNES):
        return 'Esa contraseña es demasiado común. Elige otra.'
    if len(set(n)) < 5 or any(s in n for s in _SECUENCIAS):
        return 'Evita secuencias o caracteres repetidos (12345, qwerty…).'
    for dato in contexto:
        for parte in re.split(r'[\s@.\-_]+', _plano(dato)):
            if len(parte) >= 4 and parte in n:
                return 'La contraseña no debe contener tus datos personales.'
    return None
