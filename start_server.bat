@echo off
title ocr_oo — backend
cd /d H:\ocr_oo\backend
call .venv\Scripts\activate
echo.
echo  OCR_OO starting...
echo  Frontend: H:\ocr_oo\frontend\index.html
echo  API:      http://localhost:8000
echo.
uvicorn main:app --host 127.0.0.1 --port 8000
pause
