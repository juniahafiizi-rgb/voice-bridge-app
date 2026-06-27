"""
Audio post-processing helpers. Kept separate from the API client so the
"male voice" feature is explicit about being a local pitch-shift approximation,
not a different trained voice (Sunbird's hosted TTS only offers a female
Luganda speaker at present).
"""
import io
import subprocess

import librosa
import soundfile as sf
from pydub import AudioSegment


def deepen_voice(mp3_bytes: bytes, n_steps: float = -2.5) -> bytes:
    """Pitch-shift MP3 audio down for a deeper-sounding voice. Returns MP3 bytes."""
    y, sr = librosa.load(io.BytesIO(mp3_bytes), sr=None, mono=True)
    y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=n_steps)

    wav_buf = io.BytesIO()
    sf.write(wav_buf, y_shifted, sr, format="WAV")
    wav_buf.seek(0)

    segment = AudioSegment.from_wav(wav_buf)
    mp3_buf = io.BytesIO()
    segment.export(mp3_buf, format="mp3")
    return mp3_buf.getvalue()


def concatenate_audio(mp3_chunks: list[bytes], pause_ms: int = 250) -> bytes:
    """Join multiple MP3 byte chunks into one MP3, with a short pause between each."""
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=pause_ms)
    for chunk in mp3_chunks:
        combined += AudioSegment.from_file(io.BytesIO(chunk), format="mp3") + pause

    out_buf = io.BytesIO()
    combined.export(out_buf, format="mp3")
    return out_buf.getvalue()


def extract_audio_from_video(video_path: str, output_wav_path: str) -> None:
    """Extract a mono 16kHz WAV audio track from a video file using ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_wav_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
