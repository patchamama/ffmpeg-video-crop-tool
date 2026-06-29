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
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

PORT = 5553
VERSION = "1.0.0"
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


def _kill_server_on_port() -> bool:
    """Kill any process listening on PORT. Returns True if something was killed."""
    killed = False
    if SYSTEM == "Windows":
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            )
            seen_pids: set[str] = set()
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 5:
                    continue
                local_addr = parts[1]
                foreign_addr = parts[2]
                pid = parts[-1]
                if (
                    local_addr.endswith(f":{PORT}")
                    and foreign_addr in ("0.0.0.0:0", "[::]:0", "*:*")
                    and pid.isdigit()
                    and pid not in seen_pids
                    and int(pid) != os.getpid()
                ):
                    seen_pids.add(pid)
                    subprocess.run(
                        ["taskkill", "/PID", pid, "/F"],
                        capture_output=True, timeout=5,
                    )
                    killed = True
        except Exception:
            pass
    else:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{PORT}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid in result.stdout.strip().splitlines():
                pid = pid.strip()
                if pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(["kill", "-9", pid], capture_output=True, timeout=5)
                    killed = True
        except Exception:
            try:
                subprocess.run(
                    ["fuser", "-k", f"{PORT}/tcp"],
                    capture_output=True, timeout=5,
                )
                killed = True
            except Exception:
                pass
    return killed


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
    """Register context menu entries, prompting on first run.

    On subsequent runs the registration is silently refreshed with the current
    exe path — this is critical when the user installs a new version to a
    different location, because HKCU takes precedence over HKCR and would
    otherwise keep pointing at the old exe indefinitely.
    """
    cfg = _load_config()
    first_time = not cfg.get("context_menu_asked")

    if SYSTEM == "Windows":
        if first_time:
            cfg["context_menu_asked"] = True
            _save_config(cfg)
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
                    cfg["context_menu_registered"] = True
                    _save_config(cfg)
                    _register_windows_context_menu(exe_path)
            except Exception:
                pass
        elif cfg.get("context_menu_registered"):
            # Silently re-register with current exe path so updates take effect.
            try:
                _register_windows_context_menu(exe_path)
            except Exception:
                pass

    elif SYSTEM == "Linux":
        if first_time:
            cfg["context_menu_asked"] = True
            _save_config(cfg)
            _install_linux_desktop(exe_path)


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

    # Resolve optional file argument (from right-click "Open With").
    # Accept by existence OR by extension — is_file() can return False on
    # network/cloud-synced paths even when the file is perfectly valid.
    file_arg: Path | None = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and arg.strip():
            p = Path(arg.strip())
            if p.is_file() or p.suffix.lower() in VIDEO_EXTS:
                try:
                    file_arg = p.resolve()
                except OSError:
                    file_arg = p.absolute()
                break

    # Kill any existing server instance so the new one always starts clean.
    if _kill_server_on_port():
        print(f"Stopped previous instance on port {PORT}.")
        time.sleep(1.5)

    # Build the URL to open. Always embed ?file= and ?dir= when a file is given
    # so the browser can immediately display and process them.
    if file_arg:
        open_url = (
            f"{BASE_URL}"
            f"?file={urllib.parse.quote(file_arg.name)}"
            f"&dir={urllib.parse.quote(str(file_arg.parent))}"
        )
    else:
        open_url = BASE_URL

    print(f"FFmpeg Crop Tool  v{VERSION}")
    print("=" * 40)

    if not check_and_install_deps():
        sys.exit(1)

    # Set video directory via environment so crop_tool.py uses the right folder
    # even before the browser has loaded and processed the ?dir= URL param.
    if file_arg:
        os.environ["CROP_TOOL_VIDEO_DIR"] = str(file_arg.parent)
        os.environ["CROP_TOOL_INITIAL_FILE"] = file_arg.name

    exe_path = sys.executable if getattr(sys, "frozen", False) else str(Path(__file__).resolve())
    _maybe_setup_context_menu(exe_path)

    print(f"\nServer: {BASE_URL}")
    print("Press Ctrl+C to stop.\n")

    threading.Timer(1.5, lambda: webbrowser.open_new_tab(open_url)).start()

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
