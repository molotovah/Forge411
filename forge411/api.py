"""Client de l'API C411 (catégories, options, doublons, brouillons, upload)."""

import base64
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from . import USER_AGENT

BASE = "https://c411.org"


class C411Error(Exception):
    pass


@dataclass
class OptionType:
    id: int
    name: str
    multiple: bool
    required: bool
    values: list = field(default_factory=list)   # [{"id", "value"}]

    def find(self, label: str) -> Optional[int]:
        want = norm(label)
        for v in self.values:
            if norm(v["value"]) == want:
                return v["id"]
        return None


@dataclass
class Release:
    """Torrent déjà présent sur C411 (recherche Torznab)."""
    name: str
    url: str = ""
    size: int = 0
    seeders: int = 0
    slot: str = ""          # emplacement attribué par C411, ex. HCOPT-2160-4KL-H265
    tmdb_id: str = ""
    date: str = ""


@dataclass
class Result:
    ok: bool
    message: str
    url: str = ""


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "".join(c for c in s.lower() if c.isalnum())


class C411:
    def __init__(self, key: str):
        key = (key or "").strip()
        if not key:
            raise C411Error("Clé API C411 manquante (Paramètres).")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT})
        self._cats = None
        self._opts = {}

    # ── Requêtes ──────────────────────────────────────────────────────────
    def _req(self, method: str, path: str, **kw) -> requests.Response:
        try:
            return self.s.request(method, f"{BASE}{path}", timeout=kw.pop("timeout", 30), **kw)
        except requests.RequestException as e:
            raise C411Error(f"C411 injoignable : {e.__class__.__name__}") from e

    def _json(self, path: str) -> dict:
        r = self._req("GET", path)
        if r.status_code == 401:
            raise C411Error("Clé API C411 refusée (401).")
        if r.status_code == 403:
            raise C411Error("Clé API C411 sans le droit nécessaire (403).")
        if r.status_code != 200:
            raise C411Error(f"C411 : erreur HTTP {r.status_code}.")
        try:
            return r.json()
        except ValueError as e:
            raise C411Error("C411 : réponse illisible.") from e

    @staticmethod
    def _error(r: requests.Response) -> str:
        try:
            j = r.json()
        except ValueError:
            return f"HTTP {r.status_code}"
        msg = j.get("message") or j.get("error") or ""
        errs = j.get("errors")
        if isinstance(errs, dict):
            msg += " " + " ; ".join(f"{k} : {v}" for k, v in errs.items())
        elif isinstance(errs, list):
            msg += " " + " ; ".join(str(e) for e in errs)
        return f"HTTP {r.status_code} : {msg.strip() or r.text[:200]}"

    # ── Lecture ───────────────────────────────────────────────────────────
    def test(self) -> str:
        self.categories()
        r = self._req("GET", "/api/user/drafts")
        drafts = "brouillons OK" if r.status_code == 200 else "pas d'accès aux brouillons"
        prof = "profil OK" if self._req("GET", "/api/user/profile").status_code == 200 else "pas d'accès au profil"
        return f"Connexion OK ({drafts}, {prof})"

    def categories(self) -> list:
        if self._cats is None:
            self._cats = self._json("/api/categories").get("data", [])
        return self._cats

    def options(self, sub_id: int) -> list[OptionType]:
        if sub_id not in self._opts:
            data = self._json(f"/api/categories/{sub_id}/options").get("data", [])
            self._opts[sub_id] = [
                OptionType(id=t["id"], name=t["name"], multiple=bool(t.get("allowsMultiple")),
                           required=bool(t.get("isRequired")),
                           values=[{"id": v["id"], "value": v["value"]} for v in t.get("values", [])])
                for t in sorted(data, key=lambda t: t.get("sortOrder", 0))
            ]
        return self._opts[sub_id]

    def profile(self) -> dict:
        """Profil du membre (GET /api/user/profile, scope « Profil (lecture) »)."""
        r = self._req("GET", "/api/user/profile")
        if r.status_code == 403:
            raise C411Error("Ta clé API n'a pas le droit « Profil (lecture) ». Ce droit ne s'ajoute pas à une clé "
                            "existante : crée une nouvelle clé en le cochant, puis colle-la dans les Paramètres.")
        if r.status_code == 429:
            raise C411Error("Trop de requêtes sur le profil : réessaie dans une minute.")
        if r.status_code == 401:
            raise C411Error("Clé API C411 refusée (401).")
        if r.status_code != 200:
            raise C411Error(f"C411 : erreur HTTP {r.status_code}.")
        try:
            return r.json()
        except ValueError as e:
            raise C411Error("C411 : réponse illisible.") from e

    def existing(self, tmdb_id: int, media_type: str) -> list:
        d = self._json(f"/api/torrents/by-tmdb?tmdbId={tmdb_id}&tmdbType={media_type}")
        return d.get("releases", [])

    def search(self, query: str = "", tmdb_id: int = 0, kind: str = "", limit: int = 25) -> list:
        """Releases présentes sur C411 (API Torznab, droit accordé par défaut à la clé)."""
        from xml.etree import ElementTree
        params = {"apikey": self.s.headers["Authorization"].split(" ", 1)[1], "limit": limit}
        if tmdb_id and kind in ("movie", "tv"):
            params.update(t="movie" if kind == "movie" else "tvsearch", tmdbid=tmdb_id)
        else:
            params.update(t="search", q=query)
        r = self._req("GET", "/api", params=params)
        if r.status_code in (401, 403):
            raise C411Error("Recherche C411 refusée : clé API sans le droit Torznab.")
        if r.status_code != 200:
            raise C411Error(f"Recherche C411 : erreur HTTP {r.status_code}.")
        try:
            root = ElementTree.fromstring(r.content)
        except ElementTree.ParseError as e:
            raise C411Error("Recherche C411 : réponse illisible.") from e
        out = []
        for it in root.iter("item"):
            attrs = {a.get("name"): a.get("value") for a in it if a.tag.endswith("}attr")}
            out.append(Release(name=it.findtext("title") or "", url=it.findtext("link") or "",
                               size=int(it.findtext("size") or attrs.get("size") or 0),
                               seeders=int(attrs.get("seeders") or 0), slot=attrs.get("c411:slot") or "",
                               tmdb_id=attrs.get("tmdbid") or "", date=it.findtext("pubDate") or ""))
        return out

    def drafts(self) -> list:
        return self._json("/api/user/drafts").get("data", [])

    def delete_draft(self, draft_id) -> bool:
        return self._req("DELETE", f"/api/user/drafts/{draft_id}").status_code == 200

    # ── Écriture ──────────────────────────────────────────────────────────
    def save_draft(self, *, title, description, category_id, subcategory_id, options,
                   torrent: Path, nfo: Path, meta_key: str = "", meta: Optional[dict] = None,
                   note: str = "", mediainfo: str = "", slot_justification: str = "") -> Result:
        body = {
            "name": title, "title": title, "description": description,
            "categoryId": category_id, "subcategoryId": subcategory_id, "options": options,
            "tmdbData": None, "musicData": None, "rawgData": None, "bookData": None,
            "mediainfo": mediainfo or None, "uploaderNote": note or None,
            "slotJustification": slot_justification or None,
            "torrentFileName": torrent.name,
            "torrentFileData": base64.b64encode(torrent.read_bytes()).decode(),
            "nfoFileName": nfo.name,
            "nfoFileData": base64.b64encode(nfo.read_bytes()).decode(),
        }
        if meta_key and meta:
            body[meta_key] = meta
        r = self._req("POST", "/api/user/drafts", json=body)
        if r.status_code in (200, 201):
            return Result(True, "Brouillon enregistré sur C411. Pour le reprendre : page d'upload › bouton "
                                "« Brouillons » › choisis ce brouillon.", f"{BASE}/upload")
        return Result(False, "Brouillon refusé : " + self._error(r))

    def upload(self, *, title, description, category_id, subcategory_id, options,
               torrent: Path, nfo: Path, meta_key: str = "", meta: Optional[dict] = None,
               note: str = "", mediainfo: str = "", slot_justification: str = "") -> Result:
        data = {"title": title, "description": description,
                "categoryId": str(category_id), "subcategoryId": str(subcategory_id),
                "options": json.dumps(options)}
        if meta_key and meta:
            data[meta_key] = json.dumps(meta)
        if note:
            data["uploaderNote"] = note
        if slot_justification:
            data["slotJustification"] = slot_justification
        with open(torrent, "rb") as tf, open(nfo, "rb") as nf:
            files = {"torrent": (torrent.name, tf, "application/x-bittorrent"),
                     "nfo": (nfo.name, nf, "text/plain")}
            r = self._req("POST", "/api/torrents", data=data, files=files, timeout=180)
        if r.status_code in (200, 201):
            try:
                j = r.json()
            except ValueError:
                j = {}
            d = j.get("data", j) if isinstance(j, dict) else {}
            url = d.get("url") or d.get("link") or ""
            ih = d.get("infoHash") or d.get("slug") or ""
            if url and not url.startswith("http"):
                url = BASE + url
            elif not url and ih:
                url = f"{BASE}/torrents/{ih}"
            return Result(True, j.get("message") or "Torrent publié.", url)
        return Result(False, "Publication refusée : " + self._error(r))
