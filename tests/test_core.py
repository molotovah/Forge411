"""Tests du moteur (sans réseau). Lancer : python -m unittest -v"""

import hashlib
import tempfile
import threading
import unittest
from pathlib import Path

from forge411 import files, torrent
from forge411 import videoinfo as vi
from forge411.api import OptionType
from forge411.audioinfo import AudioAnalysis, Track
from forge411.model import Ident, Source, slug
from forge411.profiles import Ctx, detect, get, options_payload
from forge411.profiles.software import SoftAnalysis, _clean_title, _version, app_tags, game_mode
from forge411.scanner import parse_release_name
from forge411.videoinfo import AudioTrack, MediaFile, SubTrack, VideoAnalysis, VideoTrack


def bdecode(data: bytes):
    def dec(i):
        c = data[i:i + 1]
        if c == b"i":
            j = data.index(b"e", i)
            return int(data[i + 1:j]), j + 1
        if c == b"l":
            i, out = i + 1, []
            while data[i:i + 1] != b"e":
                v, i = dec(i)
                out.append(v)
            return out, i + 1
        if c == b"d":
            i, out = i + 1, {}
            while data[i:i + 1] != b"e":
                k, i = dec(i)
                v, i = dec(i)
                out[k] = v
            return out, i + 1
        j = data.index(b":", i)
        n = int(data[i:j])
        return data[j + 1:j + 1 + n], j + 1 + n
    value, end = dec(0)
    assert end == len(data)
    return value


def media(width=1920, height=1080, lib="x265", fmt="HEVC", audios=None, subs=None, hdr=""):
    return MediaFile(path=Path("x.mkv"), size=1000, container="Matroska", duration_ms=3_600_000,
                     video=VideoTrack(format=fmt, library=lib, width=width, height=height, hdr=hdr),
                     audios=audios if audios is not None else [AudioTrack("E-AC-3", "JOC", "", 6, "fr")],
                     subs=subs or [])


def video_ctx(kind="movie", name="Film.2020.MULTI.1080p.WEB-DL.EAC3.5.1.x265-TEAM", mf=None,
              seasons=None, episode=None, ident=None):
    mf = mf or media(audios=[AudioTrack("E-AC-3", "", "", 6, "fr"), AudioTrack("E-AC-3", "", "", 6, "en")])
    va = VideoAnalysis(videos=[mf], kind=kind, seasons=seasons or [], episode=episode,
                       parsed=parse_release_name(name))
    src = Source(path=Path(name + ".mkv"), is_dir=False, files=[], total_size=1000)
    return Ctx(src=src, analysis=va, ident=ident)


def fake_source(tmp: Path, names: list, sizes: int = 10) -> Source:
    root = tmp / "Release"
    for n in names:
        p = root / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * sizes)
    return files.scan(root)


