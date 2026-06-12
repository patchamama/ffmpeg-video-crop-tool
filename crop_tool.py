from pathlib import Path
import json
import queue
import subprocess
import threading
import uuid

from flask import Flask, Response, abort, jsonify, request, send_from_directory, stream_with_context

VIDEO_FOLDER = Path(__file__).resolve().parent
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v")

app = Flask(__name__)
JOBS = {}


# ------------ helpers -------------------------------------------------------

def list_videos():
    return sorted(
        f.name for f in VIDEO_FOLDER.iterdir()
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    )


def safe_video_path(name):
    path = (VIDEO_FOLDER / name).resolve()
    if path.parent != VIDEO_FOLDER or not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        abort(404)
    return path


def get_video_metadata(name):
    path = safe_video_path(name)
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", str(path)],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width > 0 and height > 0:
            return {"width": width, "height": height, "source": "ffprobe"}
    except Exception as exc:
        return {"width": None, "height": None, "source": "browser", "error": str(exc)}
    return {"width": None, "height": None, "source": "browser"}


def get_url_info_via_ytdlp(url):
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist", "--no-warnings", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"error": (result.stderr or "yt-dlp failed").strip(), "width": None, "height": None}
        data = json.loads(result.stdout)
        width = int(data.get("width") or 0)
        height = int(data.get("height") or 0)
        for fmt in reversed(data.get("formats", [])):
            fw = int(fmt.get("width") or 0)
            fh = int(fmt.get("height") or 0)
            vcodec = fmt.get("vcodec") or ""
            if fw > 0 and fh > 0 and vcodec not in ("none", ""):
                if fw > width:
                    width, height = fw, fh
        return {
            "width": width or None,
            "height": height or None,
            "title": data.get("title", ""),
            "thumbnail": data.get("thumbnail", ""),
            "extractor": data.get("extractor", ""),
            "id": data.get("id", ""),
        }
    except subprocess.TimeoutExpired:
        return {"error": "yt-dlp timed out after 30s", "width": None, "height": None}
    except FileNotFoundError:
        return {"error": "yt-dlp not found — install with: pip install yt-dlp", "width": None, "height": None}
    except Exception as exc:
        return {"error": str(exc), "width": None, "height": None}


def read_process_output(job_id):
    job = JOBS[job_id]
    process = job["process"]
    try:
        for line in process.stdout:
            line = line.rstrip()
            job["logs"].append(line)
            job["queue"].put(line)
    finally:
        process.wait()
        yt_proc = job.get("yt_process")
        if yt_proc:
            try:
                yt_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                yt_proc.kill()
        job["returncode"] = process.returncode
        job["running"] = False
        final_line = f"Process exited with code {process.returncode}"
        job["logs"].append(final_line)
        job["queue"].put(final_line)
        job["queue"].put(None)


