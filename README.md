# Voice Bridge — English → Luganda

A web app (installable on phones, no app store needed) that translates
English text, audio, video, or documents into spoken Luganda.

## How it actually works

This app does **not** run any AI models itself. Every translation, speech
recognition, and text-to-speech call goes to **Sunbird AI's hosted API**
(`api.sunbird.ai`). This backend's job is just to:

- validate uploads safely (size/type limits)
- extract audio from video, and text from PDFs/EPUBs
- call Sunbird's API with retries
- stitch long documents into one audio file
- apply the "male voice" pitch-shift (Sunbird's hosted Luganda voice is
  female only — there's no separate male Luganda model to call)

This is why it's reliable on free hosting: there's no GPU, no model loading,
nothing to keep "awake." It's a lightweight Python server making API calls.

## Project structure

```
voice-bridge-app/
├── backend/
│   ├── main.py              FastAPI app, all routes, security, validation
│   ├── sunbird_client.py    Wrapper around Sunbird's API with retries
│   ├── audio_utils.py       Voice deepening, audio stitching, video extraction
│   ├── text_extraction.py   PDF/EPUB/TXT text + sentence chunking
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html           The app UI
│   ├── style.css
│   ├── app.js
│   ├── manifest.json        Makes it installable on phones
│   ├── sw.js                Service worker (caches the app shell)
│   └── icons/
└── Dockerfile
```

## 1. Get a Sunbird AI API key

Sign up at `https://api.sunbird.ai/register` and generate an API key from
your dashboard. **Never put this key in any frontend file or commit it to
git** — it only ever lives in the backend's environment variables.

## 2. Run it locally first (to make sure it works)

```bash
cd voice-bridge-app/backend
cp .env.example .env
# edit .env and paste your real SUNBIRD_API_KEY

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` in your browser — the backend serves the
frontend directly, so this one URL is the whole app.

## 3. Deploy it for free so it's reachable from a phone

**Recommended: Render.com (free tier)**

1. Push this folder to a GitHub repo (see note on `.env` below).
2. On Render: **New → Web Service** → connect your repo.
3. Environment: **Docker** (it'll pick up the `Dockerfile` automatically).
4. Add environment variables in Render's dashboard (not in your code):
   - `SUNBIRD_API_KEY` = your real key
   - `ALLOWED_ORIGINS` = the Render URL you're given (e.g. `https://voice-bridge.onrender.com`)
5. Deploy. Render gives you a public HTTPS URL.

**Important free-tier note:** Render's free web services sleep after 15
minutes of inactivity and take ~30-50 seconds to wake up on the next
request. That's normal — not a bug. If you outgrow this, a paid tier
removes the sleep.

**Alternative: Fly.io free tier** — works similarly, uses the same
`Dockerfile`, and doesn't sleep, but requires a credit card on file even for
the free allowance.

## 4. Get it onto a phone

Once deployed, open the Render URL on a phone browser (Chrome on Android,
Safari on iOS):

- **Android (Chrome):** menu (⋮) → "Add to Home screen" / "Install app"
- **iPhone (Safari):** Share button → "Add to Home Screen"

It now behaves like an installed app — its own icon, opens full-screen, no
browser address bar.

## Security notes (already built in, listed so you understand them)

- The Sunbird API key never reaches the browser — only the backend holds it.
- `ALLOWED_ORIGINS` restricts which websites are allowed to call your API
  (CORS) — set this to your real deployed URL, never `*`, once you're live.
- Every upload is checked for file type and size **before** any processing.
- Rate limiting (`slowapi`) caps requests per IP per endpoint, so one user
  (or a bot) can't burn through your whole Sunbird quota.
- Uploaded files are processed in temporary directories that are deleted
  immediately after each request — nothing persists on disk.
- A failed sentence in a long document doesn't sink the whole job — it's
  skipped, and the response tells you how many failed.

## Things worth doing next, in order of value

1. **Test with a real document/video end to end** on the deployed version,
   not just locally.
2. **Watch your Sunbird API usage** — free/standard tier accounts have rate
   limits (50/min on standard); the app's own limits are set comfortably
   under that, but high traffic could still hit Sunbird's ceiling.
3. **Replace the icon files** in `frontend/icons/` with a real designed
   logo when you're ready — the current ones are simple placeholders.
4. **Add a backend database** only if you want to save translation history
   per user — right now nothing is stored, which is the simplest and most
   private starting point.
