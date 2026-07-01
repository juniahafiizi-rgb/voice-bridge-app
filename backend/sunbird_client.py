"""
Runs translation and TTS directly inside the container using
transformers — no external API calls needed.
"""
import io
import torch
from transformers import MarianMTModel, MarianTokenizer
from speechbrain.inference.TTS import Tacotron2
from speechbrain.inference.vocoders import HIFIGAN
import soundfile as sf

# Lightweight English→Luganda model (~300MB, fits on free tier)
TRANSLATE_MODEL = "Helsinki-NLP/opus-mt-en-mul"
_tokenizer = None
_model = None
_tacotron = None
_hifigan = None


def _load_translation():
    global _tokenizer, _model
    if _tokenizer is None:
        _tokenizer = MarianTokenizer.from_pretrained(TRANSLATE_MODEL)
        _model = MarianMTModel.from_pretrained(TRANSLATE_MODEL)
        _model.eval()


def _load_tts():
    global _tacotron, _hifigan
    if _tacotron is None:
        _tacotron = Tacotron2.from_hparams(
            source="Sunbird/sunbird-lug-tts", savedir="/tmp/tts_model"
        )
        _hifigan = HIFIGAN.from_hparams(
            source="speechbrain/tts-hifigan-ljspeech", savedir="/tmp/vocoder"
        )


class SunbirdAPIError(Exception):
    pass


class SunbirdClient:
    def __init__(self, api_key: str = "", **kwargs):
        pass  # No external API needed

    async def translate(self, text: str, source: str = "eng", target: str = "lug") -> str:
        try:
            _load_translation()
            # MarianMT uses >>lug<< target language tag
            tagged = f">>lug<< {text}"
            inputs = _tokenizer([tagged], return_tensors="pt", padding=True)
            with torch.no_grad():
                output = _model.generate(**inputs)
            result = _tokenizer.decode(output[0], skip_special_tokens=True)
            return result
        except Exception as e:
            raise SunbirdAPIError(f"Translation failed: {e}")

    async def text_to_speech(self, text: str, **kwargs) -> bytes:
        try:
            _load_tts()
            mel, _, _ = _tacotron.encode_text(text)
            waveforms = _hifigan.decode_batch(mel)
            waveform_cpu = waveforms.squeeze(1).cpu().numpy()[0]
            buf = io.BytesIO()
            sf.write(buf, waveform_cpu, 22050, format="WAV")
            return buf.getvalue()
        except Exception as e:
            raise SunbirdAPIError(f"TTS failed: {e}")

    async def speech_to_text(self, audio_bytes: bytes, filename: str, language: str = "eng") -> str:
        try:
            import whisper, tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name
            asr = whisper.load_model("base")
            result = asr.transcribe(tmp_path)
            os.unlink(tmp_path)
            return result["text"]
        except Exception as e:
            raise SunbirdAPIError(f"STT failed: {e}")
