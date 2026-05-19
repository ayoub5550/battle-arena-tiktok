"""Main — Snake AI Game on TikTok Live with music + TTS commentary."""
import logging
import os
import signal
import sys
import threading
import time

import numpy as np

from game import SnakeGame
from stream_manager import (
    create_stream, end_stream, start_ffmpeg,
    setup_audio_fifo, AUDIO_FIFO,
)
from audio_mixer import AudioMixer
from tts_engine import TTSEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("main")

# ── TikTok live events ──
chat_available = False
try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import (
        CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent,
        JoinEvent, RoomUserSeqEvent,
    )
    chat_available = True
    log.info("TikTokLive library loaded ✓")
except ImportError as e:
    log.warning(f"TikTokLive not available: {e}")


game = SnakeGame()
running = True

GIFT_APPLE_MAP = {
    "Rose": 5, "rose": 5, "TikTok": 5, "Finger Heart": 5, "GG": 5,
    "Ice Cream Cone": 10, "Doughnut": 15, "Perfume": 20,
    "Bouquet": 50, "Love You": 50, "Garland": 50, "Sunglasses": 50,
    "Hand Hearts": 100, "Butterfly": 100, "Family": 100,
    "Hat and Mustache": 150, "Corgi": 150, "Cap": 150,
    "Hands Up": 499, "Donate": 499, "Gaming Keyboard": 499,
    "Train": 1000, "Elephant": 1000, "Gift Box": 1500,
    "Lion": 1500, "Universe": 2000, "Whale": 5000,
}


def signal_handler(sig, frame):
    global running
    log.info("Shutting down…")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def start_live_listener(username: str, tts: TTSEngine):
    """Connect to TikTok live chat/gifts and feed to game + TTS."""
    if not chat_available or not username:
        log.info(f"Live listener skipped (chat={chat_available}, user={username!r})")
        return

    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        log.info(f"Live connected to @{username}")

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        log.warning("Live disconnected — will reconnect…")

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent):
        try:
            user = event.user.nickname or event.user.unique_id
            text = event.comment.strip()
            game.add_message(user, text)
        except Exception as e:
            log.debug(f"Comment error: {e}")

    @client.on(GiftEvent)
    async def on_gift(event: GiftEvent):
        try:
            user = getattr(event, "user", None)
            uname = "Viewer"
            if user:
                uname = getattr(user, "nickname", "") or getattr(user, "unique_id", "Viewer")
            gift = getattr(event, "gift", None)
            gift_name = getattr(gift, "name", "") if gift else ""
            if gift_name in GIFT_APPLE_MAP:
                apple_count = GIFT_APPLE_MAP[gift_name]
            else:
                coins = getattr(gift, "diamond_count", 0) or 1
                repeat = getattr(event, "repeat_count", 1) or 1
                apple_count = max(1, int(coins * repeat * 0.5))
            game.add_apples(uname, apple_count)
            tts.announce_gift(uname, gift_name or "gift")
            log.info(f"Gift: {uname} → {gift_name} → +{apple_count} apples")
        except Exception as e:
            log.warning(f"Gift error: {e}")

    @client.on(JoinEvent)
    async def on_join(event: JoinEvent):
        try:
            user = event.user.nickname or event.user.unique_id
            tts.greet(user)
        except:
            pass

    @client.on(RoomUserSeqEvent)
    async def on_viewer_count(event: RoomUserSeqEvent):
        try:
            game.viewer_count = getattr(event, "total_user", 0) or 0
        except:
            pass

    def run_listener():
        while running:
            try:
                client.run()
            except Exception as e:
                log.error(f"Live listener error: {e}")
                time.sleep(5)

    t = threading.Thread(target=run_listener, daemon=True)
    t.start()
    log.info("Live listener thread started")


