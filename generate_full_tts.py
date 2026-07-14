"""Generate the full English narration from subtitles_en.srt using the cloned voice."""
import os
import re
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()
client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
voice_id = open(".voice_id").read().strip()

# --- Parse SRT into plain-text segments ---
SRT_TIME = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}")

def parse_segments(srt_path: Path):
    blocks = re.split(r"\n\s*\n", srt_path.read_text(encoding="utf-8").strip())
    out = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 3:
            continue
        text = " ".join(l.strip() for l in lines[2:])
        out.append(text)
    return out

segments = parse_segments(Path("transcripts/subtitles_en.srt"))
print(f"Loaded {len(segments)} segments")

# --- Group into ~800-char chunks at sentence boundaries ---
SENTENCE_END = re.compile(r"[.!?]\s*$")
CHUNK_TARGET = 800

chunks = []
buf = []
buf_len = 0
for seg in segments:
    buf.append(seg)
    buf_len += len(seg) + 1
    if buf_len >= CHUNK_TARGET and SENTENCE_END.search(seg):
        chunks.append(" ".join(buf))
        buf = []
        buf_len = 0
if buf:
    chunks.append(" ".join(buf))

total_chars = sum(len(c) for c in chunks)
print(f"Built {len(chunks)} chunks, total {total_chars:,} chars")

# --- Generate each chunk ---
out_dir = Path("audio/chunks")
out_dir.mkdir(parents=True, exist_ok=True)

for i, text in enumerate(chunks):
    out_path = out_dir / f"chunk_{i:03d}.mp3"
    if out_path.exists():
        print(f"[{i+1}/{len(chunks)}] skip (exists)")
        continue
    prev_text = chunks[i - 1] if i > 0 else None
    next_text = chunks[i + 1] if i < len(chunks) - 1 else None
    print(f"[{i+1}/{len(chunks)}] {len(text)} chars → {out_path.name}")
    audio_iter = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        previous_text=prev_text,
        next_text=next_text,
    )
    with open(out_path, "wb") as f:
        for c in audio_iter:
            f.write(c)

print("\nAll chunks generated. Concatenating...")

# --- Concatenate all chunks via ffmpeg concat demuxer ---
list_path = out_dir / "concat_list.txt"
with open(list_path, "w") as f:
    for i in range(len(chunks)):
        f.write(f"file 'chunk_{i:03d}.mp3'\n")

final_out = Path("audio/english_voice.wav")
subprocess.run(
    ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
     "-i", str(list_path),
     "-ar", "44100", "-ac", "1",
     str(final_out)],
    check=True,
    cwd=out_dir.parent.parent,
)

# Report duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", str(final_out)],
    capture_output=True, text=True, check=True,
)
duration_s = float(result.stdout.strip())
print(f"\nFinal: {final_out}")
print(f"Duration: {duration_s:.1f}s = {duration_s/60:.1f} min")
