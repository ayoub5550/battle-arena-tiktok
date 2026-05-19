"""Video Stream on TikTok Live — loops a video 24/7 with background music."""
import logging
import os
import signal
import subprocess
import sys
import time

from stream_manager import create_stream, end_stream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("main")

VIDEO_PATH = "/app/video.mp4"
MUSIC_DIR = "/app/music"
MUSIC_CONCAT = "/tmp/music_all.txt"  # FFmpeg concat list
STREAM_TITLE = os.environ.get(
    "STREAM_TITLE",
    "🎮 Elden Ring — All Bosses NO DAMAGE | 24/7",
)

# ── Settings ──
VIDEO_SPEED = float(os.environ.get("VIDEO_SPEED", "1.3"))
VIDEO_VOLUME = float(os.environ.get("VIDEO_VOLUME", "1.0"))  # 100%
MUSIC_VOLUME = float(os.environ.get("MUSIC_VOLUME", "0.5"))  # 50%
SATURATION = float(os.environ.get("SATURATION", "1.35"))
OUTPUT_FPS = int(os.environ.get("OUTPUT_FPS", "30"))
VIDEO_BITRATE = os.environ.get("VIDEO_BITRATE", "2500k")

running = True


def handle_signal(sig, frame):
    global running
    log.info(f"Signal {sig} received, shutting down...")
    running = False


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def download_video():
    """Download video from URL if not present locally."""
    if os.path.exists(VIDEO_PATH):
        size = os.path.getsize(VIDEO_PATH)
        if size > 10_000_000:  # >10MB = likely valid
            log.info(f"Video already exists: {size / 1024 / 1024:.0f} MB")
            return True

    video_url = os.environ.get("VIDEO_URL", "")
    if not video_url:
        log.error("No VIDEO_URL set and no local video file!")
        return False

    log.info(f"Downloading video from: {video_url[:80]}...")
    try:
        result = subprocess.run(
            [
                "curl", "-L", "-o", VIDEO_PATH,
                "-H", "User-Agent: Mozilla/5.0",
                "--retry", "3",
                "--retry-delay", "5",
                "--max-time", "1800",  # 30 min max
                "--progress-bar",
                video_url,
            ],
            timeout=2000,
        )
        if result.returncode != 0:
            log.error(f"Download failed with code {result.returncode}")
            return False

        size = os.path.getsize(VIDEO_PATH)
        log.info(f"Download complete: {size / 1024 / 1024:.0f} MB")
        return size > 10_000_000
    except Exception as e:
        log.error(f"Download error: {e}")
        return False


def prepare_music():
    """Create a concat list for all music files in the music directory."""
    music_files = sorted(
        [f for f in os.listdir(MUSIC_DIR) if f.endswith((".m4a", ".mp3", ".aac", ".ogg"))],
    )
    if not music_files:
        log.warning("No music files found!")
        return None

    # Write concat list
    with open(MUSIC_CONCAT, "w") as f:
        for mf in music_files:
            path = os.path.join(MUSIC_DIR, mf)
            f.write(f"file '{path}'\n")

    log.info(f"Music playlist: {', '.join(music_files)}")
    return MUSIC_CONCAT


