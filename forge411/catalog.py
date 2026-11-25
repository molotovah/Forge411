"""
Doublons et slots : comparaison du nom préparé avec les releases déjà sur C411.

C411 range chaque film en 28 slots (4 profils : Home Cinéma Pure, Home Cinéma
Optimisé, Optimisation, Compatibilité). La décision exacte est prise par le site ;
Forge411 en donne une estimation à partir du nom pour prévenir un refus et
proposer une justification hors slot.
"""

import re
from dataclasses import dataclass, field

FAMILY_LABELS = {"PURE": "Home Cinéma Pure", "HCOPT": "Home Cinéma Optimisé", "OPTI": "Optimisation",
                 "COMPAT": "Compatibilité"}
SPECIAL = ("UNCUT", "THEATRICAL", "EXTENDED", "DIRECTORS.CUT", "DC", "IMAX", "OPEN.MATTE", "REMASTERED", "HYBRID", "AD")
LOSSLESS = ("TRUEHD", "DTS.HD.MA", "DTS-HD.MA", "FLAC", "LPCM", "PCM", "ATMOS")


def _up(name: str) -> str:
    return "." + re.sub(r"[\s_\-]+", ".", name.upper()) + "."


def resolution(name: str) -> str:
    m = re.search(r"\.(2160P|1080P|720P|576P|480P)\.", _up(name))
    return m.group(1).lower() if m else ""


def family(name: str) -> str:
    """Profil de slot estimé : PURE, HCOPT, OPTI ou COMPAT (vide hors vidéo reconnue)."""
    u = _up(name)
    res = resolution(name)
    if not res:
        return ""
    if any(f".{t}." in u for t in ("REMUX", "BDMV", "ISO")):
        return "PURE"
    h264 = any(f".{t}." in u for t in ("X264", "H264", "AVC"))
    lossless = any(f".{t}." in u or t in u for t in LOSSLESS)
    hdr = any(f".{t}." in u for t in ("HDR", "HDR10", "HDR10PLUS", "DV"))
    if res == "1080p" and h264 and not hdr and not lossless:
        return "COMPAT"
    if ".AV1." in u or lossless or (res == "2160p" and ".DV." in u):
        return "HCOPT"
    return "OPTI" if not lossless else "HCOPT"


def special(name: str) -> set:
    u = _up(name)
    return {t for t in SPECIAL if f".{t}." in u}


def slot_family(slot: str) -> str:
    return (slot or "").split("-", 1)[0].upper()


def slot_resolution(slot: str) -> str:
    m = re.search(r"-(2160|1080|720)\b", slot or "")
    return f"{m.group(1)}p" if m else ""


@dataclass
class Verdict:
    exact: list = field(default_factory=list)       # même nom : doublon
    same_slot: list = field(default_factory=list)   # même profil et résolution : slot probablement occupé
    others: list = field(default_factory=list)
    family: str = ""

    @property
    def needs_justification(self) -> bool:
        return bool(self.same_slot) and not self.exact


def compare(name: str, releases: list) -> Verdict:
    """Classe les releases existantes par rapport au nom préparé."""
    v = Verdict(family=family(name))
    norm = lambda n: re.sub(r"[^a-z0-9]", "", n.lower())
    me, res, sp = norm(name), resolution(name), special(name)
    for r in releases:
        if norm(r.name) == me:
            v.exact.append(r)
            continue
        if special(r.name) != sp:              # versions spéciales : jeu de slots indépendant
            v.others.append(r)
            continue
        fam = slot_family(r.slot) or family(r.name)
        rres = slot_resolution(r.slot) or resolution(r.name)
        if v.family and fam == v.family and (rres == res or (fam == "COMPAT" and res == "1080p")):
            v.same_slot.append(r)
        else:
            v.others.append(r)
    return v
