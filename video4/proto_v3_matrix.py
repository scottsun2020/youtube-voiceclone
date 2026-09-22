"""Accent-neutralizing matrix on the 1-min clip. Vary similarity_boost /
use_speaker_boost (looser clone -> more generic/neutral English, less native
Cantonese/Indian lean). Reuses the 2-chunk approach for voice consistency.
Each variant -> its own output so nothing is overwritten.
Usage: python video4/proto_v3_matrix.py
"""
import os, wave, subprocess
from pathlib import Path
from proto_v3_chunk import CHUNKS, TRANSITION_PAUSE, SRC, SR, CMAX, decode

OUTDIR = Path("video4/output"); OUTDIR.mkdir(parents=True, exist_ok=True)

# (label, voice_settings kwargs, accent_tag)
# Round 2: sim=0.3 locked, speaker_boost ON (was OFF in a/c). d = +American tag, e = control.
VARIANTS = [
    ("v3m_d_sim03_sb_amer", dict(stability=0.5, similarity_boost=0.3, use_speaker_boost=True), "[American accent] "),
    ("v3m_e_sim03_sb",      dict(stability=0.5, similarity_boost=0.3, use_speaker_boost=True), ""),
]


def gen_chunks(seg, vs, tag, client, voice_id):
    from elevenlabs import VoiceSettings
    seg.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(CHUNKS):
        p = seg / f"chunk_{i}.mp3"
        if p.exists() and p.stat().st_size > 0: continue
        t = (tag + text) if tag else text
        audio = client.text_to_speech.convert(voice_id=voice_id, text=t,
            model_id="eleven_v3", output_format="mp3_44100_128",
            voice_settings=VoiceSettings(**vs))
        with open(p, "wb") as f:
            for c in audio: f.write(c)


def build(seg, out_wav, out_mp4):
    target = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1",SRC],capture_output=True,text=True).stdout)
    pcms = [decode(seg / f"chunk_{i}.mp3") for i in range(len(CHUNKS))]
    speech = sum(len(p)/2/SR for p in pcms)
    if speech + TRANSITION_PAUSE > target:
        comp = min(CMAX, speech/(target-TRANSITION_PAUSE))
        pcms = [decode(seg / f"chunk_{i}.mp3", comp) for i in range(len(CHUNKS))]
    silence = lambda sec: b"\x00\x00"*int(round(max(0.0,sec)*SR))
    out = bytearray()
    for i, pcm in enumerate(pcms):
        out += pcm
        if i < len(pcms)-1: out += silence(TRANSITION_PAUSE)
    if len(out)/2/SR < target: out += silence(target-len(out)/2/SR)
    with wave.open(str(out_wav),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(out))
    subprocess.run(["ffmpeg","-y","-v","error","-i",SRC,"-i",str(out_wav),
        "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","192k",
        "-metadata:s:a:0","language=eng","-movflags","+faststart",out_mp4], check=True)


def main():
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs
    load_dotenv(str(Path(".env").resolve()))
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    voice_id = open(".voice_id").read().strip()
    for label, vs, tag in VARIANTS:
        seg = Path(f"video4/audio/segments_{label}")
        out_mp4 = str(OUTDIR / f"test1min_{label}.mp4")
        print(f"[{label}] sim={vs['similarity_boost']} speaker_boost={vs['use_speaker_boost']} tag='{tag}'")
        gen_chunks(seg, vs, tag, client, voice_id)
        build(seg, Path(f"video4/audio/test1min_dub_{label}.wav"), out_mp4)
        print(f"  -> {out_mp4}")
    print("Done. Compare all variants.")


if __name__ == "__main__":
    main()
