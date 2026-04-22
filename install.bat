@echo off
setlocal

echo === Lumen Recorder — installer ===
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo Python 3.10+ is required. Install from https://www.python.org/downloads/windows/
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Dependency install failed.
    pause
    exit /b 1
)

echo.
echo Install complete. Launch the app with run.bat
pause