class TorrentTests(unittest.TestCase):
    def test_piece_length_table(self):
        G, M = torrent.GiB, torrent.MiB
        self.assertEqual(torrent.piece_length_for(500 * M), M)
        self.assertEqual(torrent.piece_length_for(int(1.5 * G)), 2 * M)
        self.assertEqual(torrent.piece_length_for(int(2.5 * G)), 4 * M)
        self.assertEqual(torrent.piece_length_for(5 * G), 8 * M)
        self.assertEqual(torrent.piece_length_for(20 * G), 16 * M)

    def test_bencode_sorted_keys(self):
        self.assertEqual(torrent.bencode({"b": 1, "a": [b"x", "é"]}), b"d1:al1:x2:\xc3\xa9e1:bi1ee")

    def _check(self, src: Path):
        with tempfile.TemporaryDirectory() as out:
            t = Path(out) / "t.torrent"
            ih = torrent.create_torrent(src, "https://tracker/announce", t)
            info = bdecode(t.read_bytes())[b"info"]
            self.assertEqual(info[b"private"], 1)
            self.assertEqual(info[b"source"], b"C411")
            self.assertEqual(hashlib.sha1(torrent.bencode({k.decode(): v for k, v in info.items()})).hexdigest(), ih)
            paths = [src.joinpath(*[p.decode() for p in f[b"path"]]) for f in info[b"files"]] \
                if b"files" in info else [src]
            blob = b"".join(p.read_bytes() for p in paths)
            plen = info[b"piece length"]
            self.assertEqual(b"".join(hashlib.sha1(blob[i:i + plen]).digest() for i in range(0, len(blob), plen)),
                             info[b"pieces"])
            return info

    def test_single_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "Film.mkv"
            f.write_bytes(bytes(range(256)) * 9000)
            self.assertEqual(self._check(f)[b"length"], 256 * 9000)

    def test_folder_skips_hidden_and_system_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Serie.S01"
            (root / "Subs").mkdir(parents=True)
            for i in range(3):
                (root / f"Serie.S01E0{i + 1}.mkv").write_bytes(bytes([i]) * 1_500_000)
            (root / "Subs" / "fr.srt").write_text("1")
            (root / "Thumbs.db").write_text("x")
            (root / ".hidden").write_text("x")
            info = self._check(root)
            names = [b"/".join(f[b"path"]).decode() for f in info[b"files"]]
            self.assertEqual(names, ["Serie.S01E01.mkv", "Serie.S01E02.mkv", "Serie.S01E03.mkv", "Subs/fr.srt"])

    def test_piece_boundaries(self):
        """Lecture et calcul en parallèle : pièces exactement pleines, fichier vide entre deux autres, plus de
        pièces que de tampons (ordre des empreintes conservé)."""
        M = torrent.MiB
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Pack"
            root.mkdir()
            (root / "a.bin").write_bytes(bytes(range(256)) * (4 * M // 256))      # 4 pièces pleines
            (root / "b.bin").write_bytes(b"")
            (root / "c.bin").write_bytes(b"\x07" * (2 * M + 123))                # coupe une pièce
            self._check(root)
            one = Path(d) / "Exact.bin"
            one.write_bytes(b"\x01" * (3 * M))
            self.assertEqual(len(self._check(one)[b"pieces"]), 3 * 20)

    def test_cancel(self):
        ev = threading.Event()
        ev.set()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.mkv"
            f.write_bytes(b"x" * 10)
            with self.assertRaises(torrent.Cancelled):
                torrent.create_torrent(f, "u", Path(d) / "a.torrent", cancel=ev)


class DetectionTests(unittest.TestCase):
    def _top(self, names):
        with tempfile.TemporaryDirectory() as d:
            return detect(fake_source(Path(d), names))[0][1].key

    def test_detection(self):
        self.assertEqual(self._top(["Show.S01E01.mkv", "Show.S01E02.mkv", "Subs/fr.srt"]), "video")
        self.assertEqual(self._top(["01 - Intro.flac", "02 - Song.flac", "cover.jpg", "album.cue"]), "music")
        self.assertEqual(self._top(["Livre.epub", "Livre.pdf"]), "ebook")
        self.assertEqual(self._top(["Tome 01.cbz", "Tome 02.cbz"]), "ebook")
        self.assertEqual(self._top(["Chapitre 01.m4b"]), "ebook")
        self.assertEqual(self._top(["Game.exe", "steam_api64.dll", "data/level.pak"]), "game")
        self.assertEqual(self._top(["Jeu.nsp"]), "game")
        self.assertEqual(self._top(["setup.exe", "Crack/keygen.exe"]), "app")
        self.assertEqual(self._top(["Mario (Europe).sfc", "Zelda (Europe).sfc"]), "emulation")
        self.assertEqual(self._top(["Support.stl", "Support.3mf"]), "print3d")


class VideoTests(unittest.TestCase):
    P = get("video")

    def test_tags(self):
        self.assertEqual(vi.resolution_tag(media(1920, 800)), "1080p")
        self.assertEqual(vi.resolution_tag(media(3840, 1600)), "2160p")
        self.assertEqual(vi.resolution_tag(media(1280, 534)), "720p")
        self.assertEqual(vi.resolution_tag(media(720, 576)), "")
        fr, en, qc = AudioTrack(language="fr"), AudioTrack(language="en"), AudioTrack(language="fr-ca")
        self.assertEqual(vi.language_tag(media(audios=[fr])), "VFF")
        self.assertEqual(vi.language_tag(media(audios=[fr, en])), "MULTI.VFF")
        self.assertEqual(vi.language_tag(media(audios=[fr, qc, en])), "MULTI.VF2")
        self.assertEqual(vi.language_tag(media(audios=[en], subs=[SubTrack(language="fr")])), "VOSTFR")
        self.assertEqual(vi.language_tag(media(audios=[en], subs=[SubTrack(language="fr", forced=True)])), "")
        self.assertEqual(vi.language_tag(media(audios=[])), "MUET")
        self.assertEqual(vi.audio_tag(media(audios=[AudioTrack("E-AC-3", "JOC", "", 6, "fr")])), "EAC3.ATMOS.5.1")
        tracks = [AudioTrack("DTS", "XLL", "DTS-HD MA", 8, "en"), AudioTrack("AC-3", "", "", 6, "fr")]
        self.assertEqual(vi.audio_tag(media(audios=tracks)), "AC3.5.1")
        self.assertEqual(vi.video_codec_tag(media(lib="", fmt="HEVC"), "WEB-DL"), "H265")
        self.assertEqual(vi.hdr_tag(media(hdr="Dolby Vision / SMPTE ST 2086, HDR10 compatible")), "DV.HDR10")

    def _name(self, ctx):
        ctx.parts = {p.key: p.value for p in self.P.parts(ctx)}
        return self.P.build(ctx.parts)

    def test_movie_name(self):
        ctx = video_ctx(ident=Ident(provider="tmdb", title="Le Film", year="2020", kind="movie"))
        name = self._name(ctx)
        self.assertEqual(name, "Le.Film.2020.MULTI.VFF.1080p.WEB.EAC3.5.1.x265-TEAM")
        self.assertFalse(self.P.validate(name, ctx).ok)          # WEB + x265 : plateforme VOD obligatoire
        ctx.details = {"platform": "Amazon Prime Video"}
        self.assertTrue(self.P.validate(name, ctx).ok)

    def test_episode_and_season(self):
        mf = media(audios=[AudioTrack("AAC LC", "", "", 2, "en")], subs=[SubTrack(language="fr")])
        ctx = video_ctx("episode", "Show.S02E05.VOSTFR.1080p.WEB.x265-GRP", mf, [2], 5,
                        Ident(provider="tmdb", title="La Série", year="2024", kind="tv"))
        self.assertEqual(self._name(ctx), "La.Serie.S02E05.VOSTFR.1080p.WEB.AAC.2.0.x265-GRP")

    def test_rejects(self):
        ctx = video_ctx()
        self.assertFalse(self.P.validate("Film.2020.MULTI.1080p.WEB-DL.EAC3.5.1.x265-TEAM", ctx).ok)
        self.assertFalse(self.P.validate("Mon Film 2020 1080p", ctx).ok)
        self.assertFalse(self.P.validate("Film.2020.MULTI.1080p.WEB.x264-RARBG", ctx).ok)
        no_fr = video_ctx(mf=media(audios=[AudioTrack(language="en")]))
        self.assertFalse(self.P.validate("Film.2020.1080p.WEB.x264-T", no_fr).ok)

    def test_light_and_bitrate(self):
        from forge411.profiles.video import light_tag
        hd = media(lib="x265", fmt="HEVC")
        hd.video.bitrate = 1_725_000
        self.assertEqual(light_tag(hd, "1080p", "x265"), "HDLight")
        hd.video.bitrate = 7_000_000
        self.assertEqual(light_tag(hd, "1080p", "x265"), "")
        hd.video.bitrate = 1_725_000
        ctx = video_ctx("episode", "Show.S02E01.VOSTFR.1080p.WEB.x265-GRP",
                        media(audios=[AudioTrack("AAC LC", "", "", 2, "en")], subs=[SubTrack(language="fr")]),
                        [2], 1, Ident(provider="tmdb", title="Show", kind="tv"))
        ctx.analysis.videos[0].video.bitrate = 1_725_000
        ctx.parts = {p.key: p.value for p in self.P.parts(ctx)}
        self.assertEqual(ctx.parts["light"], "HDLight")
        self.assertFalse(self.P.validate("Show.S02E01.VOSTFR.1080p.WEBRip.AAC.2.0.x265-GRP", ctx).ok)   # sans HDLight
        self.assertTrue(self.P.validate("Show.S02E01.VOSTFR.1080p.WEBRip.HDLight.AAC.2.0.x265-GRP", ctx).ok)
        ctx.analysis.videos[0].video.bitrate = 900_000
        self.assertFalse(self.P.validate("Show.S02E01.VOSTFR.1080p.WEBRip.HDLight.AAC.2.0.x265-GRP", ctx).ok)

    def test_rules_from_wiki(self):
        ctx = video_ctx()
        self.assertFalse(self.P.validate("Film.2020.MULTI.VFF.1080p.BluRay.REMUX.DTS.HD.MA.5.1.x264-T", ctx).ok)
        self.assertFalse(self.P.validate("Film.2020.MULTI.VFF.576p.TVRip.AC3.2.0.x264-T", ctx).ok)
        p = parse_release_name("Show.S01E01.VOSTFR.FASTSUB.1080p.WEBRip.x264-T")
        self.assertEqual(vi.language_tag(media(audios=[AudioTrack(language="en")], subs=[SubTrack(language="fr")]), p),
                         "VOSTFR.FASTSUB")

    def test_tag_fixes(self):
        with tempfile.TemporaryDirectory() as d:
            src = fake_source(Path(d), ["Show.S01E01.mkv", "Show.S01E02-GRP.mkv", "fr.srt"])
            ctx = Ctx(src=src, analysis=VideoAnalysis(), name="Show.S01.VOSTFR.1080p.WEB.H264-GRP")
            fixes = self.P.tag_fixes(ctx)
            self.assertEqual([(p.name, n) for p, n in fixes], [("Show.S01E01.mkv", "Show.S01E01-GRP.mkv")])
            files.rename_files(src, fixes)
            self.assertEqual(self.P.tag_fixes(ctx), [])

    def test_options(self):
        types = [OptionType(6, "Episode", False, False, [{"id": 96, "value": "Saison complète"},
                                                         {"id": 101, "value": "Épisode 05"}]),
                 OptionType(7, "Saison", False, False, [{"id": 122, "value": "Saison 02"}]),
                 OptionType(1, "Langue", True, True, [{"id": 8, "value": "VOSTFR"}]),
                 OptionType(5, "Genre", True, False, [{"id": 39, "value": "Action"}, {"id": 44, "value": "Aventure"},
                                                      {"id": 57, "value": "Drame"}])]
        ctx = video_ctx("episode", seasons=[2], episode=5,
                        ident=Ident(provider="tmdb", genres=["Action & Adventure", "Drame"]))
        ctx.parts = {"language": "VOSTFR"}
        self.assertEqual(self.P.auto_options(types, ctx), {6: 101, 7: 122, 1: [8], 5: [39, 44, 57]})
        self.assertEqual(options_payload({1: [8], 6: 101, 5: []}), {"1": [8], "6": 101})


class MusicTests(unittest.TestCase):
    P = get("music")

    def _ctx(self, codec="FLAC", bits=16, rate=44100, bitrate=900, vbr=False, n=10, sub=18):
        a = AudioAnalysis(tracks=[Track(rel=f"{i:02d} - T{i}.flac", title=f"T{i}", artist="Daft Punk",
                                        album="Discovery", date="2001", number=str(i), genre="House", codec=codec,
                                        bits=bits, sample_rate=rate, bitrate=bitrate, vbr=vbr, duration=200,
                                        embedded_cover=True) for i in range(n)],
                          cover="cover.jpg", cover_size=(600, 600))
        src = Source(path=Path("Daft Punk - Discovery"), is_dir=True, files=[], total_size=1)
        return Ctx(src=src, analysis=a, sub_id=sub)

    def test_names(self):
        ctx = self._ctx()
        ctx.parts = {p.key: p.value for p in self.P.parts(ctx)}
        # Exemples du wiki : The.Weeknd.Blinding.Lights.2019.FLAC[16bit.44.1kHz]-NOTAG, ….MP3[320kbps]-NOTAG
        self.assertEqual(self.P.build(ctx.parts), "Daft.Punk.Discovery.2001.FLAC[16bit.44.1kHz]-NOTAG")
        self.assertTrue(self.P.validate(self.P.build(ctx.parts), ctx).ok)
        hi = self._ctx(bits=24, rate=96000)
        self.assertIn("FLAC[24bit.96kHz]", self.P.build({p.key: p.value for p in self.P.parts(hi)}))
        mp3 = self._ctx(codec="MP3", bits=0, bitrate=320)
        self.assertIn("MP3[320kbps]", self.P.build({p.key: p.value for p in self.P.parts(mp3)}))
        pod = self.P.build({"title": "Le.Bureau.des.mysteres", "integrale": "INTEGRALE", "date": "2018-2019",
                            "format": "[MP3 192 kb/s]", "team": ""})
        self.assertEqual(pod, "Le.Bureau.des.mysteres.INTEGRALE.2018-2019.[MP3 192 kb/s]-NOTAG")

    def test_rules(self):
        self.assertTrue(self.P.issues(self._ctx(codec="MP3", bits=0, bitrate=192)).errors)
        self.assertFalse(self.P.issues(self._ctx(codec="MP3", bits=0, bitrate=245, vbr=True)).errors)
        self.assertTrue(self.P.issues(self._ctx(n=1)).warnings)   # single < 20 min
        no_cover = self._ctx()
        no_cover.analysis.cover = ""
        self.assertTrue(self.P.issues(no_cover).errors)            # pochette obligatoire


class SoftwareTests(unittest.TestCase):
    def test_game_modes(self):
        self.assertEqual(game_mode(SoftAnalysis(trusted_tag="RUNE", iso=True))[0], "Nom d'origine (scène / repack)")
        self.assertEqual(game_mode(SoftAnalysis(steam_api=True))[1], ["PORTABLE", "PREACTIVATED"])
        self.assertEqual(game_mode(SoftAnalysis(gog=True, setup=True))[1], ["GOG"])
        self.assertEqual(game_mode(SoftAnalysis(setup=True))[1], ["DRM FREE"])
        self.assertIn("iso", game_mode(SoftAnalysis(iso=True))[2])

    def test_app_tags(self):
        self.assertEqual(app_tags(SoftAnalysis(keygen=True, installer=True)), ["KEYGEN"])
        self.assertEqual(app_tags(SoftAnalysis(crack=True)), ["CRACK", "PORTABLE"])
        self.assertEqual(app_tags(SoftAnalysis(installer=True)), ["UNLOCKED"])

    def test_clean_title(self):
        self.assertEqual(_clean_title("0 A.D. v0.27.0 Portable"), "0 A.D.")
        self.assertEqual(_clean_title("Hades.v1.38.290-GOG"), "Hades")
        self.assertEqual(_clean_title("7-Zip.24.08.x64"), "7-Zip")
        self.assertEqual(_clean_title("Adobe.Photoshop.2025.v26.1.Multilingual.x64-TEAM"), "Adobe Photoshop 2025")
        self.assertEqual(_clean_title("Cyberpunk 2077 [FitGirl Repack]"), "Cyberpunk 2077")
        self.assertEqual(_version("VLC media player 3.0.21 Windows"), "3.0.21")

    def test_names(self):
        g, a = get("game"), get("app")
        self.assertEqual(g.build({"mode": "Portable", "title": "Hades", "version": "1.38", "os": "WIN X64",
                                  "lang": "MULTI", "tags": "PREACTIVATED"}),
                         "Hades V1.38 [WIN X64 MULTI PORTABLE] [PREACTIVATED]")
        self.assertEqual(g.build({"mode": "GOG", "title": "DYSTHANASIA", "version": "1.0.7WA2", "os": "WIN X64",
                                  "lang": "MULTI"}), "DYSTHANASIA (V1.0.7WA2) [MULTI WIN X64][GOG]")
        self.assertEqual(g.build({"mode": "Console", "title": "The Simpsons Game", "os": "XBOX360", "region": "PAL",
                                  "lang": "FR", "container": "ISO"}), "[XBOX360]The Simpsons Game [PAL - FR] ISO")
        self.assertEqual(g.build({"mode": "Console", "title": "God of War Ragnarok", "version": "05.005", "os": "PS5",
                                  "region": "US", "lang": "MULTI", "ps_id": "PPSA08329"}),
                         "[PS5] God of War Ragnarok (v05.005)[US - MULTI]-PPSA08329")
        self.assertEqual(g.build({"vr": "[VR]", "mode": "Nom d'origine (scène / repack)",
                                  "original": "Kayak VR Mirage v10602709 -ARMGDDN"}), "[VR] Kayak VR Mirage v10602709 -ARMGDDN")
        # Exemples du wiki Applications
        self.assertEqual(a.build({"title": "Google.Earth.Pro", "version": "v7.3.6.10441", "os": "MACOSx64",
                                  "lang": "FR", "type": "CRACK"}), "Google.Earth.Pro.v7.3.6.10441 [MACOSx64 FR CRACK]")
        self.assertEqual(a.build({"title": "Fender.Studio.Pro.8", "version": "v8.0.0", "team": "R2R", "os": "WINx64",
                                  "lang": "FR", "type": "UNLOCKED"}), "Fender.Studio.Pro.8.v8.0.0-R2R [WINx64 FR UNLOCKED]")
        self.assertEqual(a.build({"title": "Dehancer.Pro.OFX", "version": "v7.4.1", "host": "DaVinci Resolve",
                                  "team": "VR", "os": "WINx64", "lang": "MULTI", "type": "CRACK"}),
                         "Dehancer.Pro.OFX.v7.4.1.(DaVinci.Resolve)-VR [WINx64 MULTI CRACK]")
        self.assertEqual(a.build({"title": "RadarBot", "version": "v9.32.24", "os": "Android", "lang": "MULTI",
                                  "ext": "APK"}), "[Android] RadarBot.v9.32.24 MULTI [APK]")


class OtherTests(unittest.TestCase):
    def test_ebook_name(self):
        e = get("ebook")   # exemples du wiki
        self.assertEqual(e.build({"title": "Shutter.Island", "author": "Dennis.Lehane", "lang": "FR", "format": "PDF",
                                  "team": ""}), "Shutter.Island.Dennis.Lehane.FR.[PDF]-NOTAG")
        self.assertEqual(e.build({"title": "Chainsaw.Man", "set": "Tome.23", "author": "Tatsuki.Fujimoto", "lang": "FR",
                                  "format": "PDF"}), "Chainsaw.Man.Tome.23.Tatsuki.Fujimoto.FR.[PDF]-NOTAG")
        self.assertEqual(e.build({"title": "Adler.Rene.Sterne", "set": "[INTEGRALE]", "lang": "FR", "format": "CBZ"}),
                         "Adler.Rene.Sterne.[INTEGRALE].FR.[CBZ]-NOTAG")
        self.assertEqual(e.build({"author": "VICTOR.HUGO", "set": "[ANTHOLOGIE]", "lang": "FR", "format": "EPUB"}),
                         "VICTOR.HUGO.[ANTHOLOGIE].FR.[EPUB]-NOTAG")

    def test_gps_and_3d(self):
        self.assertEqual(get("gps").build({"brand": "Garmin", "zone": "City Navigator Europe", "year": "2026.20",
                                           "support": "IMG"}), "Garmin.City.Navigator.Europe.2026.20.IMG")
        p3 = get("print3d")   # exemples du wiki
        self.assertEqual(p3.build({"creator": "MyPokePrint", "title": "Gengar.Pen.Holder", "formats": "[STL]"}),
                         "MyPokePrint.Gengar.Pen.Holder[STL]")
        self.assertEqual(p3.build({"pack": "[PACK]", "creator": "Titan Forge", "title": "Collection.Patreon.2024",
                                   "formats": "[STL][LYS]"}), "[PACK]Titan.Forge.Collection.Patreon.2024[STL][LYS]")

    def test_slug(self):
        self.assertEqual(slug("L'Été meurtrier : version & co"), "L.Ete.meurtrier.version.and.co")


class XxxTests(unittest.TestCase):
    """Règles du wiki C411, catégorie Adulte."""

    def _src(self, tmp: Path, root: str, names: list) -> Source:
        r = tmp / root
        for n in names:
            f = r / n
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x" * 10)
        return files.scan(r)

    def test_scene_names(self):
        x = get("xxx")
        base = {"mode": "Studio", "studio": "BadoinkVR", "pack": "", "code": "", "date": "2022.06.28",
                "title": "Her.Biggest.Fan", "performers": "Kenna.James", "category": "", "language": "ENGLISH",
                "source": "WEB", "resolution": "7K", "audio": "AAC2", "video": "x265", "team": "Tarz"}
        self.assertEqual(x.build(base),
                         "[BadoinkVR].Her.Biggest.Fan.2022.06.28.Kenna.James.ENGLISH.7K.WEB.AAC2.x265-Tarz")
        # Retour de la Team Pending : catégorie en tête, date après le titre, source après la résolution
        lez = {**base, "studio": "ExCoGiGirls", "date": "2023.12.20", "title": "Lezzzzz.Be.Friends",
               "performers": "Amber.Moore.Hannah.Roxanne", "category": "LESBIAN", "resolution": "2160p",
               "audio": "AAC.2.0", "video": "x264", "team": ""}
        self.assertEqual(x.build(lez), "[ExCoGiGirls][LESBIAN].Lezzzzz.Be.Friends.2023.12.20.Amber.Moore.Hannah."
                                       "Roxanne.ENGLISH.2160p.WEB.AAC.2.0.x264-NOTAG")
        self.assertEqual(x.build({**base, "studio": "Nubile Films", "date": "", "title": "Dating.My.Stepson.4",
                                  "performers": "", "language": "", "resolution": "1080p", "audio": "AAC.2.0",
                                  "video": "x264", "team": ""}),
                         "[Nubile Films].Dating.My.Stepson.4.1080p.WEB.AAC.2.0.x264-NOTAG")
        self.assertEqual(x.build({**base, "studio": "LoveHerFeet", "pack": "[PACK]", "date": "", "title": "Siterip.2019-2024",
                                  "performers": "", "category": "GAY", "language": "VO", "resolution": "1080p",
                                  "audio": "AAC", "team": ""}),
                         "[LoveHerFeet][GAY][PACK].Siterip.2019-2024.VO.1080p.WEB.AAC.x265-NOTAG")
        jav = {k: "" for k in base} | {"mode": "JAV", "code": "ssis-123", "title": "Hikari No Yume"}
        self.assertEqual(x.build(jav), "JAV.[SSIS-123].Hikari.No.Yume-NOTAG")

    def test_scene_order_rules(self):
        from forge411.model import Check
        x = get("xxx")
        p = {"category": "LESBIAN"}

        def errs(name, parts=p):
            c = Check()
            x._validate_order(name, parts, c)
            return " ".join(c.errors)
        old = "[ExCoGiGirls].2023.12.20.Lezzzzz.Be.Friends.Amber.Moore.LESBIAN.ENGLISH.WEB.2160p.AAC.2.0.x264-NOTAG"
        e = errs(old)
        for what in ("source doit être placée après", "en tête", "date se place après"):
            self.assertIn(what, e)
        self.assertEqual(errs("[ExCoGiGirls][LESBIAN].Lezzzzz.Be.Friends.2023.12.20.Amber.Moore.ENGLISH.2160p.WEB."
                              "AAC.2.0.x264-NOTAG"), "")

    def test_image_name(self):
        x = get("xxx")
        self.assertEqual(x.build({"studio": "ONLYFANS", "pack": "[PACK]", "title": "SophieRaiin", "performers": "",
                                  "category": "", "formats": "[JPG]", "team": ""}),
                         "[ONLYFANS][PACK].SophieRaiin.[JPG]-NOTAG")

    def test_detection_and_subcategory(self):
        with tempfile.TemporaryDirectory() as d:
            src = self._src(Path(d), "[Brazzers].2024.01.02.Scene.1080p", ["scene.mp4"])
            self.assertEqual(detect(src)[0][1].key, "xxx")
            src = self._src(Path(d), "Film.2020.1080p.WEB", ["film.mkv"])
            self.assertEqual(detect(src)[0][1].key, "video")
            for root, names, sub in (("[BadoinkVR].Scene.VR180.7K", ["a.mp4"], 56),
                                     ("[HENTAI].Serie.S01", ["e1.mkv", "e2.mkv"], 44),
                                     ("Doujin.Titre", ["t.cbz"], 44),
                                     ("[MetArt].Modele", ["1.jpg", "2.jpg"], 45),
                                     ("XXX.Game", ["game.exe", "data.rpa"], 46)):
                src = self._src(Path(d), root, names)
                x = get("xxx")
                ctx = Ctx(src=src, analysis=x.analyze(src))
                self.assertEqual(x.guess_sub(ctx), sub, root)

    def test_forbidden(self):
        from forge411.profiles.xxx import analyze, content_errors
        with tempfile.TemporaryDirectory() as d:
            a = analyze(self._src(Path(d), "Pack", ["a.mp4", "b.zip", "c.flv"]))
            self.assertTrue(any("Archives" in e for e in a.errors))
            self.assertTrue(any("FLV" in e for e in a.errors))
            a = analyze(self._src(Path(d), "Jeu", ["game.exe", "data.zip"]))
            self.assertFalse(any("Archives RAR" in e for e in a.errors))      # archives permises pour les jeux
            a = analyze(self._src(Path(d), "Mov", ["scene.mov"]))
            self.assertFalse(a.errors)                                         # MOV accepté
        self.assertTrue(content_errors("[Studio].Lolicon.Pack"))
        self.assertTrue(content_errors("Scene.Pornhub.Rip.1080p"))
        self.assertTrue(content_errors("Amateur.Couple.Video"))
        self.assertFalse(content_errors("[Brazzers].2024.01.02.Scene.1080p"))

    def test_validation(self):
        x = get("xxx")
        mf = media(audios=[AudioTrack("AAC", "", "", 2, "en")])
        va = VideoAnalysis(videos=[mf, mf], kind="pack", parsed=parse_release_name("Studio.Scene"))
        from forge411.profiles.xxx import XxxAnalysis
        src = Source(path=Path("[Studio].Scenes"), is_dir=True, files=[], total_size=1000)
        ctx = Ctx(src=src, analysis=XxxAnalysis(kind="video", video=va), sub_id=43,
                  parts={"mode": "Studio", "title": "Scenes", "resolution": "1080p", "video": "x265"})
        c = x.validate("[Studio].Scenes.ENGLISH.WEB.1080p.AAC.2.0.x265-NOTAG", ctx)
        self.assertTrue(any("[PACK]" in e for e in c.errors))
        self.assertFalse(any("française" in e for e in c.errors))              # toute langue acceptée
        ctx.parts["mode"] = "JAV"
        self.assertTrue(any("JAV" in e for e in x.validate("JAV.Titre-NOTAG", ctx).errors))
        ctx.sub_id = 44
        self.assertTrue(any("[HENTAI]" in e for e in x.validate("Serie.S01.VOSTFR.1080p.WEB.AAC.2.0.x265-NOTAG", ctx).errors))

    def test_book_and_game_names_without_duplicates(self):
        from unittest import mock
        from forge411 import batch as B
        from forge411.lookup import LookupFailed
        with tempfile.TemporaryDirectory() as d:
            for root, files_ in (("XXX.Game.v1.0", ["game.exe", "data.rpa"]), ("Doujin.Titre.EN", ["t.cbz"])):
                (Path(d) / root).mkdir()
                for f in files_:
                    (Path(d) / root / f).write_bytes(b"x" * 10)
            cfg = mock.Mock()
            cfg.get.side_effect = lambda k: ""
            cfg.nfo_dir = Path(d)
            api = mock.Mock()
            api.options.return_value = []
            names = []
            for root in ("XXX.Game.v1.0", "Doujin.Titre.EN"):
                it = B.Item(Path(d) / root)
                B.prepare(it, cfg, api, mock.Mock(side_effect=LookupFailed("x")))
                names.append(it.name)
        self.assertEqual(names[0].count("1.0"), 1)                     # version une seule fois
        self.assertEqual(names[1], "Doujin.Titre.EN.[CBZ]-NOTAG")        # langue une seule fois

    def test_options(self):
        x = get("xxx")
        types = [OptionType(1, "Langue", True, True, [{"id": 10, "value": "Anglais"}]),
                 OptionType(2, "Qualité", False, True, [{"id": 20, "value": "WEB-DL 1080"}])]
        from forge411.profiles.xxx import XxxAnalysis
        ctx = Ctx(src=None, analysis=XxxAnalysis(kind="video"),
                  parts={"language": "ENGLISH", "source": "WEB", "resolution": "1080p"})
        self.assertEqual(options_payload(x.auto_options(types, ctx)), {"1": [10], "2": 20})


class ProfileTests(unittest.TestCase):
    SAMPLE = {   # exemple de la documentation C411 (API Profil)
        "id": 48213, "username": "membre", "avatarUrl": "/avatars/48213.webp", "memberSince": "2025-03-14T09:12:44.000Z",
        "level": {"level": 37, "xp": 18420, "xpIntoLevel": 310, "xpToNextLevel": 239},
        "class": {"slug": "team_mainstream", "effectiveSlug": "team_resident_mainstream", "foundation": "seed",
                  "treeBonusBp": 250,
                  "progress": {"questsCompleted": 23, "questsTotal": 40, "stars": 2, "grade": {"tier": "argent", "level": 2}},
                  "voies": {"seed": {"star": True, "questsCompleted": 8, "questsTotal": 8},
                            "upload": {"star": False, "questsCompleted": 5, "questsTotal": 11},
                            "specialization": {"star": True, "questsCompleted": 6, "questsTotal": 6},
                            "competitivity": {"star": False, "questsCompleted": 4, "questsTotal": 15}}},
        "team": {"name": "Example Team", "slug": "example-team", "tag": "EXT", "role": "member"},
        "zen": {"balance": 1840, "totalEarned": 12650, "totalSpent": 10810},
        "transfer": {"uploaded": {"actual": 5497558138880, "credit": 107374182400, "total": 5604932321280},
                     "downloaded": {"actual": 3298534883328, "credit": 53687091200, "total": 3244847792128}},
        "download": {"allowed": True, "blockedReason": None},
        "freeleech": {"active": True, "sources": ["campaign"]}, "silverLeech": False, "leechBonuses": []}

    def test_parse(self):
        from forge411 import profile as P
        p = P.parse(self.SAMPLE, "https://c411.org")
        self.assertEqual(p.avatar_url, "https://c411.org/avatars/48213.webp")
        self.assertEqual((p.level, p.class_name, p.grade, p.tree_bonus), (37, "Team Resident Mainstream", "Argent II", 2.5))
        self.assertEqual([(v.label, v.done, v.total, v.star) for v in p.voies][0], ("Seed", 8, 8, True))
        self.assertEqual((p.team_tag, p.team_role), ("EXT", "Membre"))
        self.assertAlmostEqual(p.ratio, 5604932321280 / 3244847792128)
        self.assertEqual(P.fmt_ratio(p.ratio), "1,73")
        self.assertAlmostEqual(p.level_progress, 310 / 549)
        self.assertEqual(p.freeleech_sources, ["événement du site"])

    def test_minimal_and_formats(self):
        from forge411 import profile as P
        p = P.parse({"username": "x", "class": None, "team": None,
                     "transfer": {"uploaded": {"total": 10}, "downloaded": {"total": 0}},
                     "download": {"allowed": False, "blockedReason": "insufficient_balance"}})
        self.assertEqual((p.class_name, p.voies, p.team_name), ("", [], ""))
        self.assertIsNone(p.ratio)
        self.assertEqual(P.fmt_ratio(p.ratio), "∞")
        self.assertEqual((p.can_download, p.blocked_reason), (False, "Solde Zen insuffisant"))
        self.assertEqual(P.fmt_bytes(199566588344), "185,9 Go")      # même valeur que la page profil C411
        self.assertEqual(P.fmt_bytes(512), "512 o")


class TpdbTests(unittest.TestCase):
    UID = "0b0e1a2c-3d4e-4f50-8a6b-7c8d9e0f1a2b"
    SCENE = {"id": UID, "_id": 123, "title": "Her Biggest Fan", "date": "2022-06-28", "slug": "her-biggest-fan",
             "description": "Résumé.", "poster": "https://cdn.example/p.jpg", "duration": 1800,
             "site": {"name": "BadoinkVR"}, "performers": [{"name": "Kenna James"}], "tags": [{"name": "VR"}]}

    def _client(self, responses):
        from unittest import mock
        from forge411.lookup.tpdb import TPDB
        c = TPDB("jeton")
        c.http = mock.Mock()
        c.http.get.side_effect = lambda path, **kw: responses.get(path, {"data": []})
        return c

    def test_helpers(self):
        from forge411.lookup.tpdb import clean_query, uuid_of
        self.assertEqual(clean_query("[BadoinkVR].2022.06.28.Her.Biggest.Fan.7K.ENGLISH.WEB.AAC2.x265-Tarz"),
                         "BadoinkVR 2022 06 28 Her Biggest Fan")
        self.assertEqual(uuid_of({"id": 5, "uuid": self.UID.upper()}), self.UID)
        self.assertEqual(uuid_of({"id": 5}), "")
        from forge411.lookup.tpdb import queries
        self.assertEqual(queries("[BadoinkVR].2022.06.28.Kenna.James.Her.Biggest.Fan.VR180.ENGLISH.WEB.AAC2.x265-Tarz")[0],
                         ("parse", "BadoinkVR.22.06.28.Kenna.James.Her.Biggest.Fan"))
        self.assertEqual(queries("Dating My Stepson"), [("q", "Dating My Stepson")])

    def test_search_and_payload(self):
        c = self._client({"/scenes": {"data": [self.SCENE, {"id": 9, "title": "sans uuid"}]},
                          f"/scenes/{self.UID}": {"data": self.SCENE}})
        res = c.search("[BadoinkVR].Her.Biggest.Fan", "2022")
        self.assertEqual([m.id for m in res], [f"scene:{self.UID}"])           # résultat sans UUID ignoré
        ident = c.details(res[0])
        self.assertEqual((ident.payload_key, ident.payload), ("tpdbData", {"id": self.UID, "kind": "scene"}))
        self.assertEqual(ident.raw["performers"], ["Kenna James"])
        self.assertEqual(ident.image, "https://cdn.example/p.jpg")

    def test_xxx_provider_and_meta(self):
        from forge411.model import Ident
        from forge411.profiles.xxx import XxxAnalysis
        x = get("xxx")
        ident = Ident(provider="tpdb", id=self.UID, title="Her Biggest Fan", payload_key="tpdbData",
                      payload={"id": self.UID, "kind": "scene"},
                      raw={"site": "BadoinkVR", "performers": ["Kenna James"], "date": "2022-06-28"})
        ctx = Ctx(src=None, analysis=XxxAnalysis(kind="video"), ident=ident, sub_id=56)
        self.assertEqual(x.provider_for(ctx), "tpdb")
        self.assertEqual(x.meta(ctx)[0], "tpdbData")
        ctx.sub_id = 44                                                       # Hentai : pas de tpdbData
        self.assertIsNone(x.provider_for(ctx))
        self.assertEqual(x.meta(ctx), ("", None))
        ctx.analysis = XxxAnalysis(kind="images")
        ctx.sub_id = 43
        self.assertIsNone(x.provider_for(ctx))

    def test_scene_parts_from_tpdb(self):
        from forge411.model import Ident
        from forge411.profiles.xxx import XxxAnalysis
        mf = media(audios=[AudioTrack("AAC", "", "", 2, "en")])
        va = VideoAnalysis(videos=[mf], kind="movie", parsed=parse_release_name("scene"))
        src = Source(path=Path("scene.mp4"), is_dir=False, files=[], total_size=1000)
        ident = Ident(provider="tpdb", id=self.UID, title="Her Biggest Fan",
                      raw={"site": "BadoinkVR", "performers": ["Kenna James"], "date": "2022-06-28"})
        x = get("xxx")
        ctx = Ctx(src=src, analysis=XxxAnalysis(kind="video", video=va), ident=ident, sub_id=56)
        parts = {p.key: p.value for p in x.parts(ctx)}
        self.assertEqual((parts["studio"], parts["date"], parts["title"], parts["performers"]),
                         ("BadoinkVR", "2022.06.28", "Her.Biggest.Fan", "Kenna.James"))


class FakeResp:
    def __init__(self, status=200, json_data=None, text="", headers=None):
        self.status_code, self._j, self.text, self.headers = status, json_data, text, headers or {}

    def json(self):
        return self._j


class ClientTests(unittest.TestCase):
    def test_qbittorrent(self):
        from unittest import mock
        from forge411 import clients as CL
        calls = []

        def req(method, url, **kw):
            calls.append((method, url))
            if url.endswith("/auth/login"):
                return FakeResp(text="Ok.")
            if url.endswith("/torrents/info"):
                return FakeResp(json_data=[{"state": "checkingUP", "progress": 0.4}] if len(calls) < 6 else
                                [{"state": "stalledUP", "progress": 1}])
            if url.endswith("/torrents/add") and not any(u.endswith("/auth/login") for _, u in calls):
                return FakeResp(403)
            return FakeResp(text="Ok.")
        q = CL.QBittorrent("http://h:8080", "u", "p", "C411")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(q.s, "request", side_effect=req):
            t = Path(d) / "a.torrent"
            t.write_bytes(b"d4:infod4:name1:aee")
            q.add(t, Path(d), "ABC")                                   # 403 → connexion → nouvel essai
            self.assertIn(("POST", "http://h:8080/api/v2/auth/login"), calls)
            seen = []
            st = CL.wait_seeding(q, "ABC", seen.append, interval=0)
            self.assertTrue(st.seeding)
            self.assertEqual(seen[0].state, "Vérification")

    def test_qbittorrent5_login_204(self):
        from unittest import mock
        from forge411 import clients as CL
        q = CL.QBittorrent("http://h:8587", "ben", "pw")
        with mock.patch.object(q.s, "request", return_value=FakeResp(204, text="")):
            q._login()                                     # qBittorrent 5 : 204 sans « Ok. »
        with mock.patch.object(q.s, "request", return_value=FakeResp(200, text="Fails.")):
            with self.assertRaises(CL.ClientError):
                q._login()

    def test_transmission_session_id(self):
        from unittest import mock
        from forge411 import clients as CL
        responses = [FakeResp(409, headers={"X-Transmission-Session-Id": "xyz"}),
                     FakeResp(json_data={"result": "success", "arguments": {"torrents": [
                         {"status": 6, "percentDone": 1, "error": 0}]}})]
        t = CL.Transmission("http://h:9091")
        with mock.patch.object(t.s, "request", side_effect=lambda *a, **k: responses.pop(0)):
            st = t.status("abc")
        self.assertEqual(t.s.headers["X-Transmission-Session-Id"], "xyz")
        self.assertTrue(st.seeding)

    def test_map_path(self):
        from pathlib import PureWindowsPath as W
        from forge411.clients import map_path
        share = "\\\\192.168.1.251\\Torrents"
        self.assertEqual(map_path(W(share + "\\c411\\Film 2008"), share, "/downloads"), "/downloads/c411/Film 2008")
        self.assertEqual(map_path(W(share.lower() + "\\c411"), share + "\\", "/downloads/"), "/downloads/c411")
        self.assertEqual(map_path(W(share), share, "/downloads"), "/downloads")
        self.assertEqual(map_path(W(share + "2\\x"), share, "/downloads"), str(W(share + "2\\x")))   # dossier voisin
        self.assertEqual(map_path(W("D:\\Films"), share, "/downloads"), "D:\\Films")                # hors correspondance
        self.assertEqual(map_path(W("Z:\\c411"), "Z:\\", "/"), "/c411")
        self.assertEqual(map_path(W("D:\\Seed\\c411"), "D:\\Seed", "E:\\Seed"), "E:\\Seed\\c411")
        self.assertEqual(map_path(W("D:\\Films"), "", ""), "D:\\Films")

    def test_make(self):
        from forge411 import clients as CL
        from unittest import mock
        cfg = mock.Mock()
        cfg.get.side_effect = lambda k: ""
        self.assertIsNone(CL.make(cfg))
        cfg.get.side_effect = lambda k: {"client_kind": "deluge"}.get(k, "")
        self.assertEqual(CL.make(cfg).url, "http://localhost:8112")


class ClientSeedOptionsTests(unittest.TestCase):
    """Torrent ajouté au client : disposition d'origine, démarrage forcé, aucune limite de seed, et « en seed »
    seulement quand le client annonce vraiment au tracker."""

    def _qbit(self, handler):
        from unittest import mock
        from forge411 import clients as CL
        q = CL.QBittorrent("http://h:8080", "u", "p")
        return q, mock.patch.object(q.s, "request", side_effect=handler)

    def test_qbittorrent_add_options(self):
        sent = {}

        def req(method, url, **kw):
            if url.endswith("/torrents/add"):
                sent.update(kw.get("data") or {})
            return FakeResp(text="Ok.")
        q, patch = self._qbit(req)
        with tempfile.TemporaryDirectory() as d, patch:
            t = Path(d) / "a.torrent"
            t.write_bytes(b"d4:infod4:name1:aee")
            q.add(t, Path(d), "ABC")
        self.assertEqual(sent["contentLayout"], "Original")       # pas de sous-dossier ajouté ou retiré
        self.assertEqual(sent["skip_checking"], "false")          # données toujours vérifiées
        for k in ("ratioLimit", "seedingTimeLimit", "inactiveSeedingTimeLimit"):
            self.assertEqual(sent[k], "-1")                         # -1 : illimité (-2 : réglage global)

    def test_qbittorrent_queued_or_stopped_is_not_seeding(self):
        from forge411 import clients as CL
        for state, seeding, idle in (("queuedUP", False, True), ("stoppedUP", False, True),
                                     ("pausedUP", False, True), ("stalledUP", True, False),
                                     ("forcedUP", True, False), ("queuedDL", False, False)):
            q, patch = self._qbit(lambda m, u, **kw: FakeResp(json_data=[{"state": state, "progress": 1}]))
            with patch:
                st = q.status("abc")
            self.assertEqual((st.seeding, st.idle), (seeding, idle), state)
        self.assertNotIn("queuedUP", CL.QBittorrent.SEED_STATES)

    def test_qbittorrent_force_start_and_limits(self):
        calls = []

        def req(method, url, **kw):
            calls.append((url.rsplit("/", 1)[-1], kw.get("data") or {}))
            return FakeResp(404 if url.endswith("/torrents/start") else 200, text="Ok.")    # qBittorrent 4
        q, patch = self._qbit(req)
        with patch:
            q.ensure_active("ABC")
        names = [c[0] for c in calls]
        self.assertIn("resume", names)
        force = dict(calls)["setForceStart"]
        self.assertEqual((force["hashes"], force["value"]), ("abc", "true"))
        self.assertEqual(dict(calls)["setShareLimits"]["ratioLimit"], "-1")

    def test_transmission_seed_wait_is_not_seeding(self):
        from unittest import mock
        from forge411 import clients as CL
        t = CL.Transmission("http://h:9091")
        sent = []

        def rpc(method, args=None):
            sent.append((method, args))
            return {"torrents": [{"status": 5, "percentDone": 1, "error": 0}]}
        with mock.patch.object(t, "_rpc", side_effect=rpc):
            st = t.status("abc")
            t.ensure_active("ABC")
        self.assertFalse(st.seeding)
        self.assertTrue(st.idle)
        self.assertEqual(sent[1], ("torrent-start-now", {"ids": ["abc"]}))
        self.assertEqual(sent[2][1]["seedRatioMode"], 2)

    def test_deluge_not_auto_managed(self):
        from unittest import mock
        from forge411 import clients as CL
        d = CL.Deluge("http://h:8112", "", "pw")
        d._ready = True
        sent = []

        def call(method, *params):
            sent.append((method, params))
            if method == "core.get_torrent_status":
                return {"state": "Queued", "progress": 100.0}
            if method == "core.resume_torrents":
                raise CL.ClientError("Deluge : méthode inconnue")          # Deluge 1.3
            return True
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(d, "_call", side_effect=call):
            tor = Path(tmp) / "a.torrent"
            tor.write_bytes(b"d4:infod4:name1:aee")
            d.add(tor, Path(tmp), "ABC")
            st = d.status("abc")
            d.ensure_active("ABC")
        opts = sent[0][1][2]
        self.assertEqual((opts["auto_managed"], opts["stop_at_ratio"], opts["remove_at_ratio"]), (False, False, False))
        self.assertTrue(st.idle)
        self.assertFalse(st.seeding)
        self.assertEqual(sent[-1], ("core.resume_torrent", (["abc"],)))

    def test_readd_incomplete_torrent_rechecks(self):
        """Seedbox : torrent ajouté avant la fin du transfert, puis ajouté à nouveau une fois les fichiers
        arrivés. Déjà présent et incomplet : le client doit revérifier, sinon il reste incomplet."""
        from forge411 import clients as CL

        class Fake:
            name = "Client"

            def __init__(self, st):
                self.st, self.rechecked = st, 0

            def add(self, *a):
                raise CL.ClientError("Client : torrent déjà présent.")

            def status(self, ih):
                return self.st

            def recheck(self, ih):
                self.rechecked += 1
        for st, expected in ((CL.Status("Données incomplètes", 0.4), 1), (CL.Status("Vérification", 0.4), 0),
                             (CL.Status("En seed", 1.0, True), 0)):
            c = Fake(st)
            CL.add_or_recheck(c, Path("a.torrent"), "/dl", "abc")
            self.assertEqual(c.rechecked, expected, st.state)

    def test_duplicates_reported_as_already_present(self):
        from unittest import mock
        from forge411 import clients as CL
        t = CL.Transmission("http://h:9091")
        d = CL.Deluge("http://h:8112", "", "pw")
        d._ready = True
        with tempfile.TemporaryDirectory() as tmp:
            tor = Path(tmp) / "a.torrent"
            tor.write_bytes(b"d4:infod4:name1:aee")
            with mock.patch.object(t, "_rpc", return_value={"torrent-duplicate": {"hashString": "abc"}}):
                with self.assertRaisesRegex(CL.ClientError, "déjà présent"):
                    t.add(tor, Path(tmp), "abc")
            with mock.patch.object(d, "_call", side_effect=CL.ClientError("Deluge : Torrent already in session (abc).")):
                with self.assertRaisesRegex(CL.ClientError, "déjà présent"):
                    d.add(tor, Path(tmp), "abc")

    def test_wait_activates_once_and_reports_idle(self):
        from forge411 import clients as CL

        class Fake:
            name = "Client"
            activated = 0

            def status(self, ih):
                return CL.Status("En file (seed)", 1.0, False, "", True)

            def ensure_active(self, ih):
                self.activated += 1
        c = Fake()
        with self.assertRaises(CL.ClientError) as e:
            CL.wait_seeding(c, "abc", lambda st: None, interval=0, idle_grace=-1)
        self.assertIn("ne seed pas", str(e.exception))
        self.assertEqual(c.activated, 1)


class CatalogTests(unittest.TestCase):
    def test_family_and_compare(self):
        from forge411 import catalog as C
        from forge411.api import Release
        self.assertEqual(C.family("Film.2010.MULTI.1080p.BluRay.REMUX.AVC.DTS.HD.MA.5.1-X"), "PURE")
        self.assertEqual(C.family("Film.2010.MULTI.1080p.WEB.EAC3.2.0.H264-X"), "COMPAT")
        self.assertEqual(C.family("Film.2010.MULTI.1080p.BluRay.HDLight.EAC3.5.1.x265-X"), "OPTI")
        self.assertEqual(C.family("Film.2010.MULTI.2160p.BluRay.DV.HDR10.TrueHD.7.1.x265-X"), "HCOPT")
        rel = [Release("Film.2010.MULTI.1080p.BluRay.HDLight.EAC3.5.1.x265-X", slot="OPTI-1080-SDR-BD"),
               Release("Film.2010.MULTI.1080p.WEB.EAC3.5.1.x265-Y", slot="OPTI-1080-SDR-BD"),
               Release("Film.2010.EXTENDED.MULTI.1080p.WEB.x265-Z", slot="OPTI-1080-SDR-BD"),
               Release("Film.2010.MULTI.2160p.WEB.x265-W", slot="HCOPT-2160-WR-H265-HDR")]
        v = C.compare("Film.2010.MULTI.1080p.BluRay.HDLight.EAC3.5.1.x265-X", rel)
        self.assertEqual(len(v.exact), 1)
        v = C.compare("Film.2010.VFF.1080p.WEB.EAC3.5.1.x265-NEW", rel)
        self.assertEqual([r.name[-1] for r in v.same_slot], ["X", "Y"])
        self.assertTrue(v.needs_justification)          # EXTENDED et 2160p : autres jeux de slots


class RelocateTests(unittest.TestCase):
    def test_move_reports_bytes_and_files(self):
        """Déplacement vers un autre disque (copie) : progression en octets sur le total réel du dossier (fichiers
        ignorés par le torrent compris) et numéro du fichier, pour les tuiles vitesse / restant / fichiers."""
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "src" / "Serie.S01"
            root.mkdir(parents=True)
            (root / "e1.mkv").write_bytes(b"a" * 3000)
            (root / "e2.mkv").write_bytes(b"b" * 5000)
            (root / "Thumbs.db").write_bytes(b"x" * 100)               # ignoré par le torrent, déplacé quand même
            src = files.scan(root)
            seen = []
            with mock.patch("forge411.files.os.rename", side_effect=OSError("autre volume")):
                files.move(src, Path(d) / "seed", lambda *a: seen.append(a))
            self.assertEqual(seen[-1], (8100, 8100, 3, 3))
            self.assertEqual({t for _, t, _, _ in seen}, {8100})
            self.assertEqual(sorted({i for _, _, i, _ in seen}), [1, 2, 3])
            self.assertEqual([b for b, *_ in seen], sorted(b for b, *_ in seen))     # jamais en arrière
            self.assertEqual(src.path, Path(d) / "seed" / "Serie.S01")
            self.assertFalse(root.exists())

    def test_analysis_follows_moved_file_and_folder(self):
        va = VideoAnalysis(videos=[MediaFile(path=Path("/dl/a.mp4"))])
        files.remap_paths({"video": va}, Path("/dl/a.mp4"), Path("/seed/a.mp4"))
        self.assertEqual(va.main.path, Path("/seed/a.mp4"))
        pack = VideoAnalysis(videos=[MediaFile(path=Path("/dl/D/e1.mkv")), MediaFile(path=Path("/other/x.mkv"))])
        files.remap_paths(pack, Path("/dl/D"), Path("/seed/D"))
        self.assertEqual([v.path for v in pack.videos], [Path("/seed/D/e1.mkv"), Path("/other/x.mkv")])


class NetworkPathTests(unittest.TestCase):
    def test_host_name_and_ip_are_the_same_share(self):
        from unittest import mock
        from forge411 import clients as CL
        addrs = {"nas": {"nas", "192.168.1.251", "192.168.1.131"}, "192.168.1.251": {"192.168.1.251"}}
        with mock.patch.object(files, "_host_addrs", lambda h: frozenset(addrs.get(h, {h}))):
            seed = r"\\192.168.1.251\Torrents\Seed\c411"
            self.assertEqual(CL.map_path(seed, r"\\NAS\Torrents", "/downloads"), "/downloads/Seed/c411")
            self.assertEqual(CL.map_path(r"\\NAS\Torrents\Seed", "\\\\192.168.1.251\\Torrents\\", "/downloads"),
                             "/downloads/Seed")
            self.assertTrue(files.same_dir(r"\\nas\torrents\Seed\c411", seed))
            self.assertFalse(files.same_dir(r"\\OTHER\Torrents\Seed\c411", seed))
            self.assertEqual(CL.map_path(r"\\NAS\Films", r"\\192.168.1.251\Torrents", "/downloads"),
                             r"\\NAS\Films")


class TrackListTranslateTests(unittest.TestCase):
    def test_track_list_is_never_translated(self):
        from unittest import mock
        from forge411 import translate
        ident = Ident(provider="musicbrainz", id="x", kind="album", title="Discovery", overview="1. One More Time (5:20)")
        with mock.patch.object(translate, "to_french", side_effect=AssertionError("appel réseau")):
            translate.french_overview(ident, True)
        self.assertEqual(ident.overview, "1. One More Time (5:20)")


class CatalogExtraTests(unittest.TestCase):
    def test_same_version_other_team_and_noise(self):
        from forge411 import catalog as CAT
        from forge411.api import Release
        mine = "Daft.Punk.Discovery.2001.FLAC[16bit.44.1kHz]-NOTAG"
        found = [Release(name="Daft.Punk.Discovery.2001.FLAC[16bit.44.1kHz]-CML34", url="", size=0, seeders=1),
                 Release(name="Harry Potter à l'école des sorciers [WIN FR] [DRM FREE]", url="", size=0, seeders=1)]
        kept = CAT.relevant(found, "Discovery")
        self.assertEqual([r.name for r in kept], [found[0].name])
        v = CAT.compare(mine, kept)
        self.assertEqual(v.same_version, [found[0]])
        self.assertFalse(v.exact)


class BooksTests(unittest.TestCase):
    def test_wrong_isbn_falls_back_to_title(self):
        from unittest import mock
        from forge411.lookup.books import Books
        from forge411.model import Match
        b = Books()
        wrong = [Match(id="ol:1", title="39 leçons d'économie contemporaine", year="1998", kind="livre")]
        right = [Match(id="ol:2", title="Le Comte de Monte-Cristo", year="1844", kind="livre")]
        with mock.patch.object(b, "_find", side_effect=lambda q, a, isbn: wrong if isbn else right):
            res = b.search("Le Comte de Monte-Cristo", "", "Alexandre Dumas", "9782070405367")
        self.assertEqual([m.id for m in res], ["ol:2", "ol:1"])


class SessionResumeTests(unittest.TestCase):
    def test_empty_session_keeps_saved_upload(self):
        from forge411 import session as S
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "session.pkl"
            p.write_bytes(b"upload en cours")
            self.assertFalse(S.save(S.Session(), p))      # démarrage de l'app : session vide
            self.assertTrue(p.exists())


class GenreMatchTests(unittest.TestCase):
    def test_fiction_is_not_science_fiction(self):
        from forge411.profiles.base import pick_fuzzy
        t = OptionType(id=7, name="Genre Ebook", multiple=True, required=False,
                       values=[{"id": 1, "value": "Science-Fiction"}, {"id": 2, "value": "Hip-Hop/Rap"},
                               {"id": 3, "value": "Electro"}, {"id": 4, "value": "Roman"}])
        out = {}
        pick_fuzzy([t], out, "Genre Ebook", ["Fiction", "Hip Hop", "Electronic", "History"])
        self.assertEqual(out.get(7), [2, 3])


class GogDetectionTests(unittest.TestCase):
    def test_gog_installer_is_a_game(self):
        root = Path("/x/Celeste.v1.4.0.0-GOG")
        fl = [root / "setup_celeste_1.4.0.0.exe", root / "setup_celeste_1.4.0.0-1.bin"]
        src = Source(path=root, is_dir=True, files=fl, total_size=8_000_000)
        self.assertEqual(detect(src)[0][1].key, "game")
        from forge411.profiles.software import analyze
        self.assertTrue(analyze(src).gog)


class XxxDatedNameTests(unittest.TestCase):
    def test_studio_date_title_without_team(self):
        from forge411.profiles.xxx import XxxAnalysis, XxxProfile
        f = Path("/x/[Vixen] 2024-03-15 Test Scene Name.mp4")
        src = Source(path=f, is_dir=False, files=[f], total_size=1)
        va = VideoAnalysis(videos=[MediaFile(path=f)], parsed=parse_release_name(f.name))
        ctx = Ctx(src=src, analysis=XxxAnalysis(kind="video", video=va))
        parts = {p.key: p.value for p in XxxProfile().parts(ctx)}
        self.assertEqual(parts["title"], "Test.Scene.Name")
        self.assertEqual(parts["date"], "2024.03.15")
        self.assertNotIn(parts["team"], ("15", "Name"))


class MiscNamingTests(unittest.TestCase):
    def test_gps_keeps_year_dot_version(self):
        from forge411.profiles.misc import GpsProfile
        r = Path("/x/Garmin.City.Navigator.Europe.NT.2025.10")
        src = Source(path=r, is_dir=True, files=[r / "gmapsupp.img"], total_size=1)
        p = GpsProfile()
        parts = {x.key: x.value for x in p.parts(Ctx(src=src, analysis=p.analyze(src)))}
        self.assertEqual(parts["year"], "2025.10")

    def test_print3d_name_does_not_repeat_format(self):
        from forge411.profiles.misc import PrintProfile
        r = Path("/x/Articulated.Dragon.STL.Pack")
        src = Source(path=r, is_dir=True, files=[r / "a.stl", r / "b.stl"], total_size=1)
        p = PrintProfile()
        parts = {x.key: x.value for x in p.parts(Ctx(src=src, analysis=p.analyze(src)))}
        self.assertEqual(p.build(parts), "Articulated.Dragon[STL]")

    def test_music_tags_row_keeps_parenthesis(self):
        from forge411.profiles.music import MusicProfile
        a = AudioAnalysis(tracks=[Track(rel=f"0{i}.flac", artist="Daft Punk", album="Discovery", date="2001")
                                  for i in (1, 2)])
        rows = dict(MusicProfile().summary(Ctx(src=None, analysis=a)))
        self.assertEqual(rows["Tags"], "Daft Punk - Discovery (2001)")


class HistoryTests(unittest.TestCase):
    def test_remove_entries_and_orphan_snapshots(self):
        import json
        from forge411 import config as C
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            snap = d / "a.pkl"
            snap.write_bytes(b"x")
            a = {"date": "2026-01-01 10:00", "name": "A", "snapshot": str(snap)}
            b = {"date": "2026-01-02 10:00", "name": "B"}
            old, C.HISTORY_PATH = C.HISTORY_PATH, d / "history.jsonl"
            try:
                C.HISTORY_PATH.write_text("".join(json.dumps(x) + "\n" for x in (a, b)), encoding="utf-8")
                self.assertEqual(C.remove_history([a]), 1)
                self.assertEqual(C.read_history(), [b])
                self.assertFalse(snap.exists())
            finally:
                C.HISTORY_PATH = old


class ScreensTests(unittest.TestCase):
    def test_timestamps_and_bbcode(self):
        from forge411 import screens as S
        self.assertEqual(S.timestamps(100_000, 3), [10.0, 50.0, 90.0])
        self.assertEqual(S.timestamps(0, 3), [])
        shots = [S.Shot(Path("a.png"), url="https://img1.pixhost.to/images/1/a.png",
                        thumb="https://t1.pixhost.to/thumbs/1/a.png", page="https://pixhost.to/show/1/a.png"),
                 S.Shot(Path("b.png"), url="https://files.catbox.moe/b.png", thumb="https://files.catbox.moe/b.png")]
        b = S.bbcode(shots)
        self.assertIn("[url=https://pixhost.to/show/1/a.png][img]https://t1.pixhost.to/thumbs/1/a.png[/img][/url]", b)
        self.assertIn("[img]https://files.catbox.moe/b.png[/img]", b)

    def test_upload_pixhost_marks_adult(self):
        from unittest import mock
        from forge411 import screens as S
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.png"
            f.write_bytes(b"\x89PNG")
            sent = {}

            def post(url, **kw):
                sent.update(kw["data"])
                return FakeResp(json_data={"show_url": "https://pixhost.to/show/9/c.png",
                                           "th_url": "https://t3.pixhost.to/thumbs/9/c.png"})
            with mock.patch.object(S.requests, "post", side_effect=post):
                sh = S.upload(S.Shot(f), "pixhost", adult=True)
        self.assertEqual(sent["content_type"], "1")
        self.assertEqual(sh.url, "https://img3.pixhost.to/images/9/c.png")


class HistoryAndSessionTests(unittest.TestCase):
    def test_profile_trend(self):
        from forge411 import profile as P
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "h.jsonl"
            p = P.parse(ProfileTests.SAMPLE)
            P.record(path, p, 1_000_000)
            P.record(path, p, 1_000_100)                         # moins d'une heure : ignoré
            self.assertEqual(len(P.load_history(path)), 1)
            p2 = P.parse({**ProfileTests.SAMPLE, "level": {"level": 37, "xp": 18520, "xpIntoLevel": 410,
                                                            "xpToNextLevel": 139}})
            t = P.trend(p2, P.load_history(path), 1_000_000 + 86400)
            self.assertEqual(t.xp, 100)
            self.assertAlmostEqual(t.days_to_next, 1.39)

    def test_session_save_load(self):
        from forge411 import session as S
        with tempfile.TemporaryDirectory() as d:
            src = fake_source(Path(d), ["a.epub"])
            s = S.Session(src=src, profile=get("ebook"), name="Titre.FR.[EPUB]-NOTAG")
            path = Path(d) / "s.pkl"
            self.assertTrue(S.save(s, path))
            back = S.load(path)
            self.assertEqual((back.name, back.profile.key), (s.name, "ebook"))
            s.result = object.__new__(type("R", (), {}))
            S.save(s, path)                                     # upload terminé : sauvegarde effacée
            self.assertFalse(path.exists())


class BatchTests(unittest.TestCase):
    def test_prepare_without_network(self):
        from unittest import mock
        from forge411 import batch as B
        from forge411.lookup import LookupFailed
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Lot"
            (root / "Pack [Europe]").mkdir(parents=True)
            (root / "Pack [Europe]" / "Mario (Europe).sfc").write_bytes(b"x" * 10)
            (root / "notes.txt").write_text("x")
            items = B.candidates(root)
            self.assertEqual([i.path.name for i in items], ["Pack [Europe]"])
            cfg = mock.Mock()
            cfg.get.side_effect = lambda k: {"team_tag": "", "uploader_note": ""}.get(k, "")
            cfg.nfo_dir = Path(d)
            api = mock.Mock()
            api.options.return_value = []
            B.prepare(items[0], cfg, api, mock.Mock(side_effect=LookupFailed("x")))
            self.assertIn(items[0].status, (B.READY, B.CHECK))
            self.assertTrue(items[0].session.nfo_path.exists())


class FfmpegSetupTests(unittest.TestCase):
    ASSETS = [
        {"name": "ffmpeg-master-latest-win64-lgpl-shared.zip", "browser_download_url": "u0", "size": 1,
         "digest": "sha256:aa"},
        {"name": "ffmpeg-n8.1-latest-win64-lgpl-shared-8.1.zip", "browser_download_url": "u1", "size": 1,
         "digest": "sha256:bb"},
        {"name": "ffmpeg-n9.0-latest-win64-lgpl-shared-9.0.zip", "browser_download_url": "u2", "size": 1,
         "digest": "sha256:CC"},
        {"name": "ffmpeg-n10.0-latest-win64-lgpl-shared-10.0.zip", "browser_download_url": "u3", "size": 1},
        {"name": "ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip", "browser_download_url": "u4", "size": 1,
         "digest": "sha256:dd"}]

    def test_pick_latest_stable_verifiable(self):
        from forge411 import ffmpeg_setup as F
        a = F.pick(self.ASSETS)                 # 10.0 sans empreinte et build GPL ignorés
        self.assertEqual((a.version, a.url, a.sha256), ("9.0", "u2", "cc"))
        with self.assertRaises(F.SetupError):
            F.pick(self.ASSETS[:1])

    def _zip(self, path):
        import zipfile
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("ffmpeg-n9.0/bin/ffmpeg.exe", b"MZ ffmpeg")
            z.writestr("ffmpeg-n9.0/bin/avcodec-62.dll", b"dll")
            z.writestr("ffmpeg-n9.0/bin/ffplay.exe", b"MZ play")
            z.writestr("ffmpeg-n9.0/doc/readme.txt", b"doc")
            z.writestr("../../evil/bin/x.dll", b"dll")          # chemin hostile : aplati dans le dossier cible

    def test_extract_and_install(self):
        from unittest import mock
        from forge411 import ffmpeg_setup as F
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            archive = d / "a.zip"
            self._zip(archive)
            dest = d / "ffmpeg"
            exe = F.extract(archive, dest)
            self.assertEqual(sorted(p.name for p in dest.iterdir()), ["avcodec-62.dll", "ffmpeg.exe", "x.dll"])
            self.assertEqual(exe.read_bytes(), b"MZ ffmpeg")
            self.assertFalse((d / "evil").exists())
            data = archive.read_bytes()

            class Resp:
                status_code = 200

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def iter_content(self, n):
                    for i in range(0, len(data), 100):
                        yield data[i:i + 100]
            good = F.Asset("x.zip", "9.0", "u", len(data), hashlib.sha256(data).hexdigest())
            with mock.patch.object(F, "install_dir", return_value=d / "inst"), \
                    mock.patch.object(F.requests, "get", return_value=Resp()):
                self.assertTrue(F.install(asset=good).is_file())
                self.assertIn("9.0", (d / "inst" / "version.txt").read_text())
                with self.assertRaises(F.SetupError):
                    F.install(asset=F.Asset("x.zip", "9.0", "u", len(data), "0" * 64))
                cancel = threading.Event()
                cancel.set()
                with self.assertRaises(F.SetupError):
                    F.install(cancel=cancel, asset=good)
                self.assertFalse(list(d.glob("*.part")))                   # rien ne traîne


class UpdaterTests(unittest.TestCase):
    def test_versions(self):
        from forge411.updater import is_newer, parse_version
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("1.1.0"), parse_version("1.1"))
        self.assertTrue(is_newer("v1.0.10", "1.0.9"))
        self.assertTrue(is_newer("1.1.0", "1.0.1"))
        self.assertFalse(is_newer("v1.0.1", "1.0.1"))
        self.assertFalse(is_newer("1.0.0", "1.0.1"))
        self.assertFalse(is_newer("nightly", "1.0.1"))

    def _fake_get(self, payload: bytes):
        class Resp:
            status_code = 200
            headers = {"Content-Length": str(len(payload))}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def iter_content(self, n):
                for i in range(0, len(payload), n):
                    yield payload[i:i + n]
        return lambda *a, **kw: Resp()

    def test_download_checks_digest(self):
        from unittest import mock
        from forge411 import updater
        payload = b"MZ" + b"x" * 300_000
        good = updater.Release("9.9.9", "v9.9.9", "", "", asset_url="https://example.invalid/F.exe",
                               asset_size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        with tempfile.TemporaryDirectory() as d, mock.patch.object(updater.requests, "get", self._fake_get(payload)):
            dest = Path(d) / "Forge411.new.exe"
            self.assertEqual(updater.download(good, dest).read_bytes(), payload)
            dest.unlink()
            bad = updater.Release(**{**good.__dict__, "sha256": "0" * 64})
            with self.assertRaises(updater.UpdateError):
                updater.download(bad, dest)
            self.assertEqual(list(Path(d).iterdir()), [])     # rien ne reste en cas d'échec
            short = updater.Release(**{**good.__dict__, "sha256": "", "asset_size": len(payload) + 1})
            with self.assertRaises(updater.UpdateError):
                updater.download(short, dest)

    def test_finish_update_replaces_target(self):
        from unittest import mock
        from forge411 import updater
        with tempfile.TemporaryDirectory() as d:
            new, target = Path(d) / updater.UPDATE_NAME, Path(d) / "Forge411.exe"
            new.write_bytes(b"MZnew")
            target.write_bytes(b"MZold")
            launched = []
            with mock.patch.object(updater.sys, "executable", str(new)), \
                    mock.patch.object(updater, "_launch", lambda exe, *a: launched.append((Path(exe).name, a))):
                self.assertEqual(updater.finish_update([str(target)], window=False), 0)
            self.assertEqual(target.read_bytes(), b"MZnew")
            self.assertEqual(launched, [("Forge411.exe", ("--cleanup-update", str(new.resolve())))])


class RulesTests(unittest.TestCase):
    def test_screenshots_and_hosts(self):
        from forge411 import rules as R
        banner = "https://cdn.theporndb.net/scene/a.jpg"
        desc = (f"[img]{banner}[/img][img]https://i.postimg.cc/a/1.png[/img][img]https://i.postimg.cc/a/2.png[/img]"
                "[img]https://img1.pixhost.to/images/1/3.png[/img][img]https://thumb.theporndb.net/x.jpg[/img]")
        rule = R.ShotRule(minimum=3, hosts=R.XXX_SHOT_HOSTS, hosts_label="postimg.cc ou zupimages.net")
        c = R.check_description(desc, rule, banner)
        self.assertTrue(any("thumb.theporndb.net" in e for e in c.errors))     # non affichée par C411
        self.assertTrue(any("2 sur 3" in e for e in c.errors))                 # pixhost ne compte pas en XXX
        ok = desc.replace("img1.pixhost.to/images/1", "i.postimg.cc/b").replace(
            "[img]https://thumb.theporndb.net/x.jpg[/img]", "")
        self.assertEqual(R.check_description(ok, rule, banner).errors, [])
        self.assertEqual(R.check_description("[img]https://image.tmdb.org/p.jpg[/img]", R.ShotRule(minimum=3)).errors[0][:22],
                         "Captures d'écran : 0 s")

    def test_profile_rules(self):
        from forge411.profiles.base import Ctx
        from forge411.model import Source
        from types import SimpleNamespace as N
        src = Source(Path("a.mkv"), False, [Path("a.mkv")])
        self.assertEqual(get("game").shot_rule(Ctx(src=src)).minimum, 3)
        self.assertEqual(get("app").shot_rule(Ctx(src=src)).minimum, 2)
        x = get("xxx")
        one = Ctx(src=src, analysis=N(kind="video", video=N(videos=[1])), name="[S].T.1080p.WEB-NOTAG")
        self.assertEqual(x.shot_rule(one).minimum, 3)
        pack = Ctx(src=src, analysis=N(kind="video", video=N(videos=[1, 2])), name="[S][PACK].T-NOTAG")
        self.assertEqual(x.shot_rule(pack).minimum, 4)


class CorrectionTests(unittest.TestCase):
    MSG = ("Merci pour l'upload, mais voici des points à corriger avant validation : 1. ➡️ Description XXX / "
           "Screenshots - ❌ : Il faut au minimum 3 screenshot(s) hors images bannières dans la description XXX "
           "(détecté 0) - 🛠️ : Utilise postimg.cc ou zupimages.net 2. ➡️ Nommage XXX > Films - ❌ : La Source doit "
           "être placée après la résolution dans le titre. 3. ➡️ Disponibilite du torrent - ❌ : Il n'y a aucun Seed "
           "sur le torrent, attention ! 4. Le tag LESBIAN doit être au début [LESBIAN]. Merci de mettre la date après "
           "le titre. Merci d'avance pour la correction 🙏 ℹ️ Retrouve la documentation et les guides dans le wiki")

    def test_parse(self):
        from forge411 import correction as F
        pts = F.parse(self.MSG)
        self.assertEqual([p.step for p in pts], [F.STEP_PREZ, F.STEP_NAME, F.STEP_PUBLISH, F.STEP_NAME])
        self.assertEqual(F.shots_needed(pts), 3)
        self.assertEqual(F.infohash_of("https://c411.org/torrents/9FB0A873A8943D967ACE770D0585E81FDA181203"),
                         "9fb0a873a8943d967ace770d0585e81fda181203")

    def test_torrent_info_roundtrip(self):
        from forge411.torrent import create_torrent, torrent_info
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "video.mkv"
            f.write_bytes(b"x" * 5000)
            ih = create_torrent(f, "https://t/a", Path(d) / "a.torrent")
            self.assertEqual(torrent_info(Path(d) / "a.torrent"), ("video.mkv", ih))


class ClientHelpTests(unittest.TestCase):
    def test_mapping_suggestion(self):
        from forge411 import clients as C
        self.assertEqual(C.unc_host(r"\\192.168.1.251\Torrents\Seed"), "192.168.1.251")
        self.assertEqual(C.suggest_mapping(r"\\NAS\Torrents\Seed\c411", "/downloads/complete"),
                         (r"\\NAS\Torrents", "/downloads"))
        self.assertEqual(C.suggest_mapping(r"D:\Seed", "/downloads"), ("", ""))
        self.assertFalse(C.is_local("http://192.168.1.251:8587"))
        self.assertTrue(C.is_local("http://localhost:8080"))

    def test_copy_file_progress(self):
        from forge411.files import copy_file
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            a.write_bytes(b"y" * 40_000_000)
            seen = []
            copy_file(a, b, seen.append)
            self.assertEqual(b.stat().st_size, 40_000_000)
            self.assertEqual(seen[-1], 40_000_000)



class CoverSizeTests(unittest.TestCase):
    """Image de fiche au format de sa base : une pochette d'album carrée n'est plus recadrée en affiche."""

    def test_shapes(self):
        from forge411.ui.steps import cover_size
        for scale in (1, 2, 3):
            w, h = cover_size("musicbrainz", scale)
            self.assertEqual(w, h)
            w, h = cover_size("rawg", scale)
            self.assertGreater(w, h)
            for prov in ("tmdb", "books", "tpdb", ""):
                w, h = cover_size(prov, scale)
                self.assertLess(w, h)


class ShotsMissingTests(unittest.TestCase):
    """Encart « Ajouter des captures » : affiché sous le minimum exigé, ou si des captures conseillées manquent."""

    def test_required_and_recommended(self):
        from forge411.rules import ShotRule, shots_missing
        img = lambda n: "".join(f"[img]https://i.imgur.com/{i}.png[/img]" for i in range(n))
        self.assertEqual(shots_missing(img(1), ShotRule(minimum=3)), (1, 3, True))
        self.assertIsNone(shots_missing(img(3), ShotRule(minimum=3)))
        self.assertEqual(shots_missing("", ShotRule(recommended=4)), (0, 4, False))
        self.assertIsNone(shots_missing(img(1), ShotRule(recommended=4)))
        self.assertIsNone(shots_missing("", ShotRule()))


class ChartAxisTests(unittest.TestCase):
    """Courbe de vitesse : graduations rondes en Mo/s (pas « 7.157 Mo/s ») et lissage sans dépassement."""

    def test_axis_round_ticks(self):
        from forge411.ui.widgets import axis
        self.assertEqual(axis(134.4 * 1024 ** 2), (1024 ** 2, "Mo", 50, 150))
        self.assertEqual(axis(2.2 * 1024 ** 3)[1:], ("Go", 1.0, 3.0))
        unit, name, step, top = axis(9.8 * 1024 ** 2)
        self.assertTrue(3 <= top / step <= 5)

    def test_smooth_curve_stays_in_range(self):
        from forge411.ui.widgets import smooth_curve
        pts = [(i * 10.0, y) for i, y in enumerate([50, 50, 5, 95, 50, 50])]
        out = smooth_curve(pts)
        self.assertGreater(len(out), len(pts))
        self.assertTrue(all(5 <= y <= 95 for _, y in out))
        self.assertEqual(out[0], pts[0])
        self.assertEqual(out[-1], pts[-1])


class SpeedChartDataTests(unittest.TestCase):
    """Courbe de vitesse : au plus 2 x points valeurs, quelle que soit la durée (coût d'affichage constant)."""

    def test_points_stay_bounded_and_average_kept(self):
        from unittest import mock
        from forge411.ui import widgets as W
        c = mock.Mock(spec=W.SpeedChart)
        c.points = 10
        W.SpeedChart.reset(c)
        for i in range(1000):
            W.SpeedChart.add(c, 100.0)
        self.assertLess(len(c.vals), 2 * c.points)
        self.assertTrue(all(v == 100.0 for v in c.vals))

class UpdateNotesTests(unittest.TestCase):
    def test_changelog_sections(self):
        from forge411.updater import changelog_sections
        text = ("# Changelog\n\n## [2.2.0] - 2026-12-01\n### Ajouté\n- A\n\n## [2.1.1] - 2026-11-25\n- B\n\n"
                "## [2.1.0] - 2026-11-20\n- C\n")
        self.assertEqual([v for v, _, _ in changelog_sections(text, "2.1.0")], ["2.2.0", "2.1.1"])
        self.assertEqual([v for v, _, _ in changelog_sections(text, "2.1.0", "2.1.1")], ["2.1.1"])
        self.assertEqual(changelog_sections(text, "2.1.0")[0][2], "### Ajouté\n- A")

    def test_summary_for_banner(self):
        """Bandeau et notification de mise à jour : première nouveauté, Markdown retiré, coupée à un mot."""
        from forge411.updater import summary
        notes = "### Ajouté\n- **Publication** : vitesse et `temps restant` du hachage.\n- Autre chose."
        self.assertEqual(summary(notes), "Publication : vitesse et temps restant du hachage.")
        long = summary("- " + "mot " * 80, limit=40)
        self.assertTrue(long.endswith("…") and len(long) <= 40 and not long[:-1].endswith(" "))
        self.assertEqual(summary(""), "")

    def test_theme_dark_by_default(self):
        from forge411.config import Config
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text('{"theme": "system"}', encoding="utf-8")
            self.assertEqual(Config(p).get("theme"), "dark")            # jamais choisi : sombre
            p.write_text('{"theme": "light", "theme_chosen": true}', encoding="utf-8")
            self.assertEqual(Config(p).get("theme"), "light")           # choix conservé



class CategoryTests(unittest.TestCase):
    def test_category_from_tpdb(self):
        from forge411.profiles.xxx import category_from_tpdb
        self.assertEqual(category_from_tpdb({"tags": ["69", "Lesbian"]}), "LESBIAN")
        self.assertEqual(category_from_tpdb({"tags": [], "genders": ["female", "female", "female"]}), "LESBIAN")
        self.assertEqual(category_from_tpdb({"tags": ["Transgender"]}), "TRANS")
        self.assertEqual(category_from_tpdb({"tags": [], "genders": ["female", "male"]}), "")



class TranslateTests(unittest.TestCase):
    def test_names_are_protected(self):
        from forge411.translate import protect, restore
        text = "Totals: Hannah Blue - 2, Roxanne White - 3. Amber kisses Hannah at ExCoGiGirls."
        masked, table = protect(text, ["Amber Moore", "Hannah", "Roxanne", "ExCoGiGirls"])
        for name in ("Hannah", "Blue", "White", "Amber", "ExCoGiGirls"):
            self.assertNotIn(name, masked)
        self.assertEqual(restore(masked, table), text)


if __name__ == "__main__":
    unittest.main()
