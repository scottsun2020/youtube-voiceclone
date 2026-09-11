"""v3s3 prototype: chunk-level generation for accent/voice CONSISTENCY.
Generate the script in 2 large chunks (split at the scene transition) so each is
one coherent v3 pass -> the American accent and voice timbre stay locked within a
chunk (fixes per-sentence drift). Keep one big pause between chunks. Fit to video.
Usage: python video4/proto_v3_chunk.py [gen|build|all]
"""
import os, sys, wave, subprocess
from pathlib import Path

SR = 44100; CMAX = 1.15
SRC = "video4/source/test_1min.mp4"
SEG = Path("video4/audio/segments_v3s3"); SEG.mkdir(parents=True, exist_ok=True)
OUT_WAV = Path("video4/audio/test1min_dub_v3s3.wav")
OUT_MP4 = "video4/output/test1min_ours_v3s3.mp4"
TRANSITION_PAUSE = 2.5

# Two chunks. Tag once at the start of each (long runway = stable accent).
# Scripture (Psalm 18:32) kept verbatim inside chunk 2.
CHUNKS = [
 "[strong American accent] So our gathering today has a name, and it's called: \"Your Sins Are Forgiven.\" "
 "Now, you might find that a bit abrupt — why talk about your sins being FORGIVEN the very first time we meet? "
 "But there's a picture next to me, a photo — and that photo comes from this book right here. "
 "I don't know if you can see this book I'm holding in my hand right now. "
 "Now, I don't think many people can read it, because it's written in Nepali. "
 "I bought it in Kathmandu. It tells of an event from the Lord Jesus' life on earth. "
 "We'll have a chance to talk about that in a bit.",

 "[strong American accent] Having just heard from Killy and Sai-fai, I wonder if you envy the change in their lives. "
 "It reminds me of this ONE verse in the Bible. What does it say? "
 "It is the One who girds us with strength, and makes our way perfect. He is GOD. "
 "The God we know today isn't just some abstract idea — He is a LIVING person.",
]


def decode(path, speed=1.0):
    filt = ["-filter:a", f"atempo={speed:.5f}"] if abs(speed-1.0) > 1e-3 else []
    r = subprocess.run(["ffmpeg","-v","error","-i",str(path),*filt,"-f","s16le","-ac","1","-ar",str(SR),"-"],
                       capture_output=True, check=True)
    return r.stdout


def generate():
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    load_dotenv(str(Path(".env").resolve()))
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    voice_id = open(".voice_id").read().strip()
    print(f"Generating {len(CHUNKS)} chunks (v3, one coherent pass each) ...")
    for i, text in enumerate(CHUNKS):
        p = SEG / f"chunk_{i}.mp3"
        if p.exists() and p.stat().st_size > 0: continue
        try:
            audio = client.text_to_speech.convert(voice_id=voice_id, text=text,
                model_id="eleven_v3", output_format="mp3_44100_128",
                voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.8))
        except Exception:
            audio = client.text_to_speech.convert(voice_id=voice_id, text=text,
                model_id="eleven_v3", output_format="mp3_44100_128")
        with open(p,"wb") as f:
            for c in audio: f.write(c)
        print(f"  chunk {i+1}/{len(CHUNKS)} ({len(text)} chars)")
    print("Done.")


def build():
    target = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1",SRC],capture_output=True,text=True).stdout)
    pcms = [decode(SEG / f"chunk_{i}.mp3") for i in range(len(CHUNKS))]
    speech = sum(len(p)/2/SR for p in pcms)
    silence = lambda sec: b"\x00\x00"*int(round(max(0.0,sec)*SR))
    total = speech + TRANSITION_PAUSE
    # if chunks overrun the video, compress uniformly (<=1.15x); else pad tail
    comp = 1.0
    if total > target:
        comp = min(CMAX, speech/(target-TRANSITION_PAUSE))
        pcms = [decode(SEG / f"chunk_{i}.mp3", comp) for i in range(len(CHUNKS))]
        speech = sum(len(p)/2/SR for p in pcms)
    out = bytearray()
    for i, pcm in enumerate(pcms):
        out += pcm
        if i < len(pcms)-1: out += silence(TRANSITION_PAUSE)
    dur = len(out)/2/SR
    if dur < target: out += silence(target-dur)
    with wave.open(str(OUT_WAV),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(out))
    print(f"Wrote {OUT_WAV}: {len(out)/2/SR:.1f}s  speech={speech:.1f}s  compress={comp:.3f}x  transition_pause={TRANSITION_PAUSE}s")
    subprocess.run(["ffmpeg","-y","-v","error","-i",SRC,"-i",str(OUT_WAV),
        "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","192k",
        "-metadata:s:a:0","language=eng","-movflags","+faststart",OUT_MP4], check=True)
    d = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",OUT_MP4],
                       capture_output=True, text=True)
    print(f"Wrote {OUT_MP4} ({float(d.stdout):.1f}s)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("gen","all"): generate()
    if cmd in ("build","all"): build()
