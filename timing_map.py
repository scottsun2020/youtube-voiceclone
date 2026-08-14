"""Dry-run timing map for segment-anchored dubbing (no API calls).

Estimates how long each English SRT segment will take to speak in the cloned
voice (calibrated to the actual 38-chunk run), compares it to the segment's SRT
slot, and reports how much silence padding vs. speed-up compression each needs.
"""
import re
import csv
from pathlib import Path

SRT = Path("transcripts/subtitles_en.srt")

# --- Calibration from the real run ---------------------------------------
# 38 generated chunks totalled 1946.5s of speech for the full transcript.
ACTUAL_SPEECH_S = 1946.5

def parse(path):
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    segs = []
    for b in blocks:
        L = b.strip().splitlines()
        if len(L) < 3:
            continue
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", L[1])
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        start = h1*3600 + m1*60 + s1 + ms1/1000
        end = h2*3600 + m2*60 + s2 + ms2/1000
        idx = L[0].strip()
        text = " ".join(x.strip() for x in L[2:])
        segs.append({"idx": idx, "start": start, "end": end, "text": text})
    return segs

segs = parse(SRT)

# Calibrate a char/sec rate to the actual run so per-segment estimates match
# the real voice, model, and pacing (includes punctuation pauses on average).
total_chars = sum(len(s["text"]) for s in segs)
chars_per_s = total_chars / ACTUAL_SPEECH_S          # ~15.9 chars/s
print(f"Calibration: {total_chars:,} chars / {ACTUAL_SPEECH_S:.0f}s "
      f"= {chars_per_s:.2f} chars/s  ({total_chars/ (ACTUAL_SPEECH_S/60):.0f} cps/min)\n")

# --- Per-segment timing --------------------------------------------------
for i, s in enumerate(segs):
    slot = s["end"] - s["start"]
    gap_after = (segs[i+1]["start"] - s["end"]) if i + 1 < len(segs) else 0.0
    est = len(s["text"]) / chars_per_s
    s["slot"] = slot
    s["gap_after"] = gap_after
    s["est"] = est
    s["headroom"] = slot - est                        # + => pad, - => compress
    # speed-up factor needed to fit inside the slot (1.0 = none)
    s["speedup"] = max(1.0, est / slot) if slot > 0 else float("inf")

# --- Summary -------------------------------------------------------------
span = segs[-1]["end"] - segs[0]["start"]
total_slot = sum(s["slot"] for s in segs)
total_est = sum(s["est"] for s in segs)
pad_avail = sum(s["headroom"] for s in segs if s["headroom"] > 0)
comp_need = sum(-s["headroom"] for s in segs if s["headroom"] < 0)

print(f"SRT span:              {span:8.1f}s = {span/60:5.1f} min")
print(f"Sum of slots:          {total_slot:8.1f}s = {total_slot/60:5.1f} min")
print(f"Est. total speech:     {total_est:8.1f}s = {total_est/60:5.1f} min")
print(f"Net headroom:          {total_slot-total_est:8.1f}s "
      f"({'plenty of slack' if total_slot>total_est else 'OVER budget'})\n")
print(f"Silence padding to add (slack segments): {pad_avail:7.1f}s = {pad_avail/60:.1f} min")
print(f"Compression needed (overrun segments):   {comp_need:7.1f}s = {comp_need/60:.1f} min\n")

# Problem buckets by required speed-up
buckets = [(1.0, 1.05, "fits (<=1.05x, imperceptible)"),
           (1.05, 1.15, "mild speed-up (1.05-1.15x, fine)"),
           (1.15, 1.30, "noticeable (1.15-1.30x, review)"),
           (1.30, 1.60, "rushed (1.30-1.60x, likely fix text)"),
           (1.60, 99, "severe (>1.60x, must fix text/timing)")]
print("Segments by required speed-up:")
for lo, hi, label in buckets:
    n = sum(1 for s in segs if lo <= s["speedup"] < hi)
    print(f"  {label:42s}: {n:4d}")

# --- Worst offenders -----------------------------------------------------
overruns = sorted((s for s in segs if s["speedup"] > 1.15),
                  key=lambda s: s["speedup"], reverse=True)
print(f"\n{len(overruns)} segments need >1.15x. Worst 25:")
print(f"  {'seg':>4} {'slot':>6} {'est':>6} {'x':>5}  text")
for s in overruns[:25]:
    print(f"  {s['idx']:>4} {s['slot']:6.1f} {s['est']:6.1f} {s['speedup']:5.2f}  "
          f"{s['text'][:60]}")

# --- Full CSV for review -------------------------------------------------
out = Path("transcripts/timing_map.csv")
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["seg", "start", "end", "slot_s", "gap_after_s",
                "est_speech_s", "headroom_s", "speedup_x", "chars", "text"])
    for s in segs:
        w.writerow([s["idx"], f"{s['start']:.2f}", f"{s['end']:.2f}",
                    f"{s['slot']:.2f}", f"{s['gap_after']:.2f}",
                    f"{s['est']:.2f}", f"{s['headroom']:.2f}",
                    f"{s['speedup']:.3f}", len(s["text"]), s["text"]])
print(f"\nFull map written to {out}")
