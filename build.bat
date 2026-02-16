@echo off
REM ============================================================
REM  Build obs-assistant.exe  (PyInstaller + electron-builder)
REM ============================================================

echo.
echo ===  Step 1/3: Install Python build dependency  ===
pip install pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: pip install pyinstaller failed
    exit /b 1
)

echo.
echo ===  Step 2/3: Package Python backend (PyInstaller --onedir)  ===
REM Output goes to electron/py/backend/ so electron-builder can find it
REM --collect-all grabs data files + submodules for tricky packages
REM --hidden-import adds modules PyInstaller can't auto-detect
pyinstaller --noconfirm --onedir backend/main.py --name backend --distpath electron/py ^
  --collect-all whisper ^
  --collect-all sounddevice ^
  --collect-all pydantic_ai ^
  --collect-all obsws_python ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import uvicorn.lifespan.off ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import tiktoken_ext.openai_public ^
  --hidden-import tiktoken_ext ^
  --exclude-module logfire ^
  --copy-metadata genai-prices ^
  --add-data "backend/voice.py;." ^
  --add-data "backend/obs.py;."
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller failed
    exit /b 1
)

echo.
echo ===  Step 3/3: Package Electron app (electron-builder)  ===
cd electron
call npm install
REM Skip code signing (not needed for personal apps, avoids symlink errors on Windows)
set CSC_IDENTITY_AUTO_DISCOVERY=false
call npx --yes electron-builder --win
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: electron-builder failed
    exit /b 1
)

echo.
echo ===  Done!  ===
echo Installer is in:  electron\dist\
echo.

