"""
CRED - Wallet
Chiavi ECDSA secp256k1, indirizzi crd1..., firma e verifica
"""

import hashlib
import json
import os
import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature


# ─────────────────────────────────────────────
# Generazione indirizzi
# ─────────────────────────────────────────────

def public_key_to_address(public_key_hex: str) -> str:
    """
    Genera un indirizzo CRED dalla chiave pubblica.
    crd1 + primi 38 caratteri del SHA-256 della chiave pubblica.
    """
    pub_bytes = bytes.fromhex(public_key_hex)
    h = hashlib.sha256(pub_bytes).hexdigest()
    return "crd1" + h[:38]


# ─────────────────────────────────────────────
# Wallet
# ─────────────────────────────────────────────

class Wallet:
    def __init__(self, private_key: ec.EllipticCurvePrivateKey = None):
        if private_key:
            self._private_key = private_key
        else:
            self._private_key = ec.generate_private_key(ec.SECP256K1())

        self._public_key = self._private_key.public_key()
        self.public_key_hex = self._serialize_public_key()
        self.address = public_key_to_address(self.public_key_hex)

    def _serialize_public_key(self) -> str:
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.CompressedPoint,
        )
        return pub_bytes.hex()

    def sign(self, data: bytes) -> str:
        """Firma i dati e restituisce la firma in hex."""
        signature = self._private_key.sign(data, ec.ECDSA(hashes.SHA256()))
        return signature.hex()

    def export_private_key(self, password: str = None) -> str:
        """Esporta la chiave privata in PEM (opzionalmente cifrata)."""
        encryption = (
            serialization.BestAvailableEncryption(password.encode())
            if password
            else serialization.NoEncryption()
        )
        pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
        return pem.decode()

    def save(self, filepath: str, password: str = None) -> None:
        """Salva il wallet su file."""
        data = {
            "address": self.address,
            "public_key": self.public_key_hex,
            "private_key_pem": self.export_private_key(password),
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str, password: str = None) -> "Wallet":
        """Carica un wallet da file."""
        with open(filepath) as f:
            data = json.load(f)
        pem = data["private_key_pem"].encode()
        pwd = password.encode() if password else None
        private_key = serialization.load_pem_private_key(pem, password=pwd)
        return cls(private_key=private_key)

    def __repr__(self):
        return f"Wallet(address={self.address})"


# ─────────────────────────────────────────────
# Verifica firma (usata dal validatore)
# ─────────────────────────────────────────────

def verify_signature(public_key_hex: str, data: bytes, signature_hex: str) -> bool:
    """Verifica che la firma corrisponda alla chiave pubblica e ai dati."""
    try:
        pub_bytes = bytes.fromhex(public_key_hex)
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256K1(), pub_bytes
        )
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, Exception):
        return False
