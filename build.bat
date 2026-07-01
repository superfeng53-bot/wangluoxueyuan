@echo off
cd /d "%~dp0"

if not exist .build-venv (
  python -m venv .build-venv
)
call .build-venv\Scripts\activate.bat
pip install -q -r requirements.txt -r requirements-build.txt
python scripts\build.py %*
