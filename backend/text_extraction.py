"""
Text extraction for documents (PDF, EPUB, TXT) and sentence chunking,
so long-form content can be translated and spoken sentence by sentence.
"""
import pdfplumber
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import nltk

# Download tokenizer data once; safe to call repeatedly (no-op if already present)
for resource in ("punkt", "punkt_tab"):
    try:
        nltk.data.find(f"tokenizers/{resource}")
    except LookupError:
        nltk.download(resource, quiet=True)

from nltk.tokenize import sent_tokenize  # noqa: E402


def extract_text_from_file(file_path: str) -> str:
    lower = file_path.lower()

    if lower.endswith(".pdf"):
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + " "
        return text

    if lower.endswith(".epub"):
        book = epub.read_epub(file_path)
        text = ""
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), "html.parser")
                text += soup.get_text() + " "
        return text

    if lower.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    raise ValueError(f"Unsupported document type for: {file_path}")


def split_into_sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())  # collapse whitespace/newlines
    if not normalized:
        return []
    return sent_tokenize(normalized)
