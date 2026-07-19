# Boomerang Looper — Code Review & Suggested Improvements

**Reviewed:** `Boomerang_Looper.py` (2026-07-19)

## Overview

A single-file Tkinter desktop app that loops a video forward→reverse until a target
duration is reached, with optional crossfades between segments, encoded via FFmpeg
(NVENC when available). The UI is polished and the overall flow (pick file → set
duration/crossfade → process in a background thread) is sound. The suggestions below
are ordered by impact.

---

## 1. Fix Tkinter thread-safety in `_process` (correctness — highest priority)

`_process()` runs on a background thread but calls `self.progress.set(...)`,
`self._set_status(...)` (which does `self.status_lbl.config(...)`) directly
(e.g. lines 308, 318, 324, 344). Tkinter is **not thread-safe** — mutating
widgets or `Variable`s from a non-main thread works "most of the time" but can
randomly deadlock or crash the interpreter, especially on Windows.

The code already does this correctly for the message boxes and the run button
(`self.after(0, ...)` in lines 358, 371, 378) — the same pattern should be used
for *every* UI touch from the worker thread:

```python
def _set_status(self, msg: str, error=False):
    def apply():
        self.status_text.set(msg)
        self.status_lbl.config(fg=self.ERROR if error else self.MUTED)
    self.after(0, apply)

def _set_progress(self, pct: float):
    self.after(0, lambda: self.progress.set(pct))
```

## 2. Stop re-encoding the same segments N times (performance — huge win)

The loop at lines 298–321 creates `loops_needed` identical copies of the forward
clip and — much worse — runs the expensive `reverse` re-encode `loops_needed`
times on the *same source*. For a 10s clip and a 4-minute target that's ~12
identical reverse encodes.

Encode **one** forward and **one** reverse segment, then reuse them:

- **No-crossfade path:** the concat demuxer happily accepts the same file listed
  multiple times — just write `fwd`/`rev` pairs into `concat.txt` repeatedly.
- **Crossfade path:** pass the same two files as repeated `-i` inputs (or better,
  build one crossfaded cycle and chain that).

This changes processing time from `O(loops)` to `O(1)` encodes plus one join, and
also fixes the misleading progress math (80% of the bar is spent on redundant work
while the actual heavy join step jumps 82→95 with no feedback).

## 3. Handle videos without an audio stream (crash bug)

Every FFmpeg command assumes audio exists:

- `-af areverse` (line 313) fails on silent clips,
- `_xfade_concat` maps `[{i}:a]` and uses `acrossfade` (lines 410, 425), which
  errors out if input has no audio,
- the concat/trim steps force `-c:a aac`.

A screen recording or GIF-style clip with no audio track will die with an opaque
"FFmpeg error". Probe for an audio stream once (ffprobe already returns all
streams in `get_video_duration`) and branch: skip `areverse`/`acrossfade`/audio
maps when there is none, or add `-an`.

## 4. Harden the FFmpeg subprocess plumbing

Several small robustness gaps around `subprocess`:

- **Console window flashes on Windows:** when run via `pythonw`/a shortcut, each
  `subprocess.run` can flash a console window. Pass
  `creationflags=subprocess.CREATE_NO_WINDOW` (Windows-only) via a small wrapper.
- **`get_video_duration` has no error handling:** no `check=True`, and
  `json.loads(result.stdout)` raises a bare `JSONDecodeError` if ffprobe fails
  (e.g. unsupported/corrupt file). Also, some containers only report duration on
  the *format* level — fall back to `-show_format` → `format.duration`.
- **Errors don't say which step failed:** wrap runs in a helper that raises with
  a step name ("reversing", "joining", "trimming") plus the stderr tail, so the
  error dialog is actionable.
- **`assert` for input validation** (lines 241–242) is stripped under `python -O`;
  use explicit `if`/`raise ValueError` instead.

## 5. Real progress reporting and a Cancel button (UX)

Two related UX gaps:

- **Progress is synthetic.** The bar tracks "segments created" and then sits at
  82→95 during the join/trim, which is the slowest part for long targets. FFmpeg
  can report real progress: add `-progress pipe:1 -nostats` and read
  `out_time_ms=` lines from stdout to drive the bar accurately.
- **No way to cancel, and closing the window orphans FFmpeg.** Use
  `subprocess.Popen` (kept as `self.current_proc`), add a Cancel button that
  terminates it, and hook `WM_DELETE_WINDOW` to kill any running process and
  clean up the temp dir before exit.

---

## Minor notes (not counted in the five)

- `cycle_dur = (clip_dur * 2) - cf` models one crossfade per cycle, but the join
  also crossfades *between* cycles — the loop count can end up one short for
  edge-case targets. Since the output is hard-trimmed anyway, simply generating
  one extra cycle (`loops_needed + 1`) guarantees enough material.
- In `_xfade_concat`, `dur` is probed from the stream-copied forward segment;
  container-level duration after `-c copy` can differ slightly from the encoded
  reverse segment, causing tiny freeze/jump artifacts at fade points.
- The `n == 1` branch of `_xfade_concat` returns the raw `-c copy` segment —
  fine today only because the final trim re-encodes; worth a comment.
- Consider a `requirements.txt`/`README.md` noting the FFmpeg dependency, and a
  check that the *saved* output path differs from the input path.
