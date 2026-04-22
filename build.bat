@echo off
setlocal

echo === Lumen Recorder — single-file build ===
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Installing PyInstaller...
pip install --upgrade pyinstaller
if %errorlevel% neq 0 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo Building single-file executable...
pyinstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "LumenRecorder" ^
    --collect-all customtkinter ^
    --collect-all imageio_ffmpeg ^
    --collect-all sounddevice ^
    --collect-all soundfile ^
    --collect-all mss ^
    --hidden-import keyboard ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\LumenRecorder.exe
echo This file is self-contained — copy it to any Windows PC and run.
pause
