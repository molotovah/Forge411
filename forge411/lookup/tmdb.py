"""TMDB : films et séries (clé v3 ou jeton d'accès v4)."""

import re

from ..model import Ident, Match
from . import Http, LookupFailed

IMG = "https://image.tmdb.org/t/p/"
KEY_URL = "https://www.themoviedb.org/settings/api"


class TMDB:
    key = "tmdb"
    label = "TMDB"

    def __init__(self, api_key: str):
        api_key = (api_key or "").strip()
        if not api_key:
            raise LookupFailed("Clé TMDB manquante (Paramètres).")
        headers, self.params = {}, {}
        if api_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            self.params = {"api_key": api_key}
        self.http = Http("TMDB", "https://api.themoviedb.org/3", headers=headers)

    def _get(self, path, **params):
        return self.http.get(path, **{"language": "fr-FR", **self.params, **params})

    def test(self) -> str:
        self._get("/configuration")
        return "Clé TMDB valide"

    def search(self, query: str, year: str = "", kind: str = "") -> list:
        query = re.sub(r"[._]+", " ", query).strip()
        out = []
        for k in ("movie", "tv"):
            params = {"query": query}
            if year:
                params["year" if k == "movie" else "first_air_date_year"] = year
            data = self._get(f"/search/{k}", **params)
            if not data.get("results") and year:
                data = self._get(f"/search/{k}", query=query)
            for r in data.get("results", []):
                movie = k == "movie"
                date = r.get("release_date" if movie else "first_air_date") or ""
                title = r.get("title" if movie else "name", "")
                orig = r.get("original_title" if movie else "original_name", "")
                score = (r.get("popularity") or 0) + (1000 if kind == k else 0) \
                    + (500 if year and date[:4] == year else 0) \
                    + (300 if query.lower() in (title.lower(), orig.lower()) else 0)
                out.append(Match(id=str(r["id"]), title=title, year=date[:4],
                                 subtitle=orig if orig != title else "",
                                 overview=r.get("overview", ""), kind="Film" if movie else "Série",
                                 image=f"{IMG}w92{r['poster_path']}" if r.get("poster_path") else "",
                                 score=score, raw={"media_type": k}))
        return sorted(out, key=lambda m: m.score, reverse=True)[:12]

    def details(self, m: Match) -> Ident:
        kind = m.raw.get("media_type", "movie")
        d = self._get(f"/{kind}/{m.id}", append_to_response="credits")
        if not d.get("overview"):
            d["overview"] = self._get(f"/{kind}/{m.id}", language="en-US").get("overview", "")
        movie = kind == "movie"
        date = d.get("release_date" if movie else "first_air_date") or ""
        credits = d.get("credits", {})
        if movie:
            makers = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
            runtime = d.get("runtime")
        else:
            makers = [c["name"] for c in d.get("created_by", [])]
            rt = d.get("episode_run_time") or []
            runtime = rt[0] if rt else None
        cast = [{"name": c["name"], "character": c.get("character", "")} for c in credits.get("cast", [])[:10]]
        title = d.get("title" if movie else "name", "")
        orig = d.get("original_title" if movie else "original_name", "")
        people = []
        if makers:
            people.append(("Réalisation" if movie else "Création", ", ".join(makers)))
        if cast:
            people.append(("Avec", ", ".join(c["name"] for c in cast[:6])))
        facts = []
        if runtime:
            facts.append(("Durée", f"{runtime} min" + ("" if movie else " / épisode")))
        if d.get("vote_average"):
            facts.append(("Note TMDB", f"{d['vote_average']:.1f}/10"))
        if d.get("production_countries"):
            facts.append(("Pays", ", ".join(c.get("name", "") for c in d["production_countries"])))
        if not movie and d.get("number_of_seasons"):
            facts.append(("Saisons", str(d["number_of_seasons"])))
        payload = {
            "id": d["id"], "mediaType": kind, "title": title, "originalTitle": orig,
            "overview": d.get("overview", ""), "releaseDate": date, "runtime": runtime,
            "voteAverage": d.get("vote_average"), "voteCount": d.get("vote_count"),
            "popularity": d.get("popularity"), "posterPath": d.get("poster_path") or "",
            "backdropPath": d.get("backdrop_path") or "", "genres": d.get("genres", []),
            "productionCountries": d.get("production_countries", []),
            "credits": {"cast": cast,
                        "crew": [{"name": n, "job": "Director" if movie else "Creator"} for n in makers]},
        }
        return Ident(provider="tmdb", id=str(d["id"]), kind=kind, title=title, original_title=orig,
                     year=date[:4], overview=d.get("overview", ""),
                     image=f"{IMG}w500{d['poster_path']}" if d.get("poster_path") else "",
                     url=f"https://www.themoviedb.org/{kind}/{d['id']}",
                     genres=[g["name"] for g in d.get("genres", [])], people=people, facts=facts,
                     payload_key="tmdbData", payload=payload, raw=d)
