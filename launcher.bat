@echo off
REM ──────────────────────────────────────────────
REM Frame Extractor Launcher (.bat)
REM ──────────────────────────────────────────────

REM 1) Ensure unbuffered Python output so tqdm bars and print(…) show immediately:
set PYTHONUNBUFFERED=1

REM 2) Switch to the directory this .bat lives in (where your .py is):
cd /d "%~dp0"

REM 3) (Optional) Activate your virtual-environment:
REM    If you’re using a venv in “venv” folder, uncomment:
REM call "%~dp0venv\Scripts\activate.bat"
REM    Or for conda, uncomment and set your env name:
REM call conda activate my_env_name

REM 4) Launch with -u for unbuffered output, preserving tqdm bars:
python -u frame_extractor.py

REM 5) Keep the window open so you can see the final summary:
pause
