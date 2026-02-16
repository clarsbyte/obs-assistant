import numpy as np
import sounddevice as sd
import whisper
import queue
import sys
import threading

SAMPLE_RATE = 16000       # Whisper expects 16kHz
CHANNELS = 1
BLOCK_DURATION = 0.5      # seconds per audio block
SILENCE_THRESHOLD = 0.01  # RMS below this = silence
SILENCE_TIMEOUT = 1.5     # seconds of silence before transcribing
MIN_SPEECH_DURATION = 0.5 # ignore very short bursts (seconds)

print("Loading Whisper model...")
model = whisper.load_model("base")
print("Model loaded.\n")


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio ** 2)))


def transcribe_audio(audio: np.ndarray) -> str:
    audio_f32 = audio.astype(np.float32).flatten()
    result = model.transcribe(audio_f32, fp16=False)
    return result["text"].strip()


class VoiceListener:
    """Always-on mic listener with VAD. Calls on_transcription(text) from a worker thread."""

    def __init__(self, on_transcription=None):
        self.on_transcription = on_transcription
        self._running = False
        self._audio_buffer = []
        self._silent_count = 0
        self._is_speaking = False
        self._queue = queue.Queue()
        self._listen_thread = None
        self._worker_thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._worker_thread = threading.Thread(target=self._transcribe_loop, daemon=True)
        self._listen_thread.start()
        self._worker_thread.start()
        print("VoiceListener started")

    def stop(self):
        self._running = False
        self._queue.put(None)  # unblock worker
        print("VoiceListener stopped")

    @property
    def running(self):
        return self._running

    def _listen_loop(self):
        block_size = int(SAMPLE_RATE * BLOCK_DURATION)
        silence_blocks = int(SILENCE_TIMEOUT / BLOCK_DURATION)

        def audio_cb(indata, frames, time_info, status):
            if not self._running:
                raise sd.CallbackAbort
            if status:
                print(f"  audio warning: {status}", file=sys.stderr)

            chunk = indata[:, 0].copy()
            level = rms(chunk)

            if level > SILENCE_THRESHOLD:
                if not self._is_speaking:
                    self._is_speaking = True
                    self._silent_count = 0
                self._audio_buffer.append(chunk)
                self._silent_count = 0
            elif self._is_speaking:
                self._audio_buffer.append(chunk)
                self._silent_count += 1

                if self._silent_count >= silence_blocks:
                    full_audio = np.concatenate(self._audio_buffer)
                    duration = len(full_audio) / SAMPLE_RATE
                    self._audio_buffer.clear()
                    self._silent_count = 0
                    self._is_speaking = False

                    if duration >= MIN_SPEECH_DURATION:
                        self._queue.put(full_audio)

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                blocksize=block_size,
                dtype="float32",
                callback=audio_cb,
            ):
                while self._running:
                    sd.sleep(100)
        except sd.CallbackAbort:
            pass
        except Exception as e:
            print(f"VoiceListener stream error: {e}", file=sys.stderr)

    def _transcribe_loop(self):
        while self._running:
            audio = self._queue.get()
            if audio is None:
                break
            try:
                text = transcribe_audio(audio)
                if text and not text.startswith("["):
                    print(f"  Heard: {text}")
                    if self.on_transcription:
                        self.on_transcription(text)
            except Exception as e:
                print(f"  Transcription error: {e}", file=sys.stderr)



def listen_and_transcribe(callback=None):
    listener = VoiceListener(on_transcription=callback or (lambda t: print(f"  You said: {t}")))
    listener.start()
    print("Listening... (speak into your mic, Ctrl+C to stop)\n")
    try:
        while True:
            sd.sleep(100)
    except KeyboardInterrupt:
        listener.stop()
        print("\nStopped listening.")


def test_mic():
    print("-- Available audio devices --")
    print(sd.query_devices())
    default = sd.query_devices(kind="input")
    print(f"\n  Default input: {default['name']}\n")

    print("-- Live mic levels (speak now, 5 seconds) --")
    block_size = int(SAMPLE_RATE * 0.1)

    def show_level(indata, frames, time_info, status):
        level = rms(indata[:, 0])
        bars = int(level * 300)
        bar = "#" * min(bars, 50)
        print(f"  {level:.5f} |{bar}", end="\r")

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        blocksize=block_size, dtype="float32",
                        callback=show_level):
        sd.sleep(5000)

    print(f"\n\nDone. SILENCE_THRESHOLD = {SILENCE_THRESHOLD}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test mic levels")
    args = parser.parse_args()

    if args.test:
        test_mic()
    else:
        listen_and_transcribe()
