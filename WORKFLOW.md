# WORKFLOW — Subscription-Only Manual Checklist

Everything here is done **by hand inside apps you already pay for**. No API
keys, no automation except the final `assemble.py` (free ffmpeg). Work through
the steps top to bottom for each job. The example job id is **`job-001`**.

> **Naming cheat-sheet** (get these exactly right or `assemble.py` will skip):
>
> | File             | Pattern                          | Examples                          |
> | ---------------- | -------------------------------- | --------------------------------- |
> | Raw clips        | `assets/job-001/raw/{fmt}_{n}.mp4`   | `short_1.mp4` … `long_8.mp4`  |
> | Narration audio  | `assets/job-001/audio/{fmt}_{lang}.wav` | `short_en.wav`, `long_fr.wav` |
> | Subtitles        | `assets/job-001/subs/{fmt}_{lang}.srt`  | `short_es.srt`, `long_en.srt` |
> | Finished videos  | `assets/job-001/final/{lang}_{fmt}.mp4` | `en_short.mp4`, `fr_long.mp4` |
>
> `fmt` ∈ {`short`, `long`}  •  `lang` ∈ {`en`, `fr`, `es`}
> **short** = 9:16 (1080×1920, 4 scenes, ~45 s) • **long** = 16:9 (1920×1080, 8 scenes, ~180 s)

---

## Step 0 — Pick a locked seed (once per job)

Choose a single integer seed and reuse it on **every** Flow clip in this job.
Write it down here so you don't forget:

```
JOB-001 SEED = 12345
```

Same seed + the same character descriptor in every prompt = clips that look
like the same show. Change it and your fox will look different shot to shot.

---

## Step 1 — Perplexity Pro (in-app): get ONE safe trending topic

Open Perplexity Pro. Paste this prompt. Copy the JSON it returns and save it as
`assets/job-001/brief.json`.

```
You are a research assistant for a YouTube channel that makes gentle,
educational videos for children aged 3–6. Find ONE currently trending,
evergreen-friendly topic that is SAFE and age-appropriate for preschoolers
(nature, animals, space, colors, simple science, friendship, feelings, etc).
Avoid anything scary, violent, commercial, political, or tied to adult news.

Return ONLY strict, valid JSON (no markdown, no commentary) in exactly this shape:

{
  "topic": "<short title, 2-5 words>",
  "keywords": ["<5-8 search keywords>"],
  "narrative_concept": "<2-3 sentence kid-friendly story angle starring a fox cub named Mimi>",
  "safety_notes": "<1-2 sentences confirming why this is safe for ages 3-6 and what to avoid>"
}
```

Save the result:

```
assets/job-001/brief.json
```

---

## Step 2 — Gemini app (in-app): script, then translate

### 2a. English script (strict JSON)

Open the Gemini app. **Attach or paste** the contents of `brief.json`, then
paste this prompt. Save the JSON it returns as `assets/job-001/script_en.json`.

```
Using the attached brief.json, write a narration script for a children's video
(ages 3-6) starring Mimi, a kind, curious fox cub. Produce TWO versions:

- "short": exactly 4 scenes, total runtime about 45 seconds.
- "long":  exactly 8 scenes, total runtime about 180 seconds.

Rules:
- Timestamps are in SECONDS, contiguous and non-overlapping, starting at 0.
  short ends at ~45, long ends at ~180.
- "narration" is what the voice says on screen — warm, simple, short sentences
  a 4-year-old understands. One or two sentences per scene.
- "visual" describes ONLY what is seen (camera, action, setting) — no text,
  language-agnostic, so the same clip works for every language.
- No scary, violent, or commercial content.

Return ONLY strict, valid JSON (no markdown, no commentary) in exactly this shape:

{
  "short": {
    "scenes": [
      {"id": 1, "start": 0,  "end": 11, "narration": "...", "visual": "..."},
      {"id": 2, "start": 11, "end": 23, "narration": "...", "visual": "..."},
      {"id": 3, "start": 23, "end": 34, "narration": "...", "visual": "..."},
      {"id": 4, "start": 34, "end": 45, "narration": "...", "visual": "..."}
    ]
  },
  "long": {
    "scenes": [
      {"id": 1, "start": 0, "end": 22, "narration": "...", "visual": "..."}
      // ... 8 scenes total, last one ending at ~180
    ]
  }
}
```

Save as:

```
assets/job-001/script_en.json
```

### 2b. Translate to FR and ES (keep the EXACT same timestamps)

In the same Gemini chat, run this once for French and once for Spanish. Save
the results as `script_fr.json` and `script_es.json`.

```
Translate ONLY the "narration" fields of the JSON you just produced into
{French | Spanish}, keeping it natural and child-friendly for ages 3-6.

Do NOT change anything else: keep the same structure, the same scene ids, the
SAME start/end timestamps, and the SAME "visual" text (visuals are
language-agnostic). Return ONLY the strict, valid JSON, same shape as before.
```

Save as:

```
assets/job-001/script_fr.json
assets/job-001/script_es.json
```

