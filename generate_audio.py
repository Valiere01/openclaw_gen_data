#!/usr/bin/env python3
"""Generate TTS audio from executive summary using gTTS."""
from gtts import gTTS

# Read the TTS script
with open('executive_summary_tts.txt', 'r') as f:
    text = f.read()

# Generate audio with Google TTS
tts = gTTS(text=text, lang='en', slow=False)
tts.save('tick_summary.mp3')

print("✅ Audio generated: tick_summary.mp3")
