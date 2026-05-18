"""Arena Renderer — Renders the battle arena to raw RGB frames using PIL."""
import math
import random
import time
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from game_engine import BattleArena, Avatar, Effect, ARENA_W, ARENA_H, ARENA_TOP, ARENA_BOTTOM

WIDTH = 720
HEIGHT = 1280

# ── Colours ──
BG_COLOR = (10, 8, 25)
TITLE_BG = (15, 12, 40, 200)
LEADERBOARD_BG = (10, 8, 30, 180)
CHAT_BG = (10, 8, 30, 160)
HP_GREEN = (50, 255, 80)
HP_YELLOW = (255, 220, 50)
HP_RED = (255, 50, 50)
GOLD = (255, 215, 0)
WHITE = (255, 255, 255)
GRAY = (150, 150, 160)
CROWN_COLOR = (255, 215, 0)

# ── Stars (pre-generated) ──
STARS = [(random.randint(0, WIDTH), random.randint(0, HEIGHT),
          random.randint(1, 3), random.randint(100, 255)) for _ in range(120)]


def _load_fonts():
    """Load fonts with fallback."""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    fonts = {}
    base = None
    for p in paths:
        try:
            base = p
            fonts["title"] = ImageFont.truetype(p, 36)
            fonts["subtitle"] = ImageFont.truetype(p, 20)
            fonts["name"] = ImageFont.truetype(p, 14)
            fonts["hp"] = ImageFont.truetype(p, 12)
            fonts["dmg"] = ImageFont.truetype(p, 22)
            fonts["lb_header"] = ImageFont.truetype(p, 18)
            fonts["lb_row"] = ImageFont.truetype(p, 14)
            fonts["chat"] = ImageFont.truetype(p, 13)
            fonts["cta"] = ImageFont.truetype(p, 16)
            fonts["level"] = ImageFont.truetype(p, 11)
            fonts["big_dmg"] = ImageFont.truetype(p, 30)
            fonts["initial"] = ImageFont.truetype(p, 20)
            return fonts
        except (OSError, IOError):
            continue
    # Fallback to default
    df = ImageFont.load_default()
    for k in ["title", "subtitle", "name", "hp", "dmg", "lb_header",
              "lb_row", "chat", "cta", "level", "big_dmg", "initial"]:
        fonts[k] = df
    return fonts


FONTS = _load_fonts()


