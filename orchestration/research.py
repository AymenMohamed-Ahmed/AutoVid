"""Research engine: Perplexity Pro -> validated structured brief.

Writes assets/{job_id}/brief.json which downstream tasks consume.
"""
import os
import json
import httpx
from pathlib import Path
from pydantic import BaseModel, ValidationError
from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-pro")


class Brief(BaseModel):
    topic: str
    keywords: list[str]
    metadata: dict
    narrative_concept: str
    safety_notes: str


PROMPT = """You are a kids-content research analyst.
Scan for ONE high-performing, safe, age-appropriate (ages 3-7) trending topic
suitable for a short animated educational story.

Return STRICT JSON only, no prose, no markdown fences, matching this schema:
{
  "topic": "string",
  "keywords": ["string", ...],          // 5-10 SEO keywords
  "metadata": {"trend_source": "string", "est_audience": "string"},
  "narrative_concept": "string",        // 2-3 sentence story premise
  "safety_notes": "string"              // why this is safe for kids
}
Avoid anything frightening, commercial, or with branded characters.
"""


def _strip_fences(text: str) -> str:
    return text.replace("```json", "").replace("```", "").strip()


@task(retries=3, retry_delay_seconds=[10, 30, 90], cache_policy=NO_CACHE)
async def research_topic(job_id: str) -> dict:
    log = get_run_logger()
    api_key = os.environ["PERPLEXITY_API_KEY"]

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            PERPLEXITY_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": PERPLEXITY_MODEL,
                "messages": [{"role": "user", "content": PROMPT}],
                "temperature": 0.4,
            },
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "30"))
            log.warning(f"Perplexity 429; sleeping {retry_after}s before retry")
            import asyncio
            await asyncio.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]

    try:
        brief = Brief.model_validate_json(_strip_fences(raw))
    except ValidationError as e:
        log.error(f"Brief validation failed: {e}\nRaw: {raw[:500]}")
        raise

    out = Path(f"assets/{job_id}/brief.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(brief.model_dump_json(indent=2))
    log.info(f"Brief written: {out} | topic={brief.topic}")
    return brief.model_dump()
