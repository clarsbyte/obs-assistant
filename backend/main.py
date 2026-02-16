import argparse
import asyncio
import ctypes
import ctypes.wintypes
import json
import re
import socket
import time
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
import obsws_python as obs
from obsws_python.error import OBSSDKError, OBSSDKRequestError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

from voice import VoiceListener


def pick_port() -> int:
    """Bind to an ephemeral port and return the number."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@dataclass
class Deps:
    obs_client: obs.ReqClient | None


def _current_scene(cl: obs.ReqClient) -> str:
    return cl.get_current_program_scene().scene_name


def _get_sources(cl: obs.ReqClient, scene: str) -> list[dict]:
    return cl.get_scene_item_list(scene).scene_items


def _exact_match_source(name: str, sources: list[dict]) -> dict | None:
    """Find a source by exact name (case-insensitive)."""
    name_lower = name.lower().strip()
    for src in sources:
        if src["sourceName"].lower() == name_lower:
            return src
    return None


def _available_sources_str(sources: list[dict]) -> str:
    """Format available source names for error messages."""
    if not sources:
        return "none"
    return ", ".join(f"'{s['sourceName']}'" for s in sources)


ollama_model = OpenAIChatModel(
    model_name='qwen3:0.6b',
    provider=OllamaProvider(base_url='http://localhost:11434/v1'),
)

agent = Agent(
    ollama_model,
    deps_type=Deps,
    output_type=str,
    retries=3,
    system_prompt=(
        'You control OBS Studio. ALWAYS call a tool. NEVER reply with instructions or questions.\n'
        'The current scene and sources are listed below. Use the EXACT source name from the list.\n'
        '\n'
        'Rules:\n'
        '- "show X" or "hide X" → find the closest source name from the list, call show_source/hide_source with that EXACT name.\n'
        '- "add text ..." → call add_text.\n'
        '- "start/stop recording" → call recording with action="start" or "stop".\n'
        '- "start/stop streaming" → call streaming with action="start" or "stop".\n'
        '- "capture window ..." → call list_windows, then add_window_capture.\n'
        '\n'
        'Name matching examples:\n'
        '- User says "capture 6" and sources include "capture_6" → use "capture_6"\n'
        '- User says "display capture" and sources include "Display Capture 2" → use "Display Capture 2"\n'
        '- User says "webcam" and sources include "Video Capture Device" → use "Video Capture Device"\n'
        '\n'
        'Just DO it. Never ask "would you like..." — act immediately.\n'
    ),
)


@agent.system_prompt
async def inject_sources(ctx: RunContext[Deps]) -> str:
    """Dynamically inject the current OBS scene + source names into the prompt."""
    if ctx.deps.obs_client is None:
        return 'OBS is NOT connected. Tell the user to connect first.'
    try:
        cl = ctx.deps.obs_client
        scene = _current_scene(cl)
        sources = _get_sources(cl, scene)
        if not sources:
            return f'Current scene: {scene}\nNo sources in this scene.'
        lines = [f'Current scene: {scene}', 'Sources:']
        for s in sources:
            status = 'visible' if s['sceneItemEnabled'] else 'hidden'
            lines.append(f'  - "{s["sourceName"]}" ({status})')
        return '\n'.join(lines)
    except Exception as e:
        return f'Could not read OBS sources: {e}'


@agent.tool
async def list_sources(ctx: RunContext[Deps]) -> str:
    """List all sources in the current OBS scene. Scene is auto-detected."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        scene = _current_scene(cl)
        sources = _get_sources(cl, scene)
        lines = [f"Scene: {scene}"]
        for item in sources:
            status = "visible" if item["sceneItemEnabled"] else "hidden"
            lines.append(f"  - {item['sourceName']} ({status})")
        return "\n".join(lines) if len(lines) > 1 else f"Scene: {scene}\n  No sources found."
    except Exception as e:
        return f"Error listing sources: {e}"


