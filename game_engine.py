"""Battle Arena Game Engine — Interactive TikTok Live Game."""
import random
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Arena dimensions (720x1280 portrait TikTok)
ARENA_W = 720
ARENA_H = 1280
ARENA_TOP = 100      # Title area
ARENA_BOTTOM = 1200  # Above info bar

# Avatar settings
BASE_HP = 100
BASE_ATTACK = 12
BASE_DEFENSE = 3
BASE_SPEED = 1.8
ATTACK_RANGE = 55
ATTACK_COOLDOWN = 0.8
RESPAWN_TIME = 4.0
MAX_AVATARS = 30

AVATAR_COLORS = [
    (255, 60, 60),   (60, 130, 255),  (50, 220, 50),
    (255, 200, 0),   (255, 50, 200),  (0, 220, 200),
    (180, 90, 255),  (255, 140, 0),   (0, 200, 255),
    (255, 255, 80),  (80, 255, 150),  (255, 100, 120),
    (100, 255, 255), (200, 200, 60),  (255, 80, 160),
]

# Gift → coin value mapping
GIFT_COIN_MAP = {
    "Rose": 1, "rose": 1, "TikTok": 1, "Finger Heart": 5, "GG": 1,
    "Ice Cream Cone": 1, "Doughnut": 3, "Perfume": 20, "Bouquet": 50,
    "Love You": 25, "Garland": 69, "Sunglasses": 5, "Confetti": 1,
    "Hand Hearts": 100, "Butterfly": 100, "Family": 100,
    "Weighlifting": 100, "Hat and Mustache": 150, "Corgi": 99,
    "Cap": 99, "Hands Up": 499, "Donate": 499,
    "Gaming Keyboard": 499, "Train": 1000, "Elephant": 1000,
    "Gift Box": 1500, "Lion": 29999, "Universe": 34999, "Whale": 5000,
}


@dataclass
class Effect:
    """Visual effect."""
    type: str        # 'hit', 'death', 'damage', 'heal', 'spawn', 'shield_hit'
    x: float
    y: float
    value: int = 0
    text: str = ""
    color: Tuple[int, int, int] = (255, 255, 255)
    created: float = field(default_factory=time.time)
    duration: float = 1.0
    particles: List = field(default_factory=list)

    @property
    def age(self) -> float:
        return time.time() - self.created

    @property
    def alive(self) -> bool:
        return self.age < self.duration

    @property
    def progress(self) -> float:
        return min(1.0, self.age / self.duration)


@dataclass
class Avatar:
    """A viewer's battle avatar."""
    name: str
    display_name: str = ""
    hp: int = BASE_HP
    max_hp: int = BASE_HP
    attack: int = BASE_ATTACK
    defense: int = BASE_DEFENSE
    speed: float = BASE_SPEED
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    color: Tuple[int, int, int] = (255, 255, 255)
    kills: int = 0
    deaths: int = 0
    damage_dealt: int = 0
    last_attack: float = 0.0
    target: Optional[str] = None
    alive: bool = True
    death_time: float = 0.0
    attack_boost: float = 1.0
    attack_boost_end: float = 0.0
    shield: bool = False
    shield_end: float = 0.0
    level: int = 1
    xp: int = 0
    is_bot: bool = False
    join_time: float = field(default_factory=time.time)
    last_hit_time: float = 0.0
    combo: int = 0

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name

    @property
    def can_attack(self) -> bool:
        return self.alive and time.time() - self.last_attack >= ATTACK_COOLDOWN

    def distance_to(self, other: "Avatar") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    @property
    def power(self) -> int:
        return int(self.attack * self.attack_boost * (1 + self.level * 0.1))


