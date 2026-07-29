"""
Boomerang Looper
- Loops video forward→reverse until target duration is reached
- Crossfade/overlap between segments (adjustable)
- Hard cut at exact target duration
- Real-time progress reporting, cancellable mid-run
- Output: MP4 H.264 (NVENC if available)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import subprocess
import threading
import os
import json
import tempfile
import shutil
from pathlib import Path
from typing import Any


class Cancelled(Exception):
    """Raised internally when the user cancels an in-progress job."""


def _subprocess_flags() -> dict[str, Any]:
    """Suppress the console window FFmpeg would otherwise flash on Windows."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def find_ffmpeg() -> str | None:
    dirs_to_check = []
    if hasattr(sys, "_MEIPASS"):
        dirs_to_check.append(getattr(sys, "_MEIPASS"))
    if getattr(sys, "frozen", False):
        dirs_to_check.append(os.path.dirname(sys.executable))
    dirs_to_check.append(os.path.dirname(os.path.abspath(__file__)))

    for d in dirs_to_check:
        p = os.path.join(d, "ffmpeg.exe") if os.name == "nt" else os.path.join(d, "ffmpeg")
        if os.path.isfile(p):
            return p

    for name in ("ffmpeg", "ffmpeg.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def find_ffprobe() -> str | None:
    dirs_to_check = []
    if hasattr(sys, "_MEIPASS"):
        dirs_to_check.append(getattr(sys, "_MEIPASS"))
    if getattr(sys, "frozen", False):
        dirs_to_check.append(os.path.dirname(sys.executable))
    dirs_to_check.append(os.path.dirname(os.path.abspath(__file__)))

    for d in dirs_to_check:
        p = os.path.join(d, "ffprobe.exe") if os.name == "nt" else os.path.join(d, "ffprobe")
        if os.path.isfile(p):
            return p

    for name in ("ffprobe", "ffprobe.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def get_video_duration(path: str) -> float:
    ffprobe = find_ffprobe()
    if not ffprobe:
        raise RuntimeError("ffprobe not found. Install FFmpeg and add it to PATH.")
    cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, **_subprocess_flags())
    except subprocess.CalledProcessError as e:
        detail = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"ffprobe failed to read '{Path(path).name}': {detail}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Could not parse ffprobe output for '{Path(path).name}'.")

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            dur = stream.get("duration")
            if dur:
                return float(dur)

    fmt_dur = data.get("format", {}).get("duration")
    if fmt_dur:
        return float(fmt_dur)

    raise RuntimeError(f"Could not determine duration for '{Path(path).name}'.")


def has_audio_stream(path: str) -> bool:
    ffprobe = find_ffprobe()
    if not ffprobe:
        return False
    cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, **_subprocess_flags())
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return False
    return any(s.get("codec_type") == "audio" for s in data.get("streams", []))


def has_nvenc() -> bool:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False
    # Seeing h264_nvenc in `-encoders` only means FFmpeg was compiled with
    # NVENC support.  It does not verify that the installed NVIDIA driver can
    # actually load the API required by this FFmpeg build.
    result = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=size=16x16:rate=1",
            "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        **_subprocess_flags(),
    )
    return result.returncode == 0


