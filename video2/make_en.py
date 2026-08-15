"""Build the concise English subtitle SRT from en_lines.txt (one line per
segment, in order), reusing the Cantonese SRT's timestamps byte-for-byte.
"""
import re
from pathlib import Path

SRC = Path("video2/transcripts/subtitles_zh.srt")
LINES = Path("video2/transcripts/en_lines.txt")
OUT = Path("video2/transcripts/subtitles_en.srt")

blocks = re.split(r"\n\s*\n", SRC.read_text(encoding="utf-8").strip())
cues = []
for b in blocks:
    L = b.strip().splitlines()
    if len(L) >= 3:
        cues.append((L[0].strip(), L[1].strip()))

en = [ln.rstrip() for ln in LINES.read_text(encoding="utf-8").splitlines() if ln.strip()]

assert len(en) == len(cues), f"count mismatch: {len(en)} english vs {len(cues)} cues"

out = []
for (num, ts), text in zip(cues, en):
    out.append(f"{num}\n{ts}\n{text}\n")
OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"Wrote {OUT}  ({len(out)} segments)")
