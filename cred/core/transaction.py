"""
CRED - Transazioni
Modello UTXO con firma digitale ECDSA (secp256k1)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature


# ─────────────────────────────────────────────
# UTXO
# ─────────────────────────────────────────────

@dataclass
class TxInput:
    """Riferimento a un output precedente."""
    tx_id: str          # hash della transazione sorgente
    output_index: int   # indice dell'output nella tx sorgente
    signature: str = "" # firma digitale del mittente (hex)
    public_key: str = ""# chiave pubblica del mittente (hex)

    def to_dict(self) -> dict:
        return {
            "tx_id": self.tx_id,
            "output_index": self.output_index,
            "signature": self.signature,
            "public_key": self.public_key,
        }


@dataclass
class TxOutput:
    """Destinatario e importo."""
    address: str    # indirizzo del destinatario
    amount: float   # quantità di CRED

    def to_dict(self) -> dict:
        return {"address": self.address, "amount": self.amount}


@dataclass
class Transaction:
    inputs: List[TxInput]
    outputs: List[TxOutput]
    timestamp: float = field(default_factory=time.time)
    tx_id: str = ""

    def __post_init__(self):
        if not self.tx_id:
            self.tx_id = self.compute_id()

    def compute_id(self) -> str:
        """Hash SHA-256 doppio del contenuto della transazione."""
        raw = json.dumps({
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
        }, sort_keys=True)
        first = hashlib.sha256(raw.encode()).digest()
        return hashlib.sha256(first).hexdigest()

    def signing_data(self) -> bytes:
        """Dati da firmare: inputs (senza firma) + outputs + timestamp."""
        raw = json.dumps({
            "inputs": [{"tx_id": i.tx_id, "output_index": i.output_index} for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
        }, sort_keys=True)
        return raw.encode()

    def to_dict(self) -> dict:
        return {
            "tx_id": self.tx_id,
            "timestamp": self.timestamp,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        inputs = [TxInput(**i) for i in d["inputs"]]
        outputs = [TxOutput(**o) for o in d["outputs"]]
        tx = cls(inputs=inputs, outputs=outputs, timestamp=d["timestamp"])
        tx.tx_id = d["tx_id"]
        return tx

    def is_coinbase(self) -> bool:
        """Una coinbase non ha inputs reali — è la ricompensa del miner."""
        return len(self.inputs) == 1 and self.inputs[0].tx_id == "0" * 64


# ─────────────────────────────────────────────
# Merkle Tree
# ─────────────────────────────────────────────

def compute_merkle_root(tx_ids: List[str]) -> str:
    """Calcola la Merkle root da una lista di tx_id."""
    if not tx_ids:
        return "0" * 64
    if len(tx_ids) == 1:
        return tx_ids[0]

    layer = tx_ids[:]
    while len(layer) > 1:
        if len(layer) % 2 != 0:
            layer.append(layer[-1])  # duplica l'ultimo se dispari
        next_layer = []
        for i in range(0, len(layer), 2):
            combined = layer[i] + layer[i + 1]
            h = hashlib.sha256(combined.encode()).hexdigest()
            next_layer.append(h)
        layer = next_layer
    return layer[0]


# ─────────────────────────────────────────────
# Coinbase (ricompensa miner)
# ─────────────────────────────────────────────

INITIAL_REWARD = 50.0
HALVING_INTERVAL = 500_000
MIN_REWARD = 1.0

def block_reward(height: int) -> float:
    """Calcola la ricompensa per il blocco all'altezza data."""
    halvings = height // HALVING_INTERVAL
    reward = INITIAL_REWARD / (2 ** halvings)
    return max(reward, MIN_REWARD)

def create_coinbase(miner_address: str, height: int, n_transactions: int = 0) -> Transaction:
    """
    Crea la transazione coinbase per il miner.
    Reward base + reward dinamico per transazione (dall'emissione, non dall'utente).
    """
    base = block_reward(height)
    dynamic = n_transactions * 0.001  # 0.001 CRED per tx inclusa
    total = base + dynamic

    coinbase_input = TxInput(
        tx_id="0" * 64,
        output_index=0,
        signature="coinbase",
        public_key="coinbase",
    )
    coinbase_output = TxOutput(address=miner_address, amount=total)
    return Transaction(inputs=[coinbase_input], outputs=[coinbase_output])
