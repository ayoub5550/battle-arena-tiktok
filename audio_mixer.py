"""Audio Mixer — Mixes background music + TTS into raw PCM for FFmpeg."""
import logging
import os
import subprocess
import threading
import numpy as np

log = logging.getLogger("audio")

SAMPLE_RATE = 44100
CHANNELS = 2
BYTES_PER_SAMPLE = 2  # s16le


class AudioMixer:
    """Mixes looped background music with TTS clips in real-time."""

    def __init__(self, music_path: str, music_volume: float = 0.5):
        self.music_volume = music_volume
        self.music_data: np.ndarray | None = None
        self.music_pos = 0
        self._tts_queue: list[np.ndarray] = []
        self._tts_active: list[dict] = []
        self._lock = threading.Lock()

        if music_path and os.path.exists(music_path):
            self.music_data = self._decode_audio(music_path)
            if self.music_data is not None:
                log.info(f"Music loaded: {len(self.music_data)} samples ({len(self.music_data) / SAMPLE_RATE / CHANNELS:.1f}s)")
            else:
                log.warning("Failed to decode music")
        else:
            log.warning(f"Music file not found: {music_path}")

    @staticmethod
    def _decode_audio(path: str) -> np.ndarray | None:
        """Decode any audio file to raw PCM s16le stereo 44100Hz."""
        try:
            cmd = [
                "ffmpeg", "-y", "-i", path,
                "-f", "s16le", "-acodec", "pcm_s16le",
                "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
                "pipe:1",
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode != 0:
                log.error(f"FFmpeg decode error: {result.stderr.decode(errors='replace')[-300:]}")
                return None
            data = np.frombuffer(result.stdout, dtype=np.int16)
            if len(data) < SAMPLE_RATE:
                log.warning("Decoded audio too short")
                return None
            return data
        except Exception as e:
            log.error(f"Audio decode error: {e}")
            return None

    def add_tts(self, pcm_bytes: bytes):
        """Queue a TTS audio clip (raw PCM s16le stereo 44100Hz) for mixing."""
        try:
            data = np.frombuffer(pcm_bytes, dtype=np.int16)
            if len(data) > 0:
                with self._lock:
                    self._tts_queue.append(data)
                log.info(f"TTS queued: {len(data)} samples ({len(data) / SAMPLE_RATE / CHANNELS:.1f}s)")
        except Exception as e:
            log.error(f"TTS queue error: {e}")

    def add_tts_mp3(self, mp3_bytes: bytes):
        """Queue a TTS clip from MP3 bytes."""
        try:
            cmd = [
                "ffmpeg", "-y", "-f", "mp3", "-i", "pipe:0",
                "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
                "pipe:1",
            ]
            result = subprocess.run(cmd, input=mp3_bytes, capture_output=True, timeout=15)
            if result.returncode == 0 and len(result.stdout) > 0:
                self.add_tts(result.stdout)
            else:
                log.warning(f"TTS MP3 decode failed")
        except Exception as e:
            log.error(f"TTS MP3 decode error: {e}")

    def get_chunk(self, num_samples: int) -> bytes:
        """Get mixed audio chunk. num_samples = samples per channel."""
        total = num_samples * CHANNELS
        chunk = np.zeros(total, dtype=np.float32)

        # Music
        if self.music_data is not None and len(self.music_data) > 0:
            remaining = total
            pos = 0
            while remaining > 0:
                avail = len(self.music_data) - self.music_pos
                take = min(remaining, avail)
                chunk[pos:pos + take] = self.music_data[self.music_pos:self.music_pos + take].astype(np.float32) * self.music_volume
                self.music_pos += take
                pos += take
                remaining -= take
                if self.music_pos >= len(self.music_data):
                    self.music_pos = 0

        # Move queued TTS to active
        with self._lock:
            while self._tts_queue:
                self._tts_active.append({"data": self._tts_queue.pop(0), "pos": 0})

        # Mix TTS
        for tts in self._tts_active:
            avail = len(tts["data"]) - tts["pos"]
            take = min(total, avail)
            chunk[:take] += tts["data"][tts["pos"]:tts["pos"] + take].astype(np.float32)
            tts["pos"] += take

        # Remove finished TTS
        self._tts_active = [t for t in self._tts_active if t["pos"] < len(t["data"])]

        # Clip and convert
        chunk = np.clip(chunk, -32768, 32767).astype(np.int16)
        return chunk.tobytes()