def start_job(ff_args, yt_args=None):
    job_id = uuid.uuid4().hex
    yt_proc = None

    if yt_args:
        yt_proc = subprocess.Popen(yt_args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        process = subprocess.Popen(
            ff_args,
            stdin=yt_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        yt_proc.stdout.close()
        log_cmd = " ".join(yt_args) + " | " + " ".join(ff_args)
    else:
        process = subprocess.Popen(
            ff_args,
            cwd=VIDEO_FOLDER,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        log_cmd = " ".join(ff_args)

    job = {
        "id": job_id,
        "args": ff_args,
        "yt_args": yt_args,
        "logs": [f"Running: {log_cmd}"],
        "queue": queue.Queue(),
        "running": True,
        "returncode": None,
        "process": process,
        "yt_process": yt_proc,
    }
    job["queue"].put(job["logs"][0])
    JOBS[job_id] = job
    threading.Thread(target=read_process_output, args=(job_id,), daemon=True).start()
    return job


def number_from_payload(payload, key, default=0):
    try:
        return int(round(float(payload.get(key, default))))
    except (TypeError, ValueError):
        return default


def build_media_args(payload):
    tool = payload.get("tool")
    if tool not in {"ffplay", "ffmpeg"}:
        abort(400, "tool must be ffplay or ffmpeg")

    source_url = (payload.get("url") or "").strip()
    file_name = (payload.get("file") or "").strip()

    if not source_url and not file_name:
        abort(400, "file or url is required")

    x = max(0, number_from_payload(payload, "x"))
    y = max(0, number_from_payload(payload, "y"))
    w = max(1, number_from_payload(payload, "w", 1))
    h = max(1, number_from_payload(payload, "h", 1))
    crop_filter = f"crop={w}:{h}:{x}:{y}"
    seek = max(0.0, float(payload.get("time") or 0))

    if source_url:
        yt_args = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "-o", "-",
            "--quiet",
            source_url,
        ]
        if tool == "ffplay":
            ff_args = ["ffplay", "-i", "pipe:0", "-vf", crop_filter]
        else:
            output_path = VIDEO_FOLDER / "cropped_output.mp4"
            ff_args = [
                "ffmpeg", "-y",
                "-i", "pipe:0",
                "-vf", crop_filter,
                "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-c:a", "copy",
                str(output_path),
            ]
        return ff_args, yt_args

    input_path = safe_video_path(file_name)
    if tool == "ffplay":
        return ["ffplay", "-ss", f"{seek:.3f}", "-i", str(input_path), "-vf", crop_filter], None

    output_path = VIDEO_FOLDER / f"cropped_{input_path.stem}.mp4"
    return [
        "ffmpeg", "-y",
        "-ss", f"{seek:.3f}",
        "-i", str(input_path),
        "-vf", crop_filter,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "copy",
        str(output_path),
    ], None


# ------------ HTML ----------------------------------------------------------

HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>FFmpeg Crop Tool</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body { margin: 0; background: #020617; }

#container {
    position: relative;
    display: block;
    width: 100%;
    background: black;
    min-height: 120px;
    overflow: hidden;
    border-radius: 1rem;
}

#video, #preview-img {
    width: 100%;
    height: auto;
    display: block;
    background: black;
}

#crop {
    position: absolute;
    box-sizing: border-box;
    border: 3px solid red;
    top: 100px;
    left: 100px;
    width: 300px;
    height: 200px;
    cursor: move;
    resize: both;
    overflow: auto;
    z-index: 10;
}

button { cursor: pointer; }

.tab-active {
    background: rgb(6 182 212);
    color: rgb(2 6 23);
}
.tab-inactive {
    background: transparent;
    color: rgb(148 163 184);
}
.tab-inactive:hover {
    background: rgb(30 41 59);
    color: rgb(226 232 240);
}
</style>
</head>

