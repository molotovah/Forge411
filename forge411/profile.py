"""
Profil C411 (GET /api/user/profile) : lecture et mise en forme, sans interface.

Scope de la clé requis : « Profil (lecture) » (profile:read). Données rafraîchies
par C411 au plus toutes les 30 secondes ; 30 requêtes par minute au maximum.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

VOIES = (("seed", "Seed"), ("upload", "Upload"), ("specialization", "Spécialisation"),
         ("competitivity", "Compétitivité"))
GRADES = {"bronze": "Bronze", "argent": "Argent", "or": "Or"}
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}
BLOCK_REASONS = {"insufficient_balance": "Solde Zen insuffisant"}
FREELEECH_SOURCES = {"personal": "personnel", "campaign": "événement du site", "window": "fenêtre Freeleech"}
TEAM_ROLES = {"member": "Membre", "owner": "Fondateur", "leader": "Chef d'équipe", "admin": "Administrateur",
              "moderator": "Modérateur"}
MIN_REFRESH = 30          # secondes : inutile d'interroger plus souvent


@dataclass
class Voie:
    key: str
    label: str
    done: int = 0
    total: int = 0
    star: bool = False


@dataclass
class Profile:
    username: str = ""
    avatar_url: str = ""
    member_since: Optional[datetime] = None
    level: int = 0
    xp: int = 0
    xp_into: int = 0
    xp_next: int = 0
    class_name: str = ""
    grade: str = ""
    stars: int = 0
    quests_done: int = 0
    quests_total: int = 0
    tree_bonus: float = 0.0              # en %
    voies: list = field(default_factory=list)
    team_name: str = ""
    team_tag: str = ""
    team_role: str = ""
    zen: int = 0
    zen_earned: int = 0
    zen_spent: int = 0
    up_actual: int = 0
    up_credit: int = 0
    up_total: int = 0
    down_actual: int = 0
    down_credit: int = 0
    down_total: int = 0
    can_download: bool = True
    blocked_reason: str = ""
    freeleech: bool = False
    freeleech_sources: list = field(default_factory=list)
    silverleech: bool = False
    leech_bonuses: list = field(default_factory=list)

    @property
    def ratio(self) -> Optional[float]:
        """Ratio envoyé / reçu (crédits compris) ; None si rien n'a été reçu."""
        return self.up_total / self.down_total if self.down_total else None

    @property
    def level_progress(self) -> float:
        span = self.xp_into + self.xp_next
        return self.xp_into / span if span else 0.0

    @property
    def days(self) -> int:
        if not self.member_since:
            return 0
        return max(0, (datetime.now(timezone.utc) - self.member_since).days)


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def class_label(slug: str) -> str:
    """« team_resident_mainstream » → « Team Resident Mainstream »."""
    return " ".join(w.capitalize() for w in (slug or "").replace("-", "_").split("_") if w)


def parse(j: dict, base_url: str = "") -> Profile:
    p = Profile(username=j.get("username") or "")
    avatar = j.get("avatarUrl") or ""
    p.avatar_url = (base_url + avatar) if avatar.startswith("/") else avatar
    try:
        p.member_since = datetime.fromisoformat((j.get("memberSince") or "").replace("Z", "+00:00"))
    except ValueError:
        p.member_since = None
    lv = j.get("level") or {}
    p.level, p.xp = _int(lv.get("level")), _int(lv.get("xp"))
    p.xp_into, p.xp_next = _int(lv.get("xpIntoLevel")), _int(lv.get("xpToNextLevel"))
    c = j.get("class")
    if c:
        p.class_name = class_label(c.get("effectiveSlug") or c.get("slug"))
        p.tree_bonus = _int(c.get("treeBonusBp")) / 100
        pr = c.get("progress") or {}
        p.quests_done, p.quests_total, p.stars = _int(pr.get("questsCompleted")), _int(pr.get("questsTotal")), _int(pr.get("stars"))
        g = pr.get("grade") or {}
        if g.get("tier"):
            p.grade = f"{GRADES.get(g['tier'], g['tier'].capitalize())} {ROMAN.get(_int(g.get('level')), g.get('level') or '')}".strip()
        voies = c.get("voies") or {}
        for key, label in VOIES:
            v = voies.get(key) or {}
            p.voies.append(Voie(key, label, _int(v.get("questsCompleted")), _int(v.get("questsTotal")), bool(v.get("star"))))
    t = j.get("team")
    if t:
        p.team_name, p.team_tag = t.get("name") or "", t.get("tag") or ""
        p.team_role = TEAM_ROLES.get(t.get("role") or "", (t.get("role") or "").capitalize())
    z = j.get("zen") or {}
    p.zen, p.zen_earned, p.zen_spent = _int(z.get("balance")), _int(z.get("totalEarned")), _int(z.get("totalSpent"))
    tr = j.get("transfer") or {}
    up, down = tr.get("uploaded") or {}, tr.get("downloaded") or {}
    p.up_actual, p.up_credit, p.up_total = _int(up.get("actual")), _int(up.get("credit")), _int(up.get("total"))
    p.down_actual, p.down_credit, p.down_total = _int(down.get("actual")), _int(down.get("credit")), _int(down.get("total"))
    d = j.get("download") or {}
    p.can_download = bool(d.get("allowed", True))
    reason = d.get("blockedReason") or ""
    p.blocked_reason = BLOCK_REASONS.get(reason, reason)
    fl = j.get("freeleech") or {}
    p.freeleech = bool(fl.get("active"))
    p.freeleech_sources = [FREELEECH_SOURCES.get(s, s) for s in fl.get("sources") or []]
    p.silverleech = bool(j.get("silverLeech"))
    p.leech_bonuses = [b if isinstance(b, str) else (b.get("label") or b.get("name") or b.get("type") or str(b))
                       for b in j.get("leechBonuses") or []]
    return p


