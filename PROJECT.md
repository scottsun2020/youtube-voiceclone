# Cantonese → English Video Translation Project

## Goal
Convert a Cantonese (Hong Kong) YouTube video into an English-dubbed version using a cloned voice, with the source video trimmed to the first 46 minutes.

## Source
- YouTube URL: https://www.youtube.com/watch?v=oPkm1ASU6mA
- Original language: Cantonese (Hong Kong)
- Keep: first 46 minutes
- Discard: everything after the 46-minute mark

## Pipeline

### Stage 1 — Download & Trim
- Download the original video (best available video + audio).
- Trim to the first 46:00 (keep both video and audio tracks aligned).
- Output: `source_46min.mp4`

**Candidate tools:** `yt-dlp` (download), `ffmpeg` (trim).

### Stage 2 — Transcribe Cantonese → Mandarin (Chinese) subtitles
- Transcribe spoken Cantonese audio.
- Produce Mandarin-written Chinese subtitle file (SRT) with timestamps.
- Output: `subtitles_zh.srt`

**Candidate tools:** Whisper (large-v3), or a Cantonese-tuned ASR. Note: Whisper transcribes Cantonese audio into written Chinese characters by default — usable as a Mandarin-style script, but may need review for HK-specific vocabulary.

### Stage 3 — Translate Chinese → English subtitles
- Translate the Chinese SRT into English, preserving timestamps.
- Output: `subtitles_en.srt`

**Candidate tools:** Claude API (high quality, context-aware), DeepL, or GPT-class model. Translate in chunks that respect subtitle boundaries.

### Stage 4 — Voice cloning + English TTS
- Clone the original speaker's voice from the source audio.
- Generate English speech from the translated script using the cloned voice.
- Align generated speech to subtitle timestamps.
- Output: `english_voice.wav`

**Candidate tools:** ElevenLabs (Professional Voice Clone), OpenVoice, XTTS-v2, F5-TTS. ElevenLabs gives the best quality; open-source options are free but lower quality.

### Stage 5 — Mux back into video
- Replace (or mix with) the original audio in the 46-min video.
- Optionally burn in English subtitles or keep them as a soft track.
- Output: `final_english.mp4`

**Candidate tools:** `ffmpeg`.

## Decisions locked in
- **Speakers:** single speaker — no diarization needed.
- **Voice cloning:** ElevenLabs (paid). Will flag before any spend.
- **Compute:** Apple M5 Pro GPU — local Whisper via `mlx-whisper` with Metal acceleration.
- **Python env:** `.venv/` in project root (Python 3.14.3).

## Stage 5 decisions locked in
- **Subtitles:** soft track (selectable, viewer can toggle on/off).
- **Audio:** fully replace original Cantonese with English.
- **Pacing:** natural — let English audio play at natural speech length, allow drift from picture timing.

## Directory layout (proposed)
```
translation/
├── PROJECT.md                  # this file
├── source/
│   ├── original.mp4            # full download
│   └── source_46min.mp4        # trimmed
├── transcripts/
│   ├── subtitles_zh.srt
│   └── subtitles_en.srt
├── audio/
│   ├── source_audio.wav        # extracted for ASR / voice cloning
│   └── english_voice.wav       # generated TTS
└── output/
    └── final_english.mp4
```
