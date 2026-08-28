# Cantonese → English Video Dubbing Runbook

A repeatable pipeline that turns a Cantonese-language talk (e.g. a YouTube
sermon/lecture) into an **English-dubbed video in a cloned copy of the original
speaker's voice**, plus matching subtitle tracks. Built and proven on 3 videos.

The result keeps the **original video length** — the English (which is naturally
~65% the length of the Cantonese delivery) is fit into the timeline with
sentence-level adaptive slow-down + short natural pauses, so lips-off narration
stays roughly in sync without speeding anyone up unnaturally.

---

## 0. What you need (one-time setup)

**Machine:** macOS on Apple Silicon (the transcriber uses Metal via MLX).

**System tools**
- `ffmpeg` / `ffprobe`  — `brew install ffmpeg`
- `yt-dlp` (only if downloading from YouTube) — `brew install yt-dlp`

**Python environment** (repo uses a `.venv/` at the project root)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install mlx-whisper elevenlabs python-dotenv
```

**Accounts / keys**
- An **ElevenLabs** account (Creator tier ~$22/mo, ~131k chars/mo is plenty for
  a 40-min talk). Put the key in a root `.env` file:
  ```
  ELEVENLABS_API_KEY=sk_...
  ```
- After cloning the voice (step 1) store the returned voice id in `.voice_id`
  (a one-line file at the project root).

**macOS gotcha (important):** `~/Documents` is TCC-protected. Grant your
terminal app **Full Disk Access** (System Settings → Privacy & Security → Full
Disk Access) and **restart the terminal**, or ffmpeg/whisper/yt-dlp will hit
permission errors. `yt-dlp --cookies-from-browser safari` (needed to beat
YouTube's bot-check) also requires this.

---

## 1. Clone the speaker's voice (once per speaker, reused across all their videos)

1. Cut a clean **~2-minute** mono sample of the speaker talking (no music, no
   other voices): `audio/voice_sample.wav`.
2. Create an ElevenLabs **Instant Voice Clone (IVC)** from that sample (via the
   ElevenLabs web UI or the API — see `clone_voice.py`).
3. Save the returned voice id into `.voice_id`.

Do **not** re-clone for a second video by the same speaker — reuse the same
voice id. (We tried a pitch-shifted variant once; the original clone sounded
better.)

---

## Per-video pipeline

Each video lives in its own self-contained folder: `video2/`, `video3/`, …
(Video 1 lives at the repo root for historical reasons.) All scripts are run
**from the project root** and have their paths pointed at that video's folder.

To start a new video, copy the 6 scripts from an existing video folder and
repoint the paths, e.g.:
```bash
mkdir -p videoN/{source,audio/segments,transcripts,output}
cp video3/*.py videoN/
sed -i '' 's#video3/#videoN/#g' videoN/*.py
# then edit the SRC filename in videoN/build_dub.py to your source video
```

### Stage 1 — Get the source video
- Download (`yt-dlp --cookies-from-browser safari <url>`) or drop the file into
  `videoN/source/`.
- Trim if needed with ffmpeg. (We kept full length on videos 2 & 3.)

### Stage 2 — Extract audio for transcription
```bash
ffmpeg -y -i "videoN/source/<file>.mp4" -ac 1 -ar 16000 -vn \
  videoN/audio/source_audio.wav
```
(16 kHz mono is what Whisper wants.)

### Stage 3 — Transcribe the Cantonese
```bash
mlx_whisper videoN/audio/source_audio.wav \
  --model mlx-community/whisper-large-v3-mlx \
  --language yue \
  --condition-on-previous-text False \
  --output-dir videoN/transcripts --output-name subtitles_zh --output-format srt
```
**`--condition-on-previous-text False` is mandatory** for this speaker — without
it Whisper falls into repetition loops. Note Whisper writes Cantonese speech as
**written Chinese characters**.

**Sanity-check the SRT** (should be true on a clean run): zero consecutive
duplicate lines, zero text repeated 3+ times in a row, no >5s gaps, coverage
runs from ~0s to the full video duration.

### Stage 4 — ⏸ Human: proofread the Chinese SRT
Open `videoN/transcripts/subtitles_zh.srt` and fix mistranscriptions — mainly
**proper nouns, place names, people, and Bible references / quoted scripture**
(Whisper's weak spots). This is the single most important manual step; the
translation and dub are only as good as this file.

### Stage 5 — Translate to English  (duration-aware)  ⟵ human/LLM step
This is a content step (done with an LLM/translator, not an automatic script).
Two principles that make the fit work:
1. **Write the English naturally *fuller*** — aim for the English to fill ~86%
   of each slot up front. This dramatically cuts the number of segments that
   need later rescue (Video 1 needed 22 rewrites; the fuller-translation
   approach on Video 2 needed only 1).
2. **Never alter quoted scripture** — keep canonical Bible phrasing verbatim.

Produce **two things**:
- `videoN/transcripts/en_lines.txt` — one English line per segment, in order,
  the same count as the Chinese SRT (the concise *reading* subtitle text).
- Then assemble it into a timed SRT, reusing the Chinese timestamps byte-for-byte:
  ```bash
  python videoN/make_en.py     # -> transcripts/subtitles_en.srt
  ```

Also produce the standard-written-Chinese subtitle (Traditional 書面語)
converted from the colloquial Cantonese:
```bash
python videoN/make_mandarin.py  # -> transcripts/subtitles_zh_mandarin.srt
```
(`make_mandarin.py` holds the colloquial→書面語 conversion for that video; it is
content and is edited per-video.)

### Stage 6 — Generate the voice clips
One TTS clip per English segment, in the cloned voice, with surrounding text as
context so prosody flows. Resumable (skips clips already on disk).
```bash
python videoN/generate_clips.py   # -> videoN/audio/segments/seg_NNN.mp3
```
Uses `eleven_multilingual_v2`, `previous_text`/`next_text` = the neighbouring
segments.

### Stage 7 — Timing analysis → rewrite punch-list  (no API, no audio written)
```bash
python videoN/timing_rewrite.py   # -> transcripts/rewrite_list.md / .json
```
This measures each clip, groups segments into **sentences**, simulates the
adaptive slow-down (≤1.25× stretch), and lists the sentences that would *still*
leave a pause longer than 4s. It flags each as **scripture (leave verbatim)** or
**narration (safe to expand)**.

### Stage 8 — ⏸ Human: approve a short list of expansions
For the flagged **narration** sentences only, write slightly longer English that
says the same thing (to fill the residual gap). **Leave all scripture alone.**
Put the approved rewrites into the `REWRITES = { sentenceNumber: "…", }` dict at
the top of `videoN/build_dub.py`.

### Stage 9 — Build the dub + mux
```bash
python videoN/build_dub.py all    # gen (TTS the rewrites) + build (assemble+mux)
```
What "build" does:
- Groups segments into sentences (no mid-sentence silence).
- Places each sentence at its start time; **slows** it up to 1.25× to fill its
  slot, or **compresses** up to 1.15× if it's running long; leftover becomes a
  short natural pause.
- Writes `videoN/audio/english_dub.wav` (same total length as the video).
- Muxes: original **video copied** (no re-encode) + new English AAC audio +
  `subtitles_en.srt` as soft subs → **`videoN/output/final_english_v2.mp4`**.
- Prints stats: minutes, #slowed, #compressed, **peak drift** (keep well under
  ~2.5s), and it should report no long pauses.

### Stage 10 — Voice-matched captions (for YouTube CC)
```bash
python videoN/make_dub_srt.py     # -> transcripts/subtitles_en_dub.srt
```
This replays the exact pacing of the build to produce captions **timed to the
spoken audio** (and using the expanded wording where sentences were rewritten).

### Stage 11 (optional) — Dual-audio "multitrack" file
One MP4 the viewer can toggle between Cantonese/English audio and Chinese/English
subs. Extract the original Cantonese audio and the built English audio, then mux
video + both audio tracks + both subtitle tracks (see `video2/output/
final_multitrack.mp4` for the reference layout: v / yue / eng / zho / eng).

---

## Deliverables (per video)

| File | What it is | Use |
|------|-----------|-----|
| `output/final_english_v2.mp4` | English dub, original length, English soft subs | the video |
| `transcripts/subtitles_en_dub.srt` | captions matching the **spoken** dub | **upload as YouTube English CC** |
| `transcripts/subtitles_en.srt` | concise English *reading* translation | alt/standalone subtitle |
| `transcripts/subtitles_zh_mandarin.srt` | Traditional 書面語 | upload as Chinese CC |
| `transcripts/subtitles_zh.srt` | Cantonese source transcript | dub reference only |

**For YouTube, upload `subtitles_en_dub.srt`** as the English caption track — it
matches what's actually said (the concise `subtitles_en.srt` is shorter than the
spoken lines wherever a sentence was expanded in Stage 8).

---

## The core idea, in one paragraph

English is systematically shorter than spoken Cantonese, so a straight dub
leaves big silences. Rather than speed the voice up (unnatural) or re-cut the
video, we (1) translate a little *fuller* on purpose, (2) pace at the **sentence**
level and **slow** each sentence up to 1.25× to fill its slot, letting any small
remainder be a natural pause, and (3) hand-expand only the handful of narration
sentences that would still gape — **never scripture**. Everything else
(transcription, clip generation, assembly, caption timing) is scripted and
repeatable.
