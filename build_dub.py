"""Build the final duration-aware English dub (46:00, keep video length).

- Groups the English SRT into sentences (same rule as the rewrite analysis).
- For the 22 approved sentences, uses a freshly TTS'd expanded "dubbing" clip.
- For every other sentence, concatenates its existing per-segment clips.
- Assembles sentence-anchored: each sentence starts at its cue, is gently
  slowed (<=1.25x) to fill its slot, overruns compressed (<=1.15x), and the
  small remainder becomes a natural pause. Pads the tail to 46:00.
- Muxes with the CONCISE subtitles unchanged (two-track: subs != dub script).

Usage: python build_dub.py [gen|build|all]
"""
import os
import re
import sys
import wave
import subprocess
from pathlib import Path

SR = 44100
LMAX = 1.25          # max gentle slow-down (lengthening)
CMAX = 1.15          # max compression for overruns
EN = Path("transcripts/subtitles_en.srt")
SEG = Path("audio/segments")
SENT = Path("audio/dubbing_sentences")
SRC = "source/source_46min.mp4"
OUT_WAV = Path("audio/english_dub_v2.wav")
OUT_MP4 = "output/final_english_v2.mp4"
END = re.compile(r'[.!?…]["\')\]]?\s*$')

# Approved expanded dubbing lines, keyed by sentence number (#147 & #338 trimmed).
REWRITES = {
3:"I think war really serves as a kind of stage — a platform, if you like — where you can see just how astonishing, how formidable, human invention can be in this area.",
14:"And that picture down on the lower left — that one there — that is a torpedo. What you're looking at is the Mk 48, a heavyweight torpedo.",
51:"So from all of these weapons here, from every single one of them, you can really see that the technology behind them is quite advanced — remarkably advanced.",
69:"Why is that? Well, because of the stirrup, the rider could actually stand up on his horse's back, and from there shoot arrows in a full 360 degrees, all around him, pinning his opponent down. And combined with that incredibly powerful bow, they had a famous tactic called the Parthian shot — so don't ever assume they're beaten just because they turn and flee and go chasing after them, because they'll spin right around in the saddle and put an arrow straight in you.",
106:"And the one right next to it — that one's like the ones they use at Shake Shack — those little robots that go around delivering documents and delivering food to people.",
117:"Well, I actually saw one of them being test-driven out on the street — and this is the special thing about it: it has no steering wheel at all.",
138:"Something closer to reality would be, for example, Big Dog — the one with a gun mounted on top of it — or else some of those robots that run along on tank-like tracks.",
147:"Last year, there was actually a scene just like this that played out: you had a group of Russian soldiers, and they surrendered — they gave themselves up to one of the enemy units. But that unit didn't have a single living person in it.",
185:"There's one scene in it that goes something like this: this female CIA analyst, this woman, manages to track down bin Laden, who had been hiding out in Pakistan.",
198:"And it wasn't just him — on that very first day, they had already taken out 48 of their most senior military generals, along with a number of other important leaders.",
233:"Alright — so in the face of all these unmanned weapons, all these drones, there are actually counter-measures too, ways that people have found to deal with them.",
238:"You see, when one of these drones is sent up into the sky, the way it works is that it keeps in constant contact with its operator, and it does that through radio waves.",
259:"And the man who wrote it is actually quite well known — this is someone who was a four-star general, and who also served as the former Director of the CIA.",
261:"And what does he mean by that? Well, here's what he said: in the end, whether or not you win a war doesn't really come down to how many drones a country happens to have, or how many unmanned weapons it's got — what it truly comes down to is how those unmanned weapons make their decisions.",
321:"So this is really quite different from nuclear weapons — because here, the materials you need are far more common, far more widely available, and much, much easier to spread around.",
322:"And take Ukraine today — in fact, if you just go and look it up online, you'll find that they're now able to manufacture drones by the millions, every single year.",
324:"And now, at this point, they can turn out drones numbering in the millions in just a single year.",
338:"Take what you're seeing now, for instance — take COVID-19. All along, from the very start, there have been certain people who didn't want anyone looking into where it really came from.",
359:"But at the very least, you'll remember that back in January and February, wasn't the U.S. still going on about a certain topic — this idea of wanting to take Greenland, in order to complete its so-called Golden Dome defense plan?",
411:"For example, you may well have seen that recent piece of news — the one about Facebook, about Meta, and some of the other platforms — where the courts fined them, saying they were using algorithms, using all that data, to work out exactly what people like, and then feed them just the right content to keep them hooked, to keep them addicted.",
432:"Personally, as I look around at the way things are developing right now — this current war between the U.S., Israel, and Iran — of course there's still an awful lot we could take away from it, especially on the political side of things.",
433:"For instance, what it means for Europe, what it means for NATO, and also for Israel's whole position in the Middle East — but all of that we'll have to leave for another day, when we get the chance.",
}


