"""
Voice Bridge backend — English to Luganda translation + speech, for text,
audio, video, and document input.

All heavy ML inference (translation, STT, TTS) runs on Sunbird AI's hosted
API — this server's job is: validate input safely, extract/chunk content,
call Sunbird, post-process audio, and return a result. It never trains or
hosts models itself, which is what keeps this reliable on free hosting tiers.
"""
import os
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from sunbird_client import SunbirdClient, SunbirdAPIError
from text_extraction import extract_text_from_file, split_into_sentences
from audio_utils import deepen_voice, concatenate_audio, extract_audio_from_video

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration & startup checks
# ---------------------------------------------------------------------------

SUNBIRD_API_KEY = os.environ.get("HF_TOKEN")
if not SUNBIRD_API_KEY:
    raise RuntimeError(
        "SUNBIRD_API_KEY is not set. Add it to a .env file (local dev) or your "
        "hosting platform's environment variables (production). Never hardcode it."
    )

# Comma-separated list of frontend origins allowed to call this API.
# In production this MUST be your real deployed frontend URL, not "*".
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000").split(",")
    if origin.strip()
]

MAX_TEXT_CHARS = 5000
MAX_AUDIO_MB = 25
MAX_VIDEO_MB = 150
MAX_DOCUMENT_MB = 20
MAX_DOCUMENT_SENTENCES = 800  # safety cap so one upload can't run unbounded API calls

ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".aac"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_DOCUMENT_EXT = {".pdf", ".epub", ".txt"}

sunbird = SunbirdClient(api_key=SUNBIRD_API_KEY)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Voice Bridge API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

def validate_extension(filename: Optional[str], allowed: set[str], kind: str) -> str:
    if not filename:
        raise HTTPException(400, f"Missing {kind} filename")
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            400, f"Unsupported {kind} file type '{ext}'. Allowed: {', '.join(sorted(allowed))}"
        )
    return ext


async def read_and_validate_size(file: UploadFile, max_mb: int, kind: str) -> bytes:
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > max_mb:
        raise HTTPException(400, f"{kind} file too large ({size_mb:.1f}MB). Max: {max_mb}MB")
    if size_mb == 0:
        raise HTTPException(400, f"{kind} file is empty")
    return contents


def clean_text_input(text: str) -> str:
    text = text.strip()
    if not text:
        raise HTTPException(400, "Text cannot be empty")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(400, f"Text too long ({len(text)} chars). Max: {MAX_TEXT_CHARS}")
    return text


def validate_voice(voice: str) -> str:
    if voice not in ("female", "male"):
        raise HTTPException(400, "voice must be 'female' or 'male'")
    return voice


def apply_voice(audio_bytes: bytes, voice: str) -> bytes:
    return deepen_voice(audio_bytes) if voice == "male" else audio_bytes


def audio_response(audio_bytes: bytes, **extra_headers: str) -> Response:
    headers = {"Content-Disposition": "inline; filename=output.mp3"}
    headers.update(extra_headers)
    return Response(content=audio_bytes, media_type="audio/mpeg", headers=headers)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/translate-speak")
@limiter.limit("15/minute")
async def translate_speak(request: Request, text: str = Form(...), voice: str = Form("female")):
    text = clean_text_input(text)
    voice = validate_voice(voice)

    try:
        translated = await sunbird.translate(text, source="eng", target="lug")
        audio_bytes = await sunbird.text_to_speech(translated)
    except SunbirdAPIError as e:
        raise HTTPException(502, f"Translation service error: {e}")

    audio_bytes = apply_voice(audio_bytes, voice)
    return audio_response(audio_bytes, **{"X-Translated-Text": translated})


