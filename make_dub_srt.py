"""Emit a caption file that matches the SPOKEN dub audio (for YouTube).

Replays build_dub.py's sentence-level pacing (adaptive <=1.25x slow-down,
compression, sentence-anchored placement) analytically from clip durations,
and writes captions timed to the actual audio. Text = the spoken words:
expanded dubbing lines for the 22 rewritten sentences, original wording
(per original subtitle fragment) elsewhere.

Output: transcripts/subtitles_en_dub.srt
"""
import re, subprocess
from pathlib import Path
from build_dub import parse, sentences, REWRITES, SEG, SENT, LMAX, CMAX

OUT = Path("transcripts/subtitles_en_dub.srt")
MAXLEN = 47   # target caption width (chars)


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())


def chunk(text):
    """Greedy caption-sized chunks, preferring breaks after clause punctuation."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > MAXLEN:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
        if cur and cur[-1] in ",;:" and len(cur) >= 28:
            lines.append(cur); cur = ""
        elif cur.endswith("—") and len(cur) >= 28:
            lines.append(cur); cur = ""
    if cur:
        lines.append(cur)
    return lines


def ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def main():
    segs = parse()
    sents = sentences(segs)
    target = segs[-1]["end"]
    caps = []          # (start, end, text)
    cursor = 0.0
    for si, sent in enumerate(sents):
        n = si + 1
        start = sent[0]["start"]
        if cursor < start:
            cursor = start                       # silence pad before the sentence
        # natural duration + the sub-units (text, natural_dur) that make up the sentence
        if n in REWRITES:
            natural = dur(SENT / f"sent_{n:03d}.mp3")
            units = [(c, None) for c in chunk(REWRITES[n])]   # dur filled proportionally
        else:
            units = []
            natural = 0.0
            for s in sent:
                d = dur(SEG / f"seg_{s['i']:03d}.mp3")
                natural += d
                units.append((s["text"], d))
        nxt = sents[si+1][0]["start"] if si+1 < len(sents) else target
        avail = nxt - cursor
        if avail <= 0:
            speed = CMAX
        elif natural > avail:
            speed = min(CMAX, natural / avail)
        else:
            speed = 1.0 / min(LMAX, avail / natural)
        sent_dur = natural / speed
        # distribute sentence duration across its units
        if n in REWRITES:
            tot = sum(len(u[0]) for u in units) or 1
            durs = [sent_dur * len(u[0]) / tot for u in units]
        else:
            durs = [u[1] / speed for u in units]
        t = cursor
        for (text, _), d in zip(units, durs):
            caps.append((t, t + d, text))
            t += d
        cursor += sent_dur

    with OUT.open("w") as f:
        for i, (a, b, txt) in enumerate(caps, 1):
            f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{txt}\n\n")
    print(f"Wrote {OUT}: {len(caps)} captions, ends at {ts(caps[-1][1])}")


if __name__ == "__main__":
    main()
