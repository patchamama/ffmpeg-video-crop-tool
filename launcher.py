"""
Standalone launcher for FFmpeg Crop Tool.

Handles dependency detection, auto-install, context-menu registration,
file-argument support (right-click "Open With"), and server lifecycle.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

PORT = 5553
BASE_URL = f"http://127.0.0.1:{PORT}"
CONFIG_DIR = Path.home() / ".ffmpeg_crop_tool"
CONFIG_FILE = CONFIG_DIR / "config.json"
SYSTEM = platform.system()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _is_server_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def _save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ---------------------------------------------------------------------------
# Portable ffmpeg detection (bundled next to exe)
# ---------------------------------------------------------------------------

def _add_bundled_tools_to_path() -> None:
    """If ffmpeg is bundled next to the exe, prepend that dir to PATH."""
    if not getattr(sys, "frozen", False):
        return
    exe_dir = Path(sys.executable).parent
    probe = "ffmpeg.exe" if SYSTEM == "Windows" else "ffmpeg"
    if (exe_dir / probe).exists():
        os.environ["PATH"] = str(exe_dir) + os.pathsep + os.environ.get("PATH", "")


# ---------------------------------------------------------------------------
# Dependency installation
# ---------------------------------------------------------------------------

def _try_install_ffmpeg_windows() -> bool:
    for manager, args in [
        ("winget",  ["winget", "install", "--id", "Gyan.FFmpeg", "-e",
                     "--accept-source-agreements", "--accept-package-agreements"]),
        ("choco",   ["choco", "install", "ffmpeg", "-y"]),
        ("scoop",   ["scoop", "install", "ffmpeg"]),
    ]:
        if _which(manager):
            print(f"  Installing ffmpeg via {manager}…")
            r = _run(args, timeout=300)
            if r.returncode == 0 or _which("ffmpeg"):
                return True
    return False


def _try_install_ffmpeg_macos() -> bool:
    if _which("brew"):
        print("  Installing ffmpeg via Homebrew…")
        r = _run(["brew", "install", "ffmpeg"], timeout=600)
        return r.returncode == 0 or bool(_which("ffmpeg"))
    return False


def _try_install_ffmpeg_linux() -> bool:
    for manager, args in [
        ("apt-get", ["sudo", "apt-get", "install", "-y", "ffmpeg"]),
        ("dnf",     ["sudo", "dnf", "install", "-y", "ffmpeg"]),
        ("pacman",  ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"]),
        ("zypper",  ["sudo", "zypper", "install", "-y", "ffmpeg"]),
    ]:
        if _which(manager):
            print(f"  Installing ffmpeg via {manager}…")
            r = _run(args, timeout=300)
            if r.returncode == 0 or bool(_which("ffmpeg")):
                return True
    return False


def _try_install_ytdlp() -> bool:
    if getattr(sys, "frozen", False):
        print(
            "  yt-dlp not found. Install it for YouTube/URL support:\n"
            "  https://github.com/yt-dlp/yt-dlp/releases/latest"
        )
        return False
    print("  Installing yt-dlp via pip…")
    r = _run([sys.executable, "-m", "pip", "install", "--quiet", "yt-dlp"])
    return r.returncode == 0


def _show_error(title: str, msg: str) -> None:
    """Show a GUI error dialog on platforms where a console may not be visible."""
    print(f"\n[ERROR] {title}\n{msg}", file=sys.stderr)
    if SYSTEM == "Windows" and getattr(sys, "frozen", False):
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(title, msg)
            root.destroy()
        except Exception:
            pass


def check_and_install_deps() -> bool:
    _add_bundled_tools_to_path()

    missing_ff = not (_which("ffmpeg") and _which("ffprobe"))

    if missing_ff:
        print("ffmpeg / ffprobe not found — attempting automatic installation…")
        installed = False
        if SYSTEM == "Windows":
            installed = _try_install_ffmpeg_windows()
        elif SYSTEM == "Darwin":
            installed = _try_install_ffmpeg_macos()
        else:
            installed = _try_install_ffmpeg_linux()

        if not installed:
            msg = (
                "ffmpeg could not be installed automatically.\n\n"
                "Please install it manually:\n"
                "  Windows : winget install Gyan.FFmpeg\n"
                "  macOS   : brew install ffmpeg\n"
                "  Linux   : sudo apt install ffmpeg\n\n"
                "Download: https://ffmpeg.org/download.html"
            )
            _show_error("ffmpeg Missing", msg)
            return False

    if not _which("yt-dlp"):
        print("yt-dlp not found (optional — needed for YouTube/URL support).")
        _try_install_ytdlp()

    return True


# ---------------------------------------------------------------------------
# Context-menu registration
# ---------------------------------------------------------------------------

VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv"]


def _register_windows_context_menu(exe_path: str) -> None:
    """Register right-click 'Open with FFmpeg Crop Tool' in HKCU (no admin needed)."""
    import winreg
    for ext in VIDEO_EXTS:
        key_path = rf"Software\Classes\{ext}\shell\FFmpegCropTool"
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Open with FFmpeg Crop Tool")
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, exe_path)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe_path}" "%1"')
        except OSError:
            pass


def _unregister_windows_context_menu() -> None:
    import winreg
    for ext in VIDEO_EXTS:
        key_path = rf"Software\Classes\{ext}\shell\FFmpegCropTool"
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path + r"\command")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        except OSError:
            pass


def _install_linux_desktop(exe_path: str) -> None:
    mime_types = (
        "video/mp4;video/x-matroska;video/x-msvideo;video/quicktime;"
        "video/webm;video/x-ms-wmv;video/x-flv;"
    )
    desktop_content = (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        "Name=FFmpeg Crop Tool\n"
        "Comment=Crop videos with a visual overlay using FFmpeg\n"
        f"Exec={exe_path} %f\n"
        "Terminal=true\n"
        f"MimeType={mime_types}\n"
        "Categories=AudioVideo;Video;;\n"
    )
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = apps_dir / "ffmpeg-crop-tool.desktop"
    desktop_file.write_text(desktop_content)
    desktop_file.chmod(0o755)
    _run(["update-desktop-database", str(apps_dir)])


def _maybe_setup_context_menu(exe_path: str) -> None:
    """On first run, prompt user and register context menu."""
    cfg = _load_config()
    if cfg.get("context_menu_asked"):
        return

    cfg["context_menu_asked"] = True
    _save_config(cfg)

    if SYSTEM == "Windows":
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            answer = messagebox.askyesno(
                "FFmpeg Crop Tool",
                "Add 'Open with FFmpeg Crop Tool' to the right-click menu for video files?\n\n"
                "(This can be undone by running the app with --unregister-context-menu)",
            )
            root.destroy()
            if answer:
                _register_windows_context_menu(exe_path)
        except Exception:
            pass

    elif SYSTEM == "Linux":
        _install_linux_desktop(exe_path)


# ---------------------------------------------------------------------------
# Notify a running server about a file to open
# ---------------------------------------------------------------------------

def _call_open_file(path: str) -> bool:
    """Tell the running server to add the file's dir and queue it for the browser."""
    try:
        data = json.dumps({"path": path}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/open-file",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Handle CLI flags
    if "--unregister-context-menu" in sys.argv:
        if SYSTEM == "Windows":
            _unregister_windows_context_menu()
            print("Context menu entries removed.")
        else:
            print("Context menu unregistration is only supported on Windows via this flag.")
        return

    # Resolve optional file argument (from right-click "Open With")
    file_arg: Path | None = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            p = Path(arg)
            if p.is_file():
                file_arg = p.resolve()
                break

    # If the server is already running: tell it which file to open, then open a
    # new browser tab. The tab's JS polls /pending-open and auto-selects the file.
    # Using open_new_tab avoids the issue where webbrowser.open() reuses an
    # existing tab without re-running initVideoList().
    if _is_server_running():
        if file_arg:
            _call_open_file(str(file_arg))
        webbrowser.open_new_tab(BASE_URL)
        return

    print("FFmpeg Crop Tool")
    print("=" * 40)

    if not check_and_install_deps():
        sys.exit(1)

    # Set video directory via environment (crop_tool.py reads this)
    if file_arg:
        os.environ["CROP_TOOL_VIDEO_DIR"] = str(file_arg.parent)
        os.environ["CROP_TOOL_INITIAL_FILE"] = file_arg.name

    exe_path = sys.executable if getattr(sys, "frozen", False) else str(Path(__file__).resolve())
    _maybe_setup_context_menu(exe_path)

    print(f"\nServer: {BASE_URL}")
    print("Press Ctrl+C to stop.\n")

    threading.Timer(1.5, lambda: webbrowser.open_new_tab(BASE_URL)).start()

    from crop_tool import app
    try:
        app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
    except OSError as exc:
        msg = (
            f"Port {PORT} is already in use.\n"
            "Close the other instance and try again.\n\n"
            f"Error: {exc}"
        )
        _show_error("Port In Use", msg)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
