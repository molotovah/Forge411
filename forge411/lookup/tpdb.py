"""
ThePornDB (theporndb.net) : fiches des scènes et films XXX (jeton API personnel).

C411 accepte tpdbData pour les sous-catégories XXX Films et VR ; l'identifiant
(UUID) et le type suffisent : {"id": "<uuid>", "kind": "scene"} ou "movie".
"""

import re

from ..model import Ident, Match
from . import Http, LookupFailed

KEY_URL = "https://theporndb.net/"
BASE = "https://api.theporndb.net"
KINDS = {"scene": ("/scenes", "Scène"), "movie": ("/movies", "Film")}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def uuid_of(item: dict) -> str:
    """Identifiant UUID d'un résultat (champ id, sinon uuid)."""
    for k in ("id", "uuid", "_id"):
        v = str(item.get(k) or "")
        if UUID_RE.match(v):
            return v.lower()
    return ""


def _image(item: dict) -> str:
    """Image de la fiche ; de préférence sur cdn.theporndb.net, seul domaine ThePornDB affiché par C411
    (thumb.theporndb.net est remplacé par un simple lien)."""
    found = []
    for k in ("poster", "image", "back_image"):
        v = item.get(k)
        if isinstance(v, str) and v.startswith("http"):
            found.append(v)
    for k in ("posters", "background"):
        v = item.get(k) or {}
        if isinstance(v, dict):
            for size in ("large", "full", "medium"):
                if str(v.get(size) or "").startswith("http"):
                    found.append(v[size])
    from ..rules import allowed
    return next((u for u in found if allowed(u)), found[0] if found else "")


def _names(items) -> list:
    out = []
    for p in items or []:
        n = (p.get("name") or (p.get("parent") or {}).get("name") or "") if isinstance(p, dict) else str(p)
        if n and n not in out:
            out.append(n)
    return out


TECH = r"\b(2160p|1080p|720p|480p|[4-8]K|WEB|WEB-?DL|WEBRip|x26[45]|H26[45]|HEVC|AVC|XXX|VR180|VR360|180|360|SBS|" \
       r"LR|3DH|ENGLISH|FRENCH|MULTI|VO|JAPANESE|GERMAN|SPANISH|ITALIAN|VOSTFR|AAC2?|AC3|MP4|MKV)\b"


def clean_query(q: str) -> str:
    """« [Brazzers].2024.01.02.Titre.Kenna.James.1080p… » → « Brazzers 2024 01 02 Titre Kenna James »."""
    q = re.sub(r"-[A-Za-z0-9]+$", "", q)
    q = re.sub(r"\[([^\]]+)\]", r" \1 ", q)
    q = re.sub(r"\b((?:19|20)\d\d)-(\d\d)-(\d\d)\b", r"\1 \2 \3", q)     # date 2023-06-27
    q = re.sub(r"[._]+", " ", q)
    q = re.split(TECH, q, flags=re.I)[0]
    return re.sub(r"\s+", " ", q).strip()


def queries(raw: str) -> list:
    """Requêtes à essayer, de la plus précise à la plus large : [(mode, texte)].

    mode « parse » : analyse du nom par ThePornDB (format Studio.AA.MM.JJ.Interprètes.Titre) ;
    mode « q » : recherche plein texte (sans date ni tags techniques, puis sans le studio) ;
    en dernier, studio + date seuls (un interprète du nom peut manquer sur la fiche)."""
    base = clean_query(raw)
    words = base.split()
    out = []
    m = re.match(r"^(.*?)\s((?:19|20)(\d\d))\s(\d\d)\s(\d\d)\s(.+)$", base)
    if m:
        studio, yy, mm, dd, rest = m.group(1).replace(" ", ""), m.group(3), m.group(4), m.group(5), m.group(6)
        out.append(("parse", f"{studio}.{yy}.{mm}.{dd}.{rest.replace(' ', '.')}"))
        out.append(("q", f"{m.group(1)} {rest}"))
        out.append(("q", rest))
        out.append(("parse", f"{studio}.{yy}.{mm}.{dd}"))
    else:
        out.append(("q", base))
        if len(words) > 3:
            out.append(("q", " ".join(words[1:])))
    seen, uniq = set(), []
    for mode, text in out:
        if text and (mode, text) not in seen:
            seen.add((mode, text))
            uniq.append((mode, text))
    return uniq


