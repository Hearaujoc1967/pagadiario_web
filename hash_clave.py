import os, hashlib, hmac
from werkzeug.security import generate_password_hash, check_password_hash

def v2_activo():
    return os.environ.get('PAGADIARIO_HASH_V2', '0') == '1'

def sha1(texto):
    return hashlib.sha1(texto.encode('utf-8')).hexdigest()

def hash_fuerte(texto):
    return generate_password_hash(texto, method='pbkdf2:sha256:600000')

def verificar(texto, clave, clave_v2=None):
    """Devuelve (ok, migrar). Prefiere clave_v2; si no hay, compara SHA-1."""
    if clave_v2:
        try:
            return check_password_hash(clave_v2, texto), False
        except Exception:
            return False, False
    ok = hmac.compare_digest(sha1(texto), clave or '')
    return ok, (ok and v2_activo())
