"""The phone web app: a small Flask server and JSON API."""
from __future__ import annotations

import io
import re
import socket
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from PIL import Image

from .config import Settings
from .imaging import ImageError, prepare_image
from .library import Library
from .queue import PENDING, RetryQueue
from .tv import TV, FakeTV, TVUnavailable
from .worker import Worker

STATIC = Path(__file__).resolve().parent / "static"
THUMB_SIZE = (480, 270)
TV_CACHE_SECONDS = 5.0
STATIC_FILES = {
    "manifest.webmanifest": "application/manifest+json",
    "apple-touch-icon.png": "image/png",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "icon-maskable-512.png": "image/png",
}
CAMERA_NAME = re.compile(r"^(img|dsc|dscn|dcim|pxl|mvimg|image|photo|screenshot|picture|p)[\s_-]*[\d_ -]*$", re.I)


def friendly_label(stem: str, when: float | None = None) -> str:
    """Use the file name as a label unless it is a camera code like IMG_0193."""
    stem = " ".join((stem or "").split())[:60]
    if stem and not CAMERA_NAME.match(stem) and not re.fullmatch(r"[\d_ -]+", stem):
        return stem
    t = time.localtime(when if when is not None else time.time())
    return f"Photo, {time.strftime('%b', t)} {t.tm_mday}"