class BattleArena:
    """Main game engine."""

    def __init__(self):
        self.avatars: Dict[str, Avatar] = {}
        self.effects: List[Effect] = []
        self.viewer_count = 0
        self.total_gifts = 0
        self.total_likes = 0
        self.champion: Optional[str] = None
        self.events_log: List[tuple] = []
        self.chat_messages: List[dict] = []
        self.gift_log: List[dict] = []
        self._tick = 0
        self._add_bots()

    def _add_bots(self):
        bot_names = [
            "Bot-Alpha", "Bot-Beta", "Bot-Gamma",
            "Bot-Delta", "Bot-Omega", "Bot-Sigma",
        ]
        for name in bot_names:
            self._spawn_avatar(name, is_bot=True)

    def _random_pos(self) -> Tuple[float, float]:
        x = random.uniform(50, ARENA_W - 50)
        y = random.uniform(ARENA_TOP + 40, ARENA_BOTTOM - 40)
        return x, y

    def _spawn_avatar(self, name: str, is_bot: bool = False, display_name: str = "") -> Avatar:
        color = AVATAR_COLORS[hash(name) % len(AVATAR_COLORS)]
        x, y = self._random_pos()
        avatar = Avatar(
            name=name,
            display_name=display_name or name,
            x=x, y=y,
            color=color,
            vx=random.uniform(-1, 1),
            vy=random.uniform(-1, 1),
            is_bot=is_bot,
        )
        self.avatars[name] = avatar
        self.effects.append(Effect(
            type="spawn", x=x, y=y, color=color, duration=1.5
        ))
        return avatar

    # ── Public API ──

    def add_viewer(self, name: str, display_name: str = "") -> Optional[Avatar]:
        if name in self.avatars:
            a = self.avatars[name]
            if not a.alive:
                a.alive = True
                a.hp = a.max_hp
                a.x, a.y = self._random_pos()
                self.effects.append(Effect(type="spawn", x=a.x, y=a.y, color=a.color, duration=1.2))
            return a

        if len(self.avatars) >= MAX_AVATARS:
            # Remove a bot to make room
            for n in list(self.avatars):
                if self.avatars[n].is_bot:
                    del self.avatars[n]
                    break
            else:
                return None

        avatar = self._spawn_avatar(name, display_name=display_name)
        self.events_log.append(("join", name, display_name or name))
        return avatar

    def gift_powerup(self, name: str, gift_name: str, coin_value: int, display_name: str = ""):
        self.total_gifts += 1
        self.gift_log.append({"name": display_name or name, "gift": gift_name, "coins": coin_value, "time": time.time()})
        if len(self.gift_log) > 20:
            self.gift_log = self.gift_log[-20:]

        if name not in self.avatars:
            self.add_viewer(name, display_name)
        avatar = self.avatars.get(name)
        if not avatar:
            return
        if not avatar.alive:
            avatar.alive = True
            avatar.hp = avatar.max_hp
            avatar.x, avatar.y = self._random_pos()

        now = time.time()
        if coin_value <= 5:
            heal = int(avatar.max_hp * 0.3)
            avatar.hp = min(avatar.max_hp, avatar.hp + heal)
            self.effects.append(Effect(type="heal", x=avatar.x, y=avatar.y - 35, value=heal, color=(0, 255, 100), duration=1.3))
        elif coin_value <= 50:
            avatar.hp = avatar.max_hp
            avatar.attack_boost = 1.6
            avatar.attack_boost_end = now + 15
            self.effects.append(Effect(type="heal", x=avatar.x, y=avatar.y - 35, value=avatar.max_hp, color=(0, 255, 255), duration=1.5))
        elif coin_value <= 500:
            avatar.level += 1
            avatar.max_hp += 25
            avatar.attack += 4
            avatar.hp = avatar.max_hp
            avatar.attack_boost = 2.0
            avatar.attack_boost_end = now + 20
            self.effects.append(Effect(type="spawn", x=avatar.x, y=avatar.y, color=(255, 215, 0), duration=2.0))
        else:
            avatar.level += 2
            avatar.max_hp += 60
            avatar.attack += 10
            avatar.hp = avatar.max_hp
            avatar.shield = True
            avatar.shield_end = now + 12
            avatar.attack_boost = 3.0
            avatar.attack_boost_end = now + 25
            self.effects.append(Effect(type="spawn", x=avatar.x, y=avatar.y, color=(255, 0, 255), duration=2.5))

        self.events_log.append(("gift", name, display_name or name, gift_name, coin_value))

    def add_like(self, count: int = 1):
        self.total_likes += count
        # Likes give a small speed boost to all alive avatars
        for a in self.avatars.values():
            if a.alive and not a.is_bot:
                a.speed = min(3.5, a.speed + 0.01 * count)

    def add_message(self, name: str, text: str, display_name: str = ""):
        self.chat_messages.append({"name": display_name or name, "text": text, "time": time.time()})
        if len(self.chat_messages) > 8:
            self.chat_messages = self.chat_messages[-8:]
        if name not in self.avatars:
            self.add_viewer(name, display_name)

    # ── Game Loop ──

    def step(self):
        self._tick += 1
        now = time.time()
        alive = [a for a in self.avatars.values() if a.alive]

        for avatar in list(self.avatars.values()):
            if not avatar.alive:
                if now - avatar.death_time >= RESPAWN_TIME:
                    avatar.alive = True
                    avatar.hp = avatar.max_hp
                    avatar.x, avatar.y = self._random_pos()
                    avatar.shield = False
                    avatar.attack_boost = 1.0
                    self.effects.append(Effect(type="spawn", x=avatar.x, y=avatar.y, color=avatar.color, duration=1.0))
                continue

            # Expire buffs
            if avatar.shield and now > avatar.shield_end:
                avatar.shield = False
            if avatar.attack_boost > 1.0 and now > avatar.attack_boost_end:
                avatar.attack_boost = 1.0

            # Find / update target
            if (not avatar.target or avatar.target not in self.avatars
                    or not self.avatars[avatar.target].alive
                    or random.random() < 0.005):
                best, best_d = None, float("inf")
                for other in alive:
                    if other.name == avatar.name:
                        continue
                    d = avatar.distance_to(other)
                    if d < best_d:
                        best_d = d
                        best = other.name
                avatar.target = best

            # Movement
            if avatar.target and avatar.target in self.avatars:
                tgt = self.avatars[avatar.target]
                if tgt.alive:
                    dx = tgt.x - avatar.x
                    dy = tgt.y - avatar.y
                    dist = math.hypot(dx, dy) or 1

                    if dist > ATTACK_RANGE:
                        avatar.vx += (dx / dist) * 0.3
                        avatar.vy += (dy / dist) * 0.3
                        spd = math.hypot(avatar.vx, avatar.vy)
                        if spd > avatar.speed:
                            avatar.vx = avatar.vx / spd * avatar.speed
                            avatar.vy = avatar.vy / spd * avatar.speed
                    else:
                        # Attack
                        if avatar.can_attack:
                            raw_dmg = max(1, int(avatar.power - tgt.defense * 0.5))
                            dmg = raw_dmg + random.randint(-2, 3)
                            dmg = max(1, dmg)

                            if tgt.shield:
                                self.effects.append(Effect(
                                    type="shield_hit", x=tgt.x, y=tgt.y - 25,
                                    value=0, color=(100, 180, 255), duration=0.6,
                                    text="BLOCKED"))
                            else:
                                tgt.hp -= dmg
                                avatar.damage_dealt += dmg
                                avatar.combo += 1
                                self.effects.append(Effect(
                                    type="damage", x=tgt.x + random.uniform(-15, 15),
                                    y=tgt.y - 35, value=dmg, color=(255, 50, 50), duration=1.0))
                                mid_x = (avatar.x + tgt.x) / 2
                                mid_y = (avatar.y + tgt.y) / 2
                                self.effects.append(Effect(
                                    type="hit", x=mid_x, y=mid_y,
                                    color=(255, 220, 60), duration=0.4,
                                    particles=[(random.uniform(-4, 4), random.uniform(-4, 4)) for _ in range(6)]))

                                if tgt.hp <= 0:
                                    self._kill(avatar, tgt, now)

                            avatar.last_attack = now

                        # Slight orbit / jitter when in range
                        angle = math.atan2(dy, dx) + math.pi / 2
                        avatar.vx = math.cos(angle) * avatar.speed * 0.4
                        avatar.vy = math.sin(angle) * avatar.speed * 0.4
            else:
                # Wander
                if random.random() < 0.03:
                    a = random.uniform(0, 2 * math.pi)
                    avatar.vx = math.cos(a) * avatar.speed * 0.6
                    avatar.vy = math.sin(a) * avatar.speed * 0.6

            # Friction
            avatar.vx *= 0.95
            avatar.vy *= 0.95

            # Apply velocity
            avatar.x += avatar.vx
            avatar.y += avatar.vy

            # Clamp to arena
            avatar.x = max(30, min(ARENA_W - 30, avatar.x))
            avatar.y = max(ARENA_TOP + 30, min(ARENA_BOTTOM - 30, avatar.y))

            # Decay combo
            if now - avatar.last_hit_time > 3:
                avatar.combo = 0

        # Clean effects
        self.effects = [e for e in self.effects if e.alive]

        # Update champion
        best = max((a for a in self.avatars.values() if a.kills > 0), key=lambda a: a.kills, default=None)
        if best:
            if self.champion != best.name:
                old = self.champion
                self.champion = best.name
                if old:
                    self.events_log.append(("champion", best.name, best.display_name, best.kills))

    def _kill(self, killer: Avatar, victim: Avatar, now: float):
        victim.alive = False
        victim.death_time = now
        victim.deaths += 1
        victim.combo = 0
        killer.kills += 1
        killer.xp += 15
        killer.last_hit_time = now
        # heal on kill
        killer.hp = min(killer.max_hp, killer.hp + int(killer.max_hp * 0.15))

        # Level up
        if killer.xp >= killer.level * 30:
            killer.level += 1
            killer.max_hp += 12
            killer.attack += 2
            killer.hp = min(killer.max_hp, killer.hp + 25)

        self.effects.append(Effect(
            type="death", x=victim.x, y=victim.y,
            color=victim.color, duration=1.8,
            particles=[(random.uniform(-5, 5), random.uniform(-5, 5)) for _ in range(10)]))
        self.events_log.append(("kill", killer.name, killer.display_name, victim.display_name))

    def get_leaderboard(self, n: int = 8) -> List[Avatar]:
        return sorted(
            [a for a in self.avatars.values()],
            key=lambda a: (a.kills, a.damage_dealt),
            reverse=True,
        )[:n]

    def pop_events(self) -> List[tuple]:
        evts = self.events_log[:]
        self.events_log.clear()
        return evts
