"""Normalización de teléfonos para Pagadiario.
Formato canónico en BD: '57' + 10 dígitos (12 caracteres, sin '+').
"""

def normalizar(t):
    """Devuelve '57' + 10 dígitos. Si no se puede, devuelve ''."""
    if t is None:
        return ''
    s = ''.join(c for c in str(t) if c.isdigit())
    if not s:
        return ''
    # Ya viene con 57 + 10 dígitos
    if len(s) == 12 and s.startswith('57'):
        return s
    # 10 dígitos (celular Colombia)
    if len(s) == 10:
        return '57' + s
    # 11 dígitos empezando por 0 -> quitar el 0
    if len(s) == 11 and s.startswith('0'):
        return '57' + s[1:]
    return s


def para_whatsapp(t):
    """Devuelve '57' + 10 dígitos para el bot WA (sin '+')."""
    return normalizar(t)


def para_sms(t):
    """Devuelve '+57' + 10 dígitos para termux-sms-send / Twilio."""
    n = normalizar(t)
    return '+' + n if n else ''


def para_display(t):
    """Devuelve '57' + 10 dígitos para mostrar en UI."""
    return normalizar(t)
