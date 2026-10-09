"""Build subtitles_en.srt from a NUMBERED translation map (en_map.txt: 'N|english'),
matched to the proofread zh SRT by cue number. Verifies every cue is translated;
reports missing/extra so the 1016-cue translation stays perfectly aligned.
Usage: python video4/make_en_mapped.py [--status]
"""
import re, sys
from pathlib import Path

ZH = Path("video4/transcripts/subtitles_zh_full_working.srt")
MAP = Path("video4/transcripts/en_map.txt")
OUT = Path("video4/transcripts/subtitles_en.srt")


def zh_cues():
    out = []
    for b in re.split(r"\n\s*\n", ZH.read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) >= 3:
            out.append((int(L[0]), L[1].strip()))
    return out


def en_map():
    m = {}
    for ln in MAP.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or "|" not in ln:
            continue
        num, txt = ln.split("|", 1)
        m[int(num)] = txt.strip()
    return m


def main():
    cues = zh_cues()
    em = en_map()
    nums = [n for n, _ in cues]
    have = set(em)
    need = set(nums)
    missing = sorted(need - have)
    extra = sorted(have - need)
    print(f"zh cues: {len(nums)} (#{nums[0]}..#{nums[-1]})")
    print(f"translated: {len(have & need)}/{len(need)}")
    if extra:
        print(f"EXTRA (not in zh): {extra[:10]}")
    if missing:
        # compress into ranges
        rngs = []; s = p = missing[0]
        for x in missing[1:]:
            if x == p + 1: p = x
            else: rngs.append((s, p)); s = p = x
        rngs.append((s, p))
        print(f"MISSING {len(missing)} cues: " + ", ".join(f"{a}-{b}" if a!=b else f"{a}" for a,b in rngs[:15]))
        if "--status" not in sys.argv:
            print("\nNot writing SRT until all cues are translated (use --status to just check).")
        return
    # all present -> write SRT
    out = []
    for i, (num, ts) in enumerate(cues, 1):
        out.append(f"{i}\n{ts}\n{em[num]}")
    OUT.write_text("\n\n".join(out) + "\n", encoding="utf-8")
    print(f"\nAll cues translated. Wrote {OUT} ({len(cues)} cues).")


if __name__ == "__main__":
    main()
