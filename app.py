import os
import json
import queue
import shutil
import tempfile
import threading
import uuid
import zipfile
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import yt_dlp

app = Flask(__name__)

# job_id -> {queue, tmp_dir, serve_path, serve_name, serve_mime, ...}
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

DOWNLOAD_BASE = os.environ.get("DOWNLOAD_DIR", "/downloads")


def format_bytes(b):
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in s).strip() or "download"


def build_ydl_opts(out_dir: str, fmt: str, mp3_quality: str, mp4_quality: str, hooks: list) -> dict:
    """Build yt-dlp options depending on desired format and quality."""
    base = {
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "progress_hooks": hooks,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    if fmt == "mp4":
        if mp4_quality == "best":
            fmt_str = "bestvideo+bestaudio/best"
        else:
            fmt_str = f"bestvideo[height<={mp4_quality}]+bestaudio/best[height<={mp4_quality}]/best"
        base.update({
            "format": fmt_str,
            "merge_output_format": "mp4",
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
            ],
        })
    else:
        # MP3
        base.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "addmetadata": True,
            "embedthumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": mp3_quality},
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail"},
            ],
        })

    return base


def run_download(job_id: str, url: str, out_dir: str, browser_mode: bool,
                 fmt: str, mp3_quality: str, mp4_quality: str):
    with jobs_lock:
        q = jobs[job_id]["queue"]

    def send(event_type: str, data: dict):
        q.put({"event": event_type, "data": data})

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        send("error", {"message": f"Cannot create directory: {e}"})
        q.put(None)
        return

    playlist_info = {"current": 0, "total": 0}

    def progress_hook(d):
        n, t = playlist_info["current"], playlist_info["total"]
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed", 0) or 0
            eta = d.get("eta", 0) or 0
            pct = (downloaded / total * 100) if total else 0

            msg = f"Downloading {n} of {t}…" if t > 1 else "Downloading…"
            scaled = ((n - 1) / t * 90 + pct / 100 * 90 / t) if t > 1 else pct * 0.9

            send("progress", {
                "percent": round(scaled, 1),
                "status": msg,
                "speed": format_bytes(speed) + "/s" if speed else "",
                "eta": f"{eta}s" if eta else "",
            })

        elif d["status"] == "finished":
            action = "Processing" if fmt == "mp4" else "Converting to MP3"
            msg = f"{action} {n} of {t}…" if t > 1 else f"{action}…"
            base = ((n - 1) / t * 90) if t > 1 else 0
            send("progress", {"percent": round(base + 90 / max(t, 1), 1),
                               "status": msg, "speed": "", "eta": ""})

    def counting_hook(d):
        if d["status"] == "downloading" and playlist_info["current"] == 0:
            playlist_info["current"] = 1
        if d["status"] == "finished":
            playlist_info["current"] = min(playlist_info["current"] + 1, playlist_info["total"])
        progress_hook(d)

    # ── Info pass ─────────────────────────────────────────────────────────────
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        send("error", {"message": str(e)})
        q.put(None)
        return

    if not info:
        send("error", {"message": "Could not fetch media info. Check the URL."})
        q.put(None)
        return

    entries = info.get("entries")
    is_playlist = bool(entries)
    playlist_info["total"] = len(list(entries)) if entries else 1
    title = info.get("title", "download")

    with jobs_lock:
        jobs[job_id]["is_playlist"] = is_playlist
        jobs[job_id]["title"] = title

    send("info", {"title": title, "count": playlist_info["total"], "is_playlist": is_playlist})

    # ── Download ──────────────────────────────────────────────────────────────
    ydl_opts = build_ydl_opts(out_dir, fmt, mp3_quality, mp4_quality, [counting_hook])

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        send("error", {"message": str(e)})
        q.put(None)
        return

    ext = "mp4" if fmt == "mp4" else "mp3"
    output_files = sorted([
        os.path.join(out_dir, f) for f in os.listdir(out_dir)
        if f.lower().endswith(f".{ext}")
    ])

    if not output_files:
        send("error", {"message": f"No {ext.upper()} files produced — ffmpeg may be missing."})
        q.put(None)
        return

    # ── Browser-download mode ─────────────────────────────────────────────────
    if browser_mode:
        send("progress", {"percent": 97, "status": "Preparing download…", "speed": "", "eta": ""})

        if is_playlist and len(output_files) > 1:
            zip_name = f"{_safe_name(title)}.zip"
            zip_path = os.path.join(out_dir, zip_name)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in output_files:
                    zf.write(f, os.path.basename(f))
            with jobs_lock:
                jobs[job_id].update(serve_path=zip_path, serve_name=zip_name,
                                    serve_mime="application/zip")
        else:
            path = output_files[0]
            mime = "video/mp4" if fmt == "mp4" else "audio/mpeg"
            with jobs_lock:
                jobs[job_id].update(serve_path=path, serve_name=os.path.basename(path),
                                    serve_mime=mime)

        send("done", {"percent": 100, "status": "Ready!", "browser_download": True, "job_id": job_id})
    else:
        send("done", {"percent": 100, "status": "✓ Saved to server!", "browser_download": False})

    q.put(None)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", download_dir=DOWNLOAD_BASE)


