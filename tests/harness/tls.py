"""Ephemeral TLS material for each harness run."""
# ruff: noqa: D101

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

REPLAY_ORIGIN = "replay-origin"


@dataclass(frozen=True)
class TLSMaterial:
    ca_certificate: Path
    alternate_ca_certificate: Path
    server_certificate: Path
    server_private_key: Path


def create_tls_material(directory: Path) -> TLSMaterial:
    """Write a trusted origin certificate and an intentionally unrelated CA."""
    directory.mkdir(parents=True, exist_ok=True)
    trusted_key, trusted_cert = _ca("failure-harness trusted")
    _, alternate_cert = _ca("failure-harness alternate")
    server_key, server_cert = _server_certificate(trusted_key, trusted_cert)
    paths = TLSMaterial(
        *(
            directory / name
            for name in ("trusted-ca.pem", "alternate-ca.pem", "server-cert.pem", "server-key.pem")
        )
    )
    paths.ca_certificate.write_bytes(trusted_cert.public_bytes(serialization.Encoding.PEM))
    paths.alternate_ca_certificate.write_bytes(
        alternate_cert.public_bytes(serialization.Encoding.PEM)
    )
    paths.server_certificate.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    paths.server_private_key.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return paths


def _ca(name: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    certificate = (
        x509
        .CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def _server_certificate(
    ca_key: rsa.RSAPrivateKey, ca_cert: x509.Certificate
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    certificate = (
        x509
        .CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, REPLAY_ORIGIN)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(REPLAY_ORIGIN)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    return key, certificate
