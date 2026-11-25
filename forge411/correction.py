"""
Correction d'un upload après un retour de la Team Pending (« Modification demandée »).

L'API C411 (clés d'intégration) ne permet ni de lire la discussion de modération
ni de modifier un torrent : l'utilisateur colle le message reçu, Forge411 le
découpe en points rattachés aux étapes de l'assistant, recharge l'upload (même
.torrent, même info-hash : le seed continue) et prépare titre, description et
NFO corrigés à coller dans « Modifier » sur la page du torrent, avant
« Soumettre pour re-examen ».
"""

import re
from dataclasses import dataclass

STEP_SOURCE, STEP_IDENT, STEP_NAME, STEP_NFO, STEP_PREZ, STEP_PUBLISH = range(6)
STEP_LABELS = ("Source", "Identification", "Nom", "NFO", "Présentation", "Publication")

# Mot-clé du point → étape où le corriger (premier trouvé)
_RULES = (
    (STEP_PUBLISH, r"\bseed|disponibilit|leech|client torrent"),
    (STEP_PREZ, r"screenshot|capture|image|banni[eè]re|description|pr[ée]sentation|postimg|zupimages|synopsis|r[ée]sum[ée]"),
    (STEP_NFO, r"\bnfo\b|mediainfo"),
    (STEP_NAME, r"nommage|titre|nom de|\btag\b|ordre|structure|placée|date|r[ée]solution|source|codec|team|\[[A-Z]+\]"),
    (STEP_PREZ, r"option|langue|qualit[ée]|genre|sous-cat[ée]gorie|cat[ée]gorie"),
    (STEP_SOURCE, r"format|fichier|archive|doublon|interdit"),
)
HASH_RE = re.compile(r"\b([0-9a-f]{40})\b", re.I)


@dataclass
class Point:
    step: int
    text: str


def parse(message: str) -> list:
    """Points du message de la Team Pending, rattachés à une étape."""
    text = (message or "").replace("\r", "")
    text = re.sub(r"(Retrouve la documentation|Merci d'avance|Modifiez votre torrent).*$", "", text, flags=re.S | re.I)
    text = re.sub(r"^.*?(points? à corriger[^:]*:)", "", text, flags=re.S | re.I)
    chunks = re.split(r"(?:^|\s)(?=\d{1,2}\.\s)", text)
    out = []
    for ch in chunks:
        ch = re.sub(r"^\d{1,2}\.\s*", "", ch.strip())
        ch = re.sub(r"[➡️❌🛠️📜✅⚠️👉•]+\s*:?", " ", ch)
        ch = re.sub(r"\s+", " ", ch).strip(" -:")
        if len(ch) < 8:
            continue
        step = next((st for st, pat in _RULES if re.search(pat, ch, re.I)), STEP_PUBLISH)
        out.append(Point(step, ch))
    return out


def infohash_of(text: str) -> str:
    m = HASH_RE.search(text or "")
    return m.group(1).lower() if m else ""


def torrent_page(infohash: str) -> str:
    from .api import BASE
    return f"{BASE}/torrents/{infohash.lower()}" if infohash else ""


def shots_needed(points: list) -> int:
    """Nombre de captures réclamé (« au minimum 3 screenshot(s) »), 0 sinon."""
    for p in points:
        m = re.search(r"minimum (?:de )?(\d+) (?:screenshot|capture)", p.text, re.I)
        if m:
            return int(m.group(1))
    return 0
