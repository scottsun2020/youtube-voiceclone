"""Video 2 dub: sentence-level adaptive assembly (<=1.25x slow-down + short
pauses), using the one rewritten sentence (#92) where present and the existing
segment clips elsewhere. Muxes with the concise subtitles.
Usage: python video2/build_dub.py [gen|build|all]
"""
import os, re, sys, wave, subprocess
from pathlib import Path

SR = 44100
LMAX = 1.25
CMAX = 1.15
EN = Path("video2/transcripts/subtitles_en.srt")
SEG = Path("video2/audio/segments")
SENT = Path("video2/audio/dubbing_sentences")
SRC = "video2/source/original.mp4"
OUT_WAV = Path("video2/audio/english_dub.wav")
OUT_MP4 = "video2/output/final_english_v2.mp4"
END = re.compile(r'[.!?…]["\')\]]?\s*$')

REWRITES = {
92:"And that's exactly why this outbreak has been given the name a 'pandemic' — meaning an outbreak that has spread right across the entire globe.",
}


def parse():
    segs = []
    for b in re.split(r"\n\s*\n", EN.read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) < 3:
            continue
        segs.append({"i": len(segs), "ts": L[1].strip(),
                     "text": " ".join(x.strip() for x in L[2:])})
    return segs


def sentences(segs):
    out, cur = [], []
    for s in segs:
        cur.append(s)
        if END.search(s["text"]):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def t2s(ts):
    a = ts.split(" --> ")[0]
    h, m, rest = a.split(":"); s, ms = rest.split(",")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000


def decode(path, speed=1.0):
    filt = ["-filter:a", f"atempo={speed:.5f}"] if abs(speed-1.0) > 1e-3 else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), *filt,
                        "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                       capture_output=True, check=True)
    return r.stdout


def decode_pcm(pcm, speed):
    if abs(speed-1.0) <= 1e-3:
        return pcm
    p = subprocess.run(["ffmpeg", "-v", "error", "-f", "s16le", "-ac", "1", "-ar", str(SR),
                        "-i", "-", "-filter:a", f"atempo={speed:.5f}",
                        "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                       input=pcm, capture_output=True, check=True)
    return p.stdout


def generate():
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs
    load_dotenv(str(Path(".env").resolve()))
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    voice_id = open(".voice_id").read().strip()
    sents = sentences(parse())
    SENT.mkdir(parents=True, exist_ok=True)
    for n, text in sorted(REWRITES.items()):
        p = SENT / f"sent_{n:03d}.mp3"
        if p.exists() and p.stat().st_size > 0:
            print(f"  #{n} skip"); continue
        prev = " ".join(x["text"] for x in sents[n-2]) if n-2 >= 0 else None
        nxt = " ".join(x["text"] for x in sents[n]) if n < len(sents) else None
        audio = client.text_to_speech.convert(
            voice_id=voice_id, text=text, model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128", previous_text=prev, next_text=nxt)
        with open(p, "wb") as f:
            for c in audio:
                f.write(c)
        print(f"  #{n} generated ({len(text)} chars)")


def build():
    segs = parse()
    sents = sentences(segs)
    target = t2s(segs[-1]["ts"])
    silence = lambda sec: b"\x00\x00" * int(round(max(0.0, sec)*SR))
    out = bytearray(); cursor = 0.0; slowed = comp = 0; peak = 0.0
    for si, sent in enumerate(sents):
        n = si + 1
        start = t2s(sent[0]["ts"])
        if cursor < start:
            out += silence(start-cursor); cursor = start
        if n in REWRITES:
            natural = decode(SENT / f"sent_{n:03d}.mp3")
        else:
            natural = b"".join(decode(SEG / f"seg_{s['i']:03d}.mp3") for s in sent)
        dur = len(natural)/2/SR
        nxt = t2s(sents[si+1][0]["ts"]) if si+1 < len(sents) else target
        avail = nxt - cursor
        if avail <= 0:
            speed = CMAX
        elif dur > avail:
            speed = min(CMAX, dur/avail); comp += 1
        else:
            L = min(LMAX, avail/dur); speed = 1.0/L
            if L > 1.001:
                slowed += 1
        pcm = decode_pcm(natural, speed)
        out += pcm; cursor += len(pcm)/2/SR
        if cursor > nxt:
            peak = max(peak, cursor-nxt)
    if cursor < target:
        out += silence(target-cursor); cursor = target
    with wave.open(str(OUT_WAV), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(out))
    print(f"Wrote {OUT_WAV}: {cursor/60:.2f} min  slowed={slowed} comp={comp} peak_drift={peak:.2f}s")
    Path("video2/output").mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", SRC, "-i", str(OUT_WAV), "-i", str(EN),
                    "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-c:s", "mov_text",
                    "-metadata:s:a:0", "language=eng", "-metadata:s:s:0", "language=eng",
                    "-movflags", "+faststart", OUT_MP4], check=True)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", OUT_MP4], capture_output=True, text=True)
    print(f"Wrote {OUT_MP4} ({float(d.stdout)/60:.2f} min)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("gen", "all"):
        generate()
    if cmd in ("build", "all"):
        build()