class TPDB:
    key = "tpdb"
    label = "ThePornDB"

    def __init__(self, token: str):
        self.token = (token or "").strip()
        if not self.token:
            raise LookupFailed("Jeton ThePornDB manquant (Paramètres).")
        self.http = Http("ThePornDB", BASE, min_interval=0.3, headers={"Authorization": f"Bearer {self.token}"})

    def test(self) -> str:
        self.http.get("/scenes", q="test", per_page=1)
        return "Jeton ThePornDB valide"

    def search(self, query: str, year: str = "", kind: str = "") -> list:
        out, seen = [], set()
        for mode, text in queries(query):
            for k in ([kind] if kind in KINDS else list(KINDS)):
                if mode == "parse" and k != "scene":
                    continue
                out += self._search(k, {mode: text}, year, seen)
            if out:
                break
        return sorted(out, key=lambda m: m.score, reverse=True)

    def _search(self, k, params, year, seen) -> list:
        path, label = KINDS[k]
        data = self.http.get(path, per_page=12, **params)
        out = []
        for rank, it in enumerate(data.get("data") or []):
            uid = uuid_of(it)
            if not uid or uid in seen:
                continue
            seen.add(uid)
            site = (it.get("site") or {}).get("name") or ""
            date = it.get("date") or ""
            performers = ", ".join(_names(it.get("performers"))[:4])
            score = 100 - rank + (20 if k == "scene" else 0) + (30 if year and date[:4] == year else 0)
            out.append(Match(id=f"{k}:{uid}", title=it.get("title") or "", year=date[:4],
                             subtitle=" · ".join(x for x in (site, date, performers) if x), image=_image(it),
                             overview=(it.get("description") or "").strip(), kind=label, score=score, raw=it))
        return out

    def details(self, m: Match) -> Ident:
        kind, uid = m.id.split(":", 1)
        it = m.raw or {}
        try:                                   # fiche complète (description, interprètes…)
            full = self.http.get(f"{KINDS[kind][0]}/{uid}").get("data")
            if isinstance(full, dict):
                it = {**it, **full}
        except LookupFailed:
            pass
        site = it.get("site") or {}
        performers = _names(it.get("performers"))
        date = it.get("date") or ""
        tags = _names(it.get("tags"))
        minutes = int(it.get("duration") or 0) // 60
        url = it.get("url") or ""
        slug = it.get("slug") or ""
        page = f"https://theporndb.net/{'scenes' if kind == 'scene' else 'movies'}/{slug or uid}"
        people = [("Interprètes", ", ".join(performers))] if performers else []
        facts = [(k, v) for k, v in (("Studio", site.get("name") or ""), ("Date", date),
                                     ("Durée", f"{minutes} min" if minutes else ""), ("Site officiel", url)) if v]
        return Ident(provider="tpdb", id=uid, kind=KINDS[kind][1], title=it.get("title") or m.title, year=date[:4],
                     overview=(it.get("description") or "").strip(), image=_image(it) or m.image, url=page,
                     genres=tags[:8], people=people, facts=facts,
                     payload_key="tpdbData", payload={"id": uid, "kind": kind},
                     raw={"site": site.get("name") or "", "site_short": site.get("short_name") or "",
                          "performers": performers, "date": date, "tags": tags,
                          "genders": [str(((p.get("extras") or (p.get("parent") or {}).get("extras") or {})
                                           .get("gender")) or "").lower() for p in it.get("performers") or []
                                      if isinstance(p, dict)]})