<body>
<div class="min-h-screen bg-slate-950 text-slate-100">
  <div class="mx-auto max-w-7xl px-4 py-8">

    <div class="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <p class="text-sm font-semibold uppercase tracking-[0.25em] text-cyan-300">Video crop workstation</p>
        <h1 class="mt-2 text-4xl font-bold tracking-tight">FFmpeg Crop Tool</h1>
        <p class="mt-2 text-slate-400">Crop local files or YouTube/URL videos. Preview with FFplay, export with FFmpeg.</p>
      </div>
      <div class="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100 shadow-lg shadow-cyan-950/30">
        Server: <span class="font-mono">http://127.0.0.1:5553</span>
      </div>
    </div>

    <div class="grid gap-6 xl:grid-cols-[1fr_440px]">

      <!-- Left: preview panel -->
      <section class="rounded-3xl border border-white/10 bg-slate-900/80 p-5 shadow-2xl shadow-black/40 backdrop-blur min-w-0">

        <!-- Source tabs -->
        <div class="mb-4 flex rounded-xl overflow-hidden border border-white/10 bg-slate-950 w-fit">
          <button id="tabLocal" onclick="setMode('local')" class="tab-active px-5 py-2 text-sm font-semibold transition">Local File</button>
          <button id="tabUrl" onclick="setMode('url')" class="tab-inactive px-5 py-2 text-sm font-semibold transition">URL / YouTube</button>
        </div>

        <!-- Local controls -->
        <div id="localControls" class="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div class="flex flex-1 gap-3 min-w-0">
            <select id="videoList" class="min-w-0 flex-1 rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-slate-100 outline-none ring-cyan-400/50 focus:ring-2"></select>
            <button onclick="loadVideo()" class="rounded-xl bg-cyan-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-cyan-300 whitespace-nowrap">Load</button>
          </div>
          <div class="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950 px-3 py-2">
            <label class="text-sm text-slate-300">Jump (min)</label>
            <input id="jump" type="number" value="30" class="w-20 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50">
            <button onclick="jump(-1)" class="rounded-lg bg-slate-800 px-3 py-2 font-bold hover:bg-slate-700">−</button>
            <button onclick="jump(1)" class="rounded-lg bg-slate-800 px-3 py-2 font-bold hover:bg-slate-700">+</button>
          </div>
        </div>

        <!-- URL controls -->
        <div id="urlControls" class="mb-4 hidden flex-col gap-3">
          <div class="flex gap-3">
            <input id="urlInput" type="url" placeholder="https://www.youtube.com/watch?v=... or any direct video URL"
              class="flex-1 min-w-0 rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-slate-100 placeholder-slate-500 outline-none focus:ring-2 focus:ring-cyan-400/50 font-mono text-sm">
            <button onclick="loadUrl()" class="rounded-xl bg-cyan-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-cyan-300 whitespace-nowrap">Load</button>
          </div>
          <div id="urlMeta" class="hidden rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-sm">
            <div id="urlTitle" class="text-slate-100 font-medium truncate"></div>
            <div id="urlDims" class="text-cyan-400 font-mono mt-1 text-xs"></div>
          </div>
          <div id="urlError" class="hidden rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-300"></div>
          <div id="urlLoading" class="hidden rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-400">
            Fetching video info via yt-dlp…
          </div>
        </div>

        <!-- Preview container -->
        <div id="container" class="border border-white/10 shadow-inner shadow-black/60">
          <video id="video" controls></video>
          <img id="preview-img" style="display:none" alt="Video thumbnail">
          <div id="crop"></div>
        </div>

        <!-- Info bars -->
        <div class="mt-4 grid gap-3 md:grid-cols-2">
          <div id="info" class="rounded-xl border border-white/10 bg-slate-950 px-4 py-3 font-mono text-sm text-emerald-300"></div>
          <div id="sourceInfo" class="rounded-xl border border-white/10 bg-slate-950 px-4 py-3 font-mono text-sm text-slate-300"></div>
        </div>
      </section>

      <!-- Right: controls panel -->
      <aside class="space-y-6 min-w-0">

        <!-- Crop values -->
        <section class="rounded-3xl border border-white/10 bg-slate-900/80 p-5 shadow-2xl shadow-black/40">
          <h2 class="text-lg font-semibold">Crop values <span class="text-sm font-normal text-slate-400">source pixels</span></h2>
          <div class="mt-4 grid grid-cols-2 gap-3">
            <label class="text-sm text-slate-300">X<input id="cropX" class="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50" type="number" min="0" value="100"></label>
            <label class="text-sm text-slate-300">Y<input id="cropY" class="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50" type="number" min="0" value="100"></label>
            <label class="text-sm text-slate-300">W<input id="cropW" class="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50" type="number" min="1" value="600"></label>
            <label class="text-sm text-slate-300">H<input id="cropH" class="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50" type="number" min="1" value="400"></label>
            <button onclick="applyManualCrop()" class="col-span-2 rounded-xl bg-emerald-400 px-4 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300">Apply values</button>
          </div>
        </section>

        <!-- Commands: local file -->
        <section id="localCmds" class="rounded-3xl border border-white/10 bg-slate-900/80 p-5 shadow-2xl shadow-black/40">
          <div class="mb-3 flex items-center justify-between gap-2 flex-wrap">
            <h2 class="text-lg font-semibold">Commands</h2>
            <div class="flex gap-2">
              <button onclick="runTool('ffplay')" class="rounded-xl bg-violet-400 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-violet-300">Run FFplay</button>
              <button onclick="runTool('ffmpeg')" class="rounded-xl bg-orange-400 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-orange-300">Run FFmpeg</button>
            </div>
          </div>
          <label class="text-sm font-medium text-slate-300">FFmpeg command</label>
          <textarea id="cmd" rows="3" class="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 p-3 font-mono text-xs text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50"></textarea>
          <button onclick="copyCmd()" class="mt-2 rounded-xl bg-slate-800 px-4 py-2 text-sm font-semibold hover:bg-slate-700">Copy FFmpeg command</button>

          <label class="mt-4 block text-sm font-medium text-slate-300">FFplay preview command</label>
          <textarea id="playCmd" rows="3" class="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 p-3 font-mono text-xs text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50"></textarea>
          <button onclick="copyPlayCmd()" class="mt-2 rounded-xl bg-slate-800 px-4 py-2 text-sm font-semibold hover:bg-slate-700">Copy FFplay command</button>
        </section>

        <!-- Commands: URL mode -->
        <section id="urlCmds" class="hidden rounded-3xl border border-white/10 bg-slate-900/80 p-5 shadow-2xl shadow-black/40">
          <div class="mb-3 flex items-center justify-between gap-2 flex-wrap">
            <h2 class="text-lg font-semibold">Commands <span class="text-sm font-normal text-slate-400">yt-dlp + ffmpeg</span></h2>
            <div class="flex gap-2">
              <button onclick="runTool('ffplay')" class="rounded-xl bg-violet-400 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-violet-300">Preview</button>
              <button onclick="runTool('ffmpeg')" class="rounded-xl bg-orange-400 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-orange-300">Export</button>
            </div>
          </div>
          <p class="mb-3 text-xs text-slate-400">These commands download and crop in one piped operation. You can also run them from any terminal.</p>

          <label class="text-sm font-medium text-slate-300">Download only (yt-dlp)</label>
          <textarea id="dlCmd" rows="2" class="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 p-3 font-mono text-xs text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50"></textarea>
          <button onclick="copyDlCmd()" class="mt-2 rounded-xl bg-slate-800 px-4 py-2 text-sm font-semibold hover:bg-slate-700">Copy download command</button>

          <label class="mt-4 block text-sm font-medium text-slate-300">Download + crop (yt-dlp | ffmpeg)</label>
          <textarea id="dlCropCmd" rows="4" class="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 p-3 font-mono text-xs text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/50"></textarea>
          <button onclick="copyDlCropCmd()" class="mt-2 rounded-xl bg-slate-800 px-4 py-2 text-sm font-semibold hover:bg-slate-700">Copy full command</button>
        </section>

      </aside>
    </div>

    <!-- Logs -->
    <section class="mt-6 rounded-3xl border border-white/10 bg-slate-900/80 p-5 shadow-2xl shadow-black/40">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-lg font-semibold">Backend logs</h2>
        <button onclick="stopCurrentJob()" class="rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-400">Stop current job</button>
      </div>
      <pre id="logs" class="min-h-48 max-h-96 overflow-auto rounded-2xl border border-white/10 bg-black p-4 font-mono text-xs leading-relaxed text-green-300">Ready.</pre>
    </section>

  </div>
