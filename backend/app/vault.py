"""
Minimal credential vault.

This is a local-dev stand-in, NOT a production secrets design. It
encrypts credentials at rest with a symmetric key from the
INFRAOS_VAULT_KEY environment variable. For anything beyond local
testing, swap this module for real HashiCorp Vault (or cloud KMS)
integration -- the rest of the codebase only depends on `store()` /
`retrieve()`, so the swap is contained to this file.
"""
from __future__ import annotations

import json
import os
import uuid

from cryptography.fernet import Fernet

_KEY_ENV = "INFRAOS_VAULT_KEY"


def _get_fernet() -> Fernet:
    key = os.environ.get(_KEY_ENV)
    if not key:
        # Dev convenience only: generate and print a key once. In any
        # real deployment INFRAOS_VAULT_KEY must be set externally.
        key = Fernet.generate_key().decode()
        os.environ[_KEY_ENV] = key
        print(f"[vault] no {_KEY_ENV} set -- generated an ephemeral dev key")
    return Fernet(key.encode() if isinstance(key, str) else key)


class CredentialVault:
    def __init__(self):
        self._fernet = _get_fernet()
        self._store: dict[str, bytes] = {}   # credential_ref -> encrypted blob

    def store(self, credential: dict) -> str:
        """Encrypts and stores a credential dict, returns an opaque
        reference to save on the Device record."""
        ref = str(uuid.uuid4())
        blob = self._fernet.encrypt(json.dumps(credential).encode())
        self._store[ref] = blob
        return ref

    def retrieve(self, credential_ref: str) -> dict:
        blob = self._store.get(credential_ref)
        if blob is None:
            raise KeyError(f"No credential stored for ref {credential_ref}")
        return json.loads(self._fernet.decrypt(blob).decode())


vault = CredentialVault()