def lan_address() -> str | None:
    """The address other devices on the Wi-Fi use to reach this machine. No packet is sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # TEST-NET address: connect() on UDP only picks a route
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        s.close()


def create_app(
    settings: Settings, tv: TV, queue: RetryQueue, library: Library, worker: Worker | None = None
) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024
    for d in (settings.prepared_dir, settings.thumbs_dir, settings.incoming_dir):
        d.mkdir(parents=True, exist_ok=True)

    cache = {"at": 0.0, "value": False}
    cache_lock = threading.Lock()

    def tv_online() -> bool:
        with cache_lock:
            if time.monotonic() - cache["at"] > TV_CACHE_SECONDS:
                try:
                    cache["value"] = bool(tv.is_available())
                except Exception:
                    cache["value"] = False
                cache["at"] = time.monotonic()
            return cache["value"]

    def wake():
        queue.retry_now()
        if worker:
            worker.wake()

    def who(raw) -> str | None:
        """A name typed on the phone. It is only a label, never a login."""
        s = " ".join(str(raw or "").split())[:30]
        return s or None

    def err(code: int, key: str, message: str):
        return jsonify(error=key, message=message), code

    @app.after_request
    def no_store(resp: Response):
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(413)
    def too_big(_):
        return err(413, "too_big", f"That file is larger than {settings.max_upload_mb} MB.")

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/<name>")
    def static_file(name: str):
        if name not in STATIC_FILES:
            return err(404, "not_found", "Not found.")
        return send_from_directory(STATIC, name, mimetype=STATIC_FILES[name], max_age=86400)

    def share_url() -> str:
        """The page address for other phones. A local-only address becomes the Wi-Fi address."""
        host, _, port = request.host.partition(":")
        if host in ("127.0.0.1", "localhost"):
            host = lan_address() or host
        return f"http://{host}{':' + port if port else ''}/"

    @app.get("/api/share")
    def share():
        return jsonify(url=share_url())

    @app.get("/qr.svg")
    def qr():
        import segno

        out = io.BytesIO()
        segno.make(share_url(), error="m").save(out, kind="svg", scale=8, border=2,
                                                 dark="#000", light="#fff", xmldecl=False)
        return Response(out.getvalue(), mimetype="image/svg+xml",
                        headers={"Cache-Control": "no-store"})

    @app.post("/api/upload")
    def upload():
        f = request.files.get("file")
        if f is None:
            return err(400, "no_file", "No file was sent.")
        mode = request.form.get("mode", "crop")
        if mode not in ("crop", "fit"):
            return err(400, "bad_mode", "Mode must be crop or fit.")
        try:
            fx = min(max(float(request.form.get("fx", 50)), 0), 100) / 100
            fy = min(max(float(request.form.get("fy", 50)), 0), 100) / 100
        except ValueError:
            return err(400, "bad_focus", "Focus values must be numbers.")
        # We never use the name from the phone for a file. It is only a label.
        label = friendly_label(Path(f.filename or "photo").stem)
        uid = uuid.uuid4().hex
        incoming = settings.incoming_dir / uid
        f.save(incoming)
        prepared = settings.prepared_dir / f"{uid}.jpg"
        try:
            prepare_image(
                incoming, prepared, size=settings.size, mode=mode,
                focus=(fx, fy), quality=settings.jpeg_quality,
            )
            with Image.open(prepared) as im:
                im.thumbnail(THUMB_SIZE)
                im.save(settings.thumbs_dir / f"{uid}.jpg", "JPEG", quality=80)
        except ImageError:
            return err(400, "bad_image", "That file is not a photo that Curator can read.")
        finally:
            incoming.unlink(missing_ok=True)
        show_now = request.form.get("show_now", "").lower() in ("1", "true", "yes", "on")
        job_id = queue.enqueue(prepared, label, show_now=show_now, by=who(request.form.get("by")))
        if worker:
            worker.wake()
        return jsonify(job=job_id, name=label), 201

    @app.get("/api/status")
    def status():
        jobs = []
        for j in queue.list_jobs(30):
            if j.status == PENDING:
                state = "waiting" if j.attempts else "sending"
            else:
                state = j.status
            thumb = f"/api/art/{j.target}/thumb" if j.kind == "show" else f"/thumb/{Path(j.path).stem}"
            jobs.append(dict(
                id=j.id, name=j.name, state=state, attempts=j.attempts, error=j.last_error,
                thumb=thumb, kind=j.kind, show_now=bool(j.show_now), by=j.by, at=j.created_at,
            ))
        return jsonify(tv_online=tv_online(), fake=isinstance(tv, FakeTV), jobs=jobs)

    @app.get("/thumb/<stem>")
    def job_thumb(stem: str):
        if not stem.isalnum():
            return err(404, "not_found", "No such image.")
        path = settings.thumbs_dir / f"{stem}.jpg"
        if not path.exists():
            return err(404, "not_found", "No such image.")
        return send_file(path, mimetype="image/jpeg", max_age=3600)

    @app.get("/api/art")
    def art():
        try:
            items = tv.list_art()
        except TVUnavailable:
            return err(503, "tv_off", "The TV is off or cannot be reached.")
        live = {i.id for i in items}
        for p in library.list_pieces():
            if p.content_id not in live:
                library.remove(p.content_id)  # deleted on the TV itself
        mark = library.get_mark()
        waiting = queue.pending_show_target()
        out = []
        for i in items:
            piece = library.get(i.id)
            chosen = mark if (mark and mark.content_id == i.id and i.current) else None
            out.append(dict(
                id=i.id, name=(piece.name if piece else i.name) or i.id,
                mine=piece is not None, current=i.current, thumb=f"/api/art/{i.id}/thumb",
                chosen_by=chosen.by if chosen else None,
                chosen_at=chosen.at if chosen else None,
                queued=(waiting == i.id),
            ))
        return jsonify(art=out)

    @app.get("/api/art/<cid>/thumb")
    def art_thumb(cid: str):
        piece = library.get(cid)
        if piece and piece.thumb_path and Path(piece.thumb_path).exists():
            return send_file(piece.thumb_path, mimetype="image/jpeg", max_age=3600)
        try:
            data = tv.thumbnail(cid)
        except TVUnavailable:
            return err(503, "tv_off", "The TV is off or cannot be reached.")
        if not data:
            return err(404, "not_found", "No such artwork.")
        return send_file(io.BytesIO(data), mimetype="image/jpeg", max_age=3600)

    @app.post("/api/art/<cid>/show")
    def art_show(cid: str):
        """Choose the photo the TV shows. It goes through the queue, so a TV that is off still works."""
        body = request.get_json(silent=True) or {}
        piece = library.get(cid)
        name = piece.name if piece else (str(body.get("name") or "")[:60] or cid)
        job_id = queue.enqueue_show(cid, name, by=who(body.get("by")))
        if worker:
            worker.wake()
        return jsonify(job=job_id), 202

    @app.delete("/api/art/<cid>")
    def art_delete(cid: str):
        piece = library.get(cid)
        if piece is None:
            return err(403, "not_yours", "Curator can remove only photos that it added.")
        try:
            tv.delete(cid)
        except TVUnavailable:
            return err(503, "tv_off", "The TV is off or cannot be reached.")
        library.remove(cid)
        if piece.thumb_path:
            Path(piece.thumb_path).unlink(missing_ok=True)
        return jsonify(ok=True)

    @app.post("/api/jobs/<int:job_id>/retry")
    def job_retry(job_id: int):
        queue.retry(job_id)
        if worker:
            worker.wake()
        return jsonify(ok=True)

    @app.post("/api/dev/tv")
    def dev_tv():
        """Switch the fake TV on or off. Exists only when the TV is fake."""
        if not isinstance(tv, FakeTV):
            return err(404, "not_found", "Not found.")
        tv.online = bool((request.get_json(silent=True) or {}).get("online", True))
        with cache_lock:
            cache["at"] = 0.0
        if tv.online:
            wake()
        return jsonify(online=tv.online)

    return app