</div>

<script>
// ---------- state -----------------------------------------------------------
let crop = document.getElementById("crop");
let video = document.getElementById("video");
let previewImg = document.getElementById("preview-img");
let videoList = document.getElementById("videoList");
let cropX = document.getElementById("cropX");
let cropY = document.getElementById("cropY");
let cropW = document.getElementById("cropW");
let cropH = document.getElementById("cropH");
let cmd = document.getElementById("cmd");
let playCmd = document.getElementById("playCmd");
let dlCmd = document.getElementById("dlCmd");
let dlCropCmd = document.getElementById("dlCropCmd");
let sourceInfo = document.getElementById("sourceInfo");

let updatingInputs = false;
let updatingCommands = false;
let cropStorageKey = "ffmpegCropTool.cropValues";
let videoStorageKey = "ffmpegCropTool.lastVideo";
let sourceSize = { width: 1920, height: 1080, source: "default" };
let pendingSourceCrop = null;
let sourceMode = "local";   // "local" | "url"
let currentUrlValue = "";

let videos = [];

// ---------- init: load video list ------------------------------------------
fetch("/list")
.then(r => r.json())
.then(data => {
    videos = data;
    videoList.innerHTML = "";
    if (data.length === 0) {
        let opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "No videos found next to crop_tool.py";
        videoList.appendChild(opt);
        updateUi();
        return;
    }
    data.forEach(v => {
        let opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v;
        videoList.appendChild(opt);
    });
    let saved = localStorage.getItem(videoStorageKey);
    if (saved && data.includes(saved)) {
        videoList.value = saved;
        loadVideo(false);
    } else {
        loadVideo(false);
    }
});

videoList.addEventListener("change", () => loadVideo(true));
video.addEventListener("timeupdate", updateUi);
video.addEventListener("seeked", updateUi);
video.addEventListener("pause", updateUi);
video.addEventListener("play", updateUi);
video.addEventListener("loadedmetadata", () => {
    if (!sourceSize.width || !sourceSize.height || sourceSize.source === "browser") {
        setSourceSize(video.videoWidth, video.videoHeight, "browser");
    }
    if (pendingSourceCrop) {
        setCropBoxFromSource(pendingSourceCrop.x, pendingSourceCrop.y, pendingSourceCrop.w, pendingSourceCrop.h, false);
        pendingSourceCrop = null;
    } else {
        syncOverlayFromCurrentSourceCrop(false);
    }
    updateUi();
});

