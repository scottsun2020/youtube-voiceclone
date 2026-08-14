"""Segment-anchored English dub aligned to the 46:00 SRT timeline.

Unlike generate_full_tts.py (which discarded timestamps and produced a
free-running 32.4-min read), this generates one clip per SRT segment and
places each at its real start time, padding the slack with silence and
compressing only the few segments that overrun their slot (capped at 1.15x).

Usage:
    python generate_aligned_tts.py generate   # synth 800 clips (billable)
    python generate_aligned_tts.py assemble   # build the 46:00 wav (no API)
    python generate_aligned_tts.py all        # both
"""
import os
import re
import sys
import wave
import subprocess
from pathlib import Path

SR = 44100
MAXSPEED = 1.15                       # cap on compression for overrun segments
EN = Path("transcripts/subtitles_en.srt")
SEG_DIR = Path("audio/segments")
OUT = Path("audio/english_voice_aligned.wav")


def parse(path=EN):
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    segs = []
    for b in blocks:
        L = b.strip().splitlines()
        if len(L) < 3:
            continue
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", L[1])
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        segs.append({
            "start": h1*3600 + m1*60 + s1 + ms1/1000,
            "end":   h2*3600 + m2*60 + s2 + ms2/1000,
            "text": " ".join(x.strip() for x in L[2:]),
        })
    return segs


def generate():
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs
    load_dotenv()
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    voice_id = open(".voice_id").read().strip()
    segs = parse()
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    texts = [s["text"] for s in segs]
    print(f"Generating {len(segs)} segment clips (resumable)...")
    for i, s in enumerate(segs):
        p = SEG_DIR / f"seg_{i:03d}.mp3"
        if p.exists() and p.stat().st_size > 0:
            continue
        # feed a few neighbouring lines as prosody context (not billed as audio)
        prev = " ".join(texts[max(0, i-4):i]) or None
        nxt = " ".join(texts[i+1:i+5]) or None
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=s["text"],
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
            previous_text=prev,
            next_text=nxt,
        )
        with open(p, "wb") as f:
            for c in audio:
                f.write(c)
        if (i + 1) % 25 == 0 or i == len(segs) - 1:
            print(f"  [{i+1}/{len(segs)}]")
    print("Done generating.")


def decode(path, speed=1.0):
    """Decode an mp3 to raw mono s16le PCM bytes, optional atempo speed-up."""
    filt = ["-filter:a", f"atempo={speed:.4f}"] if speed > 1.0001 else []
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), *filt,
         "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True,
    )
    return r.stdout


def assemble():
    segs = parse()
    target = segs[-1]["end"]
    silence = lambda sec: b"\x00\x00" * int(round(max(0.0, sec) * SR))
    out = bytearray()
    cursor = 0.0
    compressed = 0
    peak_drift = 0.0
    print(f"Assembling {len(segs)} clips onto a {target/60:.1f}-min timeline...")
    for i, s in enumerate(segs):
        nxt = segs[i+1]["start"] if i + 1 < len(segs) else target
        if cursor < s["start"]:                       # pad up to the cue
            out += silence(s["start"] - cursor)
            cursor = s["start"]
        pcm = decode(SEG_DIR / f"seg_{i:03d}.mp3")
        dur = len(pcm) / 2 / SR
        avail = nxt - cursor
        if dur > avail and avail > 0:                 # overruns its slot
            speed = min(MAXSPEED, dur / avail)
            pcm = decode(SEG_DIR / f"seg_{i:03d}.mp3", speed)
            dur = len(pcm) / 2 / SR
            compressed += 1
        out += pcm
        cursor += dur
        if cursor > nxt:                              # started next line late
            peak_drift = max(peak_drift, cursor - nxt)
        if (i + 1) % 100 == 0:
            print(f"  placed {i+1}/{len(segs)}  cursor={cursor:6.1f}s")
    if cursor < target:                               # tail pad to 46:00
        out += silence(target - cursor)
        cursor = target
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(out))
    print(f"\nWrote {OUT}")
    print(f"  duration:        {cursor:.1f}s = {cursor/60:.2f} min")
    print(f"  compressed segs: {compressed} (<= {MAXSPEED}x)")
    print(f"  peak sync drift: {peak_drift:.2f}s")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("generate", "all"):
        generate()
    if cmd in ("assemble", "all"):
        assemble()
