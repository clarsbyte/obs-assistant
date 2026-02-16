# OBS Assistant — Development & Build Guide

## Project Structure

```
obs-assistant/
├── backend/                 # Python backend (FastAPI + WebSocket)
│   ├── main.py              # Entry point — agent, tools, WS server
│   ├── voice.py             # Whisper-based voice listener
│   └── obs.py               # Standalone OBS test script
├── electron/                # Electron frontend
│   ├── main.js              # Main process — spawns backend, IPC
│   ├── preload.js           # Context bridge (IPC + WebSocket API)
│   ├── renderer.js          # UI logic
│   ├── index.html           # UI markup + styles
│   ├── package.json         # Electron deps + electron-builder config
│   └── py/                  # (generated) PyInstaller output goes here
│       └── backend/
│           └── backend.exe
├── env/                     # Python virtual environment (not in git)
├── requirements.txt         # Python dependencies (pip freeze)
├── build.bat                # One-click full build script
└── DEVELOPMENT.md           # This file
```

---

## Prerequisites

- **Python 3.12+**
- **Node.js 18+**
- **Ollama** — [ollama.com](https://ollama.com)
- **OBS Studio 28+** (with WebSocket server enabled)

---

## First-Time Setup

### 1. Clone the repo

```powershell
git clone git@github.com:clarsbyte/obs-assistant.git
cd obs-assistant
```

### 2. Create the Python virtual environment and install dependencies

```powershell
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Install Electron dependencies

```powershell
cd electron
npm install
cd ..
```

### 4. Pull the AI model

In a separate terminal:

```powershell
ollama run qwen3:0.6b
```

Leave this running — the backend needs it.

---

## Day-to-Day Development

### 1. Activate the Python venv

```powershell
.\env\Scripts\Activate.ps1
```

### 2. Run in dev mode

Open two terminals:

**Terminal 1 — Python backend (optional, Electron spawns it automatically):**
```powershell
cd backend
python main.py --port 8765
```

**Terminal 2 — Electron app:**
```powershell
cd electron
npm start
```

In dev mode (`npm start`), Electron spawns `python ../backend/main.py --port 0` automatically. The backend picks a free port, prints `PORT=<N>`, and Electron connects to it. You don't need to run the backend manually unless you want to debug it separately.

> **Tip:** If you run the backend manually on a fixed port (e.g. `--port 8765`), the renderer will fall back to `ws://127.0.0.1:8765/ws/chat` if the IPC URL isn't available.

---

## Updating Python Code

When you change anything in `backend/` (e.g. `main.py`, `voice.py`, add new files):

### During development

Just restart the Electron app — it re-spawns the Python process each time:

```powershell
cd electron
npm start
```

Or if you're running the backend separately, just restart the Python script:

```powershell
cd backend
python main.py --port 8765
```

### Before packaging / releasing

You **must** re-run PyInstaller to create a fresh `backend.exe` that includes your changes:

```powershell
# From the project root
pyinstaller --noconfirm --onedir backend/main.py --name backend --distpath electron/py
```

This overwrites `electron/py/backend/` with the updated executable. Then rebuild the Electron app:

```powershell
cd electron
npx electron-builder --win
```

Or just run the full build script:

```powershell
.\build.bat
```

---

## Adding New Python Files

If you add a new `.py` file that `main.py` imports (e.g. `backend/my_new_module.py`):

1. **Dev mode** — works automatically, Python finds it via normal imports.
2. **Packaged mode** — PyInstaller usually auto-detects imports. If it doesn't (e.g. dynamic imports), add a `--hidden-import`:

```powershell
pyinstaller --noconfirm --onedir backend/main.py --name backend --distpath electron/py --hidden-import my_new_module
```

---

## Adding New Python Dependencies

```powershell
# Activate venv
.\env\Scripts\Activate.ps1

# Install the package
pip install some-package

# Freeze requirements (good practice)
pip freeze > requirements.txt
```

PyInstaller picks up installed packages automatically. If a package has issues being bundled, you may need `--hidden-import`:

```powershell
pyinstaller --noconfirm --onedir backend/main.py --name backend --distpath electron/py --hidden-import some_package
```

---

## Adding Non-Python Files (data, models, audio, etc.)

If your backend needs data files at runtime (e.g. `backend/hi.mp3`), tell PyInstaller to include them:

```powershell
pyinstaller --noconfirm --onedir backend/main.py --name backend --distpath electron/py --add-data "backend/hi.mp3;."
```

The syntax is `--add-data "source;destination"` (semicolon on Windows, colon on mac/linux).

At runtime in the packaged app, access them via:

```python
import sys, os

def resource_path(relative_path):
    """Get path to a bundled resource (works in dev and packaged)."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
```

---

## Full Build (from scratch)

```powershell
# 1. Make sure venv is active
.\env\Scripts\Activate.ps1

# 2. Make sure Electron deps are installed
cd electron
npm install
cd ..

# 3. Run the full build (PyInstaller + electron-builder)
.\build.bat
```

Output:
- `electron/py/backend/backend.exe` — the standalone Python backend
- `electron/dist/obs-assistant Setup *.exe` — the Windows installer

---

## Build Cheat Sheet

| What changed             | What to re-run                                       |
|--------------------------|------------------------------------------------------|
| Python code only         | `pyinstaller ...` then `npx electron-builder --win`  |
| Electron JS/HTML only    | `npx electron-builder --win` (no PyInstaller needed) |
| Both Python + Electron   | `.\build.bat`                                        |
| Just testing (no build)  | `cd electron && npm start`                           |

---

## Troubleshooting

**Backend doesn't start in packaged app:**
- Check `electron/py/backend/backend.exe` exists. If not, re-run PyInstaller.
- Run `electron/py/backend/backend.exe --port 0` manually in a terminal to see errors.

**Missing module error in packaged exe:**
- Add `--hidden-import module_name` to the PyInstaller command.

**Antivirus flags the exe:**
- `--onedir` has fewer false positives than `--onefile`. If still flagged, sign the exe with a code-signing certificate.

**Port conflict:**
- The app auto-picks a free port (`--port 0`). Conflicts shouldn't happen. If they do, pass a specific port: `backend.exe --port 9999`.

