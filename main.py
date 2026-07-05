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
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

app = FastAPI(title="MarkItDown Web App")

# Serve the frontend
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# One shared converter instance.
# `enable_plugins=False` keeps behavior predictable; flip to True if you
# install third-party markitdown plugins later.

md_converter = MarkItDown()

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


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
        r"[?&]v=([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


@app.post("/convert/youtube")
async def convert_youtube(url: str = Form(...)):
    if not url or "youtu" not in url.lower():
        raise HTTPException(status_code=400, detail="That doesn't look like a YouTube URL.")

    clean_url = normalize_youtube_url(url)
    video_id = extract_video_id(clean_url)

    if not video_id:
        raise HTTPException(status_code=400, detail="Couldn't find a video ID in that URL.")

    # --- 1. Get the transcript directly (more reliable than relying on
    #     MarkItDown's internal YouTube converter, which has had several
    #     compounding bugs around URL parsing and library version mismatches).
    transcript_text = None
    transcript_error = None
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript_text = " ".join(part["text"] for part in transcript_list)
    except TranscriptsDisabled:
        transcript_error = "Captions are disabled for this video."
    except NoTranscriptFound:
        transcript_error = "No transcript/captions found for this video."
    except VideoUnavailable:
        transcript_error = "This video is unavailable."
    except Exception as e:
        transcript_error = str(e)

    # --- 2. Get title/description/metadata via MarkItDown as a bonus,
    #     but don't fail the whole request if this part breaks.
    title = None
    try:
        result = md_converter.convert(clean_url)
        # First markdown heading line is usually the title
        first_line = result.text_content.strip().splitlines()[0] if result.text_content else ""
        title = first_line.lstrip("#").strip() or None
    except Exception:
        pass

    if not transcript_text:
        raise HTTPException(
            status_code=422,
            detail=f"Couldn't get a transcript for that video. {transcript_error or ''}".strip(),
        )

    markdown_parts = []
    if title:
        markdown_parts.append(f"# {title}\n")
    markdown_parts.append(f"**Source:** {clean_url}\n")
    markdown_parts.append("## Transcript\n")
    markdown_parts.append(transcript_text)

    return JSONResponse({
        "success": True,
        "source": clean_url,
        "markdown": "\n".join(markdown_parts),
    })


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
  
