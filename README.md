# OBS Assistant

A voice & text AI assistant for OBS Studio. Control sources, streaming, recording, and more — just by talking or typing.

---

## Getting Started (Users)

### Prerequisites

1. **OBS Studio 28+** (comes with built-in WebSocket server)
2. **Ollama** — download from [ollama.com](https://ollama.com)

### Setup

**Step 1 — Start the AI model**

Open a terminal and run:

```
ollama run qwen3:0.6b
```

Leave this terminal open. The model needs to be running for the assistant to work.

**Step 2 — Launch OBS Assistant**

Download `obs-assistant Setup 1.0.0.exe` from the [Releases](https://github.com/clarsbyte/obs-assistant/releases) page and install it. It will connect to OBS via WebSocket — make sure OBS is running with the WebSocket server enabled:

> OBS → Tools → WebSocket Server Settings → ✅ Enable WebSocket server

That's it. Type or speak commands like:

- *"show webcam"*
- *"hide capture 6"*
- *"start streaming"*
- *"add text Hello World"*

---

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for the full guide.

### First-Time Setup

```powershell
# Create venv and install Python dependencies
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt

# Install Electron dependencies
cd electron
npm install
cd ..
```

### Quick Start

```powershell
# Activate the Python venv
.\env\Scripts\Activate.ps1

# Start Ollama (separate terminal)
ollama run qwen3:0.6b

# Run the Electron app (auto-spawns the Python backend)
cd electron
npm start
```

### Build

```powershell
.\env\Scripts\Activate.ps1
.\build.bat
```

Output: `electron\dist\obs-assistant Setup 1.0.0.exe`

