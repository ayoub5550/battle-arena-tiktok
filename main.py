"""Main — Orchestrates Battle Arena game, TTS, audio mixing, and RTMP stream."""
import json as _json
import logging
import os
import signal
import sys

# Write cookies from env var to file (for Railway/Docker)
_cookies_env = os.environ.get("TIKTOK_COOKIES", "")
if _cookies_env:
    try:
        _cdata = _json.loads(_cookies_env)
        os.makedirs("/app", exist_ok=True)
        with open("/app/cookies.json", "w") as _f:
            _json.dump(_cdata, _f)
        print("[init] Cookies written from env ✓")
    except Exception as _e:
        print(f"[init] Cookie parse error: {_e}")
import threading
import time

from game_engine import BattleArena, GIFT_COIN_MAP
from renderer import ArenaRenderer
from audio_mixer import AudioMixer
from tts_engine import TTSEngine
from stream_manager import create_stream, end_stream, start_ffmpeg, AUDIO_FIFO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("main")

# ── TikTokLive events ──
tiktok_live_available = False
try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import (
        CommentEvent, ConnectEvent, DisconnectEvent,
        GiftEvent, JoinEvent, LikeEvent, RoomUserSeqEvent,
    )
    tiktok_live_available = True
    log.info("TikTokLive library loaded ✓")
except ImportError as e:
    log.warning(f"TikTokLive not available: {e}")

SAMPLE_RATE = 44100
CHANNELS = 2
FPS = 15
AUDIO_SAMPLES_PER_FRAME = SAMPLE_RATE // FPS  # 2940

arena = BattleArena()
running = True


def signal_handler(sig, frame):
    global running
    log.info("Shutting down…")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def _prepare_music() -> list[str]:
    """Find all music files — return as a list for sequential playback."""
    music_dir = "/app/music"
    if not os.path.isdir(music_dir):
        music_dir = os.path.join(os.path.dirname(__file__), "music")
    if not os.path.isdir(music_dir):
        return []

    songs = sorted([
        os.path.join(music_dir, f)
        for f in os.listdir(music_dir)
        if f.endswith((".m4a", ".mp3", ".wav", ".ogg", ".aac"))
    ])
    log.info(f"Found {len(songs)} music files: {[os.path.basename(s) for s in songs]}")
    return songs


def _prepare_music_old():
    """Legacy — unused."""
    pass
    if False:
        log.warning(f"Merge failed: {e}, using first song")
        return songs[0]


def start_live_listener(username: str, tts: TTSEngine):
    """Connect to TikTok live events."""
    if not tiktok_live_available or not username:
        log.info("Live listener skipped (no TikTokLive or username)")
        return

    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        log.info(f"Live connected to @{username}")

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        log.warning("Live disconnected")

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent):
        try:
            uid = event.user.unique_id or event.user.nickname
            display = event.user.nickname or event.user.unique_id
            text = event.comment.strip()
            arena.add_message(uid, text, display)
            tts.greet(display)
        except Exception as e:
            log.debug(f"Comment error: {e}")

    @client.on(GiftEvent)
    async def on_gift(event: GiftEvent):
        try:
            user = getattr(event, "user", None)
            uid = "Viewer"
            display = "Viewer"
            if user:
                uid = getattr(user, "unique_id", "Viewer") or "Viewer"
                display = getattr(user, "nickname", uid) or uid

            gift = getattr(event, "gift", None)
            gift_name = getattr(gift, "name", "Gift") if gift else "Gift"
            coins = GIFT_COIN_MAP.get(gift_name, 0)
            if not coins:
                diamond = getattr(gift, "diamond_count", 0) or 1
                repeat = getattr(event, "repeat_count", 1) or 1
                coins = max(1, diamond * repeat)

            arena.gift_powerup(uid, gift_name, coins, display)
            tts.announce_gift(display, gift_name)
            log.info(f"Gift: {display} → {gift_name} ({coins} coins)")
        except Exception as e:
            log.warning(f"Gift error: {e}")

    @client.on(JoinEvent)
    async def on_join(event: JoinEvent):
        try:
            uid = event.user.unique_id or event.user.nickname
            display = event.user.nickname or event.user.unique_id
            arena.add_viewer(uid, display)
            tts.greet(display)
        except Exception:
            pass

    @client.on(LikeEvent)
    async def on_like(event: LikeEvent):
        try:
            count = getattr(event, "total_likes", 1) or 1
            arena.add_like(count)
        except Exception:
            pass

    @client.on(RoomUserSeqEvent)
    async def on_viewer_count(event: RoomUserSeqEvent):
        try:
            arena.viewer_count = getattr(event, "total_user", 0) or 0
        except Exception:
            pass

    def run():
        while running:
            try:
                client.run()
            except Exception as e:
                log.error(f"Live listener error: {e}")
                time.sleep(5)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    log.info("Live listener started")


