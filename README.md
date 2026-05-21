# ocr_oo

Batch OCR using Google Lens. Drop images or PDFs in, get clean plain text out. No API key, no account, no cost.

Uses [`chrome-lens-py`](https://github.com/bropines/chrome-lens-py) to talk directly to the same Protobuf endpoint the Chrome browser extension uses.

## Features

- Drag-and-drop or click-to-add — images and PDFs in the same batch
- PDFs are rasterised page-by-page automatically
- Jobs are async — submit and poll, no browser hang
- Per-job word / character / page counters
- Copy to clipboard or save as `.txt`
- No build step — frontend is a single HTML file

## Supported formats

`PNG` `JPG` `JPEG` `WEBP` `BMP` `TIFF` `PDF`

---

## Stack

| Layer | Tech |
|-------|------|
| OCR | `chrome-lens-py` ≥ 3.1 — Google Lens Protobuf endpoint |
| Backend | Python · FastAPI · PyMuPDF · Pillow |
| Frontend | HTML + CSS + vanilla JS — no framework, no build |

---

## Project layout

```
ocr_oo/
├── backend/
│   ├── main.py            FastAPI app, job queue, PDF splitting
│   ├── lens.py            chrome-lens-py async wrapper + normaliser
│   ├── test_ocr.py        CLI smoke test (no browser needed)
│   ├── introspect.py      prints LensAPI method names (debug helper)
│   └── requirements.txt
└── frontend/
    ├── index.html
    └── style.css
```

---

## Setup

### Requirements

- Python 3.10, 3.11, or 3.12
- No Chrome install needed — the library calls Google's API directly over HTTPS

### 1. Clone

```bash
git clone https://github.com/yourname/ocr_oo.git
cd ocr_oo
```

### 2. Create a virtual environment

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the backend

```bash
uvicorn main:app --port 8000
```

Add `--reload` during development to auto-restart on file changes.

### 5. Open the frontend

Open `frontend/index.html` directly in your browser. No web server needed — it talks to the backend at `http://localhost:8000`.

---

## Quick start scripts (Windows)

Two `.bat` files are included at the repo root:

| File | Purpose |
|------|---------|
| `start_server.bat` | Starts uvicorn with visible logs in the current window |
| `launch.bat` | Starts the server minimized + opens the frontend in one click |

To run on Windows startup: press `Win+R` → `shell:startup` → drop a shortcut to `launch.bat` in that folder.

---

## How it works

```
Browser  →  POST /ocr (multipart)
              │
              ├─ PDF  →  PyMuPDF rasterises pages at 150 DPI
              └─ Image → Pillow loads + converts to RGB
              │
              ▼
         LensAPI.process_image(bytes)
              → Google Lens Protobuf endpoint
              → returns ocr_text + language
              │
              ▼
         safe_ocr_data() sanitises response
         (strips non-JSON-serialisable Protobuf objects)
              │
              ▼
         Job stored in memory  +  outputs/<job_id>.txt written
              │
Browser  ←  GET /ocr/<job_id>  (polls every 900ms until done)
```

---

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Liveness — `{"ok": true}` |
| `/ocr` | POST | Submit files; returns `{"job_id": "..."}` |
| `/ocr/{job_id}` | GET | Poll status + full result |
| `/ocr/{job_id}/text` | GET | Plain text only |

### Job status values

| Status | Meaning |
|--------|---------|
| `queued` | Accepted, waiting |
| `processing` | OCR running |
| `done` | Complete |
| `error` | Failed — `error` and `trace` fields contain details |

### curl example

```bash
curl -X POST http://localhost:8000/ocr \
  -F "files=@photo.jpg" \
  -F "files=@scan.pdf"
# → {"job_id": "abc123", "file_count": 2}

curl http://localhost:8000/ocr/abc123/text
# → {"text": "..."}
```

---

## Smoke test

```bash
# with venv active, no server required
python test_ocr.py path/to/image.png
python test_ocr.py path/to/document.pdf
```

Bypasses FastAPI entirely. Good for isolating whether a problem is in the OCR layer or the HTTP layer.

---

## Deployment options

### LAN access

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Update `const API` in `frontend/index.html`:
```javascript
const API = 'http://YOUR_LAN_IP:8000';
```

### Cloudflare Tunnel (free, public URL, no VPS needed)

```bash
cloudflared tunnel --url http://localhost:8000
```

Gives you a public `https://` URL that tunnels to your local machine. See [Cloudflare Tunnel docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
RUN mkdir -p uploads outputs
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t ocr_oo .
docker run -d -p 8000:8000 --restart unless-stopped ocr_oo
```

---

## Configuration

### PDF resolution

Default is 150 DPI. Change in `main.py → pdf_to_images()`:

```python
mat = fitz.Matrix(200 / 72, 200 / 72)  # 200 DPI — better for small text
mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI — best quality, slower
```

### Job persistence

Jobs live in memory and are lost on restart. To persist, replace the `jobs` dict in `main.py` with SQLite or any key-value store.

### CORS

Open `*` by default for local use. Lock it down before exposing publicly:

```python
# main.py
allow_origins=["https://yourdomain.com"]
```

---

## Known issues & version pinning

### numpy — CPU compatibility

`chrome-lens-py` depends on numpy. Versions 2.x+ are compiled with X86_V2 instructions (SSE4.2) that older CPUs and some VMs don't support.

**Error:**
```
RuntimeError: NumPy was built with baseline optimizations (X86_V2)
but your machine doesn't support (X86_V2).
```

**Fix:** `requirements.txt` pins `numpy==1.26.4` — the last release with a broad-compatibility wheel. Only upgrade if you have confirmed your CPU supports these instructions.

### chrome-lens-py — API history

This library reverse-engineers Google's internal endpoint and has broken between major versions:

| Version | Method | Notes |
|---------|--------|-------|
| 1.x | `get_all_data()` | Synchronous, cookie-file based |
| 2.x | `get_all_data()` | Async; `CookiesManager` attribute bug in 2.1.3 |
| 3.1+ | `process_image()` | Full async rewrite, Protobuf endpoint, no cookies |

Current pin: `chrome-lens-py==3.4.2`. The v3 response contains Protobuf descriptor objects — `safe_ocr_data()` in `main.py` strips these before they reach FastAPI's JSON encoder.

---

## When it breaks

Google changes the Lens endpoint without notice. Here is how to diagnose each failure:

### Empty text / job hangs in processing

Google changed the Protobuf schema or endpoint URL.

```bash
python test_ocr.py path/to/any_image.png
```

If it hangs or returns empty, upgrade the library:

```bash
pip install --upgrade chrome-lens-py
```

Check [chrome-lens-py releases](https://github.com/bropines/chrome-lens-py/releases) for a version that mentions endpoint fixes. Update the pin in `requirements.txt` after confirming.

### `AttributeError: 'LensAPI' object has no attribute 'process_image'`

A new version renamed the method. Run the debug helper:

```bash
python introspect.py
```

This prints all public methods on `LensAPI`. Find the OCR method (historically `get_all_data`, `process_image`, `scan`) and update the call in `lens.py`:

```python
raw = await _api.process_image(image_bytes)
# change to whatever introspect.py showed
```

The return dict keys may also change. Add a temporary `print(raw)` in `_normalise()` to see the new shape, update the `.get("ocr_text")` key, remove the print.

### `ValueError: 'google._upb._message.Descriptor' object is not iterable`

A Protobuf object leaked into FastAPI's JSON encoder. `safe_ocr_data()` in `main.py` prevents this — if it reappears, a new field was added to the response. Find it by adding `print(type(v), v)` for each value in `_normalise()`.

### HTTP 429 / rate limiting

Too many requests. Add a delay in `main.py → process_job()`:

```python
await asyncio.sleep(1.5)  # after each page
```

### SSL / connection errors

```bash
pip install --upgrade chrome-lens-py httpx
```

### Nothing changed but it stopped working

```bash
pip install --upgrade chrome-lens-py
python test_ocr.py path/to/test_image.png
```

Check [chrome-lens-py issues](https://github.com/bropines/chrome-lens-py/issues) — Google breakage is usually reported and patched within a day or two.

### Maintenance checklist

```bash
# check installed versions
pip list | grep -E "chrome|numpy"

# smoke test
python test_ocr.py path/to/test_image.png

# inspect current API surface
python introspect.py

# upgrade and retest
pip install --upgrade chrome-lens-py
python test_ocr.py path/to/test_image.png

# pin the working version in requirements.txt
```

---

## License

MIT
