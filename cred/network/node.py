"""
CRED - Rete P2P
Comunicazione TCP tra nodi, sincronizzazione chain, propagazione tx e blocchi
"""

import json
import socket
import threading
import time
from typing import List, Set, Optional

from core.block import Block
from core.transaction import Transaction


# ─────────────────────────────────────────────
# Messaggi di protocollo
# ─────────────────────────────────────────────

MSG_HELLO       = "hello"        # handshake iniziale con altezza chain
MSG_GET_BLOCKS  = "get_blocks"   # richiedi blocchi da altezza X
MSG_BLOCKS      = "blocks"       # risposta con lista blocchi
MSG_NEW_BLOCK   = "new_block"    # annuncio nuovo blocco minato
MSG_NEW_TX      = "new_tx"       # propagazione nuova transazione
MSG_GET_PEERS   = "get_peers"    # richiedi lista peer
MSG_PEERS       = "peers"        # risposta con lista peer

BUFFER_SIZE = 1024 * 1024  # 1 MB per messaggio


def encode_msg(msg_type: str, payload: dict) -> bytes:
    msg = json.dumps({"type": msg_type, "payload": payload})
    return (msg + "\n").encode()


def decode_msg(data: bytes) -> Optional[dict]:
    try:
        return json.loads(data.decode().strip())
    except Exception:
        return None


# ─────────────────────────────────────────────
# Connessione con un peer
# ─────────────────────────────────────────────

class PeerConnection:
    def __init__(self, host: str, port: int, node: "Node"):
        self.host = host
        self.port = port
        self.node = node
        self.sock: Optional[socket.socket] = None
        self.connected = False

    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((self.host, self.port))
            self.connected = True
            threading.Thread(target=self._listen, daemon=True).start()
            self._send_hello()
            return True
        except Exception as e:
            print(f"[P2P] Connessione a {self.host}:{self.port} fallita: {e}")
            return False

    def send(self, msg_type: str, payload: dict) -> None:
        if not self.connected or not self.sock:
            return
        try:
            self.sock.sendall(encode_msg(msg_type, payload))
        except Exception as e:
            print(f"[P2P] Errore invio a {self.host}:{self.port}: {e}")
            self.connected = False

    def _send_hello(self) -> None:
        self.send(MSG_HELLO, {
            "height": self.node.blockchain.height,
            "version": 1,
        })

    def _listen(self) -> None:
        buffer = b""
        while self.connected:
            try:
                data = self.sock.recv(BUFFER_SIZE)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    msg = decode_msg(line)
                    if msg:
                        self.node.handle_message(msg, self)
            except Exception:
                break
        self.connected = False
        print(f"[P2P] Disconnesso da {self.host}:{self.port}")

    def __repr__(self):
        return f"Peer({self.host}:{self.port})"


# ─────────────────────────────────────────────
# Nodo P2P
# ─────────────────────────────────────────────

