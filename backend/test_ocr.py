#!/usr/bin/env python3
"""
Quick smoke-test: feed a local image to the backend OCR pipeline
without starting the HTTP server.

Usage:
    python test_ocr.py path/to/image.png
    python test_ocr.py path/to/document.pdf
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lens import run_lens_ocr
from main import pdf_to_images, pil_to_bytes
import io
from PIL import Image


async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_ocr.py <image_or_pdf>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    raw = path.read_bytes()
    ext = path.suffix.lower()

    if ext == ".pdf":
        pages = pdf_to_images(raw)
    else:
        pages = [Image.open(io.BytesIO(raw)).convert("RGB")]

    for idx, page_img in enumerate(pages, 1):
        print(f"\n{'='*60}")
        print(f"  Page {idx}")
        print(f"{'='*60}")
        img_bytes = pil_to_bytes(page_img)
        result    = await run_lens_ocr(img_bytes)
        print(result["full_text"])


if __name__ == "__main__":
    asyncio.run(main())
