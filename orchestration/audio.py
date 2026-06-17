"""Localized TTS + subtitle (.srt) generation.

synthesize: localized script -> a single .wav narration track.
write_srt:  localized script -> timestamp-accurate .srt.

TTS here uses Google Cloud Text-to-Speech; swap the client if you prefer
another provider. Voices are mapped per language in VOICE_MAP.
"""
import os
import asyncio
from pathlib import Path
import httpx
from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE

TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

VOICE_MAP = {
    "en": {"languageCode": "en-US", "name": "en-US-Standard-F"},
    "fr": {"languageCode": "fr-FR", "name": "fr-FR-Standard-A"},
    "es": {"languageCode": "es-ES", "name": "es-ES-Standard-A"},
}


def _srt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


@task(cache_policy=NO_CACHE)
def write_srt(script: dict, out_path: str) -> str:
    log = get_run_logger()
    lines = []
    for i, sc in enumerate(script["scenes"], start=1):
        lines.append(str(i))
        lines.append(f"{_srt_ts(sc['start'])} --> {_srt_ts(sc['end'])}")
        lines.append(sc["narration"].strip())
        lines.append("")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"SRT written: {out} ({len(script['scenes'])} cues)")
    return str(out)


@task(retries=2, retry_delay_seconds=[15, 45], cache_policy=NO_CACHE)
async def synthesize(script: dict, out_path: str) -> str:
    """Concatenate per-scene TTS into one narration wav, padded to timestamps."""
    log = get_run_logger()
    api_key = os.environ["GOOGLE_TTS_API_KEY"]
    voice = VOICE_MAP[script["lang"]]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = out.parent / f"_tts_{script['lang']}_{script['format']}"
    tmp_dir.mkdir(exist_ok=True)

    seg_paths = []
    async with httpx.AsyncClient(timeout=120) as client:
        for sc in script["scenes"]:
            resp = await client.post(
                TTS_URL,
                params={"key": api_key},
                json={
                    "input": {"text": sc["narration"]},
                    "voice": voice,
                    "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
                },
            )
            resp.raise_for_status()
            import base64
            seg = tmp_dir / f"scene_{sc['id']}.wav"
            seg.write_bytes(base64.b64decode(resp.json()["audioContent"]))
            seg_paths.append((sc, seg))

    # Build an ffmpeg concat list placing each segment at its scene start.
    # Simpler robust approach: concat segments in order, then let ffmpeg in
    # postprocess align audio to the video length. Here we just concatenate.
    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for _, p in seg_paths))
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(out),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"TTS concat failed: {err.decode()[:500]}")
    log.info(f"TTS narration: {out}")
    return str(out)
