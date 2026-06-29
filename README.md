# FFmpeg Crop Tool

A browser-based workstation for visually cropping videos using source-pixel-accurate coordinates. Draw a crop region by dragging, preview it with FFplay, and export with FFmpeg — for both local files and YouTube/URL videos.

## Features

- **Visual crop editor** — drag and resize the crop box directly on the video preview
- **Source-pixel accuracy** — crop coordinates always map to the original video resolution, regardless of browser display size
- **Local file support** — pick any video file from the tool's directory
- **YouTube / URL support** — paste any yt-dlp-compatible URL; the tool fetches dimensions and thumbnail via yt-dlp and generates ready-to-run commands
- **Live backend execution** — run FFplay (preview) or FFmpeg (export) from the browser; output streams in real time to the log panel
- **Command generation** — all commands are shown in copyable textareas:
  - FFmpeg crop command (local)
  - FFplay preview command (local)
  - yt-dlp download command (URL)
  - yt-dlp | ffmpeg piped crop command (URL)
- **Persistent state** — last selected video and crop values survive page reloads via `localStorage`
- **Two-way sync** — editing the command textarea updates the crop overlay, and vice versa
- **Manual input** — X / Y / W / H fields for precise numeric entry
- **Responsive UI** — adapts to any screen width

## Requirements

- Python 3.8+
- [FFmpeg](https://ffmpeg.org/) — `ffmpeg` and `ffprobe` must be in `PATH`
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — required only for URL/YouTube mode

```bash
# Install Python dependencies
pip install flask

# Install yt-dlp (for URL/YouTube support)
pip install yt-dlp
```

FFmpeg installation:
- **Windows**: download from https://ffmpeg.org/download.html or `winget install ffmpeg`
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg` or equivalent

## Installation

```bash
git clone <repo>
cd <repo>
pip install flask yt-dlp
```

Place your video files in the same directory as `crop_tool.py`.

## Usage

### Start the server

**Linux / macOS**
```bash
./start_ffmpeg-video-crop-tool.sh
```

**Windows**
```bat
start_ffmpeg-video-crop-tool.bat
```

**Manually**
```bash
python crop_tool.py
```

Then open **http://127.0.0.1:5553** in your browser.

### Local file workflow

1. Select a video from the dropdown and click **Load**
2. Drag the red crop box to position it; drag the corners to resize
3. The **X / Y / W / H** inputs update in real time — you can also type values directly
4. Click **Run FFplay** to preview the crop in a local window
5. Click **Run FFmpeg** to export `cropped_<filename>.mp4` to the same directory
6. Or copy the generated command and run it yourself

### URL / YouTube workflow

1. Click the **URL / YouTube** tab
2. Paste a YouTube URL or any direct video URL and click **Load**
3. The tool calls yt-dlp to fetch the video title, resolution, and thumbnail
4. The thumbnail is shown as the crop target — drag and resize the crop box on it
5. The **Download only** command lets you grab the raw video
6. The **Download + crop** command pipes yt-dlp into ffmpeg in one step:
   ```
   yt-dlp ... -o - "URL" | ffmpeg -i pipe:0 -vf "crop=W:H:X:Y" ... output.mp4
   ```
7. Click **Preview** or **Export** to run the piped command from the browser backend

> **Note**: The interactive preview area in URL mode uses the video thumbnail as a reference. Crop coordinates are calculated from the known source resolution, so they are accurate for the actual video even though you are looking at the thumbnail.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves the web UI |
| GET | `/list` | Returns JSON list of video files in the working directory |
| GET | `/metadata/<name>` | Returns `{ width, height, source }` via ffprobe |
| GET | `/url-info?url=<url>` | Returns `{ width, height, title, thumbnail, extractor }` via yt-dlp |
| GET | `/video/<name>` | Streams a local video file (supports range requests) |
| POST | `/run` | Starts an ffplay or ffmpeg job; returns `{ id }` |
| GET | `/logs/<id>` | Returns full log snapshot for a job |
| GET | `/stream/<id>` | Server-Sent Events stream of job output |
| POST | `/stop/<id>` | Terminates a running job |

### `/run` payload

```json
{
  "tool": "ffmpeg",
  "file": "video.mp4",
  "x": 100, "y": 50, "w": 1280, "h": 720,
  "time": 12.5
}
```

For URL mode, replace `"file"` with `"url"`:

```json
{
  "tool": "ffmpeg",
  "url": "https://www.youtube.com/watch?v=...",
  "x": 100, "y": 50, "w": 1280, "h": 720,
  "time": 0
}
```

## Output files

| Source | Output filename |
|--------|----------------|
| Local file `video.mp4` | `cropped_video.mp4` |
| URL | `cropped_output.mp4` |

All output files are written to the same directory as `crop_tool.py`.

## Supported formats

`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.m4v`

yt-dlp supports hundreds of sites — see the [full list](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).
