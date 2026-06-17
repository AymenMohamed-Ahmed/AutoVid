# VidAuto — Kids' Content Pipeline (Core)

Research → Script → Localize → Veo → ffmpeg. Produces hardcoded-subtitle
`.mp4` finals for EN/FR/ES in short (9:16) and long (16:9) formats.
Publishing is **not** in this core build — the flow stops at `assets/{job_id}/final/`.

## Layout
```
VidAuto/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example          # copy to .env, fill keys
├── orchestration/
│   ├── flow.py           # Prefect top-level DAG
│   ├── research.py       # Perplexity -> brief.json
│   ├── scripting.py      # Gemini script + localization
│   ├── veo.py            # Veo render + consistency matrix + seed-lock
│   ├── audio.py          # TTS + .srt
│   └── postprocess.py    # ffmpeg concat/scale/mux/burn-in
└── prompts/
    └── character_bible.json   # consistency source of truth
```

## Local run (no Docker)
```powershell
cd C:\Users\Aymen\Documents\VidAuto
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then edit .env with your keys
# ffmpeg must be on PATH (winget install Gyan.FFmpeg)
python -m orchestration.flow
```

## Docker run
```powershell
copy .env.example .env    # edit keys
docker compose up --build
```

## Notes
- `render_shot` seed = `sha256(job_id:character)`; retries re-render identically.
- Visuals render once from the EN master; only audio/subs vary per language.
- API model strings in `.env` are placeholders — confirm current Veo/Gemini
  endpoint names against provider docs before first run.
- Each provider client honors `Retry-After` on 429 and is concurrency-capped.
