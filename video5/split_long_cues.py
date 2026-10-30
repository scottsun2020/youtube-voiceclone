"""Split over-long SRT cues so no subtitle stays on screen too long.
Any cue whose duration exceeds MAXDUR is broken at sentence boundaries
(falling back to clause boundaries, then a mid split) with the cue's time
window distributed across the pieces in proportion to their character length.
Timestamps of normal-length cues are left untouched.

Handles both Latin and CJK text (auto-detected per cue): CJK uses Chinese
punctuation (。！？，、；：), no-space line wrapping, and a narrower wrap width.

Usage: python video4/split_long_cues.py IN.srt OUT.srt [MAXDUR]
"""
import re, sys
from pathlib import Path

MAXDUR = 8.0        # split any cue longer than this many seconds
WRAP_LATIN = 42     # soft line-wrap width (characters) for Latin text
WRAP_CJK = 18       # soft line-wrap width (characters) for CJK text

CJK = re.compile(r"[㐀-鿿]")


def is_cjk(text):
    return bool(CJK.search(text))


def t2s(ts):
    h, m, rest = ts.split(":"); s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def s2t(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def parse(p):
    cues = []
    for b in re.split(r"\n\s*\n", Path(p).read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) < 3:
            continue
        a, b2 = L[1].split(" --> ")
        sep = "" if is_cjk(" ".join(L[2:])) else " "
        cues.append([t2s(a), t2s(b2), sep.join(x.strip() for x in L[2:])])
    return cues


def sent_split(text):
    if is_cjk(text):
        parts = re.split(r"(?<=[。！？…])", text.strip())
    else:
        parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p for p in parts if p.strip()]


def clause_split(text):
    if is_cjk(text):
        parts = re.split(r"(?<=[，、；：,;])", text.strip())
    else:
        parts = re.split(r"(?<=[,;:—])\s+", text.strip())
    return [p for p in parts if p.strip()]


def half(text):
    if is_cjk(text):
        mid = len(text) // 2 or 1
        return [text[:mid], text[mid:]]
    w = text.split(); mid = len(w) // 2 or 1
    return [" ".join(w[:mid]), " ".join(w[mid:])]


def atomic(p):
    return len(p) <= 8 if is_cjk(p) else len(p.split()) < 4


def wrap(text):
    if is_cjk(text):
        return "\n".join(text[i:i + WRAP_CJK] for i in range(0, len(text), WRAP_CJK))
    words = text.split(); lines = []; cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > WRAP_LATIN:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def fit(pieces, rate):
    """Recursively break any piece still longer than MAXDUR at rate (s/char)."""
    out = []
    for p in pieces:
        if len(p) * rate <= MAXDUR or atomic(p):
            out.append(p); continue
        sub = clause_split(p)
        if len(sub) < 2:
            sub = half(p)
        out.extend(fit(sub, rate))
    return out


def main(inp, outp, maxdur):
    global MAXDUR
    MAXDUR = maxdur
    cues = parse(inp)
    out = []; n_split = 0
    for s, e, text in cues:
        dur = e - s
        if dur <= MAXDUR:
            out.append((s, e, text)); continue
        n_split += 1
        rate = dur / max(1, len(text))
        pieces = fit(sent_split(text), rate)
        tot = sum(len(p) for p in pieces) or 1
        t = s
        for i, p in enumerate(pieces):
            d = dur * len(p) / tot
            end = e if i == len(pieces) - 1 else t + d
            out.append((t, end, p.strip())); t = end
    with open(outp, "w", encoding="utf-8") as f:
        for i, (s, e, text) in enumerate(out, 1):
            f.write(f"{i}\n{s2t(s)} --> {s2t(e)}\n{wrap(text)}\n\n")
    print(f"{inp}: {len(cues)} cues -> {outp}: {len(out)} cues ({n_split} long cues split)")


if __name__ == "__main__":
    inp, outp = sys.argv[1], sys.argv[2]
    md = float(sys.argv[3]) if len(sys.argv) > 3 else MAXDUR
    main(inp, outp, md)
