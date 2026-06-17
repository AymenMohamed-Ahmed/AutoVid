"""Scripting + multilingual localization via Gemini Advanced.

write_script: brief -> master script (scene list with timestamps) for a format.
localize:     master script -> per-language localized script, timestamps preserved.
"""
import os
import json
import asyncio
from pathlib import Path
import httpx
from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# Shared semaphore so script + localize never exceed Gemini concurrency quota.
_GEMINI_SEM = asyncio.Semaphore(int(os.getenv("GEMINI_CONCURRENCY", "3")))

FORMAT_SPEC = {
    "short": {"aspect": "9:16", "target_seconds": 45, "scenes": 4},
    "long": {"aspect": "16:9", "target_seconds": 180, "scenes": 8},
}


def _strip_fences(text: str) -> str:
    return text.replace("```json", "").replace("```", "").strip()


async def _gemini(prompt: str, temperature: float = 0.7) -> str:
    api_key = os.environ["GEMINI_API_KEY"]
    async with _GEMINI_SEM:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                GEMINI_URL,
                params={"key": api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature},
                },
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "30"))
                await asyncio.sleep(retry_after)
            resp.raise_for_status()
            data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


SCRIPT_PROMPT = """You are a children's animation scriptwriter (ages 3-7).
Using this research brief, write a {fmt} script ({seconds}s, {scenes} scenes).

Brief:
{brief}

Return STRICT JSON only (no markdown fences):
{{
  "lang": "en",
  "format": "{fmt}",
  "title": "string",
  "scenes": [
    {{
      "id": 1,
      "start": 0.0,            // seconds
      "end": 0.0,             // seconds
      "narration": "string",  // spoken line, EN
      "visual": "string"      // what is on screen this scene
    }}
  ]
}}
Keep timestamps contiguous and ending at ~{seconds}s. Warm, simple language.
"""

LOCALIZE_PROMPT = """Translate and culturally localize this children's script
into {lang_name} for ages 3-7. Preserve EVERY scene's id, start, and end
timestamps EXACTLY. Adapt idioms naturally; keep it age-appropriate.

Source script JSON:
{script}

Return STRICT JSON only (no markdown fences), same structure, with "lang"
set to "{lang}" and narration translated. Do NOT change timestamps.
"""

LANG_NAMES = {"en": "English", "fr": "French", "es": "Spanish"}


@task(retries=2, retry_delay_seconds=[15, 45], cache_policy=NO_CACHE)
async def write_script(brief: dict, fmt: str) -> dict:
    log = get_run_logger()
    spec = FORMAT_SPEC[fmt]
    prompt = SCRIPT_PROMPT.format(
        fmt=fmt,
        seconds=spec["target_seconds"],
        scenes=spec["scenes"],
        brief=json.dumps(brief, ensure_ascii=False),
    )
    raw = await _gemini(prompt, temperature=0.8)
    script = json.loads(_strip_fences(raw))
    script["lang"] = "en"
    log.info(f"Master {fmt} script: {script.get('title')} ({len(script['scenes'])} scenes)")
    return script


@task(retries=2, retry_delay_seconds=[15, 45], cache_policy=NO_CACHE)
async def localize(master: dict, lang: str) -> dict:
    if lang == "en":
        return master
    log = get_run_logger()
    prompt = LOCALIZE_PROMPT.format(
        lang=lang,
        lang_name=LANG_NAMES[lang],
        script=json.dumps(master, ensure_ascii=False),
    )
    raw = await _gemini(prompt, temperature=0.4)
    localized = json.loads(_strip_fences(raw))
    localized["lang"] = lang
    # Hard guarantee: copy timestamps back from master so they never drift.
    by_id = {s["id"]: s for s in master["scenes"]}
    for sc in localized["scenes"]:
        m = by_id[sc["id"]]
        sc["start"], sc["end"] = m["start"], m["end"]
    log.info(f"Localized to {lang}: {localized.get('title')}")
    return localized
