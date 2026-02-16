const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("chatAPI", {
  /** Ask the main process for the backend WebSocket URL */
  getBackendUrl: () => ipcRenderer.invoke("get-backend-url"),

  connect: (url) => {
    let ws = null;
    let deltaCallback = null;
    let endCallback = null;
    let errorCallback = null;
    let openCallback = null;
    let closeCallback = null;
    let transcriptionCallback = null;
    let voiceStatusCallback = null;
    let obsStatusCallback = null;

    ws = new WebSocket(url);

    ws.onopen = () => {
      if (openCallback) openCallback();
    };

    ws.onclose = () => {
      if (closeCallback) closeCallback();
    };

    ws.onerror = () => {
      if (errorCallback) errorCallback("WebSocket connection error");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "stream_start":
            break;
          case "stream_delta":
            if (deltaCallback) deltaCallback(data.content);
            break;
          case "stream_end":
            if (endCallback) endCallback();
            break;
          case "transcription":
            if (transcriptionCallback) transcriptionCallback(data.content);
            break;
          case "voice_status":
            if (voiceStatusCallback) voiceStatusCallback(data.listening);
            break;
          case "obs_status":
            if (obsStatusCallback) obsStatusCallback(data);
            break;
          case "error":
            if (errorCallback) errorCallback(data.content);
            break;
        }
      } catch (e) {
        if (errorCallback) errorCallback("Failed to parse server message");
      }
    };

    return {
      send: (message) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "message", content: message }));
        }
      },
      startListening: () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "voice_start" }));
        }
      },
      stopListening: () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "voice_stop" }));
        }
      },
      obsConnect: (port, password) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "obs_connect", port, password }));
        }
      },
      onOpen: (cb) => { openCallback = cb; },
      onDelta: (cb) => { deltaCallback = cb; },
      onEnd: (cb) => { endCallback = cb; },
      onError: (cb) => { errorCallback = cb; },
      onClose: (cb) => { closeCallback = cb; },
      onTranscription: (cb) => { transcriptionCallback = cb; },
      onVoiceStatus: (cb) => { voiceStatusCallback = cb; },
      onObsStatus: (cb) => { obsStatusCallback = cb; },
      close: () => {
        if (ws) ws.close();
      },
    };
  },
});