@agent.tool
async def hide_source(ctx: RunContext[Deps], source_name: str) -> str:
    """Hide a source. Use the exact source name from the source list."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        scene = _current_scene(cl)
        sources = _get_sources(cl, scene)
        match = _exact_match_source(source_name, sources)
        if match is None:
            available = _available_sources_str(sources)
            return f"No source named '{source_name}'. Available sources: {available}. Call this tool again with the exact name."
        cl.set_scene_item_enabled(scene, match["sceneItemId"], False)
        return f"Done — '{match['sourceName']}' is now hidden in '{scene}'"
    except Exception as e:
        return f"Error hiding source: {e}"


@agent.tool
async def show_source(ctx: RunContext[Deps], source_name: str) -> str:
    """Show a source. Use the exact source name from the source list."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        scene = _current_scene(cl)
        sources = _get_sources(cl, scene)
        match = _exact_match_source(source_name, sources)
        if match is None:
            available = _available_sources_str(sources)
            return f"No source named '{source_name}'. Available sources: {available}. Call this tool again with the exact name."
        cl.set_scene_item_enabled(scene, match["sceneItemId"], True)
        return f"Done — '{match['sourceName']}' is now visible in '{scene}'"
    except Exception as e:
        return f"Error showing source: {e}"


@agent.tool
async def edit_text(ctx: RunContext[Deps], source_name: str, text: str) -> str:
    """Edit text of an existing text source. Use the exact source name from the source list."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        scene = _current_scene(cl)
        sources = _get_sources(cl, scene)
        match = _exact_match_source(source_name, sources)
        if match is None:
            available = _available_sources_str(sources)
            return f"No source named '{source_name}'. Available sources: {available}. Call this tool again with the exact name."
        cl.set_input_settings(match["sourceName"], {"text": text}, True)
        return f"Done — updated text of '{match['sourceName']}' to: {text}"
    except Exception as e:
        return f"Error editing text: {e}"


@agent.tool
async def add_text(ctx: RunContext[Deps], text: str) -> str:
    """Add a text overlay centered on screen. Just provide the text content."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        scene = _current_scene(cl)

        # Unique source name so we don't collide
        input_name = f"Text - {text[:20]}" if len(text) > 20 else f"Text - {text}"

        # Create a GDI+ text source (Windows) with sensible defaults
        settings = {
            "text": text,
            "font": {"face": "Arial", "size": 72, "style": "Bold", "flags": 0},
            "color": 0xFFFFFFFF,   # white (ABGR)
            "align": "center",
            "valign": "center",
        }
        resp = cl.create_input(scene, input_name, "text_gdiplus_v2", settings, True)
        item_id = resp.scene_item_id

        cl.set_input_settings(input_name, {"text": text}, True)

        # Give OBS a moment to render the source so dimensions are available
        time.sleep(0.15)

        # Get canvas size
        video = cl.get_video_settings()
        canvas_w = video.base_width
        canvas_h = video.base_height

        # Get the text source's rendered size
        transform = cl.get_scene_item_transform(scene, item_id)
        src_w = transform.scene_item_transform["sourceWidth"]
        src_h = transform.scene_item_transform["sourceHeight"]

        # Center it
        pos_x = (canvas_w - src_w) / 2
        pos_y = (canvas_h - src_h) / 2
        cl.set_scene_item_transform(scene, item_id, {
            "positionX": pos_x,
            "positionY": pos_y,
        })

        return (
            f"Done — added '{input_name}' centered on '{scene}' "
            f"(canvas {canvas_w}x{canvas_h}, text {src_w:.0f}x{src_h:.0f}, "
            f"pos {pos_x:.0f},{pos_y:.0f})"
        )
    except Exception as e:
        return f"Error adding text: {e}"


@agent.tool
async def recording(ctx: RunContext[Deps], action: str) -> str:
    """Start or stop OBS recording. Use action='start' to begin or action='stop' to end."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        status = cl.get_record_status()
        if action.lower().strip() == "start":
            if status.output_active:
                return "Recording is already in progress."
            cl.start_record()
            return "Done — recording started."
        elif action.lower().strip() == "stop":
            if not status.output_active:
                return "Recording is not running."
            resp = cl.stop_record()
            return f"Done — recording stopped. Saved to: {resp.output_path}"
        else:
            return f"Unknown action '{action}'. Use 'start' or 'stop'."
    except Exception as e:
        return f"Error with recording: {e}"


@agent.tool
async def streaming(ctx: RunContext[Deps], action: str) -> str:
    """Start or stop OBS streaming. Use action='start' to begin or action='stop' to end."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        status = cl.get_stream_status()
        if action.lower().strip() == "start":
            if status.output_active:
                return "Stream is already live."
            cl.start_stream()
            return "Done — stream started."
        elif action.lower().strip() == "stop":
            if not status.output_active:
                return "Stream is not running."
            cl.stop_stream()
            return "Done — stream stopped."
        else:
            return f"Unknown action '{action}'. Use 'start' or 'stop'."
    except Exception as e:
        return f"Error with streaming: {e}"


