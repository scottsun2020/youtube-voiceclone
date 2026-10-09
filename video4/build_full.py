"""Video 4 full build: chunked eleven_v3 dub of the 54-min sermon.
- Locked "variant d" recipe: eleven_v3, [American accent], stability 0.5,
  similarity_boost 0.3, use_speaker_boost True (see reference-elevenlabs-model-comparison).
- Dubs SPEECH only (cues 1-866 and 904-1016). The hymn (867-903, 43:39-48:30)
  is NOT dubbed — the original singing is spliced back in.
- Chunks the speech at ~SPAN-second sentence boundaries -> one coherent v3 pass
  per chunk (consistent voice); places each at its start time, mild-compress if
  it overruns, natural pause otherwise.
Usage: python video4/build_full.py [gen|build|all]
"""
import os, re, sys, wave, subprocess
from pathlib import Path

SR = 44100; CMAX = 1.15; SPAN = 90.0; STRETCH = 1.15
MODEL = "eleven_v4"
SIM = 0.8            # v4 holds the accent, so high sim keeps the preacher's voice identity
STAB = 0.5
EN = Path("video4/transcripts/subtitles_en.srt")
SRC = "video4/source/video4_full.mp4"
HYMN_WAV = "video4/audio/hymn_original.wav"
HYMN_START = 2619.2   # cue 866 end
HYMN_END = 2910.0     # cue 904 start
CHUNKS = Path("video4/audio/chunks_full"); CHUNKS.mkdir(parents=True, exist_ok=True)
OUT_WAV = Path("video4/audio/video4_full_dub_v4.wav")
OUT_MP4 = "video4/output/video4_full_english_v4.mp4"
SUBS = "video4/transcripts/subtitles_en_dub.srt"   # voice-matched, emitted by build()
ACCENT = "[American accent] "
END = re.compile(r'[.!?"]\s*$')


def parse():
    out = []
    for b in re.split(r"\n\s*\n", EN.read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) < 3: continue
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", L[1])
        g = list(map(int, m.groups())); s = g[0]*3600+g[1]*60+g[2]+g[3]/1000; e = g[4]*3600+g[5]*60+g[6]+g[7]/1000
        out.append({"n": int(L[0]), "s": s, "e": e, "t": " ".join(x.strip() for x in L[2:])})
    return out


def chunks():
    """Group speech cues (excluding the hymn range) into ~SPAN-second chunks,
    split at sentence boundaries. Returns list of {start,end,text,region}."""
    cues = [c for c in parse() if c["e"] <= HYMN_START + 0.01 or c["s"] >= HYMN_END - 0.01]
    out = []; cur = []
    for c in cues:
        # force a break at the hymn gap
        if cur and cur[-1]["e"] <= HYMN_START and c["s"] >= HYMN_END:
            out.append(cur); cur = []
        cur.append(c)
        span = cur[-1]["e"] - cur[0]["s"]
        if span >= SPAN and END.search(c["t"]):
            out.append(cur); cur = []
    if cur: out.append(cur)
    return [{"start": g[0]["s"], "end": g[-1]["e"],
             "text": " ".join(x["t"] for x in g if x["t"]),
             "cues": g,
             "region": 1 if g[-1]["e"] <= HYMN_START else 2} for g in out]


def decode(path, speed=1.0):
    filt = ["-filter:a", f"atempo={speed:.5f}"] if abs(speed-1.0) > 1e-3 else []
    r = subprocess.run(["ffmpeg","-v","error","-i",str(path),*filt,"-f","s16le","-ac","1","-ar",str(SR),"-"],
                       capture_output=True, check=True)
    return r.stdout


def generate():
    import time
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    load_dotenv(str(Path(".env").resolve()))
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"], timeout=600)
    voice_id = open(".voice_id").read().strip()
    ch = chunks()
    print(f"{len(ch)} chunks to generate (~{sum(len(c['text']) for c in ch)} chars)")
    for i, c in enumerate(ch):
        p = CHUNKS / f"chunk_{i:03d}.mp3"
        if p.exists() and p.stat().st_size > 0: continue
        for attempt in range(4):
            try:
                audio = client.text_to_speech.convert(voice_id=voice_id, text=ACCENT + c["text"],
                    model_id=MODEL, output_format="mp3_44100_128",
                    voice_settings=VoiceSettings(stability=STAB, similarity_boost=SIM),
                    request_options={"timeout_in_seconds": 600})
                data = b"".join(audio)
                if len(data) < 1000:
                    raise RuntimeError(f"suspiciously small ({len(data)} bytes)")
                with open(p, "wb") as f:
                    f.write(data)
                break
            except Exception as e:
                print(f"  chunk {i} attempt {attempt+1} failed: {type(e).__name__}: {str(e)[:80]}")
                if p.exists(): p.unlink()
                time.sleep(5 * (attempt + 1))
        else:
            print(f"  chunk {i} FAILED after 4 attempts — rerun to resume")
        if (i+1) % 5 == 0 or i == len(ch)-1: print(f"  [{i+1}/{len(ch)}]")
    print("Done generating.")


