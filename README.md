# Boomerang Looper

A small Windows desktop app that turns any video into a seamless
forward→reverse "boomerang" loop, cut to an exact target duration —
handy for looping a clip to match a song length (e.g. exactly 4m07s).

![loop icon](https://img.shields.io/badge/loop-forward%20%E2%86%92%20reverse-7C3AED)

## Features

- Loops a video **forward → reverse → forward → …** until it reaches an
  exact target duration, then hard-cuts it.
- **Custom audio / music track replacement & mixing** with optional end-of-track fade-out.
- **Playback speed controls** (0.5x slow-mo up to 2.0x fast-forward).
- **Multiple transition effects** (`fade`, `wipeleft`, `wiperight`, `slideup`, `slidedown`, `circlecrop`, `radial`, `zoomIn`, `pixelize`, `dissolve`).
- Optional **crossfade** between segments for a smoother join.
- **Real-time progress bar** driven by FFmpeg's own progress output.
- **Cancel** button — stops the running FFmpeg job cleanly at any time.
- Uses **NVENC** (NVIDIA hardware encoding) automatically when available,
  falling back to `libx264`.
- Output is a standard H.264 MP4 (yuv420p, faststart) compatible with
  editors like PowerDirector, Premiere, etc.
- Works with videos that have no audio track.

## Requirements

- Windows with Python 3 (Tkinter is included in the standard Python
  installer — no extra install needed).
- [FFmpeg](https://ffmpeg.org/download.html) (`ffmpeg` and `ffprobe`) on
  your `PATH`.

## Running

Double-click **`Run Boomerang Looper.bat`**, or from a terminal:

```
python Boomerang_Looper.py
```

## Usage

1. Click the file picker and choose a video.
2. Set the **target duration** (seconds) — use a preset or type your own.
3. Set the **crossfade overlap** (seconds) and choose a **transition effect** or set overlap to `0` for a hard cut.
4. Select **playback speed** (0.5x, 1.0x, 2.0x, etc.).
5. (Optional) Browse for a custom **audio / music track** and select **Replace audio**, **Mix with original**, or **Keep original**, with optional 2s fade out.
6. Click **Create Boomerang**, choose where to save, and watch the progress bar. You can cancel at any point.

## How it works

1. The source clip is copied once (forward segment) and re-encoded once
   with reversed video/audio (reverse segment).
2. Those two segments are chained forward→reverse→forward→… enough times
   to cover the target duration, joined either with a plain concat or an
   FFmpeg `xfade`/`acrossfade` filter chain if a crossfade is set.
3. The joined result is hard-trimmed to the exact target duration and
   re-encoded with compatibility flags for editing software.

## Project files

| File | Purpose |
|---|---|
| `Boomerang_Looper.py` | The entire app (UI + FFmpeg orchestration). |
| `Run Boomerang Looper.bat` | Double-click launcher (no console window). |
| `REVIEW.md` | Code review notes and improvement history. |
| `CLAUDE.md` | Project notes/changelog for AI-assisted development. |
