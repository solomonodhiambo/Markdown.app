"""
MarkItDown Web App
-------------------
A small FastAPI service that wraps Microsoft's open-source `markitdown`
library (https://github.com/microsoft/markitdown) so you can:

  1. Paste a YouTube link  -> get back the video's transcript/metadata as Markdown
  2. Upload a file         -> get back its content converted to Markdown
     (PDF, DOCX, PPTX, XLSX, images, audio, HTML, CSV, JSON, ZIP, etc.)

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Then open http://127.0.0.1:8000
"""

import os
import re
import tempfile
import traceback
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from markitdown import MarkItDown

app = FastAPI(title="MarkItDown Web App")

# Serve the frontend
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# One shared converter instance.
# `enable_plugins=False` keeps behavior predictable; flip to True if you
# install third-party markitdown plugins later.
md_converter = MarkItDown(enable_plugins=False)


def normalize_youtube_url(url: str) -> str:
    """
    MarkItDown's YouTube converter has historically been picky about URL
    shape (e.g. youtu.be short links, /shorts/ links, extra query params
    like ?si=...). This normalizes anything a user might paste into the
    canonical https://www.youtube.com/watch?v=VIDEO_ID form, which is the
    format MarkItDown handles most reliably.
    """
    url = url.strip()

    patterns = [
        r"youtu\.be/([A-Za-z0-9_-]{11})",                     # youtu.be/<id>
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",           # /shorts/<id>
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",            # /embed/<id>
        r"[?&]v=([A-Za-z0-9_-]{11})",                         # ?v=<id>
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"

    # Fall back to whatever was pasted; let MarkItDown try it directly.
    return url


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = BASE_DIR / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/convert/youtube")
async def convert_youtube(url: str = Form(...)):
    if not url or "youtu" not in url.lower():
        raise HTTPException(status_code=400, detail="That doesn't look like a YouTube URL.")

    clean_url = normalize_youtube_url(url)

    try:
        result = md_converter.convert(clean_url)
        return JSONResponse({
            "success": True,
            "source": clean_url,
            "markdown": result.text_content,
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=422,
            detail=(
                f"Couldn't convert that video ({e}). Some videos have no "
                "captions/transcript available, which MarkItDown needs."
            ),
        )


@app.post("/convert/file")
async def convert_file(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix
    tmp_path = None
    try:
        # MarkItDown works off a file path, so we stream the upload to a
        # temp file first.
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        result = md_converter.convert(tmp_path)
        return JSONResponse({
            "success": True,
            "source": file.filename,
            "markdown": result.text_content,
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=422,
            detail=f"Couldn't convert '{file.filename}' ({e}).",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.get("/health")
async def health():
    return {"status": "ok"}