def ts(t):
    h=int(t//3600); m=int(t%3600//60); s=t%60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def build():
    ch = chunks()
    allc = parse()
    target = allc[-1]["e"]
    hymn_cues = [c for c in allc if HYMN_START-0.01 < c["s"] < HYMN_END+0.01]  # 867-903 (orig timing)
    silence = lambda sec: b"\x00\x00" * int(round(max(0.0, sec)*SR))
    out = bytearray(); cursor = 0.0; comp = 0; peak = 0.0
    subs = []   # voice-matched caption cues (start, end, text)
    for i, c in enumerate(ch):
        # splice original hymn audio just before the first region-2 chunk
        if c["region"] == 2 and cursor < HYMN_END:
            if cursor < HYMN_START: out += silence(HYMN_START - cursor)
            out += decode(HYMN_WAV); cursor = HYMN_END
            for hc in hymn_cues:
                if hc["t"]: subs.append((hc["s"], hc["e"], hc["t"]))  # keep original timing (singing)
        start = c["start"]
        if cursor < start: out += silence(start - cursor); cursor = start
        natural = decode(CHUNKS / f"chunk_{i:03d}.mp3")
        dur = len(natural)/2/SR
        nxt = ch[i+1]["start"] if i+1 < len(ch) else target
        if i+1 < len(ch) and c["region"] == 1 and ch[i+1]["region"] == 2:
            nxt = HYMN_START
        avail = nxt - cursor
        if avail <= 0: speed = CMAX
        elif dur > avail: speed = min(CMAX, dur/avail); comp += 1
        else:
            fillstretch = min(STRETCH, avail/dur)   # gentle slow-down to fill the slot
            speed = 1.0/fillstretch
        pcm = decode(CHUNKS / f"chunk_{i:03d}.mp3", speed) if abs(speed-1.0) > 1e-3 else natural
        seg_start = cursor
        out += pcm; cursor += len(pcm)/2/SR
        # voice-matched captions: distribute this chunk's actual audio span across its cues by char length
        spoken = [cc for cc in c["cues"] if cc["t"]]
        tot = sum(len(cc["t"]) for cc in spoken) or 1
        t = seg_start
        for cc in spoken:
            w = (cursor - seg_start) * len(cc["t"]) / tot
            subs.append((t, t + w, cc["t"])); t += w
        if cursor > nxt: peak = max(peak, cursor - nxt)
    if cursor < target: out += silence(target - cursor)
    with wave.open(str(OUT_WAV), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(out))
    print(f"Wrote {OUT_WAV}: {len(out)/2/SR/60:.2f} min  chunks={len(ch)} compressed={comp} peak_drift={peak:.1f}s")
    # write voice-matched subtitle, then split long cues for display
    subs.sort(key=lambda x: x[0])
    raw = Path("video4/transcripts/subtitles_en_dub_raw.srt")
    with raw.open("w", encoding="utf-8") as f:
        for j, (a, b, txt) in enumerate(subs, 1):
            f.write(f"{j}\n{ts(a)} --> {ts(b)}\n{txt}\n\n")
    subprocess.run(["python","video4/split_long_cues.py",str(raw),SUBS,"8.0"], check=True)
    subprocess.run(["ffmpeg","-y","-v","error","-i",SRC,"-i",str(OUT_WAV),"-i",SUBS,
        "-map","0:v:0","-map","1:a:0","-map","2:s:0","-c:v","copy","-c:a","aac","-b:a","192k",
        "-c:s","mov_text","-metadata:s:a:0","language=eng","-metadata:s:s:0","language=eng",
        "-movflags","+faststart",OUT_MP4], check=True)
    d = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",OUT_MP4],
                       capture_output=True, text=True)
    print(f"Wrote {OUT_MP4} ({float(d.stdout)/60:.2f} min)  subs->{SUBS}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("gen","all"): generate()
    if cmd in ("build","all"): build()
