"""TTS Engine — Generates voice commentary using edge-tts (free, no API key)."""
import asyncio
import io
import logging
import os
import subprocess
import tempfile
import time
import threading

log = logging.getLogger("tts")

# edge-tts voice
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")

# Rate limiting
MIN_INTERVAL = 8  # seconds between TTS calls
MAX_TEXT_LEN = 200


class TTSEngine:
    """Generates TTS audio using edge-tts and queues it to the AudioMixer."""

    def __init__(self, audio_mixer):
        self.mixer = audio_mixer
        self._last_call = 0
        self._queue: list[str] = []
        self._lock = threading.Lock()
        self._running = True
        self._greeted: set[str] = set()

        # Start background thread
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        log.info("TTS engine started")

    def greet(self, username: str):
        """Queue a greeting for a new viewer."""
        if username in self._greeted or username.startswith("Bot-"):
            return
        self._greeted.add(username)
        if len(self._greeted) > 500:
            self._greeted = set(list(self._greeted)[-200:])
        self.say(f"Hello {username}! Welcome to the battle!")

    def announce_kill(self, killer: str, victim: str):
        self.say(f"{killer} eliminated {victim}!")

    def announce_gift(self, username: str, gift_name: str):
        self.say(f"Thank you {username} for the {gift_name}! Power up!")

    def announce_champion(self, username: str, kills: int):
        self.say(f"New champion! {username} with {kills} kills!")

    def say(self, text: str):
        """Queue text for TTS generation."""
        if not self._running:
            return
        with self._lock:
            if len(self._queue) > 5:
                self._queue = self._queue[-3:]
            self._queue.append(text[:MAX_TEXT_LEN])

    def _worker(self):
        """Background thread that processes TTS queue."""
        while self._running:
            text = None
            with self._lock:
                if self._queue:
                    text = self._queue.pop(0)

            if text:
                now = time.time()
                wait = MIN_INTERVAL - (now - self._last_call)
                if wait > 0:
                    time.sleep(wait)
                self._generate(text)
                self._last_call = time.time()
            else:
                time.sleep(1)

    def _generate(self, text: str):
        """Use edge-tts CLI to generate audio, then feed to mixer."""
        tmp_mp3 = None
        try:
            tmp_mp3 = tempfile.mktemp(suffix=".mp3")
            result = subprocess.run(
                ["edge-tts", "--voice", TTS_VOICE, "--text", text, "--write-media", tmp_mp3],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                log.warning(f"edge-tts failed: {result.stderr[:200]}")
                return

            with open(tmp_mp3, "rb") as f:
                mp3_data = f.read()

            if mp3_data:
                self.mixer.add_tts_mp3(mp3_data)
                log.info(f'TTS: "{text[:60]}" ({len(mp3_data)} bytes)')
            else:
                log.warning("edge-tts produced empty audio")
        except subprocess.TimeoutExpired:
            log.warning("edge-tts timeout")
        except Exception as e:
            log.error(f"TTS error: {e}")
        finally:
            if tmp_mp3:
                try:
                    os.unlink(tmp_mp3)
                except:
                    pass

    def stop(self):
        self._running = False
