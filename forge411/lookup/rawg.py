"""RAWG : jeux vidéo (clé gratuite)."""

import re

from ..model import Ident, Match
from . import Http, LookupFailed

KEY_URL = "https://rawg.io/apidocs"


class RAWG:
    key = "rawg"
    label = "RAWG"

    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise LookupFailed("Clé RAWG manquante (Paramètres).")
        self.http = Http("RAWG", "https://api.rawg.io/api")

    def test(self) -> str:
        self.http.get("/platforms/lists/parents", key=self.api_key, page_size=1)
        return "Clé RAWG valide"

    def search(self, query: str, year: str = "", platform: str = "") -> list:
        q = query.strip() if " " in query.strip() else re.sub(r"[._]+", " ", query).strip()
        data = self.http.get("/games", key=self.api_key, search=q, page_size=12)
        norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
        out = []
        for rank, g in enumerate(data.get("results", [])):
            plats = ", ".join(p["platform"]["name"] for p in (g.get("platforms") or [])[:4])
            # Ordre de pertinence de RAWG, titre exact et année en bonus
            score = 100 - rank + (200 if norm(g.get("name", "")) == norm(q) else 0) \
                + (50 if year and (g.get("released") or "")[:4] == year else 0)
            out.append(Match(id=str(g["id"]), title=g.get("name", ""), year=(g.get("released") or "")[:4],
                             subtitle=plats, image=g.get("background_image") or "", kind="Jeu", score=score,
                             raw={"slug": g.get("slug")}))
        return sorted(out, key=lambda m: m.score, reverse=True)

    def details(self, m: Match) -> Ident:
        g = self.http.get(f"/games/{m.id}", key=self.api_key)
        desc = g.get("description_raw") or re.sub(r"<[^>]+>", "", g.get("description", ""))
        devs = ", ".join(d["name"] for d in g.get("developers", []))
        pubs = ", ".join(p["name"] for p in g.get("publishers", []))
        plats = ", ".join(p["platform"]["name"] for p in g.get("platforms", []))
        people = [(k, v) for k, v in (("Développeur", devs), ("Éditeur", pubs)) if v]
        facts = [(k, v) for k, v in (("Sortie", g.get("released") or ""), ("Plateformes", plats),
                                     ("Metacritic", str(g.get("metacritic") or ""))) if v]
        reqs = {}
        for p in g.get("platforms", []):
            if p["platform"].get("slug") == "pc" and p.get("requirements"):
                reqs = p["requirements"]
        payload = {"id": g["id"], "slug": g.get("slug"), "name": g.get("name"), "released": g.get("released"),
                   "description": desc, "backgroundImage": g.get("background_image"),
                   "genres": [x["name"] for x in g.get("genres", [])],
                   "platforms": [p["platform"]["name"] for p in g.get("platforms", [])],
                   "developers": [d["name"] for d in g.get("developers", [])],
                   "publishers": [p["name"] for p in g.get("publishers", [])],
                   "metacritic": g.get("metacritic"), "website": g.get("website")}
        return Ident(provider="rawg", id=str(g["id"]), kind="jeu", title=g.get("name", ""),
                     year=(g.get("released") or "")[:4], overview=desc, image=g.get("background_image") or "",
                     url=f"https://rawg.io/games/{g.get('slug')}", genres=[x["name"] for x in g.get("genres", [])],
                     people=people, facts=facts, payload_key="rawgData", payload=payload,
                     raw={"requirements": reqs})
