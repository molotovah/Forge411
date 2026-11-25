"""Registre des profils de contenu."""

from .base import Ctx, Profile, options_payload
from .ebook import EbookProfile
from .misc import EmulationProfile, GpsProfile, PrintProfile
from .music import MusicProfile
from .software import AppProfile, GameProfile
from .video import VideoProfile
from .xxx import XxxProfile

PROFILES = [VideoProfile(), MusicProfile(), EbookProfile(), GameProfile(), AppProfile(),
            EmulationProfile(), GpsProfile(), PrintProfile(), XxxProfile()]


def get(key: str) -> Profile:
    return next(p for p in PROFILES if p.key == key)


def detect(src) -> list:
    """Profils triés du plus probable au moins probable : [(score, profil)]."""
    ranked = sorted(((p.score(src), p) for p in PROFILES), key=lambda x: -x[0])
    if ranked[0][0] <= 0:
        ranked.insert(0, (0.1, get("app")))
    return ranked


__all__ = ["PROFILES", "Ctx", "Profile", "detect", "get", "options_payload"]
