"""The phone web app: a small Flask server and JSON API."""
from __future__ import annotations

import io
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
        label = (Path(f.filename or "photo").stem or "photo")[:60]
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
        job_id = queue.enqueue(prepared, label)
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
            jobs.append(dict(
                id=j.id, name=j.name, state=state, attempts=j.attempts, error=j.last_error,
                thumb=f"/thumb/{Path(j.path).stem}",
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
        out = []
        for i in items:
            piece = library.get(i.id)
            out.append(dict(
                id=i.id, name=(piece.name if piece else i.name) or i.id,
                mine=piece is not None, current=i.current, thumb=f"/api/art/{i.id}/thumb",
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
        try:
            tv.select(cid)
        except TVUnavailable:
            return err(503, "tv_off", "The TV is off or cannot be reached.")
        except KeyError:
            return err(404, "not_found", "No such artwork.")
        return jsonify(ok=True)

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