// ---------- mode switching --------------------------------------------------
function setMode(mode) {
    sourceMode = mode;
    document.getElementById("tabLocal").className = mode === "local" ? "tab-active px-5 py-2 text-sm font-semibold transition" : "tab-inactive px-5 py-2 text-sm font-semibold transition";
    document.getElementById("tabUrl").className = mode === "url" ? "tab-active px-5 py-2 text-sm font-semibold transition" : "tab-inactive px-5 py-2 text-sm font-semibold transition";
    document.getElementById("localControls").classList.toggle("hidden", mode !== "local");
    document.getElementById("localControls").classList.toggle("flex", mode === "local");
    document.getElementById("urlControls").classList.toggle("hidden", mode !== "url");
    document.getElementById("urlControls").classList.toggle("flex", mode === "url");
    document.getElementById("localCmds").classList.toggle("hidden", mode !== "local");
    document.getElementById("urlCmds").classList.toggle("hidden", mode !== "url");

    if (mode === "local") {
        video.style.display = "block";
        previewImg.style.display = "none";
        currentUrlValue = "";
    }
    updateUi();
}

// ---------- local file loading ----------------------------------------------
async function loadVideo(persist = true) {
    let v = videoList.value;
    if (!v) return;
    if (persist) localStorage.setItem(videoStorageKey, v);
    await loadVideoMetadata(v);
    video.src = "/video/" + encodeURIComponent(v);
    let saved = readSavedCropValues();
    if (saved) {
        pendingSourceCrop = saved;
        setCropBoxFromSource(saved.x, saved.y, saved.w, saved.h, false);
    }
    updateUi();
}

async function loadVideoMetadata(file) {
    try {
        let r = await fetch("/metadata/" + encodeURIComponent(file));
        let data = await r.json();
        if (data.width && data.height) {
            setSourceSize(data.width, data.height, data.source || "ffprobe");
            return;
        }
    } catch (e) {
        console.warn("Could not load backend video metadata", e);
    }
    setSourceSize(video.videoWidth || 1920, video.videoHeight || 1080, "browser");
}

// ---------- URL loading -----------------------------------------------------
async function loadUrl() {
    let url = document.getElementById("urlInput").value.trim();
    if (!url) return;
    currentUrlValue = url;

    document.getElementById("urlMeta").classList.add("hidden");
    document.getElementById("urlError").classList.add("hidden");
    document.getElementById("urlLoading").classList.remove("hidden");

    try {
        let r = await fetch("/url-info?url=" + encodeURIComponent(url));
        let data = await r.json();
        document.getElementById("urlLoading").classList.add("hidden");

        if (data.error) {
            document.getElementById("urlError").textContent = "Error: " + data.error;
            document.getElementById("urlError").classList.remove("hidden");
            return;
        }

        // Show metadata
        document.getElementById("urlTitle").textContent = data.title || url;
        let dimsText = data.width && data.height
            ? `${data.width} × ${data.height}  |  ${data.extractor || "URL"}`
            : `Dimensions unknown  |  ${data.extractor || "URL"}`;
        document.getElementById("urlDims").textContent = dimsText;
        document.getElementById("urlMeta").classList.remove("hidden");

        // Set source size
        if (data.width && data.height) {
            setSourceSize(data.width, data.height, data.extractor || "url");
        }

        // Show thumbnail
        video.style.display = "none";
        if (data.thumbnail) {
            previewImg.src = data.thumbnail;
            previewImg.style.display = "block";
            previewImg.onload = () => {
                syncOverlayFromCurrentSourceCrop(false);
                updateUi();
            };
        } else {
            previewImg.style.display = "none";
        }

        let saved = readSavedCropValues();
        if (saved) {
            setCropBoxFromSource(saved.x, saved.y, saved.w, saved.h, false);
        }
        updateUi();
    } catch (e) {
        document.getElementById("urlLoading").classList.add("hidden");
        document.getElementById("urlError").textContent = "Request failed: " + e.message;
        document.getElementById("urlError").classList.remove("hidden");
    }
}

// allow pressing Enter in the URL input
document.getElementById("urlInput").addEventListener("keydown", e => {
    if (e.key === "Enter") loadUrl();
});

// ---------- source size & display helpers -----------------------------------
function getActivePreviewEl() {
    return (sourceMode === "url" && previewImg.style.display !== "none") ? previewImg : video;
}

function setSourceSize(width, height, source) {
    width = toNumber(width, 1920);
    height = toNumber(height, 1080);
    if (width <= 0 || height <= 0) return;
    sourceSize = { width, height, source };
    let container = document.getElementById("container");
    container.style.aspectRatio = `${width} / ${height}`;
    updateUi();
}

