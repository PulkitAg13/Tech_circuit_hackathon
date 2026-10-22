"""C2PA Outbound Asset Signing (`c2pa.outbound`).

Upstream `contentauth/c2pa-python` v0.38+ lifecycle notes:
- `c2pa.Builder` is a single-sign `ManagedResource` whose native Rust FFI handle
  closes immediately after `.sign()` or `.sign_file()`.
- Always instantiate a fresh `c2pa.Builder(manifest_def, context=ctx)` inside a
  `with` block for each signing operation, paired with `c2pa.Signer.from_callback(...)`.
"""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any


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


def sign_approved_asset(
    *,
    source_path: str | Path,
    output_path: str | Path,
    mime_type: str,
    manifest_def: dict[str, Any],
    sign_callback: Callable[[bytes], bytes],
    cert_chain_pem: str | bytes,
    tsa_url: str | None = None,
    c2pa_module: Any = None,
) -> bytes:
    """Sign an asset with a single-use `c2pa.Builder` and `c2pa.Context` (v0.38+ API)."""
    if c2pa_module is None:
        import c2pa as c2pa_mod  # type: ignore[import-not-found]

        c2pa_module = c2pa_mod

    src = Path(source_path)
    dst = Path(output_path)
    alg = c2pa_module.C2paSigningAlg.ES256

    with c2pa_module.Context() as ctx:
        with c2pa_module.Signer.from_callback(
            callback=sign_callback,
            alg=alg,
            certs=cert_chain_pem,
            tsa_url=tsa_url,
        ) as signer:
            # Fresh single-use Builder per signing call (closes Rust FFI handle on exit)
            with c2pa_module.Builder(manifest_def, context=ctx) as builder:
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
