"""ffmpeg post-processing: concat shots -> mux narration -> scale -> burn subs.

Produces assets/{job_id}/final/{lang}_{format}.mp4 with hardcoded subtitles.
"""
import asyncio
from pathlib import Path
from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE

SCALE = {  # target WxH per format
    "short": "1080:1920",
    "long": "1920:1080",
}

# Styled, burned-in subtitle look (libass force_style).
SUB_STYLE = (
    "FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
    "Alignment=2,MarginV=60"
)


async def _run(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(args[:3])} ...\n{err.decode()[:800]}")


@task(retries=1, retry_delay_seconds=30, cache_policy=NO_CACHE)
async def concat_shots(shot_paths: list[str], out_path: str) -> str:
    """Concatenate raw Veo clips (same codec) into one silent video."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    listf = out.parent / f"{out.stem}_concat.txt"
    listf.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in shot_paths))
    await _run("ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", str(listf), "-c", "copy", str(out))
    return str(out)


@task(retries=1, retry_delay_seconds=30, cache_policy=NO_CACHE)
async def finalize(video: str, narration_wav: str, srt: str,
                   fmt: str, out_path: str) -> str:
    """Scale to the target aspect, mux narration, burn styled subtitles."""
    log = get_run_logger()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wh = SCALE[fmt]
    w, h = wh.split(":")
    # Escape the srt path for the subtitles filter (colons/backslashes on Win).
    srt_arg = srt.replace("\\", "/").replace(":", "\\:")
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
        f"subtitles='{srt_arg}':force_style='{SUB_STYLE}'"
    )
    await _run(
        "ffmpeg", "-y",
        "-i", video,
        "-i", narration_wav,
        "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-pix_fmt", "yuv420p",
        str(out),
    )
    log.info(f"Final render: {out}")
    return str(out)