function jump(dir) {
    let m = parseInt(document.getElementById("jump").value) || 0;
    video.currentTime += dir * m * 60;
}

function toNumber(value, fallback) {
    let n = Number(value);
    return Number.isFinite(n) ? n : fallback;
}

function getDisplaySize() {
    let el = getActivePreviewEl();
    let rect = el.getBoundingClientRect();
    let w = rect.width || document.getElementById("container").offsetWidth || 800;
    let h = rect.height || Math.round(w * sourceSize.height / sourceSize.width) || 450;
    return { width: w, height: h };
}

function getScale() {
    let display = getDisplaySize();
    return {
        x: display.width / sourceSize.width,
        y: display.height / sourceSize.height
    };
}

function displayToSourceCrop() {
    let scale = getScale();
    return {
        x: Math.round(crop.offsetLeft / scale.x),
        y: Math.round(crop.offsetTop / scale.y),
        w: Math.round(crop.offsetWidth / scale.x),
        h: Math.round(crop.offsetHeight / scale.y)
    };
}

function sourceToDisplayCrop(x, y, w, h) {
    let scale = getScale();
    return {
        x: Math.round(x * scale.x),
        y: Math.round(y * scale.y),
        w: Math.round(w * scale.x),
        h: Math.round(h * scale.y)
    };
}

function clampSourceCrop(x, y, w, h) {
    x = Math.max(0, Math.round(toNumber(x, 0)));
    y = Math.max(0, Math.round(toNumber(y, 0)));
    w = Math.max(1, Math.round(toNumber(w, 1)));
    h = Math.max(1, Math.round(toNumber(h, 1)));
    w = Math.min(w, sourceSize.width - x);
    h = Math.min(h, sourceSize.height - y);
    return { x, y, w: Math.max(1, w), h: Math.max(1, h) };
}

// ---------- crop persistence ------------------------------------------------
function saveCropValues() {
    localStorage.setItem(cropStorageKey, JSON.stringify(displayToSourceCrop()));
}

function readSavedCropValues() {
    try {
        let saved = JSON.parse(localStorage.getItem(cropStorageKey));
        if (!saved) return null;
        let c = clampSourceCrop(saved.x, saved.y, saved.w, saved.h);
        return [c.x, c.y, c.w, c.h].every(Number.isFinite) ? c : null;
    } catch (e) {
        return null;
    }
}

// ---------- crop box manipulation -------------------------------------------
function setCropBoxFromDisplay(x, y, w, h, persist = true) {
    crop.style.left = Math.max(0, Math.round(x)) + "px";
    crop.style.top = Math.max(0, Math.round(y)) + "px";
    crop.style.width = Math.max(1, Math.round(w)) + "px";
    crop.style.height = Math.max(1, Math.round(h)) + "px";
    updateUi();
    if (persist) saveCropValues();
}

function setCropBoxFromSource(x, y, w, h, persist = true) {
    let sc = clampSourceCrop(x, y, w, h);
    let dc = sourceToDisplayCrop(sc.x, sc.y, sc.w, sc.h);
    setCropBoxFromDisplay(dc.x, dc.y, dc.w, dc.h, persist);
}

function syncOverlayFromCurrentSourceCrop(persist = false) {
    let sc = displayToSourceCrop();
    setCropBoxFromSource(sc.x, sc.y, sc.w, sc.h, persist);
}

function applyManualCrop() {
    setCropBoxFromSource(
        toNumber(cropX.value, 0),
        toNumber(cropY.value, 0),
        toNumber(cropW.value, 1),
        toNumber(cropH.value, 1)
    );
}

[cropX, cropY, cropW, cropH].forEach(input => {
    input.addEventListener("input", () => { if (!updatingInputs) applyManualCrop(); });
    input.addEventListener("change", () => { if (!updatingInputs) applyManualCrop(); });
});

// ---------- command parsing (sync from textarea) ----------------------------
function parseCropFilter(text) {
    let match = text.match(/crop\s*=\s*([0-9.]+)\s*:\s*([0-9.]+)\s*:\s*([0-9.]+)\s*:\s*([0-9.]+)/i);
    if (!match) return null;
    let values = match.slice(1).map(Number);
    if (!values.every(Number.isFinite)) return null;
    return { w: values[0], h: values[1], x: values[2], y: values[3] };
}

function applyCropFromCommand(text) {
    let parsed = parseCropFilter(text);
    if (!parsed) return;
    setCropBoxFromSource(parsed.x, parsed.y, parsed.w, parsed.h);
}

