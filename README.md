lofi-creation (ComfyUI custom node)

Author: ximi-ai

Overview
- Downloads a video and an audio from URLs or local paths.
- Loops the video to reach the requested duration and merges the audio.
- Output: a single MP4 written under ComfyUI/output/lofi_creation.

Inputs
- video_str: IO.STRING (connected): URL or local path.
- audio_str: IO.STRING (connected): URL or local path.
- duration_seconds: Target output duration in seconds.


Output
- video_path (STRING): Full path to the generated MP4.

Notes
- Requires ffmpeg and ffprobe on PATH.
- If URLs are not direct media links (e.g., YouTube), yt-dlp is used.
- For direct HTTP(S) downloads, requests is used.

Installation
1) Ensure ffmpeg is installed (ffmpeg and ffprobe available on PATH).
2) Place this folder under ComfyUI/custom_nodes.
3) Install Python dependencies (if ComfyUI doesn’t auto-install):

   pip install -r requirements.txt

Usage
- Add the node "lofi-creation" to your workflow.
- Provide video_url, music_url, and duration_seconds.
- The node returns the path to the output MP4.


Additional Node
- String Pass (ximi-ai): Takes a string input from another node and returns the same string. Useful to route or reuse a string value (URL/path/text) in workflows.