def fmt_bytes(n: int) -> str:
    """Comme sur C411 : base 1024, unités françaises (185,9 Go)."""
    n = float(n or 0)
    for unit in ("o", "Ko", "Mo", "Go", "To", "Po"):
        if abs(n) < 1024 or unit == "Po":
            return (f"{n:.1f}" if unit not in ("o", "Ko") else f"{n:.0f}").replace(".", ",") + f" {unit}"
        n /= 1024
    return ""


def fmt_ratio(r: Optional[float]) -> str:
    if r is None:
        return "∞"
    return f"{r:.2f}".replace(".", ",")


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


# ═══════════════════════════════════════════════════════════════════════════
# Évolution : instantanés locaux du profil
# ═══════════════════════════════════════════════════════════════════════════

SNAPSHOT_EVERY = 3600          # secondes entre deux instantanés
SNAPSHOT_KEEP = 400


def snapshot(p: Profile, at: float) -> dict:
    return {"at": int(at), "level": p.level, "xp": p.xp, "up": p.up_total, "down": p.down_total, "zen": p.zen,
            "earned": p.zen_earned, "quests": p.quests_done}


def record(path, p: Profile, at: float) -> list:
    """Ajoute un instantané (au plus un par heure) ; renvoie l'historique."""
    import json
    hist = load_history(path)
    if not hist or at - hist[-1]["at"] >= SNAPSHOT_EVERY:
        hist.append(snapshot(p, at))
        hist = hist[-SNAPSHOT_KEEP:]
        try:
            path.write_text("\n".join(json.dumps(h) for h in hist) + "\n", encoding="utf-8")
        except OSError:
            pass
    return hist


def load_history(path) -> list:
    import json
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


@dataclass
class Trend:
    since: float = 0.0          # horodatage de la référence
    up: int = 0
    down: int = 0
    zen: int = 0
    xp: int = 0
    levels: int = 0
    quests: int = 0
    ratio_before: Optional[float] = None
    xp_per_day: float = 0.0
    days_to_next: Optional[float] = None


def trend(p: Profile, hist: list, now: float, window_days: int = 7) -> Optional[Trend]:
    """Évolution depuis l'instantané le plus ancien de la fenêtre (au moins 1 h d'écart)."""
    ref = next((h for h in hist if now - h["at"] <= window_days * 86400 and now - h["at"] >= 3600), None)
    if not ref:
        return None
    t = Trend(since=ref["at"], up=p.up_total - ref["up"], down=p.down_total - ref["down"], zen=p.zen - ref["zen"],
              xp=p.xp - ref["xp"], levels=p.level - ref["level"], quests=p.quests_done - ref.get("quests", 0))
    t.ratio_before = ref["up"] / ref["down"] if ref["down"] else None
    days = (now - ref["at"]) / 86400
    if days > 0 and t.xp > 0:
        t.xp_per_day = t.xp / days
        t.days_to_next = p.xp_next / t.xp_per_day
    return t


def fmt_delta_bytes(n: int) -> str:
    return ("+" if n >= 0 else "−") + fmt_bytes(abs(n))
