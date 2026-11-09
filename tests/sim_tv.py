"""A simulated Samsung Frame art service, for tests and development only.

It speaks the same protocol that `samsungtvws` 3.0.x uses against a 2021 Frame:
a WebSocket channel for commands (`ms.channel.emit` / `d2d_service_message`) and
a separate TCP socket ("D2D") for image bytes. It runs on plain `ws://`, because
the library uses TLS only on port 8002.

It is built from reading the library code, not from captures of a real TV, so it
proves that Curator drives the library correctly. Only the real TV can prove that
the TV answers the same way.

Run it on its own: python -m tests.sim_tv --port 18002
"""
from __future__ import annotations

import io
import json
import socket
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image
from websockets.sync.server import serve

TOKEN = "SIMULATED-TOKEN-12345"


def _jpeg(color, size=(320, 180)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG", quality=80)
    return out.getvalue()


@dataclass
class Piece:
    content_id: str
    category_id: str
    data: bytes
    matte_id: str = "none"


@dataclass
class SimFrame:
    """The TV's state. Tests read and change it directly."""

    require_pairing: bool = True
    allow: bool = True  # False acts like a person pressing Deny on the remote
    api_version: str = "4.3.4.0"
    pieces: dict = field(default_factory=dict)
    current: Optional[str] = None
    paired_tokens: set = field(default_factory=set)
    log: list = field(default_factory=list)

    def __post_init__(self):
        if not self.pieces:
            for i, color in enumerate(["#2b5876", "#355c7d", "#134e5e"], 1):
                cid = f"SAM-S0000{i}"
                self.pieces[cid] = Piece(cid, "MY-C0004", _jpeg(color))
            self.current = "SAM-S00001"


class SimTVServer:
    def __init__(self, frame: SimFrame | None = None, host: str = "127.0.0.1", port: int = 0):
        self.frame = frame or SimFrame()
        self.host = host
        self._server = serve(self._handle, host, port)
        self.port = self._server.socket.getsockname()[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> "SimTVServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # -- protocol -----------------------------------------------------------

    def _handle(self, ws):
        f = self.frame
        path = ws.request.path
        query = dict(p.split("=", 1) for p in path.split("?", 1)[1].split("&")) if "?" in path else {}
        token = query.get("token")
        f.log.append(("connect", path.split("?")[0], bool(token)))
        if f.require_pairing and token not in f.paired_tokens:
            if not f.allow:
                ws.send(json.dumps({"event": "ms.channel.unauthorized"}))
                return
            f.paired_tokens.add(TOKEN)  # the person pressed Allow
            ws.send(json.dumps({"event": "ms.channel.connect", "data": {"token": TOKEN, "id": "x"}}))
        else:
            ws.send(json.dumps({"event": "ms.channel.connect", "data": {"id": "x"}}))
        ws.send(json.dumps({"event": "ms.channel.ready", "data": {}}))
        for raw in ws:
            if isinstance(raw, bytes):
                continue  # API 0.97 binary uploads are not simulated
            msg = json.loads(raw)
            if msg.get("method") != "ms.channel.emit":
                continue
            req = json.loads(msg["params"]["data"])
            with self._lock:
                self._answer(ws, req)

    def _reply(self, ws, req, **payload):
        payload.setdefault("event", req["request"])
        payload["request_id"] = req.get("request_id", req.get("id"))
        payload["id"] = payload["request_id"]
        ws.send(json.dumps({"event": "d2d_service_message", "data": json.dumps(payload)}))

    def _answer(self, ws, req):
        f = self.frame
        name = req["request"]
        f.log.append(("request", name))
        if name == "api_version":
            self._reply(ws, req, version=f.api_version)
        elif name == "get_content_list":
            items = [{"content_id": p.content_id, "category_id": p.category_id,
                      "matte_id": p.matte_id, "width": 3840, "height": 2160}
                     for p in f.pieces.values()]
            self._reply(ws, req, content_list=json.dumps(items))
        elif name == "get_current_artwork":
            self._reply(ws, req, content_id=f.current or "")
        elif name == "get_artmode_status":
            self._reply(ws, req, value="on")
        elif name == "select_image":
            cid = req.get("content_id")
            if cid not in f.pieces:
                self._reply(ws, req, event="error", error_code="-1",
                            request_data=json.dumps({"request": name}))
            else:
                f.current = cid
                self._reply(ws, req)
        elif name == "delete_image_list":
            ids = [c["content_id"] for c in req.get("content_id_list", [])]
            for cid in ids:
                f.pieces.pop(cid, None)
                if f.current == cid:
                    f.current = None
            self._reply(ws, req, content_id_list=json.dumps(req.get("content_id_list", [])))
        elif name == "get_thumbnail":
            cid = req["content_id"]
            piece = f.pieces.get(cid)
            if not piece:
                self._reply(ws, req, event="error", error_code="-1",
                            request_data=json.dumps({"request": name}))
                return
            port = self._d2d_send(piece)
            self._reply(ws, req, conn_info=json.dumps({"ip": self.host, "port": port, "key": "k"}))
        elif name == "send_image":
            key = uuid.uuid4().hex
            port = self._d2d_receive(ws, req, key)
            self._reply(ws, req, event="ready_to_use",
                        conn_info=json.dumps({"ip": self.host, "port": port, "key": key}))
        else:
            self._reply(ws, req, event="error", error_code="-7",
                        request_data=json.dumps({"request": name}))

    # -- D2D sockets --------------------------------------------------------

    def _listener(self):
        s = socket.socket()
        s.bind((self.host, 0))
        s.listen(1)
        s.settimeout(10)
        return s, s.getsockname()[1]

    def _d2d_send(self, piece: Piece) -> int:
        s, port = self._listener()

        def run():
            try:
                conn, _ = s.accept()
                with conn:
                    head = json.dumps({"fileID": piece.content_id, "fileType": "jpg",
                                       "fileLength": len(piece.data), "num": 0, "total": 1}).encode()
                    conn.sendall(len(head).to_bytes(4, "big") + head + piece.data)
            finally:
                s.close()

        threading.Thread(target=run, daemon=True).start()
        return port

    def _d2d_receive(self, ws, req, key: str) -> int:
        s, port = self._listener()
        f = self.frame

        def recv_exact(conn, n):
            buf = b""
            while len(buf) < n:
                chunk = conn.recv(n - len(buf))
                if not chunk:
                    raise ConnectionError("closed")
                buf += chunk
            return buf

        def run():
            try:
                conn, _ = s.accept()
                with conn:
                    n = int.from_bytes(recv_exact(conn, 4), "big")
                    head = json.loads(recv_exact(conn, n))
                    if head.get("secKey") != key:
                        return
                    data = recv_exact(conn, int(head["fileLength"]))
                with self._lock:
                    cid = f"MY_F{len(f.pieces) + 1:04d}"
                    f.pieces[cid] = Piece(cid, "MY-C0002", data, req.get("matte_id", "none"))
                    f.log.append(("uploaded", cid, req.get("matte_id"), req.get("file_type")))
                    ws.send(json.dumps({"event": "d2d_service_message", "data": json.dumps(
                        {"event": "image_added", "content_id": cid, "request_id": req.get("request_id")})}))
            finally:
                s.close()

        threading.Thread(target=run, daemon=True).start()
        return port


def main():
    import argparse
    import time

    ap = argparse.ArgumentParser(prog="tests.sim_tv")
    ap.add_argument("--port", type=int, default=18002)
    args = ap.parse_args()
    with SimTVServer(port=args.port) as srv:
        print(f"Simulated Frame on ws://127.0.0.1:{srv.port} (Ctrl-C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
