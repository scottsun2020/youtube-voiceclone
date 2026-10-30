"""Re-time the English dub subtitle to the ACTUAL audio, using Whisper word
timestamps, CONSTRAINED PER CHUNK so a mismatch can never cascade across the video.

Approach:
  1. Replay build_full.py's placement to get each chunk's real audio window [a0,a1].
  2. For each chunk, take only the Whisper words inside [a0,a1], and place that
     chunk's caption cues where their words actually occur (greedy fuzzy match).
     If a cue can't be matched, fall back to proportional placement *within that
     same window* -> any error is bounded to one ~90s chunk.
  3. Keep the reused hymn-lyric cues at their own timing (sung, not in the ASR).
  4. Write subtitles_en_dub.srt (after splitting long cues).

Does NOT touch audio, video, or translation. Reversible: backup_pre_align/ holds
the previous subtitle + video.
Usage: python video5/align_subs.py
"""
import re, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, "video5")
import build_full as b

WORDS = "video5/transcripts/dub_words.json"
OUT = "video5/transcripts/subtitles_en_dub.srt"
RAW = "video5/transcripts/subtitles_en_dub_aligned_raw.srt"
HYMN_EN = "video5/transcripts/hymn_cues_en.srt"


def norm(t): return re.sub(r"[^a-z0-9]", "", t.lower())
def ts(t):
    h=int(t//3600); m=int(t%3600//60); s=t%60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
def dur(p):
    return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1",str(p)],capture_output=True,text=True).stdout)


def chunk_windows():
    """Replay build() audio placement -> list of (chunk_index, a0, a1)."""
    ch = b.chunks(); target = b.parse()[-1]["e"]
    hymn_dur = dur(b.HYMN_WAV)
    cursor = 0.0; wins = []
    for i, c in enumerate(ch):
        if c["region"] == 2 and cursor < b.HYMN_END:
            if cursor < b.HYMN_START: cursor = b.HYMN_START
            cursor += hymn_dur
            if cursor < b.HYMN_END: cursor = b.HYMN_END
        if cursor < c["start"]: cursor = c["start"]
        raw = dur(b.CHUNKS / f"chunk_{i:03d}.mp3")
        nxt = ch[i+1]["start"] if i+1 < len(ch) else target
        if i+1 < len(ch) and c["region"] == 1 and ch[i+1]["region"] == 2: nxt = b.HYMN_START
        avail = nxt - cursor
        if avail <= 0: speed = b.CMAX
        elif raw > avail: speed = min(b.CMAX, raw/avail)
        else: speed = 1.0/min(b.STRETCH, avail/raw)
        adur = raw/speed
        wins.append((i, cursor, cursor+adur)); cursor += adur
    return ch, wins


def place(cues, win, a0, a1, prev_end):
    """Place spoken cues within [a0,a1], STRICTLY SEQUENTIAL.
    Forward-only word pointer; every cue start >= prev cue end (monotonic);
    a match that would go backward or jump implausibly is rejected -> proportional
    fallback, so wrong repeated-word matches can't scramble order."""
    out = []; wi = 0
    tot = sum(len(cc["t"]) for cc in cues) or 1
    off = 0
    cursor = max(a0, prev_end)
    for ci, cc in enumerate(cues):
        toks = [norm(x) for x in cc["t"].split() if norm(x)]
        s = e = None
        if win and toks:
            start_i = None
            # only search forward from wi, and only within this window
            for j in range(wi, len(win)):
                if win[j][0] == toks[0] or (len(toks[0]) >= 4 and win[j][0].startswith(toks[0][:4])):
                    start_i = j; break
            if start_i is not None:
                k = start_i; last = start_i
                for t in toks:
                    for j in range(k, min(k+5, len(win))):
                        if win[j][0] == t or (len(t) >= 4 and win[j][0].startswith(t[:4])):
                            last = j; k = j+1; break
                cs, ce = win[start_i][1], win[last][2]
                # accept only if it moves forward sensibly (no backward, no absurd jump)
                if cs >= cursor - 0.05 and cs <= a1 + 0.3:
                    s, e = cs, ce; wi = last + 1
        if s is None:   # proportional fallback, anchored after the previous cue
            span = max(0.0, a1 - cursor)
            rem = tot - off
            share = span * (len(cc["t"]) / rem) if rem > 0 else 0.6
            s = cursor; e = cursor + max(0.6, share)
        if s < cursor: s = cursor
        if e <= s: e = s + 0.6
        out.append((s, e, cc["t"]))
        cursor = e
        off += len(cc["t"])
    return out


def load_hymn():
    p = Path(HYMN_EN); cues = []
    if p.exists():
        for blk in p.read_text(encoding="utf-8").strip().split("\n\n"):
            L = blk.split("\n")
            if len(L) >= 3:
                m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", L[1])
                g = list(map(int, m.groups()))
                cues.append((g[0]*3600+g[1]*60+g[2]+g[3]/1000,
                             g[4]*3600+g[5]*60+g[6]+g[7]/1000, " ".join(L[2:])))
    return cues


def main():
    words = json.load(open(WORDS))
    wtok = [(norm(w["w"]), w["s"], w["e"]) for w in words if norm(w["w"])]
    ch, wins = chunk_windows()
    hymn = load_hymn()
    out = []; prev_end = 0.0
    hymn_done = False
    for (i, a0, a1) in wins:
        # insert the hymn-lyric block in its temporal slot (between region1 and region2)
        if not hymn_done and ch[i]["region"] == 2 and hymn:
            for hs, he, ht in hymn:
                hs = max(hs, prev_end)
                out.append((hs, max(he, hs+0.6), ht)); prev_end = out[-1][1]
            hymn_done = True
        win = [w for w in wtok if a0-0.3 <= w[1] <= a1+0.3]
        spoken = [cc for cc in ch[i]["cues"] if cc["t"].strip()]
        placed = place(spoken, win, a0, a1, prev_end)
        out += placed
        if placed: prev_end = placed[-1][1]
    if not hymn_done:   # safety: append hymn if no region-2 chunk triggered it
        for hs, he, ht in hymn:
            hs = max(hs, prev_end); out.append((hs, max(he, hs+0.6), ht)); prev_end = out[-1][1]
    # already monotonic by construction; final clamp as belt-and-suspenders
    fixed = []
    for s, e, txt in out:
        if fixed and s < fixed[-1][1]: s = fixed[-1][1]
        if e <= s: e = s + 0.6
        fixed.append((s, e, txt))
    with open(RAW, "w", encoding="utf-8") as f:
        for i, (s, e, txt) in enumerate(fixed, 1):
            f.write(f"{i}\n{ts(s)} --> {ts(e)}\n{txt}\n\n")
    subprocess.run(["python", "video5/split_long_cues.py", RAW, OUT, "8.0"], check=True)
    print(f"aligned {len(fixed)} cues -> {OUT}")


if __name__ == "__main__":
    main()
