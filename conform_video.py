"""Conform the video to the natural-pace English audio (per-segment).

Instead of padding audio with silence to fill the 46-min video, this keeps the
English clips at natural speed and re-times each original video slice to match
its clip. Result: ~30-min video with perfect audio/video/subtitle sync and no
dead air. Slides (stills) speed up invisibly; the presenter inset can be kept
(full frame) or cropped out.

Usage:
    python conform_video.py [--limit N] [--crop] [--out PATH]
"""
import re
import sys
import subprocess
from pathlib import Path

SRC = "source/source_46min.mp4"
SEG = Path("audio/segments")
TMP = Path("audio/_conform_tmp")
EN = Path("transcripts/subtitles_en.srt")

CROP = "--crop" in sys.argv
limit = None
if "--limit" in sys.argv:
    limit = int(sys.argv[sys.argv.index("--limit") + 1])
out = "output/conform_prototype.mp4" if limit else "output/final_english_conformed.mp4"
if "--out" in sys.argv:
    out = sys.argv[sys.argv.index("--out") + 1]

# Crop keeps the left slide area (896x720, x0..896), dropping the bottom-right inset.
CROP_W = 896


def parse():
    blocks = re.split(r"\n\s*\n", EN.read_text(encoding="utf-8").strip())
    segs = []
    for b in blocks:
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


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


def ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def main():
    segs = parse()
    if limit:
        segs = segs[:limit]
    TMP.mkdir(parents=True, exist_ok=True)
    vlist = TMP / "vlist.txt"
    alist = TMP / "alist.txt"
    subs = []
    cursor = 0.0
    prev_fend = 0                                     # cumulative frame count (25 fps)
    FPS = 25
    print(f"Conforming {len(segs)} segments  (crop={CROP})...")
    with vlist.open("w") as vf, alist.open("w") as af:
        for i, s in enumerate(segs):
            orig = s["end"] - s["start"]
            clip = SEG / f"seg_{i:03d}.mp3"
            tgt = dur(clip)
            # exact integer-frame length via cumulative rounding (no drift accumulation)
            fend = round((cursor + tgt) * FPS)
            nframes = fend - prev_fend
            prev_fend = fend
            factor = tgt / orig                      # speed the slice to ~tgt
            filt = ((f"crop={CROP_W}:720:0:0," if CROP else "")
                    + f"setpts={factor:.6f}*(PTS-STARTPTS),"
                    + "tpad=stop_mode=clone:stop_duration=2")   # clone tail so >= nframes exist
            vout = TMP / f"v_{i:03d}.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error",
                 "-ss", f"{s['start']:.3f}", "-t", f"{orig:.3f}", "-i", SRC,
                 "-an", "-vf", filt, "-r", str(FPS), "-frames:v", str(nframes),
                 "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20",
                 "-preset", "veryfast", str(vout)], check=True)
            vf.write(f"file '{vout.resolve()}'\n")
            af.write(f"file '{clip.resolve()}'\n")
            subs.append((cursor, cursor + tgt, s["text"]))
            cursor += tgt
            if (i + 1) % 25 == 0 or i == len(segs) - 1:
                print(f"  [{i+1}/{len(segs)}]  timeline={cursor:6.1f}s")

    # concat video (same codec/params) and audio (mp3 clips)
    vid = TMP / "video.mp4"
    aud = TMP / "audio.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(vlist), "-c", "copy", str(vid)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(alist), "-c:a", "aac", "-b:a", "192k", str(aud)], check=True)

    # subtitles synced to the new timeline
    srt = TMP / "subs.srt"
    with srt.open("w") as f:
        for n, (a, b, t) in enumerate(subs, 1):
            f.write(f"{n}\n{ts(a)} --> {ts(b)}\n{t}\n\n")

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-i", str(aud),
                    "-i", str(srt), "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
                    "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
                    "-metadata:s:s:0", "language=eng", "-movflags", "+faststart",
                    out], check=True)
    print(f"\nWrote {out}  ({dur(out)/60:.2f} min)")


if __name__ == "__main__":
    main()
