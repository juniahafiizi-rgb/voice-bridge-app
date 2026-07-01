"""
Sunbird AI models via Hugging Face Inference API.
No RunPod/Redis/PostgreSQL needed — HF hosts the models for free.
"""
import asyncio
import random
import httpx

HF_BASE = "https://api-inference.huggingface.co/models"
TRANSLATE_MODEL = "Sunbird/translate-nllb-1.3b-salt"
TTS_MODEL = "Sunbird/sunbird-lug-tts"


class SunbirdAPIError(Exception):
    pass


class SunbirdClient:
    def __init__(self, api_key: str, timeout: float = 60.0, max_retries: int = 3):
        if not api_key:
            raise ValueError("HF API key is required")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout
        self.max_retries = max_retries

    async def _post(self, url: str, payload: dict) -> dict:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=self.headers, json=payload)
                    if resp.status_code == 503:
                        # Model is loading — wait and retry
                        wait = resp.json().get("estimated_time", 20)
                        await asyncio.sleep(min(wait, 30))
                        continue
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                last_error = e
                await asyncio.sleep((2 ** attempt) + random.random())
        raise SunbirdAPIError(f"Request failed after {self.max_retries} attempts: {last_error}")

    async def translate(self, text: str, source: str = "eng", target: str = "lug") -> str:
        url = f"{HF_BASE}/{TRANSLATE_MODEL}"
        # NLLB language code mapping
        lang_map = {
            "eng": "eng_Latn", "lug": "lug_Latn",
            "ach": "luo_Latn", "nyn": "nyn_Latn",
        }
        payload = {
            "inputs": text,
            "parameters": {
                "src_lang": lang_map.get(source, source),
                "tgt_lang": lang_map.get(target, target),
            }
        }
        result = await self._post(url, payload)
        if isinstance(result, list) and result:
            return result[0].get("translation_text", "")
        raise SunbirdAPIError(f"Unexpected translation response: {result}")

    async def text_to_speech(self, text: str, **kwargs) -> bytes:
        url = f"{HF_BASE}/{TTS_MODEL}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                resp = await client.post(url, headers=self.headers, json={"inputs": text})
                if resp.status_code == 503:
                    await asyncio.sleep(20)
                    continue
                resp.raise_for_status()
                return resp.content
        raise SunbirdAPIError("TTS failed after retries")

    async def speech_to_text(self, audio_bytes: bytes, filename: str, language: str = "eng") -> str:
        # Use OpenAI Whisper via HF Inference API for English STT
        url = f"{HF_BASE}/openai/whisper-large-v3"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                resp = await client.post(
                    url,
                    headers=self.headers,
                    content=audio_bytes,
                )
                if resp.status_code == 503:
                    await asyncio.sleep(20)
                    continue
                resp.raise_for_status()
                result = resp.json()
                text = result.get("text")
                if not text:
                    raise SunbirdAPIError("No transcription returned")
                return text
        raise SunbirdAPIError("STT failed after retries")