class BoomerangApp(tk.Tk):
    ACCENT  = "#7C3AED"
    ACCENT2 = "#A78BFA"
    BG      = "#0F0F13"
    PANEL   = "#1A1A24"
    BORDER  = "#2E2E42"
    TEXT    = "#E8E8F0"
    MUTED   = "#7070A0"
    ERROR   = "#EF4444"

    def __init__(self):
        super().__init__()
        self.title("Boomerang Looper")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self.geometry("560x780")

        self.input_path     = tk.StringVar()
        self.target_secs    = tk.StringVar(value="247")
        self.crossfade      = tk.StringVar(value="1.0")
        self.speed_val      = tk.StringVar(value="1.0")
        self.transition_val = tk.StringVar(value="fade")
        self.audio_path     = tk.StringVar()
        self.audio_mode     = tk.StringVar(value="keep")  # "keep", "replace", "mix"
        self.audio_fade     = tk.BooleanVar(value=True)

        self.status_text  = tk.StringVar(value="Choose a video to get started.")
        self.progress     = tk.DoubleVar(value=0.0)
        self.processing   = False
        self.cancel_requested = False
        self.current_proc = None

        self._build_ui()
        self._check_deps()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # header
        hdr = tk.Frame(self, bg=self.BG)
        hdr.pack(fill="x", padx=24, pady=(20, 0))
        tk.Label(hdr, text="⟳", font=("Segoe UI", 28), bg=self.BG, fg=self.ACCENT).pack(side="left", padx=(0, 10))
        tk.Label(hdr, text="Boomerang Looper", font=("Segoe UI", 20, "bold"), bg=self.BG, fg=self.TEXT).pack(side="left")

        tk.Label(self, text="Forward → Reverse, crossfaded and cut to exact length.",
                 font=("Segoe UI", 9), bg=self.BG, fg=self.MUTED).pack(anchor="w", padx=24, pady=(4, 14))

        # file picker
        drop_frame = tk.Frame(self, bg=self.PANEL, highlightbackground=self.BORDER,
                              highlightthickness=1, cursor="hand2")
        drop_frame.pack(fill="x", padx=24, pady=(0, 14))
        drop_frame.bind("<Button-1>", lambda e: self._browse())

        self.drop_icon = tk.Label(drop_frame, text="🎬", font=("Segoe UI", 24),
                                  bg=self.PANEL, fg=self.ACCENT2, cursor="hand2")
        self.drop_icon.pack(pady=(12, 2))
        self.drop_icon.bind("<Button-1>", lambda e: self._browse())

        self.drop_label = tk.Label(drop_frame, text="Click to choose a video file",
                                   font=("Segoe UI", 10), bg=self.PANEL, fg=self.MUTED, cursor="hand2")
        self.drop_label.pack(pady=(0, 4))
        self.drop_label.bind("<Button-1>", lambda e: self._browse())

        self.file_label = tk.Label(drop_frame, textvariable=self.input_path,
                                   font=("Segoe UI", 8), bg=self.PANEL, fg=self.ACCENT2, wraplength=480)
        self.file_label.pack(pady=(0, 10))

        # ── settings row 1 (Duration & Crossfade) ──
        settings = tk.Frame(self, bg=self.BG)
        settings.pack(fill="x", padx=24, pady=(0, 14))
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=1)

        # target duration
        left = tk.Frame(settings, bg=self.BG)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 12))

        tk.Label(left, text="Target duration", font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=self.TEXT).pack(anchor="w")
        tk.Label(left, text="Exact cut-off in seconds\n(e.g. 247 for a 4m07s song)",
                 font=("Segoe UI", 8), bg=self.BG, fg=self.MUTED, justify="left").pack(anchor="w", pady=(2, 6))

        dur_row = tk.Frame(left, bg=self.BG)
        dur_row.pack(anchor="w")
        self.dur_entry = tk.Entry(dur_row, textvariable=self.target_secs,
                                  width=7, font=("Segoe UI", 13, "bold"),
                                  bg=self.PANEL, fg=self.ACCENT2,
                                  insertbackground=self.TEXT, relief="flat",
                                  highlightbackground=self.BORDER, highlightthickness=1)
        self.dur_entry.pack(side="left", padx=(0, 6))
        tk.Label(dur_row, text="sec", font=("Segoe UI", 9), bg=self.BG, fg=self.MUTED).pack(side="left")

        # quick presets
        presets = tk.Frame(left, bg=self.BG)
        presets.pack(anchor="w", pady=(6, 0))
        for label, val in [("30s", "30"), ("60s", "60"), ("3m", "180"), ("4m07s", "247")]:
            tk.Button(presets, text=label, font=("Segoe UI", 8),
                      bg=self.BORDER, fg=self.TEXT,
                      activebackground=self.ACCENT, activeforeground="white",
                      relief="flat", padx=6, pady=2, cursor="hand2",
                      command=lambda v=val: self.target_secs.set(v)).pack(side="left", padx=(0, 4))

        # crossfade
        right = tk.Frame(settings, bg=self.BG)
        right.grid(row=0, column=1, sticky="nw")

        tk.Label(right, text="Crossfade overlap", font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=self.TEXT).pack(anchor="w")
        tk.Label(right, text="Blend duration between\nforward and reverse segments",
                 font=("Segoe UI", 8), bg=self.BG, fg=self.MUTED, justify="left").pack(anchor="w", pady=(2, 6))

        cf_row = tk.Frame(right, bg=self.BG)
        cf_row.pack(anchor="w")
        self.cf_entry = tk.Entry(cf_row, textvariable=self.crossfade,
                                 width=5, font=("Segoe UI", 13, "bold"),
                                 bg=self.PANEL, fg=self.ACCENT2,
                                 insertbackground=self.TEXT, relief="flat",
                                 highlightbackground=self.BORDER, highlightthickness=1)
        self.cf_entry.pack(side="left", padx=(0, 6))
        tk.Label(cf_row, text="sec", font=("Segoe UI", 9), bg=self.BG, fg=self.MUTED).pack(side="left")

        cf_presets = tk.Frame(right, bg=self.BG)
        cf_presets.pack(anchor="w", pady=(6, 0))
        for label, val in [("0.5", "0.5"), ("1.0", "1.0"), ("2.0", "2.0"), ("none", "0")]:
            tk.Button(cf_presets, text=label, font=("Segoe UI", 8),
                      bg=self.BORDER, fg=self.TEXT,
                      activebackground=self.ACCENT, activeforeground="white",
                      relief="flat", padx=6, pady=2, cursor="hand2",
                      command=lambda v=val: self.crossfade.set(v)).pack(side="left", padx=(0, 4))

        # ── settings row 2 (Speed & Transition style) ──
        settings2 = tk.Frame(self, bg=self.BG)
        settings2.pack(fill="x", padx=24, pady=(0, 14))
        settings2.columnconfigure(0, weight=1)
        settings2.columnconfigure(1, weight=1)

        # speed
        s_left = tk.Frame(settings2, bg=self.BG)
        s_left.grid(row=0, column=0, sticky="nw", padx=(0, 12))

        tk.Label(s_left, text="Playback speed", font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=self.TEXT).pack(anchor="w")
        tk.Label(s_left, text="Slow-mo or fast-forward",
                 font=("Segoe UI", 8), bg=self.BG, fg=self.MUTED).pack(anchor="w", pady=(2, 6))

        speed_combo = ttk.Combobox(
            s_left, textvariable=self.speed_val,
            values=["0.5", "0.75", "1.0", "1.25", "1.5", "2.0"],
            state="readonly", width=12, font=("Segoe UI", 9)
        )
        speed_combo.pack(anchor="w")

        # transition effect
        s_right = tk.Frame(settings2, bg=self.BG)
        s_right.grid(row=0, column=1, sticky="nw")

        tk.Label(s_right, text="Transition effect", font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=self.TEXT).pack(anchor="w")
        tk.Label(s_right, text="Crossfade transition style",
                 font=("Segoe UI", 8), bg=self.BG, fg=self.MUTED).pack(anchor="w", pady=(2, 6))

        xfade_combo = ttk.Combobox(
            s_right, textvariable=self.transition_val,
            values=["fade", "wipeleft", "wiperight", "slideup", "slidedown", "circlecrop", "radial", "zoomIn", "pixelize", "dissolve"],
            state="readonly", width=14, font=("Segoe UI", 9)
        )
        xfade_combo.pack(anchor="w")

        # ── Audio / Music track section ──
        audio_panel = tk.Frame(self, bg=self.PANEL, highlightbackground=self.BORDER, highlightthickness=1)
        audio_panel.pack(fill="x", padx=24, pady=(0, 16))

        aud_hdr = tk.Frame(audio_panel, bg=self.PANEL)
        aud_hdr.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(aud_hdr, text="🎵  Audio / Music Track", font=("Segoe UI", 10, "bold"),
                 bg=self.PANEL, fg=self.TEXT).pack(side="left")

        aud_row = tk.Frame(audio_panel, bg=self.PANEL)
        aud_row.pack(fill="x", padx=12, pady=(0, 6))

        self.aud_lbl = tk.Label(aud_row, text="No custom audio track (using video audio)",
                                font=("Segoe UI", 8), bg=self.PANEL, fg=self.MUTED, anchor="w", wraplength=380)
        self.aud_lbl.pack(side="left", fill="x", expand=True)

        tk.Button(aud_row, text="Browse…", font=("Segoe UI", 8), bg=self.BORDER, fg=self.TEXT,
                  activebackground=self.ACCENT, activeforeground="white", relief="flat",
                  padx=8, pady=2, cursor="hand2", command=self._browse_audio).pack(side="right")

        aud_opts = tk.Frame(audio_panel, bg=self.PANEL)
        aud_opts.pack(fill="x", padx=12, pady=(0, 10))

        tk.Radiobutton(aud_opts, text="Keep original", variable=self.audio_mode, value="keep",
                       bg=self.PANEL, fg=self.TEXT, selectcolor=self.BG, activebackground=self.PANEL,
                       font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
        tk.Radiobutton(aud_opts, text="Replace audio", variable=self.audio_mode, value="replace",
                       bg=self.PANEL, fg=self.TEXT, selectcolor=self.BG, activebackground=self.PANEL,
                       font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
        tk.Radiobutton(aud_opts, text="Mix with original", variable=self.audio_mode, value="mix",
                       bg=self.PANEL, fg=self.TEXT, selectcolor=self.BG, activebackground=self.PANEL,
                       font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))

        tk.Checkbutton(aud_opts, text="Fade out at end (2s)", variable=self.audio_fade,
                       bg=self.PANEL, fg=self.TEXT, selectcolor=self.BG, activebackground=self.PANEL,
                       font=("Segoe UI", 8)).pack(side="right")

        # progress
        prog_frame = tk.Frame(self, bg=self.BG)
        prog_frame.pack(fill="x", padx=24, pady=(0, 12))

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Boom.Horizontal.TProgressbar",
                        troughcolor=self.PANEL, background=self.ACCENT,
                        bordercolor=self.BORDER, lightcolor=self.ACCENT,
                        darkcolor=self.ACCENT, thickness=8)

        self.prog_bar = ttk.Progressbar(prog_frame, variable=self.progress,
                                        maximum=100, mode="determinate",
                                        style="Boom.Horizontal.TProgressbar")
        self.prog_bar.pack(fill="x", pady=(0, 6))

        self.status_lbl = tk.Label(prog_frame, textvariable=self.status_text,
                                   font=("Segoe UI", 8), bg=self.BG, fg=self.MUTED, anchor="w")
        self.status_lbl.pack(fill="x")

        # run / cancel button
        self.run_btn = tk.Button(
            self, text="▶  Create Boomerang",
            font=("Segoe UI", 12, "bold"),
            bg=self.ACCENT, fg="white",
            activebackground=self.ACCENT2, activeforeground="white",
            relief="flat", padx=0, pady=10, cursor="hand2",
            command=self._on_run_button
        )
        self.run_btn.pack(fill="x", padx=24, pady=(0, 20))

    def _check_deps(self):
        if not find_ffmpeg():
            self._set_status("⚠  FFmpeg not found on PATH — please install it.", error=True)
            self.run_btn.config(state="disabled")

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select a video",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("All files", "*.*")]
        )
        if path:
            self.input_path.set(path)
            self.drop_label.config(text=Path(path).name, fg=self.TEXT)
            self.drop_icon.config(text="✅")
            self._set_status(f"Ready — {Path(path).name}")

    def _browse_audio(self):
        path = filedialog.askopenfilename(
            title="Select audio track",
            filetypes=[("Audio files", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma"), ("All files", "*.*")]
        )
        if path:
            self.audio_path.set(path)
            self.aud_lbl.config(text=Path(path).name, fg=self.ACCENT2)
            if self.audio_mode.get() == "keep":
                self.audio_mode.set("replace")
        else:
            self.audio_path.set("")
            self.aud_lbl.config(text="No custom audio track (using video audio)", fg=self.MUTED)
            self.audio_mode.set("keep")

    # ── thread-safe UI helpers ──
    def _set_status(self, msg: str, error=False):
        def apply():
            self.status_text.set(msg)
            self.status_lbl.config(fg=self.ERROR if error else self.MUTED)
        self.after(0, apply)

    def _set_progress(self, pct: float):
        pct = max(0.0, min(100.0, pct))
        self.after(0, lambda: self.progress.set(pct))

    def _on_run_button(self):
        if self.processing:
            self._cancel()
        else:
            self._start()

    def _cancel(self):
        if not self.processing or self.cancel_requested:
            return
        self.cancel_requested = True
        self._set_status("Cancelling…")
        self.run_btn.config(state="disabled", text="Cancelling…")
        proc = self.current_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _on_close(self):
        if self.processing:
            if not messagebox.askyesno("Cancel and quit?",
                                        "Boomerang creation is still in progress.\nCancel and quit?"):
                return
            self.cancel_requested = True
            proc = self.current_proc
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        self.destroy()

    def _reset_run_button(self):
        self.run_btn.config(state="normal", text="▶  Create Boomerang", bg=self.ACCENT)

    def _start(self):
        src = self.input_path.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror("No file", "Please select a valid video file first.")
            return
        if self.processing:
            return

        try:
            target = float(self.target_secs.get())
        except (TypeError, ValueError):
            messagebox.showerror("Invalid input", "Target duration must be a valid number.")
            return
        try:
            cf = float(self.crossfade.get())
        except (TypeError, ValueError):
            messagebox.showerror("Invalid input", "Crossfade must be a valid number.")
            return
        if target <= 0:
            messagebox.showerror("Invalid input", "Target duration must be greater than 0.")
            return
        if cf < 0:
            messagebox.showerror("Invalid input", "Crossfade cannot be negative.")
            return

        try:
            speed = float(self.speed_val.get())
            if speed <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            messagebox.showerror("Invalid input", "Speed must be a positive number (e.g. 1.0, 0.5, 2.0).")
            return

        transition = self.transition_val.get().strip() or "fade"
        audio_file = self.audio_path.get().strip()
        audio_mode = self.audio_mode.get()
        fade_audio = self.audio_fade.get()

        if audio_file and not os.path.isfile(audio_file):
            messagebox.showerror("Invalid audio file", "The selected audio file could not be found.")
            return

        out_path = filedialog.asksaveasfilename(
            title="Save boomerang as…",
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4")],
            initialfile=Path(src).stem + "_boomerang.mp4"
        )
        if not out_path:
            return
        if os.path.abspath(out_path) == os.path.abspath(src):
            messagebox.showerror("Invalid output", "Output file must be different from the input file.")
            return

        self.processing = True
        self.cancel_requested = False
        self.run_btn.config(state="normal", text="⏹  Cancel", bg=self.ERROR)
        self.progress.set(0)

        t = threading.Thread(
            target=self._process,
            args=(src, out_path, target, cf, speed, transition, audio_file, audio_mode, fade_audio),
            daemon=True
        )
        t.start()

    def _run_ffmpeg(self, args: list, step_name: str,
                     duration: float | None = None,
                     start_pct: float | None = None,
                     end_pct: float | None = None) -> None:
        """
        Run an FFmpeg command. If duration/start_pct/end_pct are given, streams
        real progress via `-progress pipe:1` and maps it onto that pct range.
        Stores the live Popen on self.current_proc so Cancel can terminate it.
        """
        if self.cancel_requested:
            raise Cancelled()

        track_progress = duration is not None and start_pct is not None and end_pct is not None
        cmd = list(args)
        if track_progress:
            cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]

        stderr_buf = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE if track_progress else subprocess.DEVNULL,
                stderr=stderr_buf,
                text=True,
                **_subprocess_flags(),
            )
            self.current_proc = proc
            try:
                if track_progress:
                    assert duration is not None and start_pct is not None and end_pct is not None
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        if self.cancel_requested:
                            break
                        line = line.strip()
                        if line.startswith("out_time_ms="):
                            try:
                                out_ms = int(line.split("=", 1)[1])
                                frac = min(1.0, max(0.0, (out_ms / 1_000_000) / duration))
                                self._set_progress(start_pct + frac * (end_pct - start_pct))
                            except ValueError:
                                pass
                    proc.stdout.close()
                returncode = proc.wait()
            finally:
                self.current_proc = None

            if self.cancel_requested:
                raise Cancelled()

            if returncode != 0:
                stderr_buf.seek(0)
                err = stderr_buf.read()[-600:]
                raise RuntimeError(f"FFmpeg failed while {step_name}:\n{err.strip()}")

            if track_progress:
                assert end_pct is not None
                self._set_progress(end_pct)
        finally:
            stderr_buf.close()

    def _process(self, src: str, out: str, target: float, cf: float,
                 speed: float, transition: str, audio_file: str,
                 audio_mode: str, fade_audio: bool):
        tmpdir = tempfile.mkdtemp(prefix="boomerang_")
        try:
            self._set_status("Analysing source video…")
            clip_dur = get_video_duration(src)
            have_video_audio = has_audio_stream(src)
            self._set_progress(5)

            effective_clip_dur = clip_dur / speed

            has_custom_audio = bool(audio_file and os.path.isfile(audio_file))
            if has_custom_audio and audio_mode == "replace":
                seg_has_audio = False
            else:
                seg_has_audio = have_video_audio

            cycle_dur = (effective_clip_dur * 2) - cf if cf > 0 else effective_clip_dur * 2
            if cycle_dur <= 0:
                raise ValueError("Crossfade is longer than segment duration — reduce crossfade or increase duration.")

            loops_needed = max(1, int(-(-target // cycle_dur))) + 1

            ffmpeg    = find_ffmpeg()
            use_nvenc = has_nvenc()
            encoder   = "h264_nvenc" if use_nvenc else "libx264"

            compat = [
                "-pix_fmt", "yuv420p",
                "-profile:v", "high",
                "-level", "4.1",
                "-movflags", "+faststart",
            ]

            def enc_args():
                if use_nvenc:
                    return ["-c:v", encoder, "-preset", "p4", "-rc", "vbr", "-cq", "23"] + compat
                return ["-c:v", encoder, "-preset", "fast", "-crf", "23"] + compat

            fwd = os.path.join(tmpdir, "fwd.mp4")
            rev = os.path.join(tmpdir, "rev.mp4")

            self._set_status("Creating forward segment…")
            if speed == 1.0:
                self._run_ffmpeg([ffmpeg, "-y", "-i", src, "-c", "copy", fwd],
                                  "copying the forward segment")
            else:
                fwd_cmd = [ffmpeg, "-y", "-i", src, "-vf", f"setpts={(1/speed):.4f}*PTS"]
                if seg_has_audio:
                    fwd_cmd += ["-af", f"atempo={speed:.4f}"]
                else:
                    fwd_cmd += ["-an"]
                fwd_cmd += enc_args() + [fwd]
                self._run_ffmpeg(fwd_cmd, "encoding speed-adjusted forward segment")
            self._set_progress(10)

            self._set_status("Encoding reverse segment…")
            if speed == 1.0:
                rev_cmd = [ffmpeg, "-y", "-i", src, "-vf", "reverse"]
                rev_cmd += ["-af", "areverse"] if seg_has_audio else ["-an"]
            else:
                rev_cmd = [ffmpeg, "-y", "-i", src, "-vf", f"reverse,setpts={(1/speed):.4f}*PTS"]
                rev_cmd += ["-af", f"areverse,atempo={speed:.4f}"] if seg_has_audio else ["-an"]
            rev_cmd += enc_args() + [rev]
            self._run_ffmpeg(rev_cmd, "reversing the clip",
                              duration=clip_dur, start_pct=10, end_pct=50)

            segments = [fwd, rev] * loops_needed
            join_estimated_dur = cycle_dur * loops_needed + effective_clip_dur

            self._set_status(f"Joining {loops_needed} loop(s)…")

            if cf > 0:
                joined = self._xfade_concat(
                    ffmpeg, tmpdir, segments, cf, enc_args, seg_has_audio,
                    seg_dur=effective_clip_dur, transition=transition,
                    progress_duration=join_estimated_dur,
                    start_pct=50, end_pct=90,
                )
            else:
                list_path = os.path.join(tmpdir, "concat.txt")
                with open(list_path, "w") as f:
                    for seg in segments:
                        f.write(f"file '{seg}'\n")
                joined = os.path.join(tmpdir, "joined.mp4")
                concat_cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path] + enc_args()
                concat_cmd += ["-c:a", "aac", "-b:a", "192k"] if seg_has_audio else ["-an"]
                concat_cmd += [joined]
                self._run_ffmpeg(concat_cmd, "joining segments",
                                  duration=join_estimated_dur, start_pct=50, end_pct=90)

            self._set_status(f"Trimming to {target}s & processing audio…")
            trim_cmd = [ffmpeg, "-y", "-i", joined]

            if has_custom_audio and audio_mode == "replace":
                trim_cmd += ["-stream_loop", "-1", "-i", audio_file, "-t", str(target), "-map", "0:v:0", "-map", "1:a:0"]
                trim_cmd += enc_args()
                if fade_audio:
                    fade_st = max(0.0, target - 2.0)
                    trim_cmd += ["-af", f"afade=t=out:st={fade_st:.2f}:d=2", "-c:a", "aac", "-b:a", "192k"]
                else:
                    trim_cmd += ["-c:a", "aac", "-b:a", "192k"]

            elif has_custom_audio and audio_mode == "mix":
                if seg_has_audio:
                    trim_cmd += ["-stream_loop", "-1", "-i", audio_file, "-t", str(target)]
                    trim_cmd += enc_args()
                    fade_str = f",afade=t=out:st={max(0.0, target - 2.0):.2f}:d=2" if fade_audio else ""
                    filter_complex = f"[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2{fade_str}[aout]"
                    trim_cmd += ["-filter_complex", filter_complex, "-map", "0:v:0", "-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
                else:
                    trim_cmd += ["-stream_loop", "-1", "-i", audio_file, "-t", str(target), "-map", "0:v:0", "-map", "1:a:0"]
                    trim_cmd += enc_args()
                    if fade_audio:
                        fade_st = max(0.0, target - 2.0)
                        trim_cmd += ["-af", f"afade=t=out:st={fade_st:.2f}:d=2", "-c:a", "aac", "-b:a", "192k"]
                    else:
                        trim_cmd += ["-c:a", "aac", "-b:a", "192k"]

            else:
                trim_cmd += ["-t", str(target)] + enc_args()
                if seg_has_audio:
                    if fade_audio:
                        fade_st = max(0.0, target - 2.0)
                        trim_cmd += ["-af", f"afade=t=out:st={fade_st:.2f}:d=2", "-c:a", "aac", "-b:a", "192k"]
                    else:
                        trim_cmd += ["-c:a", "aac", "-b:a", "192k"]
                else:
                    trim_cmd += ["-an"]

            trim_cmd += [out]
            self._run_ffmpeg(trim_cmd, "final export and audio processing",
                              duration=target, start_pct=90, end_pct=99)

            self._set_progress(100)
            aud_info = f"Audio: {audio_mode.title()}" if has_custom_audio else "Audio: Original"
            self._set_status(f"✅  Done — {Path(out).name}  (exactly {target}s, {loops_needed} loops)")
            self.after(0, lambda: messagebox.showinfo(
                "Done!",
                f"Boomerang created!\n\n"
                f"Loops: {loops_needed}×  (fwd + rev)\n"
                f"Crossfade: {cf}s ({transition})\n"
                f"Speed: {speed}x\n"
                f"{aud_info}\n"
                f"Output length: exactly {target}s\n"
                f"Encoder: {encoder}\n\n"
                f"Saved to:\n{out}"
            ))

        except Cancelled:
            self._set_status("Cancelled.")
        except RuntimeError as e:
            self._set_status("❌  FFmpeg error.", error=True)
            self.after(0, lambda: messagebox.showerror("FFmpeg error", str(e)))
        except Exception as e:
            self._set_status(f"❌  {e}", error=True)
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.processing = False
            self.cancel_requested = False
            self.current_proc = None
            self.after(0, self._reset_run_button)

    def _xfade_concat(self, ffmpeg, tmpdir, segments, cf, enc_args_fn, have_audio,
                       seg_dur, transition, progress_duration, start_pct, end_pct):
        """
        Chain N segments together with FFmpeg's xfade/acrossfade filters.
        `seg_dur` is the known duration of each individual segment.
        Returns path to the joined file.
        """
        n = len(segments)
        out = os.path.join(tmpdir, "joined.mp4")

        inputs = []
        for seg in segments:
            inputs += ["-i", seg]

        vparts = [f"[{i}:v]" for i in range(n)]
        aparts = [f"[{i}:a]" for i in range(n)]

        filter_lines = []
        v_cur = vparts[0]
        a_cur = aparts[0] if have_audio else None
        cumulative = seg_dur

        for i in range(1, n):
            offset = max(0.01, cumulative - cf)
            v_out = f"[vx{i}]"
            filter_lines.append(
                f"{v_cur}{vparts[i]}xfade=transition={transition}:duration={cf}:offset={offset:.3f}{v_out}"
            )
            v_cur = v_out
            if have_audio:
                a_out = f"[ax{i}]"
                filter_lines.append(f"{a_cur}{aparts[i]}acrossfade=d={cf}{a_out}")
                a_cur = a_out
            cumulative += seg_dur - cf

        filter_complex = ";".join(filter_lines)

        cmd = [ffmpeg, "-y"] + inputs + ["-filter_complex", filter_complex, "-map", v_cur]
        if have_audio:
            cmd += ["-map", a_cur]
        cmd += enc_args_fn()
        cmd += ["-c:a", "aac", "-b:a", "192k"] if have_audio else ["-an"]
        cmd += [out]

        self._run_ffmpeg(cmd, "joining segments (crossfade)",
                          duration=progress_duration, start_pct=start_pct, end_pct=end_pct)
        return out


if __name__ == "__main__":
    app = BoomerangApp()
    app.mainloop()

