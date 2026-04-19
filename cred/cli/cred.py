"""
CRED - CLI
Interfaccia a riga di comando per wallet, mining, transazioni e stato della rete
"""

import argparse
import json
import os
import sys
import time
import threading

# Aggiungi la root del progetto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.blockchain import Blockchain
from core.transaction import Transaction, TxInput, TxOutput
from wallet.wallet import Wallet
from network.node import Node


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def load_or_create_wallet(wallet_path: str) -> Wallet:
    if os.path.exists(wallet_path):
        w = Wallet.load(wallet_path)
        print(f"[wallet] Caricato: {w.address}")
    else:
        w = Wallet()
        w.save(wallet_path)
        print(f"[wallet] Nuovo wallet creato: {w.address}")
    return w


def print_block(block) -> None:
    print(f"\n{'─'*60}")
    print(f"  Blocco #{block.height}")
    print(f"  Hash:     {block.hash[:32]}...")
    print(f"  PrevHash: {block.header.prev_hash[:32]}...")
    print(f"  Merkle:   {block.header.merkle_root[:32]}...")
    print(f"  Tempo:    {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(block.header.timestamp))}")
    print(f"  Nonce:    {block.header.nonce}")
    print(f"  Tx:       {len(block.transactions)}")
    print(f"{'─'*60}")


# ─────────────────────────────────────────────
# Comandi
# ─────────────────────────────────────────────

def cmd_wallet(args):
    """Crea o mostra il wallet."""
    w = load_or_create_wallet(args.wallet)
    bc = Blockchain(args.data)
    balance = bc.balance(w.address)
    print(f"\n{'─'*60}")
    print(f"  Indirizzo: {w.address}")
    print(f"  Saldo:     {balance:.4f} CRED")
    print(f"{'─'*60}")


def cmd_mine(args):
    """Mina blocchi continuamente."""
    w = load_or_create_wallet(args.wallet)
    bc = Blockchain(args.data)

    node = None
    if args.port:
        node = Node("0.0.0.0", args.port, bc)
        node.start()
        if args.peer:
            host, port = args.peer.split(":")
            node.connect_to(host, int(port))

    print(f"\n[CRED] Mining avviato — indirizzo miner: {w.address}")
    print("[CRED] Premi Ctrl+C per fermare\n")

    blocks_mined = 0
    try:
        while True:
            block = bc.mine_pending(w.address)
            if block:
                blocks_mined += 1
                balance = bc.balance(w.address)
                print(f"[CRED] ✓ Blocco #{block.height} — saldo: {balance:.4f} CRED")
                if node:
                    node.announce_block(block)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print(f"\n[CRED] Mining fermato. Blocchi minati: {blocks_mined}")


def cmd_send(args):
    """Invia CRED a un indirizzo."""
    w = load_or_create_wallet(args.wallet)
    bc = Blockchain(args.data)

    amount = float(args.amount)
    recipient = args.to
    balance = bc.balance(w.address)

    if balance < amount:
        print(f"[errore] Saldo insufficiente: {balance:.4f} CRED disponibili")
        sys.exit(1)

    # Raccogli UTXO sufficienti
    utxos = bc.utxo_set.utxos_for(w.address)
    inputs = []
    collected = 0.0
    for (tx_id, idx), utxo in utxos:
        if collected >= amount:
            break
        inputs.append(TxInput(
            tx_id=tx_id,
            output_index=idx,
            public_key=w.public_key_hex,
        ))
        collected += utxo.amount

    # Output: destinatario + resto
    outputs = [TxOutput(address=recipient, amount=amount)]
    rest = collected - amount
    if rest > 0.0001:
        outputs.append(TxOutput(address=w.address, amount=rest))

    tx = Transaction(inputs=inputs, outputs=outputs)

    # Firma tutti gli input
    sig = w.sign(tx.signing_data())
    for inp in tx.inputs:
        inp.signature = sig

    ok, reason = bc.add_to_mempool(tx)
    if ok:
        print(f"[CRED] ✓ Transazione aggiunta alla mempool")
        print(f"       ID: {tx.tx_id}")
        print(f"       {w.address[:20]}... → {recipient[:20]}... : {amount} CRED")
    else:
        print(f"[errore] Transazione rifiutata: {reason}")


def cmd_status(args):
    """Mostra lo stato della blockchain."""
    bc = Blockchain(args.data)
    last = bc.last_block

    print(f"\n{'═'*60}")
    print(f"  CRED Blockchain Status")
    print(f"{'═'*60}")
    print(f"  Altezza:      {bc.height}")
    print(f"  Difficoltà:   {bc.difficulty}")
    print(f"  Tx in pool:   {len(bc.mempool)}")
    print(f"  Ultimo blocco: {last.hash[:32]}...")
    print(f"  Timestamp:    {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last.header.timestamp))}")
    print(f"{'═'*60}")


def cmd_blocks(args):
    """Mostra gli ultimi N blocchi."""
    bc = Blockchain(args.data)
    n = int(args.n) if args.n else 5
    recent = bc.chain[-n:]
    for block in reversed(recent):
        print_block(block)


def cmd_node(args):
    """Avvia solo il nodo P2P (senza mining)."""
    bc = Blockchain(args.data)
    node = Node("0.0.0.0", int(args.port), bc)
    node.start()

    if args.peer:
        host, port = args.peer.split(":")
        node.connect_to(host, int(port))

    print(f"[CRED] Nodo P2P attivo sulla porta {args.port}")
    print("[CRED] Premi Ctrl+C per fermare")
    try:
        while True:
            time.sleep(5)
            print(f"[CRED] Peer connessi: {node.peer_count} — Altezza chain: {bc.height}")
    except KeyboardInterrupt:
        print("\n[CRED] Nodo fermato.")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="cred",
        description="CRED — Blockchain CLI",
    )
    parser.add_argument("--wallet", default="wallet.json", help="Path del file wallet")
    parser.add_argument("--data", default="data", help="Directory dati blockchain")

    sub = parser.add_subparsers(dest="command", required=True)

    # wallet
    sub.add_parser("wallet", help="Mostra wallet e saldo")

    # mine
    p_mine = sub.add_parser("mine", help="Mina blocchi")
    p_mine.add_argument("--port", type=int, default=None, help="Porta P2P (opzionale)")
    p_mine.add_argument("--peer", default=None, help="Peer iniziale host:porta")

    # send
    p_send = sub.add_parser("send", help="Invia CRED")
    p_send.add_argument("to", help="Indirizzo destinatario")
    p_send.add_argument("amount", help="Quantità CRED")

    # status
    sub.add_parser("status", help="Stato della blockchain")

    # blocks
    p_blocks = sub.add_parser("blocks", help="Ultimi blocchi")
    p_blocks.add_argument("--n", default="5", help="Quanti blocchi mostrare")

    # node
    p_node = sub.add_parser("node", help="Avvia nodo P2P")
    p_node.add_argument("--port", type=int, required=True, help="Porta di ascolto")
    p_node.add_argument("--peer", default=None, help="Peer iniziale host:porta")

    args = parser.parse_args()

    commands = {
        "wallet": cmd_wallet,
        "mine": cmd_mine,
        "send": cmd_send,
        "status": cmd_status,
        "blocks": cmd_blocks,
        "node": cmd_node,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
