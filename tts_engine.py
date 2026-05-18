"""TTS Engine — Generates voice commentary using ElevenLabs."""
import logging
import os
import time
import threading
import requests

log = logging.getLogger("tts")

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam
TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

# Rate limiting
MIN_INTERVAL = 12  # seconds between TTS calls
MAX_TEXT_LEN = 200


class TTSEngine:
    """Generates TTS audio and queues it to the AudioMixer."""

    def __init__(self, audio_mixer):
        self.mixer = audio_mixer
        self._last_call = 0
        self._queue: list[str] = []
        self._lock = threading.Lock()
        self._running = True
        self._greeted: set[str] = set()

        if not ELEVENLABS_API_KEY:
            log.warning("No ELEVENLABS_API_KEY — TTS disabled")
            self._running = False
            return

        # Start background thread
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        log.info("TTS engine started")

    def greet(self, username: str):
        """Queue a greeting for a new viewer."""
        if username in self._greeted or username.startswith("Bot-"):
            return
        self._greeted.add(username)
        # Keep greeted set manageable
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
            # Keep queue short
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
        """Call ElevenLabs API and send audio to mixer."""
        try:
            resp = requests.post(
                TTS_URL,
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "style": 0.4,
                        "use_speaker_boost": True,
                    },
                },
                timeout=15,
            )
            if resp.status_code == 200:
                self.mixer.add_tts_mp3(resp.content)
                log.info(f"TTS generated: \"{text[:60]}\" ({len(resp.content)} bytes)")
            else:
                log.warning(f"TTS API error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log.error(f"TTS error: {e}")

    def stop(self):
        self._running = False
