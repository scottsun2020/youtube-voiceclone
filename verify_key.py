"""Verify the ElevenLabs API key and show subscription / quota."""
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()
client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

user = client.user.get()
sub = user.subscription
print(f"Tier:               {sub.tier}")
print(f"Character limit:    {sub.character_limit:,}")
print(f"Characters used:    {sub.character_count:,}")
print(f"Characters remaining: {sub.character_limit - sub.character_count:,}")
print(f"Voice slots used:   {sub.voice_limit and f'{len(client.voices.get_all().voices)}/{sub.voice_limit}'}")
print(f"Can extend voice limit: {sub.can_extend_voice_limit}")
print(f"Can use IVC: {sub.can_use_instant_voice_cloning}")
print(f"Can use PVC: {sub.can_use_professional_voice_cloning}")