> Why timestamps must stay identical: the burned-in subtitles for all three
> languages come from these timings. Same timings = subtitles line up the same
> way in every language.

---

## Step 3 — Google Flow (your Gemini subscription credits): the video clips

You will generate each scene's clip in Flow, **once**, and reuse it for all
three languages (visuals are language-agnostic). Keep
`prompts/character_bible.json` open.

For **each scene** in the script (4 for short, 8 for long), build the Flow
prompt like this:

```
<paste characters.Mimi.full_descriptor from character_bible.json verbatim>

Art style: <paste art_style.base verbatim>
Avoid: <paste art_style.negative verbatim>

Scene: <paste this scene's "visual" text from the script>

Keep the four palette colours dominant: #FFD54F, #4FC3F7, #FF8A65, #E8F5E9.
```

In Flow's settings:

- **Seed:** set it to your locked job seed (e.g. `12345`) for EVERY clip.
- **Aspect ratio:** 9:16 for the `short` clips, 16:9 for the `long` clips.
- After your first good clip, **download it and use its first frame (or the
  clip) as the reference / start image** for the following clips so the look
  stays anchored.

Download each clip and name it by format + scene number, then drop into
`raw/`:

```
assets/job-001/raw/short_1.mp4   (short scene 1)
assets/job-001/raw/short_2.mp4
assets/job-001/raw/short_3.mp4
assets/job-001/raw/short_4.mp4
assets/job-001/raw/long_1.mp4    (long scene 1)
...
assets/job-001/raw/long_8.mp4
```

> **Credit budget:** Flow Fast credits are limited (~50 clips/month on AI Pro).
> One job = 4 short + 8 long = **12 clips**. Generate visuals ONCE; never
> re-render per language. Plan scene counts before you start burning credits.

---

## Step 4 — Narration audio (free)

Produce **one WAV per language per format** — 6 files total. Either:

- **Record yourself** reading each language's `narration` lines, pacing to the
  scene timings in the script (so the voice lines up with the subtitles), **or**
- Use a **free / built-in TTS** (e.g. Windows Narrator / SAPI voices, Edge
  "Read aloud", or any free local TTS) and export to WAV.

Keep each track's length close to the format's total runtime (~45 s short,
~180 s long). `assemble.py` uses `-shortest`, so the video ends when the
narration does.

Export as WAV into `audio/`:

```
assets/job-001/audio/short_en.wav
assets/job-001/audio/short_fr.wav
assets/job-001/audio/short_es.wav
assets/job-001/audio/long_en.wav
assets/job-001/audio/long_fr.wav
assets/job-001/audio/long_es.wav
```

---

## Step 5 — Subtitles (free, automated by write_srt.py)

Turn each translated script into an `.srt`. Run from the project folder:

```powershell
cd C:\Users\Aymen\Documents\VidAuto

python write_srt.py assets\job-001\script_en.json assets\job-001\subs\short_en.srt --section short
python write_srt.py assets\job-001\script_en.json assets\job-001\subs\long_en.srt  --section long
python write_srt.py assets\job-001\script_fr.json assets\job-001\subs\short_fr.srt --section short
python write_srt.py assets\job-001\script_fr.json assets\job-001\subs\long_fr.srt  --section long
python write_srt.py assets\job-001\script_es.json assets\job-001\subs\short_es.srt --section short
python write_srt.py assets\job-001\script_es.json assets\job-001\subs\long_es.srt  --section long
```

You should now have 6 files in `assets/job-001/subs/`.

---

## Step 6 — Assemble the finals (free, ffmpeg)

```powershell
cd C:\Users\Aymen\Documents\VidAuto
python assemble.py            # job-001 by default
```

The script concatenates the raw clips per format, then for each language muxes
the narration, scales + pads to the exact resolution, burns in the subtitles,
and writes:

```
assets/job-001/final/en_short.mp4
assets/job-001/final/fr_short.mp4
assets/job-001/final/es_short.mp4
assets/job-001/final/en_long.mp4
assets/job-001/final/fr_long.mp4
assets/job-001/final/es_long.mp4
```

If anything is missing, `assemble.py` prints a `[skip]` line naming the exact
file it wanted and where — add it and re-run. Collect your finished videos from
`assets/job-001/final/`.

---

## Quick checklist

- [ ] Step 0 — seed chosen and written down
- [ ] Step 1 — `brief.json` saved
- [ ] Step 2 — `script_en.json`, `script_fr.json`, `script_es.json` saved (same timestamps)
- [ ] Step 3 — 12 clips in `raw/` (`short_1..4`, `long_1..8`), one seed, rendered once
- [ ] Step 4 — 6 WAVs in `audio/`
- [ ] Step 5 — 6 SRTs in `subs/`
- [ ] Step 6 — `python assemble.py` → 6 finals in `final/`

## New job?

Copy the folder structure to a new id and repeat:

```powershell
mkdir assets\job-002\raw, assets\job-002\audio, assets\job-002\subs, assets\job-002\final
python assemble.py job-002
```
