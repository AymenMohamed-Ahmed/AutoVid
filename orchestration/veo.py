"""Gemini Veo generation with a deterministic consistency matrix.

Each shot prompt is assembled from the character bible + a job-locked seed so
re-renders are visually identical. Visuals are language-agnostic and rendered
once from the EN master.
"""
import os
import json
import hashlib
import asyncio
from pathlib import Path
import httpx
from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE

VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.0-generate-preview")
BASE = "https://generativelanguage.googleapis.com/v1beta"

_VEO_SEM = asyncio.Semaphore(int(os.getenv("VEO_CONCURRENCY", "2")))

_BIBLE = json.loads(Path("prompts/character_bible.json").read_text())


def job_seed(job_id: str, character: str) -> int:
    """Deterministic per-(job, character) seed so all shots stay consistent."""
    h = hashlib.sha256(f"{job_id}:{character}".encode()).hexdigest()
    return int(h[:8], 16)


def build_prompt(scene: dict, character: str, fmt: str) -> str:
    bible = _BIBLE
    ch = bible["characters"][character]
    style = bible["art_style"]
    palette = bible["color_palette"]
    descriptor = (
        f"{character}, a {ch['species']} with {ch['fur']} fur, "
        f"{ch['eyes']} eyes, wearing a {ch['outfit']}, {ch['proportions']}."
    )
    aspect = "9:16 vertical" if fmt == "short" else "16:9 horizontal"
    return (
        f"{style['base']}. {style['render_quality']}. "
        f"Dominant colors {palette['primary']}, {palette['secondary']}, "
        f"{palette['accent']}. {aspect} framing. "
        f"CHARACTER (keep identical every shot): {descriptor} "
        f"SCENE: {scene['visual']} "
        f"NEGATIVE: {style['negative']}."
    )


@task(retries=2, retry_delay_seconds=[60, 180], timeout_seconds=1800,
      cache_policy=NO_CACHE)
async def render_shot(scene: dict, character: str, fmt: str,
                      job_id: str, out_path: str) -> str:
    log = get_run_logger()
    api_key = os.environ["GEMINI_API_KEY"]
    seed = job_seed(job_id, character)
    prompt = build_prompt(scene, character, fmt)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    async with _VEO_SEM:
        async with httpx.AsyncClient(timeout=120) as client:
            start = await client.post(
                f"{BASE}/models/{VEO_MODEL}:predictLongRunning",
                params={"key": api_key},
                json={
                    "instances": [{"prompt": prompt}],
                    "parameters": {
                        "aspectRatio": "9:16" if fmt == "short" else "16:9",
                        "seed": seed,
                        "personGeneration": "dont_allow",
                    },
                },
            )
            start.raise_for_status()
            op_name = start.json()["name"]

            # Poll with a hard ceiling; TimeoutError -> Prefect retry (same seed).
            max_wait, waited, interval = 1500, 0, 15
            while True:
                await asyncio.sleep(interval)
                waited += interval
                poll = await client.get(f"{BASE}/{op_name}", params={"key": api_key})
                poll.raise_for_status()
                body = poll.json()
                if body.get("done"):
                    break
                if waited >= max_wait:
                    raise TimeoutError(f"Veo render exceeded {max_wait}s for scene {scene['id']}")

            resp = body["response"]
            uri = resp["generatedVideos"][0]["video"]["uri"]
            dl = await client.get(uri, params={"key": api_key}, timeout=300)
            dl.raise_for_status()
            out.write_bytes(dl.content)

    log.info(f"Rendered scene {scene['id']} (seed={seed}) -> {out}")
    return str(out)
