"""
Test de bout en bout : chaque type de contenu suit le parcours complet de l'assistant (détection, analyse,
fiche, nom, NFO, présentation, options), puis le .torrent est créé et l'upload sauvegardé / repris.

Aucun accès réseau ni outil externe : MediaInfo, les tags audio et les bases en ligne (TMDB, MusicBrainz,
Open Library, RAWG, ThePornDB) sont remplacés par des réponses enregistrées. Chaque cas reprend une source
réelle du test manuel de la version 2.1.6 et verrouille le résultat attendu, bugs corrigés compris.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from forge411 import audioinfo, batch as B, session as S, translate, videoinfo as vi
from forge411.api import OptionType
from forge411.audioinfo import Track
from forge411.config import Config
from forge411.lookup.books import Books
from forge411.model import Ident, Match
from forge411.torrent import create_torrent, torrent_info
from forge411.videoinfo import AudioTrack, MediaFile, VideoTrack

ANNOUNCE = "https://c411.org/announce/demo"


# ── Réponses enregistrées ─────────────────────────────────────────────────────

def _video(path, width, height, kbps, audios, container="Matroska"):
    return MediaFile(path=Path(path), size=Path(path).stat().st_size, container=container, duration_ms=40_000,
                     video=VideoTrack(format="AVC", library="x264", width=width, height=height,
                                      bitrate=kbps * 1000, fps="24.000", bit_depth="8"),
                     audios=audios, text=f"General\nComplete name : {Path(path).name}")


def fake_read_media(path, with_text=True):
    name = Path(path).name
    if name.startswith("[Vixen]"):
        return _video(path, 3840, 2160, 12_000, [AudioTrack("AAC LC", "", "", 2, "en")], container="MPEG-4")
    vff_eng = [AudioTrack("AC-3", "", "", 6, "fr", title="VFF", bitrate=640_000),
               AudioTrack("AC-3", "", "", 6, "en", bitrate=640_000)]
    return _video(path, 1920, 1080, 9_000, vff_eng)


TRACKS = ["One More Time", "Aerodynamic", "Digital Love", "Harder, Better, Faster, Stronger"]


def fake_read_track(path, rel):
    i = int(Path(rel).name[:2])
    return Track(rel=rel, title=TRACKS[i - 1], artist="Daft Punk", album="Discovery", albumartist="Daft Punk",
                 date="2001", number=str(i), genre="Electronic", duration=330.0, bitrate=900, sample_rate=44100,
                 bits=16, channels=2, codec="FLAC", size=Path(path).stat().st_size, tag_format="Vorbis",
                 embedded_cover=True)


class FakeLookup:
    """Base en ligne : premier résultat et fiche enregistrés (aucun appel réseau)."""

    def __init__(self, matches, ident):
        self.matches, self.ident = matches, ident

    def search(self, *a, **k):
        return list(self.matches)

    def details(self, m):
        return self.ident


TMDB = {
    "Big Buck Bunny": FakeLookup(
        [Match(id="10378", title="Big Buck Bunny", year="2008", kind="movie")],
        Ident(provider="tmdb", id="10378", kind="movie", title="Big Buck Bunny", year="2008",
              overview="Un gros lapin se réveille et sort de sa tanière.", image="https://image.tmdb.org/t/p/w500/x.jpg",
              genres=["Animation", "Comédie", "Familial"], people=[("Réalisation", "Sacha Goedegebure")])),
    "Dark": FakeLookup(
        [Match(id="70523", title="Dark", year="2017", kind="tv")],
        Ident(provider="tmdb", id="70523", kind="tv", title="Dark", year="2017", overview="Quatre familles…",
              image="https://image.tmdb.org/t/p/w500/d.jpg", genres=["Crime", "Drame"])),
}
TRACKLIST = "1. One More Time (5:20)\n2. Aerodynamic (3:27)"
MUSICBRAINZ = FakeLookup(
    [Match(id="48117b90", title="Discovery", year="2001", subtitle="Daft Punk", kind="Album")],
    Ident(provider="musicbrainz", id="48117b90", kind="album", title="Discovery", year="2001",
          image="https://coverartarchive.org/release-group/48117b90/front-500", genres=["House", "Electronic"],
          overview=TRACKLIST, raw={"artist": "Daft Punk"}))
RAWG = FakeLookup(
    [Match(id="594", title="Celeste", year="2018", kind="Jeu")],
    Ident(provider="rawg", id="594", kind="game", title="Celeste", year="2018", overview="Jeu de plateforme.",
          image="https://media.rawg.io/c.jpg", genres=["Indie", "Platformer"]))
TPDB = FakeLookup([], None)                    # scène inconnue de ThePornDB : fiche manuelle

# Open Library : l'ISBN des métadonnées désigne un autre livre (cas réel), le titre donne le bon
WRONG_BOOK = Match(id="ol:wrong", title="39 leçons d'économie contemporaine", year="1998", kind="livre")
RIGHT_BOOK = Match(id="ol:right", title="Le Comte de Monte-Cristo", year="1844", subtitle="Alexandre Dumas",
                   kind="livre")


def books_client():
    b = Books()
    b._find = lambda q, author, isbn: [WRONG_BOOK] if isbn else [RIGHT_BOOK]
    b.details = lambda m: Ident(provider="books", id=m.id, kind="book", title=m.title, year=m.year,
                                overview="Edmond Dantès…", image="https://covers.openlibrary.org/b/id/1-L.jpg",
                                genres=["Fiction", "History"], people=[("Auteur", "Alexandre Dumas")])
    return b


def lookup_client(provider):
    return {"musicbrainz": MUSICBRAINZ, "rawg": RAWG, "tpdb": TPDB, "books": books_client()}.get(provider)


class FakeC411:
    GAME_GENRES = OptionType(id=9, name="Genre Jeux", multiple=True, required=False,
                             values=[{"id": 1, "value": "Action"}, {"id": 2, "value": "Plates-formes"},
                                     {"id": 3, "value": "Science-Fiction"}])
    EBOOK_GENRES = OptionType(id=8, name="Genre Ebook", multiple=True, required=False,
                              values=[{"id": 4, "value": "Science-Fiction"}, {"id": 5, "value": "Historique"}])

    def options(self, sub_id):
        return [self.GAME_GENRES, self.EBOOK_GENRES]


# ── Sources de démonstration ─────────────────────────────────────────────────

def _file(path: Path, size: int = 4096, head: bytes = b""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head + b"\0" * max(size - len(head), 0))


def _epub(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:'
                   'tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type='
                   '"application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
                   'version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   '<dc:title>Le Comte de Monte-Cristo</dc:title><dc:creator>Alexandre Dumas</dc:creator>'
                   '<dc:language>fr</dc:language><dc:publisher>Gallimard</dc:publisher><dc:date>1844</dc:date>'
                   '<dc:identifier id="id">9782070405367</dc:identifier></metadata><manifest/><spine/></package>')
        z.writestr("OEBPS/c.xhtml", "<html><body><p>Texte.</p></body></html>")


def build_sources(root: Path):
    _file(root / "Big.Buck.Bunny.2008.MULTi.1080p.BluRay.x264-NOTAG.mkv", 200_000)
    for e in (1, 2):
        _file(root / "Dark.S01.MULTi.1080p.WEB.x264-NOTAG" / f"Dark.S01E0{e}.MULTi.1080p.WEB.x264-NOTAG.mkv", 100_000)
    album = root / "Daft Punk - Discovery (2001) [FLAC]"
    for i, t in enumerate(TRACKS, 1):
        _file(album / f"0{i} - {t.split(',')[0]}.flac", 50_000, b"fLaC")
    try:
        from PIL import Image
        album.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (600, 600), (20, 20, 20)).save(album / "cover.jpg")
    except ImportError:
        _file(album / "cover.jpg", 2000, b"\xff\xd8\xff")
    _epub(root / "Alexandre.Dumas-Le.Comte.de.Monte-Cristo.FRENCH.EPUB-NOTAG.epub")
    _file(root / "Celeste.v1.4.0.0-GOG" / "setup_celeste_1.4.0.0.exe", 300_000, b"MZ")
    _file(root / "Celeste.v1.4.0.0-GOG" / "setup_celeste_1.4.0.0-1.bin", 300_000)
    _file(root / "7-Zip.24.08.x64" / "7z2408-x64.exe", 150_000, b"MZ")
    _file(root / "Super Mario World (USA)" / "Super Mario World (USA).sfc", 512 * 1024)
    _file(root / "Garmin.City.Navigator.Europe.NT.2025.10" / "gmapsupp.img", 100_000)
    for n in ("dragon_body", "dragon_head"):
        _file(root / "Articulated.Dragon.STL.Pack" / f"{n}.stl", 5_000, b"solid " + n.encode())
    _file(root / "[Vixen] 2024-03-15 Test Scene Name.mp4", 200_000)


# Résultat attendu pour chaque source : profil, statut du mode lot, nom de release exact
EXPECTED = {
    "Big.Buck.Bunny.2008.MULTi.1080p.BluRay.x264-NOTAG.mkv":
        ("video", B.READY, "Big.Buck.Bunny.2008.MULTI.VFF.1080p.BluRay.AC3.5.1.x264-NOTAG"),
    "Dark.S01.MULTi.1080p.WEB.x264-NOTAG":         # WEB + x264 sans plateforme VOD : refusé par C411
        ("video", B.ERROR, "Dark.S01.MULTI.VFF.1080p.WEB.AC3.5.1.x264-NOTAG"),
    "Daft Punk - Discovery (2001) [FLAC]":
        ("music", B.READY, "Daft.Punk.Discovery.2001.FLAC[16bit.44.1kHz]-NOTAG"),
    "Alexandre.Dumas-Le.Comte.de.Monte-Cristo.FRENCH.EPUB-NOTAG.epub":
        ("ebook", B.READY, "Le.Comte.de.Monte.Cristo.Alexandre.Dumas.FR.[EPUB]-NOTAG"),
    "Celeste.v1.4.0.0-GOG":
        ("game", B.READY, "Celeste (V1.4.0.0) [FR WIN X64][GOG]"),
    "7-Zip.24.08.x64":
        ("app", None, "7.Zip.v24.08 [WINx64 FR UNLOCKED PORTABLE]"),
    "Super Mario World (USA)":
        ("emulation", None, "Super Mario World (USA)"),
    "Garmin.City.Navigator.Europe.NT.2025.10":
        ("gps", None, "Garmin.City.Navigator.Europe.NT.2025.10.IMG"),
    "Articulated.Dragon.STL.Pack":
        ("print3d", None, "Articulated.Dragon[STL]"),
    "[Vixen] 2024-03-15 Test Scene Name.mp4":
        ("xxx", None, "[Vixen].Test.Scene.Name.2024.03.15.ENGLISH.2160p.WEB.AAC.2.0.x264-NOTAG"),
}


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.src = root / "sources"
        build_sources(cls.src)
        cls.cfg = Config(root / "config.json")
        cls.cfg.update({"output_dir": str(root / "sortie"), "translate_overview": True, "tracker_url": ANNOUNCE,
                        "team_tag_auto": False})
        patches = [mock.patch.object(vi, "read_media", fake_read_media),
                   mock.patch.object(vi, "MEDIAINFO_OK", True),
                   mock.patch.object(audioinfo, "read_track", fake_read_track),
                   mock.patch.object(translate, "to_french", lambda text: ("[traduit] " + text, "en")),
                   mock.patch("forge411.lookup.tmdb.TMDB.search", lambda self, q, *a, **k: TMDB[q].search()
                              if q in TMDB else []),
                   mock.patch("forge411.lookup.tmdb.TMDB.details", lambda self, m: next(
                       c.ident for c in TMDB.values() if c.matches[0].id == m.id))]
        for p in patches:
            p.start()
            cls.addClassCleanup(p.stop)
        from forge411.lookup.tmdb import TMDB as TmdbClient
        tmdb = TmdbClient("cle-de-test")
        clients = lambda prov: tmdb if prov == "tmdb" else lookup_client(prov)
        cls.items = {it.path.name: it for it in B.candidates(cls.src)}
        for it in cls.items.values():
            B.prepare(it, cls.cfg, FakeC411(), clients)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_source_is_found(self):
        self.assertEqual(sorted(self.items), sorted(EXPECTED))

    def test_profile_status_and_name(self):
        for name, (key, status, release) in EXPECTED.items():
            with self.subTest(source=name):
                it = self.items[name]
                self.assertEqual(it.session.profile.key, key, it.messages)
                self.assertEqual(it.session.name, release, it.messages)
                if status:
                    self.assertEqual(it.status, status, it.messages)
                else:
                    self.assertNotEqual(it.status, B.ERROR, it.messages)

    def test_known_regressions(self):
        dark = self.items["Dark.S01.MULTi.1080p.WEB.x264-NOTAG"]
        self.assertTrue(any("plateforme VOD" in m for _, m in dark.messages))
        music = self.items["Daft Punk - Discovery (2001) [FLAC]"].session
        self.assertEqual(music.ident.overview, TRACKLIST)                     # liste des pistes jamais traduite
        film = self.items["Big.Buck.Bunny.2008.MULTi.1080p.BluRay.x264-NOTAG.mkv"].session
        self.assertTrue(film.ident.overview.startswith("[traduit]"))         # un vrai résumé, lui, est traduit
        book = self.items["Alexandre.Dumas-Le.Comte.de.Monte-Cristo.FRENCH.EPUB-NOTAG.epub"].session
        self.assertEqual(book.ident.title, "Le Comte de Monte-Cristo")       # l'ISBN erroné ne l'emporte pas
        self.assertNotIn(8, book.options)                                    # Fiction ≠ Science-Fiction
        game = self.items["Celeste.v1.4.0.0-GOG"].session
        self.assertEqual(game.options.get(9), [2])                           # Platformer → Plates-formes
        xxx = self.items["[Vixen] 2024-03-15 Test Scene Name.mp4"].session
        self.assertEqual(xxx.parts["title"], "Test.Scene.Name")
        self.assertNotIn(xxx.parts["team"], ("15", "Name"))

    def test_nfo_and_description(self):
        for name, it in self.items.items():
            if it.status == B.ERROR:
                continue
            with self.subTest(source=name):
                s = it.session
                self.assertTrue(s.nfo_path and s.nfo_path.exists())
                self.assertIn(s.name, s.nfo)
                self.assertIn(s.name, s.description)

    def test_torrent_and_resume(self):
        for name, it in self.items.items():
            if it.status == B.ERROR:
                continue
            with self.subTest(source=name):
                s = it.session
                out = self.cfg.torrents_dir / f"{B.safe_name(s.name)}.torrent"
                s.infohash = create_torrent(s.src.path, ANNOUNCE, out)
                s.torrent, s.torrent_for = out, s.torrent_key
                data_name, infohash = torrent_info(out)
                self.assertEqual((data_name, infohash), (s.src.path.name, s.infohash))
                saved = Path(self.tmp.name) / "session.pkl"
                self.assertTrue(S.save(s, saved))
                self.assertFalse(S.save(S.Session(), saved))                  # démarrage : rien n'est effacé
                back = S.load(saved)
                self.assertIsNotNone(back)
                self.assertEqual((back.name, back.infohash), (s.name, s.infohash))
                self.assertTrue(back.torrent_ready)


if __name__ == "__main__":
    unittest.main()