@app.route("/api/folders")
def list_folders():
    base = request.args.get("path", DOWNLOAD_BASE)
    try:
        entries = [
            {"name": n, "path": os.path.join(base, n)}
            for n in sorted(os.listdir(base))
            if os.path.isdir(os.path.join(base, n))
        ]
        parent = os.path.dirname(base) if base != "/" else None
        return jsonify({"path": base, "entries": entries, "parent": parent})
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    browser_mode = bool(data.get("browser_mode", False))
    fmt = data.get("format", "mp3").lower()
    if fmt not in ("mp3", "mp4"):
        fmt = "mp3"
    mp3_quality = str(data.get("mp3_quality", "320"))
    mp4_quality = str(data.get("mp4_quality", "best"))

    if not url:
        return jsonify({"error": "URL is required"}), 400

    job_id = str(uuid.uuid4())
    tmp_dir = tempfile.mkdtemp(prefix="media_dl_") if browser_mode else None
    work_dir = tmp_dir if browser_mode else data.get("directory", DOWNLOAD_BASE).strip()

    with jobs_lock:
        jobs[job_id] = {
            "queue": queue.Queue(),
            "tmp_dir": tmp_dir,
            "serve_path": None,
            "serve_name": None,
            "serve_mime": None,
            "is_playlist": False,
            "title": "",
        }

    threading.Thread(
        target=run_download,
        args=(job_id, url, work_dir, browser_mode, fmt, mp3_quality, mp4_quality),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id})


@app.route("/api/progress/<job_id>")
def stream_progress(job_id):
    with jobs_lock:
        if job_id not in jobs:
            return jsonify({"error": "Job not found"}), 404
        q = jobs[job_id]["queue"]

    @stream_with_context
    def generate():
        while True:
            try:
                item = q.get(timeout=30)
            except queue.Empty:
                yield 'data: {"event":"ping"}\n\n'
                continue
            if item is None:
                yield f"data: {json.dumps({'event': 'end'})}\n\n"
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/fetch/<job_id>")
def fetch_file(job_id):
    """Stream the ready file to the browser, then clean up."""
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or not job.get("serve_path"):
            return "File not ready or already downloaded", 404
        serve_path = job["serve_path"]
        serve_name = job["serve_name"]
        serve_mime = job["serve_mime"]
        tmp_dir = job["tmp_dir"]
        job["serve_path"] = None  # prevent double-download

    file_size = os.path.getsize(serve_path)

    def stream_then_cleanup():
        try:
            with open(serve_path, "rb") as f:
                while chunk := f.read(1024 * 256):
                    yield chunk
        finally:
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
            with jobs_lock:
                jobs.pop(job_id, None)

    return Response(
        stream_then_cleanup(),
        mimetype=serve_mime,
        headers={
            "Content-Disposition": f'attachment; filename="{serve_name.encode("latin-1", "replace").decode("latin-1")}"',
            "Content-Length": str(file_size),
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
