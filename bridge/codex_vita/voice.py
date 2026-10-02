"""Audio format groundwork only: NOT a replacement speech-recognition service."""
import io
import wave

MAX_SECONDS = 30
SAMPLE_RATE = 16000

def pcm16_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    if sample_rate not in (16000, 48000):
        raise ValueError("Unsupported sample rate")
    if not pcm or len(pcm) % 2 or len(pcm) > sample_rate * 2 * MAX_SECONDS:
        raise ValueError("PCM must be nonempty, 16-bit mono and at most 30 seconds")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()

VOICE_STATUS = {
    "state": "unverified",
    "enabled": False,
    "paidApiFallback": False,
    "reason": "A documented audio/realtime capability is not proof of the desktop Dictate path or billing. "
              "Verify the installed official Codex, account entitlement and end-to-end audio on Windows first."
}
