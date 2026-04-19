# CRED Blockchain

A Python implementation of a minimal, functional blockchain — Phase 1 of the CRED project.

CRED is designed as the **economic layer of a distributed AI network**: a token whose value is grounded in real AI inference work, not speculation. This repository contains the complete Phase 1 foundation — a working blockchain with no dependencies on third-party chain infrastructure.

---

## What this is

Phase 1 is a self-contained blockchain implementation in pure Python, covering:

- **Proof of Work** — SHA-256 with dynamic difficulty adjustment
- **UTXO model** — same transaction structure as Bitcoin
- **ECDSA signatures** — secp256k1 curve, identical to Bitcoin's cryptography
- **P2P networking** — TCP-based node communication with chain sync and block/tx propagation
- **CLI** — wallet, mining, send, status, node commands
- **Persistence** — chain and UTXO set saved to disk as JSON

This is working, tested code. A full Alice-to-Bob transaction flow has been verified end-to-end.

---

## Project structure

```
cred/
├── core/
│   ├── block.py          # Block structure, PoW mining
│   ├── transaction.py    # UTXO model, Merkle tree, coinbase
│   └── blockchain.py     # Main chain, UTXO set, block/tx validation
├── wallet/
│   └── wallet.py         # Key generation, address derivation (crd1...), signing
├── network/
│   └── node.py           # TCP P2P layer, chain sync, broadcast
├── cli/
│   └── cred.py           # Command-line interface
└── requirements.txt
```

---

## Installation

```bash
pip install -r requirements.txt
```

**Requirements:** Python 3.10+, `cryptography`

---

## Usage

```bash
# Create or load wallet, show balance
python cli/cred.py wallet

# Mine blocks (standalone)
python cli/cred.py mine

# Mine with P2P networking
python cli/cred.py mine --port 5000

# Connect to an existing peer while mining
python cli/cred.py mine --port 5001 --peer localhost:5000

# Send CRED to an address
python cli/cred.py send crd1<recipient_address> 10.0

# Show blockchain status
python cli/cred.py status

# Show last N blocks
python cli/cred.py blocks --n 10

# Start P2P node only (no mining)
python cli/cred.py node --port 5000
```

---

## Protocol parameters

| Parameter | Value |
|---|---|
| Initial block reward | 50 CRED |
| Halving interval | 500,000 blocks |
| Minimum reward | 1 CRED |
| Dynamic tx reward | 0.001 CRED per tx included |
| Target block time | 2.5 minutes |
| Difficulty adjustment | every 10 blocks |
| PoW algorithm | SHA-256 |
| Signature scheme | ECDSA secp256k1 |
| Address prefix | `crd1...` |
| Transaction model | UTXO |

---

## Design decisions

**No pre-mine.** The genesis block carries no coinbase. All CRED in circulation is produced by mining.

**Dynamic transaction reward.** Miners receive a small additional reward per transaction included in a block (drawn from emission, not from users). This keeps transactions free while maintaining miner incentive.

**UTXO over account model.** Chosen for auditability and parallelism — each output is independently verifiable without reconstructing global state.

**Minimal external dependencies.** The core logic has no blockchain framework dependencies. The only external library is `cryptography` for secp256k1 ECDSA.

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| 1 | ✅ Complete | Blockchain foundation (this repo) |
| 2 | Planned | Proof of Inference — mining = real AI inference work (commit-reveal scheme) |
| 3 | Planned | Ollama/multi-agent node integration |
| 4 | Planned | Web explorer, dashboard, Docker packaging |
| 5 | Planned | Whitepaper v2 derived from actual implementation |

---

## Relationship to the distributed AI network

CRED is not a general-purpose cryptocurrency. It is designed to serve as the incentive and trust layer of a distributed P2P AI network (separate repository), where:

- **Mining = AI inference work** — nodes earn CRED by performing verifiable AI inference tasks
- **Token utility is intrinsic** — CRED has value because it represents computational work done, not because of speculation
- **Trust is on-chain** — inference results are committed and revealed using the blockchain as an immutable ledger

Phase 2 will implement the Proof of Inference mechanism that connects this blockchain to the AI network.

---

## License

MIT
