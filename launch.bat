@echo off
title ocr_oo — launcher
cd /d H:\ocr_oo\backend
call .venv\Scripts\activate

start "ocr_oo server" /min cmd /k "uvicorn main:app --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak >nul

start "" "H:\ocr_oo\frontend\index.html"
