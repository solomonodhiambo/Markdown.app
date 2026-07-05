# MarkItDown Web App

A small FastAPI web app wrapping Microsoft's open-source [markitdown](https://github.com/microsoft/markitdown) library.

- Paste a YouTube link → get the transcript + metadata as Markdown
- Upload a file → get it converted to Markdown (PDF, DOCX, PPTX, XLSX, CSV, images, audio, HTML, ZIP, and more)

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open **http://127.0.0.1:8000** in your browser.

## How it works

- `main.py` — FastAPI backend. Two endpoints:
  - `POST /convert/youtube` — takes a URL, normalizes it (handles `youtu.be`, `/shorts/`, `?si=` tracking params), passes it to `MarkItDown().convert()`.
  - `POST /convert/file` — takes an uploaded file, writes it to a temp path, converts it, deletes the temp file.
- `static/index.html` — single-page UI, no build step, no framework. Plain JS + fetch.

## Notes on YouTube conversion

MarkItDown extracts YouTube transcripts via the `youtube-transcript-api` package. A few things worth knowing:

- **Only works if the video has captions** (auto-generated or manual). Videos with captions disabled will fail with a clear error message in the UI.
- YouTube occasionally rate-limits transcript requests (HTTP 429) if you convert many videos in a short window from the same IP.
- The URL normalization in `main.py` covers `youtube.com/watch?v=`, `youtu.be/`, `/shorts/`, and `/embed/` formats.

## Deploying (Railway, since that's your usual stack)

1. Push this folder to a GitHub repo.
2. On Railway: New Project → Deploy from GitHub repo.
3. Railway auto-detects Python; set the start command to:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
4. No environment variables needed for the base setup — everything runs locally within the container, no external API keys required (the built-in converters don't call OpenAI/Azure unless you explicitly configure `markitdown` with an LLM client for image descriptions).

## Extending it

- **Image descriptions**: MarkItDown can use an LLM (OpenAI-compatible client) to caption embedded images in PPTX/DOCX files. Pass an `llm_client` and `llm_model` when constructing `MarkItDown(...)` in `main.py` if you want that.
- **Batch conversion**: add an endpoint that accepts multiple files/URLs and zips the Markdown outputs.
- **Persistence**: right now conversions aren't saved anywhere — add Supabase (matches your AudioBook AI stack) if you want history/search over past conversions.
