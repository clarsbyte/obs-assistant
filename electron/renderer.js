const messagesEl = document.getElementById("messages");
const input = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const statusDot = document.getElementById("connDot");
const statusLabel = document.getElementById("connLabel");

// OBS settings elements
const settingsBtn = document.getElementById("settingsBtn");
const settingsPanel = document.getElementById("settingsPanel");
const obsPortInput = document.getElementById("obsPort");
const obsPasswordInput = document.getElementById("obsPassword");
const obsConnectBtn = document.getElementById("obsConnectBtn");
const obsDot = document.getElementById("obsDot");
const obsStatusLabel = document.getElementById("obsStatusLabel");

let isWaiting = false;
let chat = null;
let isListening = false;
let wasConnected = false; // track if we ever successfully connected


let backendUrl = null;

async function connectWebSocket() {
  // Get the URL from the main process (IPC) if we don't have it yet
  if (!backendUrl) {
    try {
      backendUrl = await window.chatAPI.getBackendUrl();
    } catch (e) {
      console.warn("Could not get backend URL from main process:", e);
    }
  }

  // Fallback for dev or if IPC fails
  const url = backendUrl || "ws://127.0.0.1:8765/ws/chat";
  console.log("Connecting to:", url);

  chat = window.chatAPI.connect(url);

  chat.onOpen(() => {
    console.log("Connected to backend");
    wasConnected = true;
    statusDot.style.background = "var(--accent)";
    statusLabel.textContent = "connected";
  });

  chat.onDelta((text) => {
    appendToStream(text);
  });

  chat.onEnd(() => {
    finalizeStream();
  });

  chat.onTranscription((text) => {
    if (text) {
      clearWelcome();
      addMessage(text, "user");
      showTyping();
    }
  });

  chat.onVoiceStatus((listening) => {
    isListening = listening;
    setMicState(listening ? "listening" : "idle");
  });

  chat.onObsStatus((status) => {
    updateObsStatus(status.connected, status.message);
  });

  chat.onError((err) => {
    // Only show error messages if we were previously connected (real errors).
    // Suppress connection-attempt errors to avoid flooding during reconnect.
    if (wasConnected) {
      removeTyping();
      finalizeStream();
      addMessage(`Error: ${err}`, "bot");
    }
    isWaiting = false;
    sendBtn.disabled = input.value.trim().length === 0;
  });

  chat.onClose(() => {
    console.log("Disconnected from backend");
    statusDot.style.background = "#f85149";
    statusLabel.textContent = "disconnected";
    removeTyping();
    finalizeStream();
    setMicState("idle");
    isListening = false;
    isWaiting = false;
    sendBtn.disabled = input.value.trim().length === 0;

    // Reset so we don't show stale error messages on next successful connection
    wasConnected = false;
    setTimeout(connectWebSocket, 3000);
  });
}

connectWebSocket();


function clearWelcome() {
  const welcome = messagesEl.querySelector(".welcome");
  if (welcome) welcome.remove();
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function autosizeTextarea() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 130)}px`;
}

function addMessage(text, role) {
  const div = document.createElement("div");
  div.classList.add("message", role);

  const prefix = document.createElement("div");
  prefix.classList.add("prefix");
  prefix.textContent = role === "user" ? "You" : "Assistant";
  div.appendChild(prefix);

  const content = document.createElement("div");
  content.classList.add("content");
  content.textContent = text;
  div.appendChild(content);

  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}


let streamDiv = null;
let streamContent = null;

function startStream() {
  streamDiv = document.createElement("div");
  streamDiv.classList.add("message", "bot");
  streamDiv.id = "streaming";

  const prefix = document.createElement("div");
  prefix.classList.add("prefix");
  prefix.textContent = "Assistant";
  streamDiv.appendChild(prefix);

  streamContent = document.createElement("div");
  streamContent.classList.add("content");
  streamDiv.appendChild(streamContent);

  messagesEl.appendChild(streamDiv);
  scrollToBottom();
}

function appendToStream(text) {
  if (!streamDiv) startStream();
  removeTyping();
  streamContent.textContent += text;
  scrollToBottom();
}

function finalizeStream() {
  if (streamDiv) {
    streamDiv.removeAttribute("id");
    streamDiv = null;
    streamContent = null;
  }
  isWaiting = false;
  sendBtn.disabled = input.value.trim().length === 0;
  input.focus();
}


function showTyping() {
  const div = document.createElement("div");
  div.classList.add("message", "bot");
  div.id = "typing";

  const prefix = document.createElement("div");
  prefix.classList.add("prefix");
  prefix.textContent = "Assistant";
  div.appendChild(prefix);

  const content = document.createElement("div");
  content.classList.add("content");

  const dots = document.createElement("div");
  dots.classList.add("typing-indicator");
  dots.innerHTML = "<span></span><span></span><span></span>";
  content.appendChild(dots);
  div.appendChild(content);

  messagesEl.appendChild(div);
  scrollToBottom();
}

function removeTyping() {
  const el = document.getElementById("typing");
  if (el) el.remove();
}

//  Voice Listening

function setMicState(state) {
  micBtn.classList.remove("listening");
  if (state === "listening") {
    micBtn.classList.add("listening");
    micBtn.title = "Listening — say \"OBS\" + command (click to stop)";
  } else {
    micBtn.title = "Click to start voice control";
  }
}

function toggleListening() {
  if (isListening) {
    chat.stopListening();
  } else {
    chat.startListening();
  }
}

micBtn.addEventListener("click", toggleListening);


function send() {
  const text = input.value.trim();
  if (!text || isWaiting) return;

  clearWelcome();
  addMessage(text, "user");
  input.value = "";
  autosizeTextarea();
  sendBtn.disabled = true;
  isWaiting = true;

  showTyping();
  chat.send(text);
}


input.addEventListener("input", () => {
  sendBtn.disabled = input.value.trim().length === 0 || isWaiting;
  autosizeTextarea();
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

sendBtn.addEventListener("click", send);

input.focus();
autosizeTextarea();

// Settings
settingsBtn.addEventListener("click", () => {
  settingsPanel.classList.toggle("open");
  settingsBtn.classList.toggle("open");
});

function updateObsStatus(connected, message) {
  if (connected) {
    obsDot.style.background = "var(--accent)";
    obsStatusLabel.textContent = message || "connected";
    obsStatusLabel.style.color = "var(--accent)";
  } else {
    obsDot.style.background = "#f85149";
    obsStatusLabel.textContent = message || "not connected";
    obsStatusLabel.style.color = "#f85149";
  }
  obsConnectBtn.disabled = false;
  obsConnectBtn.textContent = "Connect";
}

obsConnectBtn.addEventListener("click", () => {
  if (!chat) return;

  const port = parseInt(obsPortInput.value, 10) || 4455;
  const password = obsPasswordInput.value;

  obsConnectBtn.disabled = true;
  obsConnectBtn.textContent = "Connecting…";
  obsDot.style.background = "#f0883e";
  obsStatusLabel.textContent = "connecting…";
  obsStatusLabel.style.color = "var(--muted)";

  chat.obsConnect(port, password);
});

// Enter key in password field triggers connect
obsPasswordInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    obsConnectBtn.click();
  }
});
