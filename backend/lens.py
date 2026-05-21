"""
lens.py — async wrapper around chrome-lens-py v3.x

v3 API (3.1.0+):
  - LensAPI.process_image(image_source, ocr_language=None) → coroutine
  - Returns a dict, but the "raw" field contains Protobuf Descriptor objects
    that are NOT JSON-serialisable — we must never pass raw to FastAPI.
"""

from typing import Any
from chrome_lens_py import LensAPI

_api = LensAPI()


async def run_lens_ocr(image_bytes: bytes) -> dict[str, Any]:
    """
    Run OCR and return a plain JSON-safe dict:

    {
      "full_text":  str,
      "paragraphs": [{"text": str, "words": []}],
      "words":      [],
      "language":   str,
    }
    """
    raw = await _api.process_image(image_bytes)
    return _normalise(raw)


def _normalise(raw: Any) -> dict[str, Any]:
    # Safely pull only the string/list fields we care about.
    # Do NOT include "raw" — it contains Protobuf Descriptor objects that
    # crash FastAPI's JSON encoder.
    full_text = ""
    language  = ""

    try:
        # v3 primary key
        val = raw.get("ocr_text") if isinstance(raw, dict) else None
        if val and isinstance(val, str):
            full_text = val.strip()
    except Exception:
        pass

    if not full_text:
        # fallbacks
        for key in ("full_text", "stitched_text", "text"):
            try:
                val = raw.get(key) if isinstance(raw, dict) else None
                if val and isinstance(val, str):
                    full_text = val.strip()
                    break
            except Exception:
                pass

    try:
        language = str(raw.get("language") or "") if isinstance(raw, dict) else ""
    except Exception:
        pass

    paragraphs = [{"text": full_text, "words": []}] if full_text else []

    return {
        "full_text":  full_text,
        "paragraphs": paragraphs,
        "words":      [],
        "language":   language,
        # "raw" intentionally omitted — contains non-serialisable Protobuf objects
    }