def process_events(tts: TTSEngine):
    """Process game events and trigger TTS."""
    events = arena.pop_events()
    for ev in events:
        if ev[0] == "join":
            tts.greet(ev[2])  # display_name
        elif ev[0] == "kill":
            tts.announce_kill(ev[2], ev[3])  # killer_display, victim_display
        elif ev[0] == "champion":
            tts.announce_champion(ev[2], ev[3])  # display_name, kills
        elif ev[0] == "gift":
            pass  # Already handled in gift event


def audio_writer(fifo_path: str, mixer: AudioMixer):
    """Background thread: writes mixed audio to FFmpeg via named FIFO."""
    frame_dur = 1.0 / FPS
    log.info(f"Audio writer waiting for FIFO: {fifo_path}")

    # Retry opening — blocks until FFmpeg opens the read end
    fd = None
    for attempt in range(30):
        try:
            fd = os.open(fifo_path, os.O_WRONLY)
            log.info("Audio FIFO opened for writing ✓")
            break
        except OSError as e:
            if attempt < 29:
                time.sleep(1)
            else:
                log.error(f"Cannot open audio FIFO after 30s: {e}")
                return

    while running:
        t0 = time.time()
        chunk = mixer.get_chunk(AUDIO_SAMPLES_PER_FRAME)
        try:
            os.write(fd, chunk)
        except OSError:
            log.error("Audio FIFO broken!")
            break
        elapsed = time.time() - t0
        sleep = frame_dur - elapsed
        if sleep > 0:
            time.sleep(sleep)
    try:
        os.close(fd)
    except OSError:
        pass


def game_loop(ffmpeg_proc, renderer: ArenaRenderer, tts: TTSEngine):
    """Main game loop: step → render → send to FFmpeg."""
    frame_interval = 1.0 / FPS
    step_interval = 0.07  # Game tick speed
    last_step = time.time()
    last_event_check = time.time()

    while running:
        t0 = time.time()

        # Game step
        if t0 - last_step >= step_interval:
            arena.step()
            last_step = t0

        # Process events for TTS every 2 seconds
        if t0 - last_event_check >= 2.0:
            process_events(tts)
            last_event_check = t0

        # Render
        frame_data = renderer.render(arena)

        # Write video frame
        try:
            ffmpeg_proc.stdin.write(frame_data)
        except (BrokenPipeError, OSError):
            log.error("Video pipe broken!")
            break

        elapsed = time.time() - t0
        sleep = frame_interval - elapsed
        if sleep > 0:
            time.sleep(sleep)


def main():
    global running

    log.info("=" * 55)
    log.info("  ⚔  TikTok Battle Arena — Interactive Live Game")
    log.info("=" * 55)

    # Prepare music (list of songs for sequential playback)
    music_paths = _prepare_music()
    mixer = AudioMixer(music_paths, music_volume=0.5)
    tts = TTSEngine(mixer)
    renderer = ArenaRenderer()

    while running:
        # Create TikTok stream
        log.info("Creating TikTok stream…")
        stream_info = create_stream(title="⚔ Battle Arena — Comment to Join! 🎁")
        if not stream_info:
            log.error("Failed to create stream. Retrying in 30s…")
            time.sleep(30)
            continue

        log.info(f"Stream live! Share: {stream_info['share_url']}")

        # Start live listener
        username = os.environ.get("TIKTOK_USERNAME", "")
        start_live_listener(username, tts)

        # Start FFmpeg with file-based audio (no FIFO needed)
        ffmpeg_proc = start_ffmpeg(stream_info["rtmp_url"])

        if ffmpeg_proc is None:
            log.error("FFmpeg failed. Retrying in 15s…")
            try:
                end_stream()
            except Exception:
                pass
            time.sleep(15)
            continue

        # Run game loop
        try:
            game_loop(ffmpeg_proc, renderer, tts)
        except KeyboardInterrupt:
            running = False
        except Exception as e:
            log.error(f"Game loop error: {e}")

        # Cleanup
        log.info("Cleaning up…")
        tts.stop()
        try:
            ffmpeg_proc.stdin.close()
            ffmpeg_proc.wait(timeout=5)
        except Exception:
            ffmpeg_proc.kill()

        if running:
            log.info("Stream ended. Restarting in 10s…")
            try:
                end_stream()
            except Exception:
                pass
            time.sleep(10)

    log.info("Ending stream…")
    try:
        end_stream()
    except Exception:
        pass
    log.info("Goodbye! ⚔")


if __name__ == "__main__":
    main()