class Node:
    def __init__(self, host: str, port: int, blockchain):
        self.host = host
        self.port = port
        self.blockchain = blockchain
        self.peers: List[PeerConnection] = []
        self.seen_hashes: Set[str] = set()  # anti-loop per blocchi/tx
        self._server_thread = None

    def start(self) -> None:
        """Avvia il server TCP in ascolto."""
        self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self._server_thread.start()
        print(f"[P2P] Nodo avviato su {self.host}:{self.port}")

    def _server_loop(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(16)
        while True:
            try:
                conn, addr = server.accept()
                peer = PeerConnection.__new__(PeerConnection)
                peer.host, peer.port = addr
                peer.node = self
                peer.sock = conn
                peer.connected = True
                self.peers.append(peer)
                threading.Thread(target=peer._listen, daemon=True).start()
                print(f"[P2P] Nuovo peer connesso: {addr[0]}:{addr[1]}")
            except Exception as e:
                print(f"[P2P] Errore server: {e}")

    def connect_to(self, host: str, port: int) -> bool:
        """Connettiti a un peer noto."""
        peer = PeerConnection(host, port, self)
        if peer.connect():
            self.peers.append(peer)
            return True
        return False

    # ─────────────────────────────────────────
    # Gestione messaggi in arrivo
    # ─────────────────────────────────────────

    def handle_message(self, msg: dict, sender: PeerConnection) -> None:
        msg_type = msg.get("type")
        payload = msg.get("payload", {})

        if msg_type == MSG_HELLO:
            self._handle_hello(payload, sender)

        elif msg_type == MSG_GET_BLOCKS:
            self._handle_get_blocks(payload, sender)

        elif msg_type == MSG_BLOCKS:
            self._handle_blocks(payload)

        elif msg_type == MSG_NEW_BLOCK:
            self._handle_new_block(payload, sender)

        elif msg_type == MSG_NEW_TX:
            self._handle_new_tx(payload, sender)

        elif msg_type == MSG_GET_PEERS:
            self._handle_get_peers(sender)

        elif msg_type == MSG_PEERS:
            self._handle_peers(payload)

    def _handle_hello(self, payload: dict, sender: PeerConnection) -> None:
        their_height = payload.get("height", 0)
        our_height = self.blockchain.height
        if their_height > our_height:
            # Il peer ha una chain più lunga — chiedi i blocchi mancanti
            sender.send(MSG_GET_BLOCKS, {"from_height": our_height + 1})

    def _handle_get_blocks(self, payload: dict, sender: PeerConnection) -> None:
        from_height = payload.get("from_height", 0)
        blocks = [b.to_dict() for b in self.blockchain.chain[from_height:from_height + 50]]
        sender.send(MSG_BLOCKS, {"blocks": blocks})

    def _handle_blocks(self, payload: dict) -> None:
        blocks_data = payload.get("blocks", [])
        added = 0
        for b_data in blocks_data:
            block = Block.from_dict(b_data)
            if block.hash in self.seen_hashes:
                continue
            ok, reason = self.blockchain.add_block(block)
            if ok:
                self.seen_hashes.add(block.hash)
                added += 1
        if added:
            print(f"[P2P] Sincronizzati {added} blocchi dalla rete")

    def _handle_new_block(self, payload: dict, sender: PeerConnection) -> None:
        block = Block.from_dict(payload)
        if block.hash in self.seen_hashes:
            return
        ok, reason = self.blockchain.add_block(block)
        if ok:
            self.seen_hashes.add(block.hash)
            # Propaga agli altri peer (escluso il mittente)
            self.broadcast(MSG_NEW_BLOCK, payload, exclude=sender)

    def _handle_new_tx(self, payload: dict, sender: PeerConnection) -> None:
        tx = Transaction.from_dict(payload)
        if tx.tx_id in self.seen_hashes:
            return
        ok, _ = self.blockchain.add_to_mempool(tx)
        if ok:
            self.seen_hashes.add(tx.tx_id)
            self.broadcast(MSG_NEW_TX, payload, exclude=sender)

    def _handle_get_peers(self, sender: PeerConnection) -> None:
        peer_list = [
            {"host": p.host, "port": p.port}
            for p in self.peers if p.connected and p != sender
        ]
        sender.send(MSG_PEERS, {"peers": peer_list})

    def _handle_peers(self, payload: dict) -> None:
        for peer_info in payload.get("peers", []):
            host, port = peer_info["host"], peer_info["port"]
            already = any(p.host == host and p.port == port for p in self.peers)
            if not already:
                self.connect_to(host, port)

    # ─────────────────────────────────────────
    # Broadcast
    # ─────────────────────────────────────────

    def broadcast(self, msg_type: str, payload: dict, exclude: PeerConnection = None) -> None:
        for peer in self.peers:
            if peer.connected and peer != exclude:
                peer.send(msg_type, payload)

    def announce_block(self, block: Block) -> None:
        self.seen_hashes.add(block.hash)
        self.broadcast(MSG_NEW_BLOCK, block.to_dict())

    def announce_tx(self, tx: Transaction) -> None:
        self.seen_hashes.add(tx.tx_id)
        self.broadcast(MSG_NEW_TX, tx.to_dict())

    @property
    def peer_count(self) -> int:
        return sum(1 for p in self.peers if p.connected)
