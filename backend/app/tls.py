"""
Secure connection for phones and tablets on the ambulance Wi-Fi.

Phones only allow the microphone and "Add to Home screen" on HTTPS pages. FieldScribe makes its own small
certificate authority on this laptop (kept in the data folder, never leaves it), issues a certificate for the
laptop's current Wi-Fi addresses, and serves HTTPS on port 8443. Each phone trusts the authority once, from
the /phone setup page. The authority's private key is never served.
"""
from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from . import db

DIR = db.DATA_DIR / "certs"
CA_CRT, CA_KEY = DIR / "fieldscribe-ca.crt", DIR / "fieldscribe-ca.key"
SRV_CRT, SRV_KEY = DIR / "server.crt", DIR / "server.key"
HTTPS_PORT = 8443


def lan_ips() -> list[str]:
    ips: set[str] = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))          # picks the Wi-Fi interface; nothing is sent
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        ips |= {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith(("127.", "169.254.")))


def _write_key(path: Path, key) -> None:
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _ca():
    DIR.mkdir(parents=True, exist_ok=True)
    if CA_CRT.exists() and CA_KEY.exists():
        return (x509.load_pem_x509_certificate(CA_CRT.read_bytes()),
                serialization.load_pem_private_key(CA_KEY.read_bytes(), None))
    key = ec.generate_private_key(ec.SECP256R1())
    host = socket.gethostname()[:40]
    name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FieldScribe"),
                      x509.NameAttribute(NameOID.COMMON_NAME, f"FieldScribe device CA ({host})")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    _write_key(CA_KEY, key)
    CA_CRT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert, key


def _server_names(cert) -> set[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        return {str(v) for v in san.get_values_for_type(x509.IPAddress)} | set(san.get_values_for_type(x509.DNSName))
    except Exception:
        return set()


def ensure() -> dict:
    """Make sure a server certificate exists for the current Wi-Fi addresses. Returns file paths and URLs."""
    ca, ca_key = _ca()
    ips = lan_ips()
    want = set(ips) | {"127.0.0.1", "localhost"}
    fresh = SRV_CRT.exists() and SRV_KEY.exists()
    if fresh:
        cur = x509.load_pem_x509_certificate(SRV_CRT.read_bytes())
        end = getattr(cur, "not_valid_after_utc", None) or cur.not_valid_after.replace(tzinfo=timezone.utc)
        fresh = want <= _server_names(cur) and end > datetime.now(timezone.utc) + timedelta(days=30)
    if not fresh:
        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        alt = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in sorted(want - {"localhost"})]
        host = socket.gethostname()
        if host:
            alt.append(x509.DNSName(host.lower()))
        cert = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FieldScribe on this laptop")]))
                .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=397))   # phones reject > 398 days
                .add_extension(x509.SubjectAlternativeName(alt), critical=False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                .sign(ca_key, hashes.SHA256()))
        _write_key(SRV_KEY, key)
        SRV_CRT.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + CA_CRT.read_bytes())   # full chain
    return {"cert": str(SRV_CRT), "key": str(SRV_KEY), "ips": ips,
            "https_urls": [f"https://{i}:{HTTPS_PORT}" for i in ips], "fingerprint": fingerprint()}


def ca_pem() -> bytes:
    _ca()
    return CA_CRT.read_bytes()


def ca_der() -> bytes:
    ca, _ = _ca()
    return ca.public_bytes(serialization.Encoding.DER)


def fingerprint() -> str:
    ca, _ = _ca()
    h = ca.fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(h[i:i + 2] for i in range(0, 16, 2))   # first 8 bytes: enough to compare by eye


def qr_svg(text: str) -> str:
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    return img.to_string(encoding="unicode")
