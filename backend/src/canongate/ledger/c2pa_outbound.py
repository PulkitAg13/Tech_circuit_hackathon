"""C2PA Outbound Asset Signing (`c2pa.outbound`).

Upstream `contentauth/c2pa-python` v0.38+ lifecycle notes:
- `c2pa.Builder` is a single-sign `ManagedResource` whose native Rust FFI handle
  closes immediately after `.sign()` or `.sign_file()`.
- Always instantiate a fresh `c2pa.Builder(manifest_def, context=ctx)` inside a
  `with` block for each signing operation, paired with `c2pa.Signer.from_callback(...)`.
- Provides `generate_ephemeral_es256_credentials()` using `cryptography.x509` +
  `ec.SECP256R1()` so outbound signing always uses a cryptographically valid
  X.509 v3 certificate chain and ECDSA SHA-256 signature, and writes a signed
  `.c2pa.json` sidecar + asset copy when `c2pa-python` is not installed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from collections.abc import Callable
from contextlib import nullcontext
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


@lru_cache(maxsize=4)
def generate_ephemeral_es256_credentials(
    common_name: str = "CanonGate Governance Authority",
) -> tuple[Callable[[bytes], bytes], bytes, str]:
    """Generate a valid X.509 v3 ECDSA P-256 (`SECP256R1`) certificate and signing callback.

    Returns `(sign_callback, cert_chain_pem_bytes, public_key_pem_str)`.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "CanonGate Governance"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    pub_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    def _sign(data: bytes) -> bytes:
        return private_key.sign(data, ec.ECDSA(hashes.SHA256()))

    return _sign, cert_pem, pub_pem


def build_governance_manifest(
    *,
    submission_id: int,
    canon_id: str,
    canon_hash: str,
    content_hash: str,
    merkle_root: str,
    approved_by: str,
    approved_at: str,
) -> dict[str, Any]:
    """Construct the C2PA manifest definition with a custom CanonGate governance assertion."""
    return {
        "claim_generator_info": [{"name": "CanonGate", "version": "0.1.0"}],
        "title": f"CanonGate Approved Asset #{submission_id}",
        "assertions": [
            {
                "label": "c2pa.actions.v2",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.opened",
                            "parameters": {"ingredientIds": ["parent-asset"]},
                        }
                    ]
                },
            },
            {
                "label": "com.canongate.governance.v1",
                "data": {
                    "submission_id": submission_id,
                    "canon_id": canon_id,
                    "canon_hash": canon_hash,
                    "content_hash": content_hash,
                    "merkle_root": merkle_root,
                    "approved_by": approved_by,
                    "approved_at": approved_at,
                },
            },
        ],
    }


def _as_context_manager(obj: Any) -> Any:
    return obj if hasattr(obj, "__enter__") else nullcontext(obj)


def _is_dummy_pem(cert_chain_pem: str | bytes | None) -> bool:
    if not cert_chain_pem:
        return True
    txt = (
        cert_chain_pem.decode("utf-8", errors="replace")
        if isinstance(cert_chain_pem, bytes)
        else cert_chain_pem
    )
    return "..." in txt or "BEGIN CERTIFICATE" not in txt


def sign_approved_asset(
    *,
    source_path: str | Path,
    output_path: str | Path,
    mime_type: str,
    manifest_def: dict[str, Any],
    sign_callback: Callable[[bytes], bytes] | None = None,
    cert_chain_pem: str | bytes | None = None,
    tsa_url: str | None = None,
    c2pa_module: Any = None,
) -> bytes:
    """Sign an asset with a single-use `c2pa.Builder` and valid X.509 ES256 credentials."""
    src = Path(source_path)
    dst = Path(output_path)

    # Replace missing or placeholder PEM/callback with real X.509 ECDSA P-256 credentials
    if sign_callback is None or _is_dummy_pem(cert_chain_pem):
        real_cb, real_pem, _ = generate_ephemeral_es256_credentials()
        if _is_dummy_pem(cert_chain_pem):
            sign_callback = real_cb
            cert_chain_pem = real_pem
        elif sign_callback is None:
            sign_callback = real_cb

    if c2pa_module is None:
        try:
            import c2pa as c2pa_mod  # type: ignore[import-not-found]

            c2pa_module = c2pa_mod
        except ImportError:
            c2pa_module = None

    if c2pa_module is not None:
        alg = c2pa_module.C2paSigningAlg.ES256
        ctx_obj = c2pa_module.Context() if hasattr(c2pa_module, "Context") else None
        with _as_context_manager(ctx_obj) as ctx:
            signer_obj = c2pa_module.Signer.from_callback(
                callback=sign_callback,
                alg=alg,
                certs=cert_chain_pem,
                tsa_url=tsa_url,
            )
            with _as_context_manager(signer_obj) as signer:
                builder_obj = (
                    c2pa_module.Builder(manifest_def, context=ctx)
                    if ctx is not None
                    else c2pa_module.Builder(manifest_def)
                )
                with _as_context_manager(builder_obj) as builder:
                    ingredient_json = json.dumps(
                        {
                            "title": src.name,
                            "relationship": "parentOf",
                            "label": "parent-asset",
                        }
                    )
                    with open(src, "rb") as ingredient_stream:
                        builder.add_ingredient(ingredient_json, mime_type, ingredient_stream)
                    return builder.sign_file(str(src), str(dst), signer)

    # Cryptographic sidecar fallback when `c2pa-python` native wheel is not installed
    shutil.copyfile(src, dst)
    asset_sha256 = hashlib.sha256(src.read_bytes()).hexdigest()
    canonical_manifest = json.dumps(manifest_def, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    payload_to_sign = f"{asset_sha256}:".encode() + canonical_manifest
    assert sign_callback is not None
    sig_bytes = sign_callback(payload_to_sign)
    pem_str = (
        cert_chain_pem.decode("utf-8", errors="replace")
        if isinstance(cert_chain_pem, bytes)
        else str(cert_chain_pem)
    )
    sidecar = {
        "asset_sha256": asset_sha256,
        "mime_type": mime_type,
        "manifest": manifest_def,
        "signing_alg": "ES256",
        "signature_hex": sig_bytes.hex(),
        "certificate_pem": pem_str,
    }
    sidecar_path = dst.with_suffix(f"{dst.suffix}.c2pa.json")
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return sig_bytes
