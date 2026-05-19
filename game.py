"""
Snake AI Game – TikTok Live Stream version
Matches the exact visual style from the reference video:
- Bright green textured snake with crosshatch pattern
- Orange pumpkin-like apples
- Dark space/nebula background with stars
- Brown wooden frame border
- Snake head with face
- "1k taps 10 apples" / "[+] X apples" notifications
- "Help me apple goal XXXX/2000" at bottom
"""

import random, time, math, collections
from PIL import Image, ImageDraw, ImageFont

# ── Dimensions ──────────────────────────────────────────
WIDTH, HEIGHT = 720, 1280
CELL = 20  # cell size in pixels

# Game area - centered with wooden frame
FRAME_THICKNESS = 8
GAME_LEFT = 20
GAME_TOP = 340
GAME_RIGHT = WIDTH - 20
GAME_BOTTOM = 920
GAME_W = GAME_RIGHT - GAME_LEFT
GAME_H = GAME_BOTTOM - GAME_TOP

# Grid dimensions (cells inside the game area)
COLS = (GAME_W - 2 * FRAME_THICKNESS) // CELL
ROWS = (GAME_H - 2 * FRAME_THICKNESS) // CELL

# Inner game area (inside frame)
INNER_LEFT = GAME_LEFT + FRAME_THICKNESS
INNER_TOP = GAME_TOP + FRAME_THICKNESS
INNER_RIGHT = INNER_LEFT + COLS * CELL
INNER_BOTTOM = INNER_TOP + ROWS * CELL

# ── Colors (SATURATED) ──────────────────────────────────
BLACK = (0, 0, 0)
BG_DARK = (2, 5, 18)  # deeper dark blue-black
NEBULA_1 = (15, 35, 65)  # richer blue nebula
NEBULA_2 = (10, 28, 50)
GREEN_BRIGHT = (0, 255, 30)  # vivid neon green snake
GREEN_DARK = (0, 190, 10)  # snake pattern dark
GREEN_HEAD = (30, 255, 50)  # slightly brighter head
ORANGE = (255, 140, 0)  # vivid saturated orange apple
ORANGE_DARK = (220, 100, 0)
BROWN_FRAME = (140, 80, 25)  # richer wooden frame
BROWN_LIGHT = (190, 120, 50)
BROWN_DARK = (90, 50, 15)
WHITE = (255, 255, 255)
GREEN_TEXT = (50, 255, 50)  # brighter green text
STAR_COLOR = (120, 255, 180)  # brighter greenish stars
YELLOW_GLOW = (255, 255, 60)  # for title glow
TITLE_COLOR = (255, 220, 50)  # golden title

# ── Font ────────────────────────────────────────────────
def _load_font(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/System/Library/Fonts/Helvetica.ttc"]:
        try:
            return ImageFont.truetype(p, size)
        except:
            continue
    return ImageFont.load_default()

FONT_LARGE = _load_font(22)
FONT_MEDIUM = _load_font(18)
FONT_SMALL = _load_font(14)
FONT_TINY = _load_font(12)
FONT_GOAL = _load_font(28)
FONT_TITLE = _load_font(32)
FONT_SUBTITLE = _load_font(16)

DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]  # right, down, left, up


