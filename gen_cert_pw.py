import datetime, ipaddress, os
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

d = os.path.expanduser('~/pagadiario_web/ssl_pw')
k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
t = datetime.datetime.now(datetime.timezone.utc)
san = x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))])
c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key())
     .serial_number(x509.random_serial_number()).not_valid_before(t)
     .not_valid_after(t + datetime.timedelta(days=365)).add_extension(san, critical=False)
     .sign(k, hashes.SHA256()))
open(d + '/cert.pem', 'wb').write(c.public_bytes(serialization.Encoding.PEM))
open(d + '/key.pem', 'wb').write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
os.chmod(d + '/key.pem', 0o600)
print('cert listo')
