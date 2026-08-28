"""Generate one TTS clip per English SRT segment for video 2, reusing the
existing cloned voice. Resumable. -> video3/audio/segments/seg_NNN.mp3
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

EN = Path("video3/transcripts/subtitles_en.srt")
SEG = Path("video3/audio/segments")

load_dotenv(str(Path(".env").resolve()))
client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
voice_id = open(".voice_id").read().strip()


def parse():
    segs = []
    for b in re.split(r"\n\s*\n", EN.read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) >= 3:
            segs.append(" ".join(x.strip() for x in L[2:]))
    return segs


texts = parse()
SEG.mkdir(parents=True, exist_ok=True)
print(f"Generating {len(texts)} clips with voice {voice_id} ...")
for i, text in enumerate(texts):
    p = SEG / f"seg_{i:03d}.mp3"
    if p.exists() and p.stat().st_size > 0:
        continue
    prev = " ".join(texts[max(0, i-4):i]) or None
    nxt = " ".join(texts[i+1:i+5]) or None
    audio = client.text_to_speech.convert(
        voice_id=voice_id, text=text, model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128", previous_text=prev, next_text=nxt)
    with open(p, "wb") as f:
        for c in audio:
            f.write(c)
    if (i + 1) % 25 == 0 or i == len(texts) - 1:
        print(f"  [{i+1}/{len(texts)}]")
print("Done.")