cmd.addEventListener("input", () => { if (!updatingCommands) applyCropFromCommand(cmd.value); });
playCmd.addEventListener("input", () => { if (!updatingCommands) applyCropFromCommand(playCmd.value); });
dlCmd.addEventListener("input", () => { if (!updatingCommands) applyCropFromCommand(dlCmd.value); });
dlCropCmd.addEventListener("input", () => { if (!updatingCommands) applyCropFromCommand(dlCropCmd.value); });

// ---------- dragging --------------------------------------------------------
let dragging = false;
let offsetX, offsetY;

function isResizeHandleEvent(e) {
    const sz = 24;
    const r = crop.getBoundingClientRect();
    const nR = e.clientX >= r.right - sz;
    const nB = e.clientY >= r.bottom - sz;
    const nL = e.clientX <= r.left + sz;
    const nT = e.clientY <= r.top + sz;
    return (nR && nB) || (nR && nT) || (nL && nB) || (nL && nT);
}

crop.addEventListener("mousedown", e => {
    if (isResizeHandleEvent(e)) { dragging = false; return; }
    dragging = true;
    offsetX = e.clientX - crop.offsetLeft;
    offsetY = e.clientY - crop.offsetTop;
});

document.addEventListener("mousemove", e => {
    if (!dragging) return;
    setCropBoxFromDisplay(e.clientX - offsetX, e.clientY - offsetY, crop.offsetWidth, crop.offsetHeight, false);
});

document.addEventListener("mouseup", () => {
    if (dragging) saveCropValues();
    dragging = false;
});

let resizeObserver = new ResizeObserver(() => { updateUi(); saveCropValues(); });
resizeObserver.observe(crop);

window.addEventListener("resize", () => syncOverlayFromCurrentSourceCrop(false));

// ---------- UI update -------------------------------------------------------
function getCurrentVideoTime() {
    return Number.isFinite(video.currentTime) ? video.currentTime : 0;
}

function buildFfmpegCommand(file, x, y, w, h) {
    let f = file || "input.mp4";
    return `ffmpeg -i "${f}" -vf "crop=${w}:${h}:${x}:${y}" -c:v libx264 -crf 18 -preset medium -c:a copy output.mp4`;
}

function buildFfplayCommand(file, x, y, w, h) {
    let seek = Math.max(0, getCurrentVideoTime()).toFixed(3);
    let f = file || "input.mp4";
    return `ffplay -ss ${seek} -i "${f}" -vf "crop=${w}:${h}:${x}:${y}"`;
}

function buildDownloadCommand(url) {
    if (!url) return "";
    return `yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" -o "download.%(ext)s" "${url}"`;
}

function buildDownloadCropCommand(url, x, y, w, h) {
    if (!url) return "";
    return `yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" -o - "${url}" \\
  | ffmpeg -i pipe:0 -vf "crop=${w}:${h}:${x}:${y}" -c:v libx264 -crf 18 -preset medium -c:a copy output.mp4`;
}

function updateUi() {
    let { x, y, w, h } = displayToSourceCrop();
    let file = videoList.value;

    updatingInputs = true;
    cropX.value = x; cropY.value = y; cropW.value = w; cropH.value = h;
    updatingInputs = false;

    document.getElementById("info").textContent = `Crop in source pixels: X=${x}, Y=${y}, W=${w}, H=${h}`;
    sourceInfo.textContent = `Source: ${sourceSize.width}×${sourceSize.height} (${sourceSize.source}) | Display: ${Math.round(getDisplaySize().width)}×${Math.round(getDisplaySize().height)}`;

    updatingCommands = true;
    cmd.value = buildFfmpegCommand(file, x, y, w, h);
    playCmd.value = buildFfplayCommand(file, x, y, w, h);
    dlCmd.value = buildDownloadCommand(currentUrlValue);
    dlCropCmd.value = buildDownloadCropCommand(currentUrlValue, x, y, w, h);
    updatingCommands = false;
}

// initialise
(function() {
    let saved = readSavedCropValues();
    if (saved) setCropBoxFromSource(saved.x, saved.y, saved.w, saved.h, false);
    else setCropBoxFromDisplay(100, 100, 300, 200, false);
    updateUi();
})();

// ---------- job execution ---------------------------------------------------
let currentJobId = null;
let logStream = null;

function getRunPayload(tool) {
    let c = displayToSourceCrop();
    let payload = { tool, x: c.x, y: c.y, w: c.w, h: c.h, time: getCurrentVideoTime() };
    if (sourceMode === "url") {
        payload.url = currentUrlValue;
    } else {
        payload.file = videoList.value;
    }
    return payload;
}

