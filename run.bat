@echo off
setlocal

if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
start "" pythonw main.py
