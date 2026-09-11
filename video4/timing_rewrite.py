"""Video 2: after clips exist, measure fill ratios, run the sentence-level
adaptive-slowdown (<=1.25x) model, and emit the outlier rephrase punch-list
(sentences still leaving a >4s gap). Flags likely scripture vs narration.
-> video4/transcripts/rewrite_list.md / .json  (no API, no audio written)
"""
import re, subprocess, json, statistics as st
from pathlib import Path

EN = Path("video4/transcripts/subtitles_en.srt")
ZH = Path("video4/transcripts/subtitles_zh.srt")
SEG = Path("video4/audio/segments")
LMAX = 1.25
GAP_FLAG = 4.0


def parse(p):
    segs = []
    for b in re.split(r"\n\s*\n", Path(p).read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) < 3:
            continue
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", L[1])
        if not m:
            continue
        g = list(map(int, m.groups()))
        segs.append({"start": g[0]*3600+g[1]*60+g[2]+g[3]/1000,
                     "end": g[4]*3600+g[5]*60+g[6]+g[7]/1000,
                     "text": " ".join(x.strip() for x in L[2:])})
    return segs


en = parse(EN); zh = parse(ZH)
for i, s in enumerate(en):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(SEG / f"seg_{i:03d}.mp3")],
                       capture_output=True, text=True)
    s["clip"] = float(r.stdout.strip())
    s["zh"] = zh[i]["text"] if i < len(zh) else ""
    s["i"] = i

END = re.compile(r'[.!?…]["\')\]]?\s*$')
sents = []; cur = []
for s in en:
    cur.append(s)
    if END.search(s["text"]):
        sents.append(cur); cur = []
if cur:
    sents.append(cur)

SCRIP = re.compile(r"\b(take heed|leads you astray|in my name|the christ|wars and rumors|"
    r"nation will rise|kingdom against|famines and earthquakes|birth pains|sword|pestilence|"
    r"sackcloth|the full moon|stars of heaven|fig tree|unripe figs|red heifer|"
    r"the end of the age|a fourth of)\b", re.I)

target = en[-1]["end"]
rows = []; cursor = 0.0
for si, sent in enumerate(sents):
    start = sent[0]["start"]
    if cursor < start:
        cursor = start
    sp = sum(x["clip"] for x in sent)
    slot0 = sent[-1]["end"] - sent[0]["start"]
    nxt = sents[si+1][0]["start"] if si+1 < len(sents) else target
    avail = nxt - cursor
    if sp > avail and avail > 0:
        dur = sp / min(1.15, sp / avail)
    else:
        dur = sp * min(LMAX, avail / sp if sp > 0 else 1)
    cursor += dur; pause = max(0.0, nxt - cursor); cursor = max(cursor, nxt)
    entxt = " ".join(x["text"] for x in sent)
    rows.append({"sent": si+1, "seg_start": sent[0]["i"]+1, "seg_end": sent[-1]["i"]+1,
                 "start": sent[0]["start"], "end": sent[-1]["end"],
                 "tts": round(sp, 2), "slot": round(slot0, 2),
                 "ratio": round(sp/slot0, 3) if slot0 > 0 else 0,
                 "residual_gap": round(pause, 2), "scripture": bool(SCRIP.search(entxt)),
                 "en": entxt, "zh": " ".join(x["zh"] for x in sent)})

out = [r for r in rows if r["residual_gap"] > GAP_FLAG]
out.sort(key=lambda r: -r["residual_gap"])
def hms(t): return f"{int(t//60):02d}:{t%60:05.2f}"
print(f"sentences={len(sents)}  natural_speech={sum(s['clip'] for s in en)/60:.1f}min  "
      f"target={target/60:.1f}min")
print(f"outliers (gap >{GAP_FLAG}s): {len(out)}   (>6s: {sum(1 for r in rows if r['residual_gap']>6)})\n")
print(f"{'#':>3} {'time':>6} {'gap':>5} {'ratio':>5} {'S':>1}  English")
for r in out:
    print(f"{r['sent']:>3} {hms(r['start']):>6} {r['residual_gap']:>4.1f}s {int(r['ratio']*100):>4}% "
          f"{'B' if r['scripture'] else '.'}  {r['en'][:66]}")

md = ["# Video 2 — targeted dubbing rewrite list\n",
      f"After 1.25x adaptive slow-down, these {len(out)} sentences still leave a >{GAP_FLAG}s pause.",
      "**B** = likely scripture (leave verbatim); **.** = narration (safe to expand).\n"]
for r in out:
    md.append(f"### #{r['sent']}  [{hms(r['start'])}–{hms(r['end'])}]  gap {r['residual_gap']}s  ratio {int(r['ratio']*100)}%  "
              f"{'SCRIPTURE — leave' if r['scripture'] else 'narration — expand'}")
    md.append(f"- ZH: {r['zh']}")
    md.append(f"- EN: {r['en']}")
    md.append(f"- TTS {r['tts']}s vs slot {r['slot']}s\n")
Path("video4/transcripts/rewrite_list.md").write_text("\n".join(md))
json.dump(out, open("video4/transcripts/rewrite_list.json", "w"), ensure_ascii=False, indent=2)
print(f"\nWrote video4/transcripts/rewrite_list.md and .json")
