"""
Thin async client around Sunbird AI's hosted API.
Docs referenced: https://salt.sunbird.ai/API/
"""
import asyncio
import random
import httpx

SUNBIRD_BASE_URL = "https://api.sunbird.ai"

# Sunbird's hosted Luganda voice is female only (speaker_id 248) at the time this
# was written. There is no male Luganda speaker available server-side, which is why
# audio_utils.deepen_voice() exists as a post-processing step, not a workaround.
LUGANDA_SPEAKER_ID = 248


class SunbirdAPIError(Exception):
    """Raised whenever Sunbird's API returns an error or an unexpected response shape."""


class SunbirdClient:
    def __init__(self, api_key: str, timeout: float = 60.0, max_retries: int = 3):
        if not api_key:
            raise ValueError("Sunbird API key is required")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {"Authorization": f"Bearer {api_key}"}

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(method, url, **kwargs)

                # Retry on rate limiting and transient server/worker errors
                if resp.status_code in (429, 503, 504):
                    last_error = SunbirdAPIError(
                        f"{resp.status_code}: {resp.text[:200]}"
                    )
                    await asyncio.sleep((2 ** attempt) + random.random())
                    continue

                resp.raise_for_status()
                return resp

            except httpx.HTTPStatusError as e:
                # Non-retryable client errors (400, 401, 422...) fail immediately
                raise SunbirdAPIError(
                    f"{e.response.status_code}: {e.response.text[:300]}"
                ) from e
            except httpx.RequestError as e:
                last_error = e
                await asyncio.sleep((2 ** attempt) + random.random())

        raise SunbirdAPIError(f"Request failed after {self.max_retries} attempts: {last_error}")

    async def translate(self, text: str, source: str = "eng", target: str = "lug") -> str:
        url = f"{SUNBIRD_BASE_URL}/tasks/nllb_translate"
        payload = {"source_language": source, "target_language": target, "text": text}
        resp = await self._request(
            "POST", url, headers={**self.headers, "Content-Type": "application/json"}, json=payload
        )
        data = resp.json()
        output = data.get("output", {})
        if output.get("Error"):
            raise SunbirdAPIError(f"Translation worker error: {output['Error']}")
        translated = output.get("translated_text")
        if not translated:
            raise SunbirdAPIError("Translation response missing 'translated_text'")
        return translated

    async def text_to_speech(
        self, text: str, speaker_id: int = LUGANDA_SPEAKER_ID, temperature: float = 0.7
    ) -> bytes:
        url = f"{SUNBIRD_BASE_URL}/tasks/tts"
        payload = {"text": text, "speaker_id": speaker_id, "temperature": temperature}
        resp = await self._request(
            "POST", url, headers={**self.headers, "Content-Type": "application/json"}, json=payload
        )
        data = resp.json()
        audio_url = data.get("output", {}).get("audio_url")
        if not audio_url:
            raise SunbirdAPIError("TTS response missing 'audio_url'")

        # The signed URL expires in ~120 seconds, so download right away.
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            audio_resp = await client.get(audio_url)
            audio_resp.raise_for_status()
            return audio_resp.content

    async def speech_to_text(self, audio_bytes: bytes, filename: str, language: str = "eng") -> str:
        url = f"{SUNBIRD_BASE_URL}/tasks/stt"
        files = {"audio": (filename, audio_bytes)}
        data = {"language": language, "adapter": language}
        resp = await self._request("POST", url, headers=self.headers, files=files, data=data)
        result = resp.json()
        text = result.get("audio_transcription")
        if not text:
            raise SunbirdAPIError("No transcription produced for this audio")
        return text