def parse():
    segs = []
    for b in re.split(r"\n\s*\n", EN.read_text(encoding="utf-8").strip()):
        L = b.strip().splitlines()
        if len(L) < 3:
            continue
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", L[1])
        if not m:
            continue
        g = list(map(int, m.groups()))
        segs.append({"i": len(segs), "start": g[0]*3600+g[1]*60+g[2]+g[3]/1000,
                     "end": g[4]*3600+g[5]*60+g[6]+g[7]/1000,
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


def decode(path, speed=1.0):
    filt = ["-filter:a", f"atempo={speed:.5f}"] if abs(speed - 1.0) > 1e-3 else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), *filt,
                        "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                       capture_output=True, check=True)
    return r.stdout


def decode_pcm(pcm_bytes, speed):
    """atempo on raw PCM via a temp roundtrip."""
    if abs(speed - 1.0) <= 1e-3:
        return pcm_bytes
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "s16le", "-ac", "1", "-ar", str(SR), "-i", "-",
         "-filter:a", f"atempo={speed:.5f}", "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
        input=pcm_bytes, capture_output=True, check=True)
    return p.stdout


def generate():
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs
    load_dotenv(str(Path(".env").resolve()))
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    voice_id = open(".voice_id").read().strip()
    segs = parse()
    sents = sentences(segs)
    SENT.mkdir(parents=True, exist_ok=True)
    print(f"Generating {len(REWRITES)} rewritten sentence clips...")
    for n, text in sorted(REWRITES.items()):
        p = SENT / f"sent_{n:03d}.mp3"
        if p.exists() and p.stat().st_size > 0:
            print(f"  #{n} skip (exists)"); continue
        prev = " ".join(x["text"] for x in sents[n-2]) if n-2 >= 0 else None
        nxt = " ".join(x["text"] for x in sents[n]) if n < len(sents) else None
        audio = client.text_to_speech.convert(
            voice_id=voice_id, text=text, model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128", previous_text=prev, next_text=nxt)
        with open(p, "wb") as f:
            for c in audio:
                f.write(c)
        print(f"  #{n} ok ({len(text)} chars)")
    print("Done generating.")


def build():
    segs = parse()
    sents = sentences(segs)
    target = segs[-1]["end"]
    silence = lambda sec: b"\x00\x00" * int(round(max(0.0, sec) * SR))
    out = bytearray()
    cursor = 0.0
    slowed = comp = 0
    peak = 0.0
    print(f"Assembling {len(sents)} sentences onto {target/60:.1f} min...")
    for si, sent in enumerate(sents):
        n = si + 1
        start = sent[0]["start"]
        if cursor < start:
            out += silence(start - cursor); cursor = start
        # natural sentence audio
        if n in REWRITES:
            natural = decode(SENT / f"sent_{n:03d}.mp3")
        else:
            natural = b"".join(decode(SEG / f"seg_{s['i']:03d}.mp3") for s in sent)
        dur = len(natural) / 2 / SR
        nxt = sents[si+1][0]["start"] if si+1 < len(sents) else target
        avail = nxt - cursor
        if avail <= 0:
            speed = CMAX
        elif dur > avail:
            speed = min(CMAX, dur / avail); comp += 1
        else:
            L = min(LMAX, avail / dur); speed = 1.0 / L
            if L > 1.001:
                slowed += 1
        pcm = decode_pcm(natural, speed)
        out += pcm
        cursor += len(pcm) / 2 / SR
        if cursor > nxt:
            peak = max(peak, cursor - nxt)
        if n % 50 == 0:
            print(f"  {n}/{len(sents)}  t={cursor:6.1f}s")
    if cursor < target:
        out += silence(target - cursor); cursor = target
    with wave.open(str(OUT_WAV), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(bytes(out))
    print(f"\nWrote {OUT_WAV}: {cursor:.1f}s = {cursor/60:.2f} min")
    print(f"  slowed sentences: {slowed}   compressed: {comp}   peak drift: {peak:.2f}s")

    print("Muxing...")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", SRC, "-i", str(OUT_WAV), "-i", str(EN),
         "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-c:s", "mov_text",
         "-metadata:s:a:0", "language=eng", "-metadata:s:s:0", "language=eng",
         "-movflags", "+faststart", OUT_MP4], check=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", OUT_MP4], capture_output=True, text=True)
    print(f"Wrote {OUT_MP4} ({float(dur.stdout)/60:.2f} min)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("gen", "all"):
        generate()
    if cmd in ("build", "all"):
        build()
