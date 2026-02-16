const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let mainWindow = null;
let pyProc = null;
let backendPort = null;

// ── Logging ────────────────────────────────────────────

const logPath = path.join(app.getPath("userData"), "backend.log");

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  process.stdout.write(line);
  fs.appendFileSync(logPath, line);
}

// ── Backend command resolution ─────────────────────────

function backendCommand() {
  if (!app.isPackaged) {
    // Dev mode: run the Python script directly
    return {
      cmd: "python",
      args: [path.join(__dirname, "..", "backend", "main.py")],
    };
  }

  // Packaged mode: use the PyInstaller --onedir binary
  const exeName = process.platform === "win32" ? "backend.exe" : "backend";
  const cmd = path.join(process.resourcesPath, "py", "backend", exeName);
  return { cmd, args: [] };
}

// ── Start backend process ──────────────────────────────

function startBackend() {
  return new Promise((resolve, reject) => {
    const { cmd, args } = backendCommand();

    log(`Starting backend: ${cmd} ${[...args, "--port", "0"].join(" ")}`);
    log(`Backend exe exists: ${fs.existsSync(cmd)}`);

    pyProc = spawn(cmd, [...args, "--port", "0"], {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });

    pyProc.stderr.on("data", (d) => {
      log("[py err] " + d.toString());
    });

    let resolved = false;

    pyProc.stdout.on("data", (d) => {
      const text = d.toString();
      log("[py] " + text);

      // Parse PORT=<number> from stdout
      const m = text.match(/PORT=(\d+)/);
      if (m && !backendPort) {
        backendPort = Number(m[1]);
        log("Backend ready on port: " + backendPort);

        if (!resolved) {
          resolved = true;
          resolve(backendPort);
        }
      }
    });

    pyProc.on("error", (err) => {
      log("Failed to start backend: " + err.message);
      if (!resolved) {
        resolved = true;
        reject(err);
      }
    });

    pyProc.on("exit", (code) => {
      log("Backend exited with code: " + code);
      pyProc = null;
      if (!resolved) {
        resolved = true;
        reject(new Error(`Backend exited with code ${code}`));
      }
    });

    // Timeout: if PORT= isn't printed within 30 seconds, reject
    setTimeout(() => {
      if (!resolved) {
        resolved = true;
        reject(new Error("Backend did not report PORT= in time"));
      }
    }, 30000);
  });
}

// ── Window creation ────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 480,
    height: 680,
    minWidth: 360,
    minHeight: 480,
    backgroundColor: "#0b0d10",
    titleBarStyle: "hiddenInset",
    frame: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile("index.html");
}

// ── IPC: renderer asks for the backend WebSocket URL ───

ipcMain.handle("get-backend-url", () => {
  if (backendPort) {
    return `ws://127.0.0.1:${backendPort}/ws/chat`;
  }
  return null;
});

// ── App lifecycle ──────────────────────────────────────

app.whenReady().then(async () => {
  log("App ready. Log file: " + logPath);
  try {
    await startBackend();
  } catch (err) {
    log("Backend startup failed: " + err.message);
    // Continue anyway — renderer will show "disconnected" and retry
  }

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (pyProc) {
    pyProc.kill();
    pyProc = null;
  }
});
