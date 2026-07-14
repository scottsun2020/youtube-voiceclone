"""Generate a short test sample with the cloned voice."""
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()
client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
voice_id = open(".voice_id").read().strip()

# First paragraph (segments 1-10), naturally flowing as one passage
test_text = (
    "Over the past month or so, I think many people have been concerned "
    "about the war between the U.S., Israel, and Iran — a conflict that "
    "has shaken the global situation. Today I'd like to start with this "
    "topic, but from a different angle. I think war serves as a kind of "
    "stage — one where you can see how astonishing human invention can be. "
    "In this war, you see all kinds of different weapons. I don't know if "
    "you've been following the news."
)
print(f"Generating {len(test_text)} chars...")

audio_iter = client.text_to_speech.convert(
    voice_id=voice_id,
    text=test_text,
    model_id="eleven_multilingual_v2",  # good for accented English
    output_format="mp3_44100_128",
)

with open("audio/test_sample.mp3", "wb") as f:
    for chunk in audio_iter:
        f.write(chunk)
print("Saved: audio/test_sample.mp3")
