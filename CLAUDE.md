# Boomerang Looper

Single-file Tkinter desktop app that loops a video forward→reverse until a target
duration is reached, with optional crossfades between segments, encoded via FFmpeg
(NVENC when available, libx264 fallback). Output is a PowerDirector-compatible
H.264 MP4, hard-cut to an exact duration.

## Files

- `Boomerang_Looper.py` — entire app (UI + FFmpeg orchestration in one file).
- `REVIEW.md` — code review with 5 prioritized improvement suggestions
  (thread-safety, redundant re-encoding, silent-audio crash, subprocess
  hardening, real progress/cancel).
- `Run Boomerang Looper.bat` — double-click launcher (uses `pythonw` to avoid
  a console window; falls back to `python`).

## Requirements

- Python 3 with Tkinter (stdlib).
- FFmpeg + ffprobe on PATH.

## Running

```
python Boomerang_Looper.py
```

or double-click `Run Boomerang Looper.bat`.

## Notes for future work

- No git repository initialized yet in this folder.
- All 5 issues from `REVIEW.md` have been implemented (see Changelog). The
  file still documents the original findings for reference.
- `_run_ffmpeg()` is now the single choke point for every FFmpeg call — it
  handles thread-safe progress reporting, cancellation, and error capture.
  Any new FFmpeg step should go through it rather than calling
  `subprocess.run`/`Popen` directly.

## Changelog

- 2026-07-19 — Reviewed project, wrote `REVIEW.md` with 5 improvement
  suggestions (Tk thread-safety, redundant encoding, silent-audio crash,
  subprocess hardening, real progress/cancel button).
- 2026-07-19 — Implemented all 5 `REVIEW.md` improvements in
  `Boomerang_Looper.py`:
  - All worker-thread UI updates now go through `self.after(0, ...)`
    (`_set_status`/`_set_progress`), fixing the Tk thread-safety bug.
  - Forward/reverse segments are now encoded once and reused across loops
    (via repeated concat/xfade inputs) instead of re-encoding per loop.
  - Added `has_audio_stream()` probe; audio filters/maps/codecs are now
    skipped for videos with no audio track instead of crashing.
  - Added `_subprocess_flags()` (hides console window flash on Windows),
    hardened `get_video_duration()` (checked ffprobe call, JSON-decode
    error handling, format-level duration fallback), replaced `assert`
    input validation with explicit `if`/`messagebox` checks, and named
    FFmpeg failures by step (e.g. "FFmpeg failed while reversing the clip").
  - Added real progress via FFmpeg's `-progress pipe:1` (mapped across
    per-step pct ranges) and a Cancel button that terminates the active
    FFmpeg process (`_run_ffmpeg`, `Cancelled` exception,
    `WM_DELETE_WINDOW` handler).
  - Minor notes also addressed: `loops_needed` gets a +1 safety margin,
    `_xfade_concat` now reuses the already-known clip duration instead of
    re-probing segments, and output-path-equals-input-path is now rejected.
  - Fixed Pyright/Pylance type-checker errors surfaced by the IDE
    (`_subprocess_flags() -> dict[str, Any]`, `Optional` narrowing via
    `assert` in `_run_ffmpeg` for `duration`/`start_pct`/`end_pct`/
    `proc.stdout`).
  - Verified end-to-end with synthetic clips: crossfade+audio,
    no-crossfade+audio, crossfade+no-audio, and mid-run cancel all produce
    correct output with no hangs.
- 2026-07-19 — Added `Run Boomerang Looper.bat` double-click launcher
  (prefers `pythonw` to avoid a console flash, falls back to `python`).
  Verified it launches the app correctly via ShellExecute (the way
  double-click actually invokes it).
- 2026-07-29 — Implemented 3 major new features in `Boomerang_Looper.py`:
  - **Audio track replacement & mixing**: Added file picker for audio/music tracks (`.mp3`, `.wav`, etc.) with 3 modes (`Keep original`, `Replace audio`, `Mix with original`) and an optional 2s end-of-track fade-out.
  - **Playback speed controls**: Added speed dropdown (`0.5x`, `0.75x`, `1.0x`, `1.25x`, `1.5x`, `2.0x`) applying `setpts` and `atempo` filters.
  - **Advanced transition styles**: Added transition effect dropdown supporting 10 FFmpeg `xfade` styles (`fade`, `wipeleft`, `wiperight`, `slideup`, `slidedown`, `circlecrop`, `radial`, `zoomIn`, `pixelize`, `dissolve`).

