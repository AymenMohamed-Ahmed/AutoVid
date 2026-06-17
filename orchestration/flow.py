"""Top-level Prefect flow: research -> script -> localize -> veo -> ffmpeg.

Publishing is intentionally out of scope for this core build. The flow stops
at producing assets/{job_id}/final/{lang}_{format}.mp4 for every language and
format, ready for a publish step to pick up later.
"""
import asyncio
from prefect import flow, get_run_logger

from .research import research_topic
from .scripting import write_script, localize
from .veo import render_shot
from .audio import synthesize, write_srt
from .postprocess import concat_shots, finalize

LANGS = ["en", "fr", "es"]
FORMATS = ["short", "long"]
CHARACTER = "Mimi"


@flow(name="kids-content-pipeline", log_prints=True)
async def pipeline(job_id: str = "job-001") -> dict:
    log = get_run_logger()
    brief = await research_topic(job_id)

    finals: dict[str, dict[str, str]] = {l: {} for l in LANGS}

    for fmt in FORMATS:
        master = await write_script(brief, fmt)

        # Visuals are language-agnostic: render shots ONCE from the EN master.
        shot_paths = await asyncio.gather(*[
            render_shot(
                sc, CHARACTER, fmt, job_id,
                f"assets/{job_id}/raw/{fmt}_{sc['id']}.mp4",
            )
            for sc in master["scenes"]
        ])
        silent = await concat_shots(
            list(shot_paths), f"assets/{job_id}/raw/{fmt}_concat.mp4"
        )

        # Localize, synthesize, subtitle, and mux per language.
        localized = await asyncio.gather(*[localize(master, l) for l in LANGS])
        for script in localized:
            lang = script["lang"]
            wav = await synthesize(script, f"assets/{job_id}/audio/{fmt}_{lang}.wav")
            srt = write_srt(script, f"assets/{job_id}/subs/{fmt}_{lang}.srt")
            final = await finalize(
                silent, wav, srt, fmt,
                f"assets/{job_id}/final/{lang}_{fmt}.mp4",
            )
            finals[lang][fmt] = final

    log.info(f"Pipeline complete. Finals: {finals}")
    return finals


if __name__ == "__main__":
    asyncio.run(pipeline("job-001"))
