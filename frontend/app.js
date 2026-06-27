// Same-origin by default — the backend serves this frontend directly.
// If you deploy the frontend separately from the backend, set this to the
// backend's full URL instead, e.g. "https://your-backend.onrender.com"
const API_BASE = "";

const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".panel");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");
const resultEl = document.getElementById("result");
const resultText = document.getElementById("result-text");
const resultAudio = document.getElementById("result-audio");
const downloadLink = document.getElementById("download-link");
const errorEl = document.getElementById("error");
const textInput = document.getElementById("text-input");
const textCount = document.getElementById("text-count");

let activeTab = "text";

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    activeTab = tab.dataset.tab;
    tabs.forEach((t) => {
      t.classList.toggle("is-active", t === tab);
      t.setAttribute("aria-selected", t === tab ? "true" : "false");
    });
    panels.forEach((p) => {
      const isMatch = p.dataset.panel === activeTab;
      p.classList.toggle("is-active", isMatch);
      p.hidden = !isMatch;
    });
    clearMessages();
  });
});

textInput.addEventListener("input", () => {
  textCount.textContent = textInput.value.length;
});

function clearMessages() {
  errorEl.hidden = true;
  resultEl.hidden = true;
}

function showError(message) {
  clearMessages();
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function getSelectedVoice() {
  return document.querySelector('input[name="voice"]:checked').value;
}

function setLoading(isLoading, label) {
  submitBtn.disabled = isLoading;
  statusEl.hidden = !isLoading;
  if (label) statusText.textContent = label;
}

async function handleResponse(resp) {
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch (_) {
      /* response wasn't JSON, keep default message */
    }
    throw new Error(detail);
  }

  const translatedText =
    resp.headers.get("X-Translated-Text") ||
    (resp.headers.get("X-Sentence-Count")
      ? `${resp.headers.get("X-Sentence-Count")} sentences spoken`
      : "");

  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);

  resultText.textContent = translatedText || "(no text preview available)";
  resultAudio.src = url;
  downloadLink.href = url;
  resultEl.hidden = false;
}

submitBtn.addEventListener("click", async () => {
  clearMessages();
  const voice = getSelectedVoice();

  try {
    if (activeTab === "text") {
      const text = textInput.value.trim();
      if (!text) return showError("Type some English text first.");

      setLoading(true, "Translating…");
      const form = new FormData();
      form.append("text", text);
      form.append("voice", voice);
      const resp = await fetch(`${API_BASE}/api/translate-speak`, { method: "POST", body: form });
      await handleResponse(resp);

    } else if (activeTab === "audio") {
      const file = document.getElementById("audio-input").files[0];
      if (!file) return showError("Choose an audio file first.");

      setLoading(true, "Transcribing and translating…");
      const form = new FormData();
      form.append("file", file);
      form.append("voice", voice);
      const resp = await fetch(`${API_BASE}/api/audio-translate`, { method: "POST", body: form });
      await handleResponse(resp);

    } else if (activeTab === "video") {
      const file = document.getElementById("video-input").files[0];
      if (!file) return showError("Choose a video file first.");

      setLoading(true, "Extracting audio and translating…");
      const form = new FormData();
      form.append("file", file);
      form.append("voice", voice);
      const resp = await fetch(`${API_BASE}/api/video-translate`, { method: "POST", body: form });
      await handleResponse(resp);

    } else if (activeTab === "document") {
      const file = document.getElementById("document-input").files[0];
      if (!file) return showError("Choose a document first.");
      const limit = document.getElementById("sentence-limit").value;

      setLoading(true, "Reading and translating document…");
      const form = new FormData();
      form.append("file", file);
      form.append("voice", voice);
      if (limit) form.append("max_sentences", limit);
      const resp = await fetch(`${API_BASE}/api/document-translate`, { method: "POST", body: form });
      await handleResponse(resp);
    }
  } catch (err) {
    showError(err.message || "Something went wrong. Try again.");
  } finally {
    setLoading(false);
  }
});

// Register the service worker for installability (best-effort; app still
// works fine if this fails, e.g. on http:// during local development)
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  });
}
