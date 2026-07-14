"""Create an Instant Voice Clone from audio/voice_sample.wav."""
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()
client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

with open("audio/voice_sample.wav", "rb") as f:
    voice = client.voices.ivc.create(
        name="Cantonese-Speaker-EN",
        description="Cloned from 2-min sample of a Hong Kong Cantonese speaker, used to narrate the English translation of his lecture.",
        files=[f],
    )

print(f"Voice created: {voice.voice_id}")
print(f"Name: {voice.name}")

# Save voice ID for later use
with open(".voice_id", "w") as f:
    f.write(voice.voice_id)
print("Voice ID saved to .voice_id")