def audio_writer(fifo_path: str, mixer: AudioMixer):
    """Write mixed audio to FIFO continuously."""
    log.info(f"Audio writer waiting for FIFO: {fifo_path}")
    fd = os.open(fifo_path, os.O_WRONLY)
    log.info("Audio FIFO opened for writing ✓")
    chunk_samples = 1024  # samples per channel per chunk
    try:
        while running:
            data = mixer.get_chunk(chunk_samples)
            try:
                os.write(fd, data)
            except OSError:
                break
    except Exception as e:
        log.error(f"Audio writer error: {e}")
    finally:
        os.close(fd)


def game_loop(ffmpeg_proc, tts: TTSEngine):
    """Main loop: step game → render → send frame to FFmpeg, with TTS."""
    frame_interval = 1.0 / 15  # 15 FPS
    step_interval = 0.08       # snake moves every 80ms
    last_step = time.time()
    last_score = 0
    last_milestone = 0

    while running:
        t0 = time.time()

        if t0 - last_step >= step_interval:
            game.step()
            last_step = t0

            # TTS for score milestones
            if game.score > last_score:
                last_score = game.score
                if game.score % 25 == 0 and game.score != last_milestone:
                    last_milestone = game.score
                    tts.say(f"Amazing! Score reached {game.score}! Snake length {len(game.snake)}!")
            # TTS when snake dies
            if not game.alive and last_score > 0:
                tts.say(f"Snake died at score {last_score}. New game starting!")
                last_score = 0

        frame_data = game.render()
        try:
            ffmpeg_proc.stdin.write(frame_data)
        except (BrokenPipeError, OSError):
            log.error("FFmpeg pipe broken!")
            break

        elapsed = time.time() - t0
        sleep_time = frame_interval - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


def main():
    global running

    log.info("=" * 55)
    log.info("  🐍 TikTok Snake AI — Interactive Live Stream")
    log.info("=" * 55)

    # Discover music
    music_dir = "/app/music"
    music_files = []
    if os.path.isdir(music_dir):
        music_files = sorted([
            os.path.join(music_dir, f) for f in os.listdir(music_dir)
            if f.endswith((".m4a", ".mp3", ".wav", ".ogg", ".aac"))
        ])
    log.info(f"Found {len(music_files)} music files: {[os.path.basename(f) for f in music_files]}")

    # Audio mixer: music at 50% volume
    mixer = AudioMixer(music_files, music_volume=0.5)
    tts = TTSEngine(mixer)

    while running:
        log.info("Creating TikTok stream…")
        stream_info = create_stream(title="🐍 Snake AI Live — Send Gifts = More Apples! 🍎")
        if not stream_info:
            log.error("Failed to create stream. Retrying in 30s…")
            time.sleep(30)
            continue

        log.info(f"Stream live! Share: {stream_info['share_url']}")

        # Live listener
        username = os.environ.get("TIKTOK_USERNAME", "")
        start_live_listener(username, tts)

        # FIFO audio
        setup_audio_fifo()
        audio_thread = threading.Thread(target=audio_writer, args=(AUDIO_FIFO, mixer), daemon=True)
        audio_thread.start()

        # FFmpeg
        ffmpeg_proc = start_ffmpeg(stream_info["rtmp_url"])
        if ffmpeg_proc is None:
            log.error("FFmpeg failed. Retrying in 15s…")
            try:
                end_stream()
            except:
                pass
            time.sleep(15)
            continue

        # Game loop
        try:
            game_loop(ffmpeg_proc, tts)
        except KeyboardInterrupt:
            running = False
        except Exception as e:
            log.error(f"Game loop error: {e}")

        # Cleanup
        log.info("Cleaning up…")
        try:
            ffmpeg_proc.stdin.close()
            ffmpeg_proc.wait(timeout=5)
        except:
            ffmpeg_proc.kill()

        if running:
            log.info("Stream ended. Restarting in 30s…")
            try:
                end_stream()
            except:
                pass
            time.sleep(30)

    log.info("Ending stream…")
    try:
        end_stream()
    except:
        pass
    tts.stop()
    log.info("Goodbye! 🐍")


if __name__ == "__main__":
    main()