class SnakeGame:
    def __init__(self):
        self.reset()
        self.viewer_count = 0
        self.apple_goal = 2000
        self.total_apples = 0
        self.high_score = 0
        self.notifications = []  # (text, expire_time)
        self.stars = [(random.randint(INNER_LEFT, INNER_RIGHT),
                       random.randint(INNER_TOP, INNER_BOTTOM),
                       random.random() * 2 + 0.5) for _ in range(40)]
        # Pre-generate nebula background
        self._bg_cache = None
        self._generate_background()

    def _generate_background(self):
        """Generate space nebula background with frame — cached for performance."""
        bg = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
        draw = ImageDraw.Draw(bg)

        # Subtle nebula clouds in game area
        for _ in range(6):
            cx = random.randint(INNER_LEFT, INNER_RIGHT)
            cy = random.randint(INNER_TOP, INNER_BOTTOM)
            r = random.randint(60, 140)
            for ring in range(r, 0, -4):
                f = ring / r
                c = tuple(int(NEBULA_1[i] * f + BG_DARK[i] * (1 - f)) for i in range(3))
                draw.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], fill=c)

        # Wooden frame (drawn once, cached)
        draw.rectangle([GAME_LEFT, GAME_TOP, GAME_RIGHT, GAME_BOTTOM],
                       outline=BROWN_FRAME, width=FRAME_THICKNESS)
        draw.line([(GAME_LEFT, GAME_TOP), (GAME_RIGHT, GAME_TOP)], fill=BROWN_LIGHT, width=2)
        draw.line([(GAME_LEFT, GAME_TOP), (GAME_LEFT, GAME_BOTTOM)], fill=BROWN_LIGHT, width=2)
        draw.line([(GAME_RIGHT, GAME_TOP), (GAME_RIGHT, GAME_BOTTOM)], fill=BROWN_DARK, width=2)
        draw.line([(GAME_LEFT, GAME_BOTTOM), (GAME_RIGHT, GAME_BOTTOM)], fill=BROWN_DARK, width=2)

        # ── Stream Title ──
        title_text = "🐍 Snake AI Live"
        subtitle_text = "Send Gifts → More Apples!"
        # Title background banner
        title_y = 40
        draw.rectangle([0, title_y - 10, WIDTH, title_y + 80], fill=(10, 10, 30))
        # Gradient-like accent line
        for i in range(4):
            draw.line([(0, title_y - 10 + i), (WIDTH, title_y - 10 + i)],
                      fill=(255, 200 - i * 20, 0))
            draw.line([(0, title_y + 80 - i), (WIDTH, title_y + 80 - i)],
                      fill=(255, 200 - i * 20, 0))
        # Title text with shadow
        draw.text((WIDTH // 2 - 130 + 2, title_y + 2), title_text,
                  fill=(0, 0, 0), font=FONT_TITLE)
        draw.text((WIDTH // 2 - 130, title_y), title_text,
                  fill=TITLE_COLOR, font=FONT_TITLE)
        # Subtitle
        draw.text((WIDTH // 2 - 110, title_y + 42), subtitle_text,
                  fill=GREEN_TEXT, font=FONT_SUBTITLE)

        # "1k taps  10 apples" static text
        draw.text((GAME_LEFT + 5, GAME_TOP - 50), "1k taps  10 apples",
                  fill=WHITE, font=FONT_MEDIUM)

        # Bottom HUD static parts
        hud_y = GAME_BOTTOM + 15
        apple_icon_x = GAME_LEFT + 15
        apple_icon_y = hud_y + 5
        r2 = 18
        draw.ellipse([apple_icon_x, apple_icon_y, apple_icon_x + r2 * 2, apple_icon_y + r2 * 2],
                     fill=ORANGE)
        draw.line([(apple_icon_x + r2, apple_icon_y), (apple_icon_x + r2, apple_icon_y - 5)],
                  fill=(0, 150, 0), width=2)
        draw.ellipse([apple_icon_x + r2 + 2, apple_icon_y - 6, apple_icon_x + r2 + 10, apple_icon_y],
                     fill=(0, 180, 0))
        draw.text((apple_icon_x + r2 * 2 + 10, hud_y + 5), "Help me apple goal",
                  fill=WHITE, font=FONT_MEDIUM)

        # Gift panel labels (static)
        gift_y = hud_y + 50
        gifts = [
            ("\u2764\ufe0f", "5 Apples"), ("\ud83c\udf39", "50 Apples"),
            ("\ud83d\udc90", "100 Apples"), ("\ud83c\udf80", "150 Apples"),
            ("\ud83c\udf19", "499 Apples"), ("\ud83c\udf39", "1000 Apples"),
            ("\ud83c\udf81", "1500 Apples"),
        ]
        for i, (emoji, label) in enumerate(gifts):
            gy = gift_y + i * 28
            if gy < HEIGHT - 40:
                draw.text((WIDTH - 155, gy), label, fill=WHITE, font=FONT_TINY)

        self._bg_cache = bg

    def reset(self):
        mid_x, mid_y = COLS // 2, ROWS // 2
        self.snake = collections.deque([(mid_x, mid_y), (mid_x - 1, mid_y), (mid_x - 2, mid_y)])
        self.direction = 0  # right
        self.apples = []
        self._spawn_apple()
        self._spawn_apple()
        self._spawn_apple()
        self.score = 0
        self.alive = True
        self.frame_count = 0

    def _spawn_apple(self):
        occupied = set(self.snake) | set(self.apples)
        attempts = 0
        while attempts < 100:
            x = random.randint(0, COLS - 1)
            y = random.randint(0, ROWS - 1)
            if (x, y) not in occupied:
                self.apples.append((x, y))
                return
            attempts += 1

    def add_message(self, username: str, text: str):
        """Display a chat message on screen."""
        self.notifications.append((f"{username}: {text}", time.time() + 5))

    def add_apples(self, username: str, count: int):
        """Called when a viewer sends a gift"""
        added = 0
        for _ in range(min(count, 200)):
            self._spawn_apple()
            added += 1
        self.total_apples += added
        self.notifications.append((f"[+] {added} apples", time.time() + 4))
        self.notifications.append((f"from {username}", time.time() + 4))

    def add_tap_apples(self, count: int = 10):
        """Simulate tap interaction"""
        for _ in range(count):
            self._spawn_apple()
        self.total_apples += count
        self.notifications.append((f"[+] {count} apples", time.time() + 3))

    def _bfs_direction(self):
        """BFS pathfinding to nearest apple"""
        head = self.snake[0]
        snake_set = set(self.snake)

        if not self.apples:
            # Wander if no apples
            for d in range(4):
                nx = (head[0] + DIRS[d][0]) % COLS
                ny = (head[1] + DIRS[d][1]) % ROWS
                if (nx, ny) not in snake_set:
                    return d
            return self.direction

        queue = collections.deque([(head, None)])
        visited = {head}
        apple_set = set(self.apples)

        while queue:
            pos, first_dir = queue.popleft()
            for d in range(4):
                nx = (pos[0] + DIRS[d][0]) % COLS
                ny = (pos[1] + DIRS[d][1]) % ROWS
                npos = (nx, ny)
                if npos in visited or npos in snake_set:
                    continue
                visited.add(npos)
                fd = d if first_dir is None else first_dir
                if npos in apple_set:
                    return fd
                queue.append((npos, fd))

        # Fallback: any safe move
        for d in range(4):
            nx = (head[0] + DIRS[d][0]) % COLS
            ny = (head[1] + DIRS[d][1]) % ROWS
            if (nx, ny) not in snake_set:
                return d
        return self.direction

    def step(self):
        self.frame_count += 1
        if not self.alive:
            if self.frame_count % 30 == 0:
                self.reset()
            return

        # AI decides direction
        self.direction = self._bfs_direction()

        # Move head
        head = self.snake[0]
        dx, dy = DIRS[self.direction]
        new_head = ((head[0] + dx) % COLS, (head[1] + dy) % ROWS)

        # Check self-collision
        if new_head in set(self.snake):
            self.alive = False
            if self.score > self.high_score:
                self.high_score = self.score
            return

        self.snake.appendleft(new_head)

        # Check apple
        if new_head in self.apples:
            self.apples.remove(new_head)
            self.score += 1
            # Keep minimum apples
            while len(self.apples) < 2:
                self._spawn_apple()
        else:
            self.snake.pop()

        # Periodically spawn apples to keep things interesting
        if self.frame_count % 100 == 0 and len(self.apples) < 3:
            self._spawn_apple()

        # Simulate occasional tap apples (for visual interest when no viewers)
        if self.frame_count % 300 == 0 and self.viewer_count == 0:
            self.add_tap_apples(3)

    def render(self) -> bytes:
        """Render the game frame as raw RGB bytes — optimised, only dynamic parts drawn."""
        img = self._bg_cache.copy()
        draw = ImageDraw.Draw(img)

        # ── Clear inner game area (redraw over cached bg) ──
        draw.rectangle([INNER_LEFT, INNER_TOP, INNER_RIGHT, INNER_BOTTOM], fill=BG_DARK)

        # ── Twinkling stars ──
        t = time.time()
        for sx, sy, speed in self.stars:
            b = int(80 + 60 * math.sin(t * speed))
            draw.point((sx, sy), fill=(b // 3, b, b // 2))

        # ── Apples (vivid orange pumpkins with glow) ──
        for ax, ay in self.apples:
            px = INNER_LEFT + ax * CELL + CELL // 2
            py = INNER_TOP + ay * CELL + CELL // 2
            r = CELL // 2 - 1
            # Outer glow
            draw.ellipse([px - r - 2, py - r - 1, px + r + 2, py + r + 3], fill=ORANGE_DARK)
            # Main apple
            draw.ellipse([px - r, py - r + 1, px + r, py + r + 1], fill=ORANGE)
            # Highlight
            draw.ellipse([px - r + 2, py - r + 2, px - 1, py - 1], fill=(255, 180, 40))
            # Stem
            draw.line([(px, py - r), (px, py - r - 4)], fill=(0, 180, 0), width=2)
            # Leaf
            draw.ellipse([px + 1, py - r - 4, px + 6, py - r], fill=(0, 200, 0))

        # ── Snake body (vivid, saturated) ──
        snake_list = list(self.snake)
        for i, (sx, sy) in enumerate(snake_list):
            px = INNER_LEFT + sx * CELL
            py = INNER_TOP + sy * CELL
            if i == 0:
                # Head with glow effect
                draw.rectangle([px - 1, py - 1, px + CELL, py + CELL], fill=(0, 200, 20))
                draw.rectangle([px, py, px + CELL - 1, py + CELL - 1], fill=GREEN_HEAD)
                # Eyes (bigger, more visible)
                ey = py + CELL // 3
                draw.ellipse([px + 2, ey - 3, px + 8, ey + 3], fill=WHITE)
                draw.ellipse([px + CELL - 9, ey - 3, px + CELL - 3, ey + 3], fill=WHITE)
                draw.ellipse([px + 4, ey - 1, px + 7, ey + 2], fill=BLACK)
                draw.ellipse([px + CELL - 8, ey - 1, px + CELL - 5, ey + 2], fill=BLACK)
                # Tongue (sometimes visible)
                if self.frame_count % 20 < 10:
                    dx, dy = DIRS[self.direction]
                    tx = px + CELL // 2 + dx * 6
                    ty = py + CELL // 2 + dy * 6
                    draw.line([(px + CELL // 2, py + CELL // 2), (tx, ty)],
                              fill=(255, 50, 50), width=1)
            else:
                # Body segments with crosshatch pattern
                draw.rectangle([px, py, px + CELL - 1, py + CELL - 1], fill=GREEN_BRIGHT)
                if i % 2 == 0:
                    draw.rectangle([px + 3, py + 3, px + CELL - 4, py + CELL - 4], fill=GREEN_DARK)
                else:
                    draw.line([(px, py), (px + CELL - 1, py + CELL - 1)], fill=GREEN_DARK, width=1)
                    draw.line([(px + CELL - 1, py), (px, py + CELL - 1)], fill=GREEN_DARK, width=1)
                # Subtle border between segments
                draw.rectangle([px, py, px + CELL - 1, py + CELL - 1], outline=(0, 140, 0))

        # ── Dynamic title area info ──
        # Score display
        score_text = f"Score: {self.score}"
        draw.text((20, 140), score_text, fill=WHITE, font=FONT_MEDIUM)
        # High score
        if self.high_score > 0:
            hs_text = f"Best: {self.high_score}"
            draw.text((20, 165), hs_text, fill=YELLOW_GLOW, font=FONT_SMALL)
        # Snake length
        length_text = f"Length: {len(self.snake)}"
        draw.text((WIDTH - 140, 140), length_text, fill=WHITE, font=FONT_MEDIUM)
        # Viewer count (if available)
        if self.viewer_count > 0:
            viewer_text = f"👀 {self.viewer_count}"
            draw.text((WIDTH - 140, 165), viewer_text, fill=(255, 100, 100), font=FONT_SMALL)

        # ── Notifications "[+] X apples" ──
        now = time.time()
        self.notifications = [(t2, e) for t2, e in self.notifications if e > now]
        y_off = GAME_TOP - 28
        for txt, _ in self.notifications[:3]:
            draw.text((GAME_LEFT + 5, y_off), txt, fill=GREEN_TEXT, font=FONT_MEDIUM)
            y_off += 22

        # ── Apple count badge ──
        if self.apples:
            ax, ay = self.apples[0]
            draw.text((INNER_LEFT + ax * CELL + CELL + 3, INNER_TOP + ay * CELL),
                      str(len(self.apples)), fill=GREEN_TEXT, font=FONT_MEDIUM)

        # ── Dynamic counter ──
        hud_y = GAME_BOTTOM + 15
        counter_text = f"{self.total_apples}/{self.apple_goal}"
        draw.text((GAME_LEFT + 15 + 36 + 10 + 280, hud_y), counter_text,
                  fill=WHITE, font=FONT_GOAL)

        # ── Death overlay ──
        if not self.alive:
            cx = (INNER_LEFT + INNER_RIGHT) // 2
            cy = (INNER_TOP + INNER_BOTTOM) // 2
            draw.rectangle([cx - 120, cy - 30, cx + 120, cy + 30], fill=BLACK, outline=GREEN_BRIGHT)
            draw.text((cx - 80, cy - 15), "Restarting...", fill=GREEN_TEXT, font=FONT_LARGE)

        return img.tobytes()

    def get_size(self):
        return (WIDTH, HEIGHT)
