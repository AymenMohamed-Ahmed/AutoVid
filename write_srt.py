#!/usr/bin/env python3
"""
SRT helper: turn a simple JSON script into a valid .srt subtitle file.

You paste your Gemini-translated script (per format, per language) into a small
JSON file and this turns it into subtitles without you ever hand-writing SRT.

Expected JSON (minimum):
    {
      "scenes": [
        {"id": 1, "start": 0.0,  "end": 11.0, "narration": "Hi, I'm Mimi!"},
        {"id": 2, "start": 11.0, "end": 23.0, "narration": "Let's explore."}
      ]
    }

- `start` / `end` may be seconds (numbers like 11 or 11.5) OR timestamp
  strings ("00:00:11,000" or "00:00:11.000"). Mixed is fine.
- Extra keys per scene (e.g. "visual") are ignored.
- If your file nests formats, e.g. {"short": {"scenes": [...]},
  "long": {"scenes": [...]}}, pass --section short / --section long.

Usage:
    python write_srt.py script_short_en.json subs/short_en.srt
    python write_srt.py script.json subs/long_fr.srt --section long
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def format_timestamp(value) -> str:
    """Return an SRT timestamp 'HH:MM:SS,mmm' from seconds or a time string."""
    if isinstance(value, (int, float)):
        if value < 0:
            value = 0.0
        total_ms = int(round(float(value) * 1000))
        hours, total_ms = divmod(total_ms, 3_600_000)
        minutes, total_ms = divmod(total_ms, 60_000)
        seconds, millis = divmod(total_ms, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    s = str(value).strip().replace(".", ",")
    # Accept "M:SS" / "MM:SS" / "HH:MM:SS" with optional ",mmm".
    if "," in s:
        clock, ms = s.split(",", 1)
        ms = (ms + "000")[:3]
    else:
        clock, ms = s, "000"
    parts = clock.split(":")
    if len(parts) == 2:
        parts = ["0"] + parts
    if len(parts) != 3:
        raise ValueError(f"Cannot parse timestamp: {value!r}")
    h, m, sec = (int(p) for p in parts)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms}"


def build_srt(scenes: list[dict]) -> str:
    """Build SRT text from a list of scene dicts."""
    blocks: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        if "start" not in scene or "end" not in scene:
            raise ValueError(f"Scene #{index} is missing 'start' or 'end': {scene!r}")
        text = str(scene.get("narration", "")).strip()
        start = format_timestamp(scene["start"])
        end = format_timestamp(scene["end"])
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")
    # Trailing newline; CRLF is the most broadly compatible SRT line ending.
    return "\n".join(blocks).replace("\n", "\r\n") + "\r\n"


def write_srt(script: dict, out_path: str | Path, section: str | None = None) -> Path:
    """Write `script` (or script[section]) to an .srt file. Returns the path."""
    data = script[section] if section else script
    if "scenes" not in data:
        where = f"section '{section}'" if section else "top level"
        raise KeyError(f"No 'scenes' key found at {where} of the JSON.")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_srt(data["scenes"]), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="write_srt.py",
        description="Convert a simple JSON script into a valid .srt subtitle file.",
    )
    parser.add_argument("input_json", help="Path to the script JSON.")
    parser.add_argument("output_srt", help="Path to write the .srt file.")
    parser.add_argument(
        "--section",
        default=None,
        help="If the JSON nests formats, the key to use (e.g. short, long).",
    )
    args = parser.parse_args(argv)

    script = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    out = write_srt(script, args.output_srt, args.section)
    n = len(json.loads(json.dumps(script))[args.section]["scenes"]) if args.section else len(script["scenes"])
    print(f"Wrote {out}  ({n} cue(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
