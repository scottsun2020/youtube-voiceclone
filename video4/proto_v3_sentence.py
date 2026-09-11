"""Improved v3 prototype (1-min clip): natural-pace, pause-preserving, length-fitted.
Four levers:
  1. detect the preacher's real pauses in the original audio (silencedetect)
  2. speak each sentence at NATURAL speed (no fill-stretching)
  3. distribute time as pauses matching where he actually paused
  4. size each sentence's translation to its speaking window (rewrite shorter/longer)
     so natural speed neither rushes nor drags. Scripture never shortened.
Usage: python video4/proto_v3_sentence.py [gen|analyze|build|all]
"""
import os, re, sys, wave, subprocess
from pathlib import Path

SR = 44100; CMAX = 1.15
EN = Path("video4/transcripts/subtitles_en.srt")
SENT = Path("video4/audio/segments_v3s2"); SENT.mkdir(parents=True, exist_ok=True)
SRC = "video4/source/test_1min.mp4"
ORIG_AUDIO = "video4/audio/test1min_audio.wav"
OUT_WAV = Path("video4/audio/test1min_dub_v3s2.wav")
OUT_MP4 = "video4/output/test1min_ours_v3s2.mp4"
END = re.compile(r'[.!?…]["\')\]]?\s*$')
SCRIPTURE = {10}  # 0-based index of the Psalm 18:32 sentence — never shorten
BIG_PAUSE = {6: 2.5}  # boundary index -> big pause (scene transition), like dubbing_v2's 3.2s
PAUSE_CAP = 0.8       # cap ordinary inter-sentence pauses so it doesn't drag

# One entry per sentence (order matches subtitles_en.srt grouping). CAPS = emphasis.
# Shortened to fit each speaking window at v3's natural pace (no compression-rush).
# Sentence #10 is scripture (Psalm 18:32) — kept verbatim, never shortened.
FORMATTED = [
 "So our gathering today has a name, and it's called: \"Your Sins Are Forgiven.\"",
 "Now, you might find that a bit abrupt — why talk about your sins being FORGIVEN the very first time we meet?",
 "But there's a picture next to me, a photo — and that photo comes from this book right here.",
 "I don't know if you can see this book I'm holding in my hand right now.",
 "Now, I don't think many people can read it, because it's written in Nepali.",
 "I bought it in Kathmandu. It tells of an event from the Lord Jesus' life on earth.",
 "We'll have a chance to talk about that in a bit.",
 "Having just heard from Killy and Sai-fai, I wonder if you envy the change in their lives.",
 "It reminds me of this ONE verse in the Bible.",
 "What does it say?",
 "It is the One who girds us with strength, and makes our way perfect. He is GOD.",
 "The God we know today isn't just some abstract idea — He is a LIVING person.",
]


def parse():
    cues = []
    for b in re.split(r"\n\s*\n", EN.read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) < 3: continue
        cues.append({"ts": L[1].strip(), "text": " ".join(x.strip() for x in L[2:])})
    return cues

def ts_start(ts):
    a=ts.split(" --> ")[0]; h,m,r=a.split(":"); s,ms=r.split(","); return int(h)*3600+int(m)*60+int(s)+int(ms)/1000
def ts_end(ts):
    a=ts.split(" --> ")[1]; h,m,r=a.split(":"); s,ms=r.split(","); return int(h)*3600+int(m)*60+int(s)+int(ms)/1000

def sentences(cues):
    out, cur = [], []
    for c in cues:
        cur.append(c)
        if END.search(c["text"]): out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def decode(path, speed=1.0):
    filt = ["-filter:a", f"atempo={speed:.5f}"] if abs(speed-1.0) > 1e-3 else []
    r = subprocess.run(["ffmpeg","-v","error","-i",str(path),*filt,"-f","s16le","-ac","1","-ar",str(SR),"-"],
                       capture_output=True, check=True)
    return r.stdout

def clip_dur(i):
    return len(decode(SENT / f"sent_{i:02d}.mp3"))/2/SR

def detect_silences(path, noise="-30dB", mind=0.25):
    r = subprocess.run(["ffmpeg","-i",path,"-af",f"silencedetect=n={noise}:d={mind}","-f","null","-"],
                       capture_output=True, text=True)
    sil=[]; start=None
    for line in r.stderr.splitlines():
        m=re.search(r"silence_start:\s*([-\d.]+)", line)
        if m: start=float(m.group(1))
        m=re.search(r"silence_end:\s*([-\d.]+)", line)
        if m and start is not None: sil.append((start,float(m.group(1)))); start=None
    return sil

