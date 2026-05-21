"""
ocr_oo — backend
FastAPI server that accepts images / PDFs, runs OCR via chrome-lens-py,
and returns structured text with geometry.
"""

import io
import uuid
import time
from pathlib import Path
from typing import List

import aiofiles
import fitz  # PyMuPDF
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from lens import run_lens_ocr

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="ocr_oo", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------

jobs: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
SUPPORTED_PDF   = {".pdf"}


def pdf_to_images(pdf_bytes: bytes) -> List[Image.Image]:
    """Rasterise every page of a PDF to a PIL Image at 150 DPI."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page in doc:
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def pil_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def safe_ocr_data(ocr: dict) -> dict:
    """
    Return only the JSON-safe fields from an OCR result.
    Strips anything that might contain Protobuf objects (like 'raw').
    """
    return {
        "full_text":  str(ocr.get("full_text") or ""),
        "language":   str(ocr.get("language") or ""),
        "paragraphs": [
            {
                "text":  str(p.get("text") or ""),
                "words": [
                    {
                        "text": str(w.get("text") or ""),
                        "x":    float(w.get("x") or 0),
                        "y":    float(w.get("y") or 0),
                        "w":    float(w.get("w") or 0),
                        "h":    float(w.get("h") or 0),
                    }
                    for w in (p.get("words") or [])
                ],
            }
            for p in (ocr.get("paragraphs") or [])
        ],
        "words": [
            {
                "text": str(w.get("text") or ""),
                "x":    float(w.get("x") or 0),
                "y":    float(w.get("y") or 0),
                "w":    float(w.get("w") or 0),
                "h":    float(w.get("h") or 0),
            }
            for w in (ocr.get("words") or [])
        ],
    }


# ---------------------------------------------------------------------------
# Background job worker
# ---------------------------------------------------------------------------

async def process_job(job_id: str, file_paths: List[Path]):
    jobs[job_id]["status"] = "processing"
    results = []

    try:
        for fpath in file_paths:
            ext = fpath.suffix.lower()
            raw = fpath.read_bytes()

            if ext in SUPPORTED_PDF:
                pages = pdf_to_images(raw)
            elif ext in SUPPORTED_IMAGE:
                pages = [Image.open(io.BytesIO(raw)).convert("RGB")]
            else:
                continue

            file_result = {
                "filename": fpath.name,
                "pages": [],
            }

            for page_idx, page_img in enumerate(pages):
                img_bytes = pil_to_bytes(page_img)
                ocr_data  = await run_lens_ocr(img_bytes)
                # Strip non-serialisable fields before storing
                clean_ocr = safe_ocr_data(ocr_data)

                file_result["pages"].append({
                    "page": page_idx + 1,
                    "ocr":  clean_ocr,
                })

            results.append(file_result)

        # Build plain-text output
        plain_lines = []
        for fr in results:
            plain_lines.append(f"=== {fr['filename']} ===")
            for pg in fr["pages"]:
                if len(fr["pages"]) > 1:
                    plain_lines.append(f"--- Page {pg['page']} ---")
                for para in pg["ocr"].get("paragraphs", []):
                    plain_lines.append(para["text"])
                    plain_lines.append("")

        plain_text = "\n".join(plain_lines).strip()

        # Persist plain text
        out_file = OUTPUT_DIR / f"{job_id}.txt"
        async with aiofiles.open(out_file, "w", encoding="utf-8") as f:
            await f.write(plain_text)

        jobs[job_id].update({
            "status":      "done",
            "results":     results,
            "plain_text":  plain_text,
            "output_file": str(out_file),
            "finished_at": time.time(),
        })

    except Exception as exc:
        import traceback
        jobs[job_id].update({
            "status": "error",
            "error":  str(exc),
            "trace":  traceback.format_exc(),
        })
    finally:
        for fpath in file_paths:
            try:
                fpath.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ocr")
async def submit_ocr(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(400, "No files uploaded.")

    job_id = uuid.uuid4().hex
    saved  = []

    for upload in files:
        ext = Path(upload.filename or "file").suffix.lower()
        if ext not in SUPPORTED_IMAGE | SUPPORTED_PDF:
            raise HTTPException(
                400,
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(SUPPORTED_IMAGE | SUPPORTED_PDF))}",
            )
        dest = UPLOAD_DIR / f"{job_id}_{uuid.uuid4().hex}{ext}"
        data = await upload.read()
        async with aiofiles.open(dest, "wb") as f:
            await f.write(data)
        saved.append(dest)

    jobs[job_id] = {
        "status":     "queued",
        "file_count": len(saved),
        "created_at": time.time(),
    }

    background_tasks.add_task(process_job, job_id, saved)
    return {"job_id": job_id, "file_count": len(saved)}


@app.get("/ocr/{job_id}")
def get_result(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    return job


@app.get("/ocr/{job_id}/text")
def get_plain_text(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    if job["status"] != "done":
        raise HTTPException(400, f"Job status is '{job['status']}', not done yet.")
    return {"text": job.get("plain_text", "")}