class ArenaRenderer:
    """Renders a BattleArena to raw RGB bytes."""

    def __init__(self):
        self._bg = self._make_background()
        self._frame_count = 0

    # ── Background ──

    @staticmethod
    def _make_background() -> Image.Image:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)
        # Gradient
        for y in range(HEIGHT):
            r = int(10 + 8 * math.sin(y / 200))
            g = int(8 + 6 * math.sin(y / 250 + 1))
            b = int(25 + 15 * math.sin(y / 180 + 2))
            draw.line([(0, y), (WIDTH, y)], fill=(max(0, r), max(0, g), max(0, min(255, b))))
        # Stars
        for sx, sy, sr, sb in STARS:
            c = (sb, sb, min(255, sb + 40))
            if sr == 1:
                draw.point((sx, sy), fill=c)
            else:
                draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=c)
        # Subtle grid
        for gx in range(0, WIDTH, 60):
            draw.line([(gx, ARENA_TOP), (gx, ARENA_BOTTOM)], fill=(25, 20, 50), width=1)
        for gy in range(ARENA_TOP, ARENA_BOTTOM, 60):
            draw.line([(0, gy), (WIDTH, gy)], fill=(25, 20, 50), width=1)
        return img

    # ── Main Render ──

    def render(self, arena: BattleArena) -> bytes:
        self._frame_count += 1
        img = self._bg.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        self._draw_effects_bg(draw, arena)
        self._draw_avatars(draw, arena, img)
        self._draw_effects_fg(draw, arena)
        self._draw_title(draw, arena)
        self._draw_leaderboard(draw, arena)
        self._draw_chat(draw, arena)
        self._draw_cta(draw, arena)
        self._draw_gifts(draw, arena)

        return img.tobytes()

    # ── Title Bar ──

    def _draw_title(self, draw: ImageDraw.Draw, arena: BattleArena):
        draw.rectangle([0, 0, WIDTH, 90], fill=(12, 10, 35, 220))
        # Title
        draw.text((WIDTH // 2, 20), "⚔  BATTLE ARENA LIVE", fill=GOLD,
                  font=FONTS["title"], anchor="mt")
        # Stats
        viewers = f"👁 {arena.viewer_count}"
        gifts_t = f"🎁 {arena.total_gifts}"
        likes_t = f"❤ {arena.total_likes}"
        fighters = f"⚔ {sum(1 for a in arena.avatars.values() if a.alive)}"
        stats = f"{viewers}   {gifts_t}   {likes_t}   {fighters}"
        draw.text((WIDTH // 2, 65), stats, fill=GRAY, font=FONTS["subtitle"], anchor="mt")

    # ── Avatars ──

    def _draw_avatars(self, draw: ImageDraw.Draw, arena: BattleArena, img: Image.Image):
        now = time.time()
        champion = arena.champion

        for avatar in sorted(arena.avatars.values(), key=lambda a: a.y):
            if not avatar.alive:
                continue

            x, y = int(avatar.x), int(avatar.y)
            r = 22  # avatar radius

            # Shield glow
            if avatar.shield:
                pulse = int(6 * math.sin(now * 4))
                sr = r + 10 + pulse
                draw.ellipse([x - sr, y - sr, x + sr, y + sr],
                             outline=(80, 160, 255, 120), width=3)

            # Attack boost glow
            if avatar.attack_boost > 1.0:
                pulse = int(4 * math.sin(now * 5))
                ar = r + 6 + pulse
                intensity = min(255, int(80 * avatar.attack_boost))
                draw.ellipse([x - ar, y - ar, x + ar, y + ar],
                             outline=(255, 80, 50, intensity), width=2)

            # Avatar body — filled circle with border
            draw.ellipse([x - r, y - r, x + r, y + r], fill=avatar.color,
                         outline=(255, 255, 255, 200), width=2)

            # Initial letter inside
            initial = avatar.display_name[0].upper() if avatar.display_name else "?"
            draw.text((x, y), initial, fill=WHITE, font=FONTS["initial"], anchor="mm")

            # Level badge (top-left)
            lx, ly = x - r - 2, y - r - 2
            draw.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=(40, 40, 80, 220),
                         outline=avatar.color, width=1)
            draw.text((lx, ly), str(avatar.level), fill=WHITE, font=FONTS["level"], anchor="mm")

            # HP bar
            hp_w = 44
            hp_h = 6
            hp_x = x - hp_w // 2
            hp_y = y - r - 14
            hp_pct = max(0, avatar.hp / avatar.max_hp)
            if hp_pct > 0.6:
                hp_col = HP_GREEN
            elif hp_pct > 0.3:
                hp_col = HP_YELLOW
            else:
                hp_col = HP_RED
            draw.rectangle([hp_x, hp_y, hp_x + hp_w, hp_y + hp_h],
                           fill=(40, 40, 40, 180), outline=(80, 80, 80, 100))
            if hp_pct > 0:
                draw.rectangle([hp_x + 1, hp_y + 1, hp_x + 1 + int((hp_w - 2) * hp_pct), hp_y + hp_h - 1],
                               fill=hp_col)

            # Name below
            name_display = avatar.display_name[:12]
            draw.text((x, y + r + 6), name_display, fill=WHITE, font=FONTS["name"], anchor="mt")

            # Power number
            power_str = f"{avatar.power}"
            draw.text((x, y + r + 20), power_str, fill=GRAY, font=FONTS["hp"], anchor="mt")

            # Crown for champion
            if avatar.name == champion:
                self._draw_crown(draw, x, y - r - 22)

            # Combo indicator
            if avatar.combo >= 3:
                combo_text = f"x{avatar.combo}"
                draw.text((x + r + 5, y - r), combo_text, fill=(255, 150, 0),
                          font=FONTS["dmg"], anchor="lt")

    @staticmethod
    def _draw_crown(draw: ImageDraw.Draw, x: int, y: int):
        """Draw a simple crown icon."""
        pts = [
            (x - 10, y + 5), (x - 10, y - 2), (x - 6, y + 2),
            (x, y - 6), (x + 6, y + 2), (x + 10, y - 2), (x + 10, y + 5),
        ]
        draw.polygon(pts, fill=CROWN_COLOR, outline=(200, 170, 0))

    # ── Effects ──

    def _draw_effects_bg(self, draw: ImageDraw.Draw, arena: BattleArena):
        """Draw background effects (spawn rings, etc.)."""
        for e in arena.effects:
            if e.type == "spawn":
                p = e.progress
                radius = int(40 * p)
                alpha = int(200 * (1 - p))
                col = (*e.color, alpha)
                x, y = int(e.x), int(e.y)
                draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                             outline=col, width=3)

    def _draw_effects_fg(self, draw: ImageDraw.Draw, arena: BattleArena):
        """Draw foreground effects (damage numbers, hit sparks, death particles)."""
        for e in arena.effects:
            p = e.progress
            alpha = int(255 * (1 - p))
            x, y = int(e.x), int(e.y)

            if e.type == "damage":
                offset_y = int(-30 * p)
                col = (255, 60, 60, alpha)
                draw.text((x, y + offset_y), f"-{e.value}", fill=col,
                          font=FONTS["dmg"] if e.value < 30 else FONTS["big_dmg"], anchor="mm")

            elif e.type == "heal":
                offset_y = int(-30 * p)
                col = (60, 255, 100, alpha)
                draw.text((x, y + offset_y), f"+{e.value}", fill=col,
                          font=FONTS["dmg"], anchor="mm")

            elif e.type == "shield_hit":
                offset_y = int(-20 * p)
                col = (100, 180, 255, alpha)
                draw.text((x, y + offset_y), e.text or "BLOCK", fill=col,
                          font=FONTS["dmg"], anchor="mm")

            elif e.type == "hit":
                for px, py in e.particles:
                    sx = x + int(px * p * 8)
                    sy = y + int(py * p * 8)
                    sr = max(1, int(3 * (1 - p)))
                    col = (*e.color[:3], alpha)
                    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=col)

            elif e.type == "death":
                for px, py in e.particles:
                    sx = x + int(px * p * 20)
                    sy = y + int(py * p * 20)
                    sr = max(1, int(5 * (1 - p)))
                    col = (*e.color[:3], alpha)
                    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=col)
                # "ELIMINATED" text
                if p < 0.7:
                    ta = int(255 * (1 - p / 0.7))
                    draw.text((x, y - 15), "ELIMINATED", fill=(255, 50, 50, ta),
                              font=FONTS["subtitle"], anchor="mm")

    # ── Leaderboard ──

    def _draw_leaderboard(self, draw: ImageDraw.Draw, arena: BattleArena):
        lb = arena.get_leaderboard()
        if not lb:
            return

        panel_w = 185
        panel_x = WIDTH - panel_w - 10
        panel_y = 100
        row_h = 28
        panel_h = 36 + len(lb) * row_h

        draw.rounded_rectangle(
            [panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
            radius=10, fill=(10, 8, 30, 170), outline=(60, 50, 100, 150), width=1)

        draw.text((panel_x + panel_w // 2, panel_y + 10), "🏆 LEADERBOARD",
                  fill=GOLD, font=FONTS["lb_header"], anchor="mt")

        for i, a in enumerate(lb):
            ry = panel_y + 34 + i * row_h
            # Rank
            rank_col = GOLD if i == 0 else ((200, 200, 200) if i == 1 else ((180, 120, 60) if i == 2 else GRAY))
            draw.text((panel_x + 12, ry), f"#{i + 1}", fill=rank_col, font=FONTS["lb_row"], anchor="lt")
            # Color dot
            draw.ellipse([panel_x + 34, ry + 2, panel_x + 44, ry + 12], fill=a.color)
            # Name (truncated)
            name = a.display_name[:8]
            draw.text((panel_x + 48, ry), name, fill=WHITE, font=FONTS["lb_row"], anchor="lt")
            # Kills
            draw.text((panel_x + panel_w - 12, ry), f"{a.kills}K", fill=(255, 100, 100),
                      font=FONTS["lb_row"], anchor="rt")

    # ── Chat Messages ──

    def _draw_chat(self, draw: ImageDraw.Draw, arena: BattleArena):
        msgs = arena.chat_messages[-5:]
        if not msgs:
            return

        now = time.time()
        panel_x = 10
        panel_y = ARENA_BOTTOM - 10 - len(msgs) * 22
        panel_w = 280
        panel_h = len(msgs) * 22 + 10

        draw.rounded_rectangle(
            [panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
            radius=8, fill=(10, 8, 30, 140))

        for i, msg in enumerate(msgs):
            age = now - msg["time"]
            alpha = max(60, int(255 * max(0, 1 - age / 30)))
            ry = panel_y + 6 + i * 22
            name = msg["name"][:10]
            text = msg["text"][:20]
            draw.text((panel_x + 8, ry), f"{name}: ", fill=(100, 180, 255, alpha), font=FONTS["chat"], anchor="lt")
            nw = FONTS["chat"].getlength(f"{name}: ")
            draw.text((panel_x + 8 + int(nw), ry), text, fill=(220, 220, 230, alpha), font=FONTS["chat"], anchor="lt")

    # ── Gift Log ──

    def _draw_gifts(self, draw: ImageDraw.Draw, arena: BattleArena):
        recent = [g for g in arena.gift_log if time.time() - g["time"] < 15][-4:]
        if not recent:
            return

        panel_x = 10
        panel_y = 100

        for i, g in enumerate(recent):
            age = time.time() - g["time"]
            alpha = max(80, int(255 * max(0, 1 - age / 15)))
            ry = panel_y + i * 26
            text = f"🎁 {g['name'][:10]} → {g['gift']}"
            draw.text((panel_x, ry), text, fill=(255, 200, 80, alpha), font=FONTS["name"], anchor="lt")

    # ── Call to Action ──

    def _draw_cta(self, draw: ImageDraw.Draw, arena: BattleArena):
        draw.rectangle([0, ARENA_BOTTOM, WIDTH, HEIGHT], fill=(12, 10, 35, 220))
        # Animate between two messages
        t = self._frame_count // 90  # switch every 6 seconds at 15fps
        if t % 2 == 0:
            text = "💬 Comment to JOIN the battle!"
        else:
            text = "🎁 Send gifts = POWER UP your fighter!"
        draw.text((WIDTH // 2, ARENA_BOTTOM + 35), text, fill=WHITE,
                  font=FONTS["cta"], anchor="mm")