async function runTool(tool) {
    if (sourceMode === "local" && !videoList.value) {
        alert("Please select a video first.");
        return;
    }
    if (sourceMode === "url" && !currentUrlValue) {
        alert("Please load a URL first.");
        return;
    }

    let logs = document.getElementById("logs");
    logs.textContent = `Starting ${tool}...\n`;

    let response = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getRunPayload(tool))
    });

    if (!response.ok) {
        logs.textContent += await response.text();
        return;
    }

    let data = await response.json();
    currentJobId = data.id;
    openLogStream(currentJobId);
}

function appendLogLine(line) {
    let logs = document.getElementById("logs");
    logs.textContent += line + "\n";
    logs.scrollTop = logs.scrollHeight;
}

function openLogStream(jobId) {
    if (logStream) logStream.close();
    let logs = document.getElementById("logs");
    logs.textContent = "";

    logStream = new EventSource(`/stream/${jobId}`);
    logStream.onmessage = event => appendLogLine(JSON.parse(event.data));
    logStream.addEventListener("done", event => {
        appendLogLine(`Stream finished: ${event.data}`);
        logStream.close();
        logStream = null;
    });
    logStream.onerror = () => {
        appendLogLine("Log stream connection lost.");
        if (logStream) { logStream.close(); logStream = null; }
    };
}

async function stopCurrentJob() {
    if (!currentJobId) return;
    await fetch(`/stop/${currentJobId}`, { method: "POST" });
}

// ---------- copy helpers ----------------------------------------------------
function copyText(text) {
    navigator.clipboard.writeText(text).catch(() => {
        let el = document.createElement("textarea");
        el.value = text;
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
    });
}

function copyCmd()       { copyText(cmd.value);       alert("FFmpeg command copied!"); }
function copyPlayCmd()   { copyText(playCmd.value);   alert("FFplay command copied!"); }
function copyDlCmd()     { copyText(dlCmd.value);     alert("Download command copied!"); }
function copyDlCropCmd() { copyText(dlCropCmd.value); alert("Download + crop command copied!"); }
</script>
</body>
</html>
"""


# ------------ routes --------------------------------------------------------

@app.route("/")
def index():
    return HTML


@app.route("/list")
def list_route():
    return jsonify(list_videos())


@app.route("/metadata/<path:name>")
def metadata(name):
    return jsonify(get_video_metadata(name))


@app.route("/url-info")
def url_info():
    url = request.args.get("url", "").strip()
    if not url:
        abort(400, "url parameter is required")
    return jsonify(get_url_info_via_ytdlp(url))


@app.route("/video/<path:name>")
def video(name):
    safe_video_path(name)
    return send_from_directory(VIDEO_FOLDER, name, conditional=True)


@app.route("/run", methods=["POST"])
def run_tool():
    payload = request.get_json(force=True)
    ff_args, yt_args = build_media_args(payload)
    job = start_job(ff_args, yt_args)
    return jsonify({"id": job["id"], "args": ff_args})


@app.route("/logs/<job_id>")
def logs(job_id):
    job = JOBS.get(job_id)
    if not job:
        abort(404)
    return jsonify({
        "id": job_id,
        "logs": job["logs"],
        "running": job["running"],
        "returncode": job["returncode"],
        "args": job["args"],
    })


@app.route("/stream/<job_id>")
def stream_logs(job_id):
    job = JOBS.get(job_id)
    if not job:
        abort(404)

    def event_stream():
        for line in list(job["logs"]):
            yield f"data: {json.dumps(line)}\n\n"

        while True:
            try:
                line = job["queue"].get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue

            if line is None:
                yield "event: done\n"
                yield f"data: {json.dumps({'returncode': job['returncode']})}\n\n"
                break

            yield f"data: {json.dumps(line)}\n\n"

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@app.route("/stop/<job_id>", methods=["POST"])
def stop_job(job_id):
    job = JOBS.get(job_id)
    if not job:
        abort(404)
    if job["running"]:
        job["process"].terminate()
        yt_proc = job.get("yt_process")
        if yt_proc:
            yt_proc.terminate()
        job["logs"].append("Terminate requested by user.")
        job["queue"].put("Terminate requested by user.")
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"Looking for videos in: {VIDEO_FOLDER}")
    print("Open: http://127.0.0.1:5553")
    app.run(host="127.0.0.1", port=5553, debug=True)