def build_ffmpeg_cmd(rtmp_url: str, music_concat: str | None) -> list:
    """Build the FFmpeg command for video + music → RTMP."""

    # Filter: speed up, 1:1 square crop (720x720), saturate colors
    # Lightweight pipeline to avoid OOM on Railway
    safe_title = STREAM_TITLE.replace("'", "'\\''").replace(":", "\\:")
    out_size = os.environ.get("OUTPUT_SIZE", "720")  # square
    vfilter = (
        f"[0:v]setpts=PTS/{VIDEO_SPEED},"
        # Scale down early to save RAM, then crop to 1:1 square center
        f"scale={out_size}:-2:force_original_aspect_ratio=decrease,"
        f"crop={out_size}:{out_size},"
        # Color saturation
        f"eq=saturation={SATURATION},"
        # Title text at top
        f"drawtext=text='{safe_title}':"
        f"fontsize=22:fontcolor=white:borderw=2:bordercolor=black@0.8:"
        f"x=(w-text_w)/2:y=10:"
        f"font=DejaVu Sans[v]"
    )

    # Audio: speed up video audio + mix with music
    if music_concat:
        afilter = (
            f"[0:a]atempo={VIDEO_SPEED},volume={VIDEO_VOLUME}[va];"
            f"[1:a]volume={MUSIC_VOLUME}[ma];"
            f"[va][ma]amix=inputs=2:duration=first:dropout_transition=3[a]"
        )
        inputs = [
            "-stream_loop", "-1", "-i", VIDEO_PATH,
            "-stream_loop", "-1", "-safe", "0", "-f", "concat", "-i", music_concat,
        ]
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        afilter = f"[0:a]atempo={VIDEO_SPEED},volume={VIDEO_VOLUME}[a]"
        inputs = ["-stream_loop", "-1", "-i", VIDEO_PATH]
        maps = ["-map", "[v]", "-map", "[a]"]

    full_filter = f"{vfilter};{afilter}"

    cmd = [
        "ffmpeg", "-y",
        "-loglevel", "warning",
        "-re",  # Read at realtime speed — critical to avoid OOM buffering
        *inputs,
        "-filter_complex", full_filter,
        *maps,
        # Video encoding — ultrafast to minimize CPU/RAM
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-b:v", VIDEO_BITRATE,
        "-maxrate", f"{int(VIDEO_BITRATE.replace('k', '')) + 500}k" if "k" in VIDEO_BITRATE else VIDEO_BITRATE,
        "-bufsize", "3000k",
        "-g", str(OUTPUT_FPS * 2),
        "-r", str(OUTPUT_FPS),
        "-threads", "2",
        # Audio encoding
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        # Output
        "-f", "flv",
        "-flvflags", "no_duration_filesize",
        rtmp_url,
    ]

    return cmd


def start_ffmpeg(rtmp_url: str, music_concat: str | None) -> subprocess.Popen | None:
    """Start the FFmpeg streaming process."""
    cmd = build_ffmpeg_cmd(rtmp_url, music_concat)
    log.info(f"FFmpeg command (first 15 args): {' '.join(cmd[:15])}...")

    stderr_path = "/tmp/ffmpeg_stderr.log"
    stderr_file = open(stderr_path, "w")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=stderr_file,
    )

    time.sleep(5)
    if proc.poll() is not None:
        stderr_file.close()
        with open(stderr_path) as f:
            err = f.read()
        log.error(f"FFmpeg crashed immediately!\n{err[-2000:]}")
        return None

    log.info("FFmpeg started successfully ✓")
    return proc


def main():
    log.info("=" * 50)
    log.info("VIDEO STREAM — TikTok Live")
    log.info("=" * 50)

    # Step 1: Download video
    if not download_video():
        log.error("Cannot start without video. Exiting.")
        sys.exit(1)

    # Step 2: Prepare music playlist
    music_concat = prepare_music()

    # Step 3: Main loop with auto-restart
    restart_count = 0
    max_restarts = 50

    while running and restart_count < max_restarts:
        restart_count += 1
        log.info(f"\n{'='*40} Stream attempt #{restart_count} {'='*40}")

        # Create TikTok stream
        stream = create_stream(title=STREAM_TITLE)
        if not stream:
            log.error("Failed to create TikTok stream. Retrying in 30s...")
            time.sleep(30)
            continue

        log.info(f"RTMP URL: {stream['rtmp_url'][:60]}...")
        log.info(f"Share URL: {stream.get('share_url', 'N/A')}")

        # Start FFmpeg
        ffmpeg_proc = start_ffmpeg(stream["rtmp_url"], music_concat)
        if not ffmpeg_proc:
            log.error("FFmpeg failed to start. Retrying in 15s...")
            time.sleep(15)
            continue

        # Monitor FFmpeg
        start_time = time.time()
        while running:
            ret = ffmpeg_proc.poll()
            if ret is not None:
                elapsed = time.time() - start_time
                log.warning(f"FFmpeg exited (code={ret}) after {elapsed:.0f}s")
                # Read stderr
                try:
                    with open("/tmp/ffmpeg_stderr.log") as f:
                        err = f.read()
                    for line in err[-1000:].split("\n"):
                        if line.strip():
                            log.warning(f"  ffmpeg: {line.strip()}")
                except:
                    pass
                break
            time.sleep(10)

        # Cleanup
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            ffmpeg_proc.terminate()
            try:
                ffmpeg_proc.wait(timeout=10)
            except:
                ffmpeg_proc.kill()

        if running:
            wait = min(15 + restart_count * 5, 120)
            log.info(f"Restarting in {wait}s...")
            time.sleep(wait)

    # End stream on shutdown
    try:
        end_stream()
    except:
        pass
    log.info("Shutdown complete.")


if __name__ == "__main__":
    main()
