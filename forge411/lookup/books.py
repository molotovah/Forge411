"""Livres : Open Library (sans clé) ; Google Books en complément si une clé est fournie."""

import re

from ..model import Ident, Match
from . import Http, LookupFailed

GOOGLE_KEY_URL = "https://developers.google.com/books/docs/v1/using#APIKey"


def _text(v) -> str:
    if isinstance(v, dict):
        v = v.get("value", "")
    return re.sub(r"<[^>]+>", "", v or "").strip()


class Books:
    key = "books"
    label = "Open Library"

    def __init__(self, google_key: str = ""):
        self.ol = Http("Open Library", "https://openlibrary.org", min_interval=0.3)
        self.google_key = (google_key or "").strip()
        self.g = Http("Google Books", "https://www.googleapis.com/books/v1") if self.google_key else None

    def test(self) -> str:
        if self.g:
            self.g.get("/volumes", q="isbn:9782070360024", key=self.google_key)
            return "Clé Google Books valide"
        return "Aucune clé nécessaire"

    # ── Recherche ─────────────────────────────────────────────────────────
    def search(self, query: str, year: str = "", author: str = "", isbn: str = "") -> list:
        out = []
        if self.g:
            try:
                out = self._search_google(query, author, isbn)
            except LookupFailed:
                out = []
        if not out:
            out = self._search_ol(query, author, isbn)
        if year:
            out.sort(key=lambda m: m.year != year)
        return out

    def _search_ol(self, query, author, isbn):
        params = {"limit": 12, "fields": "key,title,author_name,first_publish_year,cover_i,isbn,subject,"
                                         "language,edition_count,publisher"}
        if isbn:
            params["isbn"] = isbn
        else:
            params["title"] = re.sub(r"[._]+", " ", query).strip()
            if author:
                params["author"] = author
        data = self.ol.get("/search.json", **params)
        if not data.get("docs") and not isbn:
            data = self.ol.get("/search.json", q=f"{params['title']} {author}".strip(), limit=12)
        out = []
        for d in data.get("docs", []):
            cover = d.get("cover_i")
            out.append(Match(id="ol:" + d.get("key", ""), title=d.get("title", ""),
                             year=str(d.get("first_publish_year") or ""),
                             subtitle=", ".join((d.get("author_name") or [])[:3]),
                             image=f"https://covers.openlibrary.org/b/id/{cover}-M.jpg" if cover else "",
                             kind="livre", score=(5 if "fre" in (d.get("language") or []) else 0)
                             + min(d.get("edition_count") or 0, 50) / 10, raw=d))
        return sorted(out, key=lambda m: m.score, reverse=True)

    def _search_google(self, query, author, isbn):
        q = f"isbn:{isbn}" if isbn else re.sub(r"[._]+", " ", query).strip() + (f" inauthor:{author}" if author else "")
        data = self.g.get("/volumes", q=q, maxResults=12, printType="books", key=self.google_key)
        out = []
        for it in data.get("items", []):
            v = it.get("volumeInfo", {})
            img = (v.get("imageLinks") or {}).get("thumbnail", "").replace("http://", "https://")
            out.append(Match(id="g:" + it["id"], title=v.get("title", ""), year=(v.get("publishedDate") or "")[:4],
                             subtitle=", ".join(v.get("authors", [])), overview=v.get("description", ""),
                             image=img, kind="livre"))
        return out

    # ── Détails ───────────────────────────────────────────────────────────
    def details(self, m: Match) -> Ident:
        if m.id.startswith("g:"):
            return self._details_google(m.id[2:])
        d = m.raw
        key = d.get("key", "")
        work = {}
        try:
            work = self.ol.get(f"{key}.json")
        except LookupFailed:
            pass
        authors = ", ".join((d.get("author_name") or [])[:3])
        img = f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg" if d.get("cover_i") else ""
        isbn = next((i for i in (d.get("isbn") or []) if len(i) == 13), (d.get("isbn") or [""])[0])
        subjects = [s for s in (work.get("subjects") or d.get("subject") or []) if len(s) < 30][:6]
        desc = _text(work.get("description"))
        facts = [(k, v) for k, v in (("Première parution", str(d.get("first_publish_year") or "")),
                                     ("Éditeur", ", ".join((d.get("publisher") or [])[:2])),
                                     ("ISBN", isbn)) if v]
        payload = {"openLibraryKey": key, "title": d.get("title", ""), "authors": d.get("author_name") or [],
                   "firstPublishYear": d.get("first_publish_year"), "isbn": isbn, "subjects": subjects,
                   "description": desc, "coverUrl": img}
        return Ident(provider="books", id=key, kind="livre", title=d.get("title", ""),
                     year=str(d.get("first_publish_year") or ""), overview=desc, image=img,
                     url=f"https://openlibrary.org{key}", genres=subjects,
                     people=[("Auteur", authors)] if authors else [], facts=facts,
                     payload_key="bookData", payload=payload, raw={"authors": d.get("author_name") or []})

    def _details_google(self, gid: str) -> Ident:
        it = self.g.get(f"/volumes/{gid}", key=self.google_key)
        v = it.get("volumeInfo", {})
        links = v.get("imageLinks") or {}
        img = (links.get("large") or links.get("medium") or links.get("thumbnail") or "").replace("http://", "https://")
        isbns = {i.get("type"): i.get("identifier") for i in v.get("industryIdentifiers", [])}
        desc = _text(v.get("description", ""))
        facts = [(k, val) for k, val in (("Éditeur", v.get("publisher", "")), ("Parution", v.get("publishedDate", "")),
                                         ("Pages", str(v.get("pageCount") or "")),
                                         ("ISBN", isbns.get("ISBN_13") or isbns.get("ISBN_10") or "")) if val]
        authors = ", ".join(v.get("authors", []))
        payload = {"googleBooksId": it["id"], "title": v.get("title", ""), "authors": v.get("authors", []),
                   "publisher": v.get("publisher", ""), "publishedDate": v.get("publishedDate", ""),
                   "pageCount": v.get("pageCount"), "isbn": isbns, "categories": v.get("categories", []),
                   "language": v.get("language", ""), "description": desc, "coverUrl": img}
        return Ident(provider="books", id=it["id"], kind="livre", title=v.get("title", ""),
                     original_title=v.get("subtitle", ""), year=(v.get("publishedDate") or "")[:4],
                     overview=desc, image=img, url=v.get("infoLink", ""), genres=v.get("categories", []),
                     people=[("Auteur", authors)] if authors else [], facts=facts,
                     payload_key="bookData", payload=payload, raw={"authors": v.get("authors", [])})
