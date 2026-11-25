"""Modèles communs à tous les types de contenu."""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Source:
    """Fichier ou dossier choisi par l'utilisateur."""
    path: Path
    is_dir: bool
    files: list = field(default_factory=list)    # chemins absolus, triés
    total_size: int = 0

    @property
    def stem(self) -> str:
        return self.path.name if self.is_dir else self.path.stem

    def rel(self, f: Path) -> str:
        return f.relative_to(self.path).as_posix() if self.is_dir else f.name

    def by_ext(self, *exts: str) -> list:
        exts = {e.lower() for e in exts}
        return [f for f in self.files if f.suffix.lower() in exts]

    def ext_counts(self) -> dict:
        out = {}
        for f in self.files:
            e = f.suffix.lower()
            out[e] = out.get(e, 0) + 1
        return out


@dataclass
class Match:
    """Résultat de recherche dans une base en ligne."""
    id: str
    title: str
    year: str = ""
    subtitle: str = ""          # titre original, artiste, auteur, plateforme…
    overview: str = ""
    image: str = ""             # URL de vignette
    kind: str = ""              # film, série, album, livre, jeu…
    score: float = 0.0
    raw: dict = field(default_factory=dict)


@dataclass
class Ident:
    """Fiche identifiée (ou saisie à la main) d'une release."""
    provider: str = ""          # tmdb | musicbrainz | books | rawg | "" (manuel)
    id: str = ""
    kind: str = ""
    title: str = ""
    original_title: str = ""
    year: str = ""
    overview: str = ""
    image: str = ""             # grande image pour la présentation
    url: str = ""
    genres: list = field(default_factory=list)       # libellés
    people: list = field(default_factory=list)       # [(rôle, "Nom, Nom")]
    facts: list = field(default_factory=list)        # [(libellé, valeur)]
    payload_key: str = ""       # tmdbData | musicData | bookData | rawgData
    payload: Optional[dict] = None
    raw: dict = field(default_factory=dict)


@dataclass
class Part:
    """Composant éditable du nom de release."""
    key: str
    label: str
    value: str = ""
    choices: Optional[list] = None
    hint: str = ""
    width: int = 12


@dataclass
class Detail:
    """Information complémentaire saisie par l'utilisateur (NFO / présentation)."""
    key: str
    label: str
    value: str = ""
    multiline: bool = False
    hint: str = ""
    choices: Optional[list] = None


@dataclass
class Check:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def items(self) -> list:
        return ([("error", e) for e in self.errors] + [("warning", w) for w in self.warnings]
                + [("info", i) for i in self.infos])


# ── Formatage ─────────────────────────────────────────────────────────────

def fmt_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} Go"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} Mo"
    return f"{max(n, 0) / 1024:.0f} Ko"


def fmt_duration(ms: int) -> str:
    s = int(ms) // 1000
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h:
        return f"{h} h {m:02d} min"
    return f"{m} min {sec:02d} s" if m < 10 else f"{m} min"


def fmt_clock(seconds: float) -> str:
    s = int(round(seconds))
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def strip_accents(text: str) -> str:
    t = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def slug(text: str) -> str:
    """'L'Été meurtrier : version & co' → 'L.Ete.meurtrier.version.and.co'."""
    t = strip_accents(text).replace("&", " and ").replace("'", " ").replace("’", " ")
    t = re.sub(r"[^A-Za-z0-9]+", ".", t)
    return t.strip(".")


def clean_free(text: str) -> str:
    """Nom non pointé (jeux, applications) : sans accents ni caractères exotiques."""
    t = strip_accents(text)
    t = re.sub(r"[^A-Za-z0-9 .,()\[\]+&'_-]", "", t)
    return re.sub(r"\s+", " ", t).strip()


LANG_NAMES = {"fr": "Français", "fre": "Français", "fra": "Français", "fr-fr": "Français",
              "fr-ca": "Français (Québec)", "fr-be": "Français (Belgique)", "en": "Anglais",
              "eng": "Anglais", "es": "Espagnol", "de": "Allemand", "it": "Italien", "ja": "Japonais",
              "jpn": "Japonais", "ko": "Coréen", "pt": "Portugais", "nl": "Néerlandais",
              "zh": "Chinois", "ru": "Russe", "ar": "Arabe", "pl": "Polonais", "sv": "Suédois",
              "da": "Danois", "no": "Norvégien", "fi": "Finnois", "hi": "Hindi", "tr": "Turc"}


def lang_name(code: str) -> str:
    return LANG_NAMES.get((code or "").lower(), code or "Inconnue")
