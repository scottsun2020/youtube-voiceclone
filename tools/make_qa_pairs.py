"""Build a QA-pair file (ZH source vs EN translation) for the translation-QA subagent.

Pairs each cue's authentic Chinese source (subtitles_zh_*.srt) with its English
translation (en_map.txt, 'N|english'), by cue number. Output is a plain text file
the translation-qa subagent reads.

Usage:
  python tools/make_qa_pairs.py VIDEO_DIR [START END] [--zh SRT_NAME]
Examples:
  python tools/make_qa_pairs.py video5                 # all cues
  python tools/make_qa_pairs.py video5 358 456         # just a region
  python tools/make_qa_pairs.py video4 --zh subtitles_zh_full_working.srt
"""
import re, sys
from pathlib import Path


def parse_srt(p):
    out = {}
    for b in Path(p).read_text(encoding="utf-8").strip().split("\n\n"):
        L = b.strip().split("\n")
        if len(L) >= 3 and L[0].strip().isdigit():
            out[int(L[0])] = " ".join(x.strip() for x in L[2:])
    return out


def parse_map(p):
    out = {}
    for ln in Path(p).read_text(encoding="utf-8").splitlines():
        if "|" in ln and ln.split("|", 1)[0].strip().isdigit():
            n, t = ln.split("|", 1)
            out[int(n)] = t.strip()
    return out


def main(argv):
    vdir = argv[0]
    zh_name = "subtitles_zh_canto.srt"
    if "--zh" in argv:
        zh_name = argv[argv.index("--zh") + 1]
    nums = [a for a in argv[1:] if a.isdigit()]
    start = int(nums[0]) if len(nums) >= 1 else None
    end = int(nums[1]) if len(nums) >= 2 else None

    zh = parse_srt(f"{vdir}/transcripts/{zh_name}")
    en = parse_map(f"{vdir}/transcripts/en_map.txt")
    keys = sorted(set(zh) | set(en))
    if start is not None:
        keys = [k for k in keys if k >= start]
    if end is not None:
        keys = [k for k in keys if k <= end]

    out = []
    for n in keys:
        out.append(f"[{n}]\nZH: {zh.get(n,'(missing)')}\nEN: {en.get(n,'(missing)')}")
    tag = f"_{start}-{end}" if start is not None else ""
    outp = f"{vdir}/transcripts/qa_pairs{tag}.txt"
    Path(outp).write_text("\n\n".join(out), encoding="utf-8")
    print(f"wrote {len(out)} cue pairs -> {outp}")


if __name__ == "__main__":
    if not sys.argv[1:]:
        sys.exit(__doc__)
    main(sys.argv[1:])
