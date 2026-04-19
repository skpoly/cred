"""
CRED - Core Block
Struttura del blocco e Proof of Work
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class BlockHeader:
    version: int
    prev_hash: str
    merkle_root: str
    timestamp: float
    difficulty: int
    nonce: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass
class Block:
    header: BlockHeader
    transactions: List[dict]
    height: int
    hash: str = ""

    def compute_hash(self) -> str:
        raw = self.header.serialize() + json.dumps(self.transactions, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def mine(self, difficulty: int) -> None:
        """Proof of Work: trova nonce tale che hash inizi con N zeri."""
        target = "0" * difficulty
        self.header.nonce = 0
        while True:
            self.hash = self.compute_hash()
            if self.hash.startswith(target):
                break
            self.header.nonce += 1

    def is_valid_pow(self) -> bool:
        target = "0" * self.header.difficulty
        return self.compute_hash().startswith(target)

    def to_dict(self) -> dict:
        return {
            "height": self.height,
            "hash": self.hash,
            "header": self.header.to_dict(),
            "transactions": self.transactions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        header = BlockHeader(**d["header"])
        return cls(
            header=header,
            transactions=d["transactions"],
            height=d["height"],
            hash=d["hash"],
        )
