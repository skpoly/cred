"""
CRED - Blockchain
Chain principale, UTXO set, validazione blocchi e transazioni
"""

import json
import os
import time
import hashlib
from typing import Dict, List, Optional, Tuple

from core.block import Block, BlockHeader
from core.transaction import (
    Transaction, TxInput, TxOutput,
    compute_merkle_root, create_coinbase, block_reward
)
from wallet.wallet import verify_signature, public_key_to_address


# ─────────────────────────────────────────────
# Parametri protocollo
# ─────────────────────────────────────────────

DIFFICULTY_ADJUSTMENT_INTERVAL = 10   # ogni N blocchi
TARGET_BLOCK_TIME = 150                # 2.5 minuti in secondi
INITIAL_DIFFICULTY = 3                 # zeri iniziali richiesti


# ─────────────────────────────────────────────
# UTXO Set
# ─────────────────────────────────────────────

class UTXOSet:
    """
    Tiene traccia degli output non spesi.
    Chiave: (tx_id, output_index) → TxOutput
    """
    def __init__(self):
        self._utxos: Dict[Tuple[str, int], TxOutput] = {}

    def add(self, tx_id: str, index: int, output: TxOutput) -> None:
        self._utxos[(tx_id, index)] = output

    def spend(self, tx_id: str, index: int) -> Optional[TxOutput]:
        return self._utxos.pop((tx_id, index), None)

    def get(self, tx_id: str, index: int) -> Optional[TxOutput]:
        return self._utxos.get((tx_id, index))

    def balance(self, address: str) -> float:
        return sum(
            utxo.amount
            for utxo in self._utxos.values()
            if utxo.address == address
        )

    def utxos_for(self, address: str) -> List[Tuple[Tuple[str, int], TxOutput]]:
        return [
            (key, utxo)
            for key, utxo in self._utxos.items()
            if utxo.address == address
        ]

    def to_dict(self) -> dict:
        return {
            f"{k[0]}:{k[1]}": {"address": v.address, "amount": v.amount}
            for k, v in self._utxos.items()
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UTXOSet":
        utxo_set = cls()
        for key, val in d.items():
            tx_id, idx = key.rsplit(":", 1)
            utxo_set._utxos[(tx_id, int(idx))] = TxOutput(**val)
        return utxo_set


# ─────────────────────────────────────────────
# Blockchain
# ─────────────────────────────────────────────

class Blockchain:
    def __init__(self, data_dir: str = "data"):
        self.chain: List[Block] = []
        self.mempool: List[Transaction] = []
        self.utxo_set = UTXOSet()
        self.difficulty = INITIAL_DIFFICULTY
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # Carica da disco o crea genesis
        if not self._load():
            self._create_genesis()

    # ─────────────────────────────────────────
    # Genesis
    # ─────────────────────────────────────────

    def _create_genesis(self) -> None:
        """
        Blocco 0: genesis block immutabile.
        Nessuna coinbase — nessun pre-mine.
        Il messaggio è parte dell'hash e non può essere alterato.
        """
        genesis_message = {
            "message": "CRED Genesis Block — No pre-mine. No masters. Work is value.",
            "timestamp": "2025-01-01T00:00:00Z",
            "principles": [
                "Ogni CRED nasce da lavoro reale",
                "Nessuna autorità centrale",
                "Il codice è la legge, la rete è il giudice",
            ]
        }
        header = BlockHeader(
            version=1,
            prev_hash="0" * 64,
            merkle_root="0" * 64,
            timestamp=1735689600.0,  # 2025-01-01 00:00:00 UTC
            difficulty=self.difficulty,
            nonce=0,
        )
        genesis = Block(header=header, transactions=[genesis_message], height=0)
        genesis.mine(self.difficulty)
        self.chain.append(genesis)
        self._save()
        print(f"[CRED] Genesis block creato: {genesis.hash[:16]}...")

    # ─────────────────────────────────────────
    # Aggiunta blocchi
    # ─────────────────────────────────────────

    def add_block(self, block: Block) -> Tuple[bool, str]:
        """Valida e aggiunge un blocco alla chain."""
        ok, reason = self._validate_block(block)
        if not ok:
            return False, reason

        # Aggiorna UTXO set
        self._apply_block(block)

        self.chain.append(block)
        self._adjust_difficulty()
        self._save()
        return True, "ok"

    def _validate_block(self, block: Block) -> Tuple[bool, str]:
        last = self.chain[-1]

        if block.header.prev_hash != last.hash:
            return False, "prev_hash non corrisponde"
        if block.height != last.height + 1:
            return False, "altezza non valida"
        if not block.is_valid_pow():
            return False, "PoW non valido"
        if block.header.difficulty != self.difficulty:
            return False, "difficoltà non corrisponde"

        # Valida transazioni
        txs = [Transaction.from_dict(t) for t in block.transactions
               if not _is_genesis_data(t)]

        coinbase_count = sum(1 for t in txs if t.is_coinbase())
        if coinbase_count != 1:
            return False, "il blocco deve avere esattamente 1 coinbase"

        for tx in txs:
            if tx.is_coinbase():
                continue
            ok, reason = self._validate_transaction(tx)
            if not ok:
                return False, f"tx {tx.tx_id[:8]}... non valida: {reason}"

        # Verifica merkle root
        tx_ids = [t.get("tx_id", "") if isinstance(t, dict) else t.tx_id
                  for t in block.transactions]
        expected_merkle = compute_merkle_root(tx_ids)
        if block.header.merkle_root != expected_merkle:
            return False, "merkle root non corrisponde"

        return True, "ok"

    def _validate_transaction(self, tx: Transaction) -> Tuple[bool, str]:
        """Valida una transazione normale (non coinbase)."""
        total_in = 0.0
        for inp in tx.inputs:
            utxo = self.utxo_set.get(inp.tx_id, inp.output_index)
            if not utxo:
                return False, f"UTXO {inp.tx_id[:8]}:{inp.output_index} non trovato"

            # Verifica che chi spende possieda l'output
            expected_address = public_key_to_address(inp.public_key)
            if expected_address != utxo.address:
                return False, "indirizzo non corrisponde alla chiave pubblica"

            # Verifica firma
            if not verify_signature(inp.public_key, tx.signing_data(), inp.signature):
                return False, "firma non valida"

            total_in += utxo.amount

        total_out = sum(o.amount for o in tx.outputs)
        if total_out > total_in:
            return False, f"output ({total_out}) > input ({total_in})"

        return True, "ok"

    def _apply_block(self, block: Block) -> None:
        """Aggiorna l'UTXO set con le transazioni del blocco."""
        for t in block.transactions:
            if _is_genesis_data(t):
                continue
            tx = Transaction.from_dict(t)

            # Consuma inputs (eccetto coinbase)
            if not tx.is_coinbase():
                for inp in tx.inputs:
                    self.utxo_set.spend(inp.tx_id, inp.output_index)

            # Aggiunge outputs
            for i, out in enumerate(tx.outputs):
                self.utxo_set.add(tx.tx_id, i, out)

    # ─────────────────────────────────────────
    # Mining
    # ─────────────────────────────────────────

    def mine_pending(self, miner_address: str) -> Optional[Block]:
        """Costruisce e mina un nuovo blocco con le tx in mempool."""
        coinbase = create_coinbase(miner_address, self.height + 1, len(self.mempool))
        transactions = [coinbase] + list(self.mempool)
        tx_dicts = [tx.to_dict() for tx in transactions]

        tx_ids = [tx.tx_id for tx in transactions]
        merkle_root = compute_merkle_root(tx_ids)

        header = BlockHeader(
            version=1,
            prev_hash=self.chain[-1].hash,
            merkle_root=merkle_root,
            timestamp=time.time(),
            difficulty=self.difficulty,
        )
        block = Block(header=header, transactions=tx_dicts, height=self.height + 1)

        print(f"[CRED] Mining blocco {block.height} (difficulty={self.difficulty})...")
        start = time.time()
        block.mine(self.difficulty)
        elapsed = time.time() - start
        print(f"[CRED] Blocco {block.height} minato in {elapsed:.2f}s — hash: {block.hash[:16]}...")

        ok, reason = self.add_block(block)
        if ok:
            self.mempool.clear()
            return block
        else:
            print(f"[CRED] Blocco rifiutato: {reason}")
            return None

    # ─────────────────────────────────────────
    # Mempool
    # ─────────────────────────────────────────

    def add_to_mempool(self, tx: Transaction) -> Tuple[bool, str]:
        ok, reason = self._validate_transaction(tx)
        if ok:
            self.mempool.append(tx)
        return ok, reason

    # ─────────────────────────────────────────
    # Difficulty adjustment
    # ─────────────────────────────────────────

    def _adjust_difficulty(self) -> None:
        if len(self.chain) % DIFFICULTY_ADJUSTMENT_INTERVAL != 0:
            return
        if len(self.chain) < DIFFICULTY_ADJUSTMENT_INTERVAL:
            return

        recent = self.chain[-DIFFICULTY_ADJUSTMENT_INTERVAL:]
        elapsed = recent[-1].header.timestamp - recent[0].header.timestamp
        expected = TARGET_BLOCK_TIME * DIFFICULTY_ADJUSTMENT_INTERVAL

        if elapsed < expected / 2:
            self.difficulty += 1
            print(f"[CRED] Difficoltà aumentata a {self.difficulty}")
        elif elapsed > expected * 2:
            self.difficulty = max(1, self.difficulty - 1)
            print(f"[CRED] Difficoltà diminuita a {self.difficulty}")

    # ─────────────────────────────────────────
    # Proprietà
    # ─────────────────────────────────────────

    @property
    def height(self) -> int:
        return len(self.chain) - 1

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def balance(self, address: str) -> float:
        return self.utxo_set.balance(address)

    # ─────────────────────────────────────────
    # Persistenza
    # ─────────────────────────────────────────

    def _save(self) -> None:
        chain_path = os.path.join(self.data_dir, "chain.json")
        utxo_path = os.path.join(self.data_dir, "utxo.json")

        with open(chain_path, "w") as f:
            json.dump([b.to_dict() for b in self.chain], f, indent=2)
        with open(utxo_path, "w") as f:
            json.dump(self.utxo_set.to_dict(), f, indent=2)

    def _load(self) -> bool:
        chain_path = os.path.join(self.data_dir, "chain.json")
        utxo_path = os.path.join(self.data_dir, "utxo.json")

        if not os.path.exists(chain_path):
            return False
        try:
            with open(chain_path) as f:
                chain_data = json.load(f)
            self.chain = [Block.from_dict(b) for b in chain_data]

            if os.path.exists(utxo_path):
                with open(utxo_path) as f:
                    self.utxo_set = UTXOSet.from_dict(json.load(f))

            print(f"[CRED] Chain caricata: {len(self.chain)} blocchi")
            return True
        except Exception as e:
            print(f"[CRED] Errore caricamento chain: {e}")
            return False


# ─────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────

def _is_genesis_data(t) -> bool:
    """Rileva se un elemento è il messaggio del genesis block (non una tx)."""
    return isinstance(t, dict) and "message" in t
