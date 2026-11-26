"""Assistant de Forge411 en données de démonstration, pour les captures du README et du wiki (tools/screenshots.py).

Sources factices et réponses enregistrées de tests/test_e2e.py (MediaInfo, tags audio, TMDB, MusicBrainz,
Open Library, RAWG) ; C411 simulé (options, releases existantes, catalogue) ; affiches dessinées ici. Aucun
appel réseau, aucun compte : les fichiers sont créés sous C:\\Users\\Public\\Forge411-demo\\sources.
"""

import functools
import hashlib
import io
import shutil
import threading
from pathlib import Path
from unittest import mock

from forge411.api import OptionType, Release

from tests import test_e2e as E

# Fiche → affiche dessinée : (titre, sous-titre, couleurs du dégradé, format)
POSTERS = {
    "image.tmdb.org": ("Big Buck Bunny", "2008", ((52, 120, 70), (16, 40, 28)), (500, 750)),
    "coverartarchive.org": ("Discovery", "Daft Punk", ((40, 40, 70), (10, 10, 24)), (500, 500)),
    "covers.openlibrary.org": ("Le Comte de Monte-Cristo", "Alexandre Dumas", ((120, 40, 30), (40, 12, 10)),
                               (500, 750)),
    "media.rawg.io": ("Celeste", "2018", ((90, 50, 140), (20, 14, 50)), (800, 450)),
}


_LOCK = threading.Lock()


def poster(url: str) -> bytes:
    """Affiche de démonstration (dégradé + titre), au format de la base d'origine. Appelée par plusieurs fils à la
    fois (vignette de la liste et grande image) : un verrou, FreeType n'étant pas sûr entre fils."""
    with _LOCK:
        return _poster(url)


@functools.lru_cache(maxsize=None)
def _poster(url: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    host = next((h for h in POSTERS if h in url), "")
    title, sub, (top, bottom), (w, h) = POSTERS.get(host, ("Forge411", "démo", ((0, 120, 90), (0, 30, 24)), (500, 750)))
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(top, bottom)))
    seed = int(hashlib.sha1(url.encode()).hexdigest()[:6], 16)
    for i in range(14):                                   # quelques formes décoratives, fixes pour une même fiche
        x, y, r = (seed * (i + 3)) % w, (seed * (i + 7)) % h, 20 + (seed >> i) % 90
        d.ellipse([x - r, y - r, x + r, y + r], outline=tuple(min(255, c + 45) for c in top), width=2)

    def font(size, bold=False):
        for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()
    big, small = font(max(w // 11, 28), True), font(max(w // 20, 16))
    words, lines = title.split(), [""]
    for word in words:                                    # titre replié sur la largeur
        if d.textlength((lines[-1] + " " + word).strip(), font=big) > w * 0.84 and lines[-1]:
            lines.append(word)
        else:
            lines[-1] = (lines[-1] + " " + word).strip()
    y = h * 0.62
    for line in lines:
        d.text((w * 0.08, y), line, font=big, fill=(255, 255, 255))
        y += big.size * 1.15
    d.text((w * 0.08, y + 6), sub, font=small, fill=(230, 230, 230))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


def _opt(i, name, multiple, required, values):
    return OptionType(id=i, name=name, multiple=multiple, required=required,
                      values=[{"id": i * 100 + k, "value": v} for k, v in enumerate(values)])


VIDEO_OPTIONS = [
    _opt(1, "Langue", True, True, ["Multi (Français inclus)", "Français (VFF/TrueFrench)", "VOSTFR", "Anglais"]),
    _opt(5, "Genre", True, False, ["Action", "Animation", "Aventure", "Comédie", "Documentaire", "Drame", "Famille",
                                   "Fantastique", "Science Fiction"]),
    _opt(4, "Type", False, False, ["2D", "3D"]),
]


class DemoC411:
    """C411 simulé : options de catégorie, releases déjà présentes, catalogue (doublons et slots)."""

    def options(self, sub_id):
        return VIDEO_OPTIONS + [E.FakeC411.GAME_GENRES, E.FakeC411.EBOOK_GENRES]

    def existing(self, tmdb_id, kind):
        return [{"name": "Big.Buck.Bunny.2008.MULTI.1080p.WEB.H264-DEMO", "resolution": "1080p",
                 "size": 2_900_000_000, "seeders": 14},
                {"name": "Big.Buck.Bunny.2008.MULTI.2160p.WEB.H265-DEMO", "resolution": "2160p",
                 "size": 9_800_000_000, "seeders": 6}]

    def search(self, query="", tmdb_id=0, kind="", limit=25):
        return [Release("Big.Buck.Bunny.2008.MULTI.1080p.BluRay.HDLight.AC3.5.1.x264-DEMO", size=4_200_000_000,
                        seeders=9, slot="OPTI-1080-SDR-BD"),
                Release("Big.Buck.Bunny.2008.MULTI.1080p.WEB.H264-DEMO", size=2_900_000_000, seeders=14,
                        slot="COMPAT-1080-WEB"),
                Release("Big.Buck.Bunny.2008.MULTI.2160p.WEB.H265-DEMO", size=9_800_000_000, seeders=6,
                        slot="HCOPT-2160-WR-H265-HDR")]

    def categories(self):
        return []

    def drafts(self):
        return []

    def profile(self):
        raise RuntimeError("profil de démonstration fourni directement")


def sources(root: Path) -> Path:
    """Sources factices (mêmes fichiers que le test de bout en bout), recréées à chaque capture."""
    src = root / "sources"
    shutil.rmtree(src, ignore_errors=True)
    E.build_sources(src)
    return src


def patches(tmdb_key_ok: bool = True) -> list:
    """Remplacements actifs pendant toute la capture (threads de l'interface compris)."""
    tmdb = E.TMDB
    return [mock.patch.object(E.vi, "read_media", E.fake_read_media),
            mock.patch.object(E.vi, "MEDIAINFO_OK", True),
            mock.patch.object(E.audioinfo, "read_track", E.fake_read_track),
            mock.patch.object(E.translate, "to_french", lambda text: (text, "fr")),
            mock.patch("forge411.lookup.tmdb.TMDB.search",
                       lambda self, q, *a, **k: tmdb[q].search() if q in tmdb else []),
            mock.patch("forge411.lookup.tmdb.TMDB.details",
                       lambda self, m: next(c.ident for c in tmdb.values() if c.matches[0].id == m.id)),
            mock.patch("forge411.lookup.fetch_image", poster)]


def _with_images():
    """Résultats enregistrés sans image : la vignette de la liste reprend celle de la fiche."""
    import dataclasses
    for c in list(E.TMDB.values()) + [E.MUSICBRAINZ, E.RAWG]:
        if c.ident is not None:
            c.matches = [dataclasses.replace(m, image=m.image or c.ident.image) for m in c.matches]
    E.RIGHT_BOOK.image = E.RIGHT_BOOK.image or "https://covers.openlibrary.org/b/id/1-L.jpg"


def client_for(app):
    """Remplace App.client : base TMDB simulée, autres bases enregistrées."""
    from forge411.lookup.tmdb import TMDB
    _with_images()
    tmdb = TMDB("demo")
    return lambda provider: tmdb if provider == "tmdb" else E.lookup_client(provider)
