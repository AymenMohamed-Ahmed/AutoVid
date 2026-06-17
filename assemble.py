#!/usr/bin/env python3
"""
Subscription-only manual kids' video assembler.

This is the ONLY automated step in the pipeline. Everything upstream
(research, scripting, translation, video clip generation, narration) is done
by hand inside the apps you already pay for:

    Perplexity Pro   -> trending topic brief        (manual, in-app)
    Gemini app       -> EN script + FR/ES translation (manual, in-app)
    Google Flow      -> Veo video clips              (manual, in-app)
    your voice / TTS -> narration .wav files         (manual)

This script touches NO paid services and makes NO network calls. It only
shells out to the free, local `ffmpeg` binary. See WORKFLOW.md for the full
manual checklist and README.md for setup.

What it does, per job:
  1. For each format (short = 9:16 1080x1920, long = 16:9 1920x1080):
       - find raw Veo clips named  {fmt}_1.mp4, {fmt}_2.mp4, ...  in raw/
       - concatenate them (ffmpeg concat demuxer) into one silent master
  2. For each language (en, fr, es):
       - mux the matching narration wav  audio/{fmt}_{lang}.wav
       - scale + pad to the exact target resolution (letterbox, centered)
       - burn in subtitles  subs/{fmt}_{lang}.srt  with a clean mobile style
       - encode libx264 / crf 20 / yuv420p, aac 128k, -shortest
       - write  final/{lang}_{fmt}.mp4
  3. Skip (loudly, never crash) any combo whose input files are missing.
  4. Print a summary of everything produced.

Usage:
    python assemble.py                # uses job-001
    python assemble.py job-002        # any job id under assets/
    python assemble.py --keep-intermediates
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

# Target geometry + per-format subtitle font size (px in the final frame).
FORMATS: dict[str, dict] = {
    "short": {"w": 1080, "h": 1920, "fontsize": 36},   # 9:16 vertical (mobile)
    "long":  {"w": 1920, "h": 1080, "fontsize": 28},   # 16:9 horizontal
}

LANGUAGES = ["en", "fr", "es"]

# Subtitle look. ASS colours are &HAABBGGRR (alpha-blue-green-red, 00 = opaque).
# Alignment=2 -> bottom-center.  BorderStyle=1 -> outline + drop shadow.
SUB_FONT = "Arial"
SUB_PRIMARY = "&H00FFFFFF"   # white fill
SUB_OUTLINE = "&H00000000"   # black outline
SUB_BACK = "&H64000000"      # translucent shadow
SUB_OUTLINE_W = 3
SUB_SHADOW = 1
SUB_MARGIN_V = 60            # gap from the bottom edge


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def info(msg: str) -> None:
    print(msg, flush=True)


def run_ffmpeg(cmd: list[str]) -> bool:
    """Run an ffmpeg command. Return True on success, False on failure.

    We never let a single bad encode kill the whole batch; we report and move
    on so the other languages/formats still get produced.
    """
    info("  $ " + " ".join(_quote(c) for c in cmd))
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        info(f"  [error] ffmpeg exited with code {exc.returncode}; skipping this output.")
        return False


def _quote(token: str) -> str:
    """Light shell-style quoting purely for readable logging (not for execution)."""
    return f'"{token}"' if " " in token else token


def find_raw_clips(raw_dir: Path, fmt: str) -> list[Path]:
    """Return clips named {fmt}_<n>.mp4 in ascending numeric order.

    Tolerates gaps in numbering (e.g. 1,2,4) and is case-insensitive.
    """
    pattern = re.compile(rf"^{re.escape(fmt)}_(\d+)\.mp4$", re.IGNORECASE)
    numbered: list[tuple[int, Path]] = []
    if raw_dir.is_dir():
        for p in raw_dir.iterdir():
            m = pattern.match(p.name)
            if m:
                numbered.append((int(m.group(1)), p))
    numbered.sort(key=lambda t: t[0])
    return [p for _, p in numbered]


def escape_subs_path(path: Path) -> str:
    r"""Escape a path for ffmpeg's `subtitles` filter.

    The filtergraph parser treats ':' as an option separator and '\' as an
    escape char, so on Windows a path like  C:\jobs\subs.srt  must become
        C\:\\jobs\\subs.srt
    i.e. double every backslash, then escape the drive-letter colon. After the
    filtergraph un-escapes it, libass receives the original literal path.
    On POSIX (no backslashes, no drive colon) this is effectively a no-op.
    """
    p = str(path.resolve())
    p = p.replace("\\", "\\\\")   # double the backslashes
    p = p.replace(":", "\\:")     # escape the drive-letter colon
    return p


def build_force_style(fontsize: int) -> str:
    """ASS force_style string: white text, black outline, bottom-centered."""
    return (
        f"FontName={SUB_FONT},"
        f"FontSize={fontsize},"
        f"PrimaryColour={SUB_PRIMARY},"
        f"OutlineColour={SUB_OUTLINE},"
        f"BackColour={SUB_BACK},"
        f"BorderStyle=1,"
        f"Outline={SUB_OUTLINE_W},"
        f"Shadow={SUB_SHADOW},"
        f"Alignment=2,"
        f"MarginV={SUB_MARGIN_V}"
    )


# --------------------------------------------------------------------------- #
# ffmpeg stages
# --------------------------------------------------------------------------- #

def concat_clips(clips: list[Path], out_path: Path) -> bool:
    """Concatenate clips into one silent master using the concat demuxer.

    Tries a fast stream copy first; if the clips have mismatched codecs/params
    and the copy fails, falls back to a normalizing re-encode.
    """
    # The concat demuxer reads a text file of `file '<path>'` lines.
    list_path = Path(tempfile.gettempdir()) / f"_concat_{out_path.stem}.txt"
    with list_path.open("w", encoding="utf-8") as fh:
        for c in clips:
            # Forward slashes are safe for ffmpeg on every OS; single quotes
            # in a path are escaped per the concat demuxer's '\'' convention.
            safe = str(c.resolve()).replace("\\", "/").replace("'", r"'\''")
            fh.write(f"file '{safe}'\n")

    base = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-an"]
    info(f"  concatenating {len(clips)} clip(s) -> {out_path.name}")
    ok = run_ffmpeg(base + ["-c", "copy", str(out_path)])
    if not ok:
        info("  [info] stream-copy concat failed (clips likely differ); re-encoding...")
        ok = run_ffmpeg(
            base + ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out_path)]
        )

    try:
        list_path.unlink()
    except OSError:
        pass
    return ok


def render_final(
    master: Path, audio: Path, srt: Path, out_path: Path, cfg: dict
) -> bool:
    """Scale+pad the master, mux narration, burn subtitles, encode the final."""
    style = build_force_style(cfg["fontsize"])
    subs = escape_subs_path(srt)
    vf = (
        f"scale={cfg['w']}:{cfg['h']}:force_original_aspect_ratio=decrease,"
        f"pad={cfg['w']}:{cfg['h']}:(ow-iw)/2:(oh-ih)/2,"
        f"subtitles={subs}:force_style='{style}'"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(master),        # 0: silent video master
        "-i", str(audio),         # 1: narration
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path),
    ]
    info(f"  rendering {out_path.name}")
    return run_ffmpeg(cmd)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def assemble(job_id: str, base_dir: Path, keep_intermediates: bool) -> list[Path]:
    job_dir = base_dir / "assets" / job_id
    raw_dir = job_dir / "raw"
    audio_dir = job_dir / "audio"
    subs_dir = job_dir / "subs"
    final_dir = job_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    if not job_dir.is_dir():
        info(f"[skip] Job folder not found: {job_dir}")
        info("       Create it and populate raw/ audio/ subs/ first (see WORKFLOW.md).")
        return []

    produced: list[Path] = []
    intermediates: list[Path] = []

    for fmt, cfg in FORMATS.items():
        info(f"\n=== format: {fmt}  ({cfg['w']}x{cfg['h']}) ===")
        clips = find_raw_clips(raw_dir, fmt)
        if not clips:
            info(f"[skip] No raw clips for '{fmt}'.")
            info(f"       Expected files like: {raw_dir / (fmt + '_1.mp4')}")
            continue
        info(f"  found {len(clips)} clip(s): {', '.join(c.name for c in clips)}")

        master = job_dir / f"_master_{fmt}.mp4"
        intermediates.append(master)
        if not concat_clips(clips, master):
            info(f"[skip] Could not build the {fmt} master video; skipping its languages.")
            continue

        for lang in LANGUAGES:
            audio = audio_dir / f"{fmt}_{lang}.wav"
            srt = subs_dir / f"{fmt}_{lang}.srt"

            missing = [p for p in (audio, srt) if not p.exists()]
            if missing:
                info(f"[skip] {fmt}/{lang}: missing required input(s):")
                for p in missing:
                    info(f"         wanted: {p}")
                continue

            out_path = final_dir / f"{lang}_{fmt}.mp4"
            if render_final(master, audio, srt, out_path, cfg):
                produced.append(out_path)

    if not keep_intermediates:
        for m in intermediates:
            try:
                if m.exists():
                    m.unlink()
            except OSError:
                pass

    return produced


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="assemble.py",
        description="Subscription-only manual kids' video assembler (ffmpeg only, no paid APIs).",
    )
    parser.add_argument(
        "job_id",
        nargs="?",
        default="job-001",
        help="Job id under assets/ (default: job-001)",
    )
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="Keep the per-format _master_*.mp4 concatenation files for debugging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if shutil.which("ffmpeg") is None:
        info("[fatal] `ffmpeg` was not found on your PATH.")
        info("        Install it (Windows):  winget install Gyan.FFmpeg")
        info("        Then open a new terminal so PATH refreshes, and re-run.")
        return 1

    base_dir = Path(__file__).resolve().parent
    info(f"Job: {args.job_id}")
    info(f"Assets: {base_dir / 'assets' / args.job_id}")

    produced = assemble(args.job_id, base_dir, args.keep_intermediates)

    info("\n" + "=" * 60)
    if produced:
        info(f"Done. Produced {len(produced)} final video(s):")
        for p in produced:
            info(f"  - {p}")
    else:
        info("Done, but no final videos were produced.")
        info("Check the [skip] messages above for the exact files that were missing.")
    info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