def _list_windows() -> list[dict]:
    """List visible windows with titles using the Windows API."""
    windows = []
    user32 = ctypes.windll.user32

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = ""
        try:
            import ctypes as ct
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ct.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if h:
                exe_buf = ct.create_unicode_buffer(260)
                size = ct.wintypes.DWORD(260)
                ct.windll.kernel32.QueryFullProcessImageNameW(h, 0, exe_buf, ct.byref(size))
                ct.windll.kernel32.CloseHandle(h)
                exe = exe_buf.value.split("\\")[-1] if exe_buf.value else ""
        except Exception:
            pass
        # Get class name
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buf, 256)
        windows.append({
            "title": title,
            "exe": exe,
            "class": class_buf.value,
            "hwnd": hwnd,
        })
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return windows


@agent.tool
async def list_windows(ctx: RunContext[Deps]) -> str:
    """List all visible windows that can be used as a window capture source."""
    try:
        windows = _list_windows()
        if not windows:
            return "No visible windows found."
        lines = ["Available windows:"]
        for i, w in enumerate(windows, 1):
            exe_part = f" [{w['exe']}]" if w['exe'] else ""
            lines.append(f"  {i}. {w['title']}{exe_part}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing windows: {e}"


@agent.tool
async def add_window_capture(ctx: RunContext[Deps], window_title: str) -> str:
    """Add a window capture source for a specific window. Provide the window title (or part of it) to capture."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        scene = _current_scene(cl)

        # Find the window
        windows = _list_windows()
        title_lower = window_title.lower().strip()
        match = None
        for w in windows:
            if title_lower in w["title"].lower():
                match = w
                break
        if match is None:
            available = ", ".join(f"'{w['title']}'" for w in windows[:10])
            return f"No window matching '{window_title}'. Some available: {available}"

        # OBS window capture format: "title:class:exe"
        window_value = f"{match['title']}:{match['class']}:{match['exe']}"
        source_name = f"Window - {match['title'][:30]}"

        settings = {
            "window": window_value,
            "capture_method": "auto",
        }
        cl.create_input(scene, source_name, "window_capture", settings, True)
        return f"Done — added window capture '{source_name}' for '{match['title']}' in '{scene}'"
    except Exception as e:
        return f"Error adding window capture: {e}"


@agent.tool
async def change_window_capture(ctx: RunContext[Deps], source_name: str, window_title: str) -> str:
    """Change which window an existing window capture source is capturing. Provide the source name and the new window title."""
    if ctx.deps.obs_client is None:
        return "Error: OBS is not connected."
    try:
        cl = ctx.deps.obs_client
        scene = _current_scene(cl)
        sources = _get_sources(cl, scene)
        match_src = _exact_match_source(source_name, sources)
        if match_src is None:
            available = _available_sources_str(sources)
            return f"No source named '{source_name}'. Available sources: {available}."

        # Find the target window
        windows = _list_windows()
        title_lower = window_title.lower().strip()
        match_win = None
        for w in windows:
            if title_lower in w["title"].lower():
                match_win = w
                break
        if match_win is None:
            available = ", ".join(f"'{w['title']}'" for w in windows[:10])
            return f"No window matching '{window_title}'. Some available: {available}"

        window_value = f"{match_win['title']}:{match_win['class']}:{match_win['exe']}"
        cl.set_input_settings(match_src["sourceName"], {"window": window_value}, True)
        return f"Done — '{match_src['sourceName']}' now captures '{match_win['title']}'"
    except Exception as e:
        return f"Error changing window capture: {e}"


app = FastAPI()

# OBS client is no longer connected at startup.
# The user will provide port + password from the UI.
obs_client: obs.ReqClient | None = None


def connect_obs(port: int, password: str) -> tuple[obs.ReqClient | None, str]:
    """Try to connect to OBS and return (client, status_message)."""
    try:
        cl = obs.ReqClient(host="localhost", port=port, password=password, timeout=5)
        version = cl.get_version()
        msg = f"Connected — OBS {version.obs_version}"
        print(msg)
        return cl, msg
    except (OBSSDKError, ConnectionRefusedError, Exception) as e:
        msg = str(e)
        print(f"OBS connection failed: {msg}")
        return None, msg


async def _handle_agent_stream(ws: WebSocket, user_message: str, deps: Deps):
    """Run the agent with streaming, fall back to non-streaming on timeout/errors."""
    await ws.send_text(json.dumps({"type": "stream_start"}))
    try:
        result = await asyncio.wait_for(
            _run_agent_non_stream(user_message, deps), timeout=30
        )
        await ws.send_text(json.dumps({
            "type": "stream_delta",
            "content": result,
        }))
        await ws.send_text(json.dumps({"type": "stream_end"}))
    except asyncio.TimeoutError:
        await ws.send_text(json.dumps({
            "type": "error",
            "content": "Request timed out — the model took too long to respond.",
        }))
    except Exception as e:
        await ws.send_text(json.dumps({
            "type": "error",
            "content": str(e),
        }))


async def _run_agent_non_stream(user_message: str, deps: Deps) -> str:
    """Run agent without streaming — more reliable with small models."""
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            result = await agent.run(user_message, deps=deps)
            if result.output is None or result.output.strip() == "":
                if attempt < max_attempts - 1:
                    print(f"  Empty response from model, retrying ({attempt + 1}/{max_attempts})...")
                    continue
                return "Sorry, I couldn't generate a response. Please try again."
            return result.output
        except Exception as e:
            err_str = str(e)
            # qwen3 sometimes sends nil content during tool-call reasoning
            if "invalid_request_error" in err_str or "nil" in err_str:
                if attempt < max_attempts - 1:
                    print(f"  Model returned nil content, retrying ({attempt + 1}/{max_attempts})...")
                    continue
            raise
    return "Sorry, I couldn't generate a response after multiple attempts."


# wake word
_WAKE_RE = re.compile(r"\bobs[\s,.:!?]+(.+)", re.IGNORECASE)


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    global obs_client
    await ws.accept()
    deps = Deps(obs_client=obs_client)
    loop = asyncio.get_event_loop()
    listener: VoiceListener | None = None

    # Send current OBS status on connect
    await ws.send_text(json.dumps({
        "type": "obs_status",
        "connected": obs_client is not None,
        "message": "connected" if obs_client is not None else "not connected",
    }))

    # Callback fired from VoiceListener's worker thread
    def on_transcription(text: str):
        asyncio.run_coroutine_threadsafe(_handle_transcription(text), loop)

    async def _handle_transcription(text: str):
        m = _WAKE_RE.search(text.strip())
        if m:
            command = m.group(1).strip()
            print(f"  Wake word detected — command: '{command}'")
            await ws.send_text(json.dumps({
                "type": "transcription",
                "content": text,
            }))
            await _handle_agent_stream(ws, command, deps)
        else:
            print(f"  Ignored (no wake word): '{text}'")

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "message":
                user_message = data.get("content", "")
                if not user_message:
                    continue
                await _handle_agent_stream(ws, user_message, deps)

            elif msg_type == "obs_connect":
                port = int(data.get("port", 4455))
                password = data.get("password", "")
                client, msg = connect_obs(port, password)
                obs_client = client
                deps.obs_client = client
                await ws.send_text(json.dumps({
                    "type": "obs_status",
                    "connected": client is not None,
                    "message": msg,
                }))

            elif msg_type == "voice_start":
                if listener is None or not listener.running:
                    listener = VoiceListener(on_transcription=on_transcription)
                    listener.start()
                await ws.send_text(json.dumps({
                    "type": "voice_status",
                    "listening": True,
                }))

            elif msg_type == "voice_stop":
                if listener and listener.running:
                    listener.stop()
                    listener = None
                await ws.send_text(json.dumps({
                    "type": "voice_status",
                    "listening": False,
                }))

    except WebSocketDisconnect:
        if listener and listener.running:
            listener.stop()
        print("Client disconnected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OBS Assistant backend")
    parser.add_argument("--port", type=int, default=0, help="Port to listen on (0 = auto-pick)")
    args = parser.parse_args()

    port = args.port if args.port != 0 else pick_port()
    print(f"PORT={port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port)
