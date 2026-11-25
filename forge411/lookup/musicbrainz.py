"""MusicBrainz + Cover Art Archive : albums (sans clé, 1 requête/s)."""

import re

from ..model import Ident, Match, fmt_clock
from . import Http

COVER = "https://coverartarchive.org/release-group/{}/front-{}"


def _q(s: str) -> str:
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", s.strip())


class MusicBrainz:
    key = "musicbrainz"
    label = "MusicBrainz"

    def __init__(self):
        self.http = Http("MusicBrainz", "https://musicbrainz.org/ws/2", min_interval=1.1)

    def test(self) -> str:
        return "Aucune clé nécessaire"

    def search(self, query: str, year: str = "", artist: str = "") -> list:
        parts = [f'releasegroup:"{_q(query)}"'] if query else []
        if artist:
            parts.append(f'artist:"{_q(artist)}"')
        if year:
            parts.append(f"firstreleasedate:{year}*")
        data = self.http.get("/release-group", query=" AND ".join(parts) or _q(artist), fmt="json", limit=12)
        if not data.get("release-groups") and year:
            return self.search(query, "", artist)
        out = []
        for rg in data.get("release-groups", []):
            artists = "".join(a.get("name", "") + a.get("joinphrase", "") for a in rg.get("artist-credit", []))
            kind = rg.get("primary-type") or "Album"
            sec = rg.get("secondary-types") or []
            out.append(Match(id=rg["id"], title=rg.get("title", ""), year=(rg.get("first-release-date") or "")[:4],
                             subtitle=artists, kind=" / ".join([kind] + sec), image=COVER.format(rg["id"], 250),
                             score=rg.get("score", 0), raw={"artist": artists}))
        return out

    def details(self, m: Match) -> Ident:
        rg = self.http.get(f"/release-group/{m.id}", inc="artist-credits+releases+genres+tags", fmt="json")
        artists = "".join(a.get("name", "") + a.get("joinphrase", "") for a in rg.get("artist-credit", []))
        releases = sorted(rg.get("releases", []), key=lambda r: (r.get("status") != "Official", r.get("date") or "9999"))
        tracks, label, catno, country = [], "", "", ""
        if releases:
            rel = self.http.get(f"/release/{releases[0]['id']}", inc="recordings+labels", fmt="json")
            country = rel.get("country") or ""
            li = (rel.get("label-info") or [{}])[0]
            label = (li.get("label") or {}).get("name", "") if li else ""
            catno = li.get("catalog-number", "") if li else ""
            if catno and catno.strip("[]").lower() in ("none", ""):
                catno = ""
            for medium in rel.get("media", []):
                for t in medium.get("tracks", []):
                    tracks.append({"position": t.get("number"), "title": t.get("title"),
                                   "length": (t.get("length") or 0) / 1000})
        genres = [g["name"].title() for g in sorted(rg.get("genres", []), key=lambda g: -g.get("count", 0))][:5]
        year = (rg.get("first-release-date") or "")[:4]
        facts = [("Type", m.kind or rg.get("primary-type") or "Album")]
        if label:
            facts.append(("Label", label + (f" ({catno})" if catno else "")))
        if country:
            facts.append(("Pays", country))
        if tracks:
            facts.append(("Pistes", str(len(tracks))))
        payload = {"musicbrainzId": rg["id"], "title": rg.get("title", ""), "artist": artists, "year": year,
                   "type": rg.get("primary-type"), "genres": genres, "label": label, "catalogNumber": catno,
                   "tracks": tracks, "coverUrl": COVER.format(rg["id"], 500)}
        overview = ""
        if tracks:
            overview = "\n".join(f"{t['position']}. {t['title']}" + (f" ({fmt_clock(t['length'])})" if t["length"] else "")
                                 for t in tracks)
        return Ident(provider="musicbrainz", id=rg["id"], kind="album", title=rg.get("title", ""), year=year,
                     image=COVER.format(rg["id"], 500), url=f"https://musicbrainz.org/release-group/{rg['id']}",
                     genres=genres, people=[("Artiste", artists)], facts=facts, overview=overview,
                     payload_key="musicData", payload=payload, raw={"artist": artists, "tracks": tracks})
