import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from comfy.comfy_types import IO
from comfy_api.input_impl import VideoFromFile


# Utility: find ComfyUI's output directory if possible
def _resolve_output_dir():
    here = Path(__file__).resolve()
    # Look up the tree for a folder that has an 'output' directory
    for p in [here] + list(here.parents):
        out = p / "output"
        if out.is_dir():
            target = out / "lofi_creation"
            target.mkdir(parents=True, exist_ok=True)
            return target
    # Fallback to a local outputs folder inside this node directory
    fallback = Path(__file__).resolve().parent / "outputs"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


OUTPUT_DIR = _resolve_output_dir()


def _which(cmd):
    """Return path to executable or None."""
    return shutil.which(cmd)


def _require_ffmpeg():
    if not _which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found on PATH. Please install ffmpeg and ensure 'ffmpeg' and 'ffprobe' are available."
        )
    if not _which("ffprobe"):
        raise RuntimeError(
            "ffprobe not found on PATH. Please install ffmpeg (which includes ffprobe)."
        )


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return name or str(int(time.time()))


def _guess_ext_from_url(url: str, default: str = "") -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    return ext if ext else default


def _download_direct(url: str, dest: Path) -> Path:
    try:
        import requests  # type: ignore
    except Exception as e:
        raise RuntimeError("The 'requests' package is required to download direct URLs. Please install it.") from e

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 512):
                if chunk:
                    f.write(chunk)
    return dest


def _download_with_yt_dlp(url: str, out_dir: Path, base_name: str) -> Path:
    try:
        import yt_dlp  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "The 'yt-dlp' package is required for non-direct media URLs (e.g., YouTube). Please install it."
        ) from e

    out_tmpl = str(out_dir / f"{base_name}.%(ext)s")
    ydl_opts = {
        "outtmpl": out_tmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError("Failed to download media via yt-dlp.")
        # yt-dlp returns an actual filename
        if "requested_downloads" in info and info["requested_downloads"]:
            filename = info["requested_downloads"][0].get("_filename")
        else:
            filename = ydl.prepare_filename(info)
    return Path(filename)


def _download_media(url: str, out_dir: Path, label: str, media_type: str) -> Path:
    """
    Download media from a URL or copy from local path.
    media_type: 'video' or 'audio' for naming.
    Returns local file path.
    """
    if not url:
        raise ValueError(f"{media_type} url is empty")

    parsed = urlparse(url)
    base = _safe_filename(label)

    # Local file path
    if parsed.scheme in ("", "file"):
        local_path = Path(parsed.path if parsed.scheme == "file" else url)
        if not local_path.exists():
            raise FileNotFoundError(f"Local path not found: {local_path}")
        dest = out_dir / f"{base}{local_path.suffix or ''}"
        if local_path.resolve() != dest.resolve():
            shutil.copyfile(local_path, dest)
        else:
            # Already in place
            pass
        return dest

    # HTTP(S) URL
    if parsed.scheme in ("http", "https"):
        # Decide whether to attempt direct download vs yt-dlp
        ext = _guess_ext_from_url(url)
        direct_exts = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
        if ext in direct_exts:
            dest = out_dir / f"{base}{ext}"
            return _download_direct(url, dest)
        # Fallback to yt-dlp for non-direct URLs (e.g., YouTube)
        return _download_with_yt_dlp(url, out_dir, base)

    raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")


def _probe_duration_seconds(path: Path) -> float:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        dur = float(proc.stdout.strip())
        if dur <= 0:
            raise ValueError
        return dur
    except Exception:
        # Unknown; fallback large
        return 0.0


def _ffmpeg_merge_loop(video_path: Path, audio_path: Path, duration: float, out_path: Path) -> None:
    """Try looping both video and audio with -stream_loop and trim to duration."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-stream_loop", "-1", "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(audio_path),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg failed during merge")


def _ffmpeg_concat_then_merge(video_path: Path, audio_path: Path, duration: float, out_path: Path) -> None:
    """Fallback: make a concat list repeating the video enough times, then merge with audio and trim."""
    # Determine repeats needed
    vdur = _probe_duration_seconds(video_path)
    repeats = 1
    if vdur > 0 and duration > 0:
        import math
        repeats = max(1, math.ceil(duration / vdur))

    with tempfile.TemporaryDirectory() as td:
        concat_list = Path(td) / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for _ in range(repeats):
                # Use absolute paths; -safe 0 allows it
                f.write(f"file '{video_path.as_posix()}'\n")

        # Build FFmpeg command
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-stream_loop", "-1", "-i", str(audio_path),
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "ffmpeg failed during concat/merge fallback")


class XimiLofiCreation:
    """
    lofi-creation (by ximi-ai)

    Inputs:
    - video_url (string): URL or local path to a video
    - music_url (string): URL or local path to an audio
    - duration_seconds (int/float): Output duration in seconds

    Output:
    - video_path (string): Path to the generated MP4
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_str": (IO.STRING, {
                    "default": "",
                    "multiline": False,
                    "forceInput": True,
                    "tooltip": "Video URL or local file path provided by another node",
                }),
                "audio_str": (IO.STRING, {
                    "default": "",
                    "multiline": False,
                    "forceInput": True,
                    "tooltip": "Audio URL or local file path provided by another node",
                }),
                "duration_seconds": (IO.FLOAT, {"default": 600.0, "min": 1.0, "max": 60*60*6, "step": 1.0}),
            }
        }

    RETURN_TYPES = (IO.VIDEO,)
    RETURN_NAMES = ("video",)
    FUNCTION = "create_lofi"
    CATEGORY = "ximi-ai/lofi"

    def create_lofi(self, video_str: str, audio_str: str, duration_seconds: float):
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")

        _require_ffmpeg()

        session_dir = OUTPUT_DIR / time.strftime("%Y%m%d_%H%M%S")
        session_dir.mkdir(parents=True, exist_ok=True)

        # Download/copy inputs
        video_local = _download_media(video_str, session_dir, "video", "video")
        audio_local = _download_media(audio_str, session_dir, "audio", "audio")

        out_name = f"lofi_{int(time.time())}.mp4"
        out_path = session_dir / out_name

        # Try simple infinite loop + trim
        try:
            _ffmpeg_merge_loop(video_local, audio_local, float(duration_seconds), out_path)
        except Exception:
            # Fallback to concat method
            _ffmpeg_concat_then_merge(video_local, audio_local, float(duration_seconds), out_path)

        # Wrap the produced file as a Comfy VIDEO output
        video_obj = VideoFromFile(str(out_path))
        return (video_obj,)


NODE_CLASS_MAPPINGS = {
    # Internal id -> class
    "XimiLofiCreation": XimiLofiCreation,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    # Internal id -> display name in UI
    "XimiLofiCreation": "lofi-creation",
}
