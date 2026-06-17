# VidAuto - Subscription-Only Manual Assembler

Make localized (EN / FR / ES) kids' videos in two formats - **short** (9:16,
1080x1920) and **long** (16:9, 1920x1080) - with hardcoded subtitles, using
**only the apps you already pay for** plus **free local ffmpeg**.

There are **no API calls** anywhere in this project: no Perplexity API, no
Gemini API, no Veo API, no paid TTS. You do the AI steps **by hand** inside
Perplexity Pro, the Gemini app, and Google Flow, drop the resulting files into
folders, and this one script stitches the finals together.

```
Perplexity Pro  ->  Gemini app  ->  Google Flow  ->  your voice / TTS  ->  assemble.py
  (topic)           (script +       (Veo clips)       (narration wav)       (ffmpeg)
                     translation)
```

## What's automated vs. manual

| Step                         | Where            | Cost             | Automated? |
| ---------------------------- | ---------------- | ---------------- | ---------- |
| Trending topic brief         | Perplexity Pro   | your sub         | manual     |
| Script + FR/ES translation   | Gemini app       | your sub         | manual     |
| Video clips (Veo)            | Google Flow      | your sub credits | manual     |
| Narration audio              | voice / free TTS | free             | manual     |
| Subtitles from script        | write_srt.py     | free             | **auto**   |
| Concat + mux + burn-in       | assemble.py      | free (ffmpeg)    | **auto**   |

Full click-by-click instructions with copy-paste prompts are in **WORKFLOW.md**.

## Layout

```
VidAuto/
├── assemble.py            # the one script that builds the finals
├── write_srt.py           # JSON script  ->  .srt subtitle file
├── requirements.txt       # stdlib only (no paid packages)
├── README.md
├── WORKFLOW.md            # the manual step-by-step checklist + prompts
├── prompts/
│   └── character_bible.json
└── assets/
    └── job-001/
        ├── raw/           # drop downloaded Flow clips here: short_1.mp4, long_1.mp4, ...
        ├── audio/         # drop narration here: {fmt}_{lang}.wav  e.g. short_en.wav
        ├── subs/          # subtitles live here: {fmt}_{lang}.srt  e.g. short_en.srt
        └── final/         # assemble.py writes finished videos here: {lang}_{fmt}.mp4
```

## One-time setup

1. **Install ffmpeg** (free) and make sure it's on your PATH:

   ```powershell
   winget install Gyan.FFmpeg
   ```

   Open a **new** terminal afterwards so PATH refreshes, then confirm:

   ```powershell
   ffmpeg -version
   ```

2. **Python 3.8+** - no packages to install. `requirements.txt` is intentionally
   empty (standard library only).

## Run it

After you've populated `assets/job-001/raw/`, `audio/`, and `subs/` (see
WORKFLOW.md):

```powershell
cd C:\Users\Aymen\Documents\VidAuto
python assemble.py            # processes job-001 by default
python assemble.py job-002    # any other job folder under assets/
```

Finished videos land in `assets/job-001/final/` as `en_short.mp4`,
`fr_short.mp4`, `es_short.mp4`, `en_long.mp4`, etc.

If a file is missing, the script **skips that combination and tells you exactly
which file it wanted and where** - it never crashes. Add the missing file and
re-run; existing finals are simply overwritten.

## Turning a script into subtitles

```powershell
python write_srt.py path\to\script_short_en.json assets\job-001\subs\short_en.srt
```

`write_srt.py` accepts scene times as seconds (`11`, `11.5`) or as timestamp
strings (`00:00:11,000`). See its header for the exact JSON shape, and use
`--section short` / `--section long` when one JSON holds both formats.

## Encoder settings (what assemble.py uses)

- Video: `libx264`, `-crf 20`, `-pix_fmt yuv420p`
- Audio: `aac`, `128 kbps`
- Scale to fit then **pad** (centered letterbox) to the exact target resolution
- Subtitles burned in via the `subtitles` filter - white text, black outline,
  bottom-centered, sized for mobile
- `-shortest` so the video ends with the narration

## Notes

- **No Docker, no Prefect, no paid anything.**
- Visuals are **language-agnostic** - render each scene in Flow only once and
  reuse the clip for all three languages. Only narration + subtitles change.
- Keep `prompts/character_bible.json` open while generating in Flow; paste
  Mimi's full descriptor and the locked seed into every clip prompt.