@app.post("/api/audio-translate")
@limiter.limit("8/minute")
async def audio_translate(request: Request, file: UploadFile = File(...), voice: str = Form("female")):
    validate_extension(file.filename, ALLOWED_AUDIO_EXT, "audio")
    voice = validate_voice(voice)
    contents = await read_and_validate_size(file, MAX_AUDIO_MB, "Audio")

    try:
        english_text = await sunbird.speech_to_text(contents, file.filename, language="eng")
        translated = await sunbird.translate(english_text, source="eng", target="lug")
        audio_bytes = await sunbird.text_to_speech(translated)
    except SunbirdAPIError as e:
        raise HTTPException(502, f"Processing error: {e}")

    audio_bytes = apply_voice(audio_bytes, voice)
    return audio_response(
        audio_bytes,
        **{"X-Original-Text": english_text, "X-Translated-Text": translated},
    )


@app.post("/api/video-translate")
@limiter.limit("5/minute")
async def video_translate(request: Request, file: UploadFile = File(...), voice: str = Form("female")):
    validate_extension(file.filename, ALLOWED_VIDEO_EXT, "video")
    voice = validate_voice(voice)
    contents = await read_and_validate_size(file, MAX_VIDEO_MB, "Video")

    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / f"input{Path(file.filename).suffix}"
        video_path.write_bytes(contents)
        audio_path = Path(tmp) / "extracted.wav"

        try:
            extract_audio_from_video(str(video_path), str(audio_path))
        except Exception as e:
            raise HTTPException(400, f"Could not extract audio from video: {e}")

        audio_bytes_in = audio_path.read_bytes()

    try:
        english_text = await sunbird.speech_to_text(audio_bytes_in, "extracted.wav", language="eng")
        translated = await sunbird.translate(english_text, source="eng", target="lug")
        audio_bytes = await sunbird.text_to_speech(translated)
    except SunbirdAPIError as e:
        raise HTTPException(502, f"Processing error: {e}")

    audio_bytes = apply_voice(audio_bytes, voice)
    return audio_response(
        audio_bytes,
        **{"X-Original-Text": english_text, "X-Translated-Text": translated},
    )


@app.post("/api/document-translate")
@limiter.limit("3/minute")
async def document_translate(
    request: Request,
    file: UploadFile = File(...),
    voice: str = Form("female"),
    max_sentences: Optional[int] = Form(None),
):
    ext = validate_extension(file.filename, ALLOWED_DOCUMENT_EXT, "document")
    voice = validate_voice(voice)
    contents = await read_and_validate_size(file, MAX_DOCUMENT_MB, "Document")

    with tempfile.TemporaryDirectory() as tmp:
        doc_path = Path(tmp) / f"input{ext}"
        doc_path.write_bytes(contents)
        try:
            raw_text = extract_text_from_file(str(doc_path))
        except Exception as e:
            raise HTTPException(400, f"Could not read document: {e}")

    sentences = split_into_sentences(raw_text)
    limit = min(max_sentences, MAX_DOCUMENT_SENTENCES) if max_sentences else MAX_DOCUMENT_SENTENCES
    sentences = [s for s in sentences[:limit] if s.strip()]

    if not sentences:
        raise HTTPException(400, "No readable text found in this document")

    audio_chunks = []
    failed = 0
    for sentence in sentences:
        try:
            translated = await sunbird.translate(sentence, source="eng", target="lug")
            chunk_audio = await sunbird.text_to_speech(translated)
            audio_chunks.append(chunk_audio)
        except SunbirdAPIError:
            failed += 1
            continue  # one bad sentence shouldn't sink the whole document

    if not audio_chunks:
        raise HTTPException(502, "Translation service failed for every sentence. Try again shortly.")

    final_audio = concatenate_audio(audio_chunks)
    final_audio = apply_voice(final_audio, voice)

    return audio_response(
        final_audio,
        **{"X-Sentence-Count": str(len(audio_chunks)), "X-Failed-Sentences": str(failed)},
    )


# Serve the frontend's static files (the PWA) from the same server/origin.
# Mounted last so it doesn't shadow the /api/* routes above.
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
