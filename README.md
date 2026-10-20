# 🎙️ AI Video Dubbing — Cantonese → English in a Cloned Voice

An end-to-end pipeline that re-voices hour-long Cantonese talks into natural **English, in the
original speaker's own cloned voice** — keeping the original video length, preserving sung
sections, and generating synced captions.

Built on **[ElevenLabs](https://elevenlabs.io)** (voice cloning + v4 text-to-speech),
**OpenAI Whisper** (speech-to-text), and **ffmpeg**, orchestrated in Python.

---

## ▶️ Watch an example — same sermon, same voice, two languages

The English version below was produced with **ElevenLabs v4**: the speaker's voice was cloned
from the original audio, then used to narrate the English translation with a stable accent and
natural pacing.

| 🇭🇰 Original (Cantonese) | 🇺🇸 English dub — cloned voice (ElevenLabs v4) |
|:---:|:---:|
| [![Original Cantonese](https://img.youtube.com/vi/z__gkulshp8/hqdefault.jpg)](https://www.youtube.com/watch?v=z__gkulshp8) | [![English dub](https://img.youtube.com/vi/oH_vzkyf1TE/hqdefault.jpg)](https://www.youtube.com/watch?v=oH_vzkyf1TE) |
| ▶️ [Watch original](https://www.youtube.com/watch?v=z__gkulshp8) | ▶️ [Watch English dub](https://www.youtube.com/watch?v=oH_vzkyf1TE) |

> Tip: play a minute of each back-to-back — it's the **same person's voice**, speaking English.

---

## What it does

- **Clones the speaker's voice** once (ElevenLabs Instant Voice Clone) and reuses it across videos.
- **Transcribes** the Cantonese audio with Whisper (`large-v3`), then translates to English with
  attention to nuance — quoted scripture is kept word-for-word accurate.
- **Generates** the English narration in the cloned voice and **fits it to the original timeline**
  (English is ~65% the length of spoken Cantonese) using duration-aware translation + gentle
  adaptive slow-down — no re-cutting the video, no dead air.
- **Preserves sung hymns** as the original audio (not dubbed), with translated lyrics as subtitles.
- **Outputs** a finished MP4 plus voice-matched English and Traditional-Chinese caption tracks.

## Pipeline

```
Source video ─► ffmpeg (extract audio)
             ─► Whisper large-v3 (Cantonese → text)
             ─► translation (English, scripture-accurate)
             ─► ElevenLabs v4 (cloned voice, [American accent], chunked generation)
             ─► assemble + fit to timeline + splice original hymn + mux
             ─► final MP4 + English CC + 書面語 CC
```

## Engineering highlights

| Challenge | Solution |
|-----------|----------|
| English is much shorter than Cantonese → silent gaps | Duration-aware translation + adaptive slow-down → silent gaps cut from **32 → 1** on a 54-min video |
| Accent drifted / sounded unlike the speaker | Adopted **ElevenLabs v4** on launch (holds accent across a generation) at high similarity → keeps the speaker's real voice **and** a stable American accent |
| Voice consistency over a 55-min talk | Chunked generation; verified consistency across segments **27 minutes apart** |
| Cost control | Tracked character/credit usage via the **ElevenLabs usage API** to guide model/version choices |
| Sung worship sections | Detected and **kept original singing**, dubbing only the spoken parts |

## Tech

`Python` · `ElevenLabs API` (IVC, TTS, Dubbing, v4) · `OpenAI Whisper (MLX)` · `ffmpeg` · `opencc`

---

*A personal project exploring voice cloning and AI dubbing to make content accessible across languages.*
