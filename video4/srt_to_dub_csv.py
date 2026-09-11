"""Convert an SRT into an ElevenLabs Dubbing CSV (seconds format).
Columns: speaker,start_time,end_time,transcription,translation
- start/end are decimal seconds (e.g. 0.1, 1.15) per ElevenLabs' template.
- transcription = the SRT text; translation left blank by default so ElevenLabs
  translates from our (accurate) transcript. Pass a second SRT to fill it.

Usage:
  python video4/srt_to_dub_csv.py IN_zh.srt OUT.csv [EN.srt]
"""
import re, sys, csv
from pathlib import Path

CJK = re.compile(r"[㐀-鿿]")


def parse(p):
    cues = []
    for b in re.split(r"\n\s*\n", Path(p).read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) < 3:
            continue
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", L[1])
        if not m:
            continue
        g = list(map(int, m.groups()))
        s = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000
        e = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000
        body = [x.strip() for x in L[2:]]
        # join wrapped display lines: no space for CJK, space for Latin
        sep = "" if any(CJK.search(x) for x in body) else " "
        cues.append((s, e, sep.join(body)))
    return cues


def fmt(t):
    return f"{t:.3f}".rstrip("0").rstrip(".")  # 2.000 -> "2", 1.150 -> "1.15"


def main(in_srt, out_csv, en_srt=None):
    zh = parse(in_srt)
    en = parse(en_srt) if en_srt else None
    if en is not None and len(en) != len(zh):
        sys.exit(f"count mismatch: {len(zh)} zh vs {len(en)} en cues")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["speaker", "start_time", "end_time", "transcription", "translation"])
        for i, (s, e, text) in enumerate(zh):
            trans = en[i][2] if en is not None else ""
            w.writerow(["1", fmt(s), fmt(e), text, trans])
    print(f"Wrote {out_csv}: {len(zh)} rows"
          + (f" (with translation from {en_srt})" if en_srt else " (translation blank)"))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: srt_to_dub_csv.py IN_zh.srt OUT.csv [EN.srt]")
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
