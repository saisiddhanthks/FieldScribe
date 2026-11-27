"""Phones over HTTPS: the laptop's own certificate authority and the /phone set-up page."""
import os
import tempfile

os.environ.setdefault("FIELDSCRIBE_DATA", tempfile.mkdtemp())

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import ExtensionOID  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import tls  # noqa: E402


def test_certificate_chain_is_valid_for_this_laptop():
    t = tls.ensure()
    chain = open(t["cert"], "rb").read()
    srv = x509.load_pem_x509_certificate(chain)
    ca = x509.load_pem_x509_certificate(tls.ca_pem())
    ca.public_key().verify(srv.signature, srv.tbs_certificate_bytes, ec.ECDSA(srv.signature_hash_algorithm))   # signed by the CA
    san = srv.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
    names = {str(v) for v in san.get_values_for_type(x509.IPAddress)} | set(san.get_values_for_type(x509.DNSName))
    assert {"127.0.0.1", "localhost"} <= names and set(t["ips"]) <= names
    assert (srv.not_valid_after_utc - srv.not_valid_before_utc).days <= 398          # phones refuse longer
    assert tls.ensure()["cert"] == t["cert"]                                          # reused, not regenerated


def test_phone_page_and_ca_are_public_but_key_is_not(monkeypatch):
    monkeypatch.setenv("FIELDSCRIBE_AUTH", "1")
    with TestClient(app) as c:
        assert c.get("/api/incidents").status_code == 401                          # login is on
        r = c.get("/api/tls/ca.crt")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-x509-ca-cert")
        assert x509.load_der_x509_certificate(r.content).subject == x509.load_pem_x509_certificate(tls.ca_pem()).subject
        p = c.get("/phone")
        assert p.status_code == 200 and "Download certificate" in p.text and ":8443" in p.text
        for path in ("/certs/fieldscribe-ca.key", "/../data/certs/fieldscribe-ca.key", "/api/tls/ca.key"):
            assert b"PRIVATE KEY" not in c.get(path).content