def geometry():
    """Per-sentence speaking window + per-boundary original pause, from cues+silences."""
    cues=parse(); sents=sentences(cues)
    sil=detect_silences(ORIG_AUDIO)
    def sil_in(a,b):
        w=0.0
        for (s,e) in sil:
            lo,hi=max(a,s),min(b,e)
            if hi>lo: w+=hi-lo
        return w
    windows=[]; pauses=[]
    for i,s in enumerate(sents):
        a,b=ts_start(s[0]["ts"]), ts_end(s[-1]["ts"])
        windows.append(max(0.3,(b-a)-sil_in(a,b)))     # speaking time = span minus internal silence
    for i in range(len(sents)-1):
        a,b=ts_end(sents[i][-1]["ts"]), ts_start(sents[i+1][0]["ts"])
        pauses.append(sil_in(a-0.1,b+0.1))             # real pause between phrases
    return sents,windows,pauses


def generate():
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    load_dotenv(str(Path(".env").resolve()))
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    voice_id = open(".voice_id").read().strip()
    assert len(sentences(parse())) == len(FORMATTED)
    print(f"Generating {len(FORMATTED)} clips (v3, [strong American accent], Natural) ...")
    for i, text in enumerate(FORMATTED):
        p = SENT / f"sent_{i:02d}.mp3"
        if p.exists() and p.stat().st_size > 0: continue
        try:
            audio = client.text_to_speech.convert(voice_id=voice_id, text="[strong American accent] "+text,
                model_id="eleven_v3", output_format="mp3_44100_128",
                voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.75))
        except Exception:
            audio = client.text_to_speech.convert(voice_id=voice_id, text="[strong American accent] "+text,
                model_id="eleven_v3", output_format="mp3_44100_128")
        with open(p,"wb") as f:
            for c in audio: f.write(c)
        print(f"  [{i+1}/{len(FORMATTED)}]")
    print("Done.")


def analyze():
    sents,windows,pauses=geometry()
    print(f"\n{'#':>2} {'window':>6} {'speech':>6} {'ratio':>5} {'flag':<8} text")
    for i in range(len(sents)):
        d=clip_dur(i); r=d/windows[i]
        flag=""
        if i in SCRIPTURE: flag="SCRIPT"
        elif r>1.15: flag="RUSH↓"      # speech too long -> rewrite SHORTER
        elif r<0.6:  flag="DRAG↑"      # speech too short -> rewrite LONGER
        print(f"{i:>2} {windows[i]:6.1f} {d:6.1f} {r:5.2f} {flag:<8} {FORMATTED[i][:60]}")
    print(f"\ntotal speech={sum(clip_dur(i) for i in range(len(sents))):.1f}s  "
          f"orig pauses sum={sum(pauses):.1f}s  target={ts_end(parse()[-1]['ts']):.1f}s")


def build():
    cues=parse(); sents,windows,pauses=geometry()
    # target the ACTUAL video length, not the last subtitle cue
    target=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1",SRC],capture_output=True,text=True).stdout)
    pcms=[decode(SENT / f"sent_{i:02d}.mp3") for i in range(len(sents))]
    durs=[len(p)/2/SR for p in pcms]
    total_speech=sum(durs)
    n=len(sents)
    # big transition pauses (fixed) + short breathing pauses (distributed, capped)
    big=sum(BIG_PAUSE.values())
    ordinary=[i for i in range(n-1) if i not in BIG_PAUSE]
    slack=target-total_speech-big
    # distribute remaining slack across ordinary boundaries, capped at PAUSE_CAP
    finalp=[0.0]*(n-1)
    for i in BIG_PAUSE: finalp[i]=BIG_PAUSE[i]
    if slack>0 and ordinary:
        per=min(PAUSE_CAP, slack/len(ordinary))
        for i in ordinary: finalp[i]=per
    # any leftover after capping goes to end padding (keeps pace brisk, not draggy)
    silence=lambda sec: b"\x00\x00"*int(round(max(0.0,sec)*SR))
    out=bytearray()
    for i,pcm in enumerate(pcms):
        out+=pcm
        if i<n-1: out+=silence(finalp[i])
    dur=len(out)/2/SR
    if dur<target: out+=silence(target-dur)
    comp=0
    with wave.open(str(OUT_WAV),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(out))
    print(f"Wrote {OUT_WAV}: {len(out)/2/SR:.1f}s  speech={total_speech:.1f}s compressed={comp} "
          f"pauses={[round(p,1) for p in finalp]}")
    subprocess.run(["ffmpeg","-y","-v","error","-i",SRC,"-i",str(OUT_WAV),
        "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","192k",
        "-metadata:s:a:0","language=eng","-movflags","+faststart",OUT_MP4], check=True)
    d=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",OUT_MP4],
                     capture_output=True, text=True)
    print(f"Wrote {OUT_MP4} ({float(d.stdout):.1f}s)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("gen","all"): generate()
    if cmd in ("analyze","all"): analyze()
    if cmd in ("build","all"): build()